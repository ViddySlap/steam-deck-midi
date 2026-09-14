#!/usr/bin/env python3
"""RG F1 arms: git-exported trees, no local files, launcher argv + dry-run flags. SIGTERM only."""
import hashlib, json, os, shutil, signal, socket, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT = Path("/Users/viddyslap/Documents/project-workspaces/steam-deck-midi")
PY = str(ROOT / ".venv/bin/python")
BASE = Path("/tmp/sdcore2-gate/arms")
LAUNCHER = ["--listen", "0.0.0.0:45123", "--map", "config/windows_midi_map.json",
            "--midi-port", "IAC Driver DECK_IN", "--feedback-port", "IAC Driver DECK_OUT",
            "--pulse-port", "IAC Driver PULSE_OUT", "--timeout", "2.0", "--ui-port", "7723"]
DRY = ["--dry-run", "--no-ui", "--no-engines", "--no-pulse", "--no-osc-relay"]
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", BROWSER="/usr/bin/true")

def ports_free():
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); t = socket.socket()
    t.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        u.bind(("0.0.0.0", 45123)); t.bind(("127.0.0.1", 7723)); return True
    except OSError as e:
        print("  PORT BUSY:", e); return False
    finally:
        u.close(); t.close()

def export(rev, name):
    d = BASE / name
    if d.exists(): shutil.rmtree(d)
    d.mkdir(parents=True)
    subprocess.run(f"git -C '{ROOT}' archive {rev} | tar -x -C '{d}'", shell=True, check=True)
    return d

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None

def lsof(pid):
    r = subprocess.run(["lsof", "-nP", "-a", "-p", str(pid), "-i"], capture_output=True, text=True)
    return [l for l in r.stdout.splitlines()[1:]]

def run_arm(name, tree, argv, *, ui=False, expect_boot=True, wait=8.0):
    print(f"== ARM {name}: tree={tree}")
    assert ports_free(), "ports not free before arm"
    loc = tree / "config/bridge.local.json"; act = tree / "config/presets/.active"
    print(f"  pre: bridge.local.json={'present sha '+sha(loc) if loc.exists() else 'ABSENT'} .active={act.read_text().strip() if act.exists() else 'ABSENT'}")
    cmd = [PY, "-B", "-u", "-m", "windows.win_recv", *argv]
    print("  cmd:", " ".join(repr(c) if " " in c else c for c in cmd))
    log = BASE / f"{name}.log"
    with open(log, "w") as fh:
        p = subprocess.Popen(cmd, cwd=tree, env=ENV, stdout=fh, stderr=subprocess.STDOUT)
    t0 = time.time(); booted = False; settings = None
    while time.time() - t0 < wait:
        if p.poll() is not None: break
        txt = log.read_text(errors="replace")
        if "listening on udp://" in txt and (not ui or "mapping UI available" in txt):
            booted = True; break
        time.sleep(0.1)
    if booted:
        time.sleep(0.5)
        socks = lsof(p.pid)
        print("  lsof(child):"); [print("   ", l) for l in socks]
        if ui:
            with urllib.request.urlopen("http://127.0.0.1:7723/api/settings", timeout=5) as r:
                settings = json.loads(r.read()); print("  GET /api/settings", r.status, json.dumps(settings))
        p.send_signal(signal.SIGTERM)
        try: rc = p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            print("  SIGTERM did not stop in 10s; SIGKILL"); p.kill(); rc = p.wait()
    else:
        try: rc = p.wait(timeout=2)
        except subprocess.TimeoutExpired:
            p.send_signal(signal.SIGTERM); rc = p.wait(timeout=10)
    txt = log.read_text(errors="replace")
    listen = [l for l in txt.splitlines() if "listening on" in l or "mapping UI available" in l or "error" in l.lower() or "created bridge settings" in l or "preset" in l.lower()]
    print(f"  booted={booted} exit={rc}")
    for l in listen[:12]: print("   log:", l)
    time.sleep(0.3)
    free = ports_free(); print(f"  after: 45123/7723 free={free}")
    print(f"  post: bridge.local.json={('present bytes '+repr(loc.read_bytes())+' sha '+sha(loc)) if loc.exists() else 'ABSENT'}")
    return dict(name=name, booted=booted, exit=rc, settings=settings, local=loc.read_bytes() if loc.exists() else None, free=free)

