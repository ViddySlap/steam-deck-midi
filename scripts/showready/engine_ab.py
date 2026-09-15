"""Engine A/B: MIDI bytes and OSC calls of every MIDI-emitting engine, v0.4.9 vs a candidate.

The bar 1 instrument (ab_run.py) runs the receiver with --no-engines, so engine
output was NOT COVERED. This instrument covers the five engines that write to
the shared MidiOut: autopilot (including its note-emit filter on the column
trigger notes), l_stick_layer, gyro_feedback, global_color and audio_opacity
(protocol midi).

Each arm is an untouched `git archive` tree. One Python process per arm (both
trees are the `windows` package, so they cannot share an interpreter); inside
that process the engines are driven in-process through THAT revision's own
`load_engines` + `bind_registry`, with fake OSC/REST clients, a seeded RNG, a
byte recorder on the shared MidiOut, a socket guard, and a scripted, fake-time
sequence that calls the registry exactly the way windows/receiver.py does:

  feedback_cc   registry.on_midi_in                      (_handle_feedback_message)
  deck_cc       midi_out.control_change + on_midi_in     (_emit_cc)
  deck_note_on  should_emit_note -> note_on + on_note_in (_emit_note_on)
  deck_note_off midi_out.note_off                        (release / staged off)
  axis          registry.on_axis_event                   (_handle_axis_event)
  clock         registry.on_midi_clock                   (_drain_midi_clock)
  tick          registry.tick                            (serve_forever loop)
  refresh       registry.refresh                         (POST /api/engines/refresh)

Arms: A = v0.4.9; B_nostate = candidate with load_engines(..., state_dir=None);
B_state = candidate with the default derived state dir, present and EMPTY.
Both B arms must equal A event for event. Controls mutate one byte-level
constant in the candidate copy and must go RED for exactly that engine family.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

KIT = Path(__file__).resolve().parent
ROOT = KIT.parents[1]
ENGINE_TYPES = ("audio_opacity", "autopilot", "global_color", "gyro_feedback", "l_stick_layer")
RNG_SEED = 20260915
LOOPBACK_OSC_PORT = 47901
LOOPBACK_REST_PORT = 47902
CONTROLS = {
    # One-byte edit in the candidate copy's autopilot column notes: 86 -> 96.
    "sensitivity-autopilot": (
        "autopilot",
        "windows/engines/autopilot.py",
        "COLUMN_PREV_NOTES = frozenset({82, 86})",
        "COLUMN_PREV_NOTES = frozenset({82, 96})",
    ),
    # One-bit edit to the l_stick_layer positive-direction CC number it emits.
    "sensitivity-l_stick_layer": (
        "l_stick_layer",
        "windows/engines/l_stick_layer.py",
        "self._midi_out.control_change(self._channel, pos_cc, cc_value)",
        "self._midi_out.control_change(self._channel, pos_cc ^ 1, cc_value)",
    ),
}
# Minimum observations per engine on EVERY arm; zero is RED, never a pass.
REQUIRED = {
    "autopilot": ("midi", "osc"),
    "l_stick_layer": ("midi",),
    "gyro_feedback": ("midi",),
    "global_color": ("midi", "osc"),
    "audio_opacity": ("midi",),
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


# ---------------------------------------------------------------- runner ----


def run_arm(args) -> int:
    """Runs inside one arm's process. Imports nothing from the kit."""
    import logging
    import random as random_module
    import socket
    import types

    tree = Path(args.tree).resolve()
    socket_attempts: list[str] = []

    class GuardSocket:
        def __init__(self, *a, **k):
            socket_attempts.append(repr((a, k)))
            raise OSError("engine_ab: sockets are denied in an arm")

    socket.socket = GuardSocket  # type: ignore[misc]
    socket.create_connection = GuardSocket  # type: ignore[assignment]
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    sys.path.insert(0, str(tree))

    import windows.engines.registry as registry_module
    from windows.engines.base import Engine

    loaded_from = Path(registry_module.__file__).resolve()
    if not loaded_from.is_relative_to(tree):
        raise SystemExit(f"registry imported from outside the arm tree: {loaded_from}")
    port_opens: list[str] = []
    if "mido" in sys.modules:
        mido = sys.modules["mido"]
        for name in ("open_input", "open_output", "open_ioport"):
            def deny(*a, _n=name, **k):
                port_opens.append(_n)
                raise OSError("engine_ab: MIDI ports are denied in an arm")
            setattr(mido, name, deny)

    script = json.loads(Path(args.script).read_text(encoding="utf-8"))
    events: list[dict] = []
    current = {"step": "load"}

    def owner() -> str:
        frame = sys._getframe(2)
        while frame is not None:
            candidate = frame.f_locals.get("self")
            if isinstance(candidate, Engine):
                return candidate.type_name
            frame = frame.f_back
        return "receiver"

    class RecordingMidiOut:
        port_name = "engine-ab-recorder"
        port_index = None

        def _record(self, status: int, data1: int, data2: int) -> None:
            events.append({"step": current["step"], "src": owner(),
                           "midi": "%02x%02x%02x" % (status, data1, data2)})

        def note_on(self, channel, note, velocity):
            self._record(0x90 | int(channel), int(note), int(velocity))

        def note_off(self, channel, note, velocity=0):
            self._record(0x80 | int(channel), int(note), int(velocity))

        def control_change(self, channel, control, value):
            self._record(0xB0 | int(channel), int(control), int(value))

        def panic(self):
            events.append({"step": current["step"], "src": owner(), "midi": "panic"})

        def close(self):
            pass

    class FakeOsc:
        def __init__(self, *a, **k):
            pass

        def _record(self, address, value):
            events.append({"step": current["step"], "src": owner(), "osc": str(address), "value": repr(value)})

        def send(self, address, value=None):
            self._record(address, value)

        def send_color(self, address, hex_value):
            self._record(address, hex_value)

        def send_multi(self, address, *values):
            self._record(address, tuple(values))

        def close(self):
            pass

    composition = {"layers": [
        {"clips": [{"video": {"fileinfo": f"clip{j}"}} for j in range(4)]} for _ in range(8)
    ], "video": {"effects": []}}

    class FakeRest:
        def __init__(self, *a, **k):
            pass

        def get_composition(self):
            return copy.deepcopy(composition)

        def get_parameter(self, param_id):
            return {"id": param_id, "value": 0.0}

        def put_parameter(self, param_id, value):
            events.append({"step": current["step"], "src": owner(), "rest_put": repr((param_id, value))})

    def seeded_random(*_a, **_k):
        return random_module.Random(RNG_SEED)

    random_shim = types.SimpleNamespace(Random=seeded_random)
    patched = []
    for name, module in sorted(sys.modules.items()):
        if not name.startswith("windows.engines.") or module is None:
            continue
        if hasattr(module, "OscClient"):
            module.OscClient = FakeOsc
            patched.append(name + ".OscClient")
        if hasattr(module, "ResolumeRestClient"):
            module.ResolumeRestClient = FakeRest
            patched.append(name + ".ResolumeRestClient")
        if getattr(module, "random", None) is random_module:
            module.random = random_shim
            patched.append(name + ".random")

    midi = RecordingMidiOut()
    engines_dir = Path(args.config) / "engines"
    if args.state_mode == "absent":
        registry = registry_module.load_engines(engines_dir, midi)
    elif args.state_mode == "none":
        registry = registry_module.load_engines(engines_dir, midi, state_dir=None)
    else:
        registry = registry_module.load_engines(engines_dir, midi)
    registry.apply_engine_states(script["engine_states"])
    loaded = [{"name": e.name, "type": e.type_name, "active": e.active} for e in registry.engines]
    decisions: list[dict] = []

    for step in script["steps"]:
        current["step"] = step["i"]
        kind, t = step["kind"], step["t"]
        if kind == "tick":
            registry.tick(t)
        elif kind == "clock":
            registry.on_midi_clock(step["message"], t)
        elif kind == "feedback_cc":
            registry.on_midi_in(step["channel"], step["cc"], step["value"], t)
        elif kind == "deck_cc":
            midi.control_change(step["channel"], step["cc"], step["value"])
            registry.on_midi_in(step["channel"], step["cc"], step["value"], t)
        elif kind == "deck_note_on":
            allowed = registry.should_emit_note(step["channel"], step["note"], step["velocity"], t)
            decisions.append({"step": step["i"], "allowed": allowed})
            if allowed:
                midi.note_on(step["channel"], step["note"], step["velocity"])
                registry.on_note_in(step["channel"], step["note"], step["velocity"], t)
        elif kind == "deck_note_off":
            midi.note_off(step["channel"], step["note"], 0)
        elif kind == "axis":
            registry.on_axis_event(step["action"], step["value"], t)
        elif kind == "refresh":
            registry.refresh()
        else:
            raise SystemExit(f"unknown step kind {kind}")
    current["step"] = "shutdown"
    registry.shutdown()

    capture = {
        "tree": str(tree),
        "registry_file": str(loaded_from),
        "python": sys.version,
        "state_mode": args.state_mode,
        "loaded": loaded,
        "patched": patched,
        "socket_attempts": socket_attempts,
        "port_opens": port_opens,
        "decisions": decisions,
        "events": events,
    }
    Path(args.out).write_bytes(canonical(capture) + b"\n")
    return 0


