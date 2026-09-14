#!/usr/bin/env python3
"""RG F3: real bridge from the run root, launcher argv (engines on, UI 7723), IAC monitor, POST /api/shutdown."""
import http.client, json, os, signal, socket, subprocess, sys, threading, time
from pathlib import Path
import rtmidi

ROOT = Path("/Users/viddyslap/Documents/project-workspaces/steam-deck-midi")
sys.path.insert(0, str(ROOT))
from protocol.messages import encode_action_event
PY = str(ROOT / ".venv/bin/python")
EV = Path("/tmp/sdcore2-gate/evidence")
DRY = "--dry-run" in sys.argv
TAG = ("dry" if DRY else "real") + ("-dummytray" if "--dummy-tray" in sys.argv else "")

# The launcher's own section snippet (file exists -> prints its selection, writes nothing)
sec = subprocess.run([PY, "-c", 'from pathlib import Path; from windows.bridge_settings import BridgeSettings; settings = BridgeSettings.load(Path("config/bridge.local.json")); settings.save_if_missing("macbook"); print(settings.preset_section or "")'],
                     cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
ARGV = ([ "--preset-section", sec] if sec else []) + ["--listen", "0.0.0.0:45123", "--map", "config/windows_midi_map.json",
        "--midi-port", "IAC Driver DECK_IN", "--feedback-port", "IAC Driver DECK_OUT", "--pulse-port", "IAC Driver PULSE_OUT",
        "--timeout", "2.0", "--ui-port", "7723"] + (["--dry-run"] if DRY else [])
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", BROWSER="/usr/bin/true")
if "--dummy-tray" in sys.argv: ENV["PYSTRAY_BACKEND"] = "dummy"

def ports_free():
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); t = socket.socket()
    t.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try: u.bind(("0.0.0.0", 45123)); t.bind(("127.0.0.1", 7723)); return True
    except OSError as e: print("  busy:", e); return False
    finally: u.close(); t.close()

def lsof(pid):
    return subprocess.run(["lsof", "-nP", "-a", "-p", str(pid), "-i"], capture_output=True, text=True).stdout.splitlines()[1:]

def post(results, key):
    t0 = time.monotonic()
    try:
        c = http.client.HTTPConnection("127.0.0.1", 7723, timeout=10)
        c.request("POST", "/api/shutdown"); r = c.getresponse()
        results[key] = (r.status, r.read().decode(), round(time.monotonic() - t0, 3), time.monotonic())
    except Exception as e:
        results[key] = ("EXC", repr(e), round(time.monotonic() - t0, 3), time.monotonic())

msgs = []; T0 = time.monotonic()
mon = rtmidi.MidiIn(); mon.ignore_types(True, True, True)
names = mon.get_ports(); mon.open_port(names.index("IAC Driver DECK_IN"))
mon.set_callback(lambda ev, _d: msgs.append((round(time.monotonic() - T0, 3), ev[0])))

def boot(n):
    assert ports_free(), "ports busy before boot"
    log = EV / f"f3-{TAG}-bridge{n}.log"
    cmd = [PY, "-B", "-u", "-m", "windows.win_recv", *ARGV]
    print(f"BOOT{n} cmd:", " ".join(repr(c) if " " in c else c for c in cmd))
    fh = open(log, "w")
    p = subprocess.Popen(cmd, cwd=ROOT, env=ENV, stdout=fh, stderr=subprocess.STDOUT)
    t = time.monotonic()
    while time.monotonic() - t < 20:
        if p.poll() is not None: break
        s = log.read_text(errors="replace")
        if "listening on udp://" in s and "mapping UI available" in s: break
        time.sleep(0.1)
    time.sleep(1.0)
    print(f"BOOT{n} alive={p.poll() is None} rc={p.poll()} boot_s={round(time.monotonic()-t,2)}")
    for l in lsof(p.pid): print("   lsof:", l)
    return p, log

def shutdown(p, log, n, hold_note):
    if hold_note:
        mark = len(msgs)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(encode_action_event(action="BTN_A", state="down", seq=900001, profile_name=None, profile_hash=None), ("127.0.0.1", 45123))
        time.sleep(0.3)
        print(f"  after BTN_A down (no up): IAC msgs {msgs[mark:]}")
    res = {}; mark = len(msgs); tpost = time.monotonic()
    th1 = threading.Thread(target=post, args=(res, "first")); th1.start()
    time.sleep(0.01)
    th2 = threading.Thread(target=post, args=(res, "second")); th2.start()
    try: rc = p.wait(timeout=5); exit_s = round(time.monotonic() - tpost, 3)
    except subprocess.TimeoutExpired:
        print("  NOT EXITED IN 5 s -> SIGTERM"); p.send_signal(signal.SIGTERM); rc = p.wait(timeout=10); exit_s = "timeout"
    th1.join(); th2.join(); time.sleep(0.5)
    print(f"  POST first: {res['first'][:3]}  second: {res['second'][:3]}")
    print(f"  process exit code={rc} seconds_from_POST={exit_s}")
    post_msgs = msgs[mark:]
    print(f"  IAC DECK_IN after POST ({len(post_msgs)} msgs): {post_msgs[:40]}")
    txt = log.read_text(errors="replace").splitlines()
    for l in txt:
        if any(k in l for k in ("Traceback", "timeout reached", "panic", "note_off", "shutdown", "stop", "Error", "error")): print("   log:", l)
    return rc

print("PRE ports free:", ports_free())
p, log = boot(1)
rc1 = shutdown(p, log, 1, hold_note=True)
t_free = time.monotonic(); free = ports_free(); print("AFTER1 ports free:", free)
p2, log2 = boot(2)
bound2 = [l for l in lsof(p2.pid)]
print("SECOND bridge bound:", any("45123" in l for l in bound2) and any("7723" in l for l in bound2))
print("SECOND log MIDI ports:", [l for l in log2.read_text(errors="replace").splitlines() if "MIDI" in l and "port" in l])
rc2 = shutdown(p2, log2, 2, hold_note=False)
print("FINAL ports free:", ports_free(), "rc1", rc1, "rc2", rc2)
mon.close_port()
