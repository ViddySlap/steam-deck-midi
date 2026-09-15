"""OSC relay, MIDI port and log-tail routes; loopback refusal; win_recv wiring."""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import shutil
import socket
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tests.test_receiver import FakeMidiOut
from tests.test_ui_server import _make_server
from windows import win_recv
from windows.log_ring import RING_CAPACITY, RingLogHandler, install_ring_handler
from windows.osc_relay import OscRelay, OscRelayController, parse_osc_relay_config
from windows.receiver_tasks import ReceiverTaskQueue
from windows.ui_server import MappingUIServer


def _udp_sink() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(2.0)
    return sock


def _free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _addr(sock: socket.socket) -> str:
    return "127.0.0.1:%d" % sock.getsockname()[1]


def _sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


class OscRelayRouteTests(unittest.TestCase):
    def setUp(self):
        self.server, _, tmpdir, *_ = _make_server()
        self.addCleanup(shutil.rmtree, tmpdir, True)
        self.path = Path(tmpdir) / "osc_relay.json"
        self.sink_a, self.sink_b = _udp_sink(), _udp_sink()
        self.addCleanup(self.sink_a.close)
        self.addCleanup(self.sink_b.close)
        self.listen = "127.0.0.1:%d" % _free_udp_port()
        spec = {"enabled": True, "listen": self.listen, "destinations": [_addr(self.sink_a)]}
        self.path.write_text(json.dumps(spec), encoding="utf-8")
        config = parse_osc_relay_config(spec)
        relay = OscRelay(config)
        self.assertTrue(relay.start())
        self.controller = OscRelayController(self.path, relay, config)
        self.addCleanup(self.controller.shutdown)
        self.server.osc_relay_controller = self.controller
        self.client = self.server._app.test_client()

    def send_through_relay(self, payload: bytes) -> None:
        host, port = self.controller.relay.config.listen_host, self.controller.relay.config.listen_port
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.sendto(payload, (host, port))

    def assert_receives(self, sink, payload):
        self.assertEqual(sink.recvfrom(65535)[0], payload)

    def assert_silent(self, sink):
        sink.settimeout(0.3)
        with self.assertRaises(socket.timeout):
            sink.recvfrom(65535)
        sink.settimeout(2.0)

    def test_get_reports_config_and_stats(self):
        body = self.client.get("/api/osc-relay").get_json()
        self.assertEqual(body["config"], {"enabled": True, "listen": self.listen,
                                          "destinations": [_addr(self.sink_a)]})
        self.assertTrue(body["running"])
        self.assertEqual(body["stats"]["destinations"], [_addr(self.sink_a)])
        self.assertEqual(body["path"], str(self.path))

    def test_put_writes_the_file_and_the_live_relay_forwards_to_the_new_destination(self):
        old_relay = self.controller.relay
        spec = {"enabled": True, "listen": self.listen, "destinations": [_addr(self.sink_b)]}
        response = self.client.put("/api/osc-relay", json=spec)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), spec)
        self.assertIsNot(self.controller.relay, old_relay)
        self.assertFalse(old_relay.running)
        self.assertEqual(self.controller.relay.stats()["destinations"], [_addr(self.sink_b)])
        self.send_through_relay(b"/after-put")
        self.assert_receives(self.sink_b, b"/after-put")
        self.assert_silent(self.sink_a)

    def test_invalid_config_is_400_and_changes_nothing(self):
        before = _sha(self.path)
        relay = self.controller.relay
        for body in ({"listen": self.listen, "destinations": [self.listen]},
                     {"listen": "nohost", "destinations": []},
                     {"enabled": "yes"}, [], None):
            with self.subTest(body=body):
                response = self.client.put("/api/osc-relay", json=body)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(_sha(self.path), before)
        self.assertIs(self.controller.relay, relay)
        self.send_through_relay(b"/still-a")
        self.assert_receives(self.sink_a, b"/still-a")

    def test_bind_failure_restores_the_previous_relay_and_file(self):
        holder = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows lets SO_REUSEADDR steal a port otherwise
            holder.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        holder.bind(("127.0.0.1", 0))
        self.addCleanup(holder.close)
        before = _sha(self.path)
        spec = {"enabled": True, "listen": _addr(holder), "destinations": [_addr(self.sink_b)]}
        response = self.client.put("/api/osc-relay", json=spec)
        self.assertEqual(response.status_code, 500)
        self.assertIn("could not bind", response.get_json()["error"])
        self.assertEqual(_sha(self.path), before)
        self.assertTrue(self.controller.relay.running)
        self.assertEqual(self.controller.relay.stats()["listen"], self.listen)
        self.send_through_relay(b"/restored")
        self.assert_receives(self.sink_a, b"/restored")
        self.assertEqual([p.name for p in self.path.parent.glob(".osc_relay-*")], [])

    def test_disabled_relay_is_404(self):
        self.server.osc_relay_controller = None
        self.assertEqual(self.client.get("/api/osc-relay").status_code, 404)
        self.assertEqual(self.client.put("/api/osc-relay", json={}).status_code, 404)


