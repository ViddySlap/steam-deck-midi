from __future__ import annotations

import unittest

from protocol.messages import (
    ActionEvent,
    HeartbeatEvent,
    ProtocolError,
    encode_action_event,
    encode_heartbeat_event,
    parse_action_event,
)


class ParseActionEventTests(unittest.TestCase):
    def test_parses_valid_event(self) -> None:
        event = parse_action_event(
            b'{"kind":"action","action":"BTN_A","state":"down","seq":7}'
        )
        self.assertIsInstance(event, ActionEvent)
        self.assertEqual(event.kind, "action")
        self.assertEqual(event.action, "BTN_A")
        self.assertEqual(event.state, "down")
        self.assertEqual(event.seq, 7)

    def test_parses_legacy_action_event_without_kind(self) -> None:
        event = parse_action_event(b'{"action":"BTN_A","state":"down","seq":7}')
        self.assertIsInstance(event, ActionEvent)
        self.assertEqual(event.kind, "action")

    def test_parses_heartbeat_event(self) -> None:
        event = parse_action_event(b'{"kind":"heartbeat","seq":8}')
        self.assertIsInstance(event, HeartbeatEvent)
        self.assertEqual(event.kind, "heartbeat")
        self.assertEqual(event.seq, 8)

    def test_encodes_action_event_with_kind(self) -> None:
        event = parse_action_event(encode_action_event(action="BTN_A", state="down", seq=9))
        self.assertIsInstance(event, ActionEvent)
        self.assertEqual(event.kind, "action")

    def test_encodes_heartbeat_event(self) -> None:
        event = parse_action_event(encode_heartbeat_event(seq=10))
        self.assertIsInstance(event, HeartbeatEvent)
        self.assertEqual(event.kind, "heartbeat")
        self.assertEqual(event.seq, 10)

    def test_rejects_invalid_state(self) -> None:
        with self.assertRaises(ProtocolError):
            parse_action_event(b'{"action":"BTN_A","state":"held","seq":1}')

    def test_rejects_non_json(self) -> None:
        with self.assertRaises(ProtocolError):
            parse_action_event(b"not-json")
