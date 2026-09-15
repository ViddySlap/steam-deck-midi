"""Keep every shipped UI node:vm behavior check in the platform suite."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NodeUiTests(unittest.TestCase):
    def test_all_ui_node_checks(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("NODE-ABSENT: node is required for the UI VM behavior checks")
        checks = sorted((ROOT / "tests").glob("ui_*_check.cjs"))
        self.assertTrue(checks, "UI check discovery must observe actual scripts")
        for check in checks:
            with self.subTest(check=check.name):
                result = subprocess.run([node, str(check)], cwd=ROOT, capture_output=True,
                                        text=True, timeout=120,
                                        env={**os.environ, "PYTHON": sys.executable})
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_version_check_fires_on_planted_header_faults(self):
        import tempfile
        node = shutil.which("node")
        if not node:
            self.skipTest("NODE-ABSENT: node is required for the UI VM behavior checks")
        fix = "  header select { width: auto; }\n"
        source = (ROOT / "windows/static/index.html").read_text(encoding="utf-8")
        self.assertEqual(source.count(fix), 1, "the F4 rule must be present to plant its removal")
        planted = {
            # F4 reverted: the header select stretches again.
            "f4-removed": (source.replace(fix, ""), "FAIL 1440x900.sectionSelect width auto"),
            # Over-broad fix: every select shrinks, a visual change outside the header.
            "global-auto": (source.replace(fix, "  select { width: auto; }\n"), "FAIL 1440x900.macroEditorType width 100%"),
            "restored": (source, None),
        }
        for name, (html, token) in planted.items():
            with self.subTest(plant=name), tempfile.TemporaryDirectory() as tmp:
                static = Path(tmp) / "static"
                shutil.copytree(ROOT / "windows/static", static)
                (static / "index.html").write_text(html, encoding="utf-8")
                result = subprocess.run([node, str(ROOT / "tests/ui_version_check.cjs"), str(static / "index.html")],
                                        cwd=ROOT, capture_output=True, text=True, timeout=120)
                if token is None:
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                else:
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn(token, result.stdout)
