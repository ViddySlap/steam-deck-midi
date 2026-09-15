"""sdauto A2 revert proof: one-site mutants, each must turn its tests RED.

Usage (from the run root): .venv/bin/python -B docs/sdauto-a2/mutant_sweep.py
Copies windows/, tests/, config/, protocol/ and docs/api.md into a fresh
scratch dir per mutant, applies one exact string replacement, runs the named
test modules there, and records exit code and the unittest summary line.
M0 is the clean copy and must be GREEN. Writes docs/sdauto-a2/mutant_sweep.json.
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
ECA = "tests.test_engine_config_api"
AGR = "tests.test_agent_routes"
RTK = "tests.test_receiver_tasks"
HOM = "tests.test_resolume_home_defaults"
UIS = "tests.test_ui_server"

MUTANTS = [
    ("M0", "clean", None, None, None, [ECA, AGR, RTK, HOM, UIS]),
    ("M1", "serve_forever does not drain receiver tasks", "windows/receiver.py",
     "                receiver_tasks.drain()\n", "                pass\n", [RTK]),
    ("M2", "PUT applies on the HTTP thread, not the receiver thread", "windows/engine_config_api.py",
     "new = receiver_tasks.run(apply_on_receiver_thread)", "new = apply_on_receiver_thread()", [ECA]),
    ("M3", "replace keeps the old instance's note-emit filters", "windows/engines/registry.py",
     "            self.remove_note_emit_filter(callback)\n        try:\n            old.shutdown()",
     "            pass\n        try:\n            old.shutdown()", [ECA]),
    ("M4", "replace appends the new engine instead of taking the slot", "windows/engines/registry.py",
     "        self._engines[index] = new\n", "        del self._engines[index]\n        self._engines.append(new)\n", [ECA]),
    ("M5", "replace skips old.shutdown()", "windows/engines/registry.py",
     "            old.shutdown()\n        except Exception:\n            LOGGER.exception(\"engine %s shutdown failed during replace\"",
     "            pass\n        except Exception:\n            LOGGER.exception(\"engine %s shutdown failed during replace\"", [ECA]),
    ("M6", "swap does not carry the runtime active flag", "windows/engine_config_api.py",
     "        new.set_active(active)\n", "", [ECA]),
    ("M7", "no isolation probe before writing", "windows/engine_config_api.py",
     "        build_engine(spec, _SilentMidiOut(), state_dir=None)\n", "        pass\n", [ECA]),
    ("M8", "restart_required gate removed", "windows/engine_config_api.py",
     "    if type_name not in LIVE_SWAPPABLE_TYPES:\n", "    if False:\n", [ECA]),
    ("M9", "build failure does not restore the file", "windows/engine_config_api.py",
     "            _restore_file(target, previous)\n", "", [ECA]),
    ("M10", "swap emits one MIDI message (equality detector must fire)", "windows/engines/registry.py",
     "        self._engines[index] = new\n",
     "        self._engines[index] = new\n        new._midi_out.control_change(0, 1, 1)\n", [ECA]),
    ("M11", "relay bind failure does not restore the previous relay", "windows/osc_relay.py",
     "                        self._restore(previous)\n                        raise OscRelayUpdateError(",
     "                        raise OscRelayUpdateError(", [AGR]),
    ("M12", "relay file replaced before the new relay starts", "windows/osc_relay.py",
     "                new_relay = None\n                if config.active:",
     "                new_relay = None\n                os.replace(tmp_path, self.config_path)\n                if config.active:", [AGR]),
    ("M13", "midi ports route opens an input port", "windows/ui_server.py",
     "                snapshot = get_port_snapshot()\n",
     "                snapshot = get_port_snapshot()\n                __import__(\"mido\").open_input(snapshot.input_names[0])\n", [AGR]),
    ("M14", "log ring not installed by win_recv", "windows/win_recv.py",
     "    log_ring = install_ring_handler()\n", "    log_ring = None\n", [AGR]),
    ("M15", "log tail route not loopback-only", "windows/ui_server.py",
     "        def get_log_tail() -> Response:\n            if not _remote_is_loopback():",
     "        def get_log_tail() -> Response:\n            if False:", [AGR]),
    ("M16", "ring keeps unbounded memory", "windows/log_ring.py",
     "deque(maxlen=capacity)", "deque()", [AGR]),
    ("M17", "tail accepts lines above 1000", "windows/ui_server.py",
     "1 <= int(raw) <= 1000", "1 <= int(raw) <= 100000", [AGR]),
    ("M18", "osc_sync default back to the placeholder path", "windows/engines/osc_sync.py",
     "            else default_osc_preset_path()",
     "            else \"C:/Users/USER\" \"NAME/OneDrive/Documents/Resolume Arena/Shortcuts/OSC/STEAMDECK V2.xml\"", [HOM]),
    ("M19", "stageflow default ignores the home", "windows/engines/stageflow_bridge.py",
     "    return Path.home().joinpath(*COMP_PATH_HOME_SUFFIX.split(\"/\"))",
     "    return Path(\"C:/\").joinpath(*COMP_PATH_HOME_SUFFIX.split(\"/\"))", [HOM]),
    ("M20", "factory osc_sync.json carries the key again", "config/engines.factory/osc_sync.json",
     "  \"enabled\": true,\n", "  \"enabled\": true,\n  \"osc_preset_path\": \"Z:/x.xml\",\n", [HOM]),
    ("M21", "api.md row for GET /api/logs/tail removed", "docs/api.md",
     "| GET | `/api/logs/tail` |", "| GOT | `/api/logs/tail` |", [UIS]),
    ("M22", "wiring: serve_forever gets no task queue", "windows/win_recv.py",
     "            receiver_tasks=receiver_tasks,\n        )\n\n    if args.tray:",
     "        )\n\n    if args.tray:", [AGR]),
]


def main() -> int:
    rows = []
    ok = True
    for mid, what, rel, old, new, modules in MUTANTS:
        with tempfile.TemporaryDirectory(prefix=f"sdauto-a2-{mid}-") as tmp:
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
    out = ROOT / "docs/sdauto-a2/mutant_sweep.json"
    out.write_text(json.dumps({"sweep_green": ok, "rows": rows}, indent=2) + "\n", encoding="utf-8")
    print("SWEEP GREEN" if ok else "SWEEP RED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