res = {}
BASE.mkdir(parents=True, exist_ok=True)
# A1 v0.4.9
t = export("5d778eb", "A1-v049"); res["A1"] = run_arm("A1-v049", t, LAUNCHER + DRY)
# A2 HEAD fresh pull, --no-ui
t = export("HEAD", "A2-head-fresh"); res["A2"] = run_arm("A2-head-fresh-noui", t, LAUNCHER + DRY)
# A2b same arm shape WITHOUT --no-ui (fresh export)
t = export("HEAD", "A2b-head-fresh-ui"); res["A2b"] = run_arm("A2b-head-fresh-ui", t, LAUNCHER + [f for f in DRY if f != "--no-ui"], ui=True)
# A3 sectioned PTZ active, no local
t = export("HEAD", "A3-head-ptz"); shutil.copyfile(ROOT / "config/presets/PTZ.json", t / "config/presets/PTZ.json")
(t / "config/presets/.active").write_text("PTZ.json")
res["A3"] = run_arm("A3-head-ptz-noui", t, LAUNCHER + DRY)
# A3b same, with UI, fresh tree, to read the selected section over HTTP
t = export("HEAD", "A3b-head-ptz-ui"); shutil.copyfile(ROOT / "config/presets/PTZ.json", t / "config/presets/PTZ.json")
(t / "config/presets/.active").write_text("PTZ.json")
res["A3b"] = run_arm("A3b-head-ptz-ui", t, LAUNCHER + [f for f in DRY if f != "--no-ui"], ui=True)
# A4 existing windows local, sectioned PTZ active
for nm, ui in (("A4-head-windows-noui", False), ("A4b-head-windows-ui", True)):
    t = export("HEAD", nm); shutil.copyfile(ROOT / "config/presets/PTZ.json", t / "config/presets/PTZ.json")
    (t / "config/presets/.active").write_text("PTZ.json")
    loc = t / "config/bridge.local.json"; loc.write_text('{"preset_section": "windows"}\n'); b0 = loc.read_bytes()
    argv = LAUNCHER + (DRY if not ui else [f for f in DRY if f != "--no-ui"])
    r = run_arm(nm, t, argv, ui=ui); r["byte_identical"] = r["local"] == b0
    print(f"  byte_identical={r['byte_identical']}"); res[nm] = r
# A5 launcher section snippet against a no-local-file HEAD tree
t = export("HEAD", "A5-snippet")
launcher = (t / "scripts/mac/run_receiver.command").read_text()
line = [l for l in launcher.splitlines() if l.startswith("PRESET_SECTION=$(python -c")][0]
snippet = line[len("PRESET_SECTION=$("):-len(") || exit 1")]
print("== ARM A5 snippet (extracted verbatim from run_receiver.command):", snippet)
print("  pre: bridge.local.json", "present" if (t/"config/bridge.local.json").exists() else "ABSENT")
r = subprocess.run(["bash", "-c", f"source '{ROOT}/.venv/bin/activate' && cd '{t}' && PRESET_SECTION=$({snippet}) || exit 1; echo \"PRESET_SECTION=$PRESET_SECTION\""], capture_output=True, text=True, env=ENV)
print("  exit", r.returncode, r.stdout.strip(), r.stderr.strip())
loc = t / "config/bridge.local.json"
print("  post: bridge.local.json bytes", repr(loc.read_bytes()) if loc.exists() else "ABSENT")
# A5b the launcher's own resulting argv on that flat-default tree boots
res["A5b"] = run_arm("A5b-snippet-then-boot", t, ["--preset-section", "macbook"] + LAUNCHER + DRY)
print("SUMMARY", json.dumps({k: {kk: (vv.decode() if isinstance(vv, bytes) else vv) for kk, vv in v.items()} for k, v in res.items()}, indent=1))
