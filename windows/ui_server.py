"""Localhost web UI server for editing MIDI mappings."""

from __future__ import annotations

import copy
import ipaddress
import json
import os
import sys
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

from flask import Flask, Response, jsonify, request, send_from_directory
from werkzeug.serving import WSGIRequestHandler, make_server

from windows import build_fingerprint, engine_config_api
from windows.live_events import LiveEvents
from windows.osc_relay import OscRelayError, OscRelayUpdateError
from windows.bridge_settings import BridgeSettings
from windows.config import (
    _SAFE_FILENAME_RE,
    AxisToCCMapping,
    AxisSplitCCMapping,
    ConfigError,
    ControlChangeMapping,
    MacroCCMapping,
    MacroSettings,
    MidiMapping,
    NoteMapping,
    RelativeCCMapping,
    StagedNoteMacroMapping,
    get_active_preset_path,
    set_active_preset,
    load_midi_map,
    validate_preset_section,
    select_preset_section,
)

# ---------------------------------------------------------------------------
# Intentional-conflict allow-list (from wiki/reference/intentional-conflicts.md)
# ---------------------------------------------------------------------------
INTENTIONAL_SAME_CHANNEL_CC: frozenset[tuple[int, int]] = frozenset(
    {
        (0, 22),  # DPAD_UP / DPAD_UP_LONG_PRESS
        (0, 21),  # DPAD_RIGHT / DPAD_RIGHT_LONG_PRESS
        (0, 23),  # DPAD_LEFT / DPAD_LEFT_LONG_PRESS
        (0, 47),  # R_PAD_LEFT / R_PAD_RIGHT relative encoder
        (0, 48),  # L_PAD_UP / L_PAD_DOWN relative encoder
        (0, 49),  # R_PAD_UP / R_PAD_DOWN relative encoder
    }
)
INTENTIONAL_MULTI_CHANNEL_CC: frozenset[int] = frozenset({74, 78, 79})


class _MappingConflict(Exception):
    def __init__(self, conflicts: list[dict[str, Any]]) -> None:
        self.conflicts = conflicts


def _apply_macro_spec(macro: dict, current: dict | None) -> dict:
    """Mirror index.html DEFAULTS and applyMacroToSelected after compatibility."""
    defaults = {
        "macro_cc": {"type": "macro_cc", "channel": 0, "cc": 22, "gesture": "click"},
        "relative_cc": {"type": "relative_cc", "channel": 0, "cc": 47,
                        "step_value": 1, "repeat_interval_ms": 40},
        "staged_note_macro": {"type": "staged_note_macro", "note": 36, "velocity": 127,
                              "modifier_channel": 0, "trigger_channel": 1, "refresh_actions": []},
    }
    kind = macro["type"]
    base = copy.deepcopy(current if current is not None else defaults[kind])
    required, optional = {
        "macro_cc": (("gesture",), ("fade_duration_seconds",)),
        "relative_cc": (("step_value", "repeat_interval_ms"), ()),
        "staged_note_macro": (("modifier_channel", "trigger_channel"),
                              ("macro_delay_ms", "modifier_hold_ms")),
    }[kind]
    for key in required:
        # Missing staged channels become undefined in the page and are omitted
        # by JSON.stringify, letting the mapping parser supply its defaults.
        if key in macro:
            base[key] = macro[key]
        else:
            base.pop(key, None)
    for key in optional:
        if macro.get(key) is not None:
            base[key] = macro[key]
        else:
            base.pop(key, None)
    if kind == "staged_note_macro":
        base["refresh_actions"] = list(macro.get("refresh_actions") or [])
    return base


def _mapping_to_dict(m: MidiMapping) -> dict[str, Any]:
    if isinstance(m, NoteMapping):
        return {"type": "note", "channel": m.channel, "note": m.note, "velocity": m.velocity}
    if isinstance(m, ControlChangeMapping):
        return {"type": "cc", "channel": m.channel, "cc": m.cc,
                "on_value": m.on_value, "off_value": m.off_value}
    if isinstance(m, MacroCCMapping):
        d: dict[str, Any] = {"type": "macro_cc", "channel": m.channel,
                              "cc": m.cc, "gesture": m.gesture}
        if m.fade_duration_seconds is not None:
            d["fade_duration_seconds"] = m.fade_duration_seconds
        return d
    if isinstance(m, RelativeCCMapping):
        return {"type": "relative_cc", "channel": m.channel, "cc": m.cc,
                "step_value": m.step_value, "repeat_interval_ms": m.repeat_interval_ms}
    if isinstance(m, StagedNoteMacroMapping):
        d = {"type": "staged_note_macro", "note": m.note, "velocity": m.velocity,
             "modifier_channel": m.modifier_channel, "trigger_channel": m.trigger_channel,
             "refresh_actions": list(m.refresh_actions)}
        if m.macro_delay_ms is not None:
            d["macro_delay_ms"] = m.macro_delay_ms
        if m.modifier_hold_ms is not None:
            d["modifier_hold_ms"] = m.modifier_hold_ms
        return d
    if isinstance(m, AxisToCCMapping):
        return {"type": "axis_to_cc", "channel": m.channel, "cc": m.cc,
                "input_range": list(m.input_range), "output_range": list(m.output_range),
                "deadzone": m.deadzone, "curve": m.curve}
    if isinstance(m, AxisSplitCCMapping):
        return {"type": "axis_split_cc", "channel": m.channel,
                "cc_positive": m.cc_positive, "cc_negative": m.cc_negative,
                "input_max": m.input_max, "deadzone": m.deadzone, "curve": m.curve}
    raise TypeError(f"unknown mapping type: {type(m)!r}")