# ---------------------------------------------------------------- script ----


def build_script(section: dict, engine_states: dict, autopilot_cfg: dict) -> dict:
    mappings = section["mappings"]
    settings = section.get("macro_settings", {})

    def note_of(action):
        m = mappings.get(action)
        if not m or m.get("type") != "note":
            raise ValueError(f"preset has no note mapping for {action}")
        return m

    def staged_of(action):
        m = mappings.get(action)
        if not m or m.get("type") != "staged_note_macro":
            raise ValueError(f"preset has no staged_note_macro mapping for {action}")
        return m

    l3 = note_of("LEFT_STICK_CLICK_L3")
    pad_left, pad_right = note_of("L_PAD_LEFT"), note_of("L_PAD_RIGHT")
    long_left, long_right = staged_of("L_PAD_LEFT_LONG_PRESS"), staged_of("L_PAD_RIGHT_LONG_PRESS")
    l4 = mappings.get("L4")
    if not l4 or l4.get("type") != "cc":
        raise ValueError("preset has no cc mapping for L4")

    ap = autopilot_cfg["inputs"]
    ach = ap["channel"]
    steps: list[dict] = []
    now = [0.0]

    def add(kind, **fields):
        steps.append({"i": len(steps), "t": round(now[0], 6), "kind": kind, **fields})

    def advance(seconds, hz=60):
        end = now[0] + seconds
        dt = 1.0 / hz
        while now[0] + dt <= end + 1e-9:
            now[0] += dt
            add("tick")
        now[0] = end

    def beats(count, bpm=120.0):
        per_tick = 60.0 / bpm / 24
        for k in range(count * 24):
            now[0] += per_tick
            add("clock", message="clock")
            if k % 2 == 1:
                add("tick")

    def fb(channel, cc, value):
        add("feedback_cc", channel=channel, cc=cc, value=value)

    def press_note(m, hold=0.1):
        add("deck_note_on", channel=m["channel"], note=m["note"], velocity=m["velocity"])
        advance(hold)
        add("deck_note_off", channel=m["channel"], note=m["note"])

    def press_staged(m, during=None, while_pending=None):
        delay = m.get("macro_delay_ms", settings.get("macro_delay_ms", 80)) / 1000.0
        hold = m.get("modifier_hold_ms", settings.get("modifier_hold_ms", 2000)) / 1000.0
        add("deck_note_on", channel=m["modifier_channel"], note=m["note"], velocity=m["velocity"])
        if while_pending is not None:
            add("deck_note_on", channel=while_pending["channel"], note=while_pending["note"],
                velocity=while_pending["velocity"])
            add("deck_note_off", channel=while_pending["channel"], note=while_pending["note"])
        beats_during = during or 0
        advance(delay)
        add("deck_note_on", channel=m["trigger_channel"], note=m["note"], velocity=m["velocity"])
        if beats_during:
            beats(beats_during)
        advance(max(0.0, hold - delay - beats_during * 0.5))
        add("deck_note_off", channel=m["modifier_channel"], note=m["note"])

    def sweep(action, values):
        for v in values:
            add("axis", action=action, value=v)
            advance(1.0 / 60, hz=60)

    add("tick")
    # --- autopilot: all five inputs on every channel, then beats ------------
    video, fx, logo = ap["video"], ap["fx"], ap["logo"]
    for layer_cc in list(video["layer_ccs"].values())[:3]:
        fb(ach, layer_cc, 127)
    fb(ach, video["cc_beats"], 0)
    fb(ach, video["cc_transition"], 0)
    fb(ach, video["cc_mode"], 1)
    fb(ach, video["cc_enable"], 127)
    for layer_cc in fx["layer_ccs"].values():
        fb(ach, layer_cc, 127)
    fb(ach, fx["cc_beats"], 0)
    fb(ach, fx["cc_transition"], 25)
    fb(ach, fx["cc_mode"], 2)
    fb(ach, fx["cc_enable"], 127)
    for layer_cc in logo["layer_ccs"].values():
        fb(ach, layer_cc, 127)
    fb(ach, logo["cc_beats"], 1)
    fb(ach, logo["cc_transition"], 64)
    fb(ach, logo["cc_mode"], 0)
    fb(ach, logo["cc_enable"], 127)
    add("clock", message="start")
    beats(8)
    # Column triggers through the note-emit filter: long press defers, a
    # second trigger while pending is dropped, the beat re-emits.
    beats(1)
    now[0] += 0.1
    press_staged(long_left, during=2, while_pending=pad_left)
    press_note(pad_left)
    beats(2)
    press_note(pad_right)
    beats(2)
    press_staged(long_right, during=1)
    beats(1)
    # Intent changes mid-run: unselect the visible layer, mode and beats.
    fb(ach, list(video["layer_ccs"].values())[0], 0)
    fb(ach, video["cc_mode"], 2)
    fb(ach, video["cc_beats"], 2)
    fb(ach, fx["cc_mode"], 0)
    fb(ach, logo["cc_transition"], 127)
    beats(12)
    # Pulse stops: fallback clock takes over, then Pulse resumes.
    add("clock", message="stop")
    advance(5.0, hz=30)
    add("clock", message="continue")
    beats(4)
    add("refresh")
    beats(2)
    # All channels off: column notes pass straight through.
    for ch in (video, fx, logo):
        fb(ach, ch["cc_enable"], 0)
    beats(1)
    press_note(pad_left)
    press_staged(long_right)

    # --- l_stick_layer ------------------------------------------------------
    stick = [0, 2000, 3501, 12000, 32767, 20000, -3000, -3501, -18000, -32767, 0]
    sweep("L_STICK_X_AXIS", stick)
    sweep("L_STICK_Y_AXIS", stick)
    add("axis", action="L_STICK_X_AXIS", value=24000)
    press_note(l3)
    sweep("L_STICK_X_AXIS", stick)
    sweep("L_STICK_Y_AXIS", list(reversed(stick)))
    add("axis", action="L_STICK_Y_AXIS", value=-30000)
    add("deck_note_on", channel=(l3["channel"] + 1) % 16, note=l3["note"], velocity=l3["velocity"])
    press_note(l3)
    sweep("L_STICK_X_AXIS", stick)

    # --- gyro_feedback --------------------------------------------------------
    def l4_cc(value):
        add("deck_cc", channel=l4["channel"], cc=l4["cc"], value=value)

    gyro = [0, 50, 150, 400, 700, 900, -120, -600, -1000, 0]
    for axis in ("GYRO_PITCH", "GYRO_YAW", "GYRO_ROLL"):
        sweep(axis, gyro[:3])
    l4_cc(l4["on_value"])
    advance(0.1)
    l4_cc(l4["off_value"])
    for axis in ("GYRO_PITCH", "GYRO_YAW", "GYRO_ROLL"):
        sweep(axis, gyro)
    l4_cc(l4["on_value"])
    advance(0.35)
    for axis in ("GYRO_ROLL", "GYRO_PITCH"):
        sweep(axis, list(reversed(gyro)))
    l4_cc(l4["off_value"])
    add("axis", action="GYRO_STATE_NOW", value=1)
    sweep("GYRO_YAW", gyro)
    l4_cc(l4["on_value"])
    advance(0.05)
    l4_cc(l4["off_value"])
    sweep("GYRO_PITCH", gyro)

    # --- global_color ---------------------------------------------------------
    fb(14, 46, 25)
    for index, cc in enumerate((40, 41, 42, 43, 44, 47, 48, 49, 92, 93, 94, 96, 97, 98)):
        fb(14, cc, index % 10)
        advance(0.05)
    for cc in range(0, 30, 2):
        fb(13, cc, (cc * 7) % 128)
    advance(1.5)
    fb(14, 45, 3)
    fb(14, 46, 0)
    fb(14, 41, 9)
    advance(0.5)
    add("refresh")

    # --- audio_opacity (protocol midi) ----------------------------------------
    for cc, value in ((101, 127), (104, 80), (105, 20), (106, 10), (107, 30), (108, 5), (109, 15)):
        fb(14, cc, value)
    for k in range(180):
        fb(14, 100, 120 if (k // 20) % 2 == 0 else 8)
        advance(1.0 / 30, hz=30)
    for cc in (102, 103, 112, 113):
        fb(14, cc, 127)
        advance(0.7, hz=30)
        fb(14, cc, 0)
        advance(0.7, hz=30)
    fb(14, 101, 0)
    advance(1.0, hz=30)

    # --- everything at once -----------------------------------------------------
    fb(14, 101, 127)
    fb(ach, video["cc_enable"], 127)
    fb(ach, logo["cc_enable"], 127)
    l4_cc(l4["on_value"])
    advance(0.05)
    l4_cc(l4["off_value"])
    for k in range(4):
        add("axis", action="L_STICK_X_AXIS", value=[9000, -26000, 32767, 0][k])
        add("axis", action="GYRO_YAW", value=[300, -800, 600, 0][k])
        fb(14, 100, [127, 3, 90, 0][k])
        press_staged(long_left) if k == 1 else None
        beats(1)
    advance(1.0)
    return {
        "schema": "sdauto-engine-ab-script/1",
        "engine_states": engine_states,
        "steps": steps,
    }


# ------------------------------------------------------------ orchestrator ----


def engine_configs(repo: Path, baseline: str) -> dict[str, dict]:
    """Factory stanzas from the BASELINE revision, loopback-rewritten, identical for every arm."""
    from ab_run import git

    configs = {}
    for engine_type in ENGINE_TYPES:
        raw = json.loads(git(repo, "show", f"{baseline}:config/engines.factory/{engine_type}.json"))
        outputs = raw.setdefault("outputs", {})
        if engine_type == "audio_opacity":
            outputs["protocol"] = "midi"
        if "osc" in outputs or engine_type in ("autopilot", "global_color", "audio_opacity"):
            osc = outputs.setdefault("osc", {})
            osc["host"] = "127.0.0.1"
            osc["port"] = LOOPBACK_OSC_PORT
        if "rest" in outputs:
            outputs["rest"]["base_url"] = f"http://127.0.0.1:{LOOPBACK_REST_PORT}"
        raw["enabled"] = True
        configs[engine_type] = raw
    return configs


def summarize(capture: dict) -> dict:
    counts: dict[str, dict[str, int]] = {}
    kinds: dict[str, set] = {}
    for event in capture["events"]:
        kind = "midi" if "midi" in event else "osc" if "osc" in event else "rest"
        counts.setdefault(event["src"], {}).setdefault(kind, 0)
        counts[event["src"]][kind] += 1
    decisions = capture["decisions"]
    return {
        "events": len(capture["events"]),
        "by_source": counts,
        "filter_allowed": sum(1 for d in decisions if d["allowed"]),
        "filter_deferred_or_dropped": sum(1 for d in decisions if not d["allowed"]),
    }


def compare(a: dict, b: dict) -> dict:
    sources = sorted({e["src"] for e in a["events"]} | {e["src"] for e in b["events"]})
    different = [s for s in sources
                 if [e for e in a["events"] if e["src"] == s] != [e for e in b["events"] if e["src"] == s]]
    first = None
    for index, (left, right) in enumerate(zip(a["events"], b["events"])):
        if left != right:
            first = {"index": index, "a": left, "b": right}
            break
    if first is None and len(a["events"]) != len(b["events"]):
        n = min(len(a["events"]), len(b["events"]))
        first = {"index": n, "a": a["events"][n:n + 1], "b": b["events"][n:n + 1]}
    return {
        "identical_events": a["events"] == b["events"],
        "identical_filter_decisions": a["decisions"] == b["decisions"],
        "events_sha256": {"a": sha(canonical(a["events"])), "b": sha(canonical(b["events"]))},
        "different_sources": different,
        "first_difference": first,
    }


def coverage_table(script: dict, captures: dict[str, dict], judged: tuple[str, ...]) -> list[dict]:
    """Active engines need observations on every judged arm; zero is RED.

    An engine the preset turns OFF must stay silent on every input-driven step:
    only `load` (bind_registry) and `refresh` reach an inactive engine, in
    v0.4.9 as in the candidate.
    """
    kind_of = {s["i"]: s["kind"] for s in script["steps"]}
    states = script.get("engine_states", {})
    rows = []
    for engine_type in ENGINE_TYPES:
        active = states.get(engine_type, True)
        row = {"engine": engine_type, "preset_active": active, "arms": {},
               "input_kinds_with_output": set(), "covered": True}
        for arm, capture in captures.items():
            own = [e for e in capture["events"] if e["src"] == engine_type]
            counts = {k: sum(1 for e in own if k in e) for k in ("midi", "osc")}
            row["arms"][arm] = counts
            kinds = {kind_of.get(e["step"], e["step"]) for e in own}
            row["input_kinds_with_output"] |= kinds
            if arm not in judged:
                continue
            if not active:
                if kinds - {"load", "refresh", "shutdown"}:
                    row["covered"] = False
                continue
            for need in REQUIRED[engine_type]:
                if counts[need] == 0:
                    row["covered"] = False
        if engine_type == "autopilot" and active:
            for arm, capture in captures.items():
                deferred = sum(1 for d in capture["decisions"] if not d["allowed"])
                reemitted = sum(1 for e in capture["events"]
                                if e["src"] == "autopilot" and e.get("midi", "")[:2] == "90")
                row["arms"][arm]["filter_deferred_or_dropped"] = deferred
                row["arms"][arm]["column_notes_reemitted"] = reemitted
                row["arms"][arm]["column_notes_dropped"] = deferred - reemitted
                if (reemitted == 0 or deferred - reemitted <= 0) and arm in judged:
                    row["covered"] = False
        row["input_kinds_with_output"] = sorted(str(k) for k in row["input_kinds_with_output"])
        rows.append(row)
    return rows


def run(args) -> dict:
    sys.path.insert(0, str(KIT))
    from ab_run import archive, validate_scratch, verify_preset, write_result  # noqa: F401
    from deck_script import read_json, verify_fixtures

    repo = args.repo.resolve()
    verified = verify_fixtures(args.fixtures)
    preset = args.preset.resolve()
    verify_preset(repo, args.candidate, preset, verified)
    raw = read_json(preset)
    if "sections" in raw:
        if not args.section:
            raise ValueError("Sectioned fixture needs --section")
        section = raw["sections"][args.section]
    else:
        if args.section:
            raise ValueError("--section requires a sectioned fixture")
        section = raw
    block = section.get("engines", {})
    engine_states = {t: bool(block[t]) for t in ENGINE_TYPES if t in block}
    missing_states = [t for t in ENGINE_TYPES if t not in block]

    validate_scratch(args.scratch)
    args.scratch.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="engine-ab-", dir=args.scratch)).resolve()
    configs = engine_configs(repo, args.baseline)
    script = build_script(section, engine_states, configs["autopilot"])
    script_bytes = canonical(script) + b"\n"
    (work / "script.json").write_bytes(script_bytes)
    runner = work / "engine_ab_runner.py"
    runner.write_bytes(Path(__file__).read_bytes())

    result = {
        "schema": "sdauto-engine-ab/1",
        "baseline": args.baseline,
        "candidate": args.candidate,
        "control": args.control,
        "preset": str(preset),
        "section": args.section,
        "engine_states": engine_states,
        "engine_states_missing_from_preset": missing_states,
        "fixture_sha256": verified,
        "instrument_sha256": {n: sha((KIT / n).read_bytes()) for n in ("engine_ab.py", "ab_run.py", "deck_script.py")},
        "config_sha256": {t: sha(canonical(c)) for t, c in configs.items()},
        "script_sha256": sha(script_bytes),
        "script_steps": len(script["steps"]),
        "work": str(work),
        "arms": {},
        "comparisons": {},
        "passed": False,
    }
    arms = (("A", args.baseline, "absent"), ("B_nostate", args.candidate, "none"), ("B_state", args.candidate, "derived"))
    captures = {}
    for name, rev, state_mode in arms:
        arm_dir = work / name
        arm_dir.mkdir()
        identity = archive(repo, rev, arm_dir / "tree")
        if args.control and name != "A":
            family, rel, old, new = CONTROLS[args.control]
            target = arm_dir / "tree" / rel
            text = target.read_text(encoding="utf-8")
            if text.count(old) != 1:
                raise ValueError(f"control anchor not found once in {rel}")
            target.write_text(text.replace(old, new), encoding="utf-8")
            identity["control_edit"] = {"file": rel, "old": old, "new": new}
        engines_dir = arm_dir / "config" / "engines"
        engines_dir.mkdir(parents=True)
        for engine_type, config in configs.items():
            (engines_dir / f"{engine_type}.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        state_dir = arm_dir / "config" / "state"
        if state_mode == "derived":
            state_dir.mkdir()
        out = arm_dir / "capture.json"
        log = arm_dir / "arm.log"
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"}
        if os.name == "nt":
            env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
        with open(log, "wb") as handle:
            process = subprocess.Popen(
                [args.python, "-B", str(runner), "--runner", "--tree", str(arm_dir / "tree"),
                 "--config", str(arm_dir / "config"), "--script", str(work / "script.json"),
                 "--state-mode", state_mode, "--out", str(out)],
                cwd=arm_dir, stdout=handle, stderr=subprocess.STDOUT, env=env,
            )
            try:
                exit_code = process.wait(timeout=600)
            except subprocess.TimeoutExpired:
                process.kill()
                exit_code = process.wait()
        arm = {"revision": identity, "state_mode": state_mode, "pid": process.pid, "exit": exit_code,
               "exited": process.returncode is not None, "log": str(log)}
        if exit_code != 0 or not out.exists():
            arm["error"] = "arm failed"
            result["arms"][name] = arm
            result["error"] = f"arm {name} failed (exit {exit_code}); see {log}"
            return result
        capture = json.loads(out.read_text(encoding="utf-8"))
        captures[name] = capture
        arm.update({
            "capture_sha256": sha(out.read_bytes()),
            "registry_file": capture["registry_file"],
            "loaded": capture["loaded"],
            "patched": capture["patched"],
            "socket_attempts": len(capture["socket_attempts"]),
            "port_opens": len(capture["port_opens"]),
            "summary": summarize(capture),
            "state_dir_listing": sorted(p.name for p in state_dir.iterdir()) if state_dir.exists() else None,
        })
        result["arms"][name] = arm

    problems = []
    for name, arm in result["arms"].items():
        if arm["socket_attempts"] or arm["port_opens"]:
            problems.append(f"{name}: a socket or MIDI port was attempted")
        loaded_types = sorted(e["type"] for e in arm["loaded"])
        if loaded_types != sorted(ENGINE_TYPES):
            problems.append(f"{name}: loaded {loaded_types}")
    if result["arms"]["B_nostate"]["state_dir_listing"] is not None:
        problems.append("B_nostate: a state dir exists")
    if engine_states.get("autopilot", True) and "autopilot_channels.local.json" not in (
        result["arms"]["B_state"]["state_dir_listing"] or []
    ):
        # An enabled arm that never persisted did not exercise persistence.
        problems.append("B_state: persistence enabled but no state file was written")
    for name in ("B_nostate", "B_state"):
        result["comparisons"][f"A_vs_{name}"] = compare(captures["A"], captures[name])
    # A control's mutated arms are expected to lose observations; judge A only.
    judged = ("A",) if args.control else tuple(captures)
    result["coverage_judged_arms"] = list(judged)
    table = coverage_table(script, captures, judged)
    result["coverage"] = table
    uncovered = [row["engine"] for row in table if not row["covered"]]
    if uncovered:
        problems.append(f"zero observations for {uncovered}")
    result["problems"] = problems
    identical = all(c["identical_events"] and c["identical_filter_decisions"] for c in result["comparisons"].values())
    result["passed"] = identical and not problems and not args.control
    if args.control:
        family = CONTROLS[args.control][0]
        # "receiver" rows change too when the autopilot filter decides differently.
        result["control_expected"] = not problems and all(
            not c["identical_events"] and [s for s in c["different_sources"] if s != "receiver"] == [family]
            for c in result["comparisons"].values()
        )
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runner", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--tree", help=argparse.SUPPRESS)
    parser.add_argument("--config", help=argparse.SUPPRESS)
    parser.add_argument("--state-mode", choices=("absent", "none", "derived"), help=argparse.SUPPRESS)
    parser.add_argument("--script", help=argparse.SUPPRESS)
    parser.add_argument("--candidate")
    parser.add_argument("--baseline", default="v0.4.9")
    parser.add_argument("--preset", type=Path)
    parser.add_argument("--section")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--fixtures", type=Path, default=ROOT / ".showready/fixtures")
    default_scratch = (Path(os.environ["LOCALAPPDATA"]) / "Temp/sdwin/engine-ab") if os.name == "nt" else Path("/tmp/sdauto-engine-ab")
    parser.add_argument("--scratch", type=Path, default=default_scratch)
    parser.add_argument("--python", default=sys.executable, help="interpreter for the arms (the checkout venv)")
    parser.add_argument("--control", choices=sorted(CONTROLS))
    args = parser.parse_args(argv)
    if args.runner:
        return run_arm(args)
    if not (args.candidate and args.preset and args.out):
        parser.error("--candidate, --preset and --out are required")
    started = time.time()
    try:
        result = run(args)
    except Exception as exc:  # noqa: BLE001 - a refused input is a nonzero result
        result = {"schema": "sdauto-engine-ab/1", "passed": False, "error": f"{type(exc).__name__}: {exc}"}
    result["elapsed_seconds"] = round(time.time() - started, 3)
    sys.path.insert(0, str(KIT))
    from ab_run import write_result

    output = write_result(args.out, result)
    print(json.dumps({
        "result": str(output),
        "passed": result["passed"],
        "control": result.get("control"),
        "control_expected": result.get("control_expected"),
        "error": result.get("error"),
        "problems": result.get("problems"),
        "comparisons": {k: {f: v[f] for f in ("identical_events", "identical_filter_decisions", "different_sources")}
                        for k, v in result.get("comparisons", {}).items()},
        "coverage": [{"engine": r["engine"], "covered": r["covered"], "arms": r["arms"]} for r in result.get("coverage", [])],
    }, indent=1))
    if args.control:
        return 1 if result.get("control_expected") else 2
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
