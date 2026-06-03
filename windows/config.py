"""Configuration loading and validation for the Windows receiver."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(ValueError):
    """Raised when the Windows MIDI map is invalid."""


@dataclass(frozen=True)
class AnalogSettings:
    update_hz: float = 60.0
    deadzone: int = 1000
    curve: str = "linear"


@dataclass(frozen=True)
class MacroSettings:
    fade_duration_seconds: float = 2.0
    update_hz: float = 30.0
    min_value: int = 0
    max_value: int = 127
    feedback_match_tolerance: int = 2
    macro_delay_ms: int = 80
    modifier_hold_ms: int = 2000
    layer_refresh_ms: int = 500

    @property
    def step_interval_seconds(self) -> float:
        return 1.0 / self.update_hz


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


@dataclass(frozen=True)
class MacroCCMapping:
    action: str
    kind: str
    channel: int
    cc: int
    gesture: str
    fade_duration_seconds: float | None = None


@dataclass(frozen=True)
class RelativeCCMapping:
    action: str
    kind: str
    channel: int
    cc: int
    step_value: int
    repeat_interval_ms: int = 40


@dataclass(frozen=True)
class StagedNoteMacroMapping:
    action: str
    kind: str
    note: int
    modifier_channel: int = 0
    trigger_channel: int = 1
    velocity: int = 127
    refresh_actions: tuple[str, ...] = ()
    macro_delay_ms: int | None = None
    modifier_hold_ms: int | None = None


@dataclass(frozen=True)
class AxisToCCMapping:
    action: str
    kind: str
    channel: int
    cc: int
    input_range: tuple[int, int]
    output_range: tuple[int, int]
    deadzone: int
    curve: str


@dataclass(frozen=True)
class AxisSplitCCMapping:
    action: str
    kind: str
    channel: int
    cc_positive: int
    cc_negative: int
    input_max: int
    deadzone: int
    curve: str


MidiMapping = (
    NoteMapping
    | ControlChangeMapping
    | MacroCCMapping
    | RelativeCCMapping
    | StagedNoteMacroMapping
    | AxisToCCMapping
    | AxisSplitCCMapping
)


@dataclass(frozen=True)
class ReceiverConfig:
    mappings: dict[str, MidiMapping]
    macro_settings: MacroSettings
    analog_settings: AnalogSettings = field(default_factory=AnalogSettings)
    # Per-preset engine on/off overrides: {engine_type: active_bool}. Absent or
    # malformed entries fall back to each engine's own config `enabled` default.
    # Lets a preset (e.g. "PTZ") disable show engines that "EDM Show" leaves on.
    engine_states: dict[str, bool] = field(default_factory=dict)


def load_effective_midi_map(base_path: str | Path, local_path: str | Path) -> ReceiverConfig:
    """Load base map merged with local override if it exists."""
    base = Path(base_path)
    local = Path(local_path)
    if not local.exists():
        return load_midi_map(base)
    try:
        base_raw = json.loads(base.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"mapping file not found: {base}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"mapping file is not valid JSON: {base}") from exc
    try:
        local_raw = json.loads(local.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"local mapping file is not valid JSON: {local}") from exc

    merged: dict[str, object] = {}
    if isinstance(base_raw.get("macro_settings"), dict):
        merged["macro_settings"] = base_raw["macro_settings"]
    if isinstance(local_raw.get("macro_settings"), dict):
        merged["macro_settings"] = {
            **(merged.get("macro_settings") or {}),  # type: ignore[dict-item]
            **local_raw["macro_settings"],
        }
    if isinstance(base_raw.get("analog_settings"), dict):
        merged["analog_settings"] = base_raw["analog_settings"]
    if isinstance(local_raw.get("analog_settings"), dict):
        merged["analog_settings"] = {
            **(merged.get("analog_settings") or {}),  # type: ignore[dict-item]
            **local_raw["analog_settings"],
        }
    base_mappings = base_raw.get("mappings") or {}
    local_mappings = local_raw.get("mappings") or {}
    merged["mappings"] = {**base_mappings, **local_mappings}

    import tempfile, os  # noqa: E401
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(merged, tmp)
        tmp_path = tmp.name
    try:
        return load_midi_map(tmp_path)
    finally:
        os.unlink(tmp_path)


def load_midi_map(path: str | Path) -> ReceiverConfig:
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

    macro_settings = _parse_macro_settings(raw.get("macro_settings"))
    analog_settings = _parse_analog_settings(raw.get("analog_settings"))
    engine_states = _parse_engine_states(raw.get("engines"))

    validated: dict[str, MidiMapping] = {}
    for action, spec in mappings.items():
        if not isinstance(action, str) or not action:
            raise ConfigError("mapping action keys must be non-empty strings")
        if not isinstance(spec, dict):
            raise ConfigError(f"mapping for {action} must be an object")
        validated[action] = _parse_mapping(action, spec)

    return ReceiverConfig(
        mappings=validated,
        macro_settings=macro_settings,
        analog_settings=analog_settings,
        engine_states=engine_states,
    )


def _parse_engine_states(spec: object) -> dict[str, bool]:
    """Parse the optional preset `engines` map of {engine_type: active_bool}.

    Lenient by design: this rides the show-critical hot-reload path, so a
    malformed entry must never raise and break a live preset switch. Non-dict
    input → empty map; only string→bool entries are kept, others dropped.
    """
    if not isinstance(spec, dict):
        return {}
    states: dict[str, bool] = {}
    for key, value in spec.items():
        if isinstance(key, str) and key and isinstance(value, bool):
            states[key] = value
    return states


def _parse_macro_settings(spec: object) -> MacroSettings:
    if spec is None:
        return MacroSettings()
    if not isinstance(spec, dict):
        raise ConfigError("macro_settings must be an object")

    fade_duration_seconds = _read_positive_number(
        spec, "fade_duration_seconds", default=2.0
    )
    update_hz = _read_positive_number(spec, "update_hz", default=30.0)
    min_value = _read_byte(spec, "min_value", default=0)
    max_value = _read_byte(spec, "max_value", default=127)
    feedback_match_tolerance = _read_byte(
        spec,
        "feedback_match_tolerance",
        default=2,
    )
    macro_delay_ms = _read_positive_int(spec, "macro_delay_ms", default=80)
    modifier_hold_ms = _read_positive_int(spec, "modifier_hold_ms", default=2000)
    layer_refresh_ms = _read_positive_int(spec, "layer_refresh_ms", default=500)
    if min_value >= max_value:
        raise ConfigError("macro_settings min_value must be less than max_value")

    return MacroSettings(
        fade_duration_seconds=fade_duration_seconds,
        update_hz=update_hz,
        min_value=min_value,
        max_value=max_value,
        feedback_match_tolerance=feedback_match_tolerance,
        macro_delay_ms=macro_delay_ms,
        modifier_hold_ms=modifier_hold_ms,
        layer_refresh_ms=layer_refresh_ms,
    )


def _parse_analog_settings(spec: object) -> AnalogSettings:
    if spec is None:
        return AnalogSettings()
    if not isinstance(spec, dict):
        raise ConfigError("analog_settings must be an object")

    update_hz = _read_positive_number(spec, "update_hz", default=60.0)
    deadzone = _read_non_negative_int(spec, "deadzone", default=1000)
    curve = spec.get("curve", "linear")
    if curve not in {"linear", "quadratic", "s_curve"}:
        raise ConfigError("analog_settings curve must be 'linear', 'quadratic', or 's_curve'")
    return AnalogSettings(update_hz=update_hz, deadzone=deadzone, curve=curve)


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
    if kind == "macro_cc":
        channel = _read_byte(spec, "channel", maximum=15, default=0)
        cc = _read_byte(spec, "cc")
        gesture = spec.get("gesture")
        if gesture not in {"click", "long_press"}:
            raise ConfigError(
                f"mapping for {action} must set gesture to 'click' or 'long_press'"
            )
        fade_override = spec.get("fade_duration_seconds")
        if fade_override is not None:
            if not isinstance(fade_override, (int, float)) or float(fade_override) <= 0:
                raise ConfigError(f"fade_duration_seconds for {action} must be a positive number")
            fade_override = float(fade_override)
        return MacroCCMapping(
            action=action,
            kind="macro_cc",
            channel=channel,
            cc=cc,
            gesture=gesture,
            fade_duration_seconds=fade_override,
        )
    if kind == "relative_cc":
        channel = _read_byte(spec, "channel", maximum=15, default=0)
        cc = _read_byte(spec, "cc")
        step_value = _read_byte(spec, "step_value")
        repeat_interval_ms = _read_positive_int(spec, "repeat_interval_ms", default=40)
        return RelativeCCMapping(
            action=action,
            kind="relative_cc",
            channel=channel,
            cc=cc,
            step_value=step_value,
            repeat_interval_ms=repeat_interval_ms,
        )
    if kind == "staged_note_macro":
        note = _read_byte(spec, "note")
        velocity = _read_byte(spec, "velocity", default=127)
        modifier_channel = _read_byte(spec, "modifier_channel", maximum=15, default=0)
        trigger_channel = _read_byte(spec, "trigger_channel", maximum=15, default=1)
        refresh_actions = _read_string_list(spec, "refresh_actions", default=[])
        if modifier_channel == trigger_channel:
            raise ConfigError(
                f"mapping for {action} must use different modifier_channel and trigger_channel"
            )
        macro_delay_override = spec.get("macro_delay_ms")
        if macro_delay_override is not None:
            if not isinstance(macro_delay_override, int) or macro_delay_override <= 0:
                raise ConfigError(f"macro_delay_ms for {action} must be a positive integer")
        modifier_hold_override = spec.get("modifier_hold_ms")
        if modifier_hold_override is not None:
            if not isinstance(modifier_hold_override, int) or modifier_hold_override <= 0:
                raise ConfigError(f"modifier_hold_ms for {action} must be a positive integer")
        return StagedNoteMacroMapping(
            action=action,
            kind="staged_note_macro",
            note=note,
            modifier_channel=modifier_channel,
            trigger_channel=trigger_channel,
            velocity=velocity,
            refresh_actions=tuple(refresh_actions),
            macro_delay_ms=macro_delay_override,
            modifier_hold_ms=modifier_hold_override,
        )
    if kind == "axis_to_cc":
        channel = _read_byte(spec, "channel", maximum=15, default=0)
        cc = _read_byte(spec, "cc")
        input_range = _read_int_pair(spec, "input_range")
        output_range = _read_int_pair(spec, "output_range")
        if output_range[0] < 0 or output_range[1] > 127:
            raise ConfigError(f"output_range for {action} must be within [0, 127]")
        deadzone = _read_non_negative_int(spec, "deadzone", default=1000)
        curve = spec.get("curve", "linear")
        if curve not in {"linear", "quadratic", "s_curve"}:
            raise ConfigError(
                f"mapping for {action} curve must be 'linear', 'quadratic', or 's_curve'"
            )
        return AxisToCCMapping(
            action=action,
            kind="axis_to_cc",
            channel=channel,
            cc=cc,
            input_range=input_range,
            output_range=output_range,
            deadzone=deadzone,
            curve=curve,
        )
    if kind == "axis_split_cc":
        channel = _read_byte(spec, "channel", maximum=15, default=0)
        cc_positive = _read_byte(spec, "cc_positive")
        cc_negative = _read_byte(spec, "cc_negative")
        if cc_positive == cc_negative:
            raise ConfigError(
                f"mapping for {action}: cc_positive and cc_negative must differ"
            )
        input_max = _read_positive_int(spec, "input_max", default=32767)
        deadzone = _read_non_negative_int(spec, "deadzone", default=1000)
        if deadzone >= input_max:
            raise ConfigError(
                f"mapping for {action}: deadzone must be less than input_max"
            )
        curve = spec.get("curve", "linear")
        if curve not in {"linear", "quadratic", "s_curve"}:
            raise ConfigError(
                f"mapping for {action} curve must be 'linear', 'quadratic', or 's_curve'"
            )
        return AxisSplitCCMapping(
            action=action,
            kind="axis_split_cc",
            channel=channel,
            cc_positive=cc_positive,
            cc_negative=cc_negative,
            input_max=input_max,
            deadzone=deadzone,
            curve=curve,
        )
    raise ConfigError(
        "mapping for"
        " "
        f"{action} must have type 'note', 'cc', 'macro_cc', 'relative_cc',"
        " 'staged_note_macro', 'axis_to_cc', or 'axis_split_cc'"
    )


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


def _read_positive_number(
    spec: dict[str, object],
    key: str,
    *,
    default: float,
) -> float:
    value = spec.get(key, default)
    if not isinstance(value, (int, float)):
        raise ConfigError(f"{key} must be a number")
    number = float(value)
    if number <= 0:
        raise ConfigError(f"{key} must be greater than 0")
    return number


def _read_positive_int(
    spec: dict[str, object],
    key: str,
    *,
    default: int,
) -> int:
    value = spec.get(key, default)
    if not isinstance(value, int):
        raise ConfigError(f"{key} must be an integer")
    if value <= 0:
        raise ConfigError(f"{key} must be greater than 0")
    return value


def _read_string_list(
    spec: dict[str, object],
    key: str,
    *,
    default: list[str],
) -> list[str]:
    value = spec.get(key, default)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ConfigError(f"{key} must be a list of non-empty strings")
    return list(value)


def _read_non_negative_int(
    spec: dict[str, object],
    key: str,
    *,
    default: int,
) -> int:
    value = spec.get(key, default)
    if not isinstance(value, int):
        raise ConfigError(f"{key} must be an integer")
    if value < 0:
        raise ConfigError(f"{key} must be non-negative")
    return value


def _read_int_pair(
    spec: dict[str, object],
    key: str,
) -> tuple[int, int]:
    value = spec.get(key)
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(isinstance(v, int) for v in value)
    ):
        raise ConfigError(f"{key} must be a list of two integers")
    lo, hi = value
    if lo >= hi:
        raise ConfigError(f"{key} lower bound must be less than upper bound")
    return lo, hi


# ---------------------------------------------------------------------------
# Preset helpers
# ---------------------------------------------------------------------------

def ensure_presets_initialized(base_map_path: Path) -> None:
    """Create the presets directory and default preset if they don't exist."""
    presets_dir = base_map_path.parent / "presets"
    presets_dir.mkdir(exist_ok=True)

    default_preset = presets_dir / "default.json"
    if not default_preset.exists():
        default_preset.write_text(
            base_map_path.read_text(encoding="utf-8"), encoding="utf-8"
        )

    active_file = presets_dir / ".active"
    if not active_file.exists():
        active_file.write_text("default.json", encoding="utf-8")


def get_active_preset_path(presets_dir: Path, fallback: Path) -> Path:
    """Return the path of the currently active preset, falling back to fallback."""
    active_file = presets_dir / ".active"
    if active_file.exists():
        name = active_file.read_text(encoding="utf-8").strip()
        candidate = presets_dir / name
        if candidate.exists():
            return candidate
    default = presets_dir / "default.json"
    if default.exists():
        return default
    return fallback


def set_active_preset(presets_dir: Path, filename: str) -> None:
    """Write the active preset filename to .active."""
    (presets_dir / ".active").write_text(filename, encoding="utf-8")
