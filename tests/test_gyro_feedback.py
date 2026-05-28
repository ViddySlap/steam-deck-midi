"""Tests for GyroFeedbackEngine (v3 — L4-gated gyro MIDI emission).

The engine turns the deck's gyro axes into MIDI CC streams the operator
can MIDI-learn in Resolume, gated by the L4 button:

- L4 TAP (down then up within tap_threshold): toggles `midi_active`.
  While active, gyro emits SET 1 (config `toggle`).
- L4 HOLD (down, still down past tap_threshold per a tick): emits SET 2
  (config `hold`, different CCs/channel) while held; release reverts to
  the current toggle state.

Inputs:
- L4 = CC 74 ch2 via on_midi_in (down>=64, up=0).
- GYRO_PITCH / GYRO_ROLL / GYRO_YAW via on_axis_event as RAW bipolar
  values (about [-750, 750]).

There is NO OSC: every output is a MIDI control_change on the bridge's
MIDI-out (DECK_IN).
"""

from __future__ import annotations

import unittest

from tests._engine_helpers import RecordingMidiOut
from windows.engines.gyro_feedback import GyroFeedbackEngine, _scale_midi
from windows.engines.registry import _ENGINE_TYPES

TOGGLE_CH = 15
HOLD_CH = 13
PITCH_CC, ROLL_CC, YAW_CC = 122, 124, 123


