"""Localhost web UI server for editing MIDI mappings."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request, send_from_directory

from windows.config import (
    AnalogSettings,
    AxisToCCMapping,
    ConfigError,
    ControlChangeMapping,
    MacroCCMapping,
    MacroSettings,
    MidiMapping,
    NoteMapping,
    ReceiverConfig,
    RelativeCCMapping,
    StagedNoteMacroMapping,
    load_effective_midi_map,
    load_midi_map,
)

# ---------------------------------------------------------------------------
# Intentional-conflict allow-list (from wiki/reference/intentional-conflicts.md)
# Pairs (channel, cc) that are allowed to be shared between multiple actions.
# Same-CC-different-channel sharing is also intentional for layer publishers.
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
# CC numbers that intentionally appear on multiple channels (layer publishers)
INTENTIONAL_MULTI_CHANNEL_CC: frozenset[int] = frozenset({74, 78, 79})


def _mapping_to_dict(m: MidiMapping) -> dict[str, Any]:
    """Convert a mapping dataclass to a plain JSON-serialisable dict."""
    if isinstance(m, NoteMapping):
        return {
            "type": "note",
            "channel": m.channel,
            "note": m.note,
            "velocity": m.velocity,
        }
    if isinstance(m, ControlChangeMapping):
        return {
            "type": "cc",
            "channel": m.channel,
            "cc": m.cc,
            "on_value": m.on_value,
            "off_value": m.off_value,
        }
    if isinstance(m, MacroCCMapping):
        return {
            "type": "macro_cc",
            "channel": m.channel,
            "cc": m.cc,
            "gesture": m.gesture,
        }
    if isinstance(m, RelativeCCMapping):
        return {
            "type": "relative_cc",
            "channel": m.channel,
            "cc": m.cc,
            "step_value": m.step_value,
            "repeat_interval_ms": m.repeat_interval_ms,
        }
    if isinstance(m, StagedNoteMacroMapping):
        return {
            "type": "staged_note_macro",
            "note": m.note,
            "velocity": m.velocity,
            "modifier_channel": m.modifier_channel,
            "trigger_channel": m.trigger_channel,
            "refresh_actions": list(m.refresh_actions),
        }
    if isinstance(m, AxisToCCMapping):
        return {
            "type": "axis_to_cc",
            "channel": m.channel,
            "cc": m.cc,
            "input_range": list(m.input_range),
            "output_range": list(m.output_range),
            "deadzone": m.deadzone,
            "curve": m.curve,
        }
    raise TypeError(f"unknown mapping type: {type(m)!r}")


def _detect_conflicts(
    mappings: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Return a list of conflict descriptors for any (channel, cc) pair that is
    shared by multiple actions and is NOT on the intentional allow-list.
    """
    from collections import defaultdict

    by_channel_cc: dict[tuple[int, int], list[str]] = defaultdict(list)
    cc_channels: dict[int, set[int]] = defaultdict(set)

    for action, spec in mappings.items():
        if not isinstance(spec, dict):
            continue
        t = spec.get("type")
        ch = spec.get("channel", 0)
        cc = spec.get("cc")
        note = spec.get("note")
        if cc is not None:
            by_channel_cc[(int(ch), int(cc))].append(action)
            cc_channels[int(cc)].add(int(ch))

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
        conflicts.append(
            {
                "kind": "same_channel_cc",
                "channel": ch,
                "cc": cc,
                "actions": actions,
                "intentional": False,
            }
        )
    return conflicts


