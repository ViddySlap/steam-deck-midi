"""sdauto gate step 6: mutations in scratch copies; each must go RED, then restored GREEN.

  .venv/bin/python -B docs/sdauto-gate/scripts/mutations.py --out /tmp/sdauto-gate/s6

(a)-(e): `git archive HEAD` into a scratch tree, one exact one-site replacement, run the named
test modules from that tree (RED expected), write the original bytes back, require the file's
sha256 to equal HEAD's, run again (GREEN expected).
(f): a scratch clone, a commit with a one-byte column-note change in autopilot.py (86 -> 96),
engine_ab.py --repo <clone> --candidate <that commit> (exit 1 expected, autopilot in
different_sources), then --candidate HEAD in the same clone (exit 0 expected).
"""
import argparse, hashlib, json, os, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PY = str(ROOT / ".venv/bin/python")
HEAD = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()

MUTANTS = [
    ("a", "skip the restore overlay", "windows/engines/autopilot.py",
     "        self._restore_intent(path)\n", "        pass  # MUTANT: self._restore_intent(path)\n",
     ["tests.test_autopilot_state"]),
    ("b", "persist crossfade_start_time", "windows/engines/autopilot.py",
     '                "clip_mode": state.clip_mode.name,\n                "layer_enabled": {\n',
     '                "clip_mode": state.clip_mode.name,\n                "crossfade_start_time": state.crossfade_start_time,\n                "layer_enabled": {\n',
     ["tests.test_autopilot_state"]),
    ("c", "engine PUT skips filter removal and old.shutdown()", "windows/engines/registry.py",
     "        for callback in [cb for cb in self._note_emit_filters\n                         if getattr(cb, \"__self__\", None) is old]:\n            self.remove_note_emit_filter(callback)\n        try:\n            old.shutdown()\n",
     "        for callback in []:\n            self.remove_note_emit_filter(callback)\n        try:\n            pass\n",
     ["tests.test_engine_config_api"]),
    ("d", "platform function returns True on darwin", "windows/win_recv.py",
     '    return platform != "darwin"\n', "    return True\n",
     ["tests.test_win_recv_tray_platform"]),
    ("e", "VERSION 0.5.1 with APP_VERSION 0.5.0", "VERSION", "0.5.0", "0.5.1",
     ["tests.test_ui_server.VersionAgreementTests"]),
]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def run_tests(tree, modules, log):
    env = {**os.environ, "PYSTRAY_BACKEND": "dummy", "BROWSER": "/usr/bin/true", "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run([PY, "-B", "-m", "unittest", *modules], cwd=tree, env=env, capture_output=True, text=True)
    log.write_text(r.stdout + r.stderr)
    tail = [l for l in (r.stdout + r.stderr).splitlines() if l.startswith(("Ran ", "OK", "FAILED"))]
    fails = [l.split(" (")[0].replace("FAIL: ", "").replace("ERROR: ", "") for l in (r.stdout + r.stderr).splitlines() if l.startswith(("FAIL: ", "ERROR: "))]
    return {"exit": r.returncode, "summary": tail, "failing": fails}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    out = Path(ap.parse_args().out)
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    rows = []
    for key, name, rel, old, new, modules in MUTANTS:
        tree = out / f"tree-{key}"
        tree.mkdir()
        assert subprocess.run(f"git -C '{ROOT}' archive HEAD | tar -x -C '{tree}'", shell=True).returncode == 0
        target = tree / rel
        original = target.read_bytes()
        text = original.decode()
        assert text.count(old) == 1, (key, "site must occur exactly once")
        target.write_text(text.replace(old, new))
        red = run_tests(tree, modules, out / f"{key}-red.log")
        target.write_bytes(original)
        head_sha = sha(subprocess.check_output(["git", "-C", str(ROOT), "show", f"HEAD:{rel}"]))
        green = run_tests(tree, modules, out / f"{key}-green.log")
        row = {"mutant": key, "change": name, "file": rel, "tests": modules, "red": red, "restored_sha_equals_head": sha(target.read_bytes()) == head_sha,
               "green": green, "ok": red["exit"] != 0 and green["exit"] == 0 and sha(target.read_bytes()) == head_sha}
        rows.append(row)
        print(key, name, "RED" if red["exit"] else "NOT RED", red["summary"], red["failing"][:6], "| restored", "GREEN" if green["exit"] == 0 else "NOT GREEN", green["summary"], flush=True)
    # (f)
    clone = out / "clone"
    subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout", str(ROOT), str(clone)], check=True)
    subprocess.run(["git", "-C", str(clone), "checkout", "-q", HEAD], check=True)
    src = clone / "windows/engines/autopilot.py"
    t = src.read_text()
    old, new = "COLUMN_PREV_NOTES = frozenset({82, 86})", "COLUMN_PREV_NOTES = frozenset({82, 96})"
    assert t.count(old) == 1
    src.write_text(t.replace(old, new))
    subprocess.run(["git", "-C", str(clone), "-c", "user.name=gate", "-c", "user.email=gate@localhost", "commit", "-q", "-am", "mutant f: one-byte column note"], check=True)
    mut = subprocess.check_output(["git", "-C", str(clone), "rev-parse", "HEAD"], text=True).strip()
    diff = subprocess.check_output(["git", "-C", str(clone), "diff", "--numstat", HEAD, mut], text=True).strip()
    res = {}
    for label, cand in (("red", mut), ("green", HEAD)):
        outj = out / f"f-{label}.json"
        r = subprocess.run([PY, "-B", str(ROOT / "scripts/showready/engine_ab.py"), "--repo", str(clone), "--candidate", cand,
                            "--preset", str(ROOT / ".showready/fixtures/mac/presets/EDM Show.json"), "--section", "windows",
                            "--scratch", str(out / f"f-scratch-{label}"), "--out", str(outj)], capture_output=True, text=True, cwd=ROOT)
        (out / f"f-{label}.log").write_text(r.stdout + r.stderr)
        d = json.loads(outj.read_text()) if outj.exists() else {}
        res[label] = {"candidate": cand, "exit": r.returncode, "passed": d.get("passed"), "error": d.get("error"),
                      "different_sources": {k: v.get("different_sources") for k, v in d.get("comparisons", {}).items()},
                      "first_difference": {k: v.get("first_difference") for k, v in d.get("comparisons", {}).items()}}
    row = {"mutant": "f", "change": "one-byte column-note change (86 -> 96) in autopilot.py, engine_ab.py", "diff_numstat": diff, **res,
           "ok": res["red"]["exit"] == 1 and all("autopilot" in (v or []) for v in res["red"]["different_sources"].values()) and res["green"]["exit"] == 0 and res["green"]["passed"] is True}
    rows.append(row)
    print("f", row["change"], "RED" if res["red"]["exit"] == 1 else "NOT RED", res["red"]["different_sources"], "| restored", "GREEN" if res["green"]["exit"] == 0 else "NOT GREEN", flush=True)
    (out / "mutations.json").write_text(json.dumps(rows, indent=2))
    ok = all(r["ok"] for r in rows)
    print("MUTATIONS", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
