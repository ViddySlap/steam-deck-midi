"""sdauto gate steps 1, 2 and 2b on a REAL bridge (Mac, engines ON, loopback only).

  .venv/bin/python -B gate_bridge.py --out /tmp/sdauto-gate/s1/run

Boot 1: CCs on the dry-run feedback path (hook) -> GET /api/engines -> POST /api/shutdown
        -> state file holds the five fields and no runtime field.
Boot 2: NO UDP, NO MIDI input. Measure "engines loaded" (log ring asctime) -> first
        autopilot transition/duration OSC datagram at the autopilot-only listener
        (time.time() on the same host clock). Then the step 2 routes, 2b, clear, shutdown.
Boot 3: corrupt state file -> defaults, file byte-identical.
Writes <out>/gate_bridge.json. Exit 0 only if every check passed.
"""
from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path("/Users/viddyslap/Documents/project-workspaces/steam-deck-midi")
HERE = Path(__file__).resolve().parent
PY = str(ROOT / ".venv/bin/python")
RUNTIME_FIELDS = {"cycle_index", "beat_in_clip", "visible_layer", "target_layer",
                  "crossfade_start_time", "bag", "last_clip", "clip_count_cache"}
FIVE = ["enabled", "beats_per_clip", "transition_seconds", "clip_mode", "layer_enabled"]
OSC_XML = """<?xml version="1.0" encoding="utf-8"?>
<OSCShortcutPreset>
  <ShortcutManager>
    <Shortcut paramNodeName="ParamRange">
      <ShortcutPath name="InputPath" path="/composition/layers/1/master" allowedTranslationTypes="11"/>
      <ShortcutPath name="OutputPath" path="/composition/layers/1/master" allowedTranslationTypes="11"/>
    </Shortcut>
    <Shortcut paramNodeName="ParamRange">
      <ShortcutPath name="InputPath" path="/composition/layers/2/master" allowedTranslationTypes="11"/>
      <ShortcutPath name="OutputPath" path="/composition/layers/2/master" allowedTranslationTypes="11"/>
    </Shortcut>
  </ShortcutManager>
</OSCShortcutPreset>
"""

CHECKS: list[dict] = []


def check(name, ok, **detail):
    CHECKS.append({"name": name, "ok": bool(ok), **detail})
    print(("PASS " if ok else "FAIL ") + name + " " + json.dumps(detail, default=str)[:600], flush=True)
    return ok


def sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def free_port(kind=socket.SOCK_STREAM):
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class UdpRecorder:
    def __init__(self, label):
        self.label = label
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.rows = []
        self.sock.settimeout(0.2)
        self.stop = False
        self.t = threading.Thread(target=self.run, daemon=True)
        self.t.start()

    def run(self):
        while not self.stop:
            try:
                data, addr = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                return
            now = time.time()
            address = data.split(b"\0", 1)[0].decode("ascii", "replace")
            value = None
            try:
                if b",f" in data:
                    import struct
                    value = struct.unpack(">f", data[-4:])[0]
            except Exception:
                pass
            self.rows.append({"t": now, "address": address, "value": value, "len": len(data), "raw_hex": data[:96].hex()})

    def close(self):
        self.stop = True
        self.sock.close()


