"""Tests for the mapping UI Flask server."""

from __future__ import annotations

import json
import threading
import unittest
from pathlib import Path
import tempfile

from unittest.mock import patch

from windows import ui_server as ui_server_module
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


def _make_server(base_map=None, section=None):
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
        preset_section=section,
    )
    active_preset_path = presets_dir / "default.json"
    return server, reload_event, tmpdir, active_preset_path, presets_dir, macro_library_path


class BridgeSettingsApiTests(unittest.TestCase):
    def setUp(self):
        import shutil
        self.doc = {"sections": {
            "macbook": BASE_MAP,
            "windows": {"mappings": {"BTN_A": {"type": "note", "channel": 0, "note": 80}}},
        }}
        (self.server, self.reload_event, self.tmpdir, self.active_path,
         self.presets_dir, _) = _make_server(self.doc, section="macbook")
        self.addCleanup(shutil.rmtree, self.tmpdir)
        self.client = self.server._app.test_client()
        self.settings_path = Path(self.tmpdir) / "bridge.local.json"

    def test_get_settings_reports_runtime_values_and_active_map(self):
        response = self.client.get("/api/settings")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "preset_section": "macbook", "listen": "0.0.0.0:45123",
            "midi_port": "DECK_IN", "feedback_port": None, "pulse_port": "PULSE_OUT",
            "ui_port": 7723, "map_path": str(self.active_path.resolve()),
        })
        other = self.presets_dir / "other.json"
        other.write_text(json.dumps(self.doc))
        (self.presets_dir / ".active").write_text("other.json")
        self.assertEqual(self.client.get("/api/settings").get_json()["map_path"], str(other.resolve()))

    def test_put_round_trip_persists_and_requests_reload(self):
        before = self.active_path.read_bytes()
        response = self.client.put("/api/settings", json={"preset_section": "windows"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["preset_section"], "windows")
        self.assertEqual(self.client.get("/api/settings").get_json(), response.get_json())
        self.assertEqual(json.loads(self.settings_path.read_text()), {"preset_section": "windows"})
        self.assertTrue(self.reload_event.is_set())
        self.assertEqual(self.active_path.read_bytes(), before)

    def test_put_rejects_invalid_body_without_writing_or_reload(self):
        for body in ([], {}, {"midi_port": "other"}, {"preset_section": 1},
                     {"preset_section": "bad/name"}, {"preset_section": "bad\n"},
                     {"preset_section": "windows", "ui_port": 9999}):
            with self.subTest(body=body):
                response = self.client.put("/api/settings", json=body)
                self.assertEqual(response.status_code, 400)
                self.assertFalse(self.settings_path.exists())
                self.assertFalse(self.reload_event.is_set())
                self.assertEqual(self.client.get("/api/settings").get_json()["preset_section"], "macbook")

    def test_absent_section_refused_with_available_names_and_no_side_effects(self):
        for section in (None, "missing"):
            with self.subTest(section=section):
                response = self.client.put("/api/settings", json={"preset_section": section})
                self.assertEqual(response.status_code, 422)
                self.assertIn("macbook", response.get_json()["error"])
                self.assertIn("windows", response.get_json()["error"])
                self.assertFalse(self.settings_path.exists())
                self.assertFalse(self.reload_event.is_set())

    def test_legacy_preset_allows_any_safe_section_and_null(self):
        self.active_path.write_text(json.dumps(BASE_MAP))
        for section in ("Grandma 2_-", None):
            with self.subTest(section=section):
                response = self.client.put("/api/settings", json={"preset_section": section})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json()["preset_section"], section)
                self.assertEqual(json.loads(self.settings_path.read_text()), {"preset_section": section})

    def test_failed_persistence_keeps_running_selection(self):
        from unittest.mock import patch
        with patch("os.replace", side_effect=OSError("read-only disk")):
            response = self.client.put("/api/settings", json={"preset_section": "windows"})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.client.get("/api/settings").get_json()["preset_section"], "macbook")
        self.assertFalse(self.reload_event.is_set())
        self.assertFalse(self.settings_path.exists())

    def test_api_inventory_matches_registered_method_paths(self):
        import re
        documented = set(re.findall(r"\| (GET|POST|PUT|DELETE) \| `([^`]+)` \|",
                                    (Path(__file__).resolve().parents[1] / "docs/api.md").read_text().split("## Deck sender\n", 1)[0]))
        registered = {(method, rule.rule) for rule in self.server._app.url_map.iter_rules()
                      for method in rule.methods if method not in {"OPTIONS", "HEAD"}}
        self.assertEqual(documented, registered)


