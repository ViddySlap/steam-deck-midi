"""Tests for BumperBlastEngine (Pass 2 rewrite, OSC-only)."""

from __future__ import annotations

import unittest

from tests._engine_helpers import FakeOscClient, FakeRestClient, RecordingMidiOut
from windows.engines.bumper_blast import (
    DEFAULT_OSC_BLAST_PATH,
    DEFAULT_OSC_BLAST_SPEED_PATH,
    DEFAULT_OSC_SUSTAIN_PATH,
    BumperBlastEngine,
)
from windows.engines.registry import EngineRegistry
from windows.engines.steam_input_layer_tracker import (
    LAYER_CHASER,
    LAYER_FLASH,
    SteamInputLayerTrackerEngine,
)


def _comp_with_vcb(
    *,
    min_speed: float = 0.10,
    max_speed: float = 0.95,
    curve_exp: float = 2.0,
) -> dict:
    """Comp shape: just the V-C-B tunables (no layer params needed -- engine
    no longer resolves Bumper IDs; it writes OSC directly)."""
    vcb_params = {
        "BUMPER BLAST MIN SPEED": {"id": 2001, "value": min_speed},
        "BUMPER BLAST MAX SPEED": {"id": 2002, "value": max_speed},
        "BUMPER BLAST CURVE EXP": {"id": 2003, "value": curve_exp},
    }
    return {
        "layers": [],
        "video": {
            "effects": [
                {"name": {"value": "VIDDY-COLOR-BUMP"}, "params": vcb_params}
            ]
        },
    }


def _build_engine(
    *,
    comp: dict | None = None,
    overrides: dict | None = None,
    with_tracker: bool = False,
    tracker_layer: str = LAYER_CHASER,
) -> tuple[BumperBlastEngine, FakeRestClient, FakeOscClient, EngineRegistry]:
    cfg: dict = {
        "name": "Bumper Blast",
        "type": "bumper_blast",
        "inputs": {
            "channel": 0,
            "cc_amount": 2,
            "engage_threshold": 0.05,
            "disengage_threshold": 0.03,
        },
        "defaults": {
            "min_speed": 0.10,
            "max_speed": 0.95,
            "curve_exp": 2.0,
            "sustain_curve_exp": 2.0,
        },
        "layer_debounce_seconds": 0.15,
        "targets": {"vcb_effect_name": "VIDDY-COLOR-BUMP"},
        "outputs": {
            "osc": {"host": "127.0.0.1", "port": 7000},
            "osc_paths": {
                "sustain": DEFAULT_OSC_SUSTAIN_PATH,
                "blast_speed": DEFAULT_OSC_BLAST_SPEED_PATH,
                "blast": DEFAULT_OSC_BLAST_PATH,
            },
        },
    }
    if overrides:
        cfg.update(overrides)
    rest = FakeRestClient(composition=comp or _comp_with_vcb())
    osc = FakeOscClient()
    midi = RecordingMidiOut()
    engine = BumperBlastEngine(
        cfg["name"], cfg, midi, rest_client=rest, osc_client=osc
    )
    engines = [engine]
    if with_tracker:
        tracker = SteamInputLayerTrackerEngine(
            "tracker",
            {
                "chaser_notes": [60, 62],
                "flash_notes": [61, 63],
                "default_layer": tracker_layer,
            },
            RecordingMidiOut(),
        )
        engines.insert(0, tracker)
    registry = EngineRegistry(engines)
    for eng in engines:
        eng.bind_registry(registry)
    return engine, rest, osc, registry


def _sustain_writes(osc: FakeOscClient) -> list:
    return [v for path, v in osc.sends if path == DEFAULT_OSC_SUSTAIN_PATH]


def _speed_writes(osc: FakeOscClient) -> list:
    return [v for path, v in osc.sends if path == DEFAULT_OSC_BLAST_SPEED_PATH]


def _blast_writes(osc: FakeOscClient) -> list:
    return [v for path, v in osc.sends if path == DEFAULT_OSC_BLAST_PATH]


class BumperBlastTunableRefreshTests(unittest.TestCase):
    def test_init_pulls_tunables_from_vcb(self) -> None:
        comp = _comp_with_vcb(min_speed=0.2, max_speed=0.8, curve_exp=3.0)
        engine, _, _, _ = _build_engine(comp=comp)
        self.assertAlmostEqual(engine._min_speed, 0.2, places=3)
        self.assertAlmostEqual(engine._max_speed, 0.8, places=3)
        self.assertAlmostEqual(engine._curve_exp, 3.0, places=3)

    def test_missing_vcb_leaves_defaults(self) -> None:
        comp = {"layers": [], "video": {"effects": []}}
        engine, _, _, _ = _build_engine(comp=comp)
        self.assertAlmostEqual(engine._min_speed, 0.10, places=3)
        self.assertAlmostEqual(engine._max_speed, 0.95, places=3)


