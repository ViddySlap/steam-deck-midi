"""sdauto gate step 5: boot a scratch UI bridge per arm, run header_gate.cjs, prove the bridge PID gone.

  .venv/bin/python -B docs/sdauto-gate/scripts/header_gate.py --out /tmp/sdauto-gate/s5 [--engines-tree DIR --engines-state JSON --osc-ports A,B --rest-port N]

Arms: BASE 70cebd0 (header), HEAD (header + GET /api/version), and, when --engines-tree is given,
HEAD engines ON from that loopback-rewritten tree with the autopilot state file written from
--engines-state (engines PNG). Engines-off arms: --dry-run --no-engines --no-pulse --no-osc-relay
--no-browser (BASE has no --no-browser; BROWSER=/usr/bin/true covers it), PYSTRAY_BACKEND=dummy.
"""
import argparse, json, os, re, shutil, signal, socket, subprocess, sys, threading, time, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CHROMIUM = "/Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell"
REVS = {"BASE": "70cebd0b6baed2ece86a2d218843e02b6298789d", "HEAD": "a8fec2ad635e141b0634dc9a51c5442dad9fd966"}


def free(kind=socket.SOCK_STREAM):
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return r.status, r.headers.get("content-type"), json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("content-type"), None


def boot_and_measure(out, tag, cwd, argv_tail, mode, env_extra=None):
    ui, udp = free(), free(socket.SOCK_DGRAM)
    env = {**os.environ, "PYSTRAY_BACKEND": "dummy", "BROWSER": "/usr/bin/true", "PYTHONDONTWRITEBYTECODE": "1", **(env_extra or {})}
    argv = [str(ROOT / ".venv/bin/python"), "-B", "-u", "-m", "windows.win_recv", "--listen", f"127.0.0.1:{udp}", "--ui-port", str(ui), *argv_tail]
    log = open(out / f"{tag}-bridge.log", "w")
    p = subprocess.Popen(argv, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
    receipt = {"tag": tag, "argv": argv, "cwd": str(cwd), "pid": p.pid}
    url = f"http://127.0.0.1:{ui}"
    try:
        for _ in range(200):
            if p.poll() is not None:
                raise RuntimeError("bridge exited early")
            try:
                with urllib.request.urlopen(url + "/api/settings", timeout=0.5):
                    break
            except OSError:
                time.sleep(0.1)
        receipt["api_version"] = get(url + "/api/version")
        if mode == "engines":
            receipt["api_engines_autopilot"] = next(e for e in get(url + "/api/engines")[2]["engines"] if e["type"] == "autopilot")
        r = subprocess.run(["node", str(Path(__file__).with_name("header_gate.cjs")), url, CHROMIUM, str(out), tag, mode],
                           capture_output=True, text=True, timeout=180)
        receipt["node_exit"] = r.returncode
        receipt["node_stderr"] = r.stderr[-800:]
        receipt["measure"] = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else None
    finally:
        if p.poll() is None:
            p.send_signal(signal.SIGTERM)
        try:
            p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
        log.close()
        try:
            os.kill(p.pid, 0)
            receipt["pid_gone"] = False
        except ProcessLookupError:
            receipt["pid_gone"] = True
    return receipt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--engines-tree")
    ap.add_argument("--engines-state")
    ap.add_argument("--osc-ports", default="")
    ap.add_argument("--rest-port", type=int)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    receipts = {}
    for name in ("BASE", "HEAD"):
        tree = out / f"tree-{name}"
        if not tree.exists():
            tree.mkdir()
            assert subprocess.run(f"git -C '{ROOT}' archive {REVS[name]} windows protocol config | tar -x -C '{tree}'", shell=True).returncode == 0
            for src in (ROOT / ".showready/fixtures/mac/presets").glob("*.json"):
                shutil.copyfile(src, tree / "config/presets" / src.name)
            (tree / "config/presets/.active").write_text("EDM Show.json")
        tail = ["--map", "config/windows_midi_map.json", "--preset-section", "windows", "--dry-run", "--no-engines", "--no-pulse", "--no-osc-relay"]
        if name == "HEAD":
            tail.append("--no-browser")
        receipts[name] = boot_and_measure(out, "before" if name == "BASE" else "after", tree, tail, "header")
    if a.engines_tree:
        socks = []
        for port in [int(x) for x in a.osc_ports.split(",") if x]:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.bind(("127.0.0.1", port))
            socks.append(s)
        if a.rest_port:
            rs = socket.socket()
            rs.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            rs.bind(("127.0.0.1", a.rest_port))
            rs.listen(8)
            socks.append(rs)
        cfg = Path(a.engines_tree)
        state = cfg / "state/autopilot_channels.local.json"
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps(json.load(open(a.engines_state))), encoding="utf-8")
        tail = ["--map", str(cfg / "windows_midi_map.json"), "--preset-section", "windows", "--dry-run", "--no-pulse", "--no-browser",
                "--osc-relay-config", str(cfg / "osc_relay.json")]
        receipts["HEAD-engines"] = boot_and_measure(out, "after", ROOT, tail, "engines")
        for s in socks:
            s.close()
    (out / "header_gate.json").write_text(json.dumps(receipts, indent=2))
    b, h = receipts["BASE"]["measure"], receipts["HEAD"]["measure"]
    ok = (h and h["controller"]["one_row"] and h["list"]["one_row"] and "0.5.0" in (h["controller"]["version_text"] or "")
          and receipts["HEAD"]["api_version"][0] == 200 and receipts["HEAD"]["api_version"][2]["version"] == "0.5.0"
          and receipts["HEAD"]["api_version"][2]["frozen"] is False and all(r["pid_gone"] for r in receipts.values()))
    fires = bool(b) and not b["controller"]["one_row"]
    print("HEAD one row controller/list:", h and (h["controller"]["one_row"], h["list"]["one_row"]), "version:", h and h["controller"]["version_text"],
          "api:", receipts["HEAD"]["api_version"], "| BASE one row (detector must fire, expect False):", b and b["controller"]["one_row"],
          "| pids gone:", {k: r["pid_gone"] for k, r in receipts.items()})
    print("STEP5", "PASS" if ok and fires else "FAIL")
    return 0 if ok and fires else 1


if __name__ == "__main__":
    sys.exit(main())
