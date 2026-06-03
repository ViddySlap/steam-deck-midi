"""Tests for the autopilot_ptz engine — beat-synced camera-clip cutter.

A single cutting channel beat-syncs CLIP connects on one fixed layer (Layer 4)
of the PTZ composition. The engine takes MIDI Beat Clock (24 ticks/beat) and
Wire-patch CCs (channel 14, CCs 47-52), and emits OSC clip-connect triggers
only — no REST, no layer masters.

Fakes mirror tests/test_ptz_visca.py: a RecordingMidiOut, an injected FakeClock,
and a FakeOscClient that records sends. The cam picker takes a seeded
random.Random so RANDOM mode is deterministic.
"""

from __future__ import annotations

import json
import random
import unittest
from typing import Any

from windows.engines.autopilot_ptz import (
    DEFAULT_BEATS_LOOKUP,
    AutopilotPtzEngine,
    CutMode,
)
from windows.engines.registry import EngineRegistry, _ENGINE_TYPES
from windows.midi import DryRunMidiOut


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class RecordingMidiOut(DryRunMidiOut):
    def __init__(self) -> None:
        super().__init__(selected_port_name="recording")
        self.events: list[tuple] = []

    def control_change(self, channel: int, control: int, value: int) -> None:
        self.events.append(("cc", channel, control, value))

    def note_on(self, channel: int, note: int, velocity: int) -> None:
        self.events.append(("note_on", channel, note, velocity))

    def note_off(self, channel: int, note: int, velocity: int = 0) -> None:
        self.events.append(("note_off", channel, note, velocity))


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, dt: float) -> None:
        self.now += dt


class FakeOscClient:
    """Records OSC sends instead of hitting a socket."""

    def __init__(self) -> None:
        self.sends: list[tuple[str, Any]] = []
        self.closed = False

    def send(self, address: str, value: Any) -> None:
        self.sends.append((address, value))

    def close(self) -> None:
        self.closed = True

    # convenience filters
    def connects(self) -> list[tuple[str, Any]]:
        return [(a, v) for a, v in self.sends if a.endswith("/connect")]


# Channel/CC contract (channel 14 == MIDI ch15, the Wire→bridge convention).
CH = 14
CC_ENABLE = 47
CC_BEATS = 48
CC_MODE = 49
CC_CAM1 = 50
CC_CAM2 = 51
CC_CAM3 = 52


def _config(**overrides) -> dict:
    cfg = {
        "type": "autopilot_ptz",
        "name": "Autopilot PTZ",
        "enabled": True,
        "inputs": {
            "channel": CH,
            "cc_enable": CC_ENABLE,
            "cc_beats": CC_BEATS,
            "cc_mode": CC_MODE,
            "cc_cam1": CC_CAM1,
            "cc_cam2": CC_CAM2,
            "cc_cam3": CC_CAM3,
            "beats_lookup": [1, 4, 8, 16, 32, 64, 128],
        },
        "outputs": {
            "osc": {"host": "127.0.0.1", "port": 7000},
            "cutting_layer": 4,
        },
        "defaults": {
            "enabled": False,
            "beats_per_clip": 16,
            "clip_mode": 0,
            "cam1_enabled": True,
            "cam2_enabled": True,
            "cam3_enabled": True,
        },
    }
    cfg.update(overrides)
    return cfg


def _engine(
    clock: FakeClock | None = None,
    osc: FakeOscClient | None = None,
    seed: int = 0,
    **overrides,
) -> tuple[AutopilotPtzEngine, FakeOscClient]:
    clock = clock or FakeClock()
    osc = osc if osc is not None else FakeOscClient()
    eng = AutopilotPtzEngine(
        "Autopilot PTZ",
        _config(**overrides),
        RecordingMidiOut(),
        clock=clock,
        osc_client=osc,
        rng=random.Random(seed),
    )
    return eng, osc


def _send_clock_beat(engine, beats: int = 1, *, now_start: float = 1.0, tick_dt: float = 0.020833) -> None:
    """Send `beats` worth of MIDI clock messages (24 ticks per beat)."""
    now = now_start
    for _ in range(beats * 24):
        engine.on_midi_clock("clock", now)
        now += tick_dt


def _enable_cutting(engine, *, beats: int | None = None) -> None:
    """Helper: optionally set beats_per_clip, then enable cutting."""
    if beats is not None:
        # Set beats_per_clip directly so the test isn't coupled to the lookup.
        engine._beats_per_clip = beats
    engine.on_midi_in(CH, CC_ENABLE, 127, 0.0)


