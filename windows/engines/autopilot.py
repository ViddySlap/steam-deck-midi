"""Autopilot engine — beat-synced per-channel clip cycler.

Three channels (VIDEO / FX / LOGO) cycle through their selected layers every
N beats, optionally advance clips per cycle wrap, and quantize Steam Deck
column triggers to the next beat boundary.

Tempo source: MIDI Beat Clock on the configured pulse port (Pulse → loopMIDI).
24 ticks per beat. Bridge derives BPM from rolling tick spacing.

Design references:
- Spec: Projects/steam-deck-midi/specs/autopilot-engine.md (v0.4.0)
- Spec: Projects/steam-deck-midi/specs/autopilot-v0.4.1-mode-selector.md (v0.4.1)
- Wire patch dashboard: VIDEO / FX / LOGO sections, 19 inputs, CCs 60-89 ch15
- Q&A decisions in notes/q-and-a.md (B2/B3/B5/B6/B7/B10/E1-E4/F1)

The engine receives Wire patch CCs via on_midi_in (channel 14, CCs 60-89) and
emits OSC writes to layer masters, layer transition durations, and per-layer
indexed-clip-connect triggers.

REST policy (ADR-0001, no REST on the live-performance path): the only REST
read is a one-shot composition pull in `_prime_clip_cache()`, called from
`bind_registry` at init and from `refresh()` (the user-triggered
`POST /api/engines/refresh` path). LINEAR/RANDOM clip enumeration is served
entirely from that cache so the beat/hot path is OSC-only. There is no
periodic REST polling — the old ~1 Hz mouse-override poll was removed because
it dropped Steam Deck MIDI sends during shows.

Per-channel MODE (NONE/LINEAR/RANDOM, v0.4.1):
- NONE  — cycle layer masters; clips stay where they are.
- LINEAR — also advance clips left-to-right (+1 with wrap) at each cycle.
- RANDOM — also draw a clip from a per-layer shuffled bag at each cycle.

Steam Deck column quantize (v0.4.1 fix): Resolume's MIDI shortcut binds
`/composition/groups/1/connect{prev,next}column` on channel 0 to four notes —
note 82 (L_PAD_LEFT short-press), note 83 (L_PAD_RIGHT short-press),
note 86 (L_PAD_LEFT_LONG_PRESS), note 87 (L_PAD_RIGHT_LONG_PRESS). The engine
defers all four notes on channel 0 when any channel is enabled, then re-emits
the same note at the next beat boundary and resets every enabled channel to
its lowest-indexed selected layer at master 1.0.
"""

from __future__ import annotations

import logging
import random
import time
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable

from windows.engines.base import Engine
from windows.engines.osc_client import OscClient
from windows.engines.resolume_rest import ResolumeRestClient, ResolumeRestError
from windows.midi import MidiOut

LOGGER = logging.getLogger(__name__)

TICKS_PER_BEAT = 24
COLUMN_PREV_NOTES = frozenset({82, 86})  # L_PAD_LEFT short + long-press → connectprevcolumn
COLUMN_NEXT_NOTES = frozenset({83, 87})  # L_PAD_RIGHT short + long-press → connectnextcolumn
COLUMN_TRIGGER_NOTES = COLUMN_PREV_NOTES | COLUMN_NEXT_NOTES
COLUMN_TRIGGER_CHANNEL = 0  # Resolume MIDI shortcut binds on ch0 (mido 0-indexed)
COLUMN_TRIGGER_VELOCITY = 127

# Resolume's /composition/layers/N/transition/duration accepts normalized
# 0-1 over a 0-10 second range. Bridge stores transition in seconds (0-5 by
# default per the Wire patch's TRANSITION fader); divide by this constant
# before sending OSC so the value lands at the expected number of seconds.
RESOLUME_LAYER_TRANSITION_MAX_SECONDS = 10.0


class ClipMode(IntEnum):
    NONE = 0
    LINEAR = 1
    RANDOM = 2

CHANNEL_KEYS = ("video", "fx", "logo")
DEFAULT_BEATS_LOOKUP = (1, 4, 8, 16, 32, 64, 128)
DEFAULT_TRANSITION_MAX = 5.0


@dataclass
class ChannelConfig:
    cc_enable: int
    cc_beats: int
    cc_transition: int
    cc_mode: int
    layer_ccs: dict[int, int]  # layer_index -> cc number


