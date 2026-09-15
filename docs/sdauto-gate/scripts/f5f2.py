"""sdauto gate step 3: F5 and F2 on the Mac, BASE 70cebd0 vs HEAD.

  .venv/bin/python -B /tmp/sdauto-gate/s3/f5f2.py --out /tmp/sdauto-gate/s3/run

Each arm: git archive <rev> into scratch, Mac fixture presets copied (EDM Show active), the
Mac launcher argv (scripts/mac/run_receiver.command) with loopback non-default --listen and
--ui-port, plus --dry-run and the load rules' --no-engines --no-pulse --no-osc-relay.
BROWSER=/usr/bin/true (or a recorder), PYSTRAY_BACKEND NOT set. SIGINT disposition reset to
default in the child (preexec). Writes <out>/f5f2.json.
"""
import argparse, json, os, re, shutil, signal, socket, subprocess, sys, time, urllib.request, urllib.error
from pathlib import Path

ROOT = Path("/Users/viddyslap/Documents/project-workspaces/steam-deck-midi")
PY = str(ROOT / ".venv/bin/python")
HERE = Path(__file__).resolve().parent
REVS = {"BASE": "70cebd0b6baed2ece86a2d218843e02b6298789d", "HEAD": "a8fec2ad635e141b0634dc9a51c5442dad9fd966"}
CRASH_DIR = Path.home() / "Library/Logs/DiagnosticReports"


def free(kind=socket.SOCK_STREAM):
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def crash_reports():
    return sorted(p.name for p in CRASH_DIR.iterdir() if p.name.startswith("Python-"))


def load_check():
    pg = subprocess.run(["pgrep", "-f", "while True: pass"], capture_output=True, text=True)
    load = subprocess.run(["sysctl", "-n", "vm.loadavg"], capture_output=True, text=True).stdout.strip()
    ps = subprocess.run(["ps", "-A", "-o", "command="], capture_output=True, text=True).stdout.splitlines()
    foreign = []
    for line in ps:
        if "codex exec" in line:
            continue
        parts = line.split()
        if not parts:
            continue
        c = parts[0].rsplit("/", 1)[-1]
        if c not in ("zsh", "bash", "sh", "node"):
            continue
        s = next((a for a in parts[1:] if not a.startswith("-")), "")
        if s.startswith("/Users/viddyslap/Documents/project-workspaces/local-LLM-h14/engine/tests/") or s.endswith("run-all.sh"):
            foreign.append(line)
    empty = pg.returncode == 1 and not pg.stdout.strip() and not pg.stderr.strip()
    return {"t": time.strftime("%H:%M:%S"), "pgrep_exit": pg.returncode, "pgrep_stdout": pg.stdout.strip(), "pgrep_empty": empty,
            "load1": load.strip("{} ").split()[0] if load else None, "foreign_lines": len(foreign), "foreign": foreign}


def tree(rev, out):
    t = out / f"tree-{rev[:7]}"
    if not t.exists():
        t.mkdir(parents=True)
        a = subprocess.run(f"git -C {ROOT} archive {rev} | tar -x -C {t}", shell=True)
        assert a.returncode == 0
        for src in (ROOT / ".showready/fixtures/mac/presets").glob("*.json"):
            shutil.copy2(src, t / "config/presets" / src.name)
        (t / "config/presets/.active").write_text("EDM Show.json")
    return t


def spawn(t, out, tag, browser="/usr/bin/true", extra=()):
    ui, udp = free(), free(socket.SOCK_DGRAM)
    env = {k: v for k, v in os.environ.items() if k != "PYSTRAY_BACKEND"}
    env["BROWSER"] = browser
    argv = [PY, "-B", "-u", "-m", "windows.win_recv", "--preset-section", "macbook", "--listen", f"127.0.0.1:{udp}",
            "--map", "config/windows_midi_map.json", "--midi-port", "IAC Driver DECK_IN", "--feedback-port", "IAC Driver DECK_OUT",
            "--pulse-port", "IAC Driver PULSE_OUT", "--timeout", "2.0", "--ui-port", str(ui),
            "--dry-run", "--no-engines", "--no-pulse", "--no-osc-relay", *extra]
    log = open(out / f"{tag}.log", "w")
    p = subprocess.Popen(argv, cwd=t, env=env, stdout=log, stderr=subprocess.STDOUT,
                         preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))
    base = f"http://127.0.0.1:{ui}"
    up = None
    for _ in range(200):
        try:
            with urllib.request.urlopen(base + "/api/settings", timeout=0.5) as r:
                r.read()
            up = time.time()
            break
        except Exception:
            time.sleep(0.05)
    return p, log, base, {"argv": argv, "pid": p.pid, "ui_port": ui, "udp_port": udp, "ui_up": up is not None,
                          "pystray_backend_env": env.get("PYSTRAY_BACKEND"), "BROWSER": browser}


def windows_of(pid):
    r = subprocess.run([str(HERE / "statusitems"), str(pid)], capture_output=True, text=True)
    m = re.search(r"PID_WINDOWS (\d+) STATUS_LAYER_25 (\d+)", r.stdout)
    return {"pid_windows": int(m.group(1)), "status_layer_25": int(m.group(2)), "lines": r.stdout.strip().splitlines()[-4:]}


def wait_exit(p, seconds):
    t0 = time.time()
    while time.time() - t0 < seconds:
        if p.poll() is not None:
            return p.returncode, round(time.time() - t0, 3)
        time.sleep(0.05)
    return None, None


