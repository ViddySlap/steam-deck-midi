"""The controller relation must cover the shared action catalog exactly once."""

from collections import Counter
import json
import math
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "windows/static/controller/controller_map.json"
ACTIONS_PATH = ROOT / "config/actions.yaml"


class ControllerMapTests(unittest.TestCase):
    def setUp(self):
        self.map = json.loads(MAP_PATH.read_text(encoding="utf-8"))
        self.controls = self.map["controls"]

    def test_every_catalog_action_appears_exactly_once(self):
        expected = re.findall(r"^\s+-\s+(\w+)\s*$", ACTIONS_PATH.read_text(encoding="utf-8"), re.MULTILINE)
        actual = [action for c in self.controls for group in c["groups"].values() for action in group]
        self.assertTrue(expected)
        self.assertTrue(actual)
        self.assertEqual(Counter(actual), Counter(expected))
        self.assertTrue(all(count == 1 for count in Counter(actual).values()))

    def test_control_schema_and_anchors(self):
        self.assertEqual(self.map["schema_version"], 1)
        self.assertEqual(len(self.controls), 24)
        for key in ("id", "label"):
            self.assertEqual(len({c[key] for c in self.controls}), len(self.controls))
        kinds = {"button", "dpad", "stick", "trigger", "bumper", "back_button", "menu", "trackpad", "gyro"}
        for control in self.controls:
            with self.subTest(control=control["id"]):
                self.assertRegex(control["id"], r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
                self.assertTrue(control["label"].strip())
                self.assertIn(control["kind"], kinds)
                self.assertTrue(control["groups"])
                self.assertLessEqual(set(control["groups"]), {"tap", "long_press", "layer_2", "touch", "analog"})
                for group in control["groups"].values():
                    self.assertIsInstance(group, list)
                    self.assertTrue(group)
                    self.assertTrue(all(isinstance(action, str) for action in group))
                self.assertEqual(set(control["anchor"]), {"x", "y"})
                for value in control["anchor"].values():
                    self.assertIn(type(value), (int, float))
                    self.assertTrue(math.isfinite(value))
                if control["kind"] in {"stick", "trigger", "trackpad", "gyro", "back_button"}:
                    self.assertTrue(control["notes"].strip())
        self.assertTrue(MAP_PATH.read_text(encoding="utf-8").isascii())

    def test_groups_follow_action_names(self):
        for control in self.controls:
            for group, actions in control["groups"].items():
                for action in actions:
                    expected = "tap"
                    if action.endswith("_LAYER_2"):
                        expected = "layer_2"
                    elif action.endswith("_TOUCH"):
                        expected = "touch"
                    elif action.endswith("_LONG_PRESS"):
                        expected = "long_press"
                    elif re.search(r"_(AXIS|PRESSURE|POS|PITCH|YAW|ROLL)$", action):
                        expected = "analog"
                    self.assertEqual(group, expected, action)

    def test_live_ranges_cover_exactly_the_analog_actions(self):
        analog = {a for c in self.controls for a in c["groups"].get("analog", [])}
        self.assertTrue(analog)
        self.assertEqual(set(self.map["axis_ranges"]), analog)
        for action, bounds in self.map["axis_ranges"].items():
            with self.subTest(action=action):
                self.assertEqual(set(bounds), {"min", "max", "rest"})
                self.assertTrue(all(type(v) is int for v in bounds.values()))
                self.assertLessEqual(bounds["min"], bounds["rest"])
                self.assertLess(bounds["rest"], bounds["max"])
                self.assertEqual(bounds["rest"], 0)


if __name__ == "__main__":
    unittest.main()
