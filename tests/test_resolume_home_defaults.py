"""Resolume file defaults resolve from the running user's home (sdauto A2 5b)."""

from __future__ import annotations

import inspect
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests._engine_helpers import RecordingMidiOut
from windows.engines import osc_sync, stageflow_bridge
from windows.engines.osc_sync import OscSyncEngine
from windows.engines.stageflow_bridge import StageFlowBridgeEngine

REPO = Path(__file__).resolve().parents[1]

# Pinned by construction: everything after `C:/Users/<placeholder>/` in the
# defaults the branch carried before this change (sdauto base 70cebd0).
OSC_PRESET_SUFFIX = "OneDrive/Documents/Resolume Arena/Shortcuts/OSC/STEAMDECK V2.xml"
COMP_SUFFIX = "OneDrive/Documents/Resolume Arena/Compositions/5-5-26 STEAMDECK V2.avc"

# A Windows home path of a real account: drive, Users, then the name. Built
# from parts so this file never contains the string it looks for.
_REAL_NAME = "B" + "en"
USER_HOME_RE = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+" + _REAL_NAME + r"(?![A-Za-z0-9])", re.IGNORECASE)


class _FakeOsc:
    def send(self, *a, **k):
        pass

    def close(self):
        pass


def _osc_sync(config):
    return OscSyncEngine("OSC Sync", {"type": "osc_sync", **config}, RecordingMidiOut(),
                         rest_client=object(), osc_client=_FakeOsc())


def _stageflow(config):
    return StageFlowBridgeEngine("StageFlow", {"type": "stageflow_bridge", **config}, RecordingMidiOut(),
                                 rest_client=object(), osc_client=_FakeOsc())


class HomeRelativeDefaultTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name) / "home-of-someone"
        self.home.mkdir()
        env = patch.dict(os.environ, {"HOME": str(self.home), "USERPROFILE": str(self.home)})
        env.start()
        self.addCleanup(env.stop)

    def test_missing_key_resolves_under_the_running_users_home(self):
        preset = Path(_osc_sync({})._osc_preset_path)
        comp = _stageflow({})._comp_path
        self.assertEqual(preset.relative_to(self.home).as_posix(), OSC_PRESET_SUFFIX)
        self.assertEqual(comp.relative_to(self.home).as_posix(), COMP_SUFFIX)
        self.assertEqual(preset, self.home.joinpath(*OSC_PRESET_SUFFIX.split("/")))

    def test_explicit_value_is_used_verbatim(self):
        self.assertEqual(_osc_sync({"osc_preset_path": "Z:/show/preset.xml"})._osc_preset_path,
                         "Z:/show/preset.xml")
        self.assertEqual(_stageflow({"comp_path": "Z:/show/comp.avc"})._comp_path, Path("Z:/show/comp.avc"))

    def test_placeholder_is_gone_from_both_defaults_and_the_factory_file(self):
        for module in (osc_sync, stageflow_bridge):
            self.assertNotIn("USERNAME", inspect.getsource(module))
        factory = json.loads((REPO / "config/engines.factory/osc_sync.json").read_text(encoding="utf-8"))
        self.assertNotIn("osc_preset_path", factory)
        self.assertNotIn("USERNAME", str(_osc_sync(factory)._osc_preset_path))


class RealUserHomeNotInShippedTreeTests(unittest.TestCase):
    """docs/ and scripts/ are excluded: lane evidence and the pinned laptop rail
    record the laptop's real paths and are not part of a build."""

    @staticmethod
    def hits(paths):
        found = []
        for path in paths:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if USER_HOME_RE.search(text):
                found.append(path)
        return found

    def test_detector_fires_on_a_planted_path_and_not_on_a_clean_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            planted = Path(tmp) / "planted.json"
            clean = Path(tmp) / "clean.json"
            planted.write_text('{"p": "c:\\\\users\\\\' + _REAL_NAME.lower() + '\\\\x.xml"}', encoding="utf-8")
            clean.write_text('{"p": "C:/Users/Benedict/x.xml", "q": "C:/Users/someone/x"}', encoding="utf-8")
            self.assertEqual(self.hits([planted, clean]), [planted])

    def test_tracked_files_outside_docs_and_scripts_hold_no_real_user_home(self):
        try:
            listed = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True).stdout
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("not a git checkout")
        paths = [REPO / name for name in listed.decode("utf-8").split("\0")
                 if name and not name.startswith(("docs/", "scripts/"))]
        self.assertGreater(len(paths), 100)  # zero observations is not a pass
        self.assertIn(REPO / "windows/engines/osc_sync.py", paths)
        self.assertEqual(self.hits(paths), [])


if __name__ == "__main__":
    unittest.main()
