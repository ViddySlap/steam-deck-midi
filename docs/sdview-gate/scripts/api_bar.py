"""sdview gate: perform the browser's disk edits with curl against V1's routes on a second config copy.
Usage: python3 api_bar.py <ui_port> <tree_dir> <browser_steps.json> <out.json>
Each step's resulting preset (parsed) must equal the browser run's snapshot after the same step."""
import hashlib, json, subprocess, sys, time
port, tree, steps_path, out_path = sys.argv[1:5]
BASE = f"http://127.0.0.1:{port}"
PRESET = f"{tree}/config/presets/EDM Show.json"
sha = lambda: hashlib.sha256(open(PRESET, "rb").read()).hexdigest()
load = lambda: json.load(open(PRESET))
rows = []

def curl(method, path, body=None, raw=None):
    cmd = ["curl", "-sS", "-o", "/tmp/sdview-gate/api-body.json", "-w", "%{http_code}", "-X", method, BASE + path]
    if body is not None or raw is not None:
        cmd[1:1] = ["-H", "content-type: application/json", "--data", raw if raw is not None else json.dumps(body)]
    code = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return int(code), open("/tmp/sdview-gate/api-body.json").read(), " ".join(repr(c) if " " in c else c for c in cmd)

def row(id_, cmd, code, want_code, before_sha, after_sha, extra):
    ok = code == want_code and all(extra.values())
    rows.append({"id": id_, "command": cmd, "http": code, "want_http": want_code, "sha_before": before_sha, "sha_after": after_sha, **extra, "pass": ok})
    print("PASS" if ok else "FAIL", id_, code, extra)

W = "windows"
# ---- refusals on the pristine copy ----
pristine = sha()
for id_, method, path, body, raw, want in [
    ("bad-spec-channel-99", "PUT", f"/api/mappings/BTN_A?section={W}", {"type": "note", "channel": 99, "note": 36, "velocity": 127}, None, 400),
    ("bad-spec-channel-99-force", "PUT", f"/api/mappings/BTN_A?section={W}&force=1", {"type": "note", "channel": 99, "note": 36, "velocity": 127}, None, 400),
    ("bad-spec-unknown-type", "PUT", f"/api/mappings/BTN_A?section={W}", {"type": "bogus"}, None, 400),
    ("bad-spec-malformed-json", "PUT", f"/api/mappings/BTN_A?section={W}", None, "{not json", 400),
    ("unknown-action", "PUT", f"/api/mappings/NOPE?section={W}", {"type": "note", "channel": 0, "note": 1, "velocity": 1}, None, 404),
    ("unknown-section", "DELETE", "/api/mappings/BTN_A?section=nosuch", None, None, 422),
    ("macro-incompatible", "POST", "/api/macros/encoder-plus/apply", {"action_id": "BTN_A", "section": W}, None, 409),
]:
    code, text, cmd = curl(method, path, body, raw)
    time.sleep(0.3)
    row(id_, cmd, code, want, pristine, sha(), {"bytes_identical": sha() == pristine})

# ---- controller-map GETs ----
owned = json.load(open(f"{tree}/windows/static/controller/controller_map.json"))
code, text, cmd = curl("GET", "/api/controller-map")
row("get-controller-map", cmd, code, 200, pristine, sha(), {"equals_owned_file": json.loads(text) == owned})
eq = 0
for c in owned["controls"]:
    code, text, cmd = curl("GET", f"/api/controller-map/{c['id']}?section={W}")
    got = json.loads(text)
    if code == 200 and {k: [r["action_id"] for r in v] for k, v in got["groups"].items()} == c["groups"]:
        eq += 1
row("get-controller-map-23-controls", f"curl -sS -X GET {BASE}/api/controller-map/<id>?section=windows x23", 200 if eq == 23 else 0, 200, pristine, sha(), {"groups_equal_map": eq == 23, "count": eq})
code, text, cmd = curl("GET", f"/api/controller-map/nosuch?section={W}")
row("get-unknown-control", cmd, code, 404, pristine, sha(), {"bytes_identical": sha() == pristine})

# ---- the browser's writes, in order ----
browser = {s["id"]: s for s in json.load(open(steps_path))}
def e_write():
    d = load(); d["sections"]["macbook"]["mappings"]["BTN_A"]["note"] = 37
    open(PRESET, "w").write(json.dumps(d, indent=2) + "\n")
    return 0, "", "python3 outside write: sections.macbook.mappings.BTN_A.note = 37"