def _detect_conflicts(mappings: dict[str, Any]) -> list[dict[str, Any]]:
    from collections import defaultdict
    by_channel_cc: dict[tuple[int, int], list[str]] = defaultdict(list)
    for action, spec in mappings.items():
        if not isinstance(spec, dict):
            continue
        ch = spec.get("channel", 0)
        cc = spec.get("cc")
        if cc is not None:
            by_channel_cc[(int(ch), int(cc))].append(action)
        cc_pos = spec.get("cc_positive")
        if cc_pos is not None:
            by_channel_cc[(int(ch), int(cc_pos))].append(f"{action} (+)")
        cc_neg = spec.get("cc_negative")
        if cc_neg is not None:
            by_channel_cc[(int(ch), int(cc_neg))].append(f"{action} (−)")

    conflicts: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for (ch, cc), actions in by_channel_cc.items():
        if len(actions) < 2:
            continue
        key = (ch, cc)
        if key in seen:
            continue
        seen.add(key)
        if key in INTENTIONAL_SAME_CHANNEL_CC:
            continue
        conflicts.append({"kind": "same_channel_cc", "channel": ch, "cc": cc,
                           "actions": actions, "intentional": False})
    return conflicts


def _remote_is_loopback() -> bool:
    """True only when the TCP peer is a loopback address; headers are ignored."""
    try:
        return ipaddress.ip_address(request.remote_addr or "").is_loopback
    except ValueError:
        return False


def _loopback_refusal() -> tuple[Response, int]:
    return jsonify({"error": "this route requires a loopback remote address"}), 403


def _safe_preset_name(name: str) -> str | None:
    """Return sanitised filename (without .json) or None if invalid."""
    name = name.strip()
    if not name or not _SAFE_FILENAME_RE.match(name):
        return None
    return name


def _member_span(text: str, key: str, start: int = 0) -> tuple[int, int]:
    """Locate a JSON object member's value without reserializing its siblings."""
    decoder = json.JSONDecoder()
    index = start + 1  # opening brace of an already parsed object
    while True:
        while text[index].isspace() or text[index] == ',':
            index += 1
        if text[index] == '}':
            raise ConfigError(f"missing JSON member: {key}")
        name, index = decoder.raw_decode(text, index)
        while text[index].isspace() or text[index] == ':':
            index += 1
        value_start = index
        _, index = decoder.raw_decode(text, index)
        if name == key:
            return value_start, index


def _section_content(content: str, section: str | None, document: dict) -> str:
    """Replace only the selected value, retaining every other byte."""
    raw = json.loads(content)
    select_preset_section(raw, section)
    if 'sections' not in raw:
        return json.dumps(document, indent=2)
    sections_start, _ = _member_span(content, 'sections', len(content) - len(content.lstrip()))
    start, end = _member_span(content, section, sections_start)
    return content[:start] + json.dumps(document, indent=2) + content[end:]


