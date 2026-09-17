"""ActionReceiver end to end with raw button state from the Deck (ADR 0003)."""

from __future__ import annotations

import unittest

from protocol.messages import encode_button_state_event
from tests.test_receiver import FakeMidiOut
from windows.config import ControlChangeMapping, MacroCCMapping, MacroSettings, NoteMapping
from windows.raw_buttons import BUTTON_BITS
from windows.receiver import ActionReceiver


def cc(action: str, channel: int, number: int) -> ControlChangeMapping:
    return ControlChangeMapping(
        action=action, kind="cc", channel=channel, cc=number, on_value=127, off_value=0
    )


def note(action: str, number: int) -> NoteMapping:
    return NoteMapping(action=action, kind="note", channel=0, note=number)


def macro(action: str, number: int, gesture: str) -> MacroCCMapping:
    return MacroCCMapping(action=action, kind="macro_cc", channel=0, cc=number, gesture=gesture)


MAPPINGS = {
    "START": cc("START", 2, 78),
    "SELECT": cc("SELECT", 2, 79),
    "BTN_A": note("BTN_A", 36),
    "BTN_A_LAYER_2": note("BTN_A_LAYER_2", 37),
    "L1": note("L1", 60),
    "L1_LAYER_2": note("L1_LAYER_2", 61),
    "L5": note("L5", 75),
    "DPAD_LEFT": macro("DPAD_LEFT", 23, "click"),
    "DPAD_LEFT_LONG_PRESS": macro("DPAD_LEFT_LONG_PRESS", 23, "long_press"),
}


class RawButtonReceiverTests(unittest.TestCase):
    addr = ("10.10.10.5", 50000)

    def setUp(self) -> None:
        self.midi = FakeMidiOut()
        self.receiver = ActionReceiver(
            self.midi, dict(MAPPINGS), timeout_seconds=5.0, macro_settings=MacroSettings()
        )
        self.seq = 0
        self.midi.calls.clear()  # startup lamp publishing is covered elsewhere

    def send(self, *held: str, t: int, now: float, lp: int = 0, lx: int = 0) -> None:
        buttons = bytearray(8)
        for name in held:
            offset, mask = BUTTON_BITS[name]
            buttons[offset - 8] |= mask
        self.seq += 1
        payload = encode_button_state_event(
            seq=self.seq,
            deck_ms=t,
            buttons=bytes(buttons),
            left_pad_pressure=lp,
            right_pad_pressure=0,
            left_pad_x=lx,
            left_pad_y=0,
            right_pad_x=0,
            right_pad_y=0,
            left_trigger=0,
            right_trigger=0,
        )
        self.receiver.handle_datagram(payload, self.addr, now=now)

    def test_first_state_publishes_both_layers_off(self) -> None:
        self.send(t=0, now=0.0)
        self.assertEqual(
            self.midi.calls,
            [("cc", 0, 78, 127), ("cc", 1, 78, 0), ("cc", 0, 79, 127), ("cc", 1, 79, 0)],
        )

    def test_button_press_and_release(self) -> None:
        self.send(t=0, now=0.0)
        self.midi.calls.clear()
        self.send("A", t=10, now=0.01)
        self.send(t=90, now=0.09)
        self.assertEqual(self.midi.calls, [("note_on", 0, 36, 127), ("note_off", 0, 36, 0)])

    def test_right_menu_button_switches_abxy_layer_and_lamp(self) -> None:
        self.send(t=0, now=0.0)
        self.midi.calls.clear()
        self.send("MENU", t=10, now=0.01)
        self.send(t=100, now=0.1)
        self.send("A", t=200, now=0.2)
        self.assertEqual(
            self.midi.calls,
            [
                ("cc", 0, 78, 0),
                ("cc", 1, 78, 127),
                ("cc", 2, 78, 127),
                ("cc", 2, 78, 0),
                ("note_on", 0, 37, 127),
            ],
        )

    def test_left_menu_button_switches_bumper_layer(self) -> None:
        self.send("VIEW", t=0, now=0.0)
        self.send(t=100, now=0.1)
        self.midi.calls.clear()
        self.send("L1", t=200, now=0.2)
        self.assertEqual(self.midi.calls, [("note_on", 0, 61, 127)])

    def test_dpad_tap_is_one_click_toggle(self) -> None:
        self.send(t=0, now=0.0)
        self.midi.calls.clear()
        self.send("DPAD_LEFT", t=10, now=0.01)
        self.assertEqual(self.midi.calls, [])
        self.send(t=120, now=0.12)
        self.assertEqual(self.midi.calls, [("cc", 0, 23, 127)])

    def test_dpad_note_tap_is_a_real_press(self) -> None:
        self.receiver._mappings["DPAD_DOWN"] = note("DPAD_DOWN", 98)
        self.receiver._mappings["DPAD_DOWN_LONG_PRESS"] = note("DPAD_DOWN_LONG_PRESS", 99)
        self.send(t=0, now=0.0)
        self.midi.calls.clear()
        self.send("DPAD_DOWN", t=10, now=0.01)
        self.send(t=110, now=0.11)
        self.assertEqual(self.midi.calls, [("note_on", 0, 98, 127)])
        self.receiver.check_timeouts(now=0.2)
        self.assertEqual(self.midi.calls, [("note_on", 0, 98, 127), ("note_off", 0, 98, 0)])

    def test_dpad_hold_starts_fade_instead_of_click(self) -> None:
        self.send(t=0, now=0.0)
        self.midi.calls.clear()
        self.send("DPAD_LEFT", t=10, now=0.01)
        self.send("DPAD_LEFT", t=510, now=0.51)
        self.send(t=900, now=0.9)
        self.assertNotIn(("cc", 0, 23, 127), self.midi.calls[:1])
        self.assertIn((0, 23), self.receiver._active_macro_fades)

    def test_silence_releases_held_note(self) -> None:
        self.send("L5", t=0, now=0.0)
        self.midi.calls.clear()
        self.receiver.check_timeouts(now=0.4)
        self.assertEqual(self.midi.calls, [])
        self.receiver.check_timeouts(now=0.6)
        self.assertEqual(self.midi.calls, [("note_off", 0, 75, 0)])

    def test_left_pad_click_by_pressure(self) -> None:
        mappings = dict(MAPPINGS, L_PAD_RIGHT=note("L_PAD_RIGHT", 83))
        receiver = ActionReceiver(FakeMidiOut(), mappings, timeout_seconds=5.0)
        self.receiver = receiver
        self.midi = receiver._midi_out
        self.send(t=0, now=0.0, lp=1400, lx=9000)
        self.midi.calls.clear()
        self.send(t=20, now=0.02, lp=4000, lx=9000)
        self.send(t=90, now=0.09, lp=0, lx=9000)
        self.assertEqual(self.midi.calls, [("note_on", 0, 83, 127), ("note_off", 0, 83, 0)])


if __name__ == "__main__":
    unittest.main()
