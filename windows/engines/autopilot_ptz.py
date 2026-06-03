"""Autopilot PTZ engine — beat-synced camera-clip cutter on one fixed layer.

A single cutting channel beat-syncs CLIP connects on Layer 4 of the PTZ
composition. On each cut boundary it fires
`/composition/layers/4/clips/N/connect` for the picked camera (N = 1/2/3).
Resolume handles the transition itself (Layer 4's transition duration is set
via a separate fader); the engine never touches layer masters.

**This is the only job of Autopilot PTZ.** It does not control physical
cameras (that is `ptz_visca`) and does not cycle visual layers (that is the V1
`autopilot` engine). See the design doc autopilot-ptz-design.md § How it
differs from Autopilot Engine V1.

Tempo source: MIDI Beat Clock on the configured pulse port (Pulse → loopMIDI).
24 ticks per beat. Bridge derives BPM from rolling tick spacing.

REST policy (ADR-0001): there is NO REST anywhere in this engine — exactly
three camera clips are enumerated inline (1/2/3), so no composition pull is
needed.

The engine receives Wire patch CCs via `on_midi_in` (channel 14, CCs 47-52)
and emits OSC clip-connect triggers only:

- CC 47 — CUTTING ENABLE (value >= 64 → cutting on).
- CC 48 — CUTTING BEATS (raw 0..6 index → beats_lookup, clamped).
- CC 49 — CUTTING MODE (raw 0 = Sequential, 1 = Random; clamped 0..1).
- CC 50/51/52 — CAM 1/2/3 include (value >= 64 → included in the cut cycle).

Cut behavior contract:

- On CUTTING ENABLE rising edge: reset `beat_in_clip` to 0; do NOT fire a cut
  immediately (avoids a jarring jump on enable). The first cut happens after
  the first full `beats_per_clip` window.
- On CUTTING ENABLE falling edge: stop cutting (no further fires); leave
  whatever clip is connected as-is.
- On each beat boundary, if cutting is enabled and at least one cam is
  included, increment `beat_in_clip`; when it reaches `beats_per_clip`, reset
  to 0, advance the picker to the next included cam, and `_fire_clip` it.

Cam picker — two modes (mirrors the V1 RANDOM bag idea, but on the 1/2/3 cam
set with no REST):

- **Sequential** — advance through the included cams in ascending order,
  wrapping 1→2→3→1 and skipping disabled cams.
- **Random** — grab-bag: shuffle the included cams, draw without repeat until
  the bag empties, then reshuffle. Uses an injectable `random.Random` so tests
  are deterministic.
"""

from __future__ import annotations

import logging
import random
import time
from collections import deque
from enum import IntEnum
from typing import Callable

from windows.engines.base import Engine
from windows.engines.osc_client import OscClient
from windows.midi import MidiOut

LOGGER = logging.getLogger(__name__)

TICKS_PER_BEAT = 24

DEFAULT_BEATS_LOOKUP = (1, 4, 8, 16, 32, 64, 128)
DEFAULT_CUTTING_LAYER = 4
CAM_INDICES = (1, 2, 3)


class CutMode(IntEnum):
    SEQUENTIAL = 0
    RANDOM = 1