class _Clock:
    """Manually-advanced monotonic clock for deterministic tests."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _build(**overrides):
    cfg = {
        "name": "Gyro Feedback",
        "type": "gyro_feedback",
        "l4_cc": 74,
        "l4_channel": 2,
        "tap_threshold_ms": 200,
        "initial_midi_active": False,
        "axes": {"pitch": "GYRO_PITCH", "yaw": "GYRO_YAW", "roll": "GYRO_ROLL"},
        "raw_min": -750,
        "raw_max": 750,
        "out_min": 0,
        "out_max": 127,
        "deadzone": 100,
        "toggle": {"channel": TOGGLE_CH, "pitch": PITCH_CC, "roll": ROLL_CC, "yaw": YAW_CC},
        "hold": {"channel": HOLD_CH, "pitch": PITCH_CC, "roll": ROLL_CC, "yaw": YAW_CC},
    }
    cfg.update(overrides)
    clock = _Clock()
    midi = RecordingMidiOut()
    engine = GyroFeedbackEngine(name="Gyro Feedback", config=cfg, midi_out=midi, clock=clock)
    return engine, midi, clock


def _ccs(midi, *, channel=None, cc=None):
    return [
        (ch, c, v)
        for (kind, ch, c, v) in midi.events
        if kind == "cc" and (channel is None or ch == channel) and (cc is None or c == cc)
    ]


def _tap(engine, clock, *, hold_ms: float = 50.0) -> None:
    engine.on_midi_in(channel=2, cc=74, value=127, now=clock())
    clock.advance(hold_ms / 1000.0)
    engine.on_midi_in(channel=2, cc=74, value=0, now=clock())


def _hold(engine, clock, *, hold_ms: float = 250.0) -> None:
    engine.on_midi_in(channel=2, cc=74, value=127, now=clock())
    clock.advance(hold_ms / 1000.0)
    engine.tick(now=clock())


class TestScaling(unittest.TestCase):
    def test_endpoints_and_center(self) -> None:
        self.assertEqual(_scale_midi(750, -750, 750, 0, 127, 100), 127)
        self.assertEqual(_scale_midi(-750, -750, 750, 0, 127, 100), 0)
        self.assertEqual(_scale_midi(0, -750, 750, 0, 127, 100), 64)

    def test_deadzone_holds_center(self) -> None:
        self.assertEqual(_scale_midi(50, -750, 750, 0, 127, 100), 64)
        self.assertEqual(_scale_midi(-99, -750, 750, 0, 127, 100), 64)

    def test_clamps_beyond_range(self) -> None:
        # Unbounded accumulator past raw_max still clamps to the endpoint.
        self.assertEqual(_scale_midi(5000, -750, 750, 0, 127, 100), 127)
        self.assertEqual(_scale_midi(-5000, -750, 750, 0, 127, 100), 0)


class TestBootState(unittest.TestCase):
    def test_no_emit_until_l4(self) -> None:
        engine, midi, clock = _build()
        self.assertFalse(engine.status()["midi_active"])
        # Gyro streaming while inactive must produce NO MIDI.
        engine.on_axis_event("GYRO_PITCH", 500, now=clock())
        engine.on_axis_event("GYRO_ROLL", -300, now=clock())
        self.assertEqual(midi.events, [])


class TestTapToggle(unittest.TestCase):
    def test_tap_toggles_on(self) -> None:
        engine, _, clock = _build()
        _tap(engine, clock)
        self.assertTrue(engine.status()["midi_active"])
        self.assertEqual(engine.status()["tap_count"], 1)

    def test_tap_on_recenters_and_emits_center(self) -> None:
        engine, midi, clock = _build()
        engine.on_axis_event("GYRO_PITCH", 600, now=clock())  # ignored (inactive)
        self.assertEqual(midi.events, [])
        _tap(engine, clock)  # ON -> recenter at the current raw, emit center
        # Current position becomes the zero reference -> midpoint 64.
        self.assertEqual(_ccs(midi, channel=TOGGLE_CH, cc=PITCH_CC)[-1], (TOGGLE_CH, PITCH_CC, 64))
        midi.events.clear()
        # Tilting +/- a full raw span from the recenter point covers 0..127.
        engine.on_axis_event("GYRO_PITCH", 600 + 750, now=clock())
        self.assertEqual(_ccs(midi, channel=TOGGLE_CH, cc=PITCH_CC)[-1], (TOGGLE_CH, PITCH_CC, 127))
        engine.on_axis_event("GYRO_PITCH", 600 - 750, now=clock())
        self.assertEqual(_ccs(midi, channel=TOGGLE_CH, cc=PITCH_CC)[-1], (TOGGLE_CH, PITCH_CC, 0))

    def test_recenter_defeats_drift(self) -> None:
        # A drifted accumulator (raw far outside [-750,750]) would clamp a
        # non-recentered set to an endpoint. Recenter restores full travel.
        engine, midi, clock = _build()
        engine.on_axis_event("GYRO_PITCH", 4000, now=clock())  # drifted way out
        _tap(engine, clock)  # recenter at 4000 -> center
        self.assertEqual(_ccs(midi, channel=TOGGLE_CH, cc=PITCH_CC)[-1], (TOGGLE_CH, PITCH_CC, 64))
        midi.events.clear()
        engine.on_axis_event("GYRO_PITCH", 4000 + 700, now=clock())  # full range still reachable
        self.assertGreater(_ccs(midi, channel=TOGGLE_CH, cc=PITCH_CC)[-1][2], 120)

    def test_recenter_off_keeps_absolute(self) -> None:
        engine, midi, clock = _build(recenter_on_activate=False)
        engine.on_axis_event("GYRO_PITCH", 750, now=clock())
        _tap(engine, clock)  # no recenter -> absolute raw 750 -> 127
        self.assertEqual(_ccs(midi, channel=TOGGLE_CH, cc=PITCH_CC)[-1], (TOGGLE_CH, PITCH_CC, 127))

    def test_axis_emits_toggle_set_when_active(self) -> None:
        engine, midi, clock = _build()
        _tap(engine, clock)
        midi.events.clear()
        engine.on_axis_event("GYRO_PITCH", 750, now=clock())
        engine.on_axis_event("GYRO_ROLL", -750, now=clock())
        engine.on_axis_event("GYRO_YAW", 425, now=clock())  # 0.5 of travel -> 95
        self.assertEqual(_ccs(midi, channel=TOGGLE_CH, cc=PITCH_CC)[-1], (TOGGLE_CH, PITCH_CC, 127))
        self.assertEqual(_ccs(midi, channel=TOGGLE_CH, cc=ROLL_CC)[-1], (TOGGLE_CH, ROLL_CC, 0))
        self.assertEqual(_ccs(midi, channel=TOGGLE_CH, cc=YAW_CC)[-1], (TOGGLE_CH, YAW_CC, 95))
        # Nothing on the hold channel.
        self.assertEqual(_ccs(midi, channel=HOLD_CH), [])

    def test_second_tap_off_then_muted(self) -> None:
        engine, midi, clock = _build()
        _tap(engine, clock)  # ON
        _tap(engine, clock)  # OFF
        self.assertFalse(engine.status()["midi_active"])
        midi.events.clear()
        engine.on_axis_event("GYRO_PITCH", 500, now=clock())
        engine.on_axis_event("GYRO_ROLL", -300, now=clock())
        self.assertEqual(midi.events, [])

    def test_dedupe_identical_values(self) -> None:
        engine, midi, clock = _build()
        _tap(engine, clock)
        midi.events.clear()
        engine.on_axis_event("GYRO_PITCH", 750, now=clock())
        engine.on_axis_event("GYRO_PITCH", 750, now=clock())  # identical -> deduped
        self.assertEqual(len(_ccs(midi, channel=TOGGLE_CH, cc=PITCH_CC)), 1)

    def test_wrong_cc_and_channel_ignored(self) -> None:
        engine, _, clock = _build()
        engine.on_midi_in(channel=2, cc=99, value=127, now=clock())
        engine.on_midi_in(channel=15, cc=74, value=127, now=clock())
        self.assertFalse(engine.status()["l4_down"])
        self.assertFalse(engine.status()["midi_active"])


class TestHoldMode(unittest.TestCase):
    def test_hold_emits_hold_set_not_toggle(self) -> None:
        engine, midi, clock = _build()
        _hold(engine, clock)
        self.assertTrue(engine.status()["hold_mode_active"])
        self.assertEqual(engine.status()["hold_enter_count"], 1)
        midi.events.clear()
        engine.on_axis_event("GYRO_PITCH", 750, now=clock())
        engine.on_axis_event("GYRO_ROLL", -750, now=clock())
        self.assertEqual(_ccs(midi, channel=HOLD_CH, cc=PITCH_CC)[-1], (HOLD_CH, PITCH_CC, 127))
        self.assertEqual(_ccs(midi, channel=HOLD_CH, cc=ROLL_CC)[-1], (HOLD_CH, ROLL_CC, 0))
        # No emission on the toggle channel while holding.
        self.assertEqual(_ccs(midi, channel=TOGGLE_CH), [])

    def test_hold_release_reverts_to_toggle(self) -> None:
        engine, midi, clock = _build()
        _tap(engine, clock)  # toggle ON
        self.assertTrue(engine.status()["midi_active"])
        _hold(engine, clock)  # now hold
        self.assertTrue(engine.status()["hold_mode_active"])
        engine.on_axis_event("GYRO_PITCH", 750, now=clock())  # to hold set
        midi.events.clear()
        engine.on_midi_in(channel=2, cc=74, value=0, now=clock())  # release
        self.assertFalse(engine.status()["hold_mode_active"])
        self.assertEqual(engine.status()["hold_exit_count"], 1)
        # Toggle still active -> resumes emitting on the toggle channel.
        self.assertTrue(engine.status()["midi_active"])
        engine.on_axis_event("GYRO_ROLL", 750, now=clock())
        self.assertEqual(_ccs(midi, channel=TOGGLE_CH, cc=ROLL_CC)[-1], (TOGGLE_CH, ROLL_CC, 127))

    def test_hold_independent_of_toggle(self) -> None:
        engine, midi, clock = _build()
        # Toggle is OFF; hold should still emit set 2 while held...
        _hold(engine, clock)
        midi.events.clear()
        engine.on_axis_event("GYRO_PITCH", 750, now=clock())
        self.assertEqual(_ccs(midi, channel=HOLD_CH, cc=PITCH_CC)[-1], (HOLD_CH, PITCH_CC, 127))
        # ...and on release, with toggle still OFF, nothing further emits.
        engine.on_midi_in(channel=2, cc=74, value=0, now=clock())
        midi.events.clear()
        engine.on_axis_event("GYRO_PITCH", 0, now=clock())
        self.assertEqual(midi.events, [])

    def test_hold_does_not_count_as_tap(self) -> None:
        engine, _, clock = _build()
        _hold(engine, clock)
        engine.on_midi_in(channel=2, cc=74, value=0, now=clock())
        self.assertFalse(engine.status()["midi_active"])
        self.assertEqual(engine.status()["tap_count"], 0)

    def test_release_past_threshold_without_tick_is_not_tap(self) -> None:
        engine, _, clock = _build()
        engine.on_midi_in(channel=2, cc=74, value=127, now=clock())
        clock.advance(0.30)  # past 200ms, but no tick() armed hold
        engine.on_midi_in(channel=2, cc=74, value=0, now=clock())
        self.assertFalse(engine.status()["midi_active"])
        self.assertEqual(engine.status()["tap_count"], 0)


class TestLegacyTolerance(unittest.TestCase):
    def test_gyro_state_now_ignored(self) -> None:
        engine, midi, clock = _build()
        _tap(engine, clock)  # active, so a routed axis WOULD emit
        midi.events.clear()
        engine.on_axis_event("GYRO_STATE_NOW", 1, now=clock())
        engine.on_axis_event("GYRO_STATE_NOW", 0, now=clock())
        self.assertEqual(engine.status()["ignored_legacy_count"], 2)
        self.assertEqual(midi.events, [])


class TestCustomMapping(unittest.TestCase):
    def test_custom_cc_sets(self) -> None:
        engine, midi, clock = _build(
            toggle={"channel": 11, "pitch": 10, "roll": 11, "yaw": 12},
            hold={"channel": 10, "pitch": 20, "roll": 21, "yaw": 22},
        )
        _tap(engine, clock)
        midi.events.clear()
        engine.on_axis_event("GYRO_PITCH", 750, now=clock())
        self.assertEqual(_ccs(midi, channel=11, cc=10)[-1], (11, 10, 127))

    def test_custom_out_range(self) -> None:
        engine, midi, clock = _build(out_min=0, out_max=100)
        _tap(engine, clock)
        midi.events.clear()
        engine.on_axis_event("GYRO_PITCH", 750, now=clock())
        self.assertEqual(_ccs(midi, channel=TOGGLE_CH, cc=PITCH_CC)[-1], (TOGGLE_CH, PITCH_CC, 100))

    def test_per_axis_raw_range(self) -> None:
        # pitch gets a tighter range (more sensitive); roll keeps the default.
        engine, midi, clock = _build(axis_raw={"pitch": {"raw_min": -300, "raw_max": 300}})
        _tap(engine, clock)  # recenter at 0
        midi.events.clear()
        engine.on_axis_event("GYRO_PITCH", 300, now=clock())  # full range at 300
        self.assertEqual(_ccs(midi, channel=TOGGLE_CH, cc=PITCH_CC)[-1], (TOGGLE_CH, PITCH_CC, 127))
        engine.on_axis_event("GYRO_ROLL", 300, now=clock())  # still mid-ish on default range
        roll_v = _ccs(midi, channel=TOGGLE_CH, cc=ROLL_CC)[-1][2]
        self.assertTrue(64 < roll_v < 127)

    def test_custom_tap_threshold(self) -> None:
        engine, _, clock = _build(tap_threshold_ms=500)
        self.assertEqual(engine.status()["tap_threshold_ms"], 500.0)
        engine.on_midi_in(channel=2, cc=74, value=127, now=clock())
        clock.advance(0.30)
        engine.tick(now=clock())  # 300ms < 500ms -> hold NOT armed
        self.assertFalse(engine.status()["hold_mode_active"])
        engine.on_midi_in(channel=2, cc=74, value=0, now=clock())
        self.assertTrue(engine.status()["midi_active"])  # 300ms = tap


class TestRegistryIntegration(unittest.TestCase):
    def test_engine_type_registered(self) -> None:
        self.assertIn("gyro_feedback", _ENGINE_TYPES)
        self.assertIs(_ENGINE_TYPES["gyro_feedback"], GyroFeedbackEngine)


if __name__ == "__main__":
    unittest.main()
