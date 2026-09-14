#!/usr/bin/env python3
"""RG mutation gate: run the WHOLE suite in a git-exported copy per mutant.
pristine GREEN -> mutant RED -> restored GREEN with sha256 equal. Bytecode disabled."""
import hashlib, os, re, shutil, subprocess, sys
from pathlib import Path

TREE = Path("/tmp/sdcore2-gate/tree")
PY = "/Users/viddyslap/Documents/project-workspaces/steam-deck-midi/.venv/bin/python"
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TMPDIR="/tmp/sdcore2-gate/tmp")
os.makedirs(ENV["TMPDIR"], exist_ok=True)

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def suite():
    for c in TREE.rglob("__pycache__"): shutil.rmtree(c, ignore_errors=True)
    r = subprocess.run([PY, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
                       cwd=TREE, env=ENV, capture_output=True, text=True)
    out = r.stdout + r.stderr
    summary = " / ".join(l for l in out.splitlines() if re.match(r"^(Ran \d+|OK|FAILED)", l))
    fails = [l for l in out.splitlines() if re.match(r"^(FAIL|ERROR): ", l)]
    return r.returncode, summary, fails

def replace_once(rel, old, new):
    p = TREE / rel; s = p.read_text(encoding="utf-8")
    n = s.count(old)
    if n != 1: raise SystemExit(f"anchor count {n} in {rel}: {old[:60]!r}")
    p.write_text(s.replace(old, new), encoding="utf-8")

def copy_in(rel, src):
    shutil.copyfile(src, TREE / rel)

MUTANTS = [
 ("a", "re-section the tracked default.json (f809be1 bytes)",
  [("copy", "config/presets/default.json", "/tmp/sdcore2-gate/default-sectioned-f809be1.json")]),
 ("b", "darwin first-run default overwrites an existing bridge.local.json",
  [("sub", "windows/win_recv.py",
    'if platform == "darwin" and section is None and not settings.path.exists():',
    'if platform == "darwin":'),
   ("sub", "windows/bridge_settings.py",
    '        if self.path.exists():\n            self.preset_section = self.load(self.path).preset_section\n            return False\n        return self._save(section, overwrite=False)',
    '        return self._save(section, overwrite=True)')]),
 ("b2", "save_if_missing alone overwrites (loader guard intact)",
  [("sub", "windows/bridge_settings.py",
    '        if self.path.exists():\n            self.preset_section = self.load(self.path).preset_section\n            return False\n        return self._save(section, overwrite=False)',
    '        return self._save(section, overwrite=True)')]),
 ("c", "POST /api/shutdown skips the loopback check",
  [("sub", "windows/ui_server.py", "            if not loopback:\n                return jsonify({\"error\": \"shutdown requires",
    "            if False:\n                return jsonify({\"error\": \"shutdown requires")]),
 ("d", "route returns 202 before setting the stop event",
  [("sub", "windows/ui_server.py", "                return jsonify({\"error\": \"shutdown requires a loopback remote address\"}), 403\n            with self._shutdown_lock:",
    "                return jsonify({\"error\": \"shutdown requires a loopback remote address\"}), 403\n            return jsonify({\"stopping\": True}), 202\n            with self._shutdown_lock:")]),
]

allbite = True
rc, s, _ = suite(); print(f"PRISTINE exit={rc} {s}"); allbite &= rc == 0
for mid, desc, edits in MUTANTS:
    files = sorted({e[1] for e in edits})
    saved = {f: (TREE / f).read_bytes() for f in files}; before = {f: sha(TREE / f) for f in files}
    for e in edits:
        if e[0] == "copy": copy_in(e[1], e[2])
        else: replace_once(e[1], e[2], e[3])
    rc_m, s_m, fails = suite()
    for f in files: (TREE / f).write_bytes(saved[f])
    rc_r, s_r, _ = suite()
    same = all(sha(TREE / f) == before[f] for f in files)
    ok = rc_m != 0 and rc_r == 0 and same
    allbite &= ok
    print(f"[{mid}] {desc}\n    files={files}\n    MUTANT exit={rc_m} {s_m}")
    for l in fails: print("      " + l)
    print(f"    RESTORED exit={rc_r} {s_r} sha_equal={same} -> {'BITES' if ok else 'DOES NOT BITE'}")
print("ALL_BITE" if allbite else "NOT_ALL_BITE")
sys.exit(0 if allbite else 1)
