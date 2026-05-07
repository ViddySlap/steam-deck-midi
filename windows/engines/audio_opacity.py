"""Audio opacity engine.

Listens to the comp-level `Audio Engine` Wire patch on DECK_OUT (CC 100-113
on ch15 by default) and drives the VIDEO + LOGO group masters via OSC by
default (or MIDI CCs on DECK_IN if `outputs.protocol` is set to "midi").

Three layers stack to produce the output:

1. **Natural state machine** — runs continuously based on audio + ENGINE
   ENABLE. Handles bass-rising (LOGO falls via ATTACK → wait VIDEO DELAY →
   VIDEO rises via ATTACK) and bass-falling (VIDEO falls via RELEASE → wait
   LOGO DELAY → LOGO rises via RELEASE), gated by the DURATION debounce on
   the falling side. The debounce window holds VIDEO regardless of how we
   got there, so a stomp during the window recovers cleanly on release.

2. **Stomp audio override** — mirrors the v0.2.0 wire patch which literally
   pinned the audio signal while a stomp was held. LOGO STOMP held → the
   natural state machine sees an effective audio average of 0 (drifts to
   LOGO via the normal debounce + LOGO_DELAY + RELEASE pacing). VIDEO STOMP
   held → effective audio = 1 (engine snaps to VIDEO instantly via the
   bass-rising sequence). Both held → real audio (mask kills both visually
   anyway).

3. **Stomp output mask** — applied at send time. VIDEO STOMP held → kill the
   logo channel. LOGO STOMP held → kill the video channel. Both held → kill
   both. Mirrors the wire patch's piano-mode mapping of each STOMP to the
   opposite group's bypass parameter.

The override (#2) and the mask (#3) both fire while a stomp is held. The
override drives the natural state toward the stomp's target so by the time
the operator releases, the engine is already settled correctly.

**ALWAYS toggles** — `LOGO ALWAYS` overrides 0.0 logo endpoints in a
natural-VIDEO sequence to 1.0 (logo rides at full opacity even when audio
is loud); `VIDEO ALWAYS` does the symmetric thing for natural-LOGO. Stomps
override ALWAYS for the drop direction (LOGO STOMP kills video even with
VIDEO ALWAYS lock); ALWAYS still locks the same-side channel high.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Callable

from windows.engines.base import Engine
from windows.engines.osc_client import OscClient
from windows.midi import MidiOut

LOGGER = logging.getLogger(__name__)


def _midpoint_bool(value: int) -> bool:
    return value > 63


# Goal states the engine can be transitioning toward.
GOAL_OFF = "off"            # engine disabled → (1, 1)
GOAL_BLACKOUT = "blackout"  # both stomps held → (0, 0)
GOAL_VIDEO = "video"        # bass loud or video stomp → (1, 0)
GOAL_LOGO = "logo"          # bass quiet or logo stomp → (0, 1)

# Phase kinds in a transition sequence.
PHASE_SNAP = "snap"    # instant: set values, advance immediately
PHASE_RAMP = "ramp"    # linear interpolate over duration
PHASE_DELAY = "delay"  # hold values for duration
PHASE_IDLE = "idle"    # no transition in progress


class AudioOpacityEngine(Engine):
    type_name = "audio_opacity"

    def __init__(
        self,
        name: str,
        config: dict,
        midi_out: MidiOut,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(name, config, midi_out, clock=clock)

        inputs = config.get("inputs", {})
        outputs = config.get("outputs", {})
        defaults = config.get("defaults", {})

        # Inputs
        self._input_channel = int(inputs.get("channel", 14))
        self._cc_audio = int(inputs.get("cc_audio", 100))
        self._cc_enable = int(inputs.get("cc_enable", 101))
        self._cc_video_stomp = int(inputs.get("cc_video_stomp", 102))
        self._cc_logo_stomp = int(inputs.get("cc_logo_stomp", 103))
        self._cc_tipping = int(inputs.get("cc_tipping", 104))
        self._cc_duration = int(inputs.get("cc_duration", 105))
        self._cc_attack = int(inputs.get("cc_attack", 106))
        self._cc_release = int(inputs.get("cc_release", 107))
        self._cc_video_delay = int(inputs.get("cc_video_delay", 108))
        self._cc_logo_delay = int(inputs.get("cc_logo_delay", 109))
        self._cc_video_always = int(inputs.get("cc_video_always", 112))
        self._cc_logo_always = int(inputs.get("cc_logo_always", 113))
        self._duration_max_seconds = float(inputs.get("duration_max_seconds", 5.0))
        self._attack_max_seconds = float(inputs.get("attack_max_seconds", 5.0))
        self._release_max_seconds = float(inputs.get("release_max_seconds", 5.0))
        self._video_delay_max_seconds = float(inputs.get("video_delay_max_seconds", 5.0))
        self._logo_delay_max_seconds = float(inputs.get("logo_delay_max_seconds", 5.0))

        # Outputs
        self._output_protocol = str(outputs.get("protocol", "osc")).lower()
        osc = outputs.get("osc", {})
        self._osc_host = str(osc.get("host", "127.0.0.1"))
        self._osc_port = int(osc.get("port", 7000))
        self._osc_video_path = str(osc.get("video_path", "/composition/groups/1/master"))
        self._osc_logo_path = str(osc.get("logo_path", "/composition/groups/2/master"))
        self._osc: OscClient | None = (
            OscClient(self._osc_host, self._osc_port) if self._output_protocol == "osc" else None
        )
        self._output_channel = int(outputs.get("channel", 0))
        self._cc_video_master = int(outputs.get("cc_video_master", 110))
        self._cc_logo_master = int(outputs.get("cc_logo_master", 111))

        # Tunable defaults
        self._sample_size = int(config.get("sample_size", 8))
        self._update_hz = float(config.get("update_hz", 30.0))
        self._tipping_point = float(defaults.get("tipping_point", 0.65))
        self._duration_seconds = float(defaults.get("duration_seconds", 1.0))
        self._attack_seconds = float(defaults.get("attack_seconds", 0.0))
        self._release_seconds = float(defaults.get("release_seconds", 1.0))
        self._video_delay_seconds = float(defaults.get("video_delay_seconds", 0.0))
        self._logo_delay_seconds = float(defaults.get("logo_delay_seconds", 1.0))

        # State
        self._enabled = False
        self._video_stomp = False
        self._logo_stomp = False
        self._video_always = False
        self._logo_always = False
        self._audio_buffer: deque[float] = deque(maxlen=self._sample_size)
        self._below_since: float | None = None

        # Master values (smoothed 0-1)
        self._current_video = 1.0
        self._current_logo = 1.0

        # Phase machine. ALWAYS flags ride along in the goal tuple so toggling
        # either flag mid-state triggers a sequence rebuild that picks up the
        # new override.
        self._current_goal: tuple[str, str, bool, bool] = (GOAL_OFF, "engine", False, False)
        self._pending_phases: list[tuple[str, float, float, float]] = []
        self._phase = PHASE_IDLE
        self._phase_video_start = 1.0
        self._phase_logo_start = 1.0
        self._phase_video_end = 1.0
        self._phase_logo_end = 1.0
        self._phase_duration = 0.0
        self._phase_started_at = 0.0

        # Output dedupe
        self._last_video_sent: int | None = None
        self._last_logo_sent: int | None = None
        self._last_tick = 0.0
        self._initial_send_pending = True

    # ------------------------------------------------------------------
    # Inputs

    def on_midi_in(self, channel: int, cc: int, value: int, now: float) -> None:
        if channel != self._input_channel:
            return
        # CCs split into three buckets:
        #   - goal_relevant: changes the natural goal computation. Recompute,
        #     rebuild sequence, advance phase, emit. Bypasses the tick rate
        #     limit so e.g. ENGINE ENABLE flipping reacts instantly.
        #   - mask_relevant: stomps. The natural state machine ignores them
        #     entirely; they're an output mask applied at send time. Inline
        #     output update so a tap takes effect on the next frame, not the
        #     next tick boundary.
        #   - other: tuning knobs. No immediate action; tick picks them up.
        goal_relevant = False
        mask_relevant = False
        if cc == self._cc_audio:
            self._audio_buffer.append(value / 127.0)
        elif cc == self._cc_enable:
            self._enabled = _midpoint_bool(value)
            goal_relevant = True
        elif cc == self._cc_video_stomp:
            self._video_stomp = _midpoint_bool(value)
            mask_relevant = True
        elif cc == self._cc_logo_stomp:
            self._logo_stomp = _midpoint_bool(value)
            mask_relevant = True
        elif cc == self._cc_tipping:
            self._tipping_point = value / 127.0
        elif cc == self._cc_duration:
            self._duration_seconds = (value / 127.0) * self._duration_max_seconds
        elif cc == self._cc_attack:
            self._attack_seconds = (value / 127.0) * self._attack_max_seconds
        elif cc == self._cc_release:
            self._release_seconds = (value / 127.0) * self._release_max_seconds
        elif cc == self._cc_video_delay:
            self._video_delay_seconds = (value / 127.0) * self._video_delay_max_seconds
        elif cc == self._cc_logo_delay:
            self._logo_delay_seconds = (value / 127.0) * self._logo_delay_max_seconds
        elif cc == self._cc_video_always:
            self._video_always = _midpoint_bool(value)
            goal_relevant = True
        elif cc == self._cc_logo_always:
            self._logo_always = _midpoint_bool(value)
            goal_relevant = True

        if goal_relevant or mask_relevant:
            # Stomps go through the same path as goal-relevant CCs because
            # they now override the natural-state-machine's effective audio
            # (wire-patch v0.2.0 behavior). The override changes wanted, so a
            # rebuild may be needed.
            wanted = self._compute_wanted(now)
            if wanted != self._current_goal:
                self._pending_phases = self._build_sequence(
                    wanted[0], wanted[1], wanted[2], wanted[3]
                )
                self._current_goal = wanted
                self._start_next_phase(now)
                self._execute_phase(now)
            self._emit_output()

    def tick_interval_seconds(self) -> float:
        return 1.0 / self._update_hz

    # ------------------------------------------------------------------
    # Tick / state machine

    def tick(self, now: float) -> None:
        if self._initial_send_pending:
            self._send_if_changed(127, 127)
            self._initial_send_pending = False
            self._last_tick = now
            return

        interval = 1.0 / self._update_hz
        if (now - self._last_tick) < interval:
            return
        self._last_tick = now

        wanted = self._compute_wanted(now)
        if wanted != self._current_goal:
            self._pending_phases = self._build_sequence(
                wanted[0], wanted[1], wanted[2], wanted[3]
            )
            self._current_goal = wanted
            self._start_next_phase(now)

        self._execute_phase(now)
        self._emit_output()

    def _emit_output(self) -> None:
        """Apply the stomp mask and send if the integer output changed.

        The natural state machine (current_video, current_logo) tracks what
        the audio engine would emit unconditionally. Stomps don't touch it —
        they apply only at send time as an output mask, mirroring how the
        v0.2.0 wire patch had VIDEO/LOGO STOMP MIDI-mapped to group bypass
        in piano mode. Stomp release reveals the natural state instantly
        because the engine has been tracking it the whole time.
        """
        out_video, out_logo = self._apply_stomp_mask(
            self._current_video, self._current_logo
        )
        video_int = max(0, min(127, int(round(out_video * 127))))
        logo_int = max(0, min(127, int(round(out_logo * 127))))
        self._send_if_changed(
            video_int, logo_int, video_float=out_video, logo_float=out_logo
        )

    def _apply_stomp_mask(
        self, video: float, logo: float
    ) -> tuple[float, float]:
        if self._video_stomp and self._logo_stomp:
            return (0.0, 0.0)
        if self._video_stomp:
            # VIDEO STOMP zeroes the LOGO channel — matches the v0.2.0 wire
            # patch's piano-mode mapping of VIDEO STOMP → LOGO group bypass.
            return (video, 0.0)
        if self._logo_stomp:
            return (0.0, logo)
        return (video, logo)

    def _compute_wanted(self, now: float) -> tuple[str, str, bool, bool]:
        v_always = self._video_always
        l_always = self._logo_always

        if not self._enabled:
            return (GOAL_OFF, "engine", v_always, l_always)

        # Stomp audio override — mirrors the v0.2.0 wire patch where holding
        # LOGO STOMP forced the audio signal to 0 (so the natural state
        # machine drifts toward LOGO via the normal debounce + LOGO_DELAY +
        # RELEASE pacing) and VIDEO STOMP forced audio to 1 (engine snaps to
        # VIDEO instantly). The output mask in _apply_stomp_mask handles the
        # visible bypass; this override drives the natural state machine so
        # by the time the stomp releases, the engine is already settled in
        # the channel the operator was forcing toward.
        if self._video_stomp and self._logo_stomp:
            # Both held — mask kills both visually anyway. Use real audio so
            # natural state stays consistent with what the operator will see
            # when one stomp releases.
            avg = (
                sum(self._audio_buffer) / len(self._audio_buffer)
                if self._audio_buffer
                else None
            )
        elif self._logo_stomp:
            avg = 0.0
        elif self._video_stomp:
            avg = 1.0
        elif self._audio_buffer:
            avg = sum(self._audio_buffer) / len(self._audio_buffer)
        else:
            avg = None

        if avg is None:
            # No audio yet AND no stomp override; hold previous goal or
            # settle to LOGO.
            if self._current_goal[0] in (GOAL_VIDEO, GOAL_LOGO):
                return (
                    self._current_goal[0],
                    self._current_goal[1],
                    v_always,
                    l_always,
                )
            return (GOAL_LOGO, "natural", v_always, l_always)

        if avg > self._tipping_point:
            self._below_since = None
            return (GOAL_VIDEO, "natural", v_always, l_always)
        # Audio (real or stomp-overridden) is below tipping. The duration
        # debounce gates the bass-falling decision (VIDEO→LOGO) only; if we
        # weren't on natural-VIDEO, there's nothing to wait for.
        if self._below_since is None:
            if self._current_goal[0] == GOAL_VIDEO and self._current_goal[1] == "natural":
                self._below_since = now
            else:
                return (GOAL_LOGO, "natural", v_always, l_always)
        if (now - self._below_since) >= self._duration_seconds:
            return (GOAL_LOGO, "natural", v_always, l_always)
        # Inside the debounce window — hold VIDEO regardless of how the
        # engine got here. Without this, a stomp during the debounce would
        # leave the engine stuck on whatever the previous goal happened to
        # be when the stomp released.
        return (GOAL_VIDEO, "natural", v_always, l_always)

    def _build_sequence(
        self,
        goal: str,
        source: str,
        video_always: bool,
        logo_always: bool,
    ) -> list[tuple[str, float, float, float]]:
        """Return phases to reach the goal, with ALWAYS overrides applied.

        Each phase: (kind, video_end, logo_end, duration_seconds).
        For PHASE_RAMP, the start values come from the engine's current values
        captured when the phase begins. For PHASE_SNAP, end values are applied
        immediately. For PHASE_DELAY, current values are held.

        ALWAYS override rules:
          - LOGO ALWAYS on → 0.0 logo endpoints in a natural-VIDEO sequence
            become 1.0 (logo rides at full opacity even when audio is loud).
          - VIDEO ALWAYS on → 0.0 video endpoints in a natural-LOGO sequence
            become 1.0 (video rides at full opacity even when audio is quiet).
          - GOAL_OFF (engine disabled) is never overridden — both still rise
            to 1.
        """
        attack = max(0.0, self._attack_seconds)
        release = max(0.0, self._release_seconds)
        v_delay = max(0.0, self._video_delay_seconds)
        l_delay = max(0.0, self._logo_delay_seconds)

        if goal == GOAL_OFF:
            # Both rise to 1 via release; no delay.
            return [(PHASE_RAMP, 1.0, 1.0, release)]

        if goal == GOAL_VIDEO:
            # Natural: logo falls via attack → wait video delay → video rises via attack.
            l_target = 1.0 if logo_always else 0.0
            return [
                (PHASE_RAMP, self._current_video, l_target, attack),
                (PHASE_DELAY, self._current_video, l_target, v_delay),
                (PHASE_RAMP, 1.0, l_target, attack),
            ]

        if goal == GOAL_LOGO:
            # Natural: video falls via release → wait logo delay → logo rises via release.
            v_target = 1.0 if video_always else 0.0
            return [
                (PHASE_RAMP, v_target, self._current_logo, release),
                (PHASE_DELAY, v_target, self._current_logo, l_delay),
                (PHASE_RAMP, v_target, 1.0, release),
            ]

        return []

    def _start_next_phase(self, now: float) -> None:
        if not self._pending_phases:
            self._phase = PHASE_IDLE
            return
        kind, v_end, l_end, dur = self._pending_phases.pop(0)
        self._phase = kind
        self._phase_video_start = self._current_video
        self._phase_logo_start = self._current_logo
        self._phase_video_end = v_end
        self._phase_logo_end = l_end
        self._phase_duration = dur
        self._phase_started_at = now

    def _execute_phase(self, now: float) -> None:
        # Loop so zero-duration phases cascade within one tick.
        while self._phase != PHASE_IDLE:
            if self._phase == PHASE_SNAP:
                self._current_video = self._phase_video_end
                self._current_logo = self._phase_logo_end
                self._start_next_phase(now)
                continue
            elapsed = now - self._phase_started_at
            if self._phase == PHASE_DELAY:
                if elapsed >= self._phase_duration:
                    self._start_next_phase(now)
                    continue
                return
            if self._phase == PHASE_RAMP:
                if self._phase_duration <= 0.001:
                    self._current_video = self._phase_video_end
                    self._current_logo = self._phase_logo_end
                    self._start_next_phase(now)
                    continue
                t = min(1.0, elapsed / self._phase_duration)
                self._current_video = self._phase_video_start + (
                    self._phase_video_end - self._phase_video_start
                ) * t
                self._current_logo = self._phase_logo_start + (
                    self._phase_logo_end - self._phase_logo_start
                ) * t
                if t >= 1.0:
                    self._start_next_phase(now)
                    continue
                return
            return

    # ------------------------------------------------------------------
    # Output

    def _send_if_changed(
        self,
        video_int: int,
        logo_int: int,
        *,
        video_float: float | None = None,
        logo_float: float | None = None,
    ) -> None:
        # Callers pass the int (post-mask) for dedupe; if they also pass the
        # masked float we send that to OSC so the mask actually reaches
        # Resolume. Without this, the int dedupe would gate output but the
        # OSC payload would still carry the unmasked float — silently
        # ignoring the stomp on the OSC side.
        if self._last_video_sent != video_int:
            v_float = video_float if video_float is not None else video_int / 127.0
            self._send_master(self._cc_video_master, self._osc_video_path, video_int, v_float)
            self._last_video_sent = video_int
        if self._last_logo_sent != logo_int:
            l_float = logo_float if logo_float is not None else logo_int / 127.0
            self._send_master(self._cc_logo_master, self._osc_logo_path, logo_int, l_float)
            self._last_logo_sent = logo_int

    def _send_master(self, cc: int, osc_path: str, int_value: int, float_value: float) -> None:
        if self._output_protocol == "osc" and self._osc is not None:
            self._osc.send(osc_path, max(0.0, min(1.0, float(float_value))))
        else:
            self._midi_out.control_change(self._output_channel, cc, int_value)

    def shutdown(self) -> None:
        if self._osc is not None:
            self._osc.close()
            self._osc = None

    # ------------------------------------------------------------------
    # Status

    def status(self) -> dict:
        return {
            "name": self.name,
            "type": self.type_name,
            "enabled": self._enabled,
            "video_stomp": self._video_stomp,
            "logo_stomp": self._logo_stomp,
            "video_always": self._video_always,
            "logo_always": self._logo_always,
            "tipping_point": round(self._tipping_point, 3),
            "duration_seconds": round(self._duration_seconds, 3),
            "attack_seconds": round(self._attack_seconds, 3),
            "release_seconds": round(self._release_seconds, 3),
            "video_delay_seconds": round(self._video_delay_seconds, 3),
            "logo_delay_seconds": round(self._logo_delay_seconds, 3),
            "audio_window_avg": (
                round(sum(self._audio_buffer) / len(self._audio_buffer), 3)
                if self._audio_buffer
                else 0.0
            ),
            "current_video_master": round(self._current_video, 3),
            "current_logo_master": round(self._current_logo, 3),
            "phase": self._phase,
            "goal": self._current_goal[0],
            "goal_source": self._current_goal[1],
            "pending_phases": len(self._pending_phases),
        }