class MidiPortsRouteTests(unittest.TestCase):
    def test_lists_names_and_selected_ports_without_opening_any_port(self):
        server, _, tmpdir, *_ = _make_server()
        self.addCleanup(shutil.rmtree, tmpdir, True)
        server.midi_port, server.feedback_port, server.pulse_port = "DECK_IN 1", None, "PULSE_OUT 2"
        server.requested_ports = {"output": "DECK_IN", "feedback": "DECK_OUT", "pulse": "PULSE_OUT"}
        opened = []
        fake_mido = types.ModuleType("mido")
        fake_mido.get_input_names = lambda: ["DECK_OUT 0", "PULSE_OUT 2"]
        fake_mido.get_output_names = lambda: ["DECK_IN 1"]
        for name in ("open_input", "open_output", "open_ioport"):
            setattr(fake_mido, name, lambda *a, _n=name, **k: opened.append(_n))
        with patch.dict(sys.modules, {"mido": fake_mido}):
            response = server._app.test_client().get("/api/midi/ports")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "inputs": ["DECK_OUT 0", "PULSE_OUT 2"], "outputs": ["DECK_IN 1"], "error": None,
            "selected": {
                "output": {"requested": "DECK_IN", "resolved": "DECK_IN 1"},
                "feedback": {"requested": "DECK_OUT", "resolved": None},
                "pulse": {"requested": "PULSE_OUT", "resolved": "PULSE_OUT 2"},
            },
        })
        self.assertEqual(opened, [])


class LogTailRouteTests(unittest.TestCase):
    def setUp(self):
        self.server, _, tmpdir, *_ = _make_server()
        self.addCleanup(shutil.rmtree, tmpdir, True)
        self.logger = logging.getLogger("sdauto-a2-ring-test")
        self.logger.propagate = False
        self.logger.setLevel(logging.INFO)
        self.ring = install_ring_handler(self.logger)
        self.addCleanup(self.logger.removeHandler, self.ring)
        self.server.log_ring = self.ring
        self.client = self.server._app.test_client()

    def test_tail_returns_newest_lines_bounded_by_the_ring(self):
        for i in range(RING_CAPACITY + 5):
            self.logger.info("line %d", i)
        body = self.client.get("/api/logs/tail").get_json()
        self.assertEqual(body["count"], 200)
        self.assertTrue(body["lines"][-1].endswith("INFO sdauto-a2-ring-test line %d" % (RING_CAPACITY + 4)))
        self.assertRegex(body["lines"][0], r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3} INFO ")
        self.assertIsNone(body["log_file"])
        full = self.client.get("/api/logs/tail?lines=1000").get_json()["lines"]
        self.assertEqual(RING_CAPACITY, 1000)
        self.assertEqual(len(full), RING_CAPACITY)
        self.assertEqual(len(self.ring.tail(10_000)), RING_CAPACITY)  # memory is bounded, not just the reply
        self.assertTrue(full[0].endswith("line 5"))
        self.assertEqual(self.client.get("/api/logs/tail?lines=1").get_json()["count"], 1)

    def test_invalid_lines_is_400(self):
        for raw in ("0", "1001", "-1", "abc", "", "1.5", "\u0663", "00001"):
            with self.subTest(raw=raw):
                self.assertEqual(self.client.get("/api/logs/tail", query_string={"lines": raw}).status_code, 400)

    def test_tray_mode_reports_the_log_file(self):
        self.server.log_file_path = Path("C:/logs/bridge.log")
        self.assertEqual(self.client.get("/api/logs/tail").get_json()["log_file"], str(Path("C:/logs/bridge.log")))

    def test_ring_handler_creates_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                handler = RingLogHandler()
                logger = logging.getLogger("sdauto-a2-nofile")
                logger.propagate = False
                logger.addHandler(handler)
                logger.warning("hello")
                logger.removeHandler(handler)
            finally:
                os.chdir(cwd)
            self.assertEqual(os.listdir(tmp), [])
        self.assertEqual(handler.tail(5)[-1].split(" ", 2)[2], "WARNING sdauto-a2-nofile hello")


class LoopbackOnlyTests(unittest.TestCase):
    ROUTES = [("GET", "/api/engines/autopilot/config"), ("PUT", "/api/engines/autopilot/config"),
              ("GET", "/api/osc-relay"), ("PUT", "/api/osc-relay"),
              ("GET", "/api/midi/ports"), ("GET", "/api/logs/tail")]

    def test_non_loopback_remote_is_403_before_any_work(self):
        server, _, tmpdir, *_ = _make_server()
        self.addCleanup(shutil.rmtree, tmpdir, True)
        server.engine_registry = Mock()
        server.osc_relay_controller = Mock()
        server.log_ring = Mock()
        client = server._app.test_client()
        with patch("windows.midi.get_port_snapshot") as snapshot:
            for method, path in self.ROUTES:
                for remote in ("192.168.1.7", "10.10.10.5", "", "invalid"):
                    with self.subTest(method=method, path=path, remote=remote):
                        response = client.open(path, method=method, json={"type": "autopilot"},
                                               environ_base={"REMOTE_ADDR": remote},
                                               headers={"X-Forwarded-For": "127.0.0.1"})
                        self.assertEqual(response.status_code, 403)
        snapshot.assert_not_called()
        self.assertEqual(server.osc_relay_controller.mock_calls, [])
        self.assertEqual(server.log_ring.mock_calls, [])
        self.assertEqual(server.engine_registry.mock_calls, [])
        # The same route answers a loopback peer (IPv4 and IPv6).
        server.log_ring = RingLogHandler()
        for remote in ("127.0.0.1", "::1"):
            self.assertEqual(client.get("/api/logs/tail", environ_base={"REMOTE_ADDR": remote}).status_code, 200)


