"""Tests for per-preset engine on/off states.

Covers the three layers of the feature:
  1. config: parsing the optional preset `engines: {type: bool}` map.
  2. registry: runtime active-gating + apply_engine_states / current_states.
  3. ui_server: the live toggle endpoint + save baking states into the preset.
"""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path

from windows.config import load_midi_map
from windows.engines.base import Engine
from windows.engines.registry import EngineRegistry
from windows.midi import DryRunMidiOut
from windows.ui_server import MappingUIServer


def _midi_out() -> DryRunMidiOut:
    return DryRunMidiOut(selected_port_name="test")


class RecordingEngine(Engine):
    """Minimal engine that counts the dispatches it receives."""

    def __init__(self, type_name: str, enabled: bool = True) -> None:
        self.type_name = type_name
        super().__init__(
            name=type_name, config={"enabled": enabled}, midi_out=_midi_out()
        )
        self.midi_in = 0
        self.notes = 0
        self.axes = 0
        self.clocks = 0
        self.ticks = 0

    def on_midi_in(self, channel, cc, value, now):  # noqa: ANN001
        self.midi_in += 1

    def on_note_in(self, channel, note, velocity, now):  # noqa: ANN001
        self.notes += 1

    def on_axis_event(self, action, value, now):  # noqa: ANN001
        self.axes += 1

    def on_midi_clock(self, message_type, now):  # noqa: ANN001
        self.clocks += 1

    def tick(self, now):  # noqa: ANN001
        self.ticks += 1


# ---------------------------------------------------------------------------
# 1. config parsing
# ---------------------------------------------------------------------------

class EngineStatesConfigTests(unittest.TestCase):
    def _load(self, doc: dict):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(doc, f)
            path = f.name
        return load_midi_map(path)

    def test_absent_engines_section_yields_empty_map(self):
        cfg = self._load({"mappings": {}})
        self.assertEqual(cfg.engine_states, {})

    def test_valid_engines_section_parsed(self):
        cfg = self._load(
            {"mappings": {}, "engines": {"global_color": False, "autopilot": True}}
        )
        self.assertEqual(
            cfg.engine_states, {"global_color": False, "autopilot": True}
        )

    def test_malformed_entries_dropped_not_raised(self):
        # Non-bool values and non-string keys are silently dropped so a bad
        # preset can never break the show-critical hot-reload path.
        cfg = self._load(
            {"mappings": {}, "engines": {"a": "yes", "b": True, "c": 1}}
        )
        self.assertEqual(cfg.engine_states, {"b": True})

    def test_non_dict_engines_section_ignored(self):
        cfg = self._load({"mappings": {}, "engines": ["global_color"]})
        self.assertEqual(cfg.engine_states, {})


# ---------------------------------------------------------------------------
# 2. registry gating
# ---------------------------------------------------------------------------

class RegistryGatingTests(unittest.TestCase):
    def test_inactive_engine_receives_no_dispatch(self):
        e = RecordingEngine("rec")
        reg = EngineRegistry([e])
        e.set_active(False)
        reg.on_midi_in(0, 1, 64, 0.0)
        reg.on_note_in(0, 60, 127, 0.0)
        reg.on_axis_event("GYRO", 5, 0.0)
        reg.on_midi_clock("clock", 0.0)
        reg.tick(0.0)
        self.assertEqual((e.midi_in, e.notes, e.axes, e.clocks, e.ticks), (0, 0, 0, 0, 0))

    def test_active_engine_receives_dispatch(self):
        e = RecordingEngine("rec")
        reg = EngineRegistry([e])
        reg.on_midi_in(0, 1, 64, 0.0)
        reg.tick(0.0)
        self.assertEqual((e.midi_in, e.ticks), (1, 1))

    def test_apply_engine_states_only_touches_listed(self):
        a = RecordingEngine("a")
        b = RecordingEngine("b")
        reg = EngineRegistry([a, b])
        reg.apply_engine_states({"a": False})  # b omitted -> unchanged
        self.assertFalse(a.active)
        self.assertTrue(b.active)

    def test_apply_engine_states_ignores_unknown_types(self):
        a = RecordingEngine("a")
        reg = EngineRegistry([a])
        reg.apply_engine_states({"nonexistent": False})  # must not raise
        self.assertTrue(a.active)

    def test_current_states_snapshot(self):
        a = RecordingEngine("a")
        b = RecordingEngine("b")
        b.set_active(False)
        reg = EngineRegistry([a, b])
        self.assertEqual(reg.current_states(), {"a": True, "b": False})

    def test_set_active_by_type_returns_found_flag(self):
        a = RecordingEngine("a")
        reg = EngineRegistry([a])
        self.assertTrue(reg.set_active_by_type("a", False))
        self.assertFalse(a.active)
        self.assertFalse(reg.set_active_by_type("missing", True))

    def test_active_flag_defaults_from_config_enabled(self):
        self.assertFalse(RecordingEngine("x", enabled=False).active)
        self.assertTrue(RecordingEngine("y", enabled=True).active)

    def test_shortest_tick_interval_ignores_inactive(self):
        class Ticky(RecordingEngine):
            def tick_interval_seconds(self):
                return 0.1

        e = Ticky("t")
        reg = EngineRegistry([e])
        self.assertEqual(reg.shortest_tick_interval(), 0.1)
        e.set_active(False)
        self.assertIsNone(reg.shortest_tick_interval())