class VersionApiTests(unittest.TestCase):
    def setUp(self):
        import shutil
        self.server, _, tmpdir, *_ = _make_server()
        self.addCleanup(shutil.rmtree, tmpdir)
        self.client = self.server._app.test_client()

    def _patched_fingerprint(self):
        from unittest.mock import patch
        from windows import build_fingerprint
        return patch.multiple(build_fingerprint, APP_VERSION="9.8.7", GIT_COMMIT="f00dfacef00dface",
                              GIT_COMMIT_SHORT="f00dface", BUILD_TIME_UTC="2031-01-02T03:04:05Z")

    def test_version_route_reports_the_fingerprint_and_unfrozen_source(self):
        import sys
        self.assertFalse(getattr(sys, "frozen", False), "the suite never runs frozen")
        with self._patched_fingerprint():
            response = self.client.get("/api/version")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"version": "9.8.7", "git_commit": "f00dfacef00dface",
                                               "build_time_utc": "2031-01-02T03:04:05Z", "frozen": False})

    def test_version_route_reports_frozen_true_in_a_packaged_exe(self):
        import sys
        from unittest.mock import patch
        with self._patched_fingerprint(), patch.object(sys, "frozen", True, create=True):
            body = self.client.get("/api/version").get_json()
        self.assertIs(body["frozen"], True)
        self.assertEqual(body["version"], "9.8.7")

    def test_version_route_serves_the_checked_in_fingerprint(self):
        from windows import build_fingerprint
        body = self.client.get("/api/version").get_json()
        self.assertEqual(body, {"version": build_fingerprint.APP_VERSION, "git_commit": build_fingerprint.GIT_COMMIT,
                                "build_time_utc": build_fingerprint.BUILD_TIME_UTC, "frozen": False})

    def test_version_route_is_get_only(self):
        rules = [r for r in self.server._app.url_map.iter_rules() if r.rule == "/api/version"]
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].methods - {"OPTIONS", "HEAD"}, {"GET"})
        self.assertEqual(self.client.post("/api/version").status_code, 405)


def _version_pair(root):
    """Read VERSION and the fingerprint module's APP_VERSION from files on disk."""
    import ast
    version = (Path(root) / "VERSION").read_text(encoding="utf-8").strip()
    tree = ast.parse((Path(root) / "windows/build_fingerprint.py").read_text(encoding="utf-8"))
    names = {node.targets[0].id: node.value.value for node in tree.body
             if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)}
    return version, names


class VersionAgreementTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def test_version_file_and_fingerprint_agree(self):
        version, names = _version_pair(self.ROOT)
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        self.assertEqual(names.get("APP_VERSION"), version)

    def test_agreement_detector_fires_on_a_diverged_copy(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "windows").mkdir()
            shutil.copyfile(self.ROOT / "windows/build_fingerprint.py", Path(tmp) / "windows/build_fingerprint.py")
            (Path(tmp) / "VERSION").write_text("0.4.9\n", encoding="utf-8")
            version, names = _version_pair(tmp)
            self.assertEqual(version, "0.4.9")
            self.assertNotEqual(names.get("APP_VERSION"), version)

    def test_build_exe_v2_regenerates_every_fingerprint_name_from_version_and_git(self):
        import re
        script = (self.ROOT / "scripts/windows/build_exe_v2.ps1").read_text(encoding="utf-8").replace("\r\n", "\n")
        self.assertIn('$versionPath = Join-Path $RepoRoot "VERSION"', script)
        self.assertIn("$appVersion = (Get-Content $versionPath -Raw).Trim()", script)
        self.assertIn("git -C $RepoRoot rev-parse HEAD", script)
        self.assertIn('$fingerprintModulePath = Join-Path $RepoRoot "windows\\build_fingerprint.py"', script)
        template = re.search(r'\$fingerprintModule = @"\n(.*?)\n"@', script, re.S)
        self.assertIsNotNone(template)
        written = dict(re.findall(r'^([A-Z_]+) = "(\$\w+)"$', template.group(1), re.M))
        self.assertEqual(written, {"APP_VERSION": "$appVersion", "GIT_COMMIT": "$gitCommit",
                                   "GIT_COMMIT_SHORT": "$gitCommitShort", "BUILD_TIME_UTC": "$buildTimestampUtc"})
        _, names = _version_pair(self.ROOT)
        self.assertEqual(set(names), set(written))
        self.assertIn("Set-Content -Path $fingerprintModulePath -Value $fingerprintModule", script)


class BridgeShutdownApiTests(unittest.TestCase):
    def setUp(self):
        import shutil
        from unittest.mock import Mock
        self.server, _, tmpdir, *_ = _make_server()
        self.addCleanup(shutil.rmtree, tmpdir)
        self.stop_event = threading.Event()
        self.shutdown = Mock(side_effect=self.stop_event.set)
        self.server.shutdown_fn = self.shutdown
        self.client = self.server._app.test_client()

    def test_shutdown_route_is_registered_for_post_only(self):
        rules = [r for r in self.server._app.url_map.iter_rules()
                 if r.rule == "/api/shutdown"]
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].methods - {"OPTIONS"}, {"POST"})
        self.assertEqual(self.client.get("/api/shutdown").status_code, 405)
        self.assertFalse(self.stop_event.is_set())

    def test_shutdown_sets_stop_event_and_returns_202(self):
        response = self.client.post("/api/shutdown")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.get_json(), {"stopping": True})
        self.assertTrue(self.stop_event.is_set())

    def test_shutdown_is_idempotent(self):
        for _ in range(2):
            response = self.client.post("/api/shutdown")
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.get_json(), {"stopping": True})
        self.assertTrue(self.stop_event.is_set())
        self.shutdown.assert_called_once_with()

    def test_shutdown_refuses_non_loopback_even_with_forwarded_header(self):
        for remote in ("192.168.1.7", "203.0.113.1", "::", "", "invalid"):
            with self.subTest(remote=remote):
                response = self.client.post(
                    "/api/shutdown", environ_base={"REMOTE_ADDR": remote},
                    headers={"X-Forwarded-For": "127.0.0.1"},
                )
                self.assertEqual(response.status_code, 403)
                self.assertIn("loopback", response.get_json()["error"])
                self.assertFalse(self.stop_event.is_set())
        self.shutdown.assert_not_called()

    def test_unwired_ui_refuses_shutdown(self):
        self.server.shutdown_fn = None
        response = self.client.post("/api/shutdown")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(self.stop_event.is_set())

    def test_non_loopback_is_still_refused_while_stopping(self):
        self.assertEqual(self.client.post("/api/shutdown").status_code, 202)
        response = self.client.post("/api/shutdown", environ_base={"REMOTE_ADDR": "10.0.0.1"})
        self.assertEqual(response.status_code, 403)
        self.shutdown.assert_called_once_with()

    def test_shutdown_accepts_ipv6_loopback(self):
        response = self.client.post("/api/shutdown", environ_base={"REMOTE_ADDR": "::1"})
        self.assertEqual(response.status_code, 202)
        self.assertTrue(self.stop_event.is_set())


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


