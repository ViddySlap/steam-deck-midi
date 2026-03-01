from __future__ import annotations

import unittest

from windows.config import NoteMapping
from windows.receiver import ActionReceiver


class FakeMidiOut:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int, int]] = []

    def note_on(self, channel: int, note: int, velocity: int) -> None:
        self.calls.append(("note_on", channel, note, velocity))

    def note_off(self, channel: int, note: int, velocity: int = 0) -> None:
        self.calls.append(("note_off", channel, note, velocity))

    def control_change(self, channel: int, control: int, value: int) -> None:
        self.calls.append(("cc", channel, control, value))

    def panic(self) -> None:
        self.calls.append(("panic", -1, -1, -1))

    def close(self) -> None:
        return None


class ActionReceiverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.midi = FakeMidiOut()
        self.receiver = ActionReceiver(
            self.midi,
            {"BTN_A": NoteMapping(action="BTN_A", kind="note", channel=0, note=60)},
            timeout_seconds=1.0,
        )
        self.addr = ("10.10.10.2", 45123)

    def test_emits_note_on_and_off(self) -> None:
        self.receiver.handle_datagram(
            b'{"action":"BTN_A","state":"down","seq":1}', self.addr, now=0.0
        )
        self.receiver.handle_datagram(
            b'{"action":"BTN_A","state":"up","seq":2}', self.addr, now=0.1
        )
        self.assertEqual(
            self.midi.calls,
            [("note_on", 0, 60, 127), ("note_off", 0, 60, 0)],
        )

    def test_ignores_out_of_order_packets(self) -> None:
        self.receiver.handle_datagram(
            b'{"action":"BTN_A","state":"down","seq":5}', self.addr, now=0.0
        )
        self.receiver.handle_datagram(
            b'{"action":"BTN_A","state":"up","seq":4}', self.addr, now=0.1
        )
        self.assertEqual(self.midi.calls, [("note_on", 0, 60, 127)])

    def test_releases_active_state_on_timeout(self) -> None:
        self.receiver.handle_datagram(
            b'{"action":"BTN_A","state":"down","seq":1}', self.addr, now=0.0
        )
        timed_out = self.receiver.check_timeouts(now=1.5)
        self.assertTrue(timed_out)
        self.assertEqual(
            self.midi.calls,
            [("note_on", 0, 60, 127), ("note_off", 0, 60, 0), ("panic", -1, -1, -1)],
        )