class RestStub(http.server.BaseHTTPRequestHandler):
    log_rows: list = []

    def _reply(self):
        RestStub.log_rows.append({"t": time.time(), "method": self.command, "path": self.path})
        body = json.dumps({"layers": []}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_PUT = do_POST = _reply

    def log_message(self, *a):
        pass


def call(base, method, path, body=None, raw=None, timeout=10):
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    req = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as exc:
        text = exc.read()
        try:
            return exc.code, json.loads(text or b"null")
        except ValueError:
            return exc.code, text.decode("utf-8", "replace")[:300]


def hook(port, msg, timeout=3.0):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        s.sendto(json.dumps(msg).encode(), ("127.0.0.1", port))
        data, _ = s.recvfrom(1 << 20)
        return json.loads(data)


def build_tree(out: Path, osc_auto: int, osc_other: int, rest_port: int):
    cfg = out / "tree/config"
    (cfg / "engines").mkdir(parents=True)
    (cfg / "engines.factory").mkdir()
    (cfg / "presets").mkdir()
    for name in ("windows_midi_map.json", "actions.yaml", "macro_library.json"):
        shutil.copy2(ROOT / "config" / name, cfg / name)
    manifest = (ROOT / ".showready/fixtures/mac/MANIFEST.sha256").read_text()
    for src in sorted((ROOT / ".showready/fixtures/mac/presets").glob("*.json")):
        shutil.copy2(src, cfg / "presets" / src.name)
    (cfg / "presets/.active").write_text("EDM Show.json", encoding="ascii")
    rest = "http://127.0.0.1:%d" % rest_port
    removed = []

    def loopback(node, port, path=""):
        if isinstance(node, dict):
            res = {}
            for key, value in node.items():
                if key in ("osc_preset_path", "comp_path"):
                    removed.append(path + "/" + key)
                    continue
                if key in ("host", "camera_nic_ip"):
                    res[key] = "127.0.0.1"
                elif key in ("port", "visca_port") and isinstance(value, int):
                    res[key] = port
                elif key == "base_url":
                    res[key] = rest
                elif key == "cameras" and isinstance(value, dict):
                    res[key] = {k: "127.0.0.1" for k in value}
                else:
                    res[key] = loopback(value, port, path + "/" + key)
            return res
        if isinstance(node, list):
            return [loopback(v, port, path) for v in node]
        return node

    for folder in ("engines.factory", "engines"):
        for src in sorted((ROOT / "config" / folder).glob("*.json")):
            doc = json.loads(src.read_text(encoding="utf-8"))
            port = osc_auto if doc.get("type") == "autopilot" else osc_other
            text = json.dumps(loopback(doc, port, folder + "/" + src.name), indent=2)
            (cfg / folder / src.name).write_text(text, encoding="utf-8")
    foreign = {}
    for path in cfg.rglob("*"):
        if path.is_file() and path.suffix in (".json", ".yaml"):
            text = path.read_text(encoding="utf-8")
            ips = [ip for ip in re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text) if ip != "127.0.0.1"]
            urls = [u for u in re.findall(r"[a-z]+://([^/\s\"':]+)", text) if u not in ("127.0.0.1",)]
            hosts = [h for h in re.findall(r"\"host\"\s*:\s*\"([^\"]+)\"", text) if h != "127.0.0.1"]
            if ips or urls or hosts:
                foreign[str(path.relative_to(out))] = sorted(set(ips + urls + hosts))
    return cfg, removed, foreign


def spawn(out, tag, cfg, home, ui_port, listen, control, with_hook=True):
    env = {**os.environ, "PYSTRAY_BACKEND": "dummy", "BROWSER": "/usr/bin/true", "HOME": str(home), "USERPROFILE": str(home),
           "PYTHONPATH": str(ROOT)}
    argv = ["--map", str(cfg / "windows_midi_map.json"), "--preset-section", "windows", "--dry-run", "--no-pulse",
            "--no-browser", "--midi-port", "IAC Driver DECK_IN", "--feedback-port", "IAC Driver DECK_OUT",
            "--listen", "127.0.0.1:%d" % listen, "--ui-port", str(ui_port)]
    cmd = [PY, "-B", "-u", str(HERE / "hook_launch.py"), str(control), "--"] + argv
    log = open(out / f"{tag}.bridge.log", "w", encoding="utf-8")
    t_spawn = time.time()
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    base = "http://127.0.0.1:%d" % ui_port
    t_up = None
    for _ in range(300):
        try:
            if call(base, "GET", "/api/engines", timeout=1)[0] == 200:
                t_up = time.time()
                break
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.05)
    return proc, log, base, {"cmd": cmd, "pid": proc.pid, "t_spawn": t_spawn, "t_ui_up": t_up}