class BumperBlastEngageTests(unittest.TestCase):
    def test_amount_above_engage_writes_sustain_speed_and_blast_osc(self) -> None:
        engine, _, osc, _ = _build_engine()
        # 50/127 ~ 0.394 > engage 0.05.
        # Post-engage remap: (0.394 - 0.05) / 0.95 = 0.362.
        engine.on_midi_in(0, 2, 50, now=0.0)
        self.assertTrue(engine._engaged)
        remapped = (50 / 127.0 - 0.05) / 0.95
        sustains = _sustain_writes(osc)
        self.assertEqual(len(sustains), 1)
        self.assertAlmostEqual(sustains[0], (remapped ** 2) * 0.95, places=3)
        self.assertEqual(len(_speed_writes(osc)), 1)
        expected_speed = 0.10 + (0.95 - 0.10) * (remapped ** 2)
        self.assertAlmostEqual(_speed_writes(osc)[0], expected_speed, places=3)
        self.assertEqual(_blast_writes(osc), [1.0])

    def test_engage_emits_zero_sustain_just_above_engage_floor(self) -> None:
        """Post-engage remap: visible value at the engage edge starts at ~0,
        eliminating the visible "jump" from deadzone hysteresis."""
        # Tick just above engage_threshold=0.05 (~6.5/127).
        engine, _, osc, _ = _build_engine(
            overrides={
                "inputs": {
                    "channel": 0,
                    "cc_amount": 2,
                    "engage_threshold": 0.05,
                    "disengage_threshold": 0.03,
                }
            }
        )
        engine.on_midi_in(0, 2, 7, now=0.0)  # 7/127 ~ 0.055, just past 0.05
        sustain = _sustain_writes(osc)[-1]
        # Curved sustain at remapped ~0.005 is essentially 0.
        self.assertLess(sustain, 0.001)

    def test_amount_below_disengage_drops_sustain_and_releases_blast(self) -> None:
        engine, _, osc, _ = _build_engine()
        engine.on_midi_in(0, 2, 50, now=0.0)
        osc.sends.clear()
        engine.on_midi_in(0, 2, 1, now=0.1)  # 1/127 < 0.03
        self.assertFalse(engine._engaged)
        self.assertEqual(_sustain_writes(osc), [0.0])
        # Blast trigger must release on disengage so the Resolume UI
        # button doesn't stay stuck "held".
        self.assertEqual(_blast_writes(osc), [0.0])

    def test_held_amount_updates_sustain_and_blast_speed_continuously(self) -> None:
        engine, _, osc, _ = _build_engine()
        engine.on_midi_in(0, 2, 50, now=0.0)
        osc.sends.clear()
        engine.on_midi_in(0, 2, 100, now=0.05)
        engine.on_midi_in(0, 2, 127, now=0.1)
        speeds = _speed_writes(osc)
        self.assertEqual(len(speeds), 2)
        self.assertEqual(speeds, sorted(speeds))
        sustains = _sustain_writes(osc)
        self.assertEqual(len(sustains), 2)
        self.assertEqual(sustains, sorted(sustains))
        # Continuous updates must not refire the blast trigger.
        self.assertEqual(_blast_writes(osc), [])

    def test_speed_dedupe_skips_no_change(self) -> None:
        engine, _, osc, _ = _build_engine()
        engine.on_midi_in(0, 2, 64, now=0.0)
        osc.sends.clear()
        engine.on_midi_in(0, 2, 64, now=0.05)
        self.assertEqual(_speed_writes(osc), [])
        self.assertEqual(_sustain_writes(osc), [])

    def test_below_engage_threshold_does_not_engage(self) -> None:
        engine, _, osc, _ = _build_engine()
        engine.on_midi_in(0, 2, 6, now=0.0)  # 6/127 ~ 0.047 < 0.05
        self.assertFalse(engine._engaged)
        self.assertEqual(osc.sends, [])

    def test_curve_mapping_at_full_amount_hits_max_speed(self) -> None:
        engine, _, osc, _ = _build_engine()
        engine.on_midi_in(0, 2, 127, now=0.0)
        self.assertAlmostEqual(engine._last_blast_speed_sent, 0.95, places=3)

    def test_sustain_caps_at_0_95_at_full_amount(self) -> None:
        engine, _, _, _ = _build_engine()
        engine.on_midi_in(0, 2, 127, now=0.0)
        self.assertAlmostEqual(engine._last_sustain_sent, 0.95, places=3)

    def test_wrong_channel_or_cc_ignored(self) -> None:
        engine, _, osc, _ = _build_engine()
        engine.on_midi_in(14, 2, 100, now=0.0)
        engine.on_midi_in(0, 99, 100, now=0.0)
        self.assertEqual(osc.sends, [])
        self.assertFalse(engine._engaged)