# ---------------------------------------------------------------------------
# Skeleton: registration, lifecycle, status
# ---------------------------------------------------------------------------


class SkeletonTests(unittest.TestCase):
    def test_type_name_and_registration(self) -> None:
        self.assertEqual(AutopilotPtzEngine.type_name, "autopilot_ptz")
        self.assertIn("autopilot_ptz", _ENGINE_TYPES)
        self.assertIs(_ENGINE_TYPES["autopilot_ptz"], AutopilotPtzEngine)

    def test_constructs_from_minimal_config(self) -> None:
        eng = AutopilotPtzEngine(
            "PTZ", {"type": "autopilot_ptz"}, RecordingMidiOut(), osc_client=FakeOscClient()
        )
        self.assertTrue(eng.active)  # enabled defaults True

    def test_active_defaults_from_enabled_runtime_flag(self) -> None:
        eng, _ = _engine(enabled=False)
        self.assertFalse(eng.active)
        eng2, _ = _engine()
        self.assertTrue(eng2.active)  # runtime active flag on
        # ...but the cutting state still defaults OFF.
        self.assertFalse(eng2._enabled)

    def test_cutting_starts_disabled_by_default(self) -> None:
        eng, _ = _engine()
        self.assertFalse(eng._enabled)

    def test_defaults_applied(self) -> None:
        eng, _ = _engine()
        self.assertEqual(eng._beats_per_clip, 16)
        self.assertEqual(eng._clip_mode, CutMode.SEQUENTIAL)
        self.assertEqual(eng._cam_enabled, {1: True, 2: True, 3: True})
        self.assertEqual(eng._beats_lookup, tuple(DEFAULT_BEATS_LOOKUP))

    def test_status_shape_is_json_serializable(self) -> None:
        eng, _ = _engine()
        s = eng.status()
        for key in (
            "name", "type", "active", "tick_count", "clock_running", "bpm",
            "enabled", "beats_per_clip", "clip_mode", "cam_enabled",
            "selected_cam", "beat_in_clip", "cycle_index",
        ):
            self.assertIn(key, s)
        self.assertEqual(s["type"], "autopilot_ptz")
        self.assertEqual(s["clip_mode"], "SEQUENTIAL")
        self.assertEqual(s["cam_enabled"], {"1": True, "2": True, "3": True})
        json.dumps(s)  # must not raise

    def test_tick_interval_is_update_hz(self) -> None:
        eng, _ = _engine()
        self.assertAlmostEqual(eng.tick_interval_seconds(), 1.0 / 30.0)

    def test_lifecycle_hooks_no_raise_when_unmatched(self) -> None:
        eng, osc = _engine()
        eng.on_midi_in(0, CC_ENABLE, 127, 0.0)  # wrong channel
        eng.on_midi_in(CH, 5, 127, 0.0)  # unknown CC
        eng.tick(0.0)
        self.assertEqual(osc.sends, [])

    def test_shutdown_closes_osc(self) -> None:
        eng, osc = _engine()
        eng.shutdown()
        self.assertTrue(osc.closed)

    def test_registry_skips_inactive_engine(self) -> None:
        eng, osc = _engine()
        registry = EngineRegistry([eng])
        _enable_cutting(eng, beats=1)
        eng.set_active(False)
        osc.sends.clear()
        registry.on_midi_clock("clock", 0.0)  # would tick a beat if dispatched
        for _ in range(24):
            registry.on_midi_clock("clock", 0.0)
        self.assertEqual(osc.sends, [])  # no dispatch while inactive


# ---------------------------------------------------------------------------
# CC handling: enable / beats / mode / cam includes
# ---------------------------------------------------------------------------


