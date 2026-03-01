from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from deck.learn_wizard import (
    find_duplicate_action,
    load_actions,
    parse_key_press,
    write_bindings,
)


class LoadActionsTests(unittest.TestCase):
    def test_loads_simple_action_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "actions.yaml"
            path.write_text("actions:\n  - BTN_A\n  - BTN_B\n", encoding="utf-8")
            actions = load_actions(str(path))
        self.assertEqual(actions, ["BTN_A", "BTN_B"])


class ParseKeyPressTests(unittest.TestCase):
    def test_parses_press(self) -> None:
        parsed = parse_key_press("key press   14")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.token, "14")

    def test_ignores_release(self) -> None:
        self.assertIsNone(parse_key_press("key release 14"))


class DuplicateDetectionTests(unittest.TestCase):
    def test_finds_existing_assignment(self) -> None:
        action = find_duplicate_action({"BTN_A": "14"}, "14")
        self.assertEqual(action, "BTN_A")


class WriteBindingsTests(unittest.TestCase):
    def test_writes_token_to_action_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "deck_bindings.json"
            write_bindings(str(path), "default", {"BTN_A": "14", "BTN_B": "15"})
            written = path.read_text(encoding="utf-8")

        self.assertIn('"14": "BTN_A"', written)
        self.assertIn('"15": "BTN_B"', written)