class BumperBlastNoRestPutTests(unittest.TestCase):
    """Critical regression: the 2026-05-09 hot-path hazard. No REST PUTs."""

    def test_engage_does_no_rest_put_on_hot_path(self) -> None:
        engine, rest, _, _ = _build_engine()
        rest.put_calls.clear()
        engine.on_midi_in(0, 2, 100, now=0.0)
        engine.on_midi_in(0, 2, 127, now=0.05)
        engine.on_midi_in(0, 2, 1, now=0.1)
        self.assertEqual(rest.put_calls, [])


class BumperBlastLayerGuardTests(unittest.TestCase):
    def test_no_tracker_means_no_guard(self) -> None:
        engine, _, osc, _ = _build_engine()
        self.assertIsNone(engine._layer_tracker)
        engine.on_midi_in(0, 2, 100, now=0.0)
        self.assertTrue(engine._engaged)

    def test_with_tracker_only_acts_on_chaser_layer(self) -> None:
        engine, _, osc, _ = _build_engine(
            with_tracker=True, tracker_layer=LAYER_FLASH
        )
        self.assertIsNotNone(engine._layer_tracker)
        engine.on_midi_in(0, 2, 100, now=0.0)
        self.assertFalse(engine._engaged)
        # Even after engagement attempt, no OSC writes happened.
        self.assertEqual(osc.sends, [])

    def test_layer_change_during_held_trigger_disengages(self) -> None:
        engine, _, osc, _ = _build_engine(with_tracker=True)
        engine.on_midi_in(0, 2, 100, now=0.0)
        self.assertTrue(engine._engaged)
        # Simulate layer change to flash.
        tracker = engine._layer_tracker
        tracker._set_layer(LAYER_FLASH, 0.05)
        # The observer should have fired _do_disengage.
        self.assertFalse(engine._engaged)
        self.assertIn(0.0, _sustain_writes(osc))


class BumperBlastRefreshTests(unittest.TestCase):
    """`refresh()` re-pulls tunables on demand. Replaces 2026-05-11 EVENING
    periodic refresh that was choking Arena's MIDI dispatch.
    """

    def test_refresh_picks_up_dashboard_changes(self) -> None:
        comp = _comp_with_vcb(min_speed=0.10, max_speed=0.95)
        engine, rest, _, _ = _build_engine(comp=comp)
        rest.set_composition(
            _comp_with_vcb(min_speed=0.30, max_speed=0.70, curve_exp=1.5)
        )
        engine.refresh()
        self.assertAlmostEqual(engine._min_speed, 0.30, places=3)
        self.assertAlmostEqual(engine._max_speed, 0.70, places=3)
        self.assertAlmostEqual(engine._curve_exp, 1.5, places=3)


class BumperBlastNoPeriodicRestTests(unittest.TestCase):
    """Regression: the engine MUST NOT do periodic REST work.

    The 2026-05-11 EVENING REST elimination rewrote bumper_blast to do
    REST only at init (in bind_registry) and on demand via refresh().
    Periodic REST polling was contributing ~10% MIDI input drop rate.
    """

    def test_no_tick_interval_after_init(self) -> None:
        engine, _, _, _ = _build_engine()
        # Engine must not request a periodic tick.
        self.assertIsNone(engine.tick_interval_seconds())

    def test_keypress_does_no_rest_get(self) -> None:
        engine, rest, _, _ = _build_engine()
        rest.get_calls = 0
        engine.on_midi_in(0, 2, 100, now=0.0)
        engine.on_midi_in(0, 2, 1, now=0.1)
        self.assertEqual(rest.get_calls, 0)


class BumperBlastShutdownTests(unittest.TestCase):
    def test_shutdown_drops_sustain_if_engaged(self) -> None:
        engine, _, osc, _ = _build_engine()
        engine.on_midi_in(0, 2, 100, now=0.0)
        osc.sends.clear()
        engine.shutdown()
        self.assertIn(0.0, _sustain_writes(osc))
        self.assertTrue(osc.closed)


if __name__ == "__main__":
    unittest.main()