class CcHandlingTests(unittest.TestCase):
    def test_enable_cc_toggles_cutting(self) -> None:
        eng, _ = _engine()
        eng.on_midi_in(CH, CC_ENABLE, 127, 0.0)
        self.assertTrue(eng._enabled)
        eng.on_midi_in(CH, CC_ENABLE, 0, 0.0)
        self.assertFalse(eng._enabled)

    def test_enable_threshold_at_64(self) -> None:
        eng, _ = _engine()
        eng.on_midi_in(CH, CC_ENABLE, 63, 0.0)
        self.assertFalse(eng._enabled)
        eng.on_midi_in(CH, CC_ENABLE, 64, 0.0)
        self.assertTrue(eng._enabled)

    def test_enable_rising_edge_resets_beat_counter(self) -> None:
        eng, _ = _engine()
        _enable_cutting(eng, beats=4)
        _send_clock_beat(eng, beats=2)  # beat_in_clip advances to 2
        self.assertEqual(eng._beat_in_clip, 2)
        eng.on_midi_in(CH, CC_ENABLE, 0, 0.0)  # off
        eng.on_midi_in(CH, CC_ENABLE, 127, 0.0)  # rising edge resets
        self.assertEqual(eng._beat_in_clip, 0)

    def test_beats_cc_maps_index_to_lookup(self) -> None:
        eng, _ = _engine()
        eng.on_midi_in(CH, CC_BEATS, 0, 0.0)  # → lookup[0] = 1
        self.assertEqual(eng._beats_per_clip, 1)
        eng.on_midi_in(CH, CC_BEATS, 4, 0.0)  # → lookup[4] = 32
        self.assertEqual(eng._beats_per_clip, 32)
        eng.on_midi_in(CH, CC_BEATS, 6, 0.0)  # → lookup[6] = 128
        self.assertEqual(eng._beats_per_clip, 128)

    def test_beats_cc_clamps_above_max_index(self) -> None:
        eng, _ = _engine()
        eng.on_midi_in(CH, CC_BEATS, 99, 0.0)  # clamps to lookup[-1] = 128
        self.assertEqual(eng._beats_per_clip, 128)

    def test_beats_cc_resets_beat_counter(self) -> None:
        eng, _ = _engine()
        _enable_cutting(eng, beats=8)
        _send_clock_beat(eng, beats=3)
        self.assertEqual(eng._beat_in_clip, 3)
        eng.on_midi_in(CH, CC_BEATS, 1, 0.0)  # lookup[1] = 4, different → reset
        self.assertEqual(eng._beats_per_clip, 4)
        self.assertEqual(eng._beat_in_clip, 0)

    def test_mode_cc_switches_sequential_random(self) -> None:
        eng, _ = _engine()
        eng.on_midi_in(CH, CC_MODE, 0, 0.0)
        self.assertEqual(eng._clip_mode, CutMode.SEQUENTIAL)
        eng.on_midi_in(CH, CC_MODE, 1, 0.0)
        self.assertEqual(eng._clip_mode, CutMode.RANDOM)

    def test_mode_cc_clamps_to_0_1(self) -> None:
        eng, _ = _engine()
        eng.on_midi_in(CH, CC_MODE, 99, 0.0)  # clamps to 1 (RANDOM)
        self.assertEqual(eng._clip_mode, CutMode.RANDOM)

    def test_leaving_random_clears_bag(self) -> None:
        eng, _ = _engine()
        eng.on_midi_in(CH, CC_MODE, 1, 0.0)  # RANDOM
        eng._bag = [1, 2, 3]
        eng.on_midi_in(CH, CC_MODE, 0, 0.0)  # → Sequential, bag cleared
        self.assertEqual(eng._bag, [])

    def test_cam_include_ccs_toggle(self) -> None:
        eng, _ = _engine()
        eng.on_midi_in(CH, CC_CAM2, 0, 0.0)
        self.assertFalse(eng._cam_enabled[2])
        self.assertEqual(eng._included_cams(), [1, 3])
        eng.on_midi_in(CH, CC_CAM2, 127, 0.0)
        self.assertEqual(eng._included_cams(), [1, 2, 3])

    def test_wrong_channel_ignored(self) -> None:
        eng, _ = _engine()
        eng.on_midi_in(0, CC_ENABLE, 127, 0.0)
        self.assertFalse(eng._enabled)

    def test_unknown_cc_ignored(self) -> None:
        eng, _ = _engine()
        eng.on_midi_in(CH, 5, 127, 0.0)
        eng.on_midi_in(CH, 60, 127, 0.0)
        self.assertFalse(eng._enabled)
        self.assertEqual(eng._included_cams(), [1, 2, 3])


# ---------------------------------------------------------------------------
# Cam pickers (sequential + random, deterministic with seeded Random)
# ---------------------------------------------------------------------------


