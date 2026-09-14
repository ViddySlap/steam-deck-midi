"""Git-pull and first-run controls through the bridge's startup loader."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from windows import win_recv
from windows.bridge_settings import BridgeSettings
from windows.config import ConfigError


ROOT = Path(__file__).resolve().parents[1]


class UpgradeBootTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.config = self.root / "config"
        self.presets = self.config / "presets"
        self.presets.mkdir(parents=True)
        self.base = self.config / "windows_midi_map.json"
        self.base.write_bytes((ROOT / "config/windows_midi_map.json").read_bytes())
        self.local = self.config / "bridge.local.json"
        self.macbook = {"mappings": {"BTN_A": {"type": "note", "channel": 0, "note": 36}}}
        self.windows = {"mappings": {"BTN_A": {"type": "note", "channel": 1, "note": 80}}}

    def sectioned(self, sections=None):
        active = self.presets / "show.json"
        active.write_text(json.dumps({"sections": sections if sections is not None else {
            "macbook": self.macbook, "windows": self.windows,
        }}))
        (self.presets / ".active").write_text(active.name)
        return active

    def test_git_pull_default_without_marker_or_local_file_boots_everywhere(self):
        default = self.presets / "default.json"
        default.write_bytes((ROOT / "config/presets/default.json").read_bytes())
        for platform in ("darwin", "win32", "linux"):
            with self.subTest(platform=platform):
                (self.presets / ".active").unlink(missing_ok=True)
                self.local.unlink(missing_ok=True)
                self.assertFalse(self.local.exists())
                settings, active, config = win_recv.load_startup_config(self.base, platform=platform)
                self.assertEqual(active, default)
                self.assertEqual(config.mappings["BTN_A"].note, 36)
                self.assertEqual(len(config.mappings), 56)
                self.assertIsNone(settings.preset_section)
                self.assertFalse(self.local.exists())

    def test_darwin_sectioned_first_run_loads_and_persists_macbook(self):
        expected = self.sectioned()
        settings, active, config = win_recv.load_startup_config(self.base, platform="darwin")
        self.assertEqual(active, expected)
        self.assertEqual((config.mappings["BTN_A"].channel, config.mappings["BTN_A"].note), (0, 36))
        self.assertEqual(settings.preset_section, "macbook")
        self.assertEqual(json.loads(self.local.read_text()), {"preset_section": "macbook"})
        self.assertEqual(list(self.config.glob(".bridge-*.tmp")), [])

    def test_other_platforms_keep_named_error_without_writing(self):
        self.sectioned()
        for platform in ("win32", "linux"):
            with self.subTest(platform=platform):
                with self.assertRaisesRegex(ConfigError, "preset section None is not available; available sections: macbook, windows"):
                    win_recv.load_startup_config(self.base, platform=platform)
                self.assertFalse(self.local.exists())

    def test_darwin_without_macbook_keeps_named_error_without_writing(self):
        self.sectioned({"windows": self.windows})
        with self.assertRaisesRegex(ConfigError, "preset section None is not available; available sections: windows"):
            win_recv.load_startup_config(self.base, platform="darwin")
        self.assertFalse(self.local.exists())

    def test_existing_local_selection_and_sentinel_bytes_survive(self):
        self.sectioned()
        before = b'{ "preset_section": "windows", "sentinel": "keep me" }\n'
        self.local.write_bytes(before)
        settings, _, config = win_recv.load_startup_config(self.base, platform="darwin")
        self.assertEqual(settings.preset_section, "windows")
        self.assertEqual((config.mappings["BTN_A"].channel, config.mappings["BTN_A"].note), (1, 80))
        self.assertEqual(self.local.read_bytes(), before)

    def test_existing_null_or_unavailable_selection_is_not_defaulted(self):
        self.sectioned()
        for section in (None, "sentinel"):
            with self.subTest(section=section):
                before = json.dumps({"preset_section": section, "sentinel": 123}).encode()
                self.local.write_bytes(before)
                with self.assertRaisesRegex(ConfigError, "available sections: macbook, windows"):
                    win_recv.load_startup_config(self.base, platform="darwin")
                self.assertEqual(self.local.read_bytes(), before)

    def test_explicit_override_does_not_create_local_file(self):
        self.sectioned()
        settings, _, config = win_recv.load_startup_config(self.base, "windows", platform="darwin")
        self.assertEqual(settings.preset_section, "windows")
        self.assertEqual(config.mappings["BTN_A"].note, 80)
        self.assertFalse(self.local.exists())

    def test_invalid_macbook_mapping_does_not_persist_identity(self):
        self.sectioned({"macbook": {"mappings": {"BTN_A": {"type": "invalid"}}}})
        with self.assertRaises(ConfigError):
            win_recv.load_startup_config(self.base, platform="darwin")
        self.assertFalse(self.local.exists())

    def test_initialization_does_not_replace_file_created_since_load(self):
        settings = BridgeSettings.load(self.local)
        before = b'{ "preset_section": "windows", "sentinel": 123 }\n'
        self.local.write_bytes(before)
        self.assertFalse(settings.save_if_missing("macbook"))
        self.assertEqual(self.local.read_bytes(), before)
        self.assertEqual(settings.preset_section, "windows")
        self.assertEqual(list(self.config.glob(".bridge-*.tmp")), [])

    def test_atomic_publish_race_uses_existing_choice_and_mapping(self):
        self.sectioned()
        before = b'{ "preset_section": "windows", "sentinel": 456 }\n'
        link = os.link

        def competing_writer(source, destination):
            self.assertFalse(self.local.exists())
            self.assertEqual(json.loads(Path(source).read_text()), {"preset_section": "macbook"})
            self.local.write_bytes(before)
            link(source, destination)

        with patch("windows.bridge_settings.os.link", side_effect=competing_writer):
            settings, _, config = win_recv.load_startup_config(self.base, platform="darwin")
        self.assertEqual(self.local.read_bytes(), before)
        self.assertEqual(settings.preset_section, "windows")
        self.assertEqual(config.mappings["BTN_A"].note, 80)
        self.assertEqual(list(self.config.glob(".bridge-*.tmp")), [])

    def test_publish_failure_leaves_no_partial_local_file(self):
        self.sectioned()
        with patch("windows.bridge_settings.os.link", side_effect=PermissionError("denied")):
            with self.assertRaisesRegex(ConfigError, "cannot create bridge settings.*bridge.local.json"):
                win_recv.load_startup_config(self.base, platform="darwin")
        self.assertFalse(self.local.exists())
        self.assertEqual(list(self.config.glob(".bridge-*.tmp")), [])


@unittest.skipUnless(os.name == "posix" and shutil.which("bash"),
                     "Mac launcher execution requires POSIX bash and paths")
class MacLauncherSnippetTests(unittest.TestCase):
    def test_section_snippet_creates_missing_file_and_preserves_existing_bytes(self):
        source = (ROOT / "scripts/mac/run_receiver.command").read_text()
        snippet = source.split("SECTION_ARGS=()\n", 1)[1].split("\npython -m windows.win_recv", 1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local = root / "config/bridge.local.json"
            local.parent.mkdir()
            env = {**os.environ, "PYTHONPATH": str(ROOT),
                   "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")}
            for before in (None, b'{ "preset_section": "Grandma 2_-", "sentinel": 9 }\n'):
                with self.subTest(before=before):
                    if before is not None:
                        local.write_bytes(before)
                    result = subprocess.run(["bash", "-c", "SECTION_ARGS=()\n" + snippet], cwd=root,
                                            env=env, text=True, capture_output=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    if before is None:
                        self.assertEqual(json.loads(local.read_text()), {"preset_section": "macbook"})
                    else:
                        self.assertEqual(local.read_bytes(), before)
