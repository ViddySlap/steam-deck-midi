from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from windows.config import ConfigError, ControlChangeMapping, NoteMapping, load_midi_map


class LoadMidiMapTests(unittest.TestCase):
    def test_loads_note_and_cc_mappings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "map.json"
            path.write_text(
                json.dumps(
                    {
                        "mappings": {
                            "BTN_A": {"type": "note", "channel": 0, "note": 60},
                            "DPAD_UP": {"type": "cc", "channel": 1, "cc": 10},
                        }
                    }
                ),
                encoding="utf-8",
            )
            mappings = load_midi_map(path)

        self.assertIsInstance(mappings["BTN_A"], NoteMapping)
        self.assertIsInstance(mappings["DPAD_UP"], ControlChangeMapping)

    def test_rejects_missing_mappings_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "map.json"
            path.write_text(json.dumps({"bad": {}}), encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_midi_map(path)