class SequentialPickerTests(unittest.TestCase):
    def test_advances_1_2_3_1(self) -> None:
        eng, _ = _engine()
        self.assertEqual(eng._pick_cam(), 1)
        self.assertEqual(eng._pick_cam(), 2)
        self.assertEqual(eng._pick_cam(), 3)
        self.assertEqual(eng._pick_cam(), 1)  # wraps

    def test_skips_disabled_cam(self) -> None:
        eng, _ = _engine()
        eng.on_midi_in(CH, CC_CAM2, 0, 0.0)  # disable cam 2
        seen = [eng._pick_cam() for _ in range(4)]
        self.assertEqual(seen, [1, 3, 1, 3])

    def test_current_cam_excluded_picks_next_included(self) -> None:
        eng, _ = _engine()
        self.assertEqual(eng._pick_cam(), 1)
        self.assertEqual(eng._pick_cam(), 2)  # current is now 2
        eng.on_midi_in(CH, CC_CAM2, 0, 0.0)  # exclude the current cam
        self.assertEqual(eng._pick_cam(), 3)  # picks among still-included


class RandomPickerTests(unittest.TestCase):
    def test_each_included_cam_drawn_once_before_repeat(self) -> None:
        eng, _ = _engine(seed=1234)
        eng.on_midi_in(CH, CC_MODE, 1, 0.0)  # RANDOM
        first_bag = [eng._pick_cam() for _ in range(3)]
        self.assertEqual(sorted(first_bag), [1, 2, 3])  # permutation, no repeat
        second_bag = [eng._pick_cam() for _ in range(3)]
        self.assertEqual(sorted(second_bag), [1, 2, 3])  # reshuffled, full set again

    def test_random_is_deterministic_with_seed(self) -> None:
        eng_a, _ = _engine(seed=7)
        eng_b, _ = _engine(seed=7)
        eng_a.on_midi_in(CH, CC_MODE, 1, 0.0)
        eng_b.on_midi_in(CH, CC_MODE, 1, 0.0)
        seq_a = [eng_a._pick_cam() for _ in range(6)]
        seq_b = [eng_b._pick_cam() for _ in range(6)]
        self.assertEqual(seq_a, seq_b)

    def test_random_respects_disabled_cam(self) -> None:
        eng, _ = _engine(seed=99)
        eng.on_midi_in(CH, CC_MODE, 1, 0.0)
        eng.on_midi_in(CH, CC_CAM3, 0, 0.0)  # disable cam 3
        draws = [eng._pick_cam() for _ in range(10)]
        self.assertNotIn(3, draws)
        self.assertEqual(set(draws), {1, 2})


# ---------------------------------------------------------------------------
# Beat-driven cutting (clip-connect on /composition/layers/4/clips/N/connect)
# ---------------------------------------------------------------------------


