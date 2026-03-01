from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from deck.xinput_send import load_bindings, parse_xinput_line
from protocol.messages import encode_action_event, parse_action_event


class ParseXinputLineTests(unittest.TestCase):
    def test_parses_key_press(self) -> None:
        self.assertEqual(parse_xinput_line("key press   14"), ("14", "down"))

    def test_parses_key_release(self) -> None:
        self.assertEqual(parse_xinput_line("key release 14"), ("14", "up"))

    def test_ignores_other_lines(self) -> None:
        self.assertIsNone(parse_xinput_line("motion a[0]=1.00"))


class LoadBindingsTests(unittest.TestCase):
    def test_loads_profile_and_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bindings.json"
            path.write_text(
                json.dumps({"profile_name": "default", "bindings": {"14": "BTN_A"}}),
                encoding="utf-8",
            )
            profile_name, bindings = load_bindings(str(path))

        self.assertEqual(profile_name, "default")
        self.assertEqual(bindings, {"14": "BTN_A"})


class SharedProtocolEncodingTests(unittest.TestCase):
    def test_encoded_event_round_trips(self) -> None:
        payload = encode_action_event(action="BTN_A", state="down", seq=1)
        event = parse_action_event(payload)
        self.assertEqual(event.action, "BTN_A")
        self.assertEqual(event.state, "down")
        self.assertEqual(event.seq, 1)