class LiveAxisRangeTests(unittest.TestCase):
    """The controller view must be told the ranges actually in force.

    Hardware full-scale is not what the bridge maps from: a trigger's
    input_range floor is a deadzone and the gyro engine uses a far narrower
    raw band. Serving the static hardware numbers made a full-travel control
    look like it barely moved.
    """

    RANGES = {
        "R_TRIGGER_PRESSURE": {"min": 0, "max": 32767, "rest": 0},
        "L_STICK_X_AXIS": {"min": -32768, "max": 32767, "rest": 0},
        "GYRO_PITCH": {"min": -32767, "max": 32767, "rest": 0},
        "GYRO_YAW": {"min": -32767, "max": 32767, "rest": 0},
    }

    def _server(self, mappings, engine_registry=None):
        base = {"macro_settings": {"fade_duration_seconds": 2.0, "update_hz": 30},
                "mappings": mappings}
        server, *_ = _make_server(base_map=base)
        server.engine_registry = engine_registry
        return server

    def test_mapping_input_range_becomes_range_and_deadzone(self):
        server = self._server({
            "R_TRIGGER_PRESSURE": {"type": "axis_to_cc", "cc": 2, "channel": 0,
                                   "deadzone": 5500, "input_range": [5500, 32767],
                                   "output_range": [0, 127]},
        })
        ranges = server._live_axis_ranges(self.RANGES)
        self.assertEqual(ranges["R_TRIGGER_PRESSURE"]["max"], 32767)
        self.assertEqual(ranges["R_TRIGGER_PRESSURE"]["deadzone"], 5500)
        # An unmapped axis keeps its hardware bounds and gains no deadzone.
        self.assertEqual(ranges["L_STICK_X_AXIS"]["max"], 32767)
        self.assertNotIn("deadzone", ranges["L_STICK_X_AXIS"])

    def test_gyro_bounds_come_from_the_live_engine_including_per_axis_override(self):
        class _Registry:
            user_dir = "unused"

        spec = {"axes": {"pitch": "GYRO_PITCH", "yaw": "GYRO_YAW"},
                "raw_min": -750, "raw_max": 750, "deadzone": 100,
                "axis_raw": {"pitch": {"raw_min": -550, "raw_max": 550}}}
        server = self._server({}, engine_registry=_Registry())
        with patch.object(ui_server_module.engine_config_api, "get_engine_config",
                          return_value=(200, {"spec": spec})):
            ranges = server._live_axis_ranges(self.RANGES)
        self.assertEqual((ranges["GYRO_PITCH"]["min"], ranges["GYRO_PITCH"]["max"]), (-550.0, 550.0))
        self.assertEqual((ranges["GYRO_YAW"]["min"], ranges["GYRO_YAW"]["max"]), (-750.0, 750.0))
        self.assertEqual(ranges["GYRO_PITCH"]["deadzone"], 100.0)

    def test_endpoint_serves_the_live_ranges_and_a_broken_preset_is_survivable(self):
        server = self._server({
            "R_TRIGGER_PRESSURE": {"type": "axis_to_cc", "cc": 2, "channel": 0,
                                   "input_range": [5500, 32767], "output_range": [0, 127]},
        })
        client = server._app.test_client()
        served = client.get("/api/controller-map").get_json()["axis_ranges"]
        self.assertEqual(served["R_TRIGGER_PRESSURE"]["deadzone"], 5500)
        # The view is worth more than the overlay: an unreadable preset must
        # degrade to hardware bounds, never to a 500.
        with patch.object(type(server), "_load_raw_json", side_effect=OSError("gone")):
            self.assertEqual(client.get("/api/controller-map").status_code, 200)


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





