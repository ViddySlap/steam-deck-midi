"""Localhost web UI server for editing MIDI mappings."""

from __future__ import annotations

import json
import re
import threading
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request, send_from_directory

from windows.config import (
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

_SAFE_FILENAME_RE = re.compile(r'^[A-Za-z0-9 _\-]+$')


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


def _safe_preset_name(name: str) -> str | None:
    """Return sanitised filename (without .json) or None if invalid."""
    name = name.strip()
    if not name or not _SAFE_FILENAME_RE.match(name):
        return None
    return name


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
    ) -> None:
        self.base_map_path = base_map_path
        self.presets_dir = presets_dir
        self.macro_library_path = macro_library_path
        self.actions_yaml_path = actions_yaml_path
        self.reload_event = reload_event
        self.port = port
        self.engine_registry = engine_registry
        self._app = self._build_app()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_active_preset_path(self) -> Path:
        return get_active_preset_path(self.presets_dir, self.base_map_path)

    def _load_raw_json(self) -> dict[str, Any]:
        active = self._get_active_preset_path()
        try:
            return json.loads(active.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

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

        # ── Mappings ───────────────────────────────────────────────

        @app.route("/api/mappings", methods=["GET"])
        def get_mappings() -> Response:
            try:
                return jsonify(self._load_raw_json())
            except Exception as exc:
                return jsonify({"error": str(exc)}), 500

        @app.route("/api/actions", methods=["GET"])
        def get_actions() -> Response:
            return jsonify({"actions": self._load_actions()})

        @app.route("/api/conflicts", methods=["POST"])
        def check_conflicts() -> Response:
            body = request.get_json(force=True, silent=True) or {}
            return jsonify({"conflicts": _detect_conflicts(body.get("mappings", {}))})

        @app.route("/api/save", methods=["POST"])
        def save_mappings() -> Response:
            body = request.get_json(force=True, silent=True)
            if not isinstance(body, dict):
                return jsonify({"error": "expected JSON object"}), 400
            mappings_raw = body.get("mappings")
            if not isinstance(mappings_raw, dict):
                return jsonify({"error": "missing 'mappings' key"}), 400

            candidate: dict[str, Any] = {"mappings": mappings_raw}
            if "macro_settings" in body:
                candidate["macro_settings"] = body["macro_settings"]
            if "analog_settings" in body:
                candidate["analog_settings"] = body["analog_settings"]

            import tempfile, os
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            ) as tmp:
                json.dump(candidate, tmp)
                tmp_path = tmp.name
            try:
                load_midi_map(tmp_path)
            except ConfigError as exc:
                return jsonify({"error": str(exc)}), 422
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

            active = self._get_active_preset_path()
            active.write_text(json.dumps(candidate, indent=2), encoding="utf-8")
            self.reload_event.set()
            return jsonify({"ok": True, "saved_to": active.name})

        @app.route("/api/reset", methods=["POST"])
        def factory_reset() -> Response:
            """Overwrite the active preset with factory defaults."""
            factory_content = self.base_map_path.read_text(encoding="utf-8")
            active = self._get_active_preset_path()
            active.write_text(factory_content, encoding="utf-8")
            self.reload_event.set()
            return jsonify({"ok": True})

        # ── Presets ────────────────────────────────────────────────

        @app.route("/api/presets", methods=["GET"])
        def get_presets() -> Response:
            return jsonify({"presets": self._list_presets()})

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
            current_content = self._get_active_preset_path().read_text(encoding="utf-8")
            new_path.write_text(current_content, encoding="utf-8")
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
        t = threading.Thread(
            target=self._app.run,
            kwargs={"host": "127.0.0.1", "port": self.port,
                    "use_reloader": False, "debug": False},
            daemon=True,
            name="ui-server",
        )
        t.start()
        return t

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
