"""sdauto A3 revert proof: one-site mutants, each must turn its tests RED.

Usage (from the run root): .venv/bin/python -B docs/sdauto-a3/mutant_sweep.py
Copies windows/, tests/, config/, protocol/ and docs/api.md into a fresh
scratch dir per mutant, applies one exact string replacement, runs the named
test modules there, and records exit code and the unittest summary line.
M0 is the clean copy and must be GREEN. Writes docs/sdauto-a3/mutant_sweep.json.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = str(ROOT / ".venv/bin/python")
TRP = "tests.test_win_recv_tray_platform"
BSD = "tests.test_bridge_shutdown"
WRS = "tests.test_win_recv_settings"
WR = "windows/win_recv.py"

MUTANTS = [
    ("M0", "clean", None, None, None, [TRP, BSD, WRS]),
    ("M1", "platform rule starts the sidecar on darwin", WR,
     '    return platform != "darwin"\n', "    return True\n", [TRP]),
    ("M2", "platform rule never starts the sidecar (win32 regresses)", WR,
     '    return platform != "darwin"\n', "    return False\n", [TRP, BSD]),
    ("M3", "tray-mode clause removed from the platform rule", WR,
     "    if tray_mode:\n        return False\n    return platform", "    return platform", [TRP]),
    ("M4", "main() reverted to today's `if not args.tray` sidecar start", WR,
     "        if _should_start_receiver_tray(sys.platform, args.tray):\n", "        if not args.tray:\n", [TRP]),
    ("M5", "--no-browser ignored in non-tray mode", WR,
     "        if not args.tray and not args.no_browser:\n", "        if not args.tray:\n", [TRP]),
    ("M6", "--no-browser ignored in the already-running path", WR,
     "            if args.no_browser:\n", "            if False:\n", [TRP]),
    ("M7", "non-tray startup never opens the browser", WR,
     "            _open_browser_delayed(ui_server.url)\n", "            pass\n", [TRP]),
    ("M8", "win32 sidecar tray not stopped at teardown", WR,
     "        if tray is not None:\n            tray.stop()\n", "        if tray is not None:\n            pass\n", [TRP]),
    ("M9", "existing shutdown test without its win32 pin (proves the test change is needed on darwin)",
     "tests/test_bridge_shutdown.py",
     '                     patch.object(win_recv.sys, "platform", "win32"), \\\n', "", [BSD]),
]


def main() -> int:
    rows = []
    ok = True
    for mid, what, rel, old, new, modules in MUTANTS:
        with tempfile.TemporaryDirectory(prefix=f"sdauto-a3-{mid}-") as tmp:
            copy = Path(tmp)
            for name in ("windows", "tests", "config", "protocol"):
                shutil.copytree(ROOT / name, copy / name, ignore=shutil.ignore_patterns("__pycache__"))
            (copy / "docs").mkdir()
            shutil.copy2(ROOT / "docs/api.md", copy / "docs/api.md")
            if rel is not None:
                target = copy / rel
                text = target.read_text(encoding="utf-8")
                count = text.count(old)
                if count != 1:
                    rows.append({"id": mid, "what": what, "error": f"site count {count}"})
                    ok = False
                    print(mid, "site count", count, flush=True)
                    continue
                target.write_text(text.replace(old, new), encoding="utf-8")
            proc = subprocess.run([PY, "-B", "-m", "unittest", *modules], cwd=copy,
                                  capture_output=True, text=True, timeout=600,
                                  env={"PATH": "/usr/bin:/bin", "PYSTRAY_BACKEND": "dummy",
                                       "BROWSER": "/usr/bin/true", "TMPDIR": tmp, "HOME": tmp})
            tail = [l for l in proc.stderr.splitlines() if re.match(r"^(Ran |OK|FAILED)", l)]
            failing = sorted(set(re.findall(r"^(?:FAIL|ERROR): (\w+)", proc.stderr, re.M)))
            expected_red = rel is not None
            verdict = (proc.returncode != 0) == expected_red
            ok &= verdict
            rows.append({"id": mid, "what": what, "modules": modules, "exit": proc.returncode,
                         "summary": tail, "failing_tests": failing,
                         "verdict": "RED as required" if expected_red and verdict else
                                    "GREEN as required" if verdict else "SURVIVED" if expected_red else "CLEAN RED"})
            print(mid, proc.returncode, " | ".join(tail), failing[:4], flush=True)
    out = ROOT / "docs/sdauto-a3/mutant_sweep.json"
    out.write_text(json.dumps({"platform": sys.platform, "sweep_green": ok, "rows": rows}, indent=2) + "\n",
                   encoding="utf-8")
    print("SWEEP GREEN" if ok else "SWEEP RED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
