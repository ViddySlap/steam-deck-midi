"""Tests for ChaserStackDispatcherEngine."""

from __future__ import annotations

import unittest

from tests._engine_helpers import FakeOscClient, FakeRestClient, RecordingMidiOut
from windows.engines.chaser_stack_dispatcher import (
    DEFAULT_OSC_CHASER_STEP_PATH,
    DEFAULT_OSC_FEEDBACK_AMOUNT_PATH,
    DEFAULT_OSC_FEEDBACK_HUE_PATH,
    ChaserStackDispatcherEngine,
)
from windows.engines.registry import EngineRegistry
from windows.engines.steam_input_layer_tracker import (
    LAYER_CHASER,
    LAYER_FLASH,
    SteamInputLayerTrackerEngine,
)


def _comp_with_vcb(
    *,
    min_step: float = 0.0,
    max_step: float = 0.5,
    feedback: float = 0.7,
) -> dict:
    vcb_params = {
        "CHASER STACK MIN STEP": {"id": 3001, "value": min_step},
        "CHASER STACK MAX STEP": {"id": 3002, "value": max_step},
        "CHASER STACK FEEDBACK": {"id": 3004, "value": feedback},
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
) -> tuple[ChaserStackDispatcherEngine, FakeRestClient, FakeOscClient]:
    cfg: dict = {
        "name": "Chaser Stack",
        "type": "chaser_stack_dispatcher",
        "inputs": {
            "channel": 0,
            "cc_amount": 1,
            "engage_threshold": 0.05,
            "disengage_threshold": 0.03,
        },
        "tick_hz": 30,
        "defaults": {
            "min_step": 0.0,
            "max_step": 0.5,
            "feedback_max": 0.7,
            "rate_curve_exp": 2.0,
        },
        "layer_debounce_seconds": 0.15,
        "targets": {"vcb_effect_name": "VIDDY-COLOR-BUMP"},
    }
    if overrides:
        cfg.update(overrides)
    rest = FakeRestClient(composition=comp or _comp_with_vcb())
    osc = FakeOscClient()
    midi = RecordingMidiOut()
    engine = ChaserStackDispatcherEngine(
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
    return engine, rest, osc


def _writes(osc: FakeOscClient, path: str) -> list:
    return [v for p, v in osc.sends if p == path]


class ChaserStackEngageTests(unittest.TestCase):
    def test_engage_resets_step(self) -> None:
        engine, _, _ = _build_engine()
        engine.on_midi_in(0, 1, 50, now=0.0)
        self.assertTrue(engine._engaged)
        self.assertEqual(engine._current_step, 0.0)

    def test_engage_writes_feedback_hue_and_amount(self) -> None:
        engine, _, osc = _build_engine()
        osc.sends.clear()
        engine.on_midi_in(0, 1, 50, now=0.0)
        # Post-engage remap: (50/127 - 0.05) / 0.95 = 0.362.
        remapped = (50 / 127.0 - 0.05) / 0.95
        self.assertAlmostEqual(
            _writes(osc, DEFAULT_OSC_FEEDBACK_HUE_PATH)[-1], remapped, places=3
        )
        self.assertAlmostEqual(
            _writes(osc, DEFAULT_OSC_FEEDBACK_AMOUNT_PATH)[-1],
            remapped * 0.7,
            places=3,
        )

    def test_engage_emits_zero_feedback_just_above_engage_floor(self) -> None:
        engine, _, osc = _build_engine()
        engine.on_midi_in(0, 1, 7, now=0.0)  # 7/127 ~ 0.055, just past 0.05
        hue = _writes(osc, DEFAULT_OSC_FEEDBACK_HUE_PATH)[-1]
        amt = _writes(osc, DEFAULT_OSC_FEEDBACK_AMOUNT_PATH)[-1]
        self.assertLess(hue, 0.01)
        self.assertLess(amt, 0.01)

    def test_disengage_drops_feedback_to_zero(self) -> None:
        engine, _, osc = _build_engine()
        engine.on_midi_in(0, 1, 50, now=0.0)
        osc.sends.clear()
        engine.on_midi_in(0, 1, 1, now=0.1)
        self.assertFalse(engine._engaged)
        self.assertEqual(_writes(osc, DEFAULT_OSC_FEEDBACK_HUE_PATH), [0.0])
        self.assertEqual(_writes(osc, DEFAULT_OSC_FEEDBACK_AMOUNT_PATH), [0.0])

    def test_peak_does_not_fire_color_bump_bump(self) -> None:
        """Regression: L2 is a pure ramp; no flash/bump should fire at any norm."""
        engine, _, osc = _build_engine()
        osc.sends.clear()
        engine.on_midi_in(0, 1, 127, now=0.0)
        for p, _v in osc.sends:
            self.assertNotIn("colorbump", p)


class ChaserStackStepTickTests(unittest.TestCase):
    def test_tick_advances_step_when_engaged(self) -> None:
        engine, _, osc = _build_engine()
        engine.on_midi_in(0, 1, 127, now=0.0)
        osc.sends.clear()
        engine.tick(now=1.0)
        step_writes = _writes(osc, DEFAULT_OSC_CHASER_STEP_PATH)
        self.assertEqual(len(step_writes), 1)
        # At full norm, rate_hz = max_step = 0.5; tick advance = 0.5/30.
        self.assertAlmostEqual(step_writes[0], 0.5 / 30.0, places=4)

    def test_tick_does_nothing_when_disengaged(self) -> None:
        engine, _, osc = _build_engine()
        osc.sends.clear()
        engine.tick(now=1.0)
        self.assertEqual(_writes(osc, DEFAULT_OSC_CHASER_STEP_PATH), [])


class ChaserStackNoRestPutTests(unittest.TestCase):
    """Critical regression: no REST PUTs on the keypress path."""

    def test_engage_does_no_rest_put(self) -> None:
        engine, rest, _ = _build_engine()
        rest.put_calls.clear()
        engine.on_midi_in(0, 1, 100, now=0.0)
        engine.on_midi_in(0, 1, 127, now=0.05)
        engine.on_midi_in(0, 1, 0, now=0.1)
        self.assertEqual(rest.put_calls, [])

    def test_tick_does_no_rest_put_when_engaged(self) -> None:
        engine, rest, _ = _build_engine()
        engine.on_midi_in(0, 1, 127, now=0.0)
        rest.put_calls.clear()
        engine.tick(now=1.0)
        self.assertEqual(rest.put_calls, [])

    def test_tick_does_no_rest_get(self) -> None:
        """Regression: the 30Hz step animator tick must not poll REST."""
        engine, rest, _ = _build_engine()
        engine.on_midi_in(0, 1, 127, now=0.0)
        rest.get_calls = 0
        for i in range(10):
            engine.tick(now=1.0 + i * 0.1)
        self.assertEqual(rest.get_calls, 0)


class ChaserStackLayerGuardTests(unittest.TestCase):
    def test_no_tracker_means_no_guard(self) -> None:
        engine, _, _ = _build_engine()
        self.assertIsNone(engine._layer_tracker)
        engine.on_midi_in(0, 1, 100, now=0.0)
        self.assertTrue(engine._engaged)

    def test_with_tracker_only_acts_on_chaser_layer(self) -> None:
        engine, _, osc = _build_engine(
            with_tracker=True, tracker_layer=LAYER_FLASH
        )
        osc.sends.clear()
        engine.on_midi_in(0, 1, 100, now=0.0)
        self.assertFalse(engine._engaged)
        self.assertEqual(osc.sends, [])

    def test_layer_change_disengages_during_hold(self) -> None:
        engine, _, _ = _build_engine(with_tracker=True)
        engine.on_midi_in(0, 1, 100, now=0.0)
        self.assertTrue(engine._engaged)
        engine._layer_tracker._set_layer(LAYER_FLASH, 0.05)
        self.assertFalse(engine._engaged)


class ChaserStackTunableRefreshTests(unittest.TestCase):
    def test_init_pulls_tunables(self) -> None:
        comp = _comp_with_vcb(min_step=0.1, max_step=0.8)
        engine, _, _ = _build_engine(comp=comp)
        self.assertAlmostEqual(engine._min_step, 0.1, places=3)
        self.assertAlmostEqual(engine._max_step, 0.8, places=3)

    def test_refresh_picks_up_dashboard_changes(self) -> None:
        engine, rest, _ = _build_engine()
        rest.set_composition(
            _comp_with_vcb(min_step=0.2, max_step=0.6, feedback=0.4)
        )
        engine.refresh()
        self.assertAlmostEqual(engine._min_step, 0.2, places=3)
        self.assertAlmostEqual(engine._max_step, 0.6, places=3)
        self.assertAlmostEqual(engine._feedback_max, 0.4, places=3)


if __name__ == "__main__":
    unittest.main()
