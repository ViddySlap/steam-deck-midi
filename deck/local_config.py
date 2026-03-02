"""Deck-side local settings and sender preset helpers."""

from __future__ import annotations

import ipaddress
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass


@dataclass(frozen=True)
class TargetPreset:
    name: str
    host: str
    port: int = 45123


@dataclass(frozen=True)
class DeckRuntimeSettings:
    device_id: str | None
    bindings_path: str
    actions_path: str
    default_port: int
    profile_name: str | None
    profile_hash: str | None
    presets: list[TargetPreset]


def validate_ipv4_address(value: str) -> str:
    try:
        parsed = ipaddress.ip_address(value.strip())
    except ValueError as exc:
        raise ValueError(f"invalid IPv4 address: {value}") from exc
    if parsed.version != 4:
        raise ValueError(f"invalid IPv4 address: {value}")
    return str(parsed)


def load_runtime_settings(path: str) -> DeckRuntimeSettings:
    with open(path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)

    device_id = raw.get("device_id")
    bindings_path = raw.get("bindings_path", "config/deck_bindings.json")
    actions_path = raw.get("actions_path", "config/actions.yaml")
    default_port = raw.get("default_port", 45123)
    profile_name = raw.get("profile_name")
    profile_hash = raw.get("profile_hash")
    presets_raw = raw.get("presets", [])

    if device_id is not None:
        device_id = str(device_id).strip()
        if not device_id:
            device_id = None
    if not isinstance(bindings_path, str) or not bindings_path:
        raise ValueError("bindings_path must be a non-empty string")
    if not isinstance(actions_path, str) or not actions_path:
        raise ValueError("actions_path must be a non-empty string")
    if not isinstance(default_port, int) or not (1 <= default_port <= 65535):
        raise ValueError("default_port must be an integer between 1 and 65535")
    if profile_name is not None and not isinstance(profile_name, str):
        raise ValueError("profile_name must be a string when provided")
    if profile_hash is not None and not isinstance(profile_hash, str):
        raise ValueError("profile_hash must be a string when provided")
    if not isinstance(presets_raw, list):
        raise ValueError("presets must be a list")

    presets: list[TargetPreset] = []
    for entry in presets_raw:
        if not isinstance(entry, dict):
            raise ValueError("each preset must be an object")
        name = entry.get("name")
        host = entry.get("host")
        port = entry.get("port", default_port)
        if not isinstance(name, str) or not name.strip():
            raise ValueError("preset name must be a non-empty string")
        if not isinstance(host, str) or not host.strip():
            raise ValueError("preset host must be a non-empty string")
        if not isinstance(port, int) or not (1 <= port <= 65535):
            raise ValueError("preset port must be an integer between 1 and 65535")
        presets.append(TargetPreset(name=name.strip(), host=host.strip(), port=port))

    return DeckRuntimeSettings(
        device_id=device_id,
        bindings_path=bindings_path,
        actions_path=actions_path,
        default_port=default_port,
        profile_name=profile_name,
        profile_hash=profile_hash,
        presets=presets,
    )


def write_runtime_settings(path: str, settings: DeckRuntimeSettings) -> None:
    if os.path.isdir(path):
        raise ValueError(f"settings path points to a directory, not a file: {path}")

    payload = {
        "device_id": settings.device_id,
        "bindings_path": settings.bindings_path,
        "actions_path": settings.actions_path,
        "default_port": settings.default_port,
        "profile_name": settings.profile_name,
        "profile_hash": settings.profile_hash,
        "presets": [
            {"name": preset.name, "host": preset.host, "port": preset.port}
            for preset in settings.presets
        ],
    }

    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=directory
    ) as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
        temp_path = handle.name
    os.replace(temp_path, path)


def ensure_local_settings(
    local_path: str, example_path: str
) -> DeckRuntimeSettings:
    if not os.path.exists(local_path):
        settings = load_runtime_settings(example_path)
        write_runtime_settings(local_path, settings)
        return settings
    return load_runtime_settings(local_path)


def save_runtime_settings(path: str, settings: DeckRuntimeSettings) -> None:
    write_runtime_settings(path, settings)


def describe_preset(index: int, preset: TargetPreset) -> str:
    return f"{index}. {preset.name} ({preset.host}:{preset.port})"


def with_device_id(settings: DeckRuntimeSettings, device_id: str) -> DeckRuntimeSettings:
    normalized = device_id.strip()
    if not normalized:
        raise ValueError("device id must be a non-empty string")
    return DeckRuntimeSettings(
        device_id=normalized,
        bindings_path=settings.bindings_path,
        actions_path=settings.actions_path,
        default_port=settings.default_port,
        profile_name=settings.profile_name,
        profile_hash=settings.profile_hash,
        presets=settings.presets,
    )


def with_added_preset(
    settings: DeckRuntimeSettings, *, name: str, host: str
) -> DeckRuntimeSettings:
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("target name must be a non-empty string")
    normalized_host = validate_ipv4_address(host)
    updated_presets = settings.presets + [
        TargetPreset(name=normalized_name, host=normalized_host, port=settings.default_port)
    ]
    return DeckRuntimeSettings(
        device_id=settings.device_id,
        bindings_path=settings.bindings_path,
        actions_path=settings.actions_path,
        default_port=settings.default_port,
        profile_name=settings.profile_name,
        profile_hash=settings.profile_hash,
        presets=updated_presets,
    )


def get_xinput_list_output() -> str:
    try:
        result = subprocess.run(
            ["xinput", "list"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()
