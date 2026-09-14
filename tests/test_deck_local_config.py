from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from deck.local_config import (
    ensure_local_settings,
    load_runtime_settings,
    validate_ipv4_address,
    with_added_preset,
    with_deleted_preset,
    with_device_id,
    with_renamed_preset,
    with_active_targets,
    write_runtime_settings,
    describe_preset,
    validate_target_host,
)


class DeckLocalConfigTests(unittest.TestCase):
    def test_validate_ipv4_address_accepts_valid_address(self) -> None:
        self.assertEqual(validate_ipv4_address("10.10.10.20"), "10.10.10.20")

    def test_validate_ipv4_address_rejects_invalid_address(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid IPv4 address"):
            validate_ipv4_address("not-an-ip")

    def test_ensure_local_settings_copies_example_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            example = root / "example.json"
            local = root / "local.json"
            example.write_text(
                """
{
  "device_id": "5",
  "bindings_path": "config/deck_bindings.json",
  "actions_path": "config/actions.yaml",
  "default_port": 45123,
  "profile_name": "default",
  "profile_hash": null,
  "presets": []
}
""".strip()
                + "\n",
                encoding="utf-8",
            )

            settings = ensure_local_settings(str(local), str(example))

            self.assertTrue(local.exists())
            self.assertEqual(settings.default_port, 45123)
            self.assertEqual(settings.presets, [])
            self.assertEqual(settings.device_id, "5")

    def test_with_device_id_updates_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "settings.json"
            path.write_text(
                """
{
  "device_id": null,
  "bindings_path": "config/deck_bindings.json",
  "actions_path": "config/actions.yaml",
  "default_port": 45123,
  "profile_name": "default",
  "profile_hash": null,
  "presets": []
}
""".strip()
                + "\n",
                encoding="utf-8",
            )
            settings = load_runtime_settings(str(path))
            updated = with_device_id(settings, "5")

            self.assertEqual(updated.device_id, "5")

    def _settings_with_presets(self, tmpdir: str, presets: list) -> object:
        path = Path(tmpdir) / "settings.json"
        payload = {
            "device_id": "5",
            "bindings_path": "config/deck_bindings.json",
            "actions_path": "config/actions.yaml",
            "default_port": 45123,
            "profile_name": "default",
            "profile_hash": None,
            "presets": presets,
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
        return load_runtime_settings(str(path))

    def test_with_renamed_preset_updates_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings_with_presets(
                tmpdir, [{"name": "Home", "host": "10.10.10.15", "port": 45123}]
            )
            updated = with_renamed_preset(settings, 0, "Studio")
        self.assertEqual(updated.presets[0].name, "Studio")
        self.assertEqual(updated.presets[0].host, "10.10.10.15")

    def test_with_renamed_preset_rejects_empty_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings_with_presets(
                tmpdir, [{"name": "Home", "host": "10.10.10.15", "port": 45123}]
            )
            with self.assertRaises(ValueError):
                with_renamed_preset(settings, 0, "")

    def test_with_renamed_preset_rejects_out_of_range_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings_with_presets(
                tmpdir, [{"name": "Home", "host": "10.10.10.15", "port": 45123}]
            )
            with self.assertRaises(ValueError):
                with_renamed_preset(settings, 5, "New Name")

    def test_with_deleted_preset_removes_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings_with_presets(
                tmpdir,
                [
                    {"name": "Home", "host": "10.10.10.15", "port": 45123},
                    {"name": "Studio", "host": "10.10.10.20", "port": 45123},
                ],
            )
            updated = with_deleted_preset(settings, 0)
        self.assertEqual(len(updated.presets), 1)
        self.assertEqual(updated.presets[0].name, "Studio")

    def test_with_deleted_preset_rejects_out_of_range_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings_with_presets(tmpdir, [])
            with self.assertRaises(ValueError):
                with_deleted_preset(settings, 0)

    def test_with_added_preset_appends_preset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "settings.json"
            path.write_text(
                """
{
  "device_id": "5",
  "bindings_path": "config/deck_bindings.json",
  "actions_path": "config/actions.yaml",
  "default_port": 45123,
  "profile_name": "default",
  "profile_hash": null,
  "presets": []
}
""".strip()
                + "\n",
                encoding="utf-8",
            )
            settings = load_runtime_settings(str(path))
            updated = with_added_preset(settings, name="Resolume PC", host="10.10.10.20")

            self.assertEqual(len(updated.presets), 1)
            self.assertEqual(updated.presets[0].name, "Resolume PC")
            self.assertEqual(updated.presets[0].host, "10.10.10.20")


class ActiveTargetsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "settings.json"
        self.raw = {"presets": [
            {"name": "PC", "host": "192.0.2.1", "port": 45123},
            {"name": "Mac", "host": "viddymac.local", "port": 45124}]}
        self.path.write_text(json.dumps(self.raw))
        self.settings = load_runtime_settings(str(self.path))

    def test_legacy_defaults_to_empty_without_rewriting_existing_file(self):
        before = self.path.read_bytes()
        settings = ensure_local_settings(str(self.path), "unused-example.json")
        self.assertEqual(settings.active_targets, [])
        self.assertEqual(self.path.read_bytes(), before)

    def test_round_trip_preserves_order_and_uses_atomic_replace(self):
        selected = with_active_targets(self.settings, ["Mac", "PC"])
        import os
        real_replace = os.replace
        previous = self.path.read_bytes()
        def observed_replace(source, destination):
            self.assertEqual(self.path.read_bytes(), previous)
            self.assertEqual(Path(source).parent, self.path.parent)
            self.assertEqual(json.loads(Path(source).read_text())["active_targets"], ["Mac", "PC"])
            real_replace(source, destination)
        with patch("deck.local_config.os.replace", side_effect=observed_replace) as atomic:
            write_runtime_settings(str(self.path), selected)
            atomic.assert_called_once()
        self.assertEqual(load_runtime_settings(str(self.path)), selected)
        self.assertEqual(json.loads(self.path.read_text())["active_targets"], ["Mac", "PC"])
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_unknown_repeated_and_malformed_names_refused_on_load_and_write(self):
        for names in [["missing"], ["PC", "PC"], "PC", [1], None]:
            with self.subTest(names=names):
                self.path.write_text(json.dumps({**self.raw, "active_targets": names}))
                with self.assertRaises(ValueError):
                    load_runtime_settings(str(self.path))
                before = self.path.read_bytes()
                with self.assertRaises(ValueError):
                    write_runtime_settings(str(self.path), replace(self.settings, active_targets=names))
                self.assertEqual(self.path.read_bytes(), before)
                with self.assertRaises(ValueError):
                    with_active_targets(self.settings, names)

    def test_ambiguous_legacy_names_only_refused_when_selected(self):
        raw = {"presets": [self.raw["presets"][0]] * 2}
        self.path.write_text(json.dumps(raw))
        legacy = load_runtime_settings(str(self.path))
        self.assertEqual(len(legacy.presets), 2)
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            with_active_targets(legacy, ["PC"])

    def test_hostnames_accepted_by_add_and_loader(self):
        self.assertEqual(self.settings.presets[1].host, "viddymac.local")
        for host in ["viddymac.local", "travel-router", "Mac2.local.", "192.0.2.3"]:
            with self.subTest(host=host):
                updated = with_added_preset(self.settings, name="New", host=host)
                write_runtime_settings(str(self.path), updated)
                self.assertEqual(load_runtime_settings(str(self.path)).presets[-1].host, host)

    def test_invalid_host_characters_and_ipv4_refused(self):
        for host in ["", "bad host", "a/b", "a:2", "::1", "-host", "host-", "a..b", "host..",
                     "999.1.2.3", "123", "x" * 64 + ".local", "caf\u00e9.local"]:
            with self.subTest(host=host), self.assertRaises(ValueError):
                validate_target_host(host)

    def test_other_settings_edits_preserve_selection(self):
        selected = with_active_targets(self.settings, ["Mac", "PC"])
        for updated in [with_device_id(selected, "7"),
                        with_added_preset(selected, name="Desk", host="desk.local")]:
            write_runtime_settings(str(self.path), updated)
            self.assertEqual(load_runtime_settings(str(self.path)).active_targets, ["Mac", "PC"])

    def test_rename_and_delete_keep_active_names_valid_on_disk(self):
        selected = with_active_targets(self.settings, ["Mac", "PC"])
        renamed = with_renamed_preset(selected, 1, "Laptop")
        write_runtime_settings(str(self.path), renamed)
        self.assertEqual(load_runtime_settings(str(self.path)).active_targets, ["Laptop", "PC"])
        deleted = with_deleted_preset(renamed, 0)
        write_runtime_settings(str(self.path), deleted)
        self.assertEqual(load_runtime_settings(str(self.path)).active_targets, ["Laptop"])

    def test_new_duplicate_names_refused(self):
        with self.assertRaises(ValueError):
            with_added_preset(self.settings, name="Mac", host="desk.local")
        with self.assertRaises(ValueError):
            with_renamed_preset(self.settings, 0, "Mac")

    def test_describe_preset_marks_active(self):
        self.assertEqual(describe_preset(1, self.settings.presets[0], True),
                         "1. PC (192.0.2.1:45123) [active]")
        self.assertEqual(describe_preset(1, self.settings.presets[0]),
                         "1. PC (192.0.2.1:45123)")