plan = [
    ("c1", lambda: curl("PUT", f"/api/mappings/BTN_A?section={W}", {"type": "note", "channel": 0, "note": 50, "velocity": 127}), 200),
    ("c2", lambda: curl("PUT", f"/api/mappings/R_STICK_X_AXIS?section={W}", {"type": "axis_split_cc", "channel": 15, "cc_positive": 114, "cc_negative": 116, "input_max": 32767, "deadzone": 4000, "curve": "linear"}), 200),
    ("c3", lambda: curl("DELETE", f"/api/mappings/BTN_Y_LAYER_2?section={W}"), 200),
    ("c4", lambda: curl("POST", "/api/macros/click-toggle/apply", {"action_id": "DPAD_DOWN_LONG_PRESS", "section": W}), 200),
    ("c5", lambda: curl("PUT", f"/api/mappings/L5?section={W}", {"type": "note", "channel": 0, "note": 80, "velocity": 100}), 200),
    ("c6-cancel", lambda: curl("PUT", f"/api/mappings/START?section={W}", {"type": "cc", "channel": 2, "cc": 79, "on_value": 127, "off_value": 0}), 409),
    ("c6", lambda: curl("PUT", f"/api/mappings/START?section={W}&force=1", {"type": "cc", "channel": 2, "cc": 79, "on_value": 127, "off_value": 0}), 200),
    ("d8", lambda: curl("DELETE", f"/api/mappings/SELECT?section={W}"), 200),
    ("d1", lambda: curl("PUT", f"/api/mappings/GYRO_FORWARD?section={W}", {"type": "note", "channel": 0, "note": 36, "velocity": 127}), 200),
    ("d2", lambda: curl("PUT", f"/api/mappings/L4?section={W}", {"type": "cc", "channel": 2, "cc": 74, "on_value": 100, "off_value": 0}), 200),
    ("d3", lambda: curl("PUT", f"/api/mappings/DPAD_RIGHT?section={W}", {"type": "macro_cc", "channel": 0, "cc": 21, "gesture": "click", "fade_duration_seconds": 1.5}), 200),
    ("d4", lambda: curl("PUT", f"/api/mappings/R_PAD_DOWN?section={W}", {"type": "relative_cc", "channel": 0, "cc": 49, "step_value": 127, "repeat_interval_ms": 60}), 200),
    ("d5", lambda: curl("PUT", f"/api/mappings/L_PAD_LEFT_LONG_PRESS?section={W}", {"type": "staged_note_macro", "note": 86, "velocity": 127, "modifier_channel": 0, "trigger_channel": 1, "refresh_actions": ["L_PAD_LEFT", "L_PAD_RIGHT"], "macro_delay_ms": 120}), 200),
    ("d6", lambda: curl("PUT", f"/api/mappings/L_TRIGGER_PRESSURE?section={W}", {"type": "axis_to_cc", "channel": 0, "cc": 1, "input_range": [5000, 32767], "output_range": [0, 127], "deadzone": 6000, "curve": "quadratic"}), 200),
    ("e", e_write, 0),
    ("e2", lambda: curl("PUT", f"/api/mappings/BTN_X?section={W}", {"type": "note", "channel": 0, "note": 44, "velocity": 127}), 200),
    ("d12", lambda: curl("POST", "/api/reset", {"section": W}), 200),
]
assert [p[0] for p in plan] == [s["id"] for s in json.load(open(steps_path))], "plan order must equal browser step order"
for id_, fn, want in plan:
    before = sha()
    code, text, cmd = fn()
    time.sleep(1.0)
    after = sha()
    extra = {"file_equals_browser_snapshot": load() == browser[id_]["snapshot"]}
    if want == 409:
        extra["bytes_identical"] = after == before
        extra["conflicts_in_body"] = bool(json.loads(text).get("conflicts"))
    row(id_, cmd, code, want, before, after, extra)

json.dump({"rows": rows, "all_pass": all(r["pass"] for r in rows)}, open(out_path, "w"), indent=2)
print("ALL PASS" if all(r["pass"] for r in rows) else "SOME FAIL", f"{sum(r['pass'] for r in rows)}/{len(rows)}")
sys.exit(0 if all(r["pass"] for r in rows) else 1)
