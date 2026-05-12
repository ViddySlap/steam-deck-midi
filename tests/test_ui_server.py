"""Tests for the mapping UI Flask server."""

from __future__ import annotations

import json
import threading
import unittest
from pathlib import Path
import tempfile

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


def _make_server(base_map=None):
    tmpdir = tempfile.mkdtemp()
    base_path = Path(tmpdir) / "windows_midi_map.json"
    presets_dir = Path(tmpdir) / "presets"
    macro_library_path = Path(tmpdir) / "macro_library.json"
    actions_path = Path(tmpdir) / "actions.yaml"

    content = json.dumps(base_map or BASE_MAP)
    base_path.write_text(content, encoding="utf-8")
    presets_dir.mkdir()
    (presets_dir / "default.json").write_text(content, encoding="utf-8")
    (presets_dir / ".active").write_text("default.json", encoding="utf-8")
    actions_path.write_text(
        "actions:\n  - BTN_A\n  - DPAD_UP\n  - DPAD_UP_LONG_PRESS\n",
        encoding="utf-8",
    )

    reload_event = threading.Event()
    server = MappingUIServer(
        base_map_path=base_path,
        presets_dir=presets_dir,
        macro_library_path=macro_library_path,
        actions_yaml_path=actions_path,
        reload_event=reload_event,
    )
    active_preset_path = presets_dir / "default.json"
    return server, reload_event, tmpdir, active_preset_path, presets_dir, macro_library_path


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
        self.assertEqual(_detect_conflicts(mappings), [])


class MappingUIServerAPITests(unittest.TestCase):
    def setUp(self):
        (self.server, self.reload_event, self.tmpdir,
         self.active_preset_path, self.presets_dir,
         self.macro_library_path) = _make_server()
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

    def test_save_writes_active_preset(self):
        new_mappings = {
            "BTN_A": {"type": "cc", "channel": 0, "cc": 10, "on_value": 127, "off_value": 0},
        }
        resp = self.client.post("/api/save", json={"mappings": new_mappings})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["ok"])
        saved = json.loads(self.active_preset_path.read_text())
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

    def test_reset_restores_factory_defaults(self):
        # Write custom content to active preset
        custom = {"mappings": {"BTN_A": {"type": "cc", "channel": 0, "cc": 99, "on_value": 127, "off_value": 0}}}
        self.active_preset_path.write_text(json.dumps(custom), encoding="utf-8")

        self.reload_event.clear()
        resp = self.client.post("/api/reset", json={})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(self.reload_event.is_set())

        # Active preset should now match the factory base map
        restored = json.loads(self.active_preset_path.read_text())
        self.assertEqual(
            restored["mappings"]["BTN_A"]["type"], "note",
            "factory reset should restore BTN_A to note type"
        )

    def test_save_with_macro_settings(self):
        payload = {
            "mappings": {"BTN_A": {"type": "note", "channel": 0, "note": 36, "velocity": 127}},
            "macro_settings": {"fade_duration_seconds": 3.0, "update_hz": 30},
        }
        resp = self.client.post("/api/save", json=payload)
        self.assertEqual(resp.status_code, 200)
        saved = json.loads(self.active_preset_path.read_text())
        self.assertAlmostEqual(saved["macro_settings"]["fade_duration_seconds"], 3.0)

    def test_get_mappings_includes_macro_settings(self):
        resp = self.client.get("/api/mappings")
        data = resp.get_json()
        self.assertIn("macro_settings", data)

    def test_load_preset_switches_active(self):
        other_map = {"mappings": {"BTN_A": {"type": "cc", "channel": 0, "cc": 77, "on_value": 127, "off_value": 0}}}
        other_preset = self.presets_dir / "other.json"
        other_preset.write_text(json.dumps(other_map), encoding="utf-8")

        resp = self.client.post("/api/presets/load", json={"name": "other.json"})
        self.assertEqual(resp.status_code, 200)

        resp = self.client.get("/api/mappings")
        data = resp.get_json()
        self.assertEqual(data["mappings"]["BTN_A"]["cc"], 77)


