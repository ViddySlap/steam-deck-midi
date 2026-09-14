from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from windows.config import (
    AnalogSettings,
    AxisToCCMapping,
    ConfigError,
    ControlChangeMapping,
    MacroCCMapping,
    NoteMapping,
    RelativeCCMapping,
    StagedNoteMacroMapping,
    load_midi_map,
)


class PresetSectionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "map.json"
        self.windows = {"mappings": {"BTN_A": {"type": "note", "channel": 0, "note": 36}}}
        self.macbook = {"mappings": {"BTN_A": {"type": "cc", "channel": 1, "cc": 72}},
                        "macro_settings": {"update_hz": 15},
                        "analog_settings": {"deadzone": 123}}
        self.doc = {"sections": {"windows": self.windows, "macbook": self.macbook}}

    def load(self, doc, section=None):
        self.path.write_text(json.dumps(doc), encoding="utf-8")
        return load_midi_map(self.path, section=section)

    def test_legacy_applies_with_none_or_any_section(self):
        expected = self.load(self.windows)
        for section in ("macbook", "grandma", "any/name"):
            with self.subTest(section=section):
                self.assertEqual(self.load(self.windows, section), expected)

    def test_named_sections_select_all_settings(self):
        cfg = self.load(self.doc, "macbook")
        self.assertEqual(cfg.mappings["BTN_A"].cc, 72)
        self.assertEqual(cfg.mappings["BTN_A"].channel, 1)
        self.assertEqual(cfg.macro_settings.update_hz, 15)
        self.assertEqual(cfg.analog_settings.deadzone, 123)
        self.assertEqual(self.load(self.doc, "windows").mappings["BTN_A"].note, 36)

    def test_missing_selection_names_available_sections(self):
        for section in (None, "missing"):
            with self.subTest(section=section), self.assertRaises(ConfigError) as caught:
                self.load(self.doc, section)
            self.assertIn("windows", str(caught.exception))
            self.assertIn("macbook", str(caught.exception))
            if section:
                self.assertIn(section, str(caught.exception))

    def test_arbitrary_safe_names_are_allowed(self):
        self.assertEqual(self.load({"sections": {"Grandma 2_-": self.windows}},
                                   "Grandma 2_-").mappings["BTN_A"].note, 36)

    def test_bad_names_and_shapes_raise_config_error(self):
        for doc in ([], {"sections": []}, {"sections": {}},
                    {"sections": {"": self.windows, "macbook": self.macbook}},
                    {"sections": {"bad/name": self.windows, "macbook": self.macbook}},
                    {"sections": {"bad\n": self.windows, "macbook": self.macbook}},
                    {"sections": {"macbook": []}},
                    {"sections": {"macbook": {"mappings": []}}},
                    {**self.doc, "shared": []},
                    {**self.doc, "shared": {"mappings": []}}):
            with self.subTest(doc=doc), self.assertRaises(ConfigError):
                self.load(doc, "macbook")

    def test_shared_mappings_apply_everywhere_with_whole_action_override(self):
        self.doc["shared"] = {"mappings": {
            "BTN_A": {"type": "note", "channel": 3, "note": 99},
            "BTN_B": {"type": "note", "channel": 0, "note": 40},
        }}
        for section in ("macbook", "windows"):
            cfg = self.load(self.doc, section)
            self.assertEqual(cfg.mappings["BTN_B"].note, 40)
        self.assertEqual(self.load(self.doc, "macbook").mappings["BTN_A"].cc, 72)
        self.assertEqual(self.load(self.doc, "windows").mappings["BTN_A"].note, 36)

    def test_section_engines_stay_lenient(self):
        for engines, expected in ((None, {}), ([], {}), ("bad", {}),
                                  ({"osc_sync": False, "audio_opacity": "yes", "": True},
                                   {"osc_sync": False})):
            with self.subTest(engines=engines):
                self.macbook["engines"] = engines
                self.assertEqual(self.load(self.doc, "macbook").engine_states, expected)

    def test_section_validation_stays_strict_for_other_settings(self):
        for key, value in (("macro_settings", []), ("analog_settings", []),
                           ("mappings", {"BTN_A": {"type": "note", "note": 999}})):
            with self.subTest(key=key), self.assertRaises(ConfigError):
                self.load({"sections": {"macbook": {**self.macbook, key: value}}}, "macbook")


