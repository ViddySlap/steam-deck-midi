from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from deck.learn_wizard import (
    find_duplicate_action,
    is_skip_input,
    load_actions,
    load_existing_bindings,
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

    def test_preserves_action_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "actions.yaml"
            path.write_text(
                "actions:\n  - L4\n  - L5\n  - R4\n  - R5\n", encoding="utf-8"
            )
            actions = load_actions(str(path))
        self.assertEqual(actions, ["L4", "L5", "R4", "R5"])


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


class SkipInputTests(unittest.TestCase):
    def test_detects_escape(self) -> None:
        self.assertTrue(is_skip_input(b"\x1b"))

    def test_ignores_escape_prefixed_sequence(self) -> None:
        self.assertFalse(is_skip_input(b"\x1bOP"))

    def test_ignores_letter_s(self) -> None:
        self.assertFalse(is_skip_input(b"s"))

    def test_ignores_enter(self) -> None:
        self.assertFalse(is_skip_input(b"\n"))


class LoadExistingBindingsTests(unittest.TestCase):
    def test_loads_action_to_token_map_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "deck_bindings.json"
            path.write_text(
                json.dumps(
                    {"profile_name": "default", "bindings": {"14": "BTN_A", "15": "BTN_B"}}
                ),
                encoding="utf-8",
            )
            bindings = load_existing_bindings(str(path))
        self.assertEqual(bindings, {"BTN_A": "14", "BTN_B": "15"})

    def test_returns_empty_dict_for_missing_file(self) -> None:
        bindings = load_existing_bindings("/nonexistent/path/deck_bindings.json")
        self.assertEqual(bindings, {})

    def test_returns_empty_dict_for_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "deck_bindings.json"
            path.write_text("not json", encoding="utf-8")
            bindings = load_existing_bindings(str(path))
        self.assertEqual(bindings, {})

    def test_returns_empty_dict_when_bindings_key_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "deck_bindings.json"
            path.write_text(json.dumps({"profile_name": "default"}), encoding="utf-8")
            bindings = load_existing_bindings(str(path))
        self.assertEqual(bindings, {})


class WriteBindingsTests(unittest.TestCase):
    def test_writes_token_to_action_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "deck_bindings.json"
            write_bindings(str(path), "default", {"BTN_A": "14", "BTN_B": "15"})
            written = path.read_text(encoding="utf-8")

        self.assertIn('"14": "BTN_A"', written)
        self.assertIn('"15": "BTN_B"', written)

    def test_omits_skipped_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "deck_bindings.json"
            write_bindings(str(path), "default", {"BTN_A": "14"})
            written = path.read_text(encoding="utf-8")

        self.assertIn('"14": "BTN_A"', written)
        self.assertNotIn("BTN_B", written)
