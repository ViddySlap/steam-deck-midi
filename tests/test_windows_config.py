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
