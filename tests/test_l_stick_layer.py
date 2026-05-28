"""Tests for LStickLayerEngine.

Covers:
- default layer + factory-shaped CC assignment per set
- L3 (Note 72 ch0) toggle state transitions
- the active set's split CCs are the ones emitted (per-layer)
- split-CC polarity / direction-transition behavior (mirrors the
  receiver's axis_split_cc parser semantics)
- clean release of held CCs when the set is switched
"""

from __future__ import annotations

import unittest

from windows.engines.l_stick_layer import (
    LAYER_A,
    LAYER_B,
    LStickLayerEngine,
    X_AXIS_ACTION,
    Y_AXIS_ACTION,
)
from windows.midi import DryRunMidiOut


class RecordingMidiOut(DryRunMidiOut):
    def __init__(self) -> None:
        super().__init__(selected_port_name="recording")
        self.events: list[tuple[str, int, int, int]] = []

    def control_change(self, channel: int, control: int, value: int) -> None:
        self.events.append(("cc", channel, control, value))

    def note_on(self, channel: int, note: int, velocity: int) -> None:
        self.events.append(("note_on", channel, note, velocity))

    def note_off(self, channel: int, note: int, velocity: int = 0) -> None:
        self.events.append(("note_off", channel, note, velocity))

    def cc_events(self) -> list[tuple[int, int, int]]:
        return [(c, ctl, v) for kind, c, ctl, v in self.events if kind == "cc"]


# Factory-shaped CC sets (channel 15).
SET_A = {"x_pos": 118, "x_neg": 120, "y_pos": 119, "y_neg": 121}
SET_B = {"x_pos": 110, "x_neg": 112, "y_pos": 111, "y_neg": 113}


def _engine(**overrides) -> tuple[LStickLayerEngine, RecordingMidiOut]:
    cfg = {
        "name": "Left Stick Layer",
        "type": "l_stick_layer",
        "channel": 15,
        "toggle_note": 72,
        "toggle_note_channel": 0,
        "deadzone": 3500,
        "input_max": 32767,
        "default_layer": "a",
        "set_a": dict(SET_A),
        "set_b": dict(SET_B),
    }
    cfg.update(overrides)
    midi = RecordingMidiOut()
    engine = LStickLayerEngine(cfg["name"], cfg, midi)
    return engine, midi


class LStickLayerInitTests(unittest.TestCase):
    def test_default_layer_is_a(self) -> None:
        engine, _ = _engine()
        self.assertEqual(engine.current_layer, LAYER_A)

    def test_default_layer_b_honored(self) -> None:
        engine, _ = _engine(default_layer="b")
        self.assertEqual(engine.current_layer, LAYER_B)

    def test_invalid_default_layer_falls_back_to_a(self) -> None:
        engine, _ = _engine(default_layer="bogus")
        self.assertEqual(engine.current_layer, LAYER_A)

    def test_factory_cc_assignment(self) -> None:
        engine, _ = _engine()
        status = engine.status()
        self.assertEqual(status["set_a"], SET_A)
        self.assertEqual(status["set_b"], SET_B)
        self.assertEqual(status["channel"], 15)


class LStickLayerToggleTests(unittest.TestCase):
    def test_l3_note_toggles_a_to_b_and_back(self) -> None:
        engine, _ = _engine()
        self.assertEqual(engine.current_layer, LAYER_A)
        engine.on_note_in(channel=0, note=72, velocity=127, now=0.0)
        self.assertEqual(engine.current_layer, LAYER_B)
        engine.on_note_in(channel=0, note=72, velocity=127, now=0.1)
        self.assertEqual(engine.current_layer, LAYER_A)

    def test_note_off_velocity_zero_ignored(self) -> None:
        engine, _ = _engine()
        engine.on_note_in(channel=0, note=72, velocity=0, now=0.0)
        self.assertEqual(engine.current_layer, LAYER_A)

    def test_wrong_note_ignored(self) -> None:
        engine, _ = _engine()
        engine.on_note_in(channel=0, note=73, velocity=127, now=0.0)
        self.assertEqual(engine.current_layer, LAYER_A)

    def test_wrong_channel_ignored(self) -> None:
        engine, _ = _engine()
        engine.on_note_in(channel=2, note=72, velocity=127, now=0.0)
        self.assertEqual(engine.current_layer, LAYER_A)

    def test_toggle_channel_none_accepts_any(self) -> None:
        engine, _ = _engine(toggle_note_channel=None)
        engine.on_note_in(channel=7, note=72, velocity=127, now=0.0)
        self.assertEqual(engine.current_layer, LAYER_B)

    def test_toggle_count_and_timestamp_tracked(self) -> None:
        engine, _ = _engine()
        engine.on_note_in(channel=0, note=72, velocity=127, now=1.5)
        status = engine.status()
        self.assertEqual(status["toggle_count"], 1)
        self.assertEqual(status["last_toggle_at"], 1.5)