class MappingUIServer:
    def __init__(
        self,
        base_map_path: Path,
        presets_dir: Path,
        macro_library_path: Path,
        actions_yaml_path: Path,
        reload_event: threading.Event,
        port: int = 7723,
        engine_registry: Any = None,
        preset_section: str | None = None,
        bridge_settings: BridgeSettings | None = None,
        listen: str = "0.0.0.0:45123",
        midi_port: str = "DECK_IN",
        feedback_port: str | None = None,
        pulse_port: str | None = "PULSE_OUT",
        state_version_fn: Callable[[], int] | None = None,
        shutdown_fn: Callable[[], None] | None = None,
        live_events: LiveEvents | None = None,
        receiver_tasks: Any = None,
        osc_relay_controller: Any = None,
        requested_ports: dict[str, str | None] | None = None,
        log_ring: Any = None,
        log_file_path: Path | None = None,
    ) -> None:
        self.base_map_path = base_map_path
        self.presets_dir = presets_dir
        self.macro_library_path = macro_library_path
        self.actions_yaml_path = actions_yaml_path
        self.reload_event = reload_event
        self.shutdown_fn = shutdown_fn
        self.live_events = live_events if live_events is not None else LiveEvents()
        self._shutdown_lock = threading.Lock()
        self._stopping = False
        self._http_server = None
        self._thread = None
        self.state_version_fn = state_version_fn or (lambda: 0)
        self._mapping_revision = 0
        self.port = port
        self.engine_registry = engine_registry
        self.bridge_settings = bridge_settings or BridgeSettings.load(
            base_map_path.parent / "bridge.local.json", preset_section,
        )
        self.listen = listen
        self.midi_port = midi_port
        self.feedback_port = feedback_port
        self.pulse_port = pulse_port
        self.receiver_tasks = receiver_tasks
        self.osc_relay_controller = osc_relay_controller
        self.requested_ports = requested_ports or {}
        self.log_ring = log_ring
        self.log_file_path = log_file_path
        self._settings_lock = threading.Lock()
        self._app = self._build_app()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_active_preset_path(self) -> Path:
        return get_active_preset_path(self.presets_dir, self.base_map_path)

    def _live_settings(self) -> dict[str, Any]:
        return {
            "preset_section": self.bridge_settings.preset_section,
            "listen": self.listen,
            "midi_port": self.midi_port,
            "feedback_port": self.feedback_port,
            "pulse_port": self.pulse_port,
            "ui_port": self.port,
            "map_path": str(self._get_active_preset_path().resolve()),
        }

    def _load_raw_json(self) -> dict[str, Any]:
        active = self._get_active_preset_path()
        try:
            return json.loads(active.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _write_preset(self, target: Path, content: str,
                      *, before_replace: Callable[[], None] | None = None) -> None:
        """Validate every section with the loader before an atomic replacement."""
        raw = json.loads(content)
        sections = list(raw.get("sections", {})) if isinstance(raw, dict) and "sections" in raw else [None]
        if not sections:
            raise ConfigError("sections must be a non-empty object")
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                             prefix=".preset-", suffix=".tmp", delete=False, newline="") as tmp:
                tmp_path = Path(tmp.name)
                tmp.write(content)
            for section in sections:
                load_midi_map(tmp_path, section)
            if before_replace is not None:
                before_replace()
            os.replace(tmp_path, target)
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)

    def _section_metadata(self, raw: dict, preset: str, section: str | None) -> dict:
        return {"section": section, "sections": list(raw.get("sections", {})),
                "bridge_section": self.bridge_settings.preset_section,
                "preset": preset, "legacy": "sections" not in raw}

    def _list_presets(self) -> list[dict[str, Any]]:
        active_path = self._get_active_preset_path()
        presets = []
        for f in sorted(self.presets_dir.glob("*.json")):
            presets.append({
                "name": f.name,
                "display_name": f.stem,
                "active": f.resolve() == active_path.resolve(),
            })
        return presets

    def _live_axis_ranges(self, static_ranges: dict) -> dict:
        """Overlay the hardware axis bounds with the bounds actually in force.

        The live view has to draw on the same scale the bridge maps from. When
        it does not, a control that drives Resolume across its whole range
        appears to barely move, which reads as a bug in the view. Everything
        here is read from the live configuration - mapping input_range and
        deadzone from the active preset, gyro bounds from the loaded
        gyro_feedback engine - so a retune moves the display with it and no
        range is duplicated in the static map.
        """
        ranges = copy.deepcopy(static_ranges)
        try:
            raw = self._load_raw_json()
            effective = select_preset_section(raw, self.bridge_settings.preset_section)
            mappings = effective.get("mappings") or {}
        except Exception:
            # A bad or absent preset must never cost us the controller view.
            mappings = {}
        for action, bounds in ranges.items():
            spec = mappings.get(action)
            if not isinstance(spec, dict):
                continue
            span = spec.get("input_range")
            if (isinstance(span, (list, tuple)) and len(span) == 2
                    and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in span)):
                low, high = float(span[0]), float(span[1])
                if low < bounds["min"]:
                    bounds["min"] = low
                bounds["max"] = high
                # A unipolar floor above rest is a deadzone; say so explicitly
                # rather than letting the bar start part-filled.
                if low > bounds["rest"]:
                    bounds["deadzone"] = low - bounds["rest"]
            deadzone = spec.get("deadzone")
            if isinstance(deadzone, (int, float)) and not isinstance(deadzone, bool) and deadzone > 0:
                bounds["deadzone"] = max(float(deadzone), float(bounds.get("deadzone", 0.0)))
        if self.engine_registry is not None:
            status, payload = engine_config_api.get_engine_config(self.engine_registry, "gyro_feedback")
            spec = payload.get("spec") if status == 200 else None
            if isinstance(spec, dict):
                axes = spec.get("axes") or {}
                per_axis = spec.get("axis_raw") or {}
                deadzone = spec.get("deadzone", 0)
                for axis_name, action in axes.items():
                    bounds = ranges.get(action)
                    if not isinstance(bounds, dict):
                        continue
                    override = per_axis.get(axis_name) or {}
                    low = override.get("raw_min", spec.get("raw_min"))
                    high = override.get("raw_max", spec.get("raw_max"))
                    if not isinstance(low, (int, float)) or not isinstance(high, (int, float)):
                        continue
                    bounds["min"], bounds["max"], bounds["rest"] = float(low), float(high), 0.0
                    if isinstance(deadzone, (int, float)):
                        bounds["deadzone"] = float(deadzone)
        return ranges

    def _load_actions(self) -> list[str]:
        try:
            import yaml  # type: ignore[import-untyped]
            data = yaml.safe_load(self.actions_yaml_path.read_text(encoding="utf-8"))
            return list(data.get("actions", []))
        except ImportError:
            lines = self.actions_yaml_path.read_text(encoding="utf-8").splitlines()
            actions: list[str] = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("- "):
                    actions.append(stripped[2:].strip())
            return actions
        except OSError:
            return []

    def _load_macro_library(self) -> list[dict[str, Any]]:
        if not self.macro_library_path.exists():
            return []
        try:
            data = json.loads(self.macro_library_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _save_macro_library(self, entries: list[dict[str, Any]]) -> None:
        self.macro_library_path.write_text(
            json.dumps(entries, indent=2), encoding="utf-8"
        )

    # ------------------------------------------------------------------
    # Flask app
    # ------------------------------------------------------------------

    def _build_app(self) -> Flask:
        static_dir = Path(__file__).parent / "static"
        app = Flask(__name__, static_folder=str(static_dir))
        app.config["JSON_SORT_KEYS"] = False

        import logging
        logging.getLogger("werkzeug").setLevel(logging.ERROR)

        @app.route("/")
        def index() -> Response:
            return send_from_directory(str(static_dir), "index.html")

        @app.route("/api/live/snapshot", methods=["GET"])
        def live_snapshot() -> Response:
            response = jsonify(self.live_events.snapshot())
            response.headers["Cache-Control"] = "no-store"
            return response

        @app.route("/api/live/events", methods=["GET"])
        def live_events() -> Response:
            raw = request.args.get("since", request.headers.get("Last-Event-ID"))
            try:
                since = None if raw is None else int(raw)
                if since is not None and (since < 0 or len(raw) > 20):
                    raise ValueError
            except ValueError:
                return jsonify({"error": "since must be a non-negative integer"}), 400
            subscription = self.live_events.subscribe(since)
            if subscription is None:
                return jsonify({"error": "live events unavailable"}), 503
            response = Response(subscription.stream(), mimetype="text/event-stream",
                                headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
            response.call_on_close(subscription.close)
            return response

        @app.route("/api/state-version", methods=["GET"])
        def state_version() -> Response:
            response = jsonify(self.state_version_fn() + self._mapping_revision)
            response.headers["Cache-Control"] = "no-store"
            return response

        @app.route("/api/reload", methods=["POST"])
        def reload_now() -> Response:
            self.reload_event.set()
            return jsonify({"ok": True})

        @app.route("/api/shutdown", methods=["POST"])
        def shutdown() -> Response:
            if not _remote_is_loopback():
                return jsonify({"error": "shutdown requires a loopback remote address"}), 403
            with self._shutdown_lock:
                if self.shutdown_fn is None:
                    return jsonify({"error": "bridge shutdown is unavailable"}), 503
                if not self._stopping:
                    self.shutdown_fn()
                    self._stopping = True
            return jsonify({"stopping": True}), 202

        @app.route("/api/version", methods=["GET"])
        def get_version() -> Response:
            return jsonify({
                "version": build_fingerprint.APP_VERSION,
                "git_commit": build_fingerprint.GIT_COMMIT,
                "build_time_utc": build_fingerprint.BUILD_TIME_UTC,
                "frozen": bool(getattr(sys, "frozen", False)),
            })

        @app.route("/api/settings", methods=["GET"])
        def get_settings() -> Response:
            return jsonify(self._live_settings())

        @app.route("/api/settings", methods=["PUT"])
        def put_settings() -> Response:
            body = request.get_json(force=True, silent=True)
            if not isinstance(body, dict) or set(body) != {"preset_section"}:
                return jsonify({"error": "expected only 'preset_section' in a JSON object"}), 400
            section = body["preset_section"]
            try:
                validate_preset_section(section)
            except ConfigError as exc:
                return jsonify({"error": str(exc)}), 400
            with self._settings_lock:
                try:
                    load_midi_map(self._get_active_preset_path(), section)
                except ConfigError as exc:
                    return jsonify({"error": str(exc)}), 422
                try:
                    self.bridge_settings.save(section)
                except OSError as exc:
                    return jsonify({"error": str(exc)}), 500
                self.reload_event.set()
                return jsonify(self._live_settings())

        # ── Mappings ───────────────────────────────────────────────

        @app.route("/api/mappings", methods=["GET"])
        def get_mappings() -> Response:
            section = request.args.get("section", self.bridge_settings.preset_section)
            try:
                validate_preset_section(section)
                raw = self._load_raw_json()
                effective = select_preset_section(raw, section)
                load_midi_map(self._get_active_preset_path(), section)
                document = raw["sections"][section] if "sections" in raw else raw
                return jsonify({**effective, "document": document,
                                "shared_mappings": raw.get("shared", {}).get("mappings", {}) if "sections" in raw else {},
                                **self._section_metadata(raw, self._get_active_preset_path().name, section)})
            except ConfigError as exc:
                return jsonify({"error": str(exc)}), 422

        @app.route("/api/actions", methods=["GET"])
        def get_actions() -> Response:
            return jsonify({"actions": self._load_actions()})

        # The controller relation and its anchor coordinates have one owner.
        def controller_map() -> dict:
            base = json.loads((static_dir / "controller/controller_map.json").read_text(encoding="utf-8"))
            base["axis_ranges"] = self._live_axis_ranges(base.get("axis_ranges", {}))
            return base

        @app.route("/api/controller-map", methods=["GET"])
        def get_controller_map() -> Response:
            return jsonify(controller_map())

        @app.route("/api/controller-map/<control_id>", methods=["GET"])
        def get_controller_control(control_id: str) -> Response:
            control = next((c for c in controller_map()["controls"] if c["id"] == control_id), None)
            if control is None:
                return jsonify({"error": "control not found"}), 404
            section = request.args.get("section", self.bridge_settings.preset_section)
            try:
                validate_preset_section(section)
                active = self._get_active_preset_path()
                raw = json.loads(active.read_text(encoding="utf-8"))
                effective = select_preset_section(raw, section)
                load_midi_map(active, section)
                document = raw["sections"][section] if "sections" in raw else raw
                groups = {}
                for group, actions in control["groups"].items():
                    groups[group] = [{
                        "action_id": action,
                        "mapping": effective["mappings"].get(action),
                        "source": ("section" if "sections" in raw else "flat")
                        if action in document["mappings"] else
                        ("shared" if action in effective["mappings"] else None),
                    } for action in actions]
                return jsonify({**control, "groups": groups,
                                **self._section_metadata(raw, active.name, section)})
            except (ConfigError, ValueError) as exc:
                return jsonify({"error": str(exc)}), 422
            except OSError as exc:
                return jsonify({"error": str(exc)}), 500

        def edit_mapping(action_id: str, section: str | None, spec: Any = None,
                         *, clear: bool = False, macro: dict | None = None) -> Response:
            if action_id not in self._load_actions():
                return jsonify({"error": "action not found"}), 404
            with self._settings_lock:
                try:
                    validate_preset_section(section)
                    active = self._get_active_preset_path()
                    original = active.read_bytes().decode("utf-8")
                    raw = json.loads(original)
                    effective = select_preset_section(raw, section)
                    document = copy.deepcopy(raw["sections"][section] if "sections" in raw else raw)
                except (ConfigError, ValueError) as exc:
                    return jsonify({"error": str(exc)}), 422
                except OSError as exc:
                    return jsonify({"error": str(exc)}), 500
                if macro is not None:
                    current = effective["mappings"].get(action_id)
                    if current is not None and current.get("type") != macro["type"]:
                        return jsonify({"error": "macro is incompatible with the current mapping type"}), 409
                    spec = _apply_macro_spec(macro, current)
                shared = raw.get("shared", {}).get("mappings", {}) if "sections" in raw else {}
                if clear:
                    document["mappings"].pop(action_id, None)
                elif (action_id not in document["mappings"] and action_id in shared
                      and json.dumps(spec, separators=(",", ":")) ==
                      json.dumps(shared[action_id], separators=(",", ":"))):
                    # doSave leaves unchanged inherited mappings shared.
                    pass
                else:
                    document["mappings"][action_id] = spec
                try:
                    content = _section_content(original, section, document)
                    resulting = select_preset_section(json.loads(content), section)

                    def guard_conflicts() -> None:
                        conflicts = _detect_conflicts(resulting["mappings"])
                        if conflicts and request.args.get("force") != "1":
                            raise _MappingConflict(conflicts)

                    self._write_preset(active, content, before_replace=guard_conflicts)
                except _MappingConflict as exc:
                    return jsonify({"error": "mapping conflicts", "conflicts": exc.conflicts}), 409
                except (ConfigError, ValueError, TypeError) as exc:
                    return jsonify({"error": str(exc)}), 400
                except OSError as exc:
                    return jsonify({"error": str(exc)}), 500
                self._mapping_revision += 1
                self.reload_event.set()
                return jsonify({"ok": True, "action_id": action_id, "section": section,
                                "mapping": document["mappings"].get(action_id),
                                "effective_mapping": resulting["mappings"].get(action_id),
                                "saved_to": active.name})

        @app.route("/api/mappings/<action_id>", methods=["PUT"])
        def put_mapping(action_id: str) -> Response:
            return edit_mapping(action_id, request.args.get("section", self.bridge_settings.preset_section),
                                request.get_json(force=True, silent=True))

        @app.route("/api/mappings/<action_id>", methods=["DELETE"])
        def delete_mapping(action_id: str) -> Response:
            return edit_mapping(action_id, request.args.get("section", self.bridge_settings.preset_section), clear=True)

        @app.route("/api/macros/<macro_id>/apply", methods=["POST"])
        def apply_macro(macro_id: str) -> Response:
            body = request.get_json(force=True, silent=True)
            if not isinstance(body, dict) or not isinstance(body.get("action_id"), str):
                return jsonify({"error": "expected an object with action_id and optional section"}), 400
            macro = next((m for m in self._load_macro_library() if m.get("id") == macro_id), None)
            if macro is None:
                return jsonify({"error": "macro not found"}), 404
            error = _validate_macro_entry(macro)
            if error:
                return jsonify({"error": error}), 400
            return edit_mapping(body["action_id"], body.get("section", self.bridge_settings.preset_section), macro=macro)

        @app.route("/api/conflicts", methods=["POST"])
        def check_conflicts() -> Response:
            body = request.get_json(force=True, silent=True) or {}
            return jsonify({"conflicts": _detect_conflicts(body.get("mappings", {}))})

        @app.route("/api/save", methods=["POST"])
        def save_mappings() -> Response:
            body = request.get_json(force=True, silent=True)
            if not isinstance(body, dict):
                return jsonify({"error": "expected JSON object"}), 400
            section = body.get("section", self.bridge_settings.preset_section)
            document = body.get("document", body)
            if not isinstance(document, dict) or not isinstance(document.get("mappings"), dict):
                return jsonify({"error": "document must contain a 'mappings' object"}), 400
            candidate = {key: document[key] for key in
                         ("mappings", "macro_settings", "analog_settings", "engines") if key in document}
            # Retain the old flat caller's live-engine snapshot behavior. Explicit
            # section documents always own their engine states, including omissions.
            if "document" not in body and section == self.bridge_settings.preset_section:
                engine_states = self._current_engine_states()
                if engine_states:
                    candidate["engines"] = engine_states
            with self._settings_lock:
                try:
                    validate_preset_section(section)
                    active = self._get_active_preset_path()
                    content = _section_content(active.read_bytes().decode("utf-8"), section, candidate)
                    self._write_preset(active, content)
                except (ConfigError, ValueError) as exc:
                    return jsonify({"error": str(exc)}), 422
                except OSError as exc:
                    return jsonify({"error": str(exc)}), 500
                self.reload_event.set()
            return jsonify({"ok": True, "saved_to": active.name, "section": section})

        @app.route("/api/reset", methods=["POST"])
        def factory_reset() -> Response:
            """Restore factory defaults in the selected section only."""
            body = request.get_json(force=True, silent=True)
            if not isinstance(body, dict):
                return jsonify({"error": "expected JSON object"}), 400
            section = body.get("section", self.bridge_settings.preset_section)
            with self._settings_lock:
                try:
                    factory = json.loads(self.base_map_path.read_text(encoding="utf-8"))
                    document = select_preset_section(factory, section)
                    active = self._get_active_preset_path()
                    self._write_preset(active, _section_content(active.read_bytes().decode("utf-8"), section, document))
                except (ConfigError, ValueError) as exc:
                    return jsonify({"error": str(exc)}), 422
                except OSError as exc:
                    return jsonify({"error": str(exc)}), 500
                self.reload_event.set()
            return jsonify({"ok": True, "section": section})

        # ── Presets ────────────────────────────────────────────────

        @app.route("/api/presets", methods=["GET"])
        def get_presets() -> Response:
            return jsonify({"presets": self._list_presets()})

        @app.route("/api/presets/<name>/sections", methods=["GET"])
        def get_preset_sections(name: str) -> Response:
            stem = name[:-5] if name.endswith(".json") else name
            if not _SAFE_FILENAME_RE.fullmatch(stem):
                return jsonify({"error": "invalid preset name"}), 400
            target = self.presets_dir / (stem + ".json")
            try:
                raw = json.loads(target.read_text(encoding="utf-8"))
                sections = list(raw.get("sections", {}))
                load_midi_map(target, sections[0] if sections else None)
                return jsonify(self._section_metadata(raw, target.name, self.bridge_settings.preset_section))
            except FileNotFoundError:
                return jsonify({"error": "preset not found"}), 404
            except (ConfigError, ValueError, TypeError, AttributeError) as exc:
                return jsonify({"error": str(exc)}), 422

        def edit_sections(operation: str) -> Response:
            body = request.get_json(force=True, silent=True)
            keys = ("old", "new") if operation == "rename" else ("name",)
            if not isinstance(body, dict):
                return jsonify({"error": "expected JSON object"}), 400
            try:
                for key in keys + (("copy_from",) if "copy_from" in body else ()):
                    value = body.get(key)
                    if not isinstance(value, str) or not value.strip():
                        raise ConfigError(f"{key} must be a non-empty section name")
                    validate_preset_section(value)
            except ConfigError as exc:
                return jsonify({"error": str(exc)}), 400
            with self._settings_lock:
                active = self._get_active_preset_path()
                own = self.bridge_settings.preset_section
                try:
                    original = active.read_bytes().decode("utf-8")
                    raw = json.loads(original)
                    first_section = "sections" not in raw and own is None and operation == "add"
                    if "sections" not in raw:
                        if operation != "add":
                            return jsonify({"error": "legacy preset: add a named section first"}), 422
                        raw = {"sections": {body["name"] if first_section else own: raw}}
                    sections = raw["sections"]
                    if not isinstance(sections, dict) or not sections:
                        raise ConfigError("sections must be a non-empty object")
                    if operation == "add":
                        name = body["name"]
                        if name in sections and not first_section:
                            return jsonify({"error": "section already exists"}), 409
                        source = body.get("copy_from")
                        if source is not None and source not in sections:
                            return jsonify({"error": "copy source not found"}), 404
                        if not first_section:
                            sections[name] = copy.deepcopy(sections[source]) if source else {"mappings": {}}
                    elif operation == "rename":
                        old, new = body["old"], body["new"]
                        if old not in sections:
                            return jsonify({"error": "section not found"}), 404
                        if new in sections:
                            return jsonify({"error": "section already exists"}), 409
                        sections[new] = sections.pop(old)
                    else:
                        name = body["name"]
                        if name not in sections:
                            return jsonify({"error": "section not found"}), 404
                        if name == own:
                            return jsonify({"error": "cannot delete this machine's section"}), 409
                        if len(sections) == 1:
                            return jsonify({"error": "cannot delete the last section"}), 409
                        del sections[name]
                    self._write_preset(active, json.dumps(raw, indent=2))
                    if first_section or (operation == "rename" and body["old"] == own):
                        try:
                            self.bridge_settings.save(body["name"] if first_section else body["new"])
                        except OSError:
                            # Restore the preset if local identity cannot be persisted.
                            self._write_preset(active, original)
                            raise
                except (ConfigError, ValueError, TypeError) as exc:
                    return jsonify({"error": str(exc)}), 422
                except OSError as exc:
                    return jsonify({"error": str(exc)}), 500
                self.reload_event.set()
                return jsonify({"ok": True, **self._section_metadata(raw, active.name, self.bridge_settings.preset_section)})

        @app.route("/api/presets/sections/add", methods=["POST"])
        def add_section() -> Response:
            return edit_sections("add")

        @app.route("/api/presets/sections/rename", methods=["POST"])
        def rename_section() -> Response:
            return edit_sections("rename")

        @app.route("/api/presets/sections/delete", methods=["POST"])
        def delete_section() -> Response:
            return edit_sections("delete")

        @app.route("/api/presets/load", methods=["POST"])
        def load_preset() -> Response:
            body = request.get_json(force=True, silent=True) or {}
            name = body.get("name", "")
            target = self.presets_dir / name
            if not target.exists() or target.suffix != ".json":
                return jsonify({"error": f"preset not found: {name}"}), 404
            set_active_preset(self.presets_dir, name)
            self.reload_event.set()
            return jsonify({"ok": True, "active": name})

        @app.route("/api/presets/save-as", methods=["POST"])
        def save_as_preset() -> Response:
            body = request.get_json(force=True, silent=True) or {}
            display = body.get("name", "").strip()
            safe = _safe_preset_name(display)
            if not safe:
                return jsonify({"error": "preset name must be letters, numbers, spaces, hyphens, or underscores"}), 400
            filename = safe + ".json"
            new_path = self.presets_dir / filename
            current_content = self._get_active_preset_path().read_bytes().decode("utf-8")
            # Bake the live engine on/off states into the new preset so the
            # checkbox state the user sees is what gets saved.
            engine_states = self._current_engine_states()
            if engine_states:
                try:
                    doc = json.loads(current_content)
                    if isinstance(doc, dict):
                        section = self.bridge_settings.preset_section
                        select_preset_section(doc, section)
                        document = copy.deepcopy(doc["sections"][section] if "sections" in doc else doc)
                        document["engines"] = engine_states
                        current_content = _section_content(current_content, section, document)
                except (ConfigError, ValueError) as exc:
                    return jsonify({"error": str(exc)}), 422
            try:
                self._write_preset(new_path, current_content)
            except (ConfigError, ValueError) as exc:
                return jsonify({"error": str(exc)}), 422
            except OSError as exc:
                return jsonify({"error": str(exc)}), 500
            set_active_preset(self.presets_dir, filename)
            self.reload_event.set()
            return jsonify({"ok": True, "active": filename})

        @app.route("/api/presets/rename", methods=["POST"])
        def rename_preset() -> Response:
            body = request.get_json(force=True, silent=True) or {}
            old_name = body.get("old_name", "")
            new_display = body.get("new_name", "").strip()
            safe = _safe_preset_name(new_display)
            if not safe:
                return jsonify({"error": "invalid new name"}), 400
            new_name = safe + ".json"
            old_path = self.presets_dir / old_name
            if not old_path.exists():
                return jsonify({"error": "preset not found"}), 404
            if old_name == "default.json":
                return jsonify({"error": "cannot rename the default preset"}), 400
            new_path = self.presets_dir / new_name
            old_path.rename(new_path)
            active_file = self.presets_dir / ".active"
            if active_file.exists() and active_file.read_text(encoding="utf-8").strip() == old_name:
                set_active_preset(self.presets_dir, new_name)
            self.reload_event.set()
            return jsonify({"ok": True, "name": new_name})

        @app.route("/api/presets/delete", methods=["POST"])
        def delete_preset() -> Response:
            body = request.get_json(force=True, silent=True) or {}
            name = body.get("name", "")
            if name == "default.json":
                return jsonify({"error": "cannot delete the default preset"}), 400
            target = self.presets_dir / name
            if not target.exists():
                return jsonify({"error": "preset not found"}), 404
            was_active = self._get_active_preset_path().resolve() == target.resolve()
            target.unlink()
            if was_active:
                set_active_preset(self.presets_dir, "default.json")
                self.reload_event.set()
            return jsonify({"ok": True})

        # ── Macro library ──────────────────────────────────────────

        @app.route("/api/macros", methods=["GET"])
        def get_macros() -> Response:
            return jsonify({"macros": self._load_macro_library()})

        @app.route("/api/macros", methods=["POST"])
        def create_macro() -> Response:
            body = request.get_json(force=True, silent=True) or {}
            err = _validate_macro_entry(body)
            if err:
                return jsonify({"error": err}), 400
            entries = self._load_macro_library()
            entry = {**body, "id": str(uuid.uuid4())[:8]}
            entries.append(entry)
            self._save_macro_library(entries)
            return jsonify({"ok": True, "macro": entry}), 201

        @app.route("/api/macros/<macro_id>", methods=["PUT"])
        def update_macro(macro_id: str) -> Response:
            body = request.get_json(force=True, silent=True) or {}
            err = _validate_macro_entry(body)
            if err:
                return jsonify({"error": err}), 400
            entries = self._load_macro_library()
            idx = next((i for i, e in enumerate(entries) if e.get("id") == macro_id), None)
            if idx is None:
                return jsonify({"error": "macro not found"}), 404
            entries[idx] = {**body, "id": macro_id}
            self._save_macro_library(entries)
            return jsonify({"ok": True, "macro": entries[idx]})

        @app.route("/api/macros/<macro_id>", methods=["DELETE"])
        def delete_macro(macro_id: str) -> Response:
            entries = self._load_macro_library()
            new_entries = [e for e in entries if e.get("id") != macro_id]
            if len(new_entries) == len(entries):
                return jsonify({"error": "macro not found"}), 404
            self._save_macro_library(new_entries)
            return jsonify({"ok": True})

        # ── Engines ────────────────────────────────────────────────
        @app.route("/api/engines", methods=["GET"])
        def list_engines() -> Response:
            if self.engine_registry is None:
                return jsonify({"engines": []})
            return jsonify({"engines": self.engine_registry.status()})

        @app.route("/api/engines/<type_name>/active", methods=["POST"])
        def set_engine_active(type_name: str) -> Response:
            """Toggle one engine on/off live (web-UI checkbox).

            The new state is not persisted until the preset is saved — at which
            point `_current_engine_states()` captures it into the preset file.
            """
            if self.engine_registry is None:
                return jsonify({"error": "no engine registry"}), 404
            body = request.get_json(force=True, silent=True) or {}
            active = body.get("active")
            if not isinstance(active, bool):
                return jsonify({"error": "'active' must be a boolean"}), 400
            if not self.engine_registry.set_active_by_type(type_name, active):
                return jsonify({"error": f"engine not loaded: {type_name}"}), 404
            return jsonify({"ok": True, "type": type_name, "active": active})

        @app.route("/api/engines/osc-sync/resync", methods=["POST"])
        def resync_osc_sync() -> Response:
            engine = self._find_engine("osc_sync")
            if engine is None:
                return jsonify({"error": "osc_sync engine not loaded"}), 404
            try:
                count = engine.resync_targets()
            except Exception as exc:  # noqa: BLE001 - surface to UI
                return jsonify({"error": str(exc)}), 500
            return jsonify({"ok": True, "target_count": count})

        @app.route("/api/engines/gyro-feedback/resync", methods=["POST"])
        def resync_gyro_feedback() -> Response:
            """Flip the gyro_feedback engine's polarity and refresh outputs.

            Use when the bridge's gyro state has drifted opposite to the
            deck's konsole state (e.g. after bridge restart with deck mid-state,
            or when L4 events were missed during a UDP sniff). Each call
            inverts the engine's polarity and immediately pushes sprite +
            layer to match.
            """
            engine = self._find_engine("gyro_feedback")
            if engine is None:
                return jsonify({"error": "gyro_feedback engine not loaded"}), 404
            try:
                state = engine.resync_gyro_polarity()
            except Exception as exc:  # noqa: BLE001 - surface to UI
                return jsonify({"error": str(exc)}), 500
            return jsonify({"ok": True, **state})

        @app.route("/api/engines/autopilot/state/clear", methods=["POST"])
        def clear_autopilot_state() -> Response:
            """Reset autopilot channel intent to config defaults and persist it.

            Touches only the five persisted intent fields per channel (see
            docs/autopilot-state.md); deletes no file and no other state.
            """
            engine = self._find_engine("autopilot")
            if engine is None:
                return jsonify({"error": "autopilot engine not loaded"}), 404
            try:
                result = engine.clear_intent()
            except Exception as exc:  # noqa: BLE001 - surface to UI
                return jsonify({"error": str(exc)}), 500
            return jsonify({"ok": True, **result})

        @app.route("/api/engines/<type_name>/config", methods=["GET"])
        def get_engine_config(type_name: str) -> Response:
            if not _remote_is_loopback():
                return _loopback_refusal()
            status, payload = engine_config_api.get_engine_config(self.engine_registry, type_name)
            return jsonify(payload), status

        @app.route("/api/engines/<type_name>/config", methods=["PUT"])
        def put_engine_config(type_name: str) -> Response:
            if not _remote_is_loopback():
                return _loopback_refusal()
            body = request.get_json(force=True, silent=True)
            status, payload = engine_config_api.put_engine_config(
                self.engine_registry, self.receiver_tasks, type_name, body)
            return jsonify(payload), status

        # -- OSC relay, MIDI ports, log tail --
        @app.route("/api/osc-relay", methods=["GET"])
        def get_osc_relay() -> Response:
            if not _remote_is_loopback():
                return _loopback_refusal()
            if self.osc_relay_controller is None:
                return jsonify({"error": "osc relay is disabled (--no-osc-relay)"}), 404
            return jsonify(self.osc_relay_controller.snapshot())

        @app.route("/api/osc-relay", methods=["PUT"])
        def put_osc_relay() -> Response:
            if not _remote_is_loopback():
                return _loopback_refusal()
            if self.osc_relay_controller is None:
                return jsonify({"error": "osc relay is disabled (--no-osc-relay)"}), 404
            body = request.get_json(force=True, silent=True)
            try:
                return jsonify({"ok": True, **self.osc_relay_controller.apply(body)})
            except OscRelayError as exc:
                return jsonify({"error": str(exc)}), 400
            except (OscRelayUpdateError, OSError) as exc:
                return jsonify({"error": str(exc)}), 500

        @app.route("/api/midi/ports", methods=["GET"])
        def get_midi_ports() -> Response:
            if not _remote_is_loopback():
                return _loopback_refusal()
            from windows.midi import MidiError, get_port_snapshot
            payload: dict[str, Any] = {"inputs": None, "outputs": None, "error": None}
            try:
                snapshot = get_port_snapshot()
                payload["inputs"] = snapshot.input_names
                payload["outputs"] = snapshot.output_names
            except MidiError as exc:
                payload["error"] = str(exc)
            payload["selected"] = {
                role: {"requested": self.requested_ports.get(role), "resolved": resolved}
                for role, resolved in (("output", self.midi_port),
                                       ("feedback", self.feedback_port),
                                       ("pulse", self.pulse_port))
            }
            return jsonify(payload)

        @app.route("/api/logs/tail", methods=["GET"])
        def get_log_tail() -> Response:
            if not _remote_is_loopback():
                return _loopback_refusal()
            raw = request.args.get("lines", "200")
            if not (raw.isascii() and raw.isdigit() and len(raw) <= 4 and 1 <= int(raw) <= 1000):
                return jsonify({"error": "lines must be an integer from 1 to 1000"}), 400
            if self.log_ring is None:
                return jsonify({"error": "log ring is not installed"}), 503
            lines = self.log_ring.tail(int(raw))
            return jsonify({"lines": lines, "count": len(lines),
                            "log_file": str(self.log_file_path) if self.log_file_path else None})

        @app.route("/api/engines/refresh", methods=["POST"])
        def refresh_engines() -> Response:
            """Dev endpoint: trigger every engine's `refresh()` hook.

            Replaces the old periodic REST polling that was choking
            Arena's MIDI dispatch (2026-05-11 EVENING REST elimination).
            Engines re-pull their one-shot init-time state on demand
            (e.g. V-C-B dashboard tunables, StageFlow look altNames).
            """
            if self.engine_registry is None:
                return jsonify({"error": "no engine registry"}), 404
            results = self.engine_registry.refresh()
            return jsonify({"ok": True, "results": results})

        return app

    def _current_engine_states(self) -> dict[str, bool]:
        """Snapshot loaded engines' active flags for persisting into a preset."""
        if self.engine_registry is None:
            return {}
        try:
            return self.engine_registry.current_states()
        except Exception:
            return {}

    def _find_engine(self, type_name: str):
        if self.engine_registry is None:
            return None
        for engine in self.engine_registry.engines:
            if engine.type_name == type_name:
                return engine
        return None

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run_in_thread(self) -> threading.Thread:
        class LiveRequestHandler(WSGIRequestHandler):
            def run_wsgi(self):
                if self.path.split("?", 1)[0] == "/api/live/events":
                    self.connection.settimeout(0.5)
                return super().run_wsgi()

        self._http_server = make_server("127.0.0.1", self.port, self._app, threaded=True,
                                       request_handler=LiveRequestHandler)
        # server_close waits for every response to finish, including shutdown's
        # 202. A timer or a daemon request thread could truncate that response.
        self._http_server.daemon_threads = False
        self.port = self._http_server.server_port
        t = threading.Thread(
            target=self._http_server.serve_forever,
            kwargs={"poll_interval": 0.05},
            daemon=True,
            name="ui-server",
        )
        self._thread = t
        t.start()
        return t

    def stop(self) -> None:
        """Close HTTP from the bridge owner, after in-flight replies finish."""
        self.live_events.close()
        if self._http_server is not None:
            self._http_server.shutdown()
            self._http_server.server_close()
            self._thread.join()
            self._http_server = None
            self._thread = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


def _validate_macro_entry(body: dict[str, Any]) -> str | None:
    name = body.get("name", "")
    if not isinstance(name, str) or not name.strip():
        return "macro name is required"
    t = body.get("type")
    if t == "macro_cc":
        if body.get("gesture") not in {"click", "long_press"}:
            return "gesture must be 'click' or 'long_press'"
        fade = body.get("fade_duration_seconds")
        if fade is not None and (not isinstance(fade, (int, float)) or float(fade) <= 0):
            return "fade_duration_seconds must be a positive number"
    elif t == "relative_cc":
        if not isinstance(body.get("step_value"), int):
            return "step_value must be an integer"
        if not isinstance(body.get("repeat_interval_ms"), int) or body["repeat_interval_ms"] <= 0:
            return "repeat_interval_ms must be a positive integer"
    elif t == "staged_note_macro":
        mc = body.get("modifier_channel", 0)
        tc = body.get("trigger_channel", 1)
        if not isinstance(mc, int) or not isinstance(tc, int):
            return "modifier_channel and trigger_channel must be integers"
        if mc == tc:
            return "modifier_channel and trigger_channel must differ"
        ra = body.get("refresh_actions", [])
        if not isinstance(ra, list) or not all(isinstance(x, str) for x in ra):
            return "refresh_actions must be a list of strings"
        for k in ("macro_delay_ms", "modifier_hold_ms"):
            v = body.get(k)
            if v is not None and (not isinstance(v, int) or v <= 0):
                return f"{k} must be a positive integer"
    else:
        return f"unsupported macro type: {t!r}"
    return None