class SectionApiTests(unittest.TestCase):
    def setUp(self):
        import shutil
        self.doc = {"shared": {"mappings": {"BTN_B": {"type": "note", "channel": 0, "note": 42}}},
                    "sections": {"macbook": BASE_MAP, "windows": {
                        "mappings": {"BTN_A": {"type": "note", "channel": 0, "note": 80}},
                        "engines": {"rec": False}}}}
        (self.server, self.reload_event, self.tmpdir, self.active_path,
         self.presets_dir, _) = _make_server(self.doc, section="macbook")
        self.addCleanup(shutil.rmtree, self.tmpdir)
        self.client = self.server._app.test_client()

    def test_mappings_selects_own_and_requested_section_with_metadata(self):
        own = self.client.get("/api/mappings").get_json()
        self.assertEqual(own["section"], "macbook")
        self.assertEqual(own["bridge_section"], "macbook")
        self.assertEqual(set(own["sections"]), {"macbook", "windows"})
        self.assertEqual(own["preset"], "default.json")
        self.assertEqual(own["mappings"]["BTN_A"]["note"], 36)
        other = self.client.get("/api/mappings?section=windows").get_json()
        self.assertEqual(other["section"], "windows")
        self.assertEqual(other["mappings"]["BTN_A"]["note"], 80)
        self.assertEqual(other["mappings"]["BTN_B"]["note"], 42)
        self.assertEqual(other["document"], self.doc["sections"]["windows"])
        self.assertEqual(other["engines"], {"rec": False})
        self.client.put("/api/settings", json={"preset_section": "windows"})
        self.assertEqual(self.client.get("/api/mappings").get_json()["section"], "windows")

    def test_missing_section_read_and_save_refused(self):
        before = self.active_path.read_bytes()
        self.assertEqual(self.client.get("/api/mappings?section=missing").status_code, 422)
        response = self.client.post("/api/save", json={"section": "missing", "document": BASE_MAP})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.active_path.read_bytes(), before)
        self.assertFalse(self.reload_event.is_set())

    def test_section_save_preserves_literal_sibling_and_shared_bytes(self):
        # Deliberately noncanonical whitespace and escapes: equality of decoded
        # dictionaries alone would not detect a rewrite of a sibling value.
        sibling = '{ "mappings" : {"BTN_A":{"type":"note", "channel":0,"note":80}}, "engines":{"rec":false}, "tag":"a\\u0062" }'
        shared = '{ "mappings" : {"BTN_B":{"type":"note","channel":0,"note":42}} }'
        original = '{"shared":' + shared + ',"sections":{"windows":' + sibling + ',"macbook":' + json.dumps(BASE_MAP) + '}}'
        self.active_path.write_text(original)
        candidate = {"mappings": {"BTN_A": {"type": "note", "channel": 0, "note": 60}},
                     "engines": {"rec": True}, "analog_settings": {"deadzone": 800}}
        response = self.client.post("/api/save", json={"section": "macbook", "document": candidate})
        self.assertEqual(response.status_code, 200)
        saved = self.active_path.read_text()
        self.assertIn(sibling.encode(), self.active_path.read_bytes())
        self.assertIn(shared.encode(), self.active_path.read_bytes())
        self.assertEqual(json.loads(saved)["sections"]["macbook"], candidate)
        self.assertTrue(self.reload_event.is_set())

    def test_remote_save_does_not_capture_local_live_engines(self):
        from tests.test_engine_states import RecordingEngine
        from windows.engines.registry import EngineRegistry
        self.server.engine_registry = EngineRegistry([RecordingEngine("rec")])
        sibling = self.doc["sections"]["macbook"]
        candidate = self.doc["sections"]["windows"]
        response = self.client.post("/api/save", json={"section": "windows", "document": candidate})
        self.assertEqual(response.status_code, 200)
        saved = json.loads(self.active_path.read_text())
        self.assertEqual(saved["sections"]["windows"]["engines"], {"rec": False})
        self.assertEqual(saved["sections"]["macbook"], sibling)
        self.assertTrue(self.server.engine_registry.engines[0].active)

    def test_invalid_save_never_writes_or_reloads(self):
        before = self.active_path.read_bytes()
        for body, code in (([], 400), ({"section": "windows", "document": []}, 400),
                           ({"section": "windows", "document": {}}, 400),
                           ({"section": "windows", "document": {"mappings": {"BTN_A": {"type": "note", "note": 999, "channel": 0}}}}, 422)):
            with self.subTest(body=body):
                self.assertEqual(self.client.post("/api/save", json=body).status_code, code)
                self.assertEqual(self.active_path.read_bytes(), before)
                self.assertFalse(self.reload_event.is_set())

    def test_list_named_preset_sections_does_not_switch_active(self):
        (self.presets_dir / "Other scene.json").write_text(json.dumps({"sections": {"Grandma 2_-": BASE_MAP}}))
        response = self.client.get("/api/presets/Other%20scene.json/sections")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["sections"], ["Grandma 2_-"])
        self.assertEqual((self.presets_dir / ".active").read_text(), "default.json")
        self.assertEqual(self.client.get("/api/presets/missing.json/sections").status_code, 404)
        self.assertEqual(self.client.get("/api/presets/bad!.json/sections").status_code, 400)

    def test_add_empty_and_copy_sections(self):
        for body, expected in (({"name": "grandma"}, {"mappings": {}}),
                               ({"name": "Copied", "copy_from": "windows"}, self.doc["sections"]["windows"])):
            with self.subTest(body=body):
                self.reload_event.clear()
                response = self.client.post("/api/presets/sections/add", json=body)
                self.assertEqual(response.status_code, 200)
                saved = json.loads(self.active_path.read_text())
                self.assertEqual(saved["sections"][body["name"]], expected)
                self.assertEqual(saved["shared"], self.doc["shared"])
                self.assertTrue(self.reload_event.is_set())

    def test_rename_and_delete_preserve_siblings(self):
        response = self.client.post("/api/presets/sections/rename", json={"old": "windows", "new": "grandma"})
        self.assertEqual(response.status_code, 200)
        saved = json.loads(self.active_path.read_text())
        self.assertEqual(saved["sections"]["grandma"], self.doc["sections"]["windows"])
        self.assertNotIn("windows", saved["sections"])
        self.assertTrue(self.reload_event.is_set())
        self.reload_event.clear()
        response = self.client.post("/api/presets/sections/delete", json={"name": "grandma"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(self.active_path.read_text())["sections"], {"macbook": BASE_MAP})
        self.assertTrue(self.reload_event.is_set())

    def test_rename_own_section_updates_local_identity(self):
        response = self.client.post("/api/presets/sections/rename", json={"old": "macbook", "new": "Mac 2"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/settings").get_json()["preset_section"], "Mac 2")
        self.assertEqual(json.loads(self.server.bridge_settings.path.read_text()), {"preset_section": "Mac 2"})
        self.assertEqual(self.client.get("/api/mappings").get_json()["section"], "Mac 2")

    def test_crud_refusals_leave_file_and_reload_untouched(self):
        before = self.active_path.read_bytes()
        cases = [("add", {"name": "windows"}, 409), ("add", {"name": "bad/name"}, 400),
                 ("add", {"name": "bad\n"}, 400), ("add", {"name": None}, 400),
                 ("add", {"name": "x", "copy_from": "absent"}, 404),
                 ("rename", {"old": "windows", "new": "macbook"}, 409),
                 ("rename", {"old": "absent", "new": "x"}, 404),
                 ("delete", {"name": "absent"}, 404), ("delete", {"name": "macbook"}, 409),
                 ("rename", [], 400), ("delete", {}, 400)]
        for route, body, code in cases:
            with self.subTest(route=route, body=body):
                self.assertEqual(self.client.post("/api/presets/sections/" + route, json=body).status_code, code)
                self.assertEqual(self.active_path.read_bytes(), before)
                self.assertFalse(self.reload_event.is_set())

    def test_last_section_cannot_be_deleted_even_if_machine_is_missing(self):
        self.active_path.write_text(json.dumps({"sections": {"windows": BASE_MAP}}))
        before = self.active_path.read_bytes()
        response = self.client.post("/api/presets/sections/delete", json={"name": "windows"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.active_path.read_bytes(), before)
        self.assertFalse(self.reload_event.is_set())

    def test_legacy_reads_saves_and_add_migration_preserve_document(self):
        self.active_path.write_text(json.dumps(BASE_MAP))
        response = self.client.get("/api/mappings?section=windows")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["legacy"])
        self.assertEqual(response.get_json()["sections"], [])
        self.assertEqual(response.get_json()["mappings"], BASE_MAP["mappings"])
        self.assertEqual(self.client.post("/api/save", json={"section": "windows", "document": BASE_MAP}).status_code, 200)
        self.assertNotIn("sections", json.loads(self.active_path.read_text()))
        self.assertEqual(self.client.post("/api/presets/sections/add", json={"name": "windows", "copy_from": "macbook"}).status_code, 200)
        self.assertEqual(json.loads(self.active_path.read_text())["sections"], {"macbook": BASE_MAP, "windows": BASE_MAP})

    def test_reset_selected_section_and_save_as_preserve_siblings(self):
        self.server.base_map_path.write_text(json.dumps(BASE_MAP))
        response = self.client.post("/api/reset", json={"section": "windows"})
        self.assertEqual(response.status_code, 200)
        saved = json.loads(self.active_path.read_text())
        self.assertEqual(saved["sections"]["windows"], BASE_MAP)
        self.assertEqual(saved["sections"]["macbook"], BASE_MAP)
        from tests.test_engine_states import RecordingEngine
        from windows.engines.registry import EngineRegistry
        self.server.engine_registry = EngineRegistry([RecordingEngine("rec")])
        response = self.client.post("/api/presets/save-as", json={"name": "Copy"})
        self.assertEqual(response.status_code, 200)
        copied = json.loads((self.presets_dir / "Copy.json").read_text())
        self.assertEqual(copied["sections"]["windows"], saved["sections"]["windows"])
        self.assertEqual(copied["sections"]["macbook"]["engines"], {"rec": True})
        self.assertNotIn("engines", copied)

    def test_crlf_sibling_bytes_are_preserved(self):
        sibling = json.dumps(self.doc["sections"]["windows"], indent=2).replace("\n", "\r\n")
        original = '{\r\n"sections":{"windows":' + sibling + ',"macbook":' + json.dumps(BASE_MAP) + '}}'
        self.active_path.write_bytes(original.encode())
        response = self.client.post("/api/save", json={"section": "macbook", "document": BASE_MAP})
        self.assertEqual(response.status_code, 200)
        self.assertIn(sibling.encode(), self.active_path.read_bytes())
        self.assertTrue(self.active_path.read_bytes().startswith(b'{\r\n'))

    def test_failed_atomic_save_keeps_file_and_reload_untouched(self):
        from unittest.mock import patch
        before = self.active_path.read_bytes()
        with patch("windows.ui_server.os.replace", side_effect=OSError("disk failure")):
            response = self.client.post("/api/save", json={"section": "windows", "document": BASE_MAP})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.active_path.read_bytes(), before)
        self.assertFalse(self.reload_event.is_set())
        self.assertEqual(list(self.presets_dir.glob(".preset-*")), [])

    def test_failed_rename_identity_write_rolls_back_preset(self):
        from unittest.mock import patch
        before = self.active_path.read_bytes()
        with patch.object(self.server.bridge_settings, "save", side_effect=OSError("disk failure")):
            response = self.client.post("/api/presets/sections/rename", json={"old": "macbook", "new": "Mac 2"})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.active_path.read_bytes(), before)
        self.assertEqual(self.server.bridge_settings.preset_section, "macbook")
        self.assertFalse(self.reload_event.is_set())

    def test_first_section_names_legacy_document_and_persists_identity(self):
        self.active_path.write_text(json.dumps(BASE_MAP))
        self.server.bridge_settings.preset_section = None
        response = self.client.post("/api/presets/sections/add", json={"name": "macbook"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(self.active_path.read_text()), {"sections": {"macbook": BASE_MAP}})
        self.assertEqual(json.loads(self.server.bridge_settings.path.read_text()), {"preset_section": "macbook"})
        self.assertEqual(self.client.get("/api/mappings").get_json()["section"], "macbook")
        self.assertTrue(self.reload_event.is_set())

    def test_malformed_sections_list_returns_422(self):
        self.active_path.write_text('{"sections": null}')
        self.assertEqual(self.client.get("/api/presets/default/sections").status_code, 422)



class HtmlApiBarTests(unittest.TestCase):
    def test_external_static_api_detector_fires_and_restores(self):
        import shutil
        from unittest.mock import patch
        static_source = Path(__file__).resolve().parents[1] / "windows/static"
        with tempfile.TemporaryDirectory() as tmp:
            static_copy = Path(tmp) / "static"
            shutil.copytree(static_source, static_copy)
            make_server = _make_server

            def with_scratch_static():
                fixture = make_server()
                fixture[0]._app.static_folder = str(static_copy)
                return fixture

            def check():
                result = unittest.TestResult()
                case = HtmlApiBarTests("test_html_parses_and_all_api_paths_are_registered")
                with patch(__name__ + "._make_server", side_effect=with_scratch_static):
                    case.run(result)
                return result

            self.assertTrue(check().wasSuccessful(), "pristine static tree must be GREEN")
            planted = static_copy / "controller/nested/planted.js"
            planted.parent.mkdir(parents=True)
            planted.write_text("fetch('/api/ui-bar-planted-unknown');\n", encoding="utf-8")
            red = check()
            self.assertFalse(red.wasSuccessful(), "unknown external API literal must be RED")
            self.assertEqual(red.errors, [])
            self.assertIn("HTML API path has no registered route: /api/ui-bar-planted-unknown",
                          "\n".join(detail for _, detail in red.failures))
            planted.unlink()
            self.assertTrue(check().wasSuccessful(), "restored static tree must be GREEN")

    def test_html_parses_and_all_api_paths_are_registered(self):
        import re
        import shutil
        from html.parser import HTMLParser
        server, _, tmpdir, _, _, _ = _make_server()
        self.addCleanup(shutil.rmtree, tmpdir)
        with server._app.test_client().get("/") as response:
            html = response.data.decode()
        class Parser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.ids = []
                self.tags = []
                self.stack = []
                self.errors = []
            def handle_starttag(self, tag, attrs):
                self.tags.append(tag)
                self.ids.extend(value for key, value in attrs if key == "id")
                if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
                    self.stack.append(tag)
            def handle_endtag(self, tag):
                if not self.stack or self.stack.pop() != tag:
                    self.errors.append(tag)
        parser = Parser()
        parser.feed(html)
        parser.close()
        self.assertEqual(parser.errors, [], "mismatched HTML closing tags")
        self.assertEqual(parser.stack, [], "unclosed HTML tags")
        self.assertIn("html", parser.tags)
        self.assertIn("script", parser.tags)
        self.assertEqual(len(parser.ids), len(set(parser.ids)), "duplicate HTML ids")
        adapter = server._app.url_map.bind("localhost")
        paths = set(re.findall(r"[\"'`](/api/[^\"'`\s]*)", html))
        self.assertTrue(paths, "API path detector must find actual calls")
        # External scripts and future static assets obey the same API bar.
        for asset in Path(server._app.static_folder).rglob("*"):
            if asset.is_file():
                paths.update(re.findall(r"[\"'`](/api/[^\"'`\s]*)", asset.read_bytes().decode("utf-8", errors="replace")))
        for path in sorted(paths):
            # Dynamic JS template slots represent one encoded route component.
            concrete = re.sub(r"\$\{[^}]+\}", "example", path).split("?")[0]
            with self.subTest(path=path):
                allowed = adapter.allowed_methods(concrete)
                self.assertTrue(allowed, f"HTML API path has no registered route: {path}")
        print(f"HTML API bar: {len(paths)} paths registered; HTML parsed; ids unique")


if __name__ == "__main__":
    unittest.main()
