"""Tests for GyroFeedbackEngine (v2 gyro router).

The engine routes the deck's three gyro axes to Resolume OSC targets,
with an L4 tap-vs-hold gesture selecting the mode:

- L4 TAP (down then up within tap_threshold): toggles `feedback_active`.
- L4 HOLD (down, still down past tap_threshold per a tick): enters SHAKE
  routing; release zeros SHAKE and reverts to feedback routing.

Inputs:
- L4 = CC 74 ch2 via on_midi_in (down=127, up=0).
- GYRO_PITCH / GYRO_ROLL via on_axis_event as RAW bipolar values
  (about [-750, 750]). GYRO_YAW is spare.

Covers:
- TAP toggles feedback on/off.
- Toggle-OFF writes opacity 0.0 once, then mutes.
- feedback-on PITCH->opacity and ROLL->transform-X normalization.
- HOLD enters SHAKE routing (PITCH->distance, ROLL->frequency).
- HOLD release zeros SHAKE and reverts to feedback routing.
- Bipolar normalization midpoint + endpoints.
- Legacy GYRO_STATE_NOW axis event tolerated (no crash, no state flip).
- Registry registration sanity.
"""

from __future__ import annotations

import unittest

from tests._engine_helpers import FakeOscClient, RecordingMidiOut
from windows.engines.gyro_feedback import GyroFeedbackEngine
from windows.engines.registry import _ENGINE_TYPES

OPACITY_PATH = "/composition/layers/11/master"
TRANSFORM_X_PATH = "/composition/layers/11/video/transform/position-x"
SHAKE_DISTANCE_PATH = "/shake/distance/test"
SHAKE_FREQUENCY_PATH = "/shake/frequency/test"