class WinRecvWiringTests(unittest.TestCase):
    def boot(self, check, *extra, tray=False):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name) / "windows_midi_map.json"
        base.write_text('{"mappings":{}}')
        self.relay_path = Path(tmp.name) / "osc_relay.json"
        servers = []
        midi = FakeMidiOut()
        midi.port_name = "resolved output"
        midi.port_index = 0
        fake_tray = Mock()
        fake_tray.acquire_single_instance_lock.return_value = (None, True)
        self.tray_log = Path(tmp.name) / "tray" / "bridge.log"
        fake_tray.setup_log_tee.return_value = self.tray_log
        fake_tray.run_tray_mode.side_effect = lambda **kw: kw["run_bridge"]()
        argv = ["--map", str(base), "--no-engines", "--no-pulse", "--feedback-port", "DECK_OUT",
                "--midi-port", "DECK_IN", *extra]
        if tray:
            argv.append("--tray")
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(win_recv, "open_midi_output", return_value=midi))
            stack.enter_context(patch.object(win_recv, "open_midi_input", return_value=None))
            stack.enter_context(patch.object(win_recv, "serve_forever",
                                             side_effect=lambda h, p, r, **kw: check(servers[0], kw)))
            stack.enter_context(patch.object(win_recv, "_open_browser_delayed"))
            stack.enter_context(patch.object(MappingUIServer, "run_in_thread", lambda s: servers.append(s)))
            stack.enter_context(patch.object(MappingUIServer, "stop"))
            stack.enter_context(patch.dict(sys.modules, {"windows.tray": fake_tray}))
            self.assertEqual(win_recv.main(argv), 0)
        return servers[0]

    def test_ui_server_and_serve_forever_share_the_task_queue_and_ring(self):
        seen = {}

        def check(server, kw):
            seen["same_queue"] = server.receiver_tasks is kw["receiver_tasks"]
            seen["queue_type"] = type(kw["receiver_tasks"])
            seen["ring_on_root"] = server.log_ring in logging.getLogger().handlers
            logging.getLogger("windows.sdauto-a2").warning("wired-into-the-ring")
            client = server._app.test_client()
            tail = client.get("/api/logs/tail?lines=1000").get_json()
            seen["tail_has_line"] = any(line.endswith("wired-into-the-ring") for line in tail["lines"])
            seen["log_file"] = tail["log_file"]
            seen["selected"] = client.get("/api/midi/ports").get_json()["selected"]
            seen["relay_get"] = client.get("/api/osc-relay").get_json()
            sink = _udp_sink()
            seen["sink"] = sink
            spec = {"enabled": True, "listen": "127.0.0.1:%d" % _free_udp_port(), "destinations": [_addr(sink)]}
            seen["put"] = client.put("/api/osc-relay", json=spec).status_code
            seen["relay"] = server.osc_relay_controller.relay

        self.boot(check)
        self.addCleanup(seen["sink"].close)
        self.assertTrue(seen["same_queue"])
        self.assertIs(seen["queue_type"], ReceiverTaskQueue)
        self.assertTrue(seen["ring_on_root"])
        self.assertTrue(seen["tail_has_line"])
        self.assertIsNone(seen["log_file"])
        self.assertEqual(seen["selected"], {
            "output": {"requested": "DECK_IN", "resolved": "resolved output"},
            "feedback": {"requested": "DECK_OUT", "resolved": None},
            "pulse": {"requested": None, "resolved": None},
        })
        self.assertEqual(seen["relay_get"]["path"], str(self.relay_path))
        self.assertFalse(seen["relay_get"]["running"])
        self.assertEqual(seen["put"], 200)
        self.assertTrue(self.relay_path.exists())
        # main's teardown stopped the relay the PUT started.
        self.assertFalse(seen["relay"].running)

    def test_tray_mode_tail_reports_the_rotating_file(self):
        seen = {}
        self.boot(lambda server, kw: seen.update(
            log_file=server._app.test_client().get("/api/logs/tail").get_json()["log_file"]), tray=True)
        self.assertEqual(seen["log_file"], str(self.tray_log))

    def test_no_osc_relay_flag_leaves_the_route_404(self):
        seen = {}
        self.boot(lambda server, kw: seen.update(
            status=server._app.test_client().get("/api/osc-relay").status_code), "--no-osc-relay")
        self.assertEqual(seen["status"], 404)


if __name__ == "__main__":
    unittest.main()