def stop(proc, log, base, tag):
    status, body = call(base, "POST", "/api/shutdown")
    try:
        code = proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        code = None
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=10)
    log.close()
    alive = subprocess.run(["/bin/ps", "-p", str(proc.pid)], capture_output=True, text=True)
    check(f"{tag}: POST /api/shutdown 202 and exit 0, pid gone", status == 202 and code == 0 and alive.returncode == 1,
          status=status, exit=code, ps_exit=alive.returncode)
    return code


def ring_time(line):
    m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d{3}) ", line)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").timestamp() + int(m.group(2)) / 1000.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    osc_auto, osc_other = UdpRecorder("autopilot"), UdpRecorder("other")
    dest1, dest2 = UdpRecorder("relay-d1"), UdpRecorder("relay-d2")
    rest_port = free_port()
    rest = http.server.ThreadingHTTPServer(("127.0.0.1", rest_port), RestStub)
    threading.Thread(target=rest.serve_forever, daemon=True).start()
    cfg, removed, foreign = build_tree(out, osc_auto.port, osc_other.port, rest_port)
    result = {"tree": str(cfg), "removed_keys": removed, "foreign_addresses": foreign,
              "osc_autopilot_port": osc_auto.port, "osc_other_port": osc_other.port, "rest_port": rest_port}
    if not check("scratch engine configs name zero non-loopback addresses", not foreign, foreign=foreign):
        (out / "gate_bridge.json").write_text(json.dumps({"checks": CHECKS, **result}, indent=2))
        return 2
    home = out / "home"
    xml = home / "OneDrive/Documents/Resolume Arena/Shortcuts/OSC/STEAMDECK V2.xml"
    comp = home / "OneDrive/Documents/Resolume Arena/Compositions/5-5-26 STEAMDECK V2.avc"
    xml.parent.mkdir(parents=True)
    comp.parent.mkdir(parents=True)
    xml.write_text(OSC_XML, encoding="utf-8")
    comp.write_bytes(b"<gate placeholder avc>\n")
    auto_cfg = json.loads((cfg / "engines.factory/autopilot.json").read_text())
    update_hz = auto_cfg["update_hz"]
    state_file = cfg / "state/autopilot_channels.local.json"
    ui_port, listen, control = free_port(), free_port(socket.SOCK_DGRAM), free_port(socket.SOCK_DGRAM)
    relay_listen = free_port(socket.SOCK_DGRAM)
    (cfg / "osc_relay.json").write_text(json.dumps({"enabled": True, "listen": "127.0.0.1:%d" % relay_listen,
                                                    "destinations": ["127.0.0.1:%d" % osc_other.port]}), encoding="utf-8")
    ch = auto_cfg["inputs"]["channel"]
    ccs = [  # (channel key, cc, value)
        ("video", 64, 127), ("video", 65, 127), ("video", 61, 2), ("video", 62, 64), ("video", 63, 1), ("video", 60, 127),
        ("fx", 74, 127), ("fx", 71, 4), ("fx", 72, 127), ("fx", 73, 2), ("fx", 70, 127),
        ("logo", 85, 127),
    ]
    result["ccs_sent_boot1"] = [{"channel": ch, "cc": c, "value": v, "for": k} for k, c, v in ccs]

    # ---------------- Boot 1
    proc, log, base, meta = spawn(out, "boot1", cfg, home, ui_port, listen, control)
    result["boot1"] = meta
    try:
        check("boot1: UI up", meta["t_ui_up"] is not None)
        _, eng0 = call(base, "GET", "/api/engines")
        result["boot1"]["engines_before"] = eng0
        check("boot1: no state file before any CC", not state_file.exists())
        for _k, c, v in ccs:
            hook(control, {"cmd": "cc", "ch": ch, "cc": c, "val": v})
        time.sleep(1.5)
        probe = hook(control, {"cmd": "probe"})
        result["boot1"]["probe"] = {k: probe[k] for k in ("injected_cc", "autopilot_ids", "autopilot_active", "mido_opens")}
        check("boot1: hook delivered every CC through the feedback path", probe["injected_cc"] == len(ccs), injected=probe["injected_cc"])
        _, eng1 = call(base, "GET", "/api/engines")
        auto1 = next(e for e in eng1["engines"] if e["type"] == "autopilot") if isinstance(eng1, dict) and "engines" in eng1 else None
        if auto1 is None:
            auto1 = next(e for e in eng1 if e.get("type") == "autopilot")
        result["boot1"]["autopilot_status"] = auto1
        want = {
            "video": {"enabled": True, "beats_per_clip": auto_cfg["inputs"]["beats_lookup"][2], "transition_seconds": 64 / 127.0 * 5.0,
                      "clip_mode": "LINEAR", "layer_enabled": {"1": True, "2": True, "3": False, "4": False}},
            "fx": {"enabled": True, "beats_per_clip": auto_cfg["inputs"]["beats_lookup"][4], "transition_seconds": 5.0,
                   "clip_mode": "RANDOM", "layer_enabled": {"5": True}},
            "logo": {"enabled": False, "beats_per_clip": 16, "transition_seconds": 0.0, "clip_mode": "NONE",
                     "layer_enabled": {"6": False, "7": True}},
        }
        got = {k: {f: auto1["status"]["channels"][k][f] if "status" in auto1 else auto1["channels"][k][f] for f in FIVE} for k in want}
        result["boot1"]["five_fields"] = got
        check("boot1: GET /api/engines shows the CC-set five fields", got == want, got=got, want=want)
    finally:
        stop(proc, log, base, "boot1")
    doc1 = json.loads(state_file.read_text()) if state_file.exists() else None
    result["state_after_boot1"] = doc1
    result["state_after_boot1_sha256"] = sha(state_file)
    keys_ok = False
    if doc1:
        chans = doc1["engines"][next(iter(doc1["engines"]))]["channels"] if "engines" in doc1 else {}
        keys_ok = all(set(v.keys()) == set(FIVE) for v in chans.values()) and \
            not any(f in json.dumps(doc1) for f in RUNTIME_FIELDS) and \
            {k: {f: v[f] for f in FIVE} for k, v in chans.items()} == got
    check("state file holds exactly the five fields per channel, equal to GET, and no runtime field", keys_ok, doc=doc1)

    # ---------------- Boot 2 (no input)
    osc_auto.rows.clear()
    RestStub.log_rows.clear()
    t_before_boot2 = time.time()
    proc, log, base, meta = spawn(out, "boot2", cfg, home, ui_port, listen, control)
    result["boot2"] = meta
    try:
        _, eng2 = call(base, "GET", "/api/engines")
        t_eng2 = time.time()
        auto2 = next(e for e in (eng2["engines"] if isinstance(eng2, dict) else eng2) if e.get("type") == "autopilot")
        result["boot2"]["autopilot_status_first_get"] = {"t": t_eng2, "status": auto2}
        chans2 = auto2["status"]["channels"] if "status" in auto2 else auto2["channels"]
        got2 = {k: {f: chans2[k][f] for f in FIVE} for k in chans2}
        check("boot2: GET /api/engines five fields equal boot1 (no input sent)", got2 == got, got=got2)
        runtime2 = {k: {f: chans2[k].get(f) for f in ("visible_layer", "target_layer", "beat_in_clip", "cycle_index")} for k in chans2}
        result["boot2"]["runtime_first_get"] = runtime2
        time.sleep(2.5)
        _, tail = call(base, "GET", "/api/logs/tail?lines=1000")
        lines = tail["lines"]
        (out / "boot2.ring.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        loaded = [l for l in lines if "engines loaded:" in l]
        restored = [l for l in lines if "restored autopilot intent" in l]
        t_loaded = ring_time(loaded[0]) if loaded else None
        trans = [r for r in osc_auto.rows if re.fullmatch(r"/composition/layers/\d+/transition/duration", r["address"])]
        first_any_auto = osc_auto.rows[0] if osc_auto.rows else None
        first = trans[0] if trans else None
        probe2 = hook(control, {"cmd": "probe"})
        result["boot2"]["no_input_evidence"] = {"hook_injected_cc": probe2["injected_cc"], "udp_packets_sent_by_gate": 0,
                                                "filter_calls": len(probe2["filter_calls"])}
        result["boot2"]["engines_loaded_line"] = loaded[0] if loaded else None
        result["boot2"]["restored_line"] = restored[0] if restored else None
        result["boot2"]["first_transition_push"] = first
        result["boot2"]["first_autopilot_datagram"] = first_any_auto
        result["boot2"]["autopilot_datagrams_first_20"] = osc_auto.rows[:20]
        delay_ms = (first["t"] - t_loaded) * 1000 if (first and t_loaded) else None
        result["boot2"]["delay_ms_engines_loaded_to_first_transition_push"] = delay_ms
        result["boot2"]["tick_interval_ms"] = 1000.0 / update_hz
        result["boot2"]["clock_note"] = "ring asctime (record.created, time.time, ms resolution) vs listener time.time() on the same Mac: offset 0"
        check("boot2: no MIDI injected and no Deck UDP sent", probe2["injected_cc"] == 0)
        check("boot2: restored transition push arrived WITHOUT input within 1 s of engines loaded",
              delay_ms is not None and abs(delay_ms) <= 1000.0, delay_ms=delay_ms, first=first, engines_loaded=loaded[:1])
        t_restored = ring_time(restored[0]) if restored else None
        result["boot2"]["delay_ms_restored_line_to_first_push"] = (first["t"] - t_restored) * 1000 if (first and t_restored) else None
        result["boot2"]["delay_ms_spawn_to_first_push"] = (first["t"] - meta["t_spawn"]) * 1000 if first else None
        result["boot2"]["pushes_before_engines_loaded_line"] = sum(1 for r in osc_auto.rows if t_loaded and r["t"] < t_loaded)
        pushes = {r["address"]: round(r["value"], 6) for r in trans[:8]}
        want_push = {"/composition/layers/1/transition/duration": round((64 / 127.0 * 5.0) / 10.0, 6),
                     "/composition/layers/2/transition/duration": round((64 / 127.0 * 5.0) / 10.0, 6),
                     "/composition/layers/5/transition/duration": round(5.0 / 10.0, 6),
                     "/composition/layers/7/transition/duration": 0.0}
        check("boot2: restored pushes carry the restored transition per selected layer",
              all(pushes.get(a) is not None and abs(pushes[a] - v) < 1e-5 for a, v in want_push.items()), pushes=pushes, want=want_push)

        # ---------------- Step 2 routes (same boot)
        routes = result["routes"] = {}
        s, b = call(base, "GET", "/api/engines/autopilot/config")
        routes["GET autopilot config"] = {"status": s, "source": b.get("source"), "live_swappable": b.get("live_swappable")}
        check("route: GET /api/engines/autopilot/config 200 factory live_swappable", s == 200 and b.get("live_swappable") is True, **routes["GET autopilot config"])
        spec = b["spec"]
        user_auto = cfg / "engines/autopilot.json"
        # control for the filter detector: before the PUT the OLD instance is consulted
        pre = hook(control, {"cmd": "probe"})
        old_id = pre["autopilot_ids"][0]
        hook(control, {"cmd": "reset_calls"})
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as deck:
            for seq, state in ((1, "down"), (2, "up")):
                deck.sendto(json.dumps({"action": "L_PAD_LEFT", "kind": "action", "seq": seq, "state": state},
                                       sort_keys=True, separators=(",", ":")).encode(), ("127.0.0.1", listen))
                time.sleep(0.15)
        time.sleep(0.3)
        pre_calls = hook(control, {"cmd": "probe"})["filter_calls"]
        routes["filter control before PUT"] = {"old_id": old_id, "call_ids": sorted({c["id"] for c in pre_calls}), "calls": pre_calls}
        check("control: before PUT, the Deck L_PAD_LEFT note consults the OLD autopilot filter",
              bool(pre_calls) and {c["id"] for c in pre_calls} == {old_id}, calls=len(pre_calls))
        # good PUT
        new_spec = {**spec, "update_hz": 20}
        s, b = call(base, "PUT", "/api/engines/autopilot/config", new_spec)
        on_disk = json.loads(user_auto.read_text()) if user_auto.exists() else None
        post = hook(control, {"cmd": "probe"})
        routes["PUT autopilot good"] = {"status": s, "file_equals_body": on_disk == new_spec, "autopilot_ids": post["autopilot_ids"],
                                        "update_hz": post["autopilot_update_hz"], "filter_owner_ids": post["filter_owner_ids"],
                                        "filter_owner_types": post["filter_owner_types"]}
        new_id = post["autopilot_ids"][0]
        check("route: PUT autopilot config 200, file written, live instance replaced (new id, update_hz 20)",
              s == 200 and on_disk == new_spec and new_id != old_id and post["autopilot_update_hz"] == [20], **routes["PUT autopilot good"])
        auto_filters = [i for i, t in zip(post["filter_owner_ids"], post["filter_owner_types"]) if t == "AutopilotEngine"]
        check("route: after PUT the registry holds exactly the NEW autopilot filter", auto_filters == [new_id], filters=auto_filters)
        hook(control, {"cmd": "reset_calls"})
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as deck:
            for seq, state in ((3, "down"), (4, "up")):
                deck.sendto(json.dumps({"action": "L_PAD_LEFT", "kind": "action", "seq": seq, "state": state},
                                       sort_keys=True, separators=(",", ":")).encode(), ("127.0.0.1", listen))
                time.sleep(0.15)
        time.sleep(0.3)
        post_calls = hook(control, {"cmd": "probe"})["filter_calls"]
        routes["filter after PUT"] = {"new_id": new_id, "call_ids": sorted({c["id"] for c in post_calls}), "calls": post_calls}
        check("route: after PUT only the NEW instance's note-emit filter is consulted",
              bool(post_calls) and {c["id"] for c in post_calls} == {new_id}, calls=len(post_calls))
        # bad PUT
        before = sha(user_auto)
        s, b = call(base, "PUT", "/api/engines/autopilot/config", {**new_spec, "update_hz": "fast"})
        ids_after_bad = hook(control, {"cmd": "probe"})["autopilot_ids"]
        routes["PUT autopilot bad"] = {"status": s, "body": b, "sha_before": before, "sha_after": sha(user_auto), "ids": ids_after_bad}
        check("route: PUT bad spec 400, file sha256 unchanged, instance unchanged",
              s == 400 and before == sha(user_auto) and ids_after_bad == [new_id], **routes["PUT autopilot bad"])
        # restart_required
        s, b = call(base, "GET", "/api/engines/osc_sync/config")
        osc_sync_user = cfg / "engines/osc_sync.json"
        before = sha(osc_sync_user)
        listing_before = sorted(p.name for p in (cfg / "engines").iterdir())
        s2, b2 = call(base, "PUT", "/api/engines/osc_sync/config", b.get("spec", {"type": "osc_sync"}))
        routes["PUT osc_sync"] = {"get_status": s, "status": s2, "body": b2, "sha_before": before, "sha_after": sha(osc_sync_user),
                                  "engines_dir_before": listing_before, "engines_dir_after": sorted(p.name for p in (cfg / "engines").iterdir())}
        check("route: PUT restart_required type (osc_sync) 409, nothing written",
              s2 == 409 and isinstance(b2, dict) and b2.get("error") == "restart_required" and before == sha(osc_sync_user)
              and listing_before == routes["PUT osc_sync"]["engines_dir_after"], **routes["PUT osc_sync"])
        # OSC relay
        s, b = call(base, "GET", "/api/osc-relay")
        routes["GET osc-relay"] = {"status": s, "body": b}
        check("route: GET /api/osc-relay 200 running", s == 200 and b.get("running") is True, status=s)
        relay_file = cfg / "osc_relay.json"
        new_relay = {"enabled": True, "listen": "127.0.0.1:%d" % relay_listen,
                     "destinations": ["127.0.0.1:%d" % dest1.port, "127.0.0.1:%d" % dest2.port]}
        s, b = call(base, "PUT", "/api/osc-relay", new_relay)
        time.sleep(0.3)
        payload = b"/sdauto-gate/relay\x00\x00,\x00\x00\x00"
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as snd:
            snd.sendto(payload, ("127.0.0.1", relay_listen))
        time.sleep(0.8)
        got1 = [r for r in dest1.rows if r["address"] == "/sdauto-gate/relay"]
        got2 = [r for r in dest2.rows if r["address"] == "/sdauto-gate/relay"]
        routes["PUT osc-relay two destinations"] = {"status": s, "file_equals_body": json.loads(relay_file.read_text()) == new_relay,
                                                    "d1": len(got1), "d2": len(got2)}
        check("route: PUT osc-relay 200; one datagram to listen arrives at BOTH new destinations",
              s == 200 and routes["PUT osc-relay two destinations"]["file_equals_body"] and len(got1) == 1 and len(got2) == 1,
              **routes["PUT osc-relay two destinations"])
        before = sha(relay_file)
        s, b = call(base, "PUT", "/api/osc-relay", {"enabled": True, "listen": "127.0.0.1:%d" % relay_listen,
                                                    "destinations": ["127.0.0.1:%d" % relay_listen]})
        routes["PUT osc-relay dest == listen"] = {"status": s, "body": b, "sha_unchanged": before == sha(relay_file)}
        check("route: PUT osc-relay destination == listen 400, file unchanged", s == 400 and before == sha(relay_file), **routes["PUT osc-relay dest == listen"])
        # MIDI ports
        s, b = call(base, "GET", "/api/midi/ports")
        opens = hook(control, {"cmd": "probe"})["mido_opens"]
        lst = subprocess.run([PY, "-B", "-c", "import json,rtmidi; print(json.dumps({'inputs': rtmidi.MidiIn().get_ports(), 'outputs': rtmidi.MidiOut().get_ports()}))"],
                             capture_output=True, text=True)
        rt = json.loads(lst.stdout) if lst.returncode == 0 else {"error": lst.stderr[-300:]}
        routes["GET midi ports"] = {"status": s, "body": b, "python_rtmidi": rt, "mido_open_calls": opens}
        same = s == 200 and sorted(b.get("inputs") or []) == sorted(rt.get("inputs", [])) and sorted(b.get("outputs") or []) == sorted(rt.get("outputs", []))
        check("route: GET /api/midi/ports lists the python-rtmidi names (IAC present) and opened nothing",
              same and not opens and any("IAC" in n for n in (b.get("outputs") or [])), inputs=b.get("inputs"), outputs=b.get("outputs"), rtmidi=rt, opens=opens)
        # log tail
        s, b = call(base, "GET", "/api/logs/tail?lines=50")
        stamped = [l for l in b.get("lines", []) if ring_time(l) is not None]
        s1000, b1000 = call(base, "GET", "/api/logs/tail?lines=1000")
        boot_line = [l for l in b1000.get("lines", []) if "build fingerprint: version=" in l]
        routes["GET logs tail"] = {"status": s, "count": b.get("count"), "stamped": len(stamped), "first": (b.get("lines") or [None])[0],
                                   "boot_line_in_50": any("build fingerprint" in l for l in b.get("lines", [])),
                                   "status_1000": s1000, "boot_line": boot_line[:1]}
        check("route: GET /api/logs/tail?lines=50 returns <=50 timestamped records; boot line present in the ring",
              s == 200 and 0 < b.get("count", 0) <= 50 and len(stamped) == b["count"] and boot_line, **routes["GET logs tail"])
        # 2b
        s, b = call(base, "POST", "/api/engines/osc-sync/resync")
        _, tail2 = call(base, "GET", "/api/logs/tail?lines=1000")
        parsed = [l for l in tail2["lines"] if "osc_sync: parsed" in l]
        paths = hook(control, {"cmd": "probe"})
        result["step2b"] = {"resync_status": s, "resync_body": b, "parsed_log": parsed, "osc_sync_preset_path": paths["osc_sync_preset_path"],
                            "stageflow_comp_path": paths["stageflow_comp_path"], "expected_xml": str(xml), "expected_comp": str(comp)}
        check("2b: osc_sync loads the home-relative preset (resync parsed its targets from HOME)",
              s == 200 and parsed and str(xml) in parsed[-1] and "parsed 2 wigglable" in parsed[-1] and paths["osc_sync_preset_path"] == [str(xml)],
              parsed=parsed, body=b)
        check("2b: stageflow_bridge resolves comp_path under HOME (attribute read; see report: no runtime read site)",
              paths["stageflow_comp_path"] == [str(comp)], comp=paths["stageflow_comp_path"])
        # clear
        s, b = call(base, "POST", "/api/engines/autopilot/state/clear")
        _, eng3 = call(base, "GET", "/api/engines")
        auto3 = next(e for e in (eng3["engines"] if isinstance(eng3, dict) else eng3) if e.get("type") == "autopilot")
        ch3 = auto3["status"]["channels"] if "status" in auto3 else auto3["channels"]
        defaults = {k: {"enabled": False, "beats_per_clip": 16, "transition_seconds": 0.0, "clip_mode": "NONE",
                        "layer_enabled": {lk: False for lk in ch3[k]["layer_enabled"]}} for k in ch3}
        got3 = {k: {f: ch3[k][f] for f in FIVE} for k in ch3}
        file3 = json.loads(state_file.read_text())
        fchan = file3["engines"][next(iter(file3["engines"]))]["channels"]
        result["clear"] = {"status": s, "persisted": b.get("persisted") if isinstance(b, dict) else None, "get": got3, "file": fchan}
        check("clear: POST .../state/clear 200 persisted, GET and file both defaults",
              s == 200 and b.get("persisted") is True and got3 == defaults and fchan == defaults, **result["clear"])
    finally:
        stop(proc, log, base, "boot2")
    file_after2 = json.loads(state_file.read_text())
    check("after boot2 shutdown the file still holds defaults",
          file_after2["engines"][next(iter(file_after2["engines"]))]["channels"] == defaults)

    # ---------------- Boot 3 corrupt
    corrupt = b'{"schema": 1, "engines": {"Autopilot": {"channels": {"video": {"enabled": tru'
    state_file.write_bytes(corrupt)
    sha_c = sha(state_file)
    proc, log, base, meta = spawn(out, "boot3", cfg, home, ui_port, listen, control)
    result["boot3"] = meta
    try:
        _, eng4 = call(base, "GET", "/api/engines")
        auto4 = next(e for e in (eng4["engines"] if isinstance(eng4, dict) else eng4) if e.get("type") == "autopilot")
        ch4 = auto4["status"]["channels"] if "status" in auto4 else auto4["channels"]
        got4 = {k: {f: ch4[k][f] for f in FIVE} for k in ch4}
        _, tail4 = call(base, "GET", "/api/logs/tail?lines=1000")
        warn = [l for l in tail4["lines"] if "ignoring autopilot state file" in l]
        time.sleep(1.0)
        result["boot3"].update({"get": got4, "warning": warn, "hook_injected_cc": hook(control, {"cmd": "probe"})["injected_cc"]})
        check("boot3: corrupt file -> GET shows config defaults and one warning", got4 == defaults and len(warn) == 1, got=got4, warn=warn)
    finally:
        stop(proc, log, base, "boot3")
    check("boot3: corrupt file byte-identical after boot and shutdown", sha(state_file) == sha_c and state_file.read_bytes() == corrupt,
          sha_before=sha_c, sha_after=sha(state_file))

    for r in (osc_auto, osc_other, dest1, dest2):
        r.close()
    rest.shutdown()
    result["rest_requests"] = RestStub.log_rows[:20]
    result["checks"] = CHECKS
    result["passed"] = all(c["ok"] for c in CHECKS)
    (out / "gate_bridge.json").write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    print("GATE BRIDGE PASSED" if result["passed"] else "GATE BRIDGE FAILED", sum(c["ok"] for c in CHECKS), "/", len(CHECKS))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
