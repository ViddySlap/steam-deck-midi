"""GET/PUT /api/engines/<type>/config: read, write and live-apply one stanza.

A PUT validates by constructing the engine class from the new stanza in
isolation (a MidiOut that sends nothing, no registry, no state dir), then
hands one task to the receiver thread (windows/receiver_tasks.py). That task
writes config/engines/<type>.json and swaps the live instance through
EngineRegistry.replace, so MIDI dispatch never sees a half-built engine.

Only types whose teardown and bind are self-contained are swapped live.
Every other type answers 409 restart_required and writes nothing.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from windows.engines.registry import (
    build_engine,
    effective_engine_spec,
    engine_class,
)
from windows.midi import MidiOut
from windows.receiver_tasks import ReceiverTaskTimeout

LIVE_SWAPPABLE_TYPES: frozenset[str] = frozenset({
    "audio_opacity",
    "autopilot",
    "autopilot_ptz",
    "global_color",
    "gyro_feedback",
    "l_stick_layer",
    "ptz_visca",
})

RESTART_REQUIRED_REASONS: dict[str, str] = {
    "steam_input_layer_tracker": (
        "bumper_blast, chaser_stack_dispatcher and flash_blast hold a reference to the "
        "tracker instance and its observer list has no unregister"
    ),
    "bumper_blast": "registers an observer on the layer tracker that cannot be unregistered",
    "chaser_stack_dispatcher": "registers an observer on the layer tracker that cannot be unregistered",
    "flash_blast": "registers an observer on the layer tracker that cannot be unregistered",
    "nestdrop": "shutdown does not join in-flight press threads that use a process-wide lock",
    "osc_sync": (
        "shutdown joins an in-flight sync pass for up to 5 s, which would stall MIDI on "
        "the receiver thread while the pass holds composition master at 0"
    ),
    "stageflow_bridge": "shutdown is a no-op: its OSC socket and rescan thread would outlive the swap",
}


class _SilentMidiOut(MidiOut):
    """MidiOut for the isolation probe: accepts and drops everything."""

    @property
    def port_name(self) -> str:
        return "validation-probe"

    def note_on(self, channel: int, note: int, velocity: int) -> None:
        pass

    def note_off(self, channel: int, note: int, velocity: int = 0) -> None:
        pass

    def control_change(self, channel: int, control: int, value: int) -> None:
        pass


class _ApplyFailed(RuntimeError):
    pass


def get_engine_config(registry: Any, type_name: str) -> tuple[int, dict]:
    if registry is None or registry.user_dir is None:
        return 404, {"error": "no engine registry"}
    if engine_class(type_name) is None:
        return 404, {"error": f"unknown engine type: {type_name}"}
    found = effective_engine_spec(registry.user_dir, type_name)
    if found is None:
        return 404, {"error": f"no config for engine type: {type_name}"}
    return 200, {
        "type": type_name,
        "source": found["source"],
        "path": str(found["path"]),
        "user_files": found["user_files"],
        "spec": found["spec"],
        "loaded": registry.get_by_type(type_name) is not None,
        "live_swappable": type_name in LIVE_SWAPPABLE_TYPES,
        "restart_required_reason": RESTART_REQUIRED_REASONS.get(type_name),
    }


def put_engine_config(registry: Any, receiver_tasks: Any, type_name: str, body: object) -> tuple[int, dict]:
    if registry is None or registry.user_dir is None:
        return 404, {"error": "no engine registry"}
    if engine_class(type_name) is None:
        return 404, {"error": f"unknown engine type: {type_name}"}
    if type_name not in LIVE_SWAPPABLE_TYPES:
        return 409, {"error": "restart_required", "type": type_name,
                     "reason": RESTART_REQUIRED_REASONS.get(type_name, "not live-swappable")}
    if not isinstance(body, dict):
        return 400, {"error": "expected a JSON object engine stanza"}
    if body.get("type", type_name) != type_name:
        return 400, {"error": f"stanza type {body.get('type')!r} does not match {type_name!r}"}
    spec = {**body, "type": type_name}
    if not spec.get("enabled", True):
        return 409, {"error": "restart_required", "type": type_name,
                     "reason": "enabled=false unloads the engine; the live API only replaces a loaded engine"}
    target = registry.user_dir / f"{type_name}.json"
    found = effective_engine_spec(registry.user_dir, type_name)
    others = [name for name in (found or {}).get("user_files", []) if name != target.name]
    if others:
        return 409, {"error": "config_file_conflict", "type": type_name, "files": others,
                     "reason": f"another user file declares this type; only {target.name} is written"}
    if registry.get_by_type(type_name) is None:
        return 409, {"error": "restart_required", "type": type_name,
                     "reason": "engine is not loaded; the live API only replaces a loaded engine"}
    if receiver_tasks is None:
        return 503, {"error": "live apply is unavailable (no receiver loop); nothing written"}

    try:
        # Isolation probe. Discarded without shutdown(): some engines' shutdown
        # sends (ptz_visca VISCA stops), and construction starts no threads.
        build_engine(spec, _SilentMidiOut(), state_dir=None)
    except Exception as exc:  # noqa: BLE001 - the message is the answer
        return 400, {"error": f"invalid {type_name} config: {exc}"}

    text = json.dumps(spec, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=registry.user_dir,
                                     prefix=f".{type_name}-", suffix=".tmp",
                                     delete=False, newline="") as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(text)
        tmp.flush()
        os.fsync(tmp.fileno())

    def apply_on_receiver_thread():
        current = registry.get_by_type(type_name)
        if current is None:
            raise _ApplyFailed("engine was unloaded before the change applied; nothing written")
        current.flush_state()
        previous = target.read_bytes() if target.exists() else None
        os.replace(tmp_path, target)
        try:
            new = build_engine(spec, registry.midi_out, state_dir=registry.state_dir)
        except Exception as exc:
            _restore_file(target, previous)
            raise _ApplyFailed(f"could not build {type_name}: {exc}; previous engine kept, file unchanged") from exc
        active = current.active
        registry.replace(current, new)
        new.set_active(active)
        return new

    try:
        new = receiver_tasks.run(apply_on_receiver_thread)
    except ReceiverTaskTimeout:
        return 503, {"error": "receiver loop did not apply the change; nothing written"}
    except _ApplyFailed as exc:
        return 500, {"error": str(exc)}
    except OSError as exc:
        return 500, {"error": f"could not write {target}: {exc}; nothing written"}
    finally:
        tmp_path.unlink(missing_ok=True)
    return 200, {"ok": True, "type": type_name, "source": "user", "path": str(target),
                 "spec": spec, "active": new.active}


def _restore_file(target: Path, previous: bytes | None) -> None:
    if previous is None:
        target.unlink(missing_ok=True)
        return
    with tempfile.NamedTemporaryFile("wb", dir=target.parent, prefix=f".{target.stem}-",
                                     suffix=".tmp", delete=False) as tmp:
        tmp.write(previous)
    os.replace(tmp.name, target)
