"""sdauto gate test hook: run windows.win_recv unchanged inside a process with observers.

  hook_launch.py CONTROL_PORT -- <win_recv argv>

Observers only; no product file is modified:
  * windows.engines.load_engines is wrapped to keep a reference to the registry.
  * AutopilotEngine._note_emit_filter (class attribute, patched before any instance
    exists) records id(self) for every call, then calls the original.
  * DryRunMidiIn.poll_control_changes returns CCs queued by the control socket
    (the dry-run feedback port path: receiver._handle_feedback_message ->
    registry.on_midi_in). With no queued CC it returns [] exactly like the original.
  * mido.open_input / open_output / open_ioport are wrapped to count calls.
Control socket (UDP 127.0.0.1:CONTROL_PORT, JSON): {"cmd":"cc","ch":..,"cc":..,"val":..},
{"cmd":"probe"}, {"cmd":"reset_calls"}. Replies go to the sender address.
"""
import json
import os
import queue
import runpy
import socket
import sys
import threading
import time

control_port = int(sys.argv[1])
assert sys.argv[2] == "--"
bridge_argv = sys.argv[3:]

import windows.engines as engines_pkg
import windows.engines.registry as registry_mod
import windows.midi as midi_mod
from windows.engines.autopilot import AutopilotEngine

STATE = {"registry": None, "filter_calls": [], "injected_cc": 0, "mido_opens": []}
CC_QUEUE: "queue.Queue" = queue.Queue()

_orig_load = registry_mod.load_engines


def load_engines(*args, **kwargs):
    reg = _orig_load(*args, **kwargs)
    STATE["registry"] = reg
    return reg


registry_mod.load_engines = load_engines
engines_pkg.load_engines = load_engines

_orig_filter = AutopilotEngine._note_emit_filter


def _note_emit_filter(self, channel, note, velocity, now):
    result = _orig_filter(self, channel, note, velocity, now)
    STATE["filter_calls"].append({"id": id(self), "channel": channel, "note": note,
                                  "velocity": velocity, "result": result, "t": time.time()})
    return result


AutopilotEngine._note_emit_filter = _note_emit_filter


def poll_control_changes(self):
    out = []
    while True:
        try:
            ch, cc, val = CC_QUEUE.get_nowait()
        except queue.Empty:
            return out
        STATE["injected_cc"] += 1
        out.append(midi_mod.MidiControlChange(channel=ch, control=cc, value=val))


midi_mod.DryRunMidiIn.poll_control_changes = poll_control_changes

try:
    import mido

    for _name in ("open_input", "open_output", "open_ioport"):
        _orig = getattr(mido, _name)

        def _wrap(*a, _orig=_orig, _name=_name, **k):
            STATE["mido_opens"].append({"fn": _name, "args": [str(x) for x in a], "t": time.time()})
            return _orig(*a, **k)

        setattr(mido, _name, _wrap)
except ImportError:
    pass


def _probe():
    reg = STATE["registry"]
    engines = reg.engines if reg is not None else []
    auto = [e for e in engines if e.type_name == "autopilot"]
    osc_sync = [e for e in engines if e.type_name == "osc_sync"]
    stageflow = [e for e in engines if e.type_name == "stageflow_bridge"]
    filters = list(getattr(reg, "_note_emit_filters", [])) if reg is not None else []
    return {
        "pid": os.getpid(),
        "registry": reg is not None,
        "engine_types": [e.type_name for e in engines],
        "autopilot_ids": [id(e) for e in auto],
        "autopilot_update_hz": [getattr(e, "_update_hz", None) for e in auto],
        "autopilot_active": [e.active for e in auto],
        "filter_owner_ids": [id(getattr(cb, "__self__", None)) for cb in filters],
        "filter_owner_types": [type(getattr(cb, "__self__", None)).__name__ for cb in filters],
        "filter_calls": list(STATE["filter_calls"]),
        "injected_cc": STATE["injected_cc"],
        "mido_opens": list(STATE["mido_opens"]),
        "osc_sync_preset_path": [str(getattr(e, "_osc_preset_path", None)) for e in osc_sync],
        "stageflow_comp_path": [str(getattr(e, "_comp_path", None)) for e in stageflow],
    }


def _control():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", control_port))
    while True:
        data, addr = sock.recvfrom(65535)
        try:
            msg = json.loads(data)
            if msg["cmd"] == "cc":
                CC_QUEUE.put((int(msg["ch"]), int(msg["cc"]), int(msg["val"])))
                reply = {"ok": True}
            elif msg["cmd"] == "reset_calls":
                STATE["filter_calls"].clear()
                reply = {"ok": True}
            else:
                reply = _probe()
        except Exception as exc:  # noqa: BLE001
            reply = {"error": repr(exc)}
        sock.sendto(json.dumps(reply).encode(), addr)


threading.Thread(target=_control, daemon=True, name="gate-hook").start()
sys.argv = ["windows.win_recv"] + bridge_argv
runpy.run_module("windows.win_recv", run_name="__main__", alter_sys=True)
