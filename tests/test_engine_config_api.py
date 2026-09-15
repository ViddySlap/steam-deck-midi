"""GET/PUT /api/engines/<type>/config and the receiver-thread engine swap."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from tests._engine_helpers import RecordingMidiOut
from tests.test_ui_server import _make_server
from windows import engine_config_api
from windows.config import NoteMapping
from windows.engines.autopilot import AutopilotEngine
from windows.engines.base import Engine
from windows.engines.registry import EngineRegistry, engine_type_names, load_engines
from windows.receiver import ActionReceiver
from windows.receiver_tasks import ReceiverTaskQueue

REPO = Path(__file__).resolve().parents[1]
FACTORY = REPO / "config" / "engines.factory"


def _closed_tcp_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


class _TreeMixin:
    """A temp config tree: engines/ (user), engines.factory/ (copies), state/.

    Every OSC and REST target in a copied stanza is rewritten to loopback
    ports this test owns: a bound UDP sink for OSC and a closed TCP port for
    REST, so no packet leaves the machine.
    """

    def make_tree(self, factory_types=("autopilot", "global_color")):
        tmp = tempfile.mkdtemp(prefix="sdauto-a2-")
        self.addCleanup(shutil.rmtree, tmp, True)
        self.root = Path(tmp)
        self.user_dir = self.root / "engines"
        self.factory_dir = self.root / "engines.factory"
        self.user_dir.mkdir()
        self.factory_dir.mkdir()
        self.osc_sink = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.osc_sink.bind(("127.0.0.1", 0))
        self.addCleanup(self.osc_sink.close)
        self.rest_url = f"http://127.0.0.1:{_closed_tcp_port()}"
        for type_name in factory_types:
            spec = json.loads((FACTORY / f"{type_name}.json").read_text(encoding="utf-8"))
            (self.factory_dir / f"{type_name}.json").write_text(
                json.dumps(self.loopback(spec), indent=2), encoding="utf-8")

    def loopback(self, spec):
        spec = json.loads(json.dumps(spec))
        port = self.osc_sink.getsockname()[1]
        for holder in (spec, spec.get("outputs", {})):
            if "osc" in holder:
                holder["osc"] = {"host": "127.0.0.1", "port": port}
            if "rest" in holder:
                holder["rest"] = {"base_url": self.rest_url, "timeout_seconds": 0.2}
        return spec

    def factory_spec(self, type_name):
        return json.loads((self.factory_dir / f"{type_name}.json").read_text(encoding="utf-8"))

    def load(self, midi=None):
        self.midi = midi if midi is not None else RecordingMidiOut()
        registry = load_engines(self.user_dir, self.midi, state_dir=self.root / "state")
        self.addCleanup(registry.shutdown)
        return registry

    def server(self, registry, tasks):
        server, _, tmpdir, *_ = _make_server()
        self.addCleanup(shutil.rmtree, tmpdir, True)
        server.engine_registry = registry
        server.receiver_tasks = tasks
        return server


class _ReceiverThread:
    """Stand-in for serve_forever: drains tasks until stopped."""

    def __init__(self, tasks: ReceiverTaskQueue) -> None:
        self.tasks = tasks
        self.stop = threading.Event()
        self.ident = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        self.ident = threading.get_ident()
        while not self.stop.is_set():
            self.tasks.drain()
            time.sleep(0.002)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        self.thread.join(5)


class RegistryReplaceTests(unittest.TestCase):
    def test_remove_note_emit_filter_unregisters_only_that_callback(self):
        registry = EngineRegistry()
        seen = []
        first = lambda ch, note, vel, now: seen.append("first") or False
        second = lambda ch, note, vel, now: seen.append("second") or True
        registry.add_note_emit_filter(first)
        registry.add_note_emit_filter(second)
        self.assertTrue(registry.remove_note_emit_filter(first))
        self.assertFalse(registry.remove_note_emit_filter(first))
        self.assertTrue(registry.should_emit_note(0, 60, 127, 0.0))
        self.assertEqual(seen, ["second"])

    def test_replace_removes_filters_shuts_down_keeps_slot_and_binds(self):
        events = []

        class Fake(Engine):
            type_name = "fake"

            def bind_registry(self, registry):
                events.append(("bind", self.name))
                registry.add_note_emit_filter(self.flt)

            def flt(self, ch, note, vel, now):
                events.append(("filter", self.name))
                return True

            def shutdown(self):
                events.append(("shutdown", self.name,
                               any(getattr(cb, "__self__", None) is self for cb in registry._note_emit_filters)))

        before, old, after = (Fake(n, {}, RecordingMidiOut()) for n in ("before", "old", "after"))
        registry = EngineRegistry([before, old, after])
        for engine in registry.engines:
            engine.bind_registry(registry)
        new = Fake("new", {}, RecordingMidiOut())
        events.clear()
        registry.replace(old, new)
        self.assertEqual([e.name for e in registry.engines], ["before", "new", "after"])
        # The old filter was already gone when shutdown ran, then new was bound.
        self.assertEqual(events, [("shutdown", "old", False), ("bind", "new")])
        events.clear()
        registry.should_emit_note(0, 60, 127, 0.0)
        self.assertEqual([name for kind, name in events], ["before", "after", "new"])
        with self.assertRaises(ValueError):
            registry.replace(old, new)


class EngineConfigRouteTests(_TreeMixin, unittest.TestCase):
    def setUp(self):
        self.make_tree()
        self.tasks = ReceiverTaskQueue()

    def test_every_engine_type_is_classified_exactly_once(self):
        swappable = engine_config_api.LIVE_SWAPPABLE_TYPES
        restart = set(engine_config_api.RESTART_REQUIRED_REASONS)
        self.assertEqual(swappable & restart, set())
        self.assertEqual(swappable | restart, set(engine_type_names()))

    def test_get_reports_factory_then_user_source(self):
        registry = self.load()
        client = self.server(registry, self.tasks)._app.test_client()
        body = client.get("/api/engines/autopilot/config").get_json()
        self.assertEqual((body["source"], Path(body["path"]).parent.name), ("factory", "engines.factory"))
        self.assertEqual(body["spec"], self.factory_spec("autopilot"))
        self.assertEqual((body["loaded"], body["live_swappable"], body["restart_required_reason"]),
                         (True, True, None))
        user = {**self.factory_spec("autopilot"), "update_hz": 20}
        (self.user_dir / "autopilot.json").write_text(json.dumps(user))
        body = client.get("/api/engines/autopilot/config").get_json()
        self.assertEqual((body["source"], body["spec"]["update_hz"]), ("user", 20))
        self.assertEqual(client.get("/api/engines/nope/config").status_code, 404)
        self.assertEqual(client.get("/api/engines/osc_sync/config").status_code, 404)  # no stanza

    def test_put_writes_only_the_user_file_and_swaps_the_live_instance(self):
        registry = self.load()
        old = registry.get_by_type("autopilot")
        factory_before = {p.name: _sha(p) for p in self.factory_dir.iterdir()}
        client = self.server(registry, self.tasks)._app.test_client()
        spec = {**self.factory_spec("autopilot"), "update_hz": 20, "name": "Autopilot"}
        del spec["type"]
        with _ReceiverThread(self.tasks):
            response = client.put("/api/engines/autopilot/config", json=spec)
        self.assertEqual(response.status_code, 200, response.get_json())
        on_disk = json.loads((self.user_dir / "autopilot.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk, {**spec, "type": "autopilot"})
        self.assertEqual(sorted(p.name for p in self.user_dir.iterdir()), ["autopilot.json"])
        self.assertEqual({p.name: _sha(p) for p in self.factory_dir.iterdir()}, factory_before)
        new = registry.get_by_type("autopilot")
        self.assertIsNot(new, old)
        self.assertIsInstance(new, AutopilotEngine)
        self.assertEqual(new.tick_interval_seconds(), 1.0 / 20)
        self.assertEqual([e.type_name for e in registry.engines], ["autopilot", "global_color"])
        # A reload from disk now yields the same stanza the live engine runs.
        self.assertEqual(client.get("/api/engines/autopilot/config").get_json()["source"], "user")

    def test_swap_runs_on_the_receiver_thread(self):
        registry = self.load()
        client = self.server(registry, self.tasks)._app.test_client()
        ran_on = []
        original = registry.replace
        with patch.object(registry, "replace",
                          side_effect=lambda o, n: (ran_on.append(threading.get_ident()), original(o, n))), \
                _ReceiverThread(self.tasks) as receiver:
            response = client.put("/api/engines/autopilot/config", json=self.factory_spec("autopilot"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ran_on, [receiver.ident])
        self.assertNotEqual(receiver.ident, threading.get_ident())

    def test_replaced_autopilot_filter_is_gone(self):
        consulted = []
        real = AutopilotEngine._note_emit_filter

        def spy(engine, channel, note, velocity, now):
            consulted.append(engine)
            return real(engine, channel, note, velocity, now)

        with patch.object(AutopilotEngine, "_note_emit_filter", spy):
            registry = self.load()
            old = registry.get_by_type("autopilot")
            client = self.server(registry, self.tasks)._app.test_client()
            registry.should_emit_note(0, 60, 127, 0.0)
            self.assertEqual(consulted, [old])
            with _ReceiverThread(self.tasks):
                self.assertEqual(client.put("/api/engines/autopilot/config",
                                            json=self.factory_spec("autopilot")).status_code, 200)
            new = registry.get_by_type("autopilot")
            consulted.clear()
            registry.should_emit_note(0, 60, 127, 0.0)
        self.assertEqual(consulted, [new])
        self.assertEqual([getattr(cb, "__self__", None) for cb in registry._note_emit_filters], [new])

    def test_swap_carries_the_runtime_active_flag(self):
        registry = self.load()
        registry.set_active_by_type("autopilot", False)
        client = self.server(registry, self.tasks)._app.test_client()
        with _ReceiverThread(self.tasks):
            body = client.put("/api/engines/autopilot/config", json=self.factory_spec("autopilot")).get_json()
        self.assertFalse(body["active"])
        self.assertFalse(registry.get_by_type("autopilot").active)

    def test_invalid_input_writes_nothing_and_keeps_the_instance(self):
        target = self.user_dir / "autopilot.json"
        target.write_text(json.dumps(self.factory_spec("autopilot")))
        registry = self.load()
        old = registry.get_by_type("autopilot")
        before = _sha(target)
        client = self.server(registry, self.tasks)._app.test_client()
        bad_hz = {**self.factory_spec("autopilot"), "update_hz": "fast"}
        cases = [
            ("PUT", "/api/engines/autopilot/config", bad_hz, 400),
            ("PUT", "/api/engines/autopilot/config", [], 400),
            ("PUT", "/api/engines/autopilot/config", {**bad_hz, "update_hz": 30, "type": "global_color"}, 400),
            ("PUT", "/api/engines/autopilot/config", {**self.factory_spec("autopilot"), "enabled": False}, 409),
            ("PUT", "/api/engines/nope/config", {}, 404),
            ("PUT", "/api/engines/osc_sync/config", {"type": "osc_sync"}, 409),
        ]
        with _ReceiverThread(self.tasks):
            for method, path, body, status in cases:
                with self.subTest(path=path, body=str(body)[:40]):
                    response = client.open(path, method=method, json=body)
                    self.assertEqual(response.status_code, status, response.get_json())
        self.assertIn("invalid autopilot config", client.put("/api/engines/autopilot/config", json=bad_hz).get_json()["error"])
        self.assertEqual(_sha(target), before)
        self.assertFalse((self.user_dir / "osc_sync.json").exists())
        self.assertEqual(sorted(p.name for p in self.user_dir.iterdir()), ["autopilot.json"])
        self.assertIs(registry.get_by_type("autopilot"), old)

    def test_restart_required_types_answer_409_and_write_nothing(self):
        registry = self.load()
        client = self.server(registry, self.tasks)._app.test_client()
        for type_name in sorted(engine_config_api.RESTART_REQUIRED_REASONS):
            with self.subTest(type_name=type_name):
                response = client.put(f"/api/engines/{type_name}/config", json={"type": type_name})
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.get_json()["error"], "restart_required")
                self.assertFalse((self.user_dir / f"{type_name}.json").exists())

    def test_other_user_file_for_the_type_is_a_conflict(self):
        (self.user_dir / "aaa.json").write_text(json.dumps(self.factory_spec("autopilot")))
        registry = self.load()
        before = _sha(self.user_dir / "aaa.json")
        client = self.server(registry, self.tasks)._app.test_client()
        response = client.put("/api/engines/autopilot/config", json=self.factory_spec("autopilot"))
        self.assertEqual((response.status_code, response.get_json()["error"]), (409, "config_file_conflict"))
        self.assertFalse((self.user_dir / "autopilot.json").exists())
        self.assertEqual(_sha(self.user_dir / "aaa.json"), before)

    def test_no_receiver_loop_times_out_writes_nothing_and_never_runs_later(self):
        registry = self.load()
        old = registry.get_by_type("autopilot")
        client = self.server(registry, self.tasks)._app.test_client()
        tasks = self.tasks
        with patch.object(tasks, "run", lambda fn: ReceiverTaskQueue.run(tasks, fn, start_timeout=0.05)):
            response = client.put("/api/engines/autopilot/config", json=self.factory_spec("autopilot"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.tasks.drain(), 0)
        self.assertFalse((self.user_dir / "autopilot.json").exists())
        self.assertEqual([p.name for p in self.user_dir.iterdir()], [])
        self.assertIs(registry.get_by_type("autopilot"), old)

    def test_build_failure_on_the_receiver_thread_restores_the_file(self):
        target = self.user_dir / "autopilot.json"
        target.write_text(json.dumps(self.factory_spec("autopilot")))
        registry = self.load()
        old = registry.get_by_type("autopilot")
        before = _sha(target)
        client = self.server(registry, self.tasks)._app.test_client()
        real_build = engine_config_api.build_engine
        calls = []

        def build(spec, midi_out, *, state_dir):
            calls.append(midi_out)
            if len(calls) == 2:  # the receiver-thread build, after the probe
                raise OSError("disk went away")
            return real_build(spec, midi_out, state_dir=state_dir)

        with patch.object(engine_config_api, "build_engine", build), _ReceiverThread(self.tasks):
            response = client.put("/api/engines/autopilot/config",
                                  json={**self.factory_spec("autopilot"), "update_hz": 20})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(_sha(target), before)
        self.assertIs(registry.get_by_type("autopilot"), old)
        self.assertEqual(sorted(p.name for p in self.user_dir.iterdir()), ["autopilot.json"])


class SwapDuringTrafficTests(_TreeMixin, unittest.TestCase):
    """handle_datagram on the receiver thread while a PUT swaps autopilot."""

    NOTES = {f"ACT_{i}": 60 + i for i in range(8)}

    def setUp(self):
        self.make_tree(factory_types=("autopilot",))

    def payloads(self):
        out = []
        seq = 0
        for round_ in range(12):
            for action in self.NOTES:
                for state in ("down", "up"):
                    seq += 1
                    out.append(json.dumps({"action": action, "state": state, "seq": seq}).encode())
        return out

    def run_traffic(self, *, put: bool):
        registry = self.load()
        tasks = ReceiverTaskQueue()
        client = self.server(registry, tasks)._app.test_client()
        mappings = {a: NoteMapping(action=a, kind="note", channel=0, note=n) for a, n in self.NOTES.items()}
        receiver = ActionReceiver(self.midi, mappings, engine_registry=registry)
        payloads = self.payloads()
        errors = []
        swapped_at = []
        original_replace = registry.replace

        def replace(old, new):
            swapped_at.append(handled[0])
            original_replace(old, new)

        handled = [0]
        started = threading.Event()

        def receiver_loop():
            try:
                for index, payload in enumerate(payloads):
                    tasks.drain()
                    receiver.handle_datagram(payload, ("127.0.0.1", 50000), now=100.0 + index * 0.02)
                    handled[0] = index + 1
                    if index == 20:
                        started.set()
                    time.sleep(0.003)
                tasks.drain()
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        thread = threading.Thread(target=receiver_loop)
        with patch.object(registry, "replace", side_effect=replace), \
                self.assertNoLogs("windows", level=logging.ERROR):
            thread.start()
            response = None
            if put:
                started.wait(5)
                response = client.put("/api/engines/autopilot/config", json=self.factory_spec("autopilot"))
            thread.join(30)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        return list(self.midi.events), response, swapped_at, registry

    def test_recorded_midi_equals_a_run_without_the_put(self):
        baseline, _, no_swaps, _ = self.run_traffic(put=False)
        self.assertEqual(no_swaps, [])
        with_put, response, swapped_at, registry = self.run_traffic(put=True)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(len(swapped_at), 1)
        # The swap landed in the middle of the traffic, not before or after it.
        self.assertGreater(swapped_at[0], 20)
        self.assertLess(swapped_at[0], len(self.payloads()))
        self.assertEqual(len(baseline), len(self.payloads()))
        self.assertEqual(with_put, baseline)


if __name__ == "__main__":
    unittest.main()
