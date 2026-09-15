"""Autopilot channel intent survives a bridge restart (sdauto A1).

Every test drives state through the REAL on_midi_in with the factory
config's CC numbers, then asserts the world: the JSON on disk, the fields of
a NEW engine built from the same config and state dir, the OSC and MIDI the
recording fakes captured, and the JSON the clear route returned.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import shutil
import stat
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from tests._engine_helpers import FakeOscClient, FakeRestClient, RecordingMidiOut
from windows.engines import autopilot_state
from windows.engines.autopilot import AutopilotEngine, ClipMode
from windows.engines.registry import EngineRegistry, load_engines

REPO = Path(__file__).resolve().parents[1]
FACTORY = json.loads((REPO / "config/engines.factory/autopilot.json").read_text(encoding="utf-8"))
CH = FACTORY["inputs"]["channel"]
VIDEO = FACTORY["inputs"]["video"]
FX = FACTORY["inputs"]["fx"]
LOGO = FACTORY["inputs"]["logo"]
RUNTIME_FIELDS = (
    "cycle_index", "beat_in_clip", "visible_layer", "target_layer",
    "crossfade_start_time", "bag", "last_clip", "clip_count_cache",
)


def _comp(layers: int = 8, clips: int = 3) -> dict:
    return {"layers": [
        {"clips": [{"video": {"file": f"c{j}"}} for j in range(clips)]} for _ in range(layers)
    ]}


class Rig:
    """One engine with recording fakes."""

    def __init__(self, state_dir: Path | None, config: dict | None = None) -> None:
        self.midi = RecordingMidiOut()
        self.osc = FakeOscClient()
        self.rest = FakeRestClient(_comp())
        self.engine = AutopilotEngine(
            "Autopilot",
            copy.deepcopy(config or FACTORY),
            self.midi,
            rest_client=self.rest,
            osc_client=self.osc,
            state_dir=state_dir,
        )
        self.registry = EngineRegistry([self.engine])
        self.engine.bind_registry(self.registry)

    def cc(self, cc: int, value: int, now: float = 0.0) -> None:
        self.engine.on_midi_in(CH, cc, value, now)


def _drive_show_state(rig: Rig) -> None:
    """A mid-show state touching all five fields on every channel."""
    # video: layers 1+3, beats idx 2 (=8), transition 64, RANDOM, enabled
    rig.cc(VIDEO["layer_ccs"]["1"], 127)
    rig.cc(VIDEO["layer_ccs"]["3"], 127)
    rig.cc(VIDEO["cc_beats"], 2)
    rig.cc(VIDEO["cc_transition"], 64)
    rig.cc(VIDEO["cc_mode"], 2)
    rig.cc(VIDEO["cc_enable"], 127)
    # fx: layer 5, beats idx 0 (=1), transition 127, LINEAR, enabled
    rig.cc(FX["layer_ccs"]["5"], 127)
    rig.cc(FX["cc_beats"], 0)
    rig.cc(FX["cc_transition"], 127)
    rig.cc(FX["cc_mode"], 1)
    rig.cc(FX["cc_enable"], 127)
    # logo: layer 7 only, beats idx 6 (=128), transition 10, NONE, NOT enabled
    rig.cc(LOGO["layer_ccs"]["7"], 127)
    rig.cc(LOGO["cc_beats"], 6)
    rig.cc(LOGO["cc_transition"], 10)


def _intent(engine: AutopilotEngine) -> dict:
    return {
        key: (s.enabled, s.beats_per_clip, s.transition_seconds, s.clip_mode, dict(s.layer_enabled))
        for key, s in engine._states.items()
    }


def _walk_keys(value) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for k, v in value.items():
            keys.add(k)
            keys |= _walk_keys(v)
    elif isinstance(value, list):
        for v in value:
            keys |= _walk_keys(v)
    return keys


class AutopilotStateTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="sdauto-a1-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.state_dir = self.tmp / "state"
        self.state_file = self.state_dir / autopilot_state.STATE_FILE_NAME


class RoundTripTests(AutopilotStateTestBase):
    def test_five_fields_survive_restart_and_runtime_is_fresh(self) -> None:
        first = Rig(self.state_dir)
        _drive_show_state(first)
        # Make runtime fields non-default: beats, clip draws, a crossfade.
        for beat in range(1, 40):
            first.engine._on_beat_boundary(beat * 0.5)
        first.engine.tick(20.0)
        expected = _intent(first.engine)
        self.assertTrue(expected["video"][0] and expected["fx"][0])
        self.assertFalse(expected["logo"][0])
        self.assertEqual(expected["video"][3], ClipMode.RANDOM)
        first.engine.shutdown()

        second = Rig(self.state_dir)
        self.assertEqual(_intent(second.engine), expected)
        for key, state in second.engine._states.items():
            fresh = AutopilotEngine("x", copy.deepcopy(FACTORY), RecordingMidiOut(),
                                    rest_client=FakeRestClient(), osc_client=FakeOscClient())._states[key]
            for name in RUNTIME_FIELDS:
                with self.subTest(channel=key, field=name):
                    self.assertEqual(getattr(state, name), getattr(fresh, name))

    def test_file_on_disk_has_schema_names_and_no_runtime_fields(self) -> None:
        rig = Rig(self.state_dir)
        _drive_show_state(rig)
        rig.engine.shutdown()
        document = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertEqual(document["schema"], autopilot_state.SCHEMA_VERSION)
        channels = document["engines"]["Autopilot"]["channels"]
        self.assertEqual(set(channels), {"video", "fx", "logo"})
        self.assertEqual(channels["video"]["clip_mode"], "RANDOM")
        self.assertEqual(channels["fx"]["clip_mode"], "LINEAR")
        self.assertEqual(channels["video"]["layer_enabled"], {"1": True, "2": False, "3": True, "4": False})
        self.assertEqual(channels["video"]["beats_per_clip"], 8)
        for fields in channels.values():
            self.assertEqual(set(fields), set(autopilot_state.INTENT_FIELDS))
        keys = _walk_keys(document)
        self.assertNotIn("crossfade_start_time", keys)
        for name in RUNTIME_FIELDS:
            self.assertNotIn(name, keys)
        leftovers = [p.name for p in self.state_dir.iterdir() if p.name != autopilot_state.STATE_FILE_NAME]
        self.assertEqual(leftovers, [], "atomic write must not leave temp files")

    def test_last_change_before_teardown_is_on_disk_even_with_a_slow_disk(self) -> None:
        rig = Rig(self.state_dir)
        real_fsync = os.fsync

        def slow_fsync(fd):
            time.sleep(0.05)
            real_fsync(fd)

        with mock.patch("windows.engines.autopilot_state.os.fsync", side_effect=slow_fsync):
            for value in range(0, 128):
                rig.cc(VIDEO["cc_transition"], value)
            rig.engine.shutdown()
        channels = json.loads(self.state_file.read_text(encoding="utf-8"))["engines"]["Autopilot"]["channels"]
        self.assertEqual(channels["video"]["transition_seconds"], FACTORY["inputs"]["transition_max_seconds"])

    def test_on_midi_in_never_touches_the_disk_on_the_calling_thread(self) -> None:
        rig = Rig(self.state_dir)
        caller = threading.get_ident()
        writers: list[int] = []
        real_replace = os.replace

        def spy_replace(src, dst):
            writers.append(threading.get_ident())
            real_replace(src, dst)

        with mock.patch("windows.engines.autopilot_state.os.replace", side_effect=spy_replace):
            rig.cc(VIDEO["cc_enable"], 127)
            rig.engine.shutdown()
        self.assertTrue(writers, "a write must have happened")
        self.assertNotIn(caller, writers)

    def test_each_field_change_alone_is_persisted(self) -> None:
        cases = (
            ("enabled", VIDEO["cc_enable"], 127, True),
            ("beats_per_clip", VIDEO["cc_beats"], 1, 4),
            ("transition_seconds", VIDEO["cc_transition"], 127, FACTORY["inputs"]["transition_max_seconds"]),
            ("clip_mode", VIDEO["cc_mode"], 1, "LINEAR"),
            ("layer_enabled", VIDEO["layer_ccs"]["2"], 127, {"1": False, "2": True, "3": False, "4": False}),
        )
        for field_name, cc, value, expected in cases:
            with self.subTest(field=field_name):
                state_dir = self.tmp / f"one-{field_name}"
                rig = Rig(state_dir)
                rig.cc(cc, value)
                rig.engine.shutdown()
                document = json.loads((state_dir / autopilot_state.STATE_FILE_NAME).read_text(encoding="utf-8"))
                self.assertEqual(document["engines"]["Autopilot"]["channels"]["video"][field_name], expected)

    def test_no_change_means_no_write(self) -> None:
        rig = Rig(self.state_dir)
        rig.cc(VIDEO["cc_enable"], 0)          # already off
        rig.cc(VIDEO["cc_beats"], 3)           # already 16
        rig.cc(VIDEO["cc_mode"], 0)            # already NONE
        rig.cc(VIDEO["cc_transition"], 0)      # already 0.0
        rig.cc(VIDEO["layer_ccs"]["1"], 0)     # already off
        rig.engine.shutdown()
        self.assertFalse(self.state_file.exists())

    def test_no_state_dir_writes_nothing(self) -> None:
        rig = Rig(None)
        _drive_show_state(rig)
        rig.engine.shutdown()
        self.assertIsNone(rig.engine._state_writer)
        self.assertFalse(self.state_dir.exists())


class InvalidFileTests(AutopilotStateTestBase):
    def _assert_defaults_and_bytes_kept(self, content: bytes) -> None:
        self.state_dir.mkdir()
        self.state_file.write_bytes(content)
        rig = Rig(self.state_dir)
        defaults = _intent(Rig(None).engine)
        self.assertEqual(_intent(rig.engine), defaults)
        rig.engine.tick(1.0)
        rig.cc(VIDEO["cc_enable"], 0)  # not a change
        self.assertEqual(rig.osc.sends, [])
        rig.engine.shutdown()
        self.assertEqual(self.state_file.read_bytes(), content)
        # The next valid change replaces it.
        rig = Rig(self.state_dir)
        rig.cc(VIDEO["cc_enable"], 127)
        rig.engine.shutdown()
        document = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertTrue(document["engines"]["Autopilot"]["channels"]["video"]["enabled"])

    def test_malformed_json(self) -> None:
        self._assert_defaults_and_bytes_kept(b'{"schema": 1, "engines": {"Autopilot": ')

    def test_future_schema(self) -> None:
        good = Rig(None)
        good.cc(VIDEO["cc_enable"], 127)
        document = good.engine._intent_document()
        document["schema"] = autopilot_state.SCHEMA_VERSION + 1
        self._assert_defaults_and_bytes_kept(json.dumps(document).encode())

    def test_wrong_field_type(self) -> None:
        good = Rig(None)
        good.cc(VIDEO["cc_enable"], 127)
        document = good.engine._intent_document()
        document["engines"]["Autopilot"]["channels"]["video"]["enabled"] = "yes"
        self._assert_defaults_and_bytes_kept(json.dumps(document).encode())

    def test_channel_and_layer_removed_from_config_are_ignored(self) -> None:
        rig = Rig(self.state_dir)
        _drive_show_state(rig)
        rig.engine.shutdown()
        document = json.loads(self.state_file.read_text(encoding="utf-8"))
        channels = document["engines"]["Autopilot"]["channels"]
        channels["strobe"] = copy.deepcopy(channels["video"])
        channels["video"]["layer_enabled"]["9"] = True
        self.state_file.write_text(json.dumps(document), encoding="utf-8")
        # A config without the logo channel's layer 7 and with no layer 9.
        config = copy.deepcopy(FACTORY)
        del config["inputs"]["logo"]["layer_ccs"]["7"]
        with self.assertLogs("windows.engines.autopilot", level="WARNING") as logs:
            restored = Rig(self.state_dir, config)
        state = restored.engine._states
        self.assertNotIn("strobe", state)
        self.assertNotIn(9, state["video"].layer_enabled)
        self.assertNotIn(7, state["logo"].layer_enabled)
        self.assertEqual(state["video"].layer_enabled, {1: True, 2: False, 3: True, 4: False})
        self.assertEqual(state["logo"].beats_per_clip, 128)
        warnings = [r for r in logs.records if "ignored" in r.getMessage()]
        self.assertEqual(len(warnings), 1, "ignored entries are logged once")


class RestoreSideEffectTests(AutopilotStateTestBase):
    def test_restored_enable_matches_a_live_enable_cc(self) -> None:
        live = Rig(self.state_dir)
        _drive_show_state(live)
        live.engine.tick(1.0)
        live.engine.shutdown()

        restored = Rig(self.state_dir)
        self.assertEqual(restored.osc.sends, [], "nothing is sent before the first dispatch")
        restored.engine.tick(1.0)

        self.assertTrue(live.osc.sends, "the live arm must record OSC (non-vacuous)")
        self.assertEqual(restored.osc.sends, live.osc.sends)
        # Both arms now defer a column note through the registry and re-emit it.
        for rig in (live, restored):
            self.assertFalse(rig.registry.should_emit_note(0, 82, 127, 2.0))
            rig.engine._on_beat_boundary(2.5)
        self.assertEqual(restored.midi.events, live.midi.events)
        self.assertEqual(live.midi.events, [("note_on", 0, 82, 127)])
        self.assertEqual(restored.osc.sends, live.osc.sends)
        runtime = lambda e: {k: (s.visible_layer, s.cycle_index, s.beat_in_clip) for k, s in e._states.items()}
        self.assertEqual(runtime(restored.engine), runtime(live.engine))

    def test_inactive_engine_sends_nothing_until_active(self) -> None:
        live = Rig(self.state_dir)
        _drive_show_state(live)
        live.engine.shutdown()
        restored = Rig(self.state_dir)
        restored.engine.set_active(False)
        restored.registry.tick(1.0)
        restored.registry.on_midi_in(CH, 1, 1, 1.0)
        self.assertEqual(restored.osc.sends, [])
        restored.engine.set_active(True)
        restored.registry.tick(2.0)
        self.assertIn(("/composition/layers/1/master", 1.0), restored.osc.sends)

    def test_restore_is_replayed_once(self) -> None:
        live = Rig(self.state_dir)
        _drive_show_state(live)
        live.engine.shutdown()
        restored = Rig(self.state_dir)
        restored.engine.tick(1.0)
        count = len(restored.osc.sends)
        restored.engine.tick(1.01)
        restored.engine.on_midi_in(CH, 1, 1, 1.02)
        self.assertEqual(len(restored.osc.sends), count)


class WriteFailureTests(AutopilotStateTestBase):
    def test_unwritable_state_dir_never_raises_into_on_midi_in(self) -> None:
        blocker = self.tmp / "not-a-dir"
        blocker.write_text("file where the state dir should be", encoding="utf-8")
        rig = Rig(blocker)
        _drive_show_state(rig)  # must not raise
        self.assertFalse(rig.engine._state_writer.flush())
        rig.engine.shutdown()  # must not raise
        self.assertTrue(rig.engine._states["video"].enabled)

    @unittest.skipIf(os.name == "nt" or os.geteuid() == 0, "POSIX non-root permission check")
    def test_read_only_state_dir_never_raises(self) -> None:
        self.state_dir.mkdir()
        self.state_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)
        self.addCleanup(self.state_dir.chmod, stat.S_IRWXU)
        rig = Rig(self.state_dir)
        rig.cc(VIDEO["cc_enable"], 127)
        self.assertFalse(rig.engine._state_writer.flush())
        rig.engine.shutdown()
        self.assertEqual(list(self.state_dir.iterdir()), [])

    def test_failure_log_is_rate_limited_to_one_per_60_seconds(self) -> None:
        now = [100.0]
        writer = autopilot_state.AutopilotStateWriter(self.tmp / "nope" / "x.json", clock=lambda: now[0])
        (self.tmp / "nope").write_text("blocker", encoding="utf-8")
        with self.assertLogs("windows.engines.autopilot_state", level="WARNING") as logs:
            for t in (100.0, 130.0, 159.9, 160.0, 170.0):
                now[0] = t
                writer.submit({"schema": 1, "engines": {}})
                self.assertFalse(writer.flush())
        writer.close()
        self.assertEqual(len(logs.records), 2)


class ClearRouteTests(AutopilotStateTestBase):
    def _server(self, engines):
        from tests.test_ui_server import _make_server
        server, _, tmpdir, *_ = _make_server()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        server.engine_registry = EngineRegistry(engines)
        return server._app.test_client()

    def test_clear_resets_to_defaults_and_persists(self) -> None:
        rig = Rig(self.state_dir)
        _drive_show_state(rig)
        client = self._server([rig.engine])
        response = client.post("/api/engines/autopilot/state/clear")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["persisted"])
        defaults = _intent(Rig(None).engine)
        self.assertEqual(_intent(rig.engine), defaults)
        for key, channel in body["channels"].items():
            self.assertFalse(channel["enabled"])
            self.assertEqual(channel["clip_mode"], "NONE")
            self.assertEqual(set(channel["layer_enabled"].values()), {False})
        # On disk, before any shutdown/flush by the test.
        channels = json.loads(self.state_file.read_text(encoding="utf-8"))["engines"]["Autopilot"]["channels"]
        self.assertEqual({k: v["enabled"] for k, v in channels.items()}, {"video": False, "fx": False, "logo": False})
        self.assertEqual(channels["logo"]["beats_per_clip"], 16)
        rig.engine.shutdown()
        self.assertEqual(_intent(Rig(self.state_dir).engine), defaults)
        self.assertEqual(sorted(p.name for p in self.state_dir.iterdir()), [autopilot_state.STATE_FILE_NAME])

    def test_clear_without_autopilot_is_404(self) -> None:
        client = self._server([])
        self.assertEqual(client.post("/api/engines/autopilot/state/clear").status_code, 404)

    def test_clear_without_state_dir_resets_but_reports_not_persisted(self) -> None:
        rig = Rig(None)
        _drive_show_state(rig)
        body = self._server([rig.engine]).post("/api/engines/autopilot/state/clear").get_json()
        self.assertFalse(body["persisted"])
        self.assertFalse(rig.engine._states["video"].enabled)

    def test_get_engines_reports_the_five_fields_per_channel(self) -> None:
        rig = Rig(self.state_dir)
        _drive_show_state(rig)
        body = self._server([rig.engine]).get("/api/engines").get_json()
        channels = body["engines"][0]["channels"]
        for key in ("video", "fx", "logo"):
            for name in autopilot_state.INTENT_FIELDS:
                self.assertIn(name, channels[key])
        self.assertEqual(channels["video"]["clip_mode"], "RANDOM")
        self.assertEqual(channels["video"]["layer_enabled"]["3"], True)
        rig.engine.shutdown()


class RegistryPlumbingTests(AutopilotStateTestBase):
    def _config_tree(self) -> Path:
        engines = self.tmp / "config" / "engines"
        engines.mkdir(parents=True)
        (engines / "autopilot.json").write_text(json.dumps(FACTORY), encoding="utf-8")
        return engines

    def setUp(self) -> None:
        super().setUp()
        for target, fake in (("ResolumeRestClient", FakeRestClient), ("OscClient", FakeOscClient)):
            patcher = mock.patch(f"windows.engines.autopilot.{target}", side_effect=lambda *a, _f=fake, **k: _f())
            patcher.start()
            self.addCleanup(patcher.stop)

    def _drive(self, registry) -> AutopilotEngine:
        engine = registry.get_by_type("autopilot")
        self.assertIsInstance(engine._osc, FakeOscClient)
        registry.on_midi_in(CH, VIDEO["cc_enable"], 127, 0.0)
        registry.shutdown()
        return engine

    def test_default_state_dir_is_config_state_beside_engines(self) -> None:
        engines = self._config_tree()
        with self.subTest("load"):
            engine = self._drive(load_engines(engines, RecordingMidiOut()))
        expected = self.tmp / "config" / "state" / autopilot_state.STATE_FILE_NAME
        self.assertEqual(engine._state_writer.path, expected)
        self.assertTrue(expected.is_file())
        self.assertEqual(sorted(p.name for p in engines.iterdir()), ["autopilot.json"])

    def test_state_dir_none_disables_persistence(self) -> None:
        engines = self._config_tree()
        with self.subTest("load"):
            engine = self._drive(load_engines(engines, RecordingMidiOut(), state_dir=None))
        self.assertIsNone(engine._state_writer)
        self.assertFalse((self.tmp / "config" / "state").exists())

    def test_state_dir_inside_engines_dir_is_refused(self) -> None:
        engines = self._config_tree()
        with self.subTest("load"):
            engine = self._drive(load_engines(engines, RecordingMidiOut(), state_dir=engines / "state"))
        self.assertIsNone(engine._state_writer)
        self.assertEqual(sorted(p.name for p in engines.iterdir()), ["autopilot.json"])

    def test_explicit_state_dir_restores_across_two_loads(self) -> None:
        engines = self._config_tree()
        with self.subTest("load"):
            self._drive(load_engines(engines, RecordingMidiOut(), state_dir=self.state_dir))
            again = load_engines(engines, RecordingMidiOut(), state_dir=self.state_dir)
        self.assertTrue(again.get_by_type("autopilot")._states["video"].enabled)
        again.shutdown()


if __name__ == "__main__":
    unittest.main()
