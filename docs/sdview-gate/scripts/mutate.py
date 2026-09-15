"""sdview gate mutations: each in its own git-archive scratch copy; RED, restore, GREEN.
Usage: python3 mutate.py <run_root> <scratch_root> <out.json>"""
import json, os, shutil, subprocess, sys, time, signal
RUN, SCR, OUT = sys.argv[1:4]
PY = f"{RUN}/.venv/bin/python"
NODE = "/opt/homebrew/bin/node"
HEAD = subprocess.run(["git", "-C", RUN, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
env = {**os.environ, "TMPDIR": f"{SCR}/tmp", "PYSTRAY_BACKEND": "dummy", "BROWSER": "/usr/bin/true"}
os.makedirs(f"{SCR}/tmp", exist_ok=True)
rows = []

def copy(name):
    d = f"{SCR}/{name}"
    shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    subprocess.run(f"git -C {RUN} archive {HEAD} | tar -x -C {d}", shell=True, check=True)
    return d

def run(cmd, cwd):
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=600)
    return p.returncode, (p.stdout + p.stderr)

def mutate(path, old, new):
    s = open(path, encoding="utf-8").read()
    assert s.count(old) == 1, (path, old, s.count(old))
    open(path, "w", encoding="utf-8").write(s.replace(old, new))

def case(id_, desc, rel, old, new, cmd, red_marker):
    d = copy(id_)
    target = f"{d}/{rel}"
    pristine = open(target, "rb").read()
    mutate(target, old, new)
    red_code, red_out = run(cmd, d)
    open(f"{SCR}/{id_}-red.log", "w").write(red_out)
    open(target, "wb").write(pristine)
    blob = subprocess.run(["git", "-C", RUN, "show", f"{HEAD}:{rel}"], capture_output=True, check=True).stdout
    restored_equal = open(target, "rb").read() == blob
    green_code, green_out = run(cmd, d)
    open(f"{SCR}/{id_}-green.log", "w").write(green_out)
    ok = red_code != 0 and red_marker in red_out and restored_equal and green_code == 0
    rows.append({"id": id_, "mutation": desc, "file": rel, "command": " ".join(cmd), "red_exit": red_code, "red_marker": red_marker,
                 "red_marker_found": red_marker in red_out, "restored_equals_head_blob": restored_equal, "green_exit": green_code, "pass": ok,
                 "red_log": f"{SCR}/{id_}-red.log", "green_log": f"{SCR}/{id_}-green.log"})
    print("PASS" if ok else "FAIL", id_, "red", red_code, "marker", red_marker in red_out, "green", green_code)

case("a-map-id", "remove BTN_A_LAYER_2 from btn_a layer_2 in controller_map.json",
     "windows/static/controller/controller_map.json", '"layer_2": [\n          "BTN_A_LAYER_2"\n        ]', '"layer_2": [\n        ]',
     [PY, "-B", "-m", "unittest", "-v", "tests.test_controller_map"], "test_every_catalog_action_appears_exactly_once")
case("b-put-skips-validation", "edit_mapping writes the file directly instead of through _write_preset (no load_midi_map validation)",
     "windows/ui_server.py", "self._write_preset(active, content, before_replace=guard_conflicts)",
     "guard_conflicts(); active.write_text(content, encoding=\"utf-8\")",
     [PY, "-B", "-m", "unittest", "-v", "tests.test_controller_routes"], "test_bad_specs_return_parser_error_and_preserve_bytes_even_when_forced")
case("c-clear-noop", "drill-in Clear mapping no longer commits null",
     "windows/static/controller/controller_view.js", "commit(action, null); toast(`${action} cleared`);", "toast(`${action} cleared`);",
     [NODE, "tests/ui_controller_check.cjs"], "AssertionError")
case("d-api-row", "remove the DELETE /api/mappings/<action_id> row from docs/api.md",
     "docs/api.md", "| DELETE | `/api/mappings/<action_id>` | Clear one section mapping idempotently; optional section and force=1 for conflicts. |\n", "",
     [PY, "-B", "-m", "unittest", "-v", "tests.test_ui_server.BridgeSettingsApiTests.test_api_inventory_matches_registered_method_paths"], "AssertionError")
case("e-default-list-node", "default sub-view becomes List when no preference is stored",
     "windows/static/controller/controller_view.js", "view = localStorage.getItem(STORAGE_KEY) === 'list' ? 'list' : 'controller'; } catch (_) { view = 'controller'; }",
     "view = localStorage.getItem(STORAGE_KEY) === 'controller' ? 'controller' : 'list'; } catch (_) { view = 'list'; }",
     [NODE, "tests/ui_controller_check.cjs"], "Controller is the default front door")

# e in a real browser: boot a bridge from the mutant copy, frontdoor RED; restore the file in place, frontdoor GREEN
d = copy("e-default-list-browser")
for f in ("EDM Show.json", "PTZ.json", "default.json"):
    shutil.copy(f"{RUN}/.showready/fixtures/mac/presets/{f}", f"{d}/config/presets/{f}"); os.chmod(f"{d}/config/presets/{f}", 0o644)
open(f"{d}/config/presets/.active", "w").write("EDM Show.json")
js = f"{d}/windows/static/controller/controller_view.js"
pristine = open(js, "rb").read()
mutate(js, "view = localStorage.getItem(STORAGE_KEY) === 'list' ? 'list' : 'controller'; } catch (_) { view = 'controller'; }",
       "view = localStorage.getItem(STORAGE_KEY) === 'controller' ? 'controller' : 'list'; } catch (_) { view = 'list'; }")
argv = [PY, "-u", "-m", "windows.win_recv", "--listen", "127.0.0.1:47794", "--map", "config/windows_midi_map.json", "--preset-section", "windows",
        "--dry-run", "--no-engines", "--no-pulse", "--no-osc-relay", "--ui-port", "17794", "--timeout", "2.0"]
bridge = subprocess.Popen(argv, cwd=d, env=env, stdout=open(f"{SCR}/e-bridge.log", "w"), stderr=subprocess.STDOUT)
time.sleep(5)
gate = f"{RUN}/docs/sdview-gate/scripts/ui_gate.cjs"
r1 = subprocess.run([NODE, gate, "frontdoor", "17794", d, f"{SCR}/e-browser-red"], capture_output=True, text=True)
open(f"{SCR}/e-browser-red.log", "w").write(r1.stdout + r1.stderr)
open(js, "wb").write(pristine)
r2 = subprocess.run([NODE, gate, "frontdoor", "17794", d, f"{SCR}/e-browser-green"], capture_output=True, text=True)
open(f"{SCR}/e-browser-green.log", "w").write(r2.stdout + r2.stderr)
bridge.send_signal(signal.SIGTERM)
try: bridge.wait(timeout=15)
except subprocess.TimeoutExpired: bridge.kill(); bridge.wait()
try: os.kill(bridge.pid, 0); gone = False
except ProcessLookupError: gone = True
ok = r1.returncode != 0 and "FAIL a.1440x900.opens-on-controller" in r1.stdout and r2.returncode == 0 and gone
rows.append({"id": "e-default-list-browser", "mutation": "same mutation, served by a real bridge from the mutant copy; ui_gate.cjs frontdoor in Chromium",
             "command": f"node {gate} frontdoor 17794 {d} <out>", "bridge_argv": " ".join(argv), "bridge_pid": bridge.pid, "bridge_gone": gone,
             "red_exit": r1.returncode, "red_marker": "FAIL a.1440x900.opens-on-controller", "red_marker_found": "FAIL a.1440x900.opens-on-controller" in r1.stdout,
             "restored_equals_head_blob": open(js, "rb").read() == subprocess.run(["git", "-C", RUN, "show", f"{HEAD}:windows/static/controller/controller_view.js"], capture_output=True).stdout,
             "green_exit": r2.returncode, "pass": ok, "red_log": f"{SCR}/e-browser-red.log", "green_log": f"{SCR}/e-browser-green.log"})
print("PASS" if ok else "FAIL", "e-default-list-browser red", r1.returncode, "green", r2.returncode, "bridge gone", gone)
json.dump({"head": HEAD, "rows": rows, "all_pass": all(r["pass"] for r in rows)}, open(OUT, "w"), indent=2)
sys.exit(0 if all(r["pass"] for r in rows) else 1)
