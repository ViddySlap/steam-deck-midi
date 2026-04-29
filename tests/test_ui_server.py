"""Tests for the mapping UI Flask server."""

from __future__ import annotations

import json
import threading
import unittest
from pathlib import Path
import tempfile
import os

from windows.ui_server import MappingUIServer, _detect_conflicts, INTENTIONAL_SAME_CHANNEL_CC


BASE_MAP = {
    "macro_settings": {"fade_duration_seconds": 2.0, "update_hz": 30},
    "mappings": {
        "BTN_A": {"type": "note", "channel": 0, "note": 36, "velocity": 127},
        "DPAD_UP": {"type": "macro_cc", "channel": 0, "cc": 22, "gesture": "click"},
        "DPAD_UP_LONG_PRESS": {"type": "macro_cc", "channel": 0, "cc": 22, "gesture": "long_press"},
        "R_PAD_LEFT": {"type": "relative_cc", "channel": 0, "cc": 47, "step_value": 127, "repeat_interval_ms": 40},
        "R_PAD_RIGHT": {"type": "relative_cc", "channel": 0, "cc": 47, "step_value": 1, "repeat_interval_ms": 40},
    },
}


def _make_server(base_map=None, local_map=None):
    tmpdir = tempfile.mkdtemp()
    base_path = Path(tmpdir) / "windows_midi_map.json"
    local_path = Path(tmpdir) / "windows_midi_map.local.json"
    actions_path = Path(tmpdir) / "actions.yaml"

    base_path.write_text(json.dumps(base_map or BASE_MAP), encoding="utf-8")
    if local_map is not None:
        local_path.write_text(json.dumps(local_map), encoding="utf-8")
    actions_path.write_text(
        "actions:\n  - BTN_A\n  - DPAD_UP\n  - DPAD_UP_LONG_PRESS\n",
        encoding="utf-8",
    )

    reload_event = threading.Event()
    server = MappingUIServer(
        base_map_path=base_path,
        local_map_path=local_path,
        actions_yaml_path=actions_path,
        reload_event=reload_event,
    )
    return server, reload_event, tmpdir, local_path


class DetectConflictsTests(unittest.TestCase):
    def test_no_conflict_returns_empty(self):
        mappings = {
            "BTN_A": {"type": "note", "channel": 0, "note": 36},
            "BTN_B": {"type": "note", "channel": 0, "note": 38},
        }
        self.assertEqual(_detect_conflicts(mappings), [])

    def test_intentional_conflict_not_flagged(self):
        # DPAD_UP and DPAD_UP_LONG_PRESS both on (0, 22) — intentional
        mappings = {
            "DPAD_UP": {"type": "macro_cc", "channel": 0, "cc": 22, "gesture": "click"},
            "DPAD_UP_LONG_PRESS": {"type": "macro_cc", "channel": 0, "cc": 22, "gesture": "long_press"},
        }
        self.assertEqual(_detect_conflicts(mappings), [])

    def test_unintentional_conflict_flagged(self):
        mappings = {
            "BTN_A": {"type": "cc", "channel": 0, "cc": 50},
            "BTN_B": {"type": "cc", "channel": 0, "cc": 50},
        }
        conflicts = _detect_conflicts(mappings)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["cc"], 50)
        self.assertEqual(set(conflicts[0]["actions"]), {"BTN_A", "BTN_B"})

    def test_relative_encoder_pair_not_flagged(self):
        # R_PAD_LEFT / R_PAD_RIGHT share CC 47 on channel 0 — intentional
        mappings = {
            "R_PAD_LEFT": {"type": "relative_cc", "channel": 0, "cc": 47, "step_value": 127},
            "R_PAD_RIGHT": {"type": "relative_cc", "channel": 0, "cc": 47, "step_value": 1},
        }
        self.assertEqual(_detect_conflicts(mappings), [])

    def test_different_channels_not_flagged(self):
        # CC 78 on channels 0, 1, 2 — intentional layer publisher pattern
        mappings = {
            "START": {"type": "cc", "channel": 2, "cc": 78},
            "LAMP_L1": {"type": "cc", "channel": 0, "cc": 78},
            "LAMP_L2": {"type": "cc", "channel": 1, "cc": 78},
        }
        # Different channels — not caught by same_channel_cc detector
        conflicts = _detect_conflicts(mappings)
        self.assertEqual(conflicts, [])