class AutopilotPtzEngine(Engine):
    type_name = "autopilot_ptz"

    def __init__(
        self,
        name: str,
        config: dict,
        midi_out: MidiOut,
        *,
        clock: Callable[[], float] = time.monotonic,
        osc_client: OscClient | None = None,
        rng: random.Random | None = None,
    ) -> None:
        super().__init__(name, config, midi_out, clock=clock)
        inputs = config.get("inputs", {})
        outputs = config.get("outputs", {})
        defaults = config.get("defaults", {})

        self._midi_channel = int(inputs.get("channel", 14))
        self._cc_enable = int(inputs.get("cc_enable", 47))
        self._cc_beats = int(inputs.get("cc_beats", 48))
        self._cc_mode = int(inputs.get("cc_mode", 49))
        self._cc_cam = {
            1: int(inputs.get("cc_cam1", 50)),
            2: int(inputs.get("cc_cam2", 51)),
            3: int(inputs.get("cc_cam3", 52)),
        }
        # Reverse map for cam-include CC dispatch.
        self._cam_cc_to_index = {cc: idx for idx, cc in self._cc_cam.items()}

        beats_lookup = tuple(inputs.get("beats_lookup", DEFAULT_BEATS_LOOKUP))
        self._beats_lookup: tuple[int, ...] = tuple(int(b) for b in beats_lookup)
        self._update_hz = float(config.get("update_hz", 30))

        # OSC client for clip-connect writes.
        osc_cfg = outputs.get("osc", {})
        self._osc_host = str(osc_cfg.get("host", "127.0.0.1"))
        self._osc_port = int(osc_cfg.get("port", 7000))
        self._osc = osc_client or OscClient(host=self._osc_host, port=self._osc_port)

        self._cutting_layer = int(outputs.get("cutting_layer", DEFAULT_CUTTING_LAYER))
        self._osc_clip_connect_template = "/composition/layers/{n}/clips/{m}/connect"

        self._rng = rng or random.Random()

        # --- cutting state (config-driven defaults) ------------------------
        self._enabled = bool(defaults.get("enabled", False))
        self._beats_per_clip = int(defaults.get("beats_per_clip", 16))
        default_mode_raw = int(defaults.get("clip_mode", 0))
        self._clip_mode = CutMode(max(0, min(1, default_mode_raw)))
        self._cam_enabled = {
            1: bool(defaults.get("cam1_enabled", True)),
            2: bool(defaults.get("cam2_enabled", True)),
            3: bool(defaults.get("cam3_enabled", True)),
        }

        # cut runtime
        self._cycle_index = 0
        self._beat_in_clip = 0
        self._selected_cam: int | None = None
        # grab-bag for RANDOM mode (drawn without repeat until empty).
        self._bag: list[int] = []

        # tempo derivation
        self._tick_count = 0
        self._tick_timestamps: deque[float] = deque(maxlen=TICKS_PER_BEAT)
        self._clock_running = True

    # ----- Engine ABC overrides -----------------------------------------------

    def tick_interval_seconds(self) -> float | None:
        return 1.0 / self._update_hz

    def on_midi_in(self, channel: int, cc: int, value: int, now: float) -> None:
        if channel != self._midi_channel:
            return
        if cc == self._cc_enable:
            new_val = value >= 64
            if new_val != self._enabled:
                self._enabled = new_val
                # Reset the beat counter on the rising edge so the first cut
                # lands a full window after enable (no jarring jump on enable);
                # the falling edge just stops further fires.
                self._beat_in_clip = 0
                LOGGER.info("autopilot_ptz: cutting enabled=%s", new_val)
            return
        if cc == self._cc_beats:
            idx = max(0, min(value, len(self._beats_lookup) - 1))
            new_beats = self._beats_lookup[idx]
            if new_beats != self._beats_per_clip:
                self._beats_per_clip = new_beats
                self._beat_in_clip = 0
                LOGGER.info("autopilot_ptz: beats_per_clip=%s", new_beats)
            return
        if cc == self._cc_mode:
            # Wire dropdown sends raw 0/1 (normalize=false on the Write CC node).
            clamped = max(0, min(1, int(value)))
            new_mode = CutMode(clamped)
            if new_mode != self._clip_mode:
                old_mode = self._clip_mode
                self._clip_mode = new_mode
                # Clear the bag whenever leaving RANDOM so a fresh shuffle
                # starts on re-entry.
                if old_mode == CutMode.RANDOM:
                    self._bag.clear()
                LOGGER.info("autopilot_ptz: mode=%s", new_mode.name)
            return
        cam_index = self._cam_cc_to_index.get(cc)
        if cam_index is not None:
            new_val = value >= 64
            if new_val != self._cam_enabled.get(cam_index, False):
                self._cam_enabled[cam_index] = new_val
                LOGGER.info(
                    "autopilot_ptz: cam %d included=%s", cam_index, new_val
                )
            return

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

    def shutdown(self) -> None:
        try:
            self._osc.close()
        except Exception:
            pass

    def status(self) -> dict:
        return {
            "name": self.name,
            "type": self.type_name,
            "active": self.active,
            "tick_count": self._tick_count,
            "clock_running": self._clock_running,
            "bpm": self._estimate_bpm(),
            "enabled": self._enabled,
            "beats_per_clip": self._beats_per_clip,
            "clip_mode": self._clip_mode.name,
            "cam_enabled": {str(k): v for k, v in self._cam_enabled.items()},
            "selected_cam": self._selected_cam,
            "beat_in_clip": self._beat_in_clip,
            "cycle_index": self._cycle_index,
        }

    # ----- internal helpers ---------------------------------------------------

    def _reset_clock_state(self) -> None:
        self._tick_count = 0
        self._tick_timestamps.clear()
        self._beat_in_clip = 0
        self._cycle_index = 0
        self._bag.clear()

    def _on_beat_boundary(self, now: float) -> None:
        if not self._enabled:
            return
        if not self._included_cams():
            return
        self._beat_in_clip += 1
        if self._beat_in_clip < self._beats_per_clip:
            return
        self._beat_in_clip = 0
        cam = self._pick_cam()
        if cam is None:
            return
        self._fire_clip(cam)

    def _included_cams(self) -> list[int]:
        return [i for i in CAM_INDICES if self._cam_enabled.get(i, False)]

    def _pick_cam(self) -> int | None:
        """Pick the next included cam per the active mode, or None if none.

        Updates `self._selected_cam` so the sequential walk advances and status
        reflects the live pick. Returns None (and leaves `selected_cam` as-is)
        when no cam is included.
        """
        included = self._included_cams()
        if not included:
            return None
        if self._clip_mode == CutMode.RANDOM:
            cam = self._pick_random(included)
        else:
            cam = self._pick_sequential(included)
        self._selected_cam = cam
        return cam

    def _pick_sequential(self, included: list[int]) -> int:
        """Advance to the next included cam in ascending order, wrapping.

        Walks ascending from just after the current cam, wrapping 1→2→3→1 and
        skipping disabled cams. If the current cam is no longer included (or
        nothing has been picked yet) the lowest included cam is chosen.
        """
        current = self._selected_cam
        if current is None:
            return included[0]
        # First included cam strictly greater than current; else wrap to lowest.
        for cam in included:
            if cam > current:
                return cam
        return included[0]

    def _pick_random(self, included: list[int]) -> int:
        """Grab-bag draw over the included cams (no repeat until the bag empties).

        The bag is filtered to the currently-included cams on each draw so a
        mid-run include-set change is respected. When the bag empties it is
        reshuffled from the current included set.
        """
        # Drop any cams that are no longer included from the live bag.
        self._bag = [c for c in self._bag if c in included]
        if not self._bag:
            self._bag = list(included)
            self._rng.shuffle(self._bag)
        return self._bag.pop(0)

    def _fire_clip(self, cam_index: int) -> None:
        path = self._osc_clip_connect_template.format(
            n=self._cutting_layer, m=cam_index
        )
        self._osc.send(path, True)

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
