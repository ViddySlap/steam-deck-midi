"""Real-HTTP end-to-end check of the A2 routes against a live dry-run bridge.

Usage (run root): .venv/bin/python -B docs/sdauto-a2/e2e_http.py --out <dir>
Builds a scratch config tree (map, default preset, actions, macro library,
empty engines/, engines.factory/ copied with EVERY host/IP/port/base_url
rewritten to loopback; refuses to start if any non-loopback IPv4 literal
remains), starts `python -m windows.win_recv --dry-run` with engines ON,
--no-pulse, non-default --listen/--ui-port, PYSTRAY_BACKEND=dummy and
BROWSER=/usr/bin/true, drives the six routes over HTTP, POSTs /api/shutdown,
and proves the process is gone. Writes <out>/e2e.json.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def free_port(kind=socket.SOCK_STREAM) -> int:
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def call(base, method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"null")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    cfg = out / "config"
    (cfg / "engines").mkdir(parents=True)
    (cfg / "engines.factory").mkdir()
    (cfg / "presets").mkdir()
    for name in ("windows_midi_map.json", "actions.yaml", "macro_library.json"):
        shutil.copy2(ROOT / "config" / name, cfg / name)
    shutil.copy2(ROOT / "config/presets/default.json", cfg / "presets/default.json")

    sink = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sink.bind(("127.0.0.1", 0))
    sink.settimeout(3.0)
    sink_port = sink.getsockname()[1]
    rest = "http://127.0.0.1:%d" % free_port()

    def loopback(node):
        if isinstance(node, dict):
            res = {}
            for key, value in node.items():
                if key in ("host", "camera_nic_ip"):
                    res[key] = "127.0.0.1"
                elif key in ("port", "visca_port") and isinstance(value, int):
                    res[key] = sink_port
                elif key == "base_url":
                    res[key] = rest
                elif key == "cameras" and isinstance(value, dict):
                    res[key] = {k: "127.0.0.1" for k in value}
                else:
                    res[key] = loopback(value)
            return res
        if isinstance(node, list):
            return [loopback(v) for v in node]
        return node

    for src in sorted((ROOT / "config/engines.factory").glob("*.json")):
        text = json.dumps(loopback(json.loads(src.read_text(encoding="utf-8"))), indent=2)
        (cfg / "engines.factory" / src.name).write_text(text, encoding="utf-8")
    relay_listen = free_port(socket.SOCK_DGRAM)
    (cfg / "osc_relay.json").write_text(json.dumps(
        {"enabled": True, "listen": "127.0.0.1:%d" % relay_listen, "destinations": ["127.0.0.1:%d" % free_port(socket.SOCK_DGRAM)]}),
        encoding="utf-8")
    for path in cfg.rglob("*"):
        if path.is_file() and path.suffix in (".json", ".yaml"):
            foreign = [ip for ip in re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", path.read_text(encoding="utf-8"))
                       if ip != "127.0.0.1"]
            if foreign:
                print(f"REFUSING: {path} still names {sorted(set(foreign))}")
                return 2

    ui_port = free_port()
    listen = free_port(socket.SOCK_DGRAM)
    env = {**os.environ, "PYSTRAY_BACKEND": "dummy", "BROWSER": "/usr/bin/true"}
    log = open(out / "bridge.log", "w", encoding="utf-8")
    proc = subprocess.Popen(
        [str(ROOT / ".venv/bin/python"), "-B", "-m", "windows.win_recv", "--map", str(cfg / "windows_midi_map.json"),
         "--dry-run", "--no-pulse", "--listen", "127.0.0.1:%d" % listen, "--ui-port", str(ui_port)],
        cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    base = "http://127.0.0.1:%d" % ui_port
    results = {"pid": proc.pid, "ui_port": ui_port, "listen": listen, "steps": []}

    def step(name, status, body, ok):
        results["steps"].append({"name": name, "status": status, "ok": bool(ok), "body": body})
        print(name, status, "OK" if ok else "FAIL", flush=True)

    try:
        for _ in range(100):
            try:
                if call(base, "GET", "/api/engines")[0] == 200:
                    break
            except (urllib.error.URLError, ConnectionError):
                time.sleep(0.1)
        status, body = call(base, "GET", "/api/engines/autopilot/config")
        step("GET autopilot config", status, {k: body.get(k) for k in ("source", "loaded", "live_swappable")},
             status == 200 and body["source"] == "factory" and body["loaded"])
        spec = {**body["spec"], "update_hz": 20}
        status, body = call(base, "PUT", "/api/engines/autopilot/config", spec)
        on_disk = json.loads((cfg / "engines/autopilot.json").read_text(encoding="utf-8")) if (cfg / "engines/autopilot.json").exists() else None
        step("PUT autopilot config", status, {"body": body, "file_update_hz": on_disk and on_disk.get("update_hz")},
             status == 200 and on_disk == spec)
        status, body = call(base, "GET", "/api/engines/autopilot/config")
        step("GET after PUT", status, {"source": body.get("source"), "update_hz": body["spec"].get("update_hz")},
             status == 200 and body["source"] == "user" and body["spec"]["update_hz"] == 20)
        status, body = call(base, "PUT", "/api/engines/osc_sync/config", {"type": "osc_sync"})
        step("PUT osc_sync is restart_required", status, body,
             status == 409 and body["error"] == "restart_required" and not (cfg / "engines/osc_sync.json").exists())
        status, body = call(base, "PUT", "/api/engines/autopilot/config", {**spec, "update_hz": "fast"})
        step("PUT invalid autopilot", status, body,
             status == 400 and json.loads((cfg / "engines/autopilot.json").read_text(encoding="utf-8")) == spec)
        status, body = call(base, "GET", "/api/osc-relay")
        step("GET osc-relay", status, body, status == 200 and body["running"])
        new_relay = {"enabled": True, "listen": "127.0.0.1:%d" % relay_listen, "destinations": ["127.0.0.1:%d" % sink_port]}
        status, body = call(base, "PUT", "/api/osc-relay", new_relay)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.sendto(b"/sdauto-a2/e2e", ("127.0.0.1", relay_listen))
        received = None
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                data, _ = sink.recvfrom(65535)
            except socket.timeout:
                break
            if data == b"/sdauto-a2/e2e":
                received = data.decode()
                break
        file_relay = json.loads((cfg / "osc_relay.json").read_text(encoding="utf-8"))
        step("PUT osc-relay and forward one datagram", status, {"body": body, "received": received},
             status == 200 and received == "/sdauto-a2/e2e" and file_relay == new_relay)
        status, body = call(base, "GET", "/api/midi/ports")
        step("GET midi ports", status, body, status == 200 and body["selected"]["pulse"] == {"requested": None, "resolved": None})
        status, body = call(base, "GET", "/api/logs/tail?lines=1000")
        step("GET logs tail", status, {"count": body.get("count"), "log_file": body.get("log_file"),
                                        "first": (body.get("lines") or [None])[0]},
             status == 200 and body["count"] > 0 and any("mapping UI available" in l for l in body["lines"]))
        status, body = call(base, "GET", "/api/logs/tail?lines=0")
        step("GET logs tail lines=0", status, body, status == 400)
        status, body = call(base, "POST", "/api/shutdown")
        step("POST shutdown", status, body, status == 202)
        try:
            code = proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            code = None
        results["exit_code"] = code
        step("process exited 0", code, None, code == 0)
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        log.close()
        sink.close()
    alive = subprocess.run(["/bin/ps", "-p", str(proc.pid)], capture_output=True, text=True)
    results["ps_after"] = {"exit": alive.returncode, "stdout": alive.stdout.strip()}
    step("ps -p shows no process", alive.returncode, None, alive.returncode == 1)
    results["passed"] = all(s["ok"] for s in results["steps"])
    (out / "e2e.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print("E2E PASSED" if results["passed"] else "E2E FAILED")
    return 0 if results["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
