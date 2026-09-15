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