class LStickLayerAxisEmitTests(unittest.TestCase):
    def test_x_positive_emits_set_a_x_pos(self) -> None:
        engine, midi = _engine()
        engine.on_axis_event(X_AXIS_ACTION, 32767, now=0.0)
        self.assertEqual(midi.cc_events(), [(15, 118, 127)])

    def test_x_negative_emits_set_a_x_neg(self) -> None:
        engine, midi = _engine()
        engine.on_axis_event(X_AXIS_ACTION, -32767, now=0.0)
        self.assertEqual(midi.cc_events(), [(15, 120, 127)])

    def test_y_positive_emits_set_a_y_pos(self) -> None:
        engine, midi = _engine()
        engine.on_axis_event(Y_AXIS_ACTION, 32767, now=0.0)
        self.assertEqual(midi.cc_events(), [(15, 119, 127)])

    def test_y_negative_emits_set_a_y_neg(self) -> None:
        engine, midi = _engine()
        engine.on_axis_event(Y_AXIS_ACTION, -32767, now=0.0)
        self.assertEqual(midi.cc_events(), [(15, 121, 127)])

    def test_inside_deadzone_emits_nothing(self) -> None:
        engine, midi = _engine()
        engine.on_axis_event(X_AXIS_ACTION, 3000, now=0.0)  # < deadzone 3500
        self.assertEqual(midi.cc_events(), [])

    def test_at_deadzone_boundary_emits_nothing(self) -> None:
        engine, midi = _engine()
        engine.on_axis_event(X_AXIS_ACTION, 3500, now=0.0)  # == deadzone
        self.assertEqual(midi.cc_events(), [])

    def test_just_above_deadzone_emits_low_value(self) -> None:
        engine, midi = _engine()
        engine.on_axis_event(X_AXIS_ACTION, 3501, now=0.0)
        events = midi.cc_events()
        self.assertEqual(len(events), 1)
        ch, cc, val = events[0]
        self.assertEqual((ch, cc), (15, 118))
        self.assertEqual(val, 0)  # rounds to ~0 just above deadzone

    def test_midpoint_magnitude_emits_half(self) -> None:
        engine, midi = _engine()
        # magnitude halfway through the post-deadzone span
        mid = 3500 + (32767 - 3500) // 2
        engine.on_axis_event(X_AXIS_ACTION, mid, now=0.0)
        ch, cc, val = midi.cc_events()[-1]
        self.assertEqual((ch, cc), (15, 118))
        self.assertGreater(val, 60)
        self.assertLess(val, 67)

    def test_direction_flip_zeroes_old_cc_first(self) -> None:
        engine, midi = _engine()
        # Push right (pos) -> CC 118 ramps.
        engine.on_axis_event(X_AXIS_ACTION, 32767, now=0.0)
        # Cross to left (neg) without passing through center event: the
        # split parser should zero the old pos CC (118) then ramp neg (120).
        engine.on_axis_event(X_AXIS_ACTION, -32767, now=0.1)
        self.assertEqual(
            midi.cc_events(),
            [(15, 118, 127), (15, 118, 0), (15, 120, 127)],
        )

    def test_return_to_center_zeroes_active_cc(self) -> None:
        engine, midi = _engine()
        engine.on_axis_event(X_AXIS_ACTION, 32767, now=0.0)
        engine.on_axis_event(X_AXIS_ACTION, 0, now=0.1)
        self.assertEqual(midi.cc_events(), [(15, 118, 127), (15, 118, 0)])

    def test_unknown_axis_action_ignored(self) -> None:
        engine, midi = _engine()
        engine.on_axis_event("R_STICK_X_AXIS", 32767, now=0.0)
        self.assertEqual(midi.cc_events(), [])


class LStickLayerPerLayerEmitTests(unittest.TestCase):
    def test_set_b_emitted_after_toggle(self) -> None:
        engine, midi = _engine()
        engine.on_note_in(channel=0, note=72, velocity=127, now=0.0)  # -> B
        engine.on_axis_event(X_AXIS_ACTION, 32767, now=0.1)
        self.assertEqual(midi.cc_events(), [(15, 110, 127)])  # set B x_pos

    def test_set_b_all_four_directions(self) -> None:
        engine, midi = _engine(default_layer="b")
        engine.on_axis_event(X_AXIS_ACTION, 32767, now=0.0)   # right -> 110
        engine.on_axis_event(X_AXIS_ACTION, -32767, now=0.1)  # left -> 112
        engine.on_axis_event(Y_AXIS_ACTION, 32767, now=0.2)   # up -> 111
        engine.on_axis_event(Y_AXIS_ACTION, -32767, now=0.3)  # down -> 113
        ccs = [cc for _ch, cc, _v in midi.cc_events()]
        # x flip zeroes 110 before 112; y flip zeroes 111 before 113.
        self.assertEqual(ccs, [110, 110, 112, 111, 111, 113])

    def test_toggle_back_returns_to_set_a(self) -> None:
        engine, midi = _engine()
        engine.on_note_in(channel=0, note=72, velocity=127, now=0.0)  # -> B
        engine.on_note_in(channel=0, note=72, velocity=127, now=0.1)  # -> A
        engine.on_axis_event(Y_AXIS_ACTION, -32767, now=0.2)
        self.assertEqual(midi.cc_events(), [(15, 121, 127)])  # set A y_neg

    def test_toggle_while_held_releases_old_set_cc(self) -> None:
        engine, midi = _engine()
        # Hold stick right on set A -> CC 118 active.
        engine.on_axis_event(X_AXIS_ACTION, 32767, now=0.0)
        # Toggle to B mid-hold: the active set-A CC (118) must be zeroed so
        # it doesn't stick on the old set.
        engine.on_note_in(channel=0, note=72, velocity=127, now=0.1)
        self.assertIn((15, 118, 0), midi.cc_events())
        # Next axis event on the new set drives set-B CC, cleanly re-ramped.
        engine.on_axis_event(X_AXIS_ACTION, 32767, now=0.2)
        self.assertEqual(midi.cc_events()[-1], (15, 110, 127))


class LStickLayerChannelTests(unittest.TestCase):
    def test_custom_channel_used_for_emit(self) -> None:
        engine, midi = _engine(channel=10)
        engine.on_axis_event(X_AXIS_ACTION, 32767, now=0.0)
        self.assertEqual(midi.cc_events(), [(10, 118, 127)])


if __name__ == "__main__":
    unittest.main()
