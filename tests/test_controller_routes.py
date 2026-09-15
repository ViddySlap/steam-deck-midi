"""Controller API evidence uses real preset bytes in disposable config trees."""

import copy
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch

from windows.config import ConfigError, load_midi_map
from windows.ui_server import MappingUIServer, _member_span


ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "windows/static/controller/controller_map.json"
NOTE = {"type": "note", "channel": 0, "note": 36, "velocity": 127}
CC = {"type": "cc", "channel": 2, "cc": 99}
DOCUMENT = {
    "mappings": {"BTN_A": NOTE}, "macro_settings": {"update_hz": 30},
    "analog_settings": {"deadzone": 123}, "engines": {"osc_sync": False},
}


class ControllerRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.base = root / "windows_midi_map.json"
        self.presets = root / "presets"
        self.presets.mkdir()
        self.active = self.presets / "default.json"
        self.library = root / "macro_library.json"
        self.actions = root / "actions.yaml"
        shutil.copyfile(ROOT / "config/actions.yaml", self.actions)
        self.base.write_text(json.dumps(DOCUMENT), encoding="utf-8")
        self.event = threading.Event()
        self.server = MappingUIServer(self.base, self.presets, self.library, self.actions,
                                      self.event, preset_section="windows")
        self.client = self.server._app.test_client()
        self.seed()

    def seed(self, flat=False, shared=None):
        document = copy.deepcopy(DOCUMENT)
        raw = document if flat else {"shared": {"mappings": shared or {}}, "sections": {
            "windows": document, "macbook": {"mappings": {"BTN_A": {**NOTE, "note": 90}}},
        }}
        # Deliberately odd whitespace tests byte retention outside the section.
        self.active.write_text(json.dumps(raw, indent=3) + "\n", encoding="utf-8")
        self.event.clear()
        return raw

    def disk(self):
        return json.loads(self.active.read_text(encoding="utf-8"))

    def document(self):
        raw = self.disk()
        return raw["sections"]["windows"] if "sections" in raw else raw

    def version(self):
        return self.client.get("/api/state-version").get_json()

    def assert_refused(self, response, status, before, version):
        self.assertEqual(response.status_code, status, response.get_json())
        self.assertEqual(self.active.read_bytes(), before)
        self.assertFalse(self.event.is_set())
        self.assertEqual(self.version(), version)
        self.assertEqual(list(self.presets.glob(".preset-*.tmp")), [])

    def test_map_is_read_from_owned_file_and_read_routes_do_not_write(self):
        before = self.active.read_bytes()
        expected = json.loads(MAP_PATH.read_text(encoding="utf-8"))
        self.assertEqual(self.client.get("/api/controller-map").get_json(), expected)
        changed = copy.deepcopy(expected)
        changed["controls"][0]["notes"] = "Scratch file read proof"
        original = Path.read_text
        def read(path, *args, **kwargs):
            return json.dumps(changed) if path == MAP_PATH else original(path, *args, **kwargs)
        with patch.object(Path, "read_text", read):
            self.assertEqual(self.client.get("/api/controller-map").get_json(), changed)
            self.assertEqual(self.client.get("/api/controller-map/btn_a").get_json()["notes"],
                             changed["controls"][0]["notes"])
        self.assertEqual(self.active.read_bytes(), before)

    def test_drill_in_matches_every_group_and_current_section_mapping(self):
        raw = self.seed(shared={"BTN_A_LAYER_2": CC})
        before = self.active.read_bytes()
        owned_map = json.loads(MAP_PATH.read_text(encoding="utf-8"))
        for control in owned_map["controls"]:
            response = self.client.get("/api/controller-map/" + control["id"])
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertEqual(data["section"], "windows")
            for group, actions in control["groups"].items():
                self.assertEqual([row["action_id"] for row in data["groups"][group]], actions)
                for row in data["groups"][group]:
                    action = row["action_id"]
                    expected = raw["sections"]["windows"]["mappings"].get(action, raw["shared"]["mappings"].get(action))
                    self.assertEqual(row["mapping"], expected)
                    self.assertEqual(row["source"], "section" if action == "BTN_A" else
                                     "shared" if action == "BTN_A_LAYER_2" else None)
        other = self.client.get("/api/controller-map/btn_a?section=macbook").get_json()
        self.assertEqual(other["groups"]["tap"][0]["mapping"]["note"], 90)
        self.assertEqual(self.active.read_bytes(), before)

    def test_flat_drill_in_works_for_named_and_null_selection(self):
        self.seed(flat=True)
        before = self.active.read_bytes()
        self.server.bridge_settings.preset_section = None
        for query in ("", "?section=Any machine"):
            data = self.client.get("/api/controller-map/btn_a" + query).get_json()
            self.assertTrue(data["legacy"])
            self.assertEqual(data["groups"]["tap"][0], {"action_id": "BTN_A", "mapping": NOTE, "source": "flat"})
        self.assertEqual(self.active.read_bytes(), before)

    def test_put_all_mapping_types_flat_and_sectioned(self):
        specs = [NOTE, CC, {"type": "macro_cc", "cc": 66, "gesture": "long_press"},
                 {"type": "relative_cc", "cc": 68, "step_value": 127},
                 {"type": "staged_note_macro", "note": 40},
                 {"type": "axis_to_cc", "cc": 70, "input_range": [-32768, 32767], "output_range": [0, 127]},
                 {"type": "axis_split_cc", "cc_positive": 72, "cc_negative": 73}]
        for flat in (False, True):
            self.seed(flat=flat)
            for spec in specs:
                with self.subTest(flat=flat, kind=spec["type"]):
                    before_version = self.version()
                    response = self.client.put("/api/mappings/BTN_A", json=spec)
                    self.assertEqual(response.status_code, 200, response.get_json())
                    self.assertEqual(self.document()["mappings"]["BTN_A"], spec)
                    self.assertEqual(response.get_json()["mapping"], spec)
                    self.assertEqual(response.get_json()["effective_mapping"], spec)
                    self.assertEqual(self.version(), before_version + 1)
                    self.assertTrue(self.event.is_set())
                    self.assertEqual("sections" not in self.disk(), flat)
                    self.assertEqual(load_midi_map(self.active, "windows").mappings["BTN_A"].kind, spec["type"])

    def test_put_preserves_other_section_shared_bytes_and_settings(self):
        self.seed(shared={"BTN_B": NOTE})
        before = self.active.read_text(encoding="utf-8")
        sections, _ = _member_span(before, "sections")
        start, end = _member_span(before, "windows", sections)
        response = self.client.put("/api/mappings/BTN_A?section=windows", json=CC)
        self.assertEqual(response.status_code, 200)
        after = self.active.read_text(encoding="utf-8")
        sections2, _ = _member_span(after, "sections")
        start2, end2 = _member_span(after, "windows", sections2)
        self.assertEqual(before[:start], after[:start2])
        self.assertEqual(before[end:], after[end2:])
        for key in ("macro_settings", "analog_settings", "engines"):
            self.assertEqual(self.document()[key], DOCUMENT[key])
        self.assertEqual(self.document()["mappings"]["BTN_A"], CC)

    def test_explicit_remote_section_put_and_delete(self):
        original = copy.deepcopy(self.document())
        response = self.client.put("/api/mappings/BTN_A?section=macbook", json=CC)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.disk()["sections"]["macbook"]["mappings"]["BTN_A"], CC)
        self.assertEqual(self.document(), original)
        self.assertEqual(self.client.delete("/api/mappings/BTN_A?section=macbook").status_code, 200)
        self.assertEqual(self.disk()["sections"]["macbook"]["mappings"], {})
        self.assertEqual(self.document(), original)

    def test_bad_specs_return_parser_error_and_preserve_bytes_even_when_forced(self):
        for spec in (None, [], {}, {"type": "note", "note": 999},
                     {"type": "staged_note_macro", "note": 36, "modifier_channel": 0, "trigger_channel": 0},
                     {"type": "axis_split_cc", "cc_positive": 7, "cc_negative": 7}):
            for force in ("", "?force=1"):
                with self.subTest(spec=spec, force=force):
                    bad = self.base.parent / "bad.json"
                    bad.write_text(json.dumps({"mappings": {"BTN_A": spec}}), encoding="utf-8")
                    with self.assertRaises(ConfigError) as parser_error:
                        load_midi_map(bad)
                    before, version = self.active.read_bytes(), self.version()
                    response = self.client.put("/api/mappings/BTN_A" + force,
                                               data=json.dumps(spec), content_type="application/json")
                    self.assert_refused(response, 400, before, version)
                    self.assertEqual(response.get_json()["error"], str(parser_error.exception))

    def test_invalid_sibling_section_blocks_write_via_whole_file_validation(self):
        raw = self.disk()
        raw["sections"]["macbook"]["mappings"]["BTN_A"]["note"] = 999
        self.active.write_text(json.dumps(raw), encoding="utf-8")
        before, version = self.active.read_bytes(), self.version()
        self.assert_refused(self.client.put("/api/mappings/BTN_A", json=CC), 400, before, version)

    def test_conflict_409_and_force_200_include_shared_mappings(self):
        for flat in (False, True):
            raw = self.seed(flat=flat, shared={"BTN_B": CC})
            if flat:
                raw["mappings"]["BTN_B"] = CC
                self.active.write_text(json.dumps(raw), encoding="utf-8")
            before, version = self.active.read_bytes(), self.version()
            response = self.client.put("/api/mappings/BTN_A", json=CC)
            self.assert_refused(response, 409, before, version)
            conflict = response.get_json()["conflicts"][0]
            self.assertEqual((conflict["channel"], conflict["cc"]), (2, 99))
            self.assertEqual(set(conflict["actions"]), {"BTN_A", "BTN_B"})
            response = self.client.put("/api/mappings/BTN_A?force=1", json=CC)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.document()["mappings"]["BTN_A"], CC)

    def test_delete_twice_and_shared_fallback_flat_and_sectioned(self):
        for flat in (False, True):
            self.seed(flat=flat, shared={"BTN_A": CC})
            for _ in range(2):
                version = self.version()
                response = self.client.delete("/api/mappings/BTN_A")
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("BTN_A", self.document()["mappings"])
                self.assertIsNone(response.get_json()["mapping"])
                self.assertEqual(response.get_json()["effective_mapping"], None if flat else CC)
                self.assertEqual(self.version(), version + 1)

    def test_unchanged_inheritance_does_not_become_owned(self):
        self.seed(shared={"BTN_B": CC})
        response = self.client.put("/api/mappings/BTN_B", data=json.dumps(CC), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("BTN_B", self.document()["mappings"])
        self.assertEqual(response.get_json()["effective_mapping"], CC)
        self.assertEqual(self.disk()["shared"]["mappings"]["BTN_B"], CC)

    def test_inherited_spec_with_float_integer_field_still_runs_parser(self):
        self.seed(shared={"BTN_B": CC})
        before, version = self.active.read_bytes(), self.version()
        response = self.client.put("/api/mappings/BTN_B", json={**CC, "cc": 99.0})
        self.assert_refused(response, 400, before, version)
        self.assertEqual(response.get_json()["error"], "cc must be an integer")

    def test_delete_conflict_guard_and_force(self):
        self.seed(shared={"BTN_A": CC, "BTN_B": CC})
        before, version = self.active.read_bytes(), self.version()
        self.assert_refused(self.client.delete("/api/mappings/BTN_A"), 409, before, version)
        self.assertEqual(self.client.delete("/api/mappings/BTN_A?force=1").status_code, 200)
        self.assertNotIn("BTN_A", self.document()["mappings"])
        self.assertEqual(self.disk()["shared"]["mappings"]["BTN_A"], CC)

    def test_bad_ids_sections_and_json_leave_bytes_unchanged(self):
        cases = [("get", "/api/controller-map/missing", None, 404),
                 ("put", "/api/mappings/missing", NOTE, 404),
                 ("delete", "/api/mappings/missing", None, 404),
                 ("get", "/api/controller-map/btn_a?section=missing", None, 422),
                 ("put", "/api/mappings/BTN_A?section=missing", NOTE, 422),
                 ("delete", "/api/mappings/BTN_A?section=bad/name", None, 422),
                 ("post", "/api/macros/missing/apply", {"action_id": "BTN_A"}, 404),
                 ("post", "/api/macros/missing/apply", [], 400)]
        for method, url, body, status in cases:
            with self.subTest(url=url):
                before, version = self.active.read_bytes(), self.version()
                self.assert_refused(getattr(self.client, method)(url, json=body), status, before, version)
        before, version = self.active.read_bytes(), self.version()
        self.assert_refused(self.client.put("/api/mappings/BTN_A", data="{", content_type="application/json"), 400, before, version)

    def test_failed_atomic_replace_leaves_original_and_version(self):
        before, version = self.active.read_bytes(), self.version()
        with patch("windows.ui_server.os.replace", side_effect=OSError("disk unavailable")):
            self.assert_refused(self.client.put("/api/mappings/BTN_A", json=CC), 500, before, version)

    def test_version_keeps_receiver_reload_observations(self):
        external = [7]
        self.server.state_version_fn = lambda: external[0]
        self.assertEqual(self.version(), 7)
        self.assertEqual(self.client.put("/api/mappings/BTN_A", json=CC).status_code, 200)
        self.assertEqual(self.document()["mappings"]["BTN_A"], CC)
        self.assertEqual(self.version(), 8)
        external[0] += 1
        self.assertEqual(self.version(), 9)
        self.assertEqual(self.client.get("/api/state-version").headers["Cache-Control"], "no-store")

    def macro(self, macro, action="BTN_A", **kwargs):
        self.library.write_text(json.dumps([{**macro, "id": "example", "name": "Example"}]), encoding="utf-8")
        return self.client.post("/api/macros/example/apply" + kwargs.pop("query", ""),
                                json={"action_id": action, **kwargs})

    def test_macro_cc_and_staged_merge_preserve_targets_remove_optional_overrides(self):
        for flat in (False, True):
            self.seed(flat=flat)
            cases = [
                ({"type": "macro_cc", "channel": 3, "cc": 42, "gesture": "click", "fade_duration_seconds": 8},
                 {"type": "macro_cc", "gesture": "long_press"},
                 {"type": "macro_cc", "channel": 3, "cc": 42, "gesture": "long_press"}),
                ({"type": "staged_note_macro", "note": 88, "velocity": 77, "modifier_channel": 0,
                  "trigger_channel": 1, "refresh_actions": ["BTN_B"], "macro_delay_ms": 300, "modifier_hold_ms": 400},
                 {"type": "staged_note_macro", "modifier_channel": 2, "trigger_channel": 3, "refresh_actions": ["BTN_X"]},
                 {"type": "staged_note_macro", "note": 88, "velocity": 77, "modifier_channel": 2,
                  "trigger_channel": 3, "refresh_actions": ["BTN_X"]}),
            ]
            for current, macro, expected in cases:
                self.assertEqual(self.client.put("/api/mappings/BTN_A", json=current).status_code, 200)
                response = self.macro(macro)
                self.assertEqual(response.status_code, 200, response.get_json())
                self.assertEqual(response.get_json()["mapping"], expected)
                self.assertEqual(self.document()["mappings"]["BTN_A"], expected)

    def test_macro_defaults_and_relative_merge(self):
        cases = [({"type": "macro_cc", "gesture": "long_press", "fade_duration_seconds": 3},
                  {"type": "macro_cc", "channel": 0, "cc": 22, "gesture": "long_press", "fade_duration_seconds": 3}),
                 ({"type": "relative_cc", "step_value": 127, "repeat_interval_ms": 55},
                  {"type": "relative_cc", "channel": 0, "cc": 47, "step_value": 127, "repeat_interval_ms": 55}),
                 ({"type": "staged_note_macro", "modifier_channel": 4, "trigger_channel": 5,
                   "macro_delay_ms": 30, "modifier_hold_ms": 50},
                  {"type": "staged_note_macro", "note": 36, "velocity": 127, "modifier_channel": 4,
                   "trigger_channel": 5, "refresh_actions": [], "macro_delay_ms": 30, "modifier_hold_ms": 50})]
        for macro, expected in cases:
            self.seed()
            response = self.macro(macro, action="BTN_B")
            self.assertEqual(response.status_code, 200, response.get_json())
            self.assertEqual(self.document()["mappings"]["BTN_B"], expected)
        self.client.put("/api/mappings/BTN_A", json={"type": "relative_cc", "channel": 8, "cc": 81, "step_value": 1})
        response = self.macro({"type": "relative_cc", "step_value": 127, "repeat_interval_ms": 77})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.document()["mappings"]["BTN_A"],
                         {"type": "relative_cc", "channel": 8, "cc": 81, "step_value": 127, "repeat_interval_ms": 77})

    def test_macro_incompatible_unknown_action_invalid_section_and_parser_error(self):
        macro = {"type": "macro_cc", "gesture": "click"}
        for action, section, status in [("BTN_A", "windows", 409), ("missing", "windows", 404), ("BTN_B", "missing", 422)]:
            before, version = self.active.read_bytes(), self.version()
            self.assert_refused(self.macro(macro, action=action, section=section), status, before, version)
        # Library validation accepts channels >15; application must still parse.
        before, version = self.active.read_bytes(), self.version()
        invalid = {"type": "staged_note_macro", "modifier_channel": 99, "trigger_channel": 1}
        self.assert_refused(self.macro(invalid, action="BTN_B"), 400, before, version)

    def test_macro_shared_compatibility_remote_section_and_conflicts(self):
        self.seed(shared={"BTN_B": {"type": "macro_cc", "channel": 3, "cc": 42, "gesture": "click"}})
        macro = {"type": "macro_cc", "gesture": "long_press"}
        response = self.macro(macro, action="BTN_B", section="macbook")
        self.assertEqual(response.status_code, 200)
        expected = {"type": "macro_cc", "channel": 3, "cc": 42, "gesture": "long_press"}
        self.assertEqual(self.disk()["sections"]["macbook"]["mappings"]["BTN_B"], expected)
        self.assertNotIn("BTN_B", self.document()["mappings"])
        self.seed(shared={"BTN_B": {**CC, "channel": 0, "cc": 47}})
        macro = {"type": "relative_cc", "step_value": 1, "repeat_interval_ms": 40}
        # Use a non-allowlisted channel/CC on two existing relative mappings.
        raw = self.disk()
        raw["sections"]["windows"]["mappings"]["BTN_A"] = {**CC, "type": "relative_cc", "step_value": 1}
        raw["shared"]["mappings"]["BTN_B"] = CC
        self.active.write_text(json.dumps(raw), encoding="utf-8")
        before, version = self.active.read_bytes(), self.version()
        self.assert_refused(self.macro(macro), 409, before, version)
        response = self.macro(macro, query="?force=1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.document()["mappings"]["BTN_A"],
                         {**CC, "type": "relative_cc", "step_value": 1, "repeat_interval_ms": 40})


if __name__ == "__main__":
    unittest.main()
