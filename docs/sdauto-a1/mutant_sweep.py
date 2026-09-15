"""Mutant sweep for sdauto A1: each mutant is a one-site edit in a scratch copy."""
import json, re, shutil, subprocess, sys
from pathlib import Path
ROOT = Path("/Users/viddyslap/Documents/project-workspaces/steam-deck-midi")
PY = ROOT / ".venv/bin/python"
OUT = Path("/tmp/sdauto-a1/mutants")
MUTANTS = [
 ("M0_clean", None, None, None),
 ("M1_restore_call_commented", "windows/engines/autopilot.py",
  "        self._restore_intent(path)\n", "        # self._restore_intent(path)\n"),
 ("M2_no_restore_replay_in_tick", "windows/engines/autopilot.py",
  "    def tick(self, now: float) -> None:\n        if self._restored_channels:\n            self._apply_restored_intent()\n",
  "    def tick(self, now: float) -> None:\n"),
 ("M3_replay_at_construction", "windows/engines/autopilot.py",
  "        self._restore_intent(path)\n", "        self._restore_intent(path)\n        self._apply_restored_intent()\n"),
 ("M4_shutdown_skips_writer_close", "windows/engines/autopilot.py",
  "            self._state_writer.close()\n", "            pass\n"),
 ("M5_transition_not_persisted", "windows/engines/autopilot.py",
  "            if changed:\n                self._persist_intent()\n", "            if changed:\n                pass\n"),
 ("M6_runtime_field_on_disk", "windows/engines/autopilot.py",
  '                "layer_enabled": {\n                    str(layer)', '                "crossfade_start_time": state.crossfade_start_time,\n                "layer_enabled": {\n                    str(layer)'),
 ("M7_registry_drops_state_dir", "windows/engines/registry.py",
  '            kwargs["state_dir"] = Path(state_dir)\n', '            pass\n'),
 ("M8_state_dir_inside_engines_allowed", "windows/engines/registry.py",
  "        if resolved_state == resolved_user or resolved_user in resolved_state.parents:\n",
  "        if False:\n"),
 ("M9_write_on_calling_thread_unguarded", "windows/engines/autopilot_state.py",
  "            else:\n                self._pending = document\n",
  "            else:\n                self._completed = self._submitted\n                self.path.parent.mkdir(parents=True, exist_ok=True)\n                self.path.write_text(json.dumps(document))\n                return\n"),
 ("M10_failure_log_not_rate_limited", "windows/engines/autopilot_state.py",
  "                or now - self._last_failure_log_at >= FAILURE_LOG_INTERVAL_SECONDS\n",
  "                or True\n"),
 ("M11_invalid_file_rewritten_at_start", "windows/engines/autopilot.py",
  "        self._restore_intent(path)\n", "        self._restore_intent(path)\n        self._state_writer.submit(self._intent_document())\n"),
 ("M12_clear_route_removed", "windows/ui_server.py",
  '@app.route("/api/engines/autopilot/state/clear", methods=["POST"])', '@app.route("/api/engines/autopilot/state/clear-x", methods=["POST"])'),
 ("M13_unknown_layer_not_ignored", "windows/engines/autopilot.py",
  "                if layer in state.layer_enabled:\n", "                if True:\n"),
 ("M14_future_schema_accepted", "windows/engines/autopilot_state.py",
  "    if schema != SCHEMA_VERSION:\n", "    if schema < SCHEMA_VERSION:\n"),
 ("M15_mode_change_not_persisted", "windows/engines/autopilot.py",
  '                LOGGER.info("autopilot %s: mode=%s", ch_key, new_mode.name)\n                self._persist_intent()\n',
  '                LOGGER.info("autopilot %s: mode=%s", ch_key, new_mode.name)\n'),
 ("M16_clear_does_not_persist", "windows/engines/autopilot.py",
  "            self._persist_intent()\n            persisted = self._state_writer.flush()\n",
  "            persisted = self._state_writer.flush()\n"),
]
results = []
for name, rel, old, new in MUTANTS:
    dest = OUT / "trees" / name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns(".git", ".venv", ".showready", "__pycache__", "node_modules", "config"))
    shutil.copytree(ROOT / "config/engines.factory", dest / "config/engines.factory")
    if rel:
        f = dest / rel
        text = f.read_text()
        assert text.count(old) == 1, (name, text.count(old))
        f.write_text(text.replace(old, new))
    proc = subprocess.run([str(PY), "-B", "-m", "unittest", "tests.test_autopilot_state"], cwd=dest,
                          capture_output=True, text=True, timeout=300, env={"PATH": "/usr/bin:/bin", "TMPDIR": "/tmp/sdauto-a1/suite"})
    failed = sorted(set(re.findall(r"^(?:FAIL|ERROR): (\w+)", proc.stderr, re.M)))
    summary = [l for l in proc.stderr.splitlines() if l.startswith(("Ran ", "OK", "FAILED"))]
    results.append({"mutant": name, "exit": proc.returncode, "summary": summary, "failed": failed})
    print(name, proc.returncode, summary, failed, flush=True)
    shutil.rmtree(dest)
(OUT / "sweep.json").write_text(json.dumps(results, indent=2))
bad = [r for r in results if (r["mutant"] == "M0_clean") == (r["exit"] != 0)]
print("SWEEP", "GREEN" if not bad else f"RED {[r['mutant'] for r in bad]}")
sys.exit(1 if bad else 0)