class MappingUIServer:
    def __init__(
        self,
        base_map_path: Path,
        local_map_path: Path,
        actions_yaml_path: Path,
        reload_event: threading.Event,
        port: int = 7723,
    ) -> None:
        self.base_map_path = base_map_path
        self.local_map_path = local_map_path
        self.actions_yaml_path = actions_yaml_path
        self.reload_event = reload_event
        self.port = port
        self._app = self._build_app()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_raw_json(self) -> dict[str, Any]:
        """Return the effective merged mapping as a plain dict (not validated)."""
        if self.local_map_path.exists():
            try:
                local_raw = json.loads(self.local_map_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                local_raw = {}
        else:
            local_raw = {}
        try:
            base_raw = json.loads(self.base_map_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            base_raw = {}

        base_mappings = base_raw.get("mappings") or {}
        local_mappings = local_raw.get("mappings") or {}
        merged_mappings = {**base_mappings, **local_mappings}

        base_macro = base_raw.get("macro_settings") or {}
        local_macro = local_raw.get("macro_settings") or {}
        merged_macro = {**base_macro, **local_macro}

        base_analog = base_raw.get("analog_settings") or {}
        local_analog = local_raw.get("analog_settings") or {}
        merged_analog = {**base_analog, **local_analog}

        result: dict[str, Any] = {"mappings": merged_mappings}
        if merged_macro:
            result["macro_settings"] = merged_macro
        if merged_analog:
            result["analog_settings"] = merged_analog
        return result

    def _load_actions(self) -> list[str]:
        try:
            import yaml  # type: ignore[import-untyped]
            data = yaml.safe_load(self.actions_yaml_path.read_text(encoding="utf-8"))
            return list(data.get("actions", []))
        except ImportError:
            # Parse actions.yaml manually without PyYAML
            lines = self.actions_yaml_path.read_text(encoding="utf-8").splitlines()
            actions: list[str] = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("- "):
                    actions.append(stripped[2:].strip())
            return actions
        except OSError:
            return []

    # ------------------------------------------------------------------
    # Flask app
    # ------------------------------------------------------------------

    def _build_app(self) -> Flask:
        static_dir = Path(__file__).parent / "static"
        app = Flask(__name__, static_folder=str(static_dir))
        app.config["JSON_SORT_KEYS"] = False

        # Silence Flask request logs (terminal already shows receiver output)
        import logging
        log = logging.getLogger("werkzeug")
        log.setLevel(logging.ERROR)

        @app.route("/")
        def index() -> Response:
            return send_from_directory(str(static_dir), "index.html")

        @app.route("/api/mappings", methods=["GET"])
        def get_mappings() -> Response:
            try:
                data = self._load_raw_json()
                return jsonify(data)
            except Exception as exc:
                return jsonify({"error": str(exc)}), 500

        @app.route("/api/actions", methods=["GET"])
        def get_actions() -> Response:
            return jsonify({"actions": self._load_actions()})

        @app.route("/api/conflicts", methods=["POST"])
        def check_conflicts() -> Response:
            body = request.get_json(force=True, silent=True) or {}
            mappings = body.get("mappings", {})
            conflicts = _detect_conflicts(mappings)
            return jsonify({"conflicts": conflicts})

        @app.route("/api/save", methods=["POST"])
        def save_mappings() -> Response:
            body = request.get_json(force=True, silent=True)
            if not isinstance(body, dict):
                return jsonify({"error": "expected JSON object"}), 400

            mappings_raw = body.get("mappings")
            if not isinstance(mappings_raw, dict):
                return jsonify({"error": "missing 'mappings' key"}), 400

            # Validate by round-tripping through config parser
            import tempfile, os
            candidate: dict[str, Any] = {"mappings": mappings_raw}
            if "macro_settings" in body:
                candidate["macro_settings"] = body["macro_settings"]
            if "analog_settings" in body:
                candidate["analog_settings"] = body["analog_settings"]

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            ) as tmp:
                json.dump(candidate, tmp)
                tmp_path = tmp.name
            try:
                load_midi_map(tmp_path)
            except ConfigError as exc:
                os.unlink(tmp_path)
                return jsonify({"error": str(exc)}), 422
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

            # Write to local override file
            self.local_map_path.write_text(
                json.dumps(candidate, indent=2), encoding="utf-8"
            )

            # Signal the receiver to reload
            self.reload_event.set()
            return jsonify({"ok": True, "saved_to": str(self.local_map_path)})

        @app.route("/api/reset", methods=["POST"])
        def reset_to_base() -> Response:
            """Delete the local override so the base map takes effect."""
            if self.local_map_path.exists():
                self.local_map_path.unlink()
            self.reload_event.set()
            return jsonify({"ok": True})

        return app

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run_in_thread(self) -> threading.Thread:
        t = threading.Thread(
            target=self._app.run,
            kwargs={"host": "127.0.0.1", "port": self.port, "use_reloader": False, "debug": False},
            daemon=True,
            name="ui-server",
        )
        t.start()
        return t

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"
