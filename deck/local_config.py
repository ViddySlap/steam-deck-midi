"""Deck-side local settings and sender preset helpers."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field, replace


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
    active_targets: list[str] = field(default_factory=list)
    api_bind: str = "127.0.0.1"
    api_port: int = 7724
    api_token: str | None = None
    # "keys": buttons come from Steam Input keycodes over XI2 (legacy path).
    # "hidraw": the sender streams raw button state and the receiver decodes
    # layers and long press (ADR 0003). Needs a receiver that understands it.
    button_source: str = "keys"


BUTTON_SOURCES = ("keys", "hidraw")


def validate_ipv4_address(value: str) -> str:
    try:
        parsed = ipaddress.ip_address(value.strip())
    except ValueError as exc:
        raise ValueError(f"invalid IPv4 address: {value}") from exc
    if parsed.version != 4:
        raise ValueError(f"invalid IPv4 address: {value}")
    return str(parsed)


def validate_target_host(value: str) -> str:
    """Accept IPv4 or ASCII DNS labels, including .local and single-label hosts."""
    value = value.strip()
    try:
        return validate_ipv4_address(value)
    except ValueError:
        pass
    hostname = value[:-1] if value.endswith(".") else value
    labels = hostname.split(".")
    if (not hostname or len(hostname) > 253
            or re.fullmatch(r"[0-9.]+", hostname)
            or any(not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                   for label in labels)):
        raise ValueError(f"invalid IPv4 address or hostname: {value}")
    return value


def _validate_active_targets(names: list[str], presets: list[TargetPreset]) -> None:
    if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
        raise ValueError("active_targets must be a list of preset names")
    if len(names) != len(set(names)):
        raise ValueError("active_targets must not repeat a preset name")
    for name in names:
        matches = sum(preset.name == name for preset in presets)
        if matches != 1:
            raise ValueError(f"active_targets has an unknown or ambiguous preset name: {name}")


def with_active_targets(settings: DeckRuntimeSettings, names: list[str]) -> DeckRuntimeSettings:
    _validate_active_targets(names, settings.presets)
    return replace(settings, active_targets=list(names))


def load_runtime_settings(path: str) -> DeckRuntimeSettings:
    with open(path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)

    return runtime_settings_from_dict(raw)


def runtime_settings_from_dict(raw: dict) -> DeckRuntimeSettings:
    if not isinstance(raw, dict):
        raise ValueError("settings must be an object")
    device_id = raw.get("device_id", "5")
    bindings_path = raw.get("bindings_path", "config/deck_bindings.json")
    actions_path = raw.get("actions_path", "config/actions.yaml")
    default_port = raw.get("default_port", 45123)
    profile_name = raw.get("profile_name")
    profile_hash = raw.get("profile_hash")
    presets_raw = raw.get("presets", [])
    active_targets = raw.get("active_targets", [])

    api_bind = raw.get("api_bind", "127.0.0.1")
    api_port = raw.get("api_port", 7724)
    api_token = raw.get("api_token")
    button_source = raw.get("button_source", "keys")
    if button_source not in BUTTON_SOURCES:
        raise ValueError(f"button_source must be one of {', '.join(BUTTON_SOURCES)}")
    validate_api_bind(api_bind)
    if type(api_port) is not int or not 1 <= api_port <= 65535:
        raise ValueError("api_port must be an integer between 1 and 65535")
    if api_token is not None and (not isinstance(api_token, str) or not api_token.strip()
                                  or not api_token.isascii() or not api_token.isprintable()):
        raise ValueError("api_token must be a non-empty printable ASCII string")
    if device_id is not None:
        if not isinstance(device_id, (str, int)) or isinstance(device_id, bool):
            raise ValueError("device_id must be a string or integer")
        device_id = str(device_id).strip()
        if not device_id:
            device_id = None
    if not isinstance(bindings_path, str) or not bindings_path:
        raise ValueError("bindings_path must be a non-empty string")
    if not isinstance(actions_path, str) or not actions_path:
        raise ValueError("actions_path must be a non-empty string")
    if type(default_port) is not int or not (1 <= default_port <= 65535):
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
        if type(port) is not int or not (1 <= port <= 65535):
            raise ValueError("preset port must be an integer between 1 and 65535")
        presets.append(TargetPreset(name=name.strip(), host=validate_target_host(host), port=port))

    _validate_active_targets(active_targets, presets)

    return DeckRuntimeSettings(
        device_id=device_id,
        bindings_path=bindings_path,
        actions_path=actions_path,
        default_port=default_port,
        profile_name=profile_name,
        profile_hash=profile_hash,
        presets=presets,
        active_targets=active_targets,
        api_bind=api_bind,
        api_port=api_port,
        api_token=api_token,
        button_source=button_source,
    )


def write_runtime_settings(path: str, settings: DeckRuntimeSettings) -> None:
    if os.path.isdir(path):
        raise ValueError(f"settings path points to a directory, not a file: {path}")
    _validate_active_targets(settings.active_targets, settings.presets)

    payload = {
        "device_id": settings.device_id,
        "bindings_path": settings.bindings_path,
        "actions_path": settings.actions_path,
        "default_port": settings.default_port,
        "profile_name": settings.profile_name,
        "profile_hash": settings.profile_hash,
        "active_targets": settings.active_targets,
        "api_bind": settings.api_bind,
        "api_port": settings.api_port,
        "api_token": settings.api_token,
        "button_source": settings.button_source,
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


def describe_preset(index: int, preset: TargetPreset, active: bool = False) -> str:
    marker = " [active]" if active else ""
    return f"{index}. {preset.name} ({preset.host}:{preset.port}){marker}"


def with_device_id(settings: DeckRuntimeSettings, device_id: str) -> DeckRuntimeSettings:
    normalized = device_id.strip()
    if not normalized:
        raise ValueError("device id must be a non-empty string")
    return replace(
        settings,
        device_id=normalized,
        bindings_path=settings.bindings_path,
        actions_path=settings.actions_path,
        default_port=settings.default_port,
        profile_name=settings.profile_name,
        profile_hash=settings.profile_hash,
        presets=settings.presets,
        active_targets=settings.active_targets,
    )


def with_added_preset(
    settings: DeckRuntimeSettings, *, name: str, host: str
) -> DeckRuntimeSettings:
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("target name must be a non-empty string")
    if any(preset.name == normalized_name for preset in settings.presets):
        raise ValueError(f"preset name already exists: {normalized_name}")
    normalized_host = validate_target_host(host)
    updated_presets = settings.presets + [
        TargetPreset(name=normalized_name, host=normalized_host, port=settings.default_port)
    ]
    return replace(
        settings,
        device_id=settings.device_id,
        bindings_path=settings.bindings_path,
        actions_path=settings.actions_path,
        default_port=settings.default_port,
        profile_name=settings.profile_name,
        profile_hash=settings.profile_hash,
        presets=updated_presets,
        active_targets=settings.active_targets,
    )


def with_renamed_preset(
    settings: DeckRuntimeSettings, index: int, name: str
) -> DeckRuntimeSettings:
    normalized = name.strip()
    if not normalized:
        raise ValueError("preset name must be a non-empty string")
    if not (0 <= index < len(settings.presets)):
        raise ValueError(f"preset index out of range: {index}")
    if any(preset.name == normalized for i, preset in enumerate(settings.presets) if i != index):
        raise ValueError(f"preset name already exists: {normalized}")
    updated = list(settings.presets)
    updated[index] = TargetPreset(
        name=normalized, host=updated[index].host, port=updated[index].port
    )
    return replace(
        settings,
        device_id=settings.device_id,
        bindings_path=settings.bindings_path,
        actions_path=settings.actions_path,
        default_port=settings.default_port,
        profile_name=settings.profile_name,
        profile_hash=settings.profile_hash,
        presets=updated,
        active_targets=[normalized if name == settings.presets[index].name else name
                        for name in settings.active_targets],
    )


def with_deleted_preset(settings: DeckRuntimeSettings, index: int) -> DeckRuntimeSettings:
    if not (0 <= index < len(settings.presets)):
        raise ValueError(f"preset index out of range: {index}")
    updated = [p for i, p in enumerate(settings.presets) if i != index]
    return replace(
        settings,
        device_id=settings.device_id,
        bindings_path=settings.bindings_path,
        actions_path=settings.actions_path,
        default_port=settings.default_port,
        profile_name=settings.profile_name,
        profile_hash=settings.profile_hash,
        presets=updated,
        active_targets=[name for name in settings.active_targets
                        if name != settings.presets[index].name],
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


def validate_api_bind(bind: str) -> str:
    """Use literal IPv4 binds so authentication cannot depend on changing DNS."""
    if bind == "localhost":
        return "127.0.0.1"
    if not isinstance(bind, str):
        raise ValueError("api_bind must be an IPv4 address or localhost")
    return validate_ipv4_address(bind)


def api_is_loopback(bind: str) -> bool:
    return ipaddress.ip_address(validate_api_bind(bind)).is_loopback