class MappingUIServerPresetTests(unittest.TestCase):
    def setUp(self):
        (self.server, self.reload_event, self.tmpdir,
         self.active_preset_path, self.presets_dir,
         self.macro_library_path) = _make_server()
        self.client = self.server._app.test_client()

    def test_get_presets_returns_list(self):
        resp = self.client.get("/api/presets")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("presets", data)
        presets = data["presets"]
        self.assertTrue(any(p["name"] == "default.json" for p in presets))
        default = next(p for p in presets if p["name"] == "default.json")
        self.assertEqual(default["display_name"], "default")
        self.assertTrue(default["active"])

    def test_load_missing_preset_returns_404(self):
        resp = self.client.post("/api/presets/load", json={"name": "nonexistent.json"})
        self.assertEqual(resp.status_code, 404)

    def test_save_as_creates_new_preset(self):
        resp = self.client.post("/api/presets/save-as", json={"name": "My Custom Preset"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["active"], "My Custom Preset.json")
        self.assertTrue((self.presets_dir / "My Custom Preset.json").exists())

    def test_save_as_invalid_name_returns_400(self):
        resp = self.client.post("/api/presets/save-as", json={"name": "bad/name!"})
        self.assertEqual(resp.status_code, 400)

    def test_save_as_appears_in_preset_list(self):
        self.client.post("/api/presets/save-as", json={"name": "Second"})
        resp = self.client.get("/api/presets")
        names = [p["name"] for p in resp.get_json()["presets"]]
        self.assertIn("Second.json", names)

    def test_rename_default_returns_400(self):
        resp = self.client.post("/api/presets/rename", json={"old_name": "default.json", "new_name": "Renamed"})
        self.assertEqual(resp.status_code, 400)

    def test_rename_preset(self):
        (self.presets_dir / "toRename.json").write_text("{}", encoding="utf-8")
        resp = self.client.post("/api/presets/rename", json={"old_name": "toRename.json", "new_name": "Renamed"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue((self.presets_dir / "Renamed.json").exists())
        self.assertFalse((self.presets_dir / "toRename.json").exists())

    def test_delete_default_returns_400(self):
        resp = self.client.post("/api/presets/delete", json={"name": "default.json"})
        self.assertEqual(resp.status_code, 400)

    def test_delete_preset(self):
        (self.presets_dir / "temp.json").write_text("{}", encoding="utf-8")
        resp = self.client.post("/api/presets/delete", json={"name": "temp.json"})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse((self.presets_dir / "temp.json").exists())

    def test_delete_active_preset_switches_to_default(self):
        # Create and activate a non-default preset
        (self.presets_dir / "active_one.json").write_text(
            json.dumps(BASE_MAP), encoding="utf-8"
        )
        self.client.post("/api/presets/load", json={"name": "active_one.json"})
        self.reload_event.clear()

        resp = self.client.post("/api/presets/delete", json={"name": "active_one.json"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(self.reload_event.is_set())

        # Active should fall back to default
        active_name = (self.presets_dir / ".active").read_text(encoding="utf-8").strip()
        self.assertEqual(active_name, "default.json")


class MappingUIServerMacroTests(unittest.TestCase):
    def setUp(self):
        (self.server, self.reload_event, self.tmpdir,
         self.active_preset_path, self.presets_dir,
         self.macro_library_path) = _make_server()
        self.client = self.server._app.test_client()

    def test_get_macros_empty(self):
        resp = self.client.get("/api/macros")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("macros", data)
        self.assertEqual(data["macros"], [])

    def test_create_macro_cc(self):
        payload = {"name": "My Toggle", "type": "macro_cc", "gesture": "click", "fade_duration_seconds": None}
        resp = self.client.post("/api/macros", json=payload)
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertIn("id", data["macro"])
        self.assertEqual(data["macro"]["name"], "My Toggle")

    def test_create_macro_persists_to_file(self):
        payload = {"name": "Encoder Plus", "type": "relative_cc", "step_value": 1, "repeat_interval_ms": 40}
        self.client.post("/api/macros", json=payload)
        entries = json.loads(self.macro_library_path.read_text())
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["name"], "Encoder Plus")

    def test_create_macro_invalid_gesture_returns_400(self):
        payload = {"name": "Bad", "type": "macro_cc", "gesture": "invalid"}
        resp = self.client.post("/api/macros", json=payload)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    def test_create_macro_missing_name_returns_400(self):
        payload = {"type": "macro_cc", "gesture": "click"}
        resp = self.client.post("/api/macros", json=payload)
        self.assertEqual(resp.status_code, 400)

    def test_update_macro(self):
        create_resp = self.client.post(
            "/api/macros",
            json={"name": "Original", "type": "relative_cc", "step_value": 1, "repeat_interval_ms": 40},
        )
        macro_id = create_resp.get_json()["macro"]["id"]

        update_resp = self.client.put(
            f"/api/macros/{macro_id}",
            json={"name": "Updated", "type": "relative_cc", "step_value": 5, "repeat_interval_ms": 60},
        )
        self.assertEqual(update_resp.status_code, 200)
        self.assertEqual(update_resp.get_json()["macro"]["name"], "Updated")
        self.assertEqual(update_resp.get_json()["macro"]["step_value"], 5)

    def test_update_macro_not_found_returns_404(self):
        resp = self.client.put(
            "/api/macros/nonexistent",
            json={"name": "X", "type": "macro_cc", "gesture": "click"},
        )
        self.assertEqual(resp.status_code, 404)

    def test_delete_macro(self):
        create_resp = self.client.post(
            "/api/macros",
            json={"name": "ToDelete", "type": "macro_cc", "gesture": "long_press"},
        )
        macro_id = create_resp.get_json()["macro"]["id"]

        del_resp = self.client.delete(f"/api/macros/{macro_id}")
        self.assertEqual(del_resp.status_code, 200)

        entries = json.loads(self.macro_library_path.read_text())
        self.assertFalse(any(e["id"] == macro_id for e in entries))

    def test_delete_macro_not_found_returns_404(self):
        resp = self.client.delete("/api/macros/nonexistent")
        self.assertEqual(resp.status_code, 404)

    def test_create_staged_note_macro(self):
        payload = {
            "name": "Staged",
            "type": "staged_note_macro",
            "modifier_channel": 0,
            "trigger_channel": 1,
            "refresh_actions": [],
            "macro_delay_ms": None,
            "modifier_hold_ms": None,
        }
        resp = self.client.post("/api/macros", json=payload)
        self.assertEqual(resp.status_code, 201)

    def test_create_staged_note_macro_same_channel_returns_400(self):
        payload = {
            "name": "Bad Staged",
            "type": "staged_note_macro",
            "modifier_channel": 0,
            "trigger_channel": 0,
            "refresh_actions": [],
        }
        resp = self.client.post("/api/macros", json=payload)
        self.assertEqual(resp.status_code, 400)


class MappingUIServerLoadRawTests(unittest.TestCase):
    """Verify _load_raw_json reads the active preset directly."""

    def test_reads_active_preset(self):
        server, _, _, active_path, presets_dir, _ = _make_server()
        raw = server._load_raw_json()
        self.assertEqual(raw["mappings"]["BTN_A"]["type"], "note")

    def test_load_raw_json_after_preset_switch(self):
        server, _, _, _, presets_dir, _ = _make_server()
        other_map = {"mappings": {"BTN_B": {"type": "cc", "channel": 0, "cc": 42, "on_value": 127, "off_value": 0}}}
        (presets_dir / "other.json").write_text(json.dumps(other_map), encoding="utf-8")
        (presets_dir / ".active").write_text("other.json", encoding="utf-8")
        raw = server._load_raw_json()
        self.assertIn("BTN_B", raw["mappings"])
        self.assertNotIn("BTN_A", raw["mappings"])


class _StubEngine:
    """Minimal Engine stub for /api/engines/refresh endpoint tests."""

    def __init__(self, name: str, *, raise_on_refresh: bool = False) -> None:
        self.name = name
        self.type_name = name
        self.refresh_calls = 0
        self._raise_on_refresh = raise_on_refresh

    def refresh(self) -> None:
        self.refresh_calls += 1
        if self._raise_on_refresh:
            raise RuntimeError("simulated refresh failure")

    def status(self) -> dict:
        return {"name": self.name, "type": self.type_name}


class MappingUIServerEnginesRefreshTests(unittest.TestCase):
    """Verify POST /api/engines/refresh fans out to each engine.

    Replaces the periodic REST polling that was choking Arena's MIDI
    dispatch (2026-05-11 EVENING REST elimination, Tier 1).
    """

    def _make_server_with_engines(self, engines):
        from windows.engines.registry import EngineRegistry
        server, _, _, _, _, _ = _make_server()
        server.engine_registry = EngineRegistry(engines)
        return server

    def test_refresh_calls_each_engine(self):
        e1 = _StubEngine("alpha")
        e2 = _StubEngine("beta")
        server = self._make_server_with_engines([e1, e2])
        client = server._app.test_client()
        resp = client.post("/api/engines/refresh")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["results"], {"alpha": "ok", "beta": "ok"})
        self.assertEqual(e1.refresh_calls, 1)
        self.assertEqual(e2.refresh_calls, 1)

    def test_refresh_isolates_engine_failures(self):
        good = _StubEngine("good")
        bad = _StubEngine("bad", raise_on_refresh=True)
        server = self._make_server_with_engines([good, bad])
        client = server._app.test_client()
        resp = client.post("/api/engines/refresh")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["results"]["good"], "ok")
        self.assertIn("error", body["results"]["bad"])
        # Good engine still ran.
        self.assertEqual(good.refresh_calls, 1)

    def test_refresh_without_registry_returns_404(self):
        server, _, _, _, _, _ = _make_server()
        self.assertIsNone(server.engine_registry)
        client = server._app.test_client()
        resp = client.post("/api/engines/refresh")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
