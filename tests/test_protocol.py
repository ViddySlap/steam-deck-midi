from __future__ import annotations

import unittest

from protocol.messages import (
    ActionEvent,
    AxisEvent,
    HeartbeatEvent,
    ProtocolError,
    encode_action_event,
    encode_axis_event,
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


class ParseAxisEventTests(unittest.TestCase):
    def test_encode_axis_event_round_trips(self) -> None:
        event = parse_action_event(
            encode_axis_event(action="L_STICK_X_AXIS", value=-12345, seq=42)
        )
        self.assertIsInstance(event, AxisEvent)
        self.assertEqual(event.kind, "axis")
        self.assertEqual(event.action, "L_STICK_X_AXIS")
        self.assertEqual(event.value, -12345)
        self.assertEqual(event.seq, 42)

    def test_parses_axis_event_from_raw_bytes(self) -> None:
        event = parse_action_event(
            b'{"kind":"axis","action":"L_TRIGGER_PRESSURE","value":5000,"seq":1}'
        )
        self.assertIsInstance(event, AxisEvent)
        self.assertEqual(event.value, 5000)

    def test_axis_event_positive_value_round_trips(self) -> None:
        event = parse_action_event(
            encode_axis_event(action="R_STICK_Y_AXIS", value=32767, seq=10)
        )
        self.assertIsInstance(event, AxisEvent)
        self.assertEqual(event.value, 32767)

    def test_rejects_axis_event_with_non_integer_value(self) -> None:
        with self.assertRaises(ProtocolError):
            parse_action_event(
                b'{"kind":"axis","action":"L_STICK_X_AXIS","value":"bad","seq":1}'
            )

    def test_rejects_axis_event_with_missing_action(self) -> None:
        with self.assertRaises(ProtocolError):
            parse_action_event(b'{"kind":"axis","value":100,"seq":1}')

    def test_rejects_axis_event_with_float_value(self) -> None:
        with self.assertRaises(ProtocolError):
            parse_action_event(
                b'{"kind":"axis","action":"L_STICK_X_AXIS","value":1.5,"seq":1}'
            )