class MappingUIServerAPITests(unittest.TestCase):
    def setUp(self):
        self.server, self.reload_event, self.tmpdir, self.local_path = _make_server()
        self.client = self.server._app.test_client()

    def test_get_mappings_returns_base(self):
        resp = self.client.get("/api/mappings")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("mappings", data)
        self.assertIn("BTN_A", data["mappings"])

    def test_get_actions(self):
        resp = self.client.get("/api/actions")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("BTN_A", data["actions"])
        self.assertIn("DPAD_UP", data["actions"])

    def test_index_serves_html(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Steam Deck MIDI", resp.data)

    def test_save_valid_mapping_writes_local_file(self):
        new_mappings = {
            "BTN_A": {"type": "cc", "channel": 0, "cc": 10, "on_value": 127, "off_value": 0},
        }
        resp = self.client.post(
            "/api/save",
            json={"mappings": new_mappings},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["ok"])
        self.assertTrue(self.local_path.exists())
        saved = json.loads(self.local_path.read_text())
        self.assertEqual(saved["mappings"]["BTN_A"]["cc"], 10)

    def test_save_triggers_reload_event(self):
        self.reload_event.clear()
        self.client.post(
            "/api/save",
            json={"mappings": {"BTN_A": {"type": "note", "channel": 0, "note": 40, "velocity": 127}}},
        )
        self.assertTrue(self.reload_event.is_set())

    def test_save_invalid_mapping_returns_422(self):
        bad_mappings = {
            "BTN_A": {"type": "note", "channel": 0, "note": 999},  # note out of range
        }
        resp = self.client.post("/api/save", json={"mappings": bad_mappings})
        self.assertEqual(resp.status_code, 422)
        self.assertIn("error", resp.get_json())

    def test_save_non_json_returns_400(self):
        resp = self.client.post("/api/save", data="not json", content_type="text/plain")
        self.assertEqual(resp.status_code, 400)

    def test_check_conflicts_no_conflict(self):
        resp = self.client.post(
            "/api/conflicts",
            json={"mappings": {"BTN_A": {"type": "note", "channel": 0, "note": 36}}},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["conflicts"], [])

    def test_check_conflicts_flags_unintentional(self):
        resp = self.client.post(
            "/api/conflicts",
            json={
                "mappings": {
                    "ACT_1": {"type": "cc", "channel": 0, "cc": 99},
                    "ACT_2": {"type": "cc", "channel": 0, "cc": 99},
                }
            },
        )
        self.assertEqual(resp.status_code, 200)
        conflicts = resp.get_json()["conflicts"]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["cc"], 99)

    def test_reset_deletes_local_file(self):
        # Create a local file first
        self.local_path.write_text('{"mappings":{}}', encoding="utf-8")
        self.assertTrue(self.local_path.exists())
        resp = self.client.post("/api/reset", json={})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(self.local_path.exists())
        self.assertTrue(self.reload_event.is_set())

    def test_local_override_merges_with_base(self):
        server, _, tmpdir, local_path = _make_server(
            local_map={
                "mappings": {
                    "BTN_A": {"type": "cc", "channel": 1, "cc": 99, "on_value": 127, "off_value": 0},
                    "BTN_NEW": {"type": "note", "channel": 0, "note": 60, "velocity": 127},
                }
            }
        )
        client = server._app.test_client()
        resp = client.get("/api/mappings")
        data = resp.get_json()
        # BTN_A overridden
        self.assertEqual(data["mappings"]["BTN_A"]["cc"], 99)
        # BTN_NEW added
        self.assertIn("BTN_NEW", data["mappings"])
        # DPAD_UP still from base
        self.assertIn("DPAD_UP", data["mappings"])

    def test_save_with_macro_settings(self):
        payload = {
            "mappings": {"BTN_A": {"type": "note", "channel": 0, "note": 36, "velocity": 127}},
            "macro_settings": {"fade_duration_seconds": 3.0, "update_hz": 30},
        }
        resp = self.client.post("/api/save", json=payload)
        self.assertEqual(resp.status_code, 200)
        saved = json.loads(self.local_path.read_text())
        self.assertAlmostEqual(saved["macro_settings"]["fade_duration_seconds"], 3.0)

    def test_get_mappings_includes_macro_settings(self):
        resp = self.client.get("/api/mappings")
        data = resp.get_json()
        self.assertIn("macro_settings", data)


class MappingUIServerMergeTests(unittest.TestCase):
    """Test load_raw_json merging logic directly."""

    def _make(self, base, local_map=None):
        server, _, _, _ = _make_server(base_map=base, local_map=local_map)
        return server

    def test_no_local_returns_base(self):
        s = self._make(BASE_MAP)
        raw = s._load_raw_json()
        self.assertEqual(raw["mappings"]["BTN_A"]["type"], "note")

    def test_local_overrides_base_mapping(self):
        s = self._make(
            BASE_MAP,
            local_map={"mappings": {"BTN_A": {"type": "cc", "channel": 0, "cc": 5, "on_value": 100, "off_value": 0}}},
        )
        raw = s._load_raw_json()
        self.assertEqual(raw["mappings"]["BTN_A"]["cc"], 5)

    def test_local_adds_new_mapping(self):
        s = self._make(
            BASE_MAP,
            local_map={"mappings": {"NEW_ACTION": {"type": "note", "channel": 0, "note": 90, "velocity": 127}}},
        )
        raw = s._load_raw_json()
        self.assertIn("NEW_ACTION", raw["mappings"])
        self.assertIn("BTN_A", raw["mappings"])

    def test_macro_settings_merged(self):
        s = self._make(
            BASE_MAP,
            local_map={"macro_settings": {"fade_duration_seconds": 5.0}},
        )
        raw = s._load_raw_json()
        self.assertAlmostEqual(raw["macro_settings"]["fade_duration_seconds"], 5.0)
        # update_hz from base still present
        self.assertEqual(raw["macro_settings"]["update_hz"], 30)


if __name__ == "__main__":
    unittest.main()
