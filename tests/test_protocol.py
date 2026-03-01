from __future__ import annotations

import unittest

from protocol.messages import ProtocolError, parse_action_event


class ParseActionEventTests(unittest.TestCase):
    def test_parses_valid_event(self) -> None:
        event = parse_action_event(b'{"action":"BTN_A","state":"down","seq":7}')
        self.assertEqual(event.action, "BTN_A")
        self.assertEqual(event.state, "down")
        self.assertEqual(event.seq, 7)

    def test_rejects_invalid_state(self) -> None:
        with self.assertRaises(ProtocolError):
            parse_action_event(b'{"action":"BTN_A","state":"held","seq":1}')

    def test_rejects_non_json(self) -> None:
        with self.assertRaises(ProtocolError):
            parse_action_event(b"not-json")