def finish(p, log):
    if p.poll() is None:
        p.send_signal(signal.SIGTERM)
        code, _ = wait_exit(p, 5)
        if code is None:
            p.kill()
            p.wait()
    log.close()
    gone = subprocess.run(["/bin/ps", "-p", str(p.pid)], capture_output=True).returncode == 1
    return {"final_returncode": p.returncode, "pid_gone": gone}


def arm_shutdown(rev_name, out, n):
    t = tree(REVS[rev_name], out)
    before = crash_reports()
    p, log, base, meta = spawn(t, out, f"{rev_name}-shutdown{n}")
    time.sleep(3)
    meta["windows_while_running"] = windows_of(p.pid)
    req = urllib.request.Request(base + "/api/shutdown", data=b"{}", method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            meta["shutdown_status"] = r.status
    except urllib.error.HTTPError as e:
        meta["shutdown_status"] = e.code
    code, secs = wait_exit(p, 10)
    meta["exit_code_from_wait"] = code
    meta["exit_seconds"] = secs
    meta.update(finish(p, log))
    time.sleep(2)
    meta["new_crash_reports"] = sorted(set(crash_reports()) - set(before))
    return meta


def arm_f2(rev_name, out):
    t = tree(REVS[rev_name], out)
    p, log, base, meta = spawn(t, out, f"{rev_name}-f2")
    time.sleep(2)
    meta["load_before"] = load_check()
    meta["windows_while_running"] = windows_of(p.pid)
    cpu0 = subprocess.run(["ps", "-o", "time=", "-p", str(p.pid)], capture_output=True, text=True).stdout.strip()
    samples = []
    t0 = time.time()
    for _ in range(30):
        time.sleep(1)
        samples.append(float(subprocess.run(["ps", "-o", "%cpu=", "-p", str(p.pid)], capture_output=True, text=True).stdout.strip() or "nan"))
    wall = time.time() - t0
    cpu1 = subprocess.run(["ps", "-o", "time=", "-p", str(p.pid)], capture_output=True, text=True).stdout.strip()

    def secs(s):
        parts = [float(x) for x in s.split(":")]
        return sum(v * 60 ** i for i, v in enumerate(reversed(parts)))
    meta["load_after"] = load_check()
    meta["cpu"] = {"ps_time_before": cpu0, "ps_time_after": cpu1, "cpu_seconds": round(secs(cpu1) - secs(cpu0), 2),
                   "wall_seconds": round(wall, 2), "pct_one_core": round(100 * (secs(cpu1) - secs(cpu0)) / wall, 1),
                   "ps_pct_samples": samples, "ps_pct_mean": round(sum(samples) / len(samples), 1)}
    before = crash_reports()
    p.send_signal(signal.SIGINT)
    code, s = wait_exit(p, 5)
    meta["sigint"] = {"exited_within_5s": code is not None, "exit_code": code, "seconds": s}
    meta.update(finish(p, log))
    time.sleep(2)
    meta["new_crash_reports"] = sorted(set(crash_reports()) - set(before))
    meta["load_valid"] = meta["load_before"]["pgrep_empty"] and meta["load_after"]["pgrep_empty"] and \
        meta["load_before"]["foreign_lines"] == 0 and meta["load_after"]["foreign_lines"] == 0
    return meta


def arm_browser(out, flag):
    t = tree(REVS["HEAD"], out)
    rec = out / f"browser-rec-{'flag' if flag else 'noflag'}.txt"
    script = out / f"rec-{'flag' if flag else 'noflag'}.sh"
    script.write_text(f"#!/bin/sh\necho \"$@\" >> '{rec}'\nexit 0\n")
    script.chmod(0o755)
    p, log, base, meta = spawn(t, out, f"HEAD-browser-{'flag' if flag else 'noflag'}", browser=str(script),
                               extra=("--no-browser",) if flag else ())
    time.sleep(5)
    p.send_signal(signal.SIGINT)
    code, _ = wait_exit(p, 5)
    meta["sigint_exit"] = code
    meta.update(finish(p, log))
    meta["records"] = rec.read_text().splitlines() if rec.exists() else []
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    res = {"crash_reports_start": len(crash_reports())}
    res["HEAD-shutdown1"] = arm_shutdown("HEAD", out, 1)
    res["HEAD-shutdown2"] = arm_shutdown("HEAD", out, 2)
    for rev in ("HEAD", "BASE"):
        for attempt in range(1, 4):
            m = arm_f2(rev, out)
            res[f"{rev}-f2-try{attempt}"] = m
            if m["load_valid"]:
                break
            time.sleep(30)
    res["HEAD-browser-flag"] = arm_browser(out, True)
    res["HEAD-browser-noflag"] = arm_browser(out, False)
    res["crash_reports_end"] = len(crash_reports())
    (out / "f5f2.json").write_text(json.dumps(res, indent=2))
    for k, v in res.items():
        if isinstance(v, dict):
            print(k, json.dumps({x: v.get(x) for x in ("shutdown_status", "exit_code_from_wait", "exit_seconds", "new_crash_reports", "windows_while_running",
                                                      "cpu", "sigint", "load_valid", "records", "sigint_exit", "pid_gone") if x in v})[:700])
        else:
            print(k, v)


if __name__ == "__main__":
    main()
