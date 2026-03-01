"""Configuration loading and validation for the Windows receiver."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    """Raised when the Windows MIDI map is invalid."""


@dataclass(frozen=True)
class NoteMapping:
    action: str
    kind: str
    channel: int
    note: int
    velocity: int = 127


@dataclass(frozen=True)
class ControlChangeMapping:
    action: str
    kind: str
    channel: int
    cc: int
    on_value: int = 127
    off_value: int = 0


MidiMapping = NoteMapping | ControlChangeMapping


def load_midi_map(path: str | Path) -> dict[str, MidiMapping]:
    config_path = Path(path)
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"mapping file not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"mapping file is not valid JSON: {config_path}") from exc

    mappings = raw.get("mappings")
    if not isinstance(mappings, dict):
        raise ConfigError("mapping file must contain an object at 'mappings'")

    validated: dict[str, MidiMapping] = {}
    for action, spec in mappings.items():
        if not isinstance(action, str) or not action:
            raise ConfigError("mapping action keys must be non-empty strings")
        if not isinstance(spec, dict):
            raise ConfigError(f"mapping for {action} must be an object")
        validated[action] = _parse_mapping(action, spec)

    return validated


def _parse_mapping(action: str, spec: dict[str, object]) -> MidiMapping:
    kind = spec.get("type")
    if kind == "note":
        channel = _read_byte(spec, "channel", maximum=15, default=0)
        note = _read_byte(spec, "note")
        velocity = _read_byte(spec, "velocity", default=127)
        return NoteMapping(
            action=action,
            kind="note",
            channel=channel,
            note=note,
            velocity=velocity,
        )
    if kind == "cc":
        channel = _read_byte(spec, "channel", maximum=15, default=0)
        cc = _read_byte(spec, "cc")
        on_value = _read_byte(spec, "on_value", default=127)
        off_value = _read_byte(spec, "off_value", default=0)
        return ControlChangeMapping(
            action=action,
            kind="cc",
            channel=channel,
            cc=cc,
            on_value=on_value,
            off_value=off_value,
        )
    raise ConfigError(f"mapping for {action} must have type 'note' or 'cc'")


def _read_byte(
    spec: dict[str, object],
    key: str,
    *,
    maximum: int = 127,
    default: int | None = None,
) -> int:
    value = spec.get(key, default)
    if not isinstance(value, int):
        raise ConfigError(f"{key} must be an integer")
    if value < 0 or value > maximum:
        raise ConfigError(f"{key} must be between 0 and {maximum}")
    return value
