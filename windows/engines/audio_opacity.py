"""Audio opacity engine.

Listens to the comp-level `Audio Engine` Wire patch on DECK_OUT (CC 100-109 on
ch15 by default) and drives the VIDEO + LOGO group masters via OSC by default
(or MIDI CCs on DECK_IN if `outputs.protocol` is set to "midi").

Sequential phase state machine matches Ben's spec for v0.3.2:

  Natural bass-rising  : LOGO falls via ATTACK → wait VIDEO DELAY → VIDEO rises via ATTACK
  Natural bass-falling : VIDEO falls via RELEASE → wait LOGO DELAY → LOGO rises via RELEASE
                          (in addition to the DURATION debounce that gates the decision)
  VIDEO STOMP press    : INSTANT cut both to 0 → wait VIDEO DELAY → VIDEO rises via ATTACK
  LOGO STOMP press     : INSTANT cut both to 0 → wait LOGO DELAY → LOGO rises via RELEASE
  Both STOMPs held     : INSTANT cut both to 0, hold (0, 0)
  ENGINE ENABLE off    : both ramp toward 1 via RELEASE (soft handoff to manual control)

Phases run sequentially; only one channel moves at a time within a sequence.
A new state event (audio threshold cross, stomp press/release, enable change)
restarts the appropriate sequence from the current values.
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
        self._audio_buffer: deque[float] = deque(maxlen=self._sample_size)
        self._below_since: float | None = None

        # Master values (smoothed 0-1)
        self._current_video = 1.0
        self._current_logo = 1.0

        # Phase machine
        self._current_goal: tuple[str, str] = (GOAL_OFF, "engine")
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
        if cc == self._cc_audio:
            self._audio_buffer.append(value / 127.0)
        elif cc == self._cc_enable:
            self._enabled = _midpoint_bool(value)
        elif cc == self._cc_video_stomp:
            self._video_stomp = _midpoint_bool(value)
        elif cc == self._cc_logo_stomp:
            self._logo_stomp = _midpoint_bool(value)
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
            self._pending_phases = self._build_sequence(wanted[0], wanted[1])
            self._current_goal = wanted
            self._start_next_phase(now)

        self._execute_phase(now)

        video_int = max(0, min(127, int(round(self._current_video * 127))))
        logo_int = max(0, min(127, int(round(self._current_logo * 127))))
        self._send_if_changed(video_int, logo_int)

    def _compute_wanted(self, now: float) -> tuple[str, str]:
        if not self._enabled:
            return (GOAL_OFF, "engine")
        if self._video_stomp and self._logo_stomp:
            return (GOAL_BLACKOUT, "stomp")
        if self._video_stomp:
            return (GOAL_VIDEO, "stomp")
        if self._logo_stomp:
            return (GOAL_LOGO, "stomp")
        if not self._audio_buffer:
            # No audio yet; hold whatever we were doing, or settle to logo state.
            if self._current_goal[0] in (GOAL_VIDEO, GOAL_LOGO):
                return self._current_goal
            return (GOAL_LOGO, "natural")
        avg = sum(self._audio_buffer) / len(self._audio_buffer)
        if avg > self._tipping_point:
            self._below_since = None
            return (GOAL_VIDEO, "natural")
        if self._below_since is None:
            self._below_since = now
        if (now - self._below_since) >= self._duration_seconds:
            return (GOAL_LOGO, "natural")
        # In debounce window — hold previous goal.
        if self._current_goal[0] in (GOAL_VIDEO, GOAL_LOGO):
            return self._current_goal
        return (GOAL_LOGO, "natural")

    def _build_sequence(self, goal: str, source: str) -> list[tuple[str, float, float, float]]:
        """Return remaining phases (after the snap, if any) to reach the goal.

        Each phase: (kind, video_end, logo_end, duration_seconds).
        For PHASE_RAMP, the start values come from the engine's current values
        captured when the phase begins. For PHASE_SNAP, end values are applied
        immediately. For PHASE_DELAY, current values are held.
        """
        attack = max(0.0, self._attack_seconds)
        release = max(0.0, self._release_seconds)
        v_delay = max(0.0, self._video_delay_seconds)
        l_delay = max(0.0, self._logo_delay_seconds)

        if goal == GOAL_OFF:
            # Both rise to 1 via release; no delay.
            return [(PHASE_RAMP, 1.0, 1.0, release)]

        if goal == GOAL_BLACKOUT:
            # Snap both to 0 and hold.
            return [(PHASE_SNAP, 0.0, 0.0, 0.0)]

        if goal == GOAL_VIDEO:
            if source == "stomp":
                return [
                    (PHASE_SNAP, 0.0, 0.0, 0.0),
                    (PHASE_DELAY, 0.0, 0.0, v_delay),
                    (PHASE_RAMP, 1.0, 0.0, attack),
                ]
            # Natural: logo falls via attack → wait video delay → video rises via attack.
            return [
                (PHASE_RAMP, self._current_video, 0.0, attack),
                (PHASE_DELAY, self._current_video, 0.0, v_delay),
                (PHASE_RAMP, 1.0, 0.0, attack),
            ]

        if goal == GOAL_LOGO:
            if source == "stomp":
                return [
                    (PHASE_SNAP, 0.0, 0.0, 0.0),
                    (PHASE_DELAY, 0.0, 0.0, l_delay),
                    (PHASE_RAMP, 0.0, 1.0, release),
                ]
            # Natural: video falls via release → wait logo delay → logo rises via release.
            return [
                (PHASE_RAMP, 0.0, self._current_logo, release),
                (PHASE_DELAY, 0.0, self._current_logo, l_delay),
                (PHASE_RAMP, 0.0, 1.0, release),
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

    def _send_if_changed(self, video_int: int, logo_int: int) -> None:
        if self._last_video_sent != video_int:
            self._send_master(self._cc_video_master, self._osc_video_path, video_int, self._current_video)
            self._last_video_sent = video_int
        if self._last_logo_sent != logo_int:
            self._send_master(self._cc_logo_master, self._osc_logo_path, logo_int, self._current_logo)
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