class _Clock:
    """Manually-advanced monotonic clock for deterministic tests."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _build(*, bind: bool = True, **overrides):
    cfg = {
        "name": "Gyro Feedback",
        "type": "gyro_feedback",
        "l4_cc": 74,
        "l4_channel": 2,
        "tap_threshold_ms": 200,
        "initial_feedback_active": False,
        "axes": {"pitch": "GYRO_PITCH", "yaw": "GYRO_YAW", "roll": "GYRO_ROLL"},
        "raw_min": -750,
        "raw_max": 750,
        "out_min": 0.0,
        "out_max": 1.0,
        "targets": {
            "feedback_opacity": {"path": OPACITY_PATH},
            "feedback_transform_x": {"path": TRANSFORM_X_PATH},
            "shake_distance": {"path": SHAKE_DISTANCE_PATH},
            "shake_frequency": {"path": SHAKE_FREQUENCY_PATH},
        },
    }
    cfg.update(overrides)
    osc = FakeOscClient()
    clock = _Clock()
    engine = GyroFeedbackEngine(
        name="Gyro Feedback",
        config=cfg,
        midi_out=RecordingMidiOut(),
        clock=clock,
        osc_client=osc,
    )
    if bind:
        engine.bind_registry(registry=None)
        osc.sends.clear()  # discard the boot rest-state writes
    return engine, osc, clock


def _values_for(osc: FakeOscClient, path: str) -> list:
    return [v for p, v in osc.sends if p == path]


class TestBootState(unittest.TestCase):
    def test_bind_registry_writes_idle_rest_state(self) -> None:
        engine, osc, _ = _build(bind=False)
        engine.bind_registry(registry=None)
        # Opacity 0.0 once + SHAKE distance/frequency zeroed.
        self.assertIn((OPACITY_PATH, 0.0), osc.sends)
        self.assertIn((SHAKE_DISTANCE_PATH, 0.0), osc.sends)
        self.assertIn((SHAKE_FREQUENCY_PATH, 0.0), osc.sends)


class TestTapToggle(unittest.TestCase):
    def _tap(self, engine, clock, *, hold_ms: float = 50.0) -> None:
        engine.on_midi_in(channel=2, cc=74, value=127, now=clock())
        clock.advance(hold_ms / 1000.0)
        engine.on_midi_in(channel=2, cc=74, value=0, now=clock())

    def test_tap_toggles_feedback_on(self) -> None:
        engine, _, clock = _build()
        self.assertFalse(engine.status()["feedback_active"])
        self._tap(engine, clock)
        self.assertTrue(engine.status()["feedback_active"])
        self.assertEqual(engine.status()["tap_count"], 1)

    def test_second_tap_toggles_feedback_off(self) -> None:
        engine, osc, clock = _build()
        self._tap(engine, clock)
        # Feed a gyro value so opacity is non-zero while feedback is on.
        engine.on_axis_event("GYRO_PITCH", 750, now=clock())
        self.assertEqual(_values_for(osc, OPACITY_PATH)[-1], 1.0)
        # Second tap toggles OFF -> opacity 0.0 written once.
        self._tap(engine, clock)
        self.assertFalse(engine.status()["feedback_active"])
        self.assertEqual(_values_for(osc, OPACITY_PATH)[-1], 0.0)

    def test_toggle_off_then_gyro_is_muted(self) -> None:
        engine, osc, clock = _build()
        self._tap(engine, clock)  # ON
        self._tap(engine, clock)  # OFF -> writes opacity 0.0 once
        osc.sends.clear()
        # Gyro events while muted must produce NO writes.
        engine.on_axis_event("GYRO_PITCH", 500, now=clock())
        engine.on_axis_event("GYRO_ROLL", -300, now=clock())
        self.assertEqual(osc.sends, [])

    def test_wrong_cc_and_channel_ignored(self) -> None:
        engine, _, clock = _build()
        engine.on_midi_in(channel=2, cc=99, value=127, now=clock())
        engine.on_midi_in(channel=15, cc=74, value=127, now=clock())
        # No L4 gesture registered.
        self.assertFalse(engine.status()["l4_down"])
        self.assertFalse(engine.status()["feedback_active"])


class TestFeedbackRouting(unittest.TestCase):
    def _turn_feedback_on(self, engine, clock) -> None:
        engine.on_midi_in(channel=2, cc=74, value=127, now=clock())
        clock.advance(0.05)
        engine.on_midi_in(channel=2, cc=74, value=0, now=clock())

    def test_pitch_to_opacity_normalization(self) -> None:
        engine, osc, clock = _build()
        self._turn_feedback_on(engine, clock)
        osc.sends.clear()
        # raw +750 -> 1.0
        engine.on_axis_event("GYRO_PITCH", 750, now=clock())
        self.assertAlmostEqual(_values_for(osc, OPACITY_PATH)[-1], 1.0, places=4)
        # raw 0 -> midpoint 0.5
        engine.on_axis_event("GYRO_PITCH", 0, now=clock())
        self.assertAlmostEqual(_values_for(osc, OPACITY_PATH)[-1], 0.5, places=4)
        # raw -750 -> 0.0
        engine.on_axis_event("GYRO_PITCH", -750, now=clock())
        self.assertAlmostEqual(_values_for(osc, OPACITY_PATH)[-1], 0.0, places=4)

    def test_roll_to_transform_x_normalization(self) -> None:
        engine, osc, clock = _build()
        self._turn_feedback_on(engine, clock)
        osc.sends.clear()
        engine.on_axis_event("GYRO_ROLL", 375, now=clock())
        # 375 of [-750,750] -> 0.75
        self.assertAlmostEqual(_values_for(osc, TRANSFORM_X_PATH)[-1], 0.75, places=4)

    def test_yaw_is_spare_no_output(self) -> None:
        engine, osc, clock = _build()
        self._turn_feedback_on(engine, clock)
        osc.sends.clear()
        engine.on_axis_event("GYRO_YAW", 500, now=clock())
        self.assertEqual(osc.sends, [])


class TestHoldMode(unittest.TestCase):
    def test_hold_enters_shake_routing(self) -> None:
        engine, osc, clock = _build()
        engine.on_midi_in(channel=2, cc=74, value=127, now=clock())
        # Advance past the 200ms tap threshold; tick should arm hold.
        clock.advance(0.25)
        engine.tick(now=clock())
        self.assertTrue(engine.status()["hold_mode_active"])
        self.assertEqual(engine.status()["hold_enter_count"], 1)
        osc.sends.clear()
        # Now gyro routes to SHAKE, not feedback.
        engine.on_axis_event("GYRO_PITCH", 750, now=clock())
        engine.on_axis_event("GYRO_ROLL", -750, now=clock())
        self.assertAlmostEqual(_values_for(osc, SHAKE_DISTANCE_PATH)[-1], 1.0, places=4)
        self.assertAlmostEqual(_values_for(osc, SHAKE_FREQUENCY_PATH)[-1], 0.0, places=4)
        # No feedback writes while holding.
        self.assertEqual(_values_for(osc, OPACITY_PATH), [])

    def test_hold_release_zeros_shake_and_reverts(self) -> None:
        engine, osc, clock = _build()
        # Feedback ON first so we can verify the revert restores it.
        engine.on_midi_in(channel=2, cc=74, value=127, now=clock())
        clock.advance(0.05)
        engine.on_midi_in(channel=2, cc=74, value=0, now=clock())
        self.assertTrue(engine.status()["feedback_active"])
        # Now HOLD L4.
        engine.on_midi_in(channel=2, cc=74, value=127, now=clock())
        clock.advance(0.25)
        engine.tick(now=clock())
        self.assertTrue(engine.status()["hold_mode_active"])
        # Push SHAKE values up while holding.
        engine.on_axis_event("GYRO_PITCH", 750, now=clock())
        engine.on_axis_event("GYRO_ROLL", 750, now=clock())
        osc.sends.clear()
        # Release the hold.
        engine.on_midi_in(channel=2, cc=74, value=0, now=clock())
        self.assertFalse(engine.status()["hold_mode_active"])
        self.assertEqual(engine.status()["hold_exit_count"], 1)
        # SHAKE explicitly zeroed on exit.
        self.assertEqual(_values_for(osc, SHAKE_DISTANCE_PATH)[-1], 0.0)
        self.assertEqual(_values_for(osc, SHAKE_FREQUENCY_PATH)[-1], 0.0)
        # Reverted to feedback routing (feedback still ON).
        self.assertTrue(engine.status()["feedback_active"])
        engine.on_axis_event("GYRO_PITCH", 0, now=clock())
        self.assertAlmostEqual(_values_for(osc, OPACITY_PATH)[-1], 0.5, places=4)

    def test_hold_does_not_count_as_tap(self) -> None:
        engine, _, clock = _build()
        engine.on_midi_in(channel=2, cc=74, value=127, now=clock())
        clock.advance(0.25)
        engine.tick(now=clock())
        engine.on_midi_in(channel=2, cc=74, value=0, now=clock())
        # A hold must not toggle feedback.
        self.assertFalse(engine.status()["feedback_active"])
        self.assertEqual(engine.status()["tap_count"], 0)

    def test_release_past_threshold_without_tick_zeros_shake(self) -> None:
        """Defensive: if down->up exceeds threshold but no tick armed hold,
        engine treats it as a hold-release (zeros SHAKE), not a tap."""
        engine, osc, clock = _build()
        engine.on_midi_in(channel=2, cc=74, value=127, now=clock())
        clock.advance(0.30)  # well past 200ms, but no tick() called
        osc.sends.clear()
        engine.on_midi_in(channel=2, cc=74, value=0, now=clock())
        # Not a tap.
        self.assertFalse(engine.status()["feedback_active"])
        self.assertEqual(engine.status()["tap_count"], 0)
        # SHAKE zeroed defensively.
        self.assertIn(SHAKE_DISTANCE_PATH, [p for p, _ in osc.sends])


class TestLegacyTolerance(unittest.TestCase):
    def test_gyro_state_now_ignored_no_crash_no_flip(self) -> None:
        engine, osc, clock = _build()
        before = engine.status()["feedback_active"]
        # Legacy ping with value 1 (would have meant "gyro on" in v1).
        engine.on_axis_event("GYRO_STATE_NOW", 1, now=clock())
        engine.on_axis_event("GYRO_STATE_NOW", 0, now=clock())
        # State unchanged, counted, no OSC emitted.
        self.assertEqual(engine.status()["feedback_active"], before)
        self.assertEqual(engine.status()["ignored_legacy_count"], 2)
        self.assertEqual(osc.sends, [])


class TestCustomMapping(unittest.TestCase):
    def test_custom_out_range_applied(self) -> None:
        engine, osc, clock = _build(
            targets={
                "feedback_opacity": {
                    "path": OPACITY_PATH,
                    "out_min": 0.2,
                    "out_max": 0.8,
                },
                "feedback_transform_x": {"path": TRANSFORM_X_PATH},
                "shake_distance": {"path": SHAKE_DISTANCE_PATH},
                "shake_frequency": {"path": SHAKE_FREQUENCY_PATH},
            }
        )
        engine.on_midi_in(channel=2, cc=74, value=127, now=clock())
        clock.advance(0.05)
        engine.on_midi_in(channel=2, cc=74, value=0, now=clock())
        osc.sends.clear()
        # raw +750 -> out_max 0.8
        engine.on_axis_event("GYRO_PITCH", 750, now=clock())
        self.assertAlmostEqual(_values_for(osc, OPACITY_PATH)[-1], 0.8, places=4)
        # raw 0 -> midpoint of [0.2, 0.8] = 0.5
        engine.on_axis_event("GYRO_PITCH", 0, now=clock())
        self.assertAlmostEqual(_values_for(osc, OPACITY_PATH)[-1], 0.5, places=4)

    def test_custom_tap_threshold(self) -> None:
        engine, _, clock = _build(tap_threshold_ms=500)
        self.assertEqual(engine.status()["tap_threshold_ms"], 500.0)
        # A 300ms hold is now a TAP (below the 500ms threshold).
        engine.on_midi_in(channel=2, cc=74, value=127, now=clock())
        clock.advance(0.30)
        engine.tick(now=clock())  # 300ms < 500ms -> hold NOT armed
        self.assertFalse(engine.status()["hold_mode_active"])
        engine.on_midi_in(channel=2, cc=74, value=0, now=clock())
        self.assertTrue(engine.status()["feedback_active"])


class TestRegistryIntegration(unittest.TestCase):
    def test_engine_type_registered(self) -> None:
        self.assertIn("gyro_feedback", _ENGINE_TYPES)
        self.assertIs(_ENGINE_TYPES["gyro_feedback"], GyroFeedbackEngine)


if __name__ == "__main__":
    unittest.main()