@dataclass
class ChannelState:
    enabled: bool = False
    beats_per_clip: int = 16
    transition_seconds: float = 0.0
    clip_mode: ClipMode = ClipMode.NONE
    layer_enabled: dict[int, bool] = field(default_factory=dict)

    # cycle runtime
    cycle_index: int = 0
    beat_in_clip: int = 0
    visible_layer: int | None = None
    target_layer: int | None = None
    crossfade_start_time: float | None = None  # wall clock (time.monotonic) at fade start

    # bag-random per layer (RANDOM mode)
    bag: dict[int, list[int]] = field(default_factory=dict)
    # last clip fired per layer (tracked for both LINEAR and RANDOM, plus mouse override)
    last_clip: dict[int, int | None] = field(default_factory=dict)
    # REST-derived loaded-clip count per layer (LINEAR wrap)
    clip_count_cache: dict[int, int] = field(default_factory=dict)

    def selected_layers(self) -> list[int]:
        return sorted(n for n, on in self.layer_enabled.items() if on)


class AutopilotEngine(Engine):
    type_name = "autopilot"

    def __init__(
        self,
        name: str,
        config: dict,
        midi_out: MidiOut,
        *,
        clock: Callable[[], float] = time.monotonic,
        rest_client: ResolumeRestClient | None = None,
        osc_client: OscClient | None = None,
        rng: random.Random | None = None,
    ) -> None:
        super().__init__(name, config, midi_out, clock=clock)
        inputs = config.get("inputs", {})
        outputs = config.get("outputs", {})
        defaults = config.get("defaults", {})

        self._midi_channel = int(inputs.get("channel", 14))
        beats_lookup = tuple(inputs.get("beats_lookup", DEFAULT_BEATS_LOOKUP))
        self._beats_lookup: tuple[int, ...] = tuple(int(b) for b in beats_lookup)
        self._transition_max = float(inputs.get("transition_max_seconds", DEFAULT_TRANSITION_MAX))
        self._update_hz = float(config.get("update_hz", 30))

        self._channels: dict[str, ChannelConfig] = {}
        self._states: dict[str, ChannelState] = {}
        self._cc_to_channel_param: dict[int, tuple[str, str, int | None]] = {}

        for key in CHANNEL_KEYS:
            ch_inputs = inputs.get(key, {})
            layer_ccs_raw = ch_inputs.get("layer_ccs", {})
            layer_ccs = {int(layer): int(cc) for layer, cc in layer_ccs_raw.items()}
            # Accept either cc_mode (v0.4.1) or legacy cc_random (v0.4.0).
            cc_mode_raw = ch_inputs.get("cc_mode", ch_inputs.get("cc_random", 0))
            channel_config = ChannelConfig(
                cc_enable=int(ch_inputs.get("cc_enable", 0)),
                cc_beats=int(ch_inputs.get("cc_beats", 0)),
                cc_transition=int(ch_inputs.get("cc_transition", 0)),
                cc_mode=int(cc_mode_raw),
                layer_ccs=layer_ccs,
            )
            self._channels[key] = channel_config
            self._cc_to_channel_param[channel_config.cc_enable] = (key, "enable", None)
            self._cc_to_channel_param[channel_config.cc_beats] = (key, "beats", None)
            self._cc_to_channel_param[channel_config.cc_transition] = (key, "transition", None)
            self._cc_to_channel_param[channel_config.cc_mode] = (key, "mode", None)
            for layer, cc in layer_ccs.items():
                self._cc_to_channel_param[cc] = (key, "layer", layer)

            ch_defaults = defaults.get(key, {})
            default_mode_raw = int(ch_defaults.get("clip_mode", 0))
            default_mode = ClipMode(max(0, min(2, default_mode_raw)))
            state = ChannelState(
                beats_per_clip=int(ch_defaults.get("beats_per_clip", 16)),
                transition_seconds=float(ch_defaults.get("transition_seconds", 0.0)),
                clip_mode=default_mode,
                layer_enabled={layer: False for layer in layer_ccs},
            )
            self._states[key] = state

        # OSC client for layer master / next-clip / transition writes
        osc_cfg = outputs.get("osc", {})
        self._osc_host = str(osc_cfg.get("host", "127.0.0.1"))
        self._osc_port = int(osc_cfg.get("port", 7000))
        self._osc = osc_client or OscClient(host=self._osc_host, port=self._osc_port)

        # REST client (for clip enumeration in random mode + mouse override poll)
        rest_cfg = outputs.get("rest", {})
        self._rest_base = str(rest_cfg.get("base_url", "http://127.0.0.1:8080"))
        self._rest_timeout = float(rest_cfg.get("timeout_seconds", 1.5))
        self._rest = rest_client or ResolumeRestClient(
            base_url=self._rest_base, timeout_seconds=self._rest_timeout
        )

        self._rng = rng or random.Random()

        # tempo derivation
        self._tick_count = 0
        self._tick_timestamps: deque[float] = deque(maxlen=TICKS_PER_BEAT)
        self._clock_running = True

        # column trigger quantize
        self._pending_column_note: int | None = None  # 86 or 87 if pending
        self._column_quantize = bool(config.get("column_quantize", True))

        # Loaded-clip index cache per managed layer, primed by a one-shot REST
        # read at bind_registry / refresh() only (ADR-0001 — no REST on the hot
        # path). LINEAR/RANDOM clip enumeration reads from here.
        self._all_layers: list[int] = sorted(
            {layer for ch in self._channels.values() for layer in ch.layer_ccs}
        )
        self._layer_clips: dict[int, list[int]] = {}

        self._registry = None

        # OSC paths. v0.4.1 dropped /connect_next_clip — it isn't a real Resolume
        # path and silently no-ops in LINEAR. Use indexed /clips/M/connect only.
        self._osc_layer_master_template = "/composition/layers/{n}/master"
        self._osc_layer_clip_connect_template = "/composition/layers/{n}/clips/{m}/connect"
        self._osc_layer_transition_duration_template = (
            "/composition/layers/{n}/transition/duration"
        )

    # ----- Engine ABC overrides ------------------------------------------------

    def bind_registry(self, registry) -> None:
        self._registry = registry
        if self._column_quantize:
            registry.add_note_emit_filter(self._note_emit_filter)
        # One-shot init read of the loaded-clip layout (sanctioned by ADR-0001).
        self._prime_clip_cache()

    def refresh(self) -> None:
        # User-triggered re-pull (POST /api/engines/refresh). Re-reads the clip
        # layout so a mid-session clip reload is picked up without a restart.
        self._prime_clip_cache()

    def tick_interval_seconds(self) -> float | None:
        return 1.0 / self._update_hz

    def on_midi_in(self, channel: int, cc: int, value: int, now: float) -> None:
        if channel != self._midi_channel:
            return
        target = self._cc_to_channel_param.get(cc)
        if target is None:
            return
        ch_key, param, payload = target
        state = self._states[ch_key]
        if param == "enable":
            new_val = value >= 64
            if new_val != state.enabled:
                state.enabled = new_val
                LOGGER.info("autopilot %s: enabled=%s", ch_key, new_val)
                if new_val:
                    # On enable, snap masters to the first selected layer.
                    self._snap_to_first_selected(ch_key)
        elif param == "beats":
            idx = max(0, min(value, len(self._beats_lookup) - 1))
            new_beats = self._beats_lookup[idx]
            if new_beats != state.beats_per_clip:
                state.beats_per_clip = new_beats
                state.beat_in_clip = 0
                LOGGER.info("autopilot %s: beats_per_clip=%s", ch_key, new_beats)
        elif param == "transition":
            new_seconds = (value / 127.0) * self._transition_max
            state.transition_seconds = new_seconds
            # Push to Resolume per-layer transition param immediately.
            for layer in state.selected_layers():
                self._send_layer_transition(layer, new_seconds)
        elif param == "mode":
            # Wire dropdown sends raw 0/1/2 (normalize=false on the Write CC node).
            clamped = max(0, min(2, int(value)))
            new_mode = ClipMode(clamped)
            if new_mode != state.clip_mode:
                old_mode = state.clip_mode
                state.clip_mode = new_mode
                # Clear bag whenever leaving RANDOM so a fresh shuffle starts on re-entry.
                if old_mode == ClipMode.RANDOM:
                    state.bag.clear()
                LOGGER.info("autopilot %s: mode=%s", ch_key, new_mode.name)
        elif param == "layer":
            assert payload is not None
            new_val = value >= 64
            old_val = state.layer_enabled.get(payload, False)
            if new_val != old_val:
                state.layer_enabled[payload] = new_val
                LOGGER.info(
                    "autopilot %s: layer %d enabled=%s",
                    ch_key,
                    payload,
                    new_val,
                )
                # If the visible layer was unselected, advance to next selected.
                if not new_val and state.visible_layer == payload:
                    self._snap_to_first_selected(ch_key)

    def on_midi_clock(self, message_type: str, now: float) -> None:
        if message_type == "start":
            self._reset_clock_state()
            self._clock_running = True
            return
        if message_type == "stop":
            self._clock_running = False
            return
        if message_type == "continue":
            self._clock_running = True
            return
        if message_type != "clock":
            return
        if not self._clock_running:
            return
        self._tick_count += 1
        self._tick_timestamps.append(now)
        if self._tick_count % TICKS_PER_BEAT == 0:
            self._on_beat_boundary(now)

    def tick(self, now: float) -> None:
        # Per-tick cross-fade ramping. Uses wall clock (not MIDI clock ticks)
        # so the fade is smooth even when Pulse → Windows MIDI input has timing
        # jitter. Decoupled from clock entirely — fades complete on schedule
        # regardless of Pulse pauses or BPM drift.
        for ch_key, state in self._states.items():
            if state.target_layer is None or state.crossfade_start_time is None:
                continue
            elapsed_seconds = max(0.0, now - state.crossfade_start_time)
            duration = state.transition_seconds
            progress = 1.0 if duration <= 0 else min(elapsed_seconds / duration, 1.0)
            old_master = max(0.0, 1.0 - progress)
            new_master = progress
            if state.visible_layer is not None:
                self._send_layer_master(state.visible_layer, old_master)
            self._send_layer_master(state.target_layer, new_master)
            if progress >= 1.0:
                if state.visible_layer is not None:
                    self._send_layer_master(state.visible_layer, 0.0)
                state.visible_layer = state.target_layer
                state.target_layer = None
                state.crossfade_start_time = None

    def shutdown(self) -> None:
        try:
            self._osc.close()
        except Exception:
            pass

    def status(self) -> dict:
        out: dict = {
            "name": self.name,
            "type": self.type_name,
            "tick_count": self._tick_count,
            "clock_running": self._clock_running,
            "bpm": self._estimate_bpm(),
            "pending_column_note": self._pending_column_note,
            "channels": {},
        }
        for key, state in self._states.items():
            out["channels"][key] = {
                "enabled": state.enabled,
                "beats_per_clip": state.beats_per_clip,
                "transition_seconds": state.transition_seconds,
                "clip_mode": state.clip_mode.name,
                "layer_enabled": {str(k): v for k, v in state.layer_enabled.items()},
                "visible_layer": state.visible_layer,
                "target_layer": state.target_layer,
                "beat_in_clip": state.beat_in_clip,
                "cycle_index": state.cycle_index,
            }
        return out

    # ----- internal helpers ---------------------------------------------------

    def _reset_clock_state(self) -> None:
        self._tick_count = 0
        self._tick_timestamps.clear()
        for state in self._states.values():
            state.beat_in_clip = 0
            state.cycle_index = 0
            state.target_layer = None
            state.crossfade_start_time = None
            if state.enabled and state.selected_layers():
                state.visible_layer = state.selected_layers()[0]

    def _on_beat_boundary(self, now: float) -> None:
        # If a column trigger was pending, replay it now and skip cycle advance
        # for this beat — the column shift IS the cycle event, and bumping
        # beat_in_clip on top of the reset would double-count.
        if self._pending_column_note is not None:
            self._fire_pending_column()
            return

        for ch_key, state in self._states.items():
            if not state.enabled:
                continue
            selected = state.selected_layers()
            if not selected:
                continue

            # Single-layer fast path (v0.4.1): skip cross-fade entirely. No
            # master writes on cycle wrap — the layer just holds steady at 1.0.
            # Clip advance still fires when MODE != NONE.
            if len(selected) == 1:
                layer = selected[0]
                if state.visible_layer != layer:
                    self._send_layer_master(layer, 1.0)
                    state.visible_layer = layer
                    state.cycle_index = 0
                    state.beat_in_clip = 0
                state.beat_in_clip += 1
                if state.beat_in_clip >= state.beats_per_clip:
                    state.beat_in_clip = 0
                    if state.clip_mode != ClipMode.NONE:
                        self._fire_next_clip(state, layer)
                        self._send_layer_transition(layer, state.transition_seconds)
                continue

            # Multi-layer path.
            if state.visible_layer is None or state.visible_layer not in selected:
                state.visible_layer = selected[0]
                state.cycle_index = 0
                state.beat_in_clip = 0
                self._send_layer_master(state.visible_layer, 1.0)
                for layer in selected:
                    if layer != state.visible_layer:
                        self._send_layer_master(layer, 0.0)
                continue
            state.beat_in_clip += 1
            if state.beat_in_clip < state.beats_per_clip:
                continue
            state.beat_in_clip = 0
            state.cycle_index = (state.cycle_index + 1) % len(selected)
            if state.cycle_index == 0:
                # Cycle complete — fire clip advance on every selected layer
                # and re-apply transition seconds (handles user re-ordering layers).
                for layer in selected:
                    self._fire_next_clip(state, layer)
                    self._send_layer_transition(layer, state.transition_seconds)
            target = selected[state.cycle_index]
            state.target_layer = target
            state.crossfade_start_time = now
            if state.transition_seconds <= 0:
                # Instant snap; the tick handler will close it on the next iteration,
                # but pre-emit the final masters now so there's no visible gap.
                if state.visible_layer is not None:
                    self._send_layer_master(state.visible_layer, 0.0)
                self._send_layer_master(target, 1.0)
                state.visible_layer = target
                state.target_layer = None
                state.crossfade_start_time = None

    def _snap_to_first_selected(self, ch_key: str) -> None:
        state = self._states[ch_key]
        selected = state.selected_layers()
        if not selected:
            state.visible_layer = None
            state.target_layer = None
            return
        state.visible_layer = selected[0]
        state.target_layer = None
        state.crossfade_start_time = None
        state.cycle_index = 0
        state.beat_in_clip = 0
        for layer in selected:
            self._send_layer_master(layer, 1.0 if layer == state.visible_layer else 0.0)
        for layer in selected:
            self._send_layer_transition(layer, state.transition_seconds)

    def _fire_next_clip(self, state: ChannelState, layer: int) -> None:
        if state.clip_mode == ClipMode.NONE:
            return
        if state.clip_mode == ClipMode.RANDOM:
            clip_idx = self._draw_random_clip(state, layer)
        else:  # LINEAR
            clip_idx = self._next_linear_clip(state, layer)
        if clip_idx is None:
            # REST enumeration empty — silently skip this cycle.
            return
        path = self._osc_layer_clip_connect_template.format(n=layer, m=clip_idx)
        self._osc.send(path, True)
        state.last_clip[layer] = clip_idx

    def _next_linear_clip(self, state: ChannelState, layer: int) -> int | None:
        count = state.clip_count_cache.get(layer)
        if count is None:
            count = self._count_layer_clips(layer)
            if count == 0:
                return None
            state.clip_count_cache[layer] = count
        current = state.last_clip.get(layer)
        if current is None:
            return 1
        nxt = current + 1
        if nxt > count:
            nxt = 1
        return nxt

    def _count_layer_clips(self, layer: int) -> int:
        return len(self._enumerate_layer_clips(layer))

    def _draw_random_clip(self, state: ChannelState, layer: int) -> int | None:
        bag = state.bag.get(layer)
        if not bag:
            clips = self._enumerate_layer_clips(layer)
            if not clips:
                return None
            current = state.last_clip.get(layer)
            shuffle_pool = [c for c in clips if c != current] or list(clips)
            self._rng.shuffle(shuffle_pool)
            bag = shuffle_pool
            state.bag[layer] = bag
        return bag.pop(0) if bag else None

    def _enumerate_layer_clips(self, layer: int) -> list[int]:
        # Cache-only — primed by _prime_clip_cache() at init/refresh. No REST
        # on the beat/hot path (ADR-0001).
        return list(self._layer_clips.get(layer, []))

    def _prime_clip_cache(self) -> None:
        """One-shot REST read of loaded-clip indices for every managed layer.

        Called only from bind_registry (init) and refresh() (user-triggered) —
        never on the beat/hot path. Builds `self._layer_clips[layer] = [indices]`
        and invalidates the per-channel derived caches so a new clip layout
        takes effect. REST failure leaves the previous cache intact.
        """
        try:
            comp = self._rest.get_composition()
        except ResolumeRestError as exc:
            LOGGER.warning("autopilot: clip-cache prime failed (REST): %s", exc)
            return
        layers = comp.get("layers", [])
        new_cache: dict[int, list[int]] = {}
        for layer in self._all_layers:
            try:
                layer_obj = layers[layer - 1]  # OSC 1-indexed; JSON tree 0-indexed
            except IndexError:
                new_cache[layer] = []
                continue
            clips = layer_obj.get("clips", [])
            loaded: list[int] = []
            for i, clip in enumerate(clips, start=1):
                # Treat any clip with a non-empty file/source field as loaded.
                video = clip.get("video") or clip.get("source")
                if video:
                    loaded.append(i)
            new_cache[layer] = loaded
        self._layer_clips = new_cache
        # Derived caches must be rebuilt against the fresh layout.
        for state in self._states.values():
            state.clip_count_cache.clear()
            state.bag.clear()
        LOGGER.info(
            "autopilot: clip cache primed for layers %s",
            {k: len(v) for k, v in new_cache.items()},
        )

    def _send_layer_master(self, layer: int, value: float) -> None:
        path = self._osc_layer_master_template.format(n=layer)
        clamped = max(0.0, min(1.0, float(value)))
        self._osc.send(path, clamped)

    def _send_layer_transition(self, layer: int, seconds: float) -> None:
        path = self._osc_layer_transition_duration_template.format(n=layer)
        # Resolume normalizes 0-1 over RESOLUME_LAYER_TRANSITION_MAX_SECONDS.
        # Send seconds/max so the value lands at the intended duration.
        normalized = max(0.0, min(1.0, float(seconds) / RESOLUME_LAYER_TRANSITION_MAX_SECONDS))
        self._osc.send(path, normalized)

    def _tick_to_seconds(self, tick_delta: int) -> float:
        # When we don't have BPM history yet, assume 120 BPM (0.5 s/beat).
        if len(self._tick_timestamps) < 2:
            return tick_delta * (0.5 / TICKS_PER_BEAT)
        first, last = self._tick_timestamps[0], self._tick_timestamps[-1]
        spread = last - first
        if spread <= 0:
            return tick_delta * (0.5 / TICKS_PER_BEAT)
        per_tick = spread / max(1, len(self._tick_timestamps) - 1)
        return tick_delta * per_tick

    def _estimate_bpm(self) -> float | None:
        if len(self._tick_timestamps) < 2:
            return None
        first, last = self._tick_timestamps[0], self._tick_timestamps[-1]
        spread = last - first
        if spread <= 0:
            return None
        per_tick = spread / (len(self._tick_timestamps) - 1)
        seconds_per_beat = per_tick * TICKS_PER_BEAT
        if seconds_per_beat <= 0:
            return None
        return round(60.0 / seconds_per_beat, 2)

    # ----- column trigger quantize -------------------------------------------

    def _any_channel_enabled(self) -> bool:
        return any(s.enabled and s.selected_layers() for s in self._states.values())

    def _note_emit_filter(
        self, channel: int, note: int, velocity: int, now: float
    ) -> bool:
        # Defer all 4 column-trigger notes (short-press 82/83 + long-press
        # 86/87) on channel 0 when any channel is enabled. Resolume's MIDI
        # shortcut binds these to /composition/groups/1/connect{prev,next}column.
        if channel != COLUMN_TRIGGER_CHANNEL:
            return True
        if note not in COLUMN_TRIGGER_NOTES:
            return True
        if not self._any_channel_enabled():
            return True
        if self._pending_column_note is not None:
            # Already a pending trigger — drop the second one rather than queue.
            LOGGER.debug(
                "autopilot: dropping note %d (column trigger already pending)", note
            )
            return False
        self._pending_column_note = note
        LOGGER.info("autopilot: deferring column trigger note=%d to next beat", note)
        return False

    def _fire_pending_column(self) -> None:
        note = self._pending_column_note
        if note is None:
            return
        self._pending_column_note = None
        try:
            self._midi_out.note_on(
                COLUMN_TRIGGER_CHANNEL, note, COLUMN_TRIGGER_VELOCITY
            )
        except Exception:
            LOGGER.exception("autopilot: failed to re-emit column trigger note=%d", note)
            return
        # Reset every enabled channel to first selected layer at full master.
        for ch_key, state in self._states.items():
            if not state.enabled:
                continue
            selected = state.selected_layers()
            if not selected:
                continue
            new_visible = selected[0]
            for layer in selected:
                self._send_layer_master(layer, 1.0 if layer == new_visible else 0.0)
            state.visible_layer = new_visible
            state.target_layer = None
            state.crossfade_start_time = None
            state.cycle_index = 0
            state.beat_in_clip = 0
            # Bags carry over — column shift doesn't invalidate clip choices.