# ---------------------------------------------------------------------------
# 3. ui_server endpoints
# ---------------------------------------------------------------------------

BASE_MAP = {"mappings": {"BTN_A": {"type": "note", "channel": 0, "note": 36}}}


class EngineUiServerTests(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.mkdtemp()
        base_path = Path(tmpdir) / "windows_midi_map.json"
        self.presets_dir = Path(tmpdir) / "presets"
        content = json.dumps(BASE_MAP)
        base_path.write_text(content, encoding="utf-8")
        self.presets_dir.mkdir()
        (self.presets_dir / "default.json").write_text(content, encoding="utf-8")
        (self.presets_dir / ".active").write_text("default.json", encoding="utf-8")
        (Path(tmpdir) / "actions.yaml").write_text("actions:\n  - BTN_A\n", encoding="utf-8")

        self.reg = EngineRegistry([RecordingEngine("rec1"), RecordingEngine("rec2")])
        self.server = MappingUIServer(
            base_map_path=base_path,
            presets_dir=self.presets_dir,
            macro_library_path=Path(tmpdir) / "macro_library.json",
            actions_yaml_path=Path(tmpdir) / "actions.yaml",
            reload_event=threading.Event(),
            engine_registry=self.reg,
        )
        self.client = self.server._app.test_client()

    def test_list_engines_includes_active(self):
        data = self.client.get("/api/engines").get_json()
        actives = {e["type"]: e["active"] for e in data["engines"]}
        self.assertEqual(actives, {"rec1": True, "rec2": True})

    def test_toggle_engine_active(self):
        resp = self.client.post("/api/engines/rec1/active", json={"active": False})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(self.reg.get_by_type("rec1").active)

    def test_toggle_unknown_engine_404(self):
        resp = self.client.post("/api/engines/nope/active", json={"active": False})
        self.assertEqual(resp.status_code, 404)

    def test_toggle_requires_bool(self):
        resp = self.client.post("/api/engines/rec1/active", json={"active": "off"})
        self.assertEqual(resp.status_code, 400)

    def test_save_bakes_engine_states_into_preset(self):
        # Turn rec2 off live, then save the preset.
        self.client.post("/api/engines/rec2/active", json={"active": False})
        resp = self.client.post("/api/save", json={"mappings": BASE_MAP["mappings"]})
        self.assertEqual(resp.status_code, 200)
        saved = json.loads((self.presets_dir / "default.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["engines"], {"rec1": True, "rec2": False})

    def test_save_as_bakes_engine_states(self):
        self.client.post("/api/engines/rec1/active", json={"active": False})
        resp = self.client.post("/api/presets/save-as", json={"name": "PTZ"})
        self.assertEqual(resp.status_code, 200)
        saved = json.loads((self.presets_dir / "PTZ.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["engines"], {"rec1": False, "rec2": True})


if __name__ == "__main__":
    unittest.main()