class LoadMidiMapTests(unittest.TestCase):
    def test_loads_note_and_cc_mappings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "map.json"
            path.write_text(
                json.dumps(
                    {
                        "macro_settings": {"fade_duration_seconds": 1.5, "update_hz": 20},
                        "mappings": {
                            "BTN_A": {"type": "note", "channel": 0, "note": 60},
                            "DPAD_UP": {"type": "cc", "channel": 1, "cc": 10},
                            "DPAD_UP_LONG_PRESS": {
                                "type": "macro_cc",
                                "channel": 1,
                                "cc": 11,
                                "gesture": "long_press",
                            },
                            "R_PAD_RIGHT": {
                                "type": "relative_cc",
                                "channel": 1,
                                "cc": 47,
                                "step_value": 1,
                                "repeat_interval_ms": 40,
                            },
                            "L_PAD_LEFT_LONG_PRESS": {
                                "type": "staged_note_macro",
                                "note": 86,
                                "velocity": 120,
                                "modifier_channel": 1,
                                "trigger_channel": 2,
                                "refresh_actions": ["L_PAD_LEFT", "L_PAD_RIGHT"],
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            config = load_midi_map(path)

        self.assertEqual(config.macro_settings.fade_duration_seconds, 1.5)
        self.assertEqual(config.macro_settings.update_hz, 20)
        self.assertEqual(config.macro_settings.macro_delay_ms, 80)
        self.assertEqual(config.macro_settings.modifier_hold_ms, 2000)
        self.assertEqual(config.macro_settings.layer_refresh_ms, 500)
        self.assertIsInstance(config.mappings["BTN_A"], NoteMapping)
        self.assertIsInstance(config.mappings["DPAD_UP"], ControlChangeMapping)
        self.assertIsInstance(config.mappings["DPAD_UP_LONG_PRESS"], MacroCCMapping)
        self.assertIsInstance(config.mappings["R_PAD_RIGHT"], RelativeCCMapping)
        self.assertIsInstance(config.mappings["L_PAD_LEFT_LONG_PRESS"], StagedNoteMacroMapping)
        self.assertEqual(
            config.mappings["L_PAD_LEFT_LONG_PRESS"].refresh_actions,
            ("L_PAD_LEFT", "L_PAD_RIGHT"),
        )

    def test_rejects_missing_mappings_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "map.json"
            path.write_text(json.dumps({"bad": {}}), encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_midi_map(path)

    def test_loads_default_analog_settings_when_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "map.json"
            path.write_text(json.dumps({"mappings": {}}), encoding="utf-8")
            config = load_midi_map(path)
        self.assertEqual(config.analog_settings.update_hz, 60.0)
        self.assertEqual(config.analog_settings.deadzone, 1000)
        self.assertEqual(config.analog_settings.curve, "linear")

    def test_loads_axis_to_cc_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "map.json"
            path.write_text(
                json.dumps(
                    {
                        "analog_settings": {"update_hz": 30.0, "deadzone": 500},
                        "mappings": {
                            "L_STICK_X_AXIS": {
                                "type": "axis_to_cc",
                                "channel": 0,
                                "cc": 100,
                                "input_range": [-32767, 32767],
                                "output_range": [0, 127],
                                "deadzone": 2000,
                                "curve": "linear",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            config = load_midi_map(path)
        self.assertEqual(config.analog_settings.update_hz, 30.0)
        self.assertEqual(config.analog_settings.deadzone, 500)
        mapping = config.mappings["L_STICK_X_AXIS"]
        self.assertIsInstance(mapping, AxisToCCMapping)
        self.assertEqual(mapping.cc, 100)
        self.assertEqual(mapping.input_range, (-32767, 32767))
        self.assertEqual(mapping.output_range, (0, 127))
        self.assertEqual(mapping.deadzone, 2000)
        self.assertEqual(mapping.curve, "linear")

    def test_axis_to_cc_defaults_deadzone_and_curve(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "map.json"
            path.write_text(
                json.dumps(
                    {
                        "mappings": {
                            "R_TRIGGER_PRESSURE": {
                                "type": "axis_to_cc",
                                "channel": 0,
                                "cc": 20,
                                "input_range": [0, 32767],
                                "output_range": [0, 127],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            config = load_midi_map(path)
        mapping = config.mappings["R_TRIGGER_PRESSURE"]
        self.assertIsInstance(mapping, AxisToCCMapping)
        self.assertEqual(mapping.deadzone, 1000)
        self.assertEqual(mapping.curve, "linear")

    def test_rejects_axis_to_cc_with_inverted_input_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "map.json"
            path.write_text(
                json.dumps(
                    {
                        "mappings": {
                            "L_STICK_X_AXIS": {
                                "type": "axis_to_cc",
                                "channel": 0,
                                "cc": 100,
                                "input_range": [32767, -32767],
                                "output_range": [0, 127],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ConfigError):
                load_midi_map(path)

    def test_rejects_axis_to_cc_with_output_range_exceeding_midi_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "map.json"
            path.write_text(
                json.dumps(
                    {
                        "mappings": {
                            "L_STICK_X_AXIS": {
                                "type": "axis_to_cc",
                                "channel": 0,
                                "cc": 100,
                                "input_range": [-32767, 32767],
                                "output_range": [0, 200],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ConfigError):
                load_midi_map(path)

    def test_rejects_invalid_macro_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "map.json"
            path.write_text(
                json.dumps(
                    {
                        "macro_settings": {"min_value": 127, "max_value": 0},
                        "mappings": {"BTN_A": {"type": "note", "channel": 0, "note": 60}},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ConfigError):
                load_midi_map(path)