class CuttingBeatTests(unittest.TestCase):
    def test_full_window_fires_exactly_one_connect(self) -> None:
        eng, osc = _engine()
        _enable_cutting(eng, beats=4)
        _send_clock_beat(eng, beats=4)  # one full window
        connects = osc.connects()
        self.assertEqual(len(connects), 1)
        path, value = connects[0]
        self.assertEqual(path, "/composition/layers/4/clips/1/connect")
        self.assertIs(value, True)

    def test_no_cut_before_first_full_window(self) -> None:
        eng, osc = _engine()
        _enable_cutting(eng, beats=4)
        _send_clock_beat(eng, beats=3)  # one shy of the window
        self.assertEqual(osc.connects(), [])

    def test_no_cut_on_enable(self) -> None:
        eng, osc = _engine()
        _enable_cutting(eng, beats=4)
        self.assertEqual(osc.connects(), [])  # enable alone fires nothing

    def test_sequential_cuts_cycle_cameras(self) -> None:
        eng, osc = _engine()
        _enable_cutting(eng, beats=2)
        _send_clock_beat(eng, beats=8)  # 4 windows of 2 beats each
        cams = [int(p.split("/")[-2]) for p, _ in osc.connects()]
        self.assertEqual(cams, [1, 2, 3, 1])

    def test_window_fires_on_configured_layer(self) -> None:
        eng, osc = _engine(outputs={
            "osc": {"host": "127.0.0.1", "port": 7000},
            "cutting_layer": 7,
        })
        _enable_cutting(eng, beats=2)
        _send_clock_beat(eng, beats=2)
        self.assertEqual(osc.connects()[0][0], "/composition/layers/7/clips/1/connect")

    def test_no_cut_when_disabled(self) -> None:
        eng, osc = _engine()
        # Cutting never enabled.
        _send_clock_beat(eng, beats=64)
        self.assertEqual(osc.connects(), [])

    def test_disable_mid_run_stops_cuts(self) -> None:
        eng, osc = _engine()
        _enable_cutting(eng, beats=2)
        _send_clock_beat(eng, beats=2)  # fires cam 1
        self.assertEqual(len(osc.connects()), 1)
        eng.on_midi_in(CH, CC_ENABLE, 0, 0.0)  # disable
        osc.sends.clear()
        _send_clock_beat(eng, beats=8)
        self.assertEqual(osc.connects(), [])  # no further fires

    def test_no_cut_when_zero_cams_included(self) -> None:
        eng, osc = _engine()
        eng.on_midi_in(CH, CC_CAM1, 0, 0.0)
        eng.on_midi_in(CH, CC_CAM2, 0, 0.0)
        eng.on_midi_in(CH, CC_CAM3, 0, 0.0)
        _enable_cutting(eng, beats=2)
        _send_clock_beat(eng, beats=8)
        self.assertEqual(osc.connects(), [])
        # The beat counter must not advance while no cams are included.
        self.assertEqual(eng._beat_in_clip, 0)

    def test_sequential_skips_disabled_cam_during_cutting(self) -> None:
        eng, osc = _engine()
        eng.on_midi_in(CH, CC_CAM2, 0, 0.0)  # cam 2 out
        _enable_cutting(eng, beats=1)
        _send_clock_beat(eng, beats=4)
        cams = [int(p.split("/")[-2]) for p, _ in osc.connects()]
        self.assertEqual(cams, [1, 3, 1, 3])

    def test_random_cutting_draws_each_cam_before_repeat(self) -> None:
        eng, osc = _engine(seed=5)
        eng.on_midi_in(CH, CC_MODE, 1, 0.0)  # RANDOM
        _enable_cutting(eng, beats=1)
        _send_clock_beat(eng, beats=3)  # 3 windows → one full bag
        cams = [int(p.split("/")[-2]) for p, _ in osc.connects()]
        self.assertEqual(sorted(cams), [1, 2, 3])

    def test_mode_change_takes_effect_next_boundary(self) -> None:
        eng, osc = _engine(seed=3)
        _enable_cutting(eng, beats=1)
        _send_clock_beat(eng, beats=1)  # SEQUENTIAL → cam 1
        eng.on_midi_in(CH, CC_MODE, 1, 0.0)  # switch to RANDOM mid-run
        osc.sends.clear()
        _send_clock_beat(eng, beats=3, now_start=2.0)
        cams = [int(p.split("/")[-2]) for p, _ in osc.connects()]
        # Three RANDOM draws form a full permutation of the included set.
        self.assertEqual(sorted(cams), [1, 2, 3])

    def test_selected_cam_tracked_in_status(self) -> None:
        eng, _ = _engine()
        _enable_cutting(eng, beats=2)
        _send_clock_beat(eng, beats=2)
        self.assertEqual(eng.status()["selected_cam"], 1)


# ---------------------------------------------------------------------------
# MIDI clock start/stop/continue + BPM estimate
# ---------------------------------------------------------------------------


class ClockTests(unittest.TestCase):
    def test_start_resets_state(self) -> None:
        eng, _ = _engine()
        _enable_cutting(eng, beats=4)
        _send_clock_beat(eng, beats=2)
        eng.on_midi_clock("start", 0.0)
        self.assertEqual(eng._tick_count, 0)
        self.assertEqual(eng._beat_in_clip, 0)
        self.assertEqual(eng._cycle_index, 0)

    def test_stop_pauses_continue_resumes(self) -> None:
        eng, _ = _engine()
        eng.on_midi_clock("stop", 0.0)
        ticks_before = eng._tick_count
        eng.on_midi_clock("clock", 0.1)  # ignored while stopped
        self.assertEqual(eng._tick_count, ticks_before)
        eng.on_midi_clock("continue", 0.2)
        eng.on_midi_clock("clock", 0.3)
        self.assertEqual(eng._tick_count, ticks_before + 1)

    def test_bpm_estimate_within_tolerance(self) -> None:
        eng, _ = _engine()
        now = 0.0
        for _ in range(48):  # two beats of ticks at 120 BPM
            eng.on_midi_clock("clock", now)
            now += 0.020833
        bpm = eng._estimate_bpm()
        self.assertIsNotNone(bpm)
        assert bpm is not None  # mypy
        self.assertAlmostEqual(bpm, 120.0, delta=1.0)


if __name__ == "__main__":
    unittest.main()
