"""Tests for TvTreeModeEngine (R3-toggled Christmas look slot jobs)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from windows.engines.base import Engine
from windows.engines.registry import EngineRegistry, engine_class
from windows.engines.tv_tree_mode import TvTreeModeEngine
from windows.midi import DryRunMidiOut

FACTORY = Path(__file__).resolve().parents[1] / "config" / "engines.factory" / "tv_tree_mode.json"


class RecordingMidiOut(DryRunMidiOut):
    def __init__(self) -> None:
        super().__init__(selected_port_name="recording")
        self.ccs: list[tuple[int, int, int]] = []

    def control_change(self, channel: int, control: int, value: int) -> None:
        self.ccs.append((channel, control, value))

    def last(self, cc: int) -> int | None:
        for ch, c, v in reversed(self.ccs):
            if c == cc:
                return v
        return None


class FakeEngine(Engine):
    def __init__(self, type_name: str) -> None:
        super().__init__(type_name, {"enabled": True}, DryRunMidiOut(selected_port_name="x"))
        self.type_name = type_name
        self.released = 0

    def _release_active_ccs(self) -> None:
        self.released += 1


def _setup(**overrides):
    cfg = json.loads(FACTORY.read_text(encoding="utf-8"))
    cfg["start_active"] = True
    cfg.update(overrides)
    out = RecordingMidiOut()
    eng = TvTreeModeEngine("TV Tree Mode", cfg, out, clock=lambda: 0.0)
    stick = FakeEngine("l_stick_layer")
    gyro = FakeEngine("gyro_feedback")
    reg = EngineRegistry([stick, gyro])
    reg.add(eng)
    eng.bind_registry(reg)
    return eng, out, reg, stick, gyro


def press(eng, action, state="down"):
    eng.on_input_event(action, state, 0.0)


class TvTreeModeTests(unittest.TestCase):
    def test_registered_loaded_but_inactive_by_default(self):
        self.assertIs(engine_class("tv_tree_mode"), TvTreeModeEngine)
        cfg = json.loads(FACTORY.read_text(encoding="utf-8"))
        self.assertTrue(cfg["enabled"])           # must load, or no preset can switch it on
        eng = TvTreeModeEngine("t", cfg, RecordingMidiOut(), clock=lambda: 0.0)
        self.assertFalse(eng.active)

    def test_mode_off_is_inert(self):
        eng, out, reg, stick, gyro = _setup()
        press(eng, "BTN_A")
        eng.on_axis_event("L_STICK_X_AXIS", 30000, 0.0)
        self.assertEqual(out.ccs, [])
        self.assertTrue(reg.should_emit_note(0, 36, 127, 0.0))
        self.assertTrue(stick.active and gyro.active)

    def test_r3_toggles_and_publishes_rest_state(self):
        eng, out, reg, stick, gyro = _setup()
        press(eng, "RIGHT_STICK_CLICK_R3")
        self.assertTrue(eng.mode)
        self.assertEqual(out.last(20), 127)
        self.assertEqual(out.last(6), 64)
        self.assertEqual(out.last(7), 64)
        self.assertEqual(out.last(8), round(64 + 0.15 * 63))
        self.assertTrue(all(ch == 3 for ch, _, _ in out.ccs))
        press(eng, "RIGHT_STICK_CLICK_R3", "up")
        self.assertTrue(eng.mode)          # toggles on press only
        press(eng, "RIGHT_STICK_CLICK_R3")
        self.assertFalse(eng.mode)
        self.assertEqual(out.last(20), 0)

    def test_pauses_and_restores_stick_and_gyro_engines(self):
        eng, out, reg, stick, gyro = _setup()
        gyro.set_active(False)              # was already off before the mode
        press(eng, "RIGHT_STICK_CLICK_R3")
        self.assertFalse(stick.active)
        self.assertEqual(stick.released, 1)
        press(eng, "RIGHT_STICK_CLICK_R3")
        self.assertTrue(stick.active)
        self.assertFalse(gyro.active)       # restored to its prior state, not forced on

    def test_suppresses_preset_notes_only_in_mode(self):
        eng, out, reg, *_ = _setup()
        press(eng, "RIGHT_STICK_CLICK_R3")
        for note in (36, 37, 42, 43, 76, 77):
            self.assertFalse(reg.should_emit_note(0, note, 127, 0.0), note)
        self.assertTrue(reg.should_emit_note(0, 64, 127, 0.0))   # L2 flash untouched
        self.assertTrue(reg.should_emit_note(1, 36, 127, 0.0))
        press(eng, "RIGHT_STICK_CLICK_R3")
        self.assertTrue(reg.should_emit_note(0, 36, 127, 0.0))

    def test_chase_buttons_both_abxy_layers(self):
        eng, out, *_ = _setup()
        press(eng, "RIGHT_STICK_CLICK_R3")
        press(eng, "BTN_Y")
        self.assertEqual(out.last(2), 127)
        press(eng, "BTN_Y", "up")
        self.assertEqual(out.last(2), 0)
        press(eng, "BTN_B_LAYER_2")
        self.assertEqual(out.last(5), 127)

    def test_blackout_toggle_and_momentary(self):
        eng, out, *_ = _setup()
        press(eng, "RIGHT_STICK_CLICK_R3")
        press(eng, "R5"); press(eng, "R5", "up")
        self.assertEqual(out.last(1), 127)
        press(eng, "R5")
        self.assertEqual(out.last(1), 0)
        press(eng, "R4")
        self.assertEqual(out.last(1), 127)
        press(eng, "R4", "up")
        self.assertEqual(out.last(1), 0)

    def test_stick_is_centred(self):
        eng, out, *_ = _setup()
        press(eng, "RIGHT_STICK_CLICK_R3")
        eng.on_axis_event("L_STICK_X_AXIS", 32767, 0.0)
        self.assertEqual(out.last(6), 127)
        eng.on_axis_event("L_STICK_X_AXIS", -32767, 0.0)
        self.assertEqual(out.last(6), 1)
        eng.on_axis_event("L_STICK_Y_AXIS", 1000, 0.0)   # inside deadzone
        self.assertEqual(out.last(7), 64)

    def test_gyro_tilt_from_entry_pose(self):
        eng, out, *_ = _setup(spin_rest=0.0)
        eng.on_axis_event("GYRO_PITCH", 300, 0.0)          # pose before entering
        self.assertEqual(out.ccs, [])
        press(eng, "RIGHT_STICK_CLICK_R3")
        self.assertEqual(out.last(8), 64)
        eng.on_axis_event("GYRO_PITCH", 300 + 25 + 450, 0.0)
        self.assertEqual(out.last(8), 127)
        eng.on_axis_event("GYRO_PITCH", 300 - 25 - 225, 0.0)
        self.assertEqual(out.last(8), round(64 - 0.5 * 63))

    def test_deactivating_engine_exits_mode_cleanly(self):
        eng, out, reg, stick, gyro = _setup()
        press(eng, "RIGHT_STICK_CLICK_R3")
        press(eng, "BTN_X")
        reg.apply_engine_states({"tv_tree_mode": False})
        self.assertFalse(eng.mode)
        self.assertEqual(out.last(4), 0)
        self.assertTrue(stick.active)
        self.assertTrue(reg.should_emit_note(0, 40, 127, 0.0))

    def test_dedupes_repeated_values(self):
        eng, out, *_ = _setup()
        press(eng, "RIGHT_STICK_CLICK_R3")
        n = len(out.ccs)
        eng.on_axis_event("L_STICK_X_AXIS", 32767, 0.0)
        eng.on_axis_event("L_STICK_X_AXIS", 32767, 0.0)
        self.assertEqual(len(out.ccs), n + 1)


class RealGyroEngineTests(unittest.TestCase):
    """The real gyro_feedback engine is paused in the mode and works again after it."""

    def _setup(self):
        from windows.engines.gyro_feedback import GyroFeedbackEngine
        root = Path(__file__).resolve().parents[1] / "config" / "engines.factory"
        gcfg = json.loads((root / "gyro_feedback.json").read_text(encoding="utf-8"))
        tcfg = json.loads(FACTORY.read_text(encoding="utf-8"))
        tcfg["start_active"] = True
        out = RecordingMidiOut()
        gyro = GyroFeedbackEngine("Gyro", gcfg, out, clock=lambda: 0.0)
        tree = TvTreeModeEngine("Tree", tcfg, out, clock=lambda: 0.0)
        reg = EngineRegistry([gyro, tree])     # gyro first, as in the loaded registry
        tree.bind_registry(reg)
        return reg, gyro, tree, out, gcfg

    def _l4_tap(self, reg, gcfg, t):
        ch, cc = int(gcfg.get("l4_channel", 2)), int(gcfg.get("l4_cc", 74))
        # receiver order: input event to engines first, then the button's mapped CC
        reg.on_input_event("L4", "down", t); reg.on_midi_in(ch, cc, 127, t)
        reg.on_input_event("L4", "up", t + 0.05); reg.on_midi_in(ch, cc, 0, t + 0.05)

    def test_gyro_paused_in_mode_and_back_after_r3(self):
        reg, gyro, tree, out, gcfg = self._setup()
        reg.on_input_event("RIGHT_STICK_CLICK_R3", "down", 0.0)
        self.assertTrue(tree.mode)
        self.assertFalse(gyro.active)
        reg.on_input_event("RIGHT_STICK_CLICK_R3", "down", 1.0)
        self.assertFalse(tree.mode)
        self.assertTrue(gyro.active)
        self._l4_tap(reg, gcfg, 2.0)
        self.assertTrue(gyro.status()["midi_active"])

    def test_l4_in_mode_exits_and_counts_as_the_gyro_tap(self):
        reg, gyro, tree, out, gcfg = self._setup()
        reg.on_input_event("RIGHT_STICK_CLICK_R3", "down", 0.0)
        self._l4_tap(reg, gcfg, 1.0)
        self.assertFalse(tree.mode)
        self.assertTrue(gyro.active)
        self.assertTrue(gyro.status()["midi_active"])


if __name__ == "__main__":
    unittest.main()
