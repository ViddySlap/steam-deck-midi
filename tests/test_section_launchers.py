"""Observe launcher argv without opening a browser or starting a second bridge."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "posix" and shutil.which("bash"),
                     "Mac launcher execution requires POSIX bash and executable shebangs")
class MacSectionLauncherTests(unittest.TestCase):
    def test_local_section_is_passed_as_one_argument_and_missing_file_still_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root / "scripts/mac"
            scripts.mkdir(parents=True)
            launcher = scripts / "run_receiver.command"
            shutil.copyfile(ROOT / "scripts/mac/run_receiver.command", launcher)
            bin_dir = root / ".venv/bin"
            bin_dir.mkdir(parents=True)
            (bin_dir / "activate").write_text('export PATH="' + str(bin_dir) + ':$PATH"\n')
            stub = bin_dir / "python"
            stub.write_text(
                "#!" + sys.executable + "\n"
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "if sys.argv[1] == '-c':\n"
                "    exec(sys.argv[2])\n"
                "else:\n"
                "    Path(os.environ['ARGV_CAPTURE']).write_text(json.dumps(sys.argv[1:]))\n"
            )
            stub.chmod(0o755)
            for name in ("sleep", "open"):
                path = bin_dir / name
                path.write_text("#!/bin/sh\nexit 0\n")
                path.chmod(0o755)
            local = root / "config/bridge.local.json"
            local.parent.mkdir()
            capture = root / "argv.json"
            env = {**os.environ, "PYTHONPATH": str(ROOT), "ARGV_CAPTURE": str(capture),
                   "PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", "")}
            for section in ("Grandma 2_-", None):
                with self.subTest(section=section):
                    if section:
                        local.write_text(json.dumps({"preset_section": section}))
                    else:
                        local.unlink()
                    result = subprocess.run(["bash", str(launcher)], env=env, input="\n",
                                            text=True, capture_output=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    argv = json.loads(capture.read_text())
                    self.assertEqual(argv[:2], ["-m", "windows.win_recv"])
                    if section:
                        self.assertEqual(argv[argv.index("--preset-section") + 1], section)
                    else:
                        self.assertEqual(argv[argv.index("--preset-section") + 1], "macbook")
                        self.assertEqual(json.loads(local.read_text()), {"preset_section": "macbook"})


class WindowsSectionLauncherContractTests(unittest.TestCase):
    def test_all_three_launchers_pass_the_backfilled_or_persisted_section(self):
        # A source contract guard; the gate still owes execution on Windows.
        for name in ("start_receiver.ps1", "start_installed_receiver.ps1",
                     "start_installed_receiver_v2.ps1"):
            with self.subTest(name=name):
                source = (ROOT / "scripts/windows" / name).read_text()
                self.assertIn('$presetSection = [string]$settings.preset_section', source)
                self.assertIn('$presetSection = [string]$bridgeSettings.preset_section', source)
                self.assertIn('$args += "--preset-section"\n    $args += $presetSection', source)
                self.assertLess(source.index('foreach ($property'), source.index('$presetSection ='))
        example = json.loads((ROOT / "config/windows_receiver_settings.example.json").read_text())
        self.assertEqual(example["preset_section"], "windows")
