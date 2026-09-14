"""Real HTTP contract checks for the stdlib Deck control service."""
import contextlib
import http.client
import io
import json
import tempfile
import threading
import time
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

from deck.control_api import ControlServer, SenderController
from deck.local_config import load_runtime_settings


class DeckControlAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bindings = self.root / "bindings.json"
        self.document = {"profile_name": "learned", "bindings": {"14": "BTN_A"}}
        self.bindings.write_text(json.dumps(self.document))
        self.actions = self.root / "actions.yaml"
        self.actions.write_text("actions:\n- BTN_A\n- BTN_B\n")
        self.path = self.root / "settings.json"
        self.path.write_text(json.dumps({"bindings_path": str(self.bindings),
            "actions_path": str(self.actions), "presets": [
                {"name": "PC", "host": "pc.local"},
                {"name": "Mac", "host": "192.0.2.2", "port": 45124}],
            "active_targets": ["PC"]}))
        self.runs = []
        self.entered = threading.Event()
        def fake_sender(**kwargs):
            self.runs.append(kwargs)
            self.entered.set()
            kwargs["on_status"](seq=8, heartbeat_at=time.monotonic())
            kwargs["stop_event"].wait(3)
            return 0
        self.controller = SenderController(str(self.path), run=fake_sender)
        self.server = ControlServer(self.controller, port=0)
        self.server.start()
        self.addCleanup(self.server.close)
        self.addCleanup(self.controller.stop)

    def request(self, method, path, data=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=3)
        try:
            conn.request(method, path, body=None if data is None else json.dumps(data),
                         headers={"Content-Type": "application/json", **(headers or {})})
            response = conn.getresponse()
            self.assertEqual(response.getheader("Content-Type"), "application/json")
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def test_status_and_sender_lifecycle(self):
        code, status = self.request("GET", "/api/status")
        self.assertEqual(code, 200)
        self.assertFalse(status["running"])
        self.assertEqual(status["seq"], 0)
        self.assertIsNone(status["heartbeat_age"])
        self.assertEqual(status["profile_name"], "learned")
        self.assertIsNone(status["profile_hash"])
        self.assertEqual(status["device_id"], "5")
        self.assertEqual(status["bindings_path"], str(self.bindings))
        self.assertEqual(status["active_targets"], [{"name": "PC", "host": "pc.local", "port": 45123}])
        self.assertEqual(self.request("POST", "/api/sender/start")[0], 200)
        self.assertTrue(self.entered.wait(1))
        self.assertFalse(self.controller.stop_event.is_set())
        code, status = self.request("GET", "/api/status")
        self.assertTrue(status["running"])
        self.assertEqual(status["seq"], 8)
        self.assertLess(status["heartbeat_age"], 1)
        self.assertEqual(self.request("POST", "/api/sender/start")[0], 200)
        self.assertEqual(len(self.runs), 1)
        old_event = self.controller.stop_event
        self.assertEqual(self.request("POST", "/api/sender/restart")[0], 200)
        self.assertTrue(old_event.is_set())
        self.assertEqual(len(self.runs), 2)
        self.assertEqual(self.request("POST", "/api/sender/stop")[0], 200)
        self.assertTrue(self.controller.stop_event.is_set())
        self.assertFalse(self.request("GET", "/api/status")[1]["running"])

    def test_target_routes_persist_and_update_running_destinations(self):
        code, targets = self.request("GET", "/api/targets")
        self.assertEqual(code, 200)
        self.assertEqual(targets["active_targets"], ["PC"])
        self.assertEqual(len(targets["presets"]), 2)
        self.assertEqual(self.request("POST", "/api/targets/add", {"name": "Desk", "host": "desk", "port": 9})[0], 200)
        self.assertEqual(load_runtime_settings(str(self.path)).presets[-1].port, 9)
        self.assertEqual(self.request("POST", "/api/targets/active", {"names": ["Mac", "Desk"]})[0], 200)
        self.assertEqual(load_runtime_settings(str(self.path)).active_targets, ["Mac", "Desk"])
        self.request("POST", "/api/sender/start")
        self.assertTrue(self.entered.wait(1))
        self.assertEqual(self.runs[-1]["targets"], [("192.0.2.2", 45124), ("desk", 9)])
        self.assertEqual(self.request("POST", "/api/targets/rename", {"old": "Desk", "new": "Stage"})[0], 200)
        self.assertEqual(load_runtime_settings(str(self.path)).active_targets, ["Mac", "Stage"])
        self.assertEqual(self.request("POST", "/api/targets/delete", {"name": "Stage"})[0], 200)
        self.assertEqual(load_runtime_settings(str(self.path)).active_targets, ["Mac"])
        self.assertEqual(self.runs[-1]["targets"], [("192.0.2.2", 45124)])
        self.assertEqual(self.request("POST", "/api/targets", {"presets": [{"name": "Only", "host": "host"}]})[0], 200)
        settings = load_runtime_settings(str(self.path))
        self.assertEqual([p.name for p in settings.presets], ["Only"])
        self.assertEqual(settings.active_targets, [])
        self.assertFalse(self.request("GET", "/api/status")[1]["running"])

    def test_bindings_snapshot_and_reload(self):
        self.assertEqual(self.request("GET", "/api/bindings"), (200, self.document))
        updated = {"profile_name": "new", "bindings": {"18": "BTN_B"}}
        self.bindings.write_text(json.dumps(updated))
        self.assertEqual(self.request("GET", "/api/bindings")[1], self.document)
        self.request("POST", "/api/sender/start")
        self.assertEqual(self.request("POST", "/api/bindings/reload"), (200, updated))
        self.assertEqual(self.runs[-1]["bindings_document"], updated)
        self.bindings.write_text('{"bindings": []}')
        self.assertEqual(self.request("POST", "/api/bindings/reload")[0], 400)
        self.assertEqual(self.request("GET", "/api/bindings")[1], updated)

    def test_settings_roundtrip(self):
        code, settings = self.request("GET", "/api/settings")
        self.assertEqual(code, 200)
        self.assertEqual(settings["api_bind"], "127.0.0.1")
        self.assertEqual(settings["api_port"], 7724)
        updated = {"device_id": "7", "profile_name": "show", "profile_hash": "abc",
                   "api_bind": "0.0.0.0", "api_token": "test-secret", "default_port": 9}
        self.assertEqual(self.request("PUT", "/api/settings", updated)[0], 200)
        saved = load_runtime_settings(str(self.path))
        self.assertEqual(saved.device_id, "7")
        self.assertEqual(saved.api_bind, "0.0.0.0")
        self.assertEqual(saved.api_token, "test-secret")
        self.assertEqual(saved.profile_hash, "abc")
        self.assertNotIn("api_token", self.request("GET", "/api/settings")[1])
        self.request("POST", "/api/targets/add", {"name": "Third", "host": "third"})
        self.assertEqual(load_runtime_settings(str(self.path)).presets[-1].port, 9)
        self.assertEqual(load_runtime_settings(str(self.path)).api_token, "test-secret")

    def test_invalid_requests_are_json_4xx_and_do_not_write(self):
        before = self.path.read_bytes()
        for method, path, data in [
            ("GET", "/missing", None), ("DELETE", "/api/targets", None),
            ("POST", "/api/targets", []), ("POST", "/api/targets", {"presets": [{"name": "x", "host": "h"}]*2}),
            ("POST", "/api/targets/add", {"name": "PC", "host": "other"}),
            ("POST", "/api/targets/add", {"name": "New", "host": "bad/host"}),
            ("POST", "/api/targets/add", {"name": "New", "host": "host", "port": True}),
            ("POST", "/api/targets/active", {"names": ["Missing"]}),
            ("POST", "/api/targets/active", {"names": ["PC", "PC"]}),
            ("POST", "/api/targets/delete", {"name": "Missing"}),
            ("POST", "/api/targets/rename", {"old": "PC", "new": "Mac"}),
            ("PUT", "/api/settings", {"api_bind": "0.0.0.0"}),
            ("PUT", "/api/settings", {"device_id": []}),
            ("PUT", "/api/settings", {"unknown": 3}),
        ]:
            with self.subTest(path=path, data=data):
                code, result = self.request(method, path, data)
                self.assertTrue(400 <= code < 500, result)
                self.assertIsInstance(result["error"], str)
                self.assertEqual(self.path.read_bytes(), before)

    def test_off_loopback_requires_token_on_every_route(self):
        self.server.close()
        with self.assertRaises(ValueError):
            ControlServer(self.controller, bind="0.0.0.0", port=0)
        self.controller.update_settings({"api_token": "test-secret"})
        self.server = ControlServer(self.controller, bind="0.0.0.0", port=0)
        self.server.start()
        self.addCleanup(self.server.close)
        for method, path in self.server.routes:
            with self.subTest(method=method, path=path):
                self.assertEqual(self.request(method, path)[0], 401)
        self.assertEqual(self.request("GET", "/api/status", headers={"X-Deck-Token": "wrong"})[0], 401)
        self.assertEqual(self.request("GET", "/api/status", headers={"X-Deck-Token": "test-secret"})[0], 200)

    def test_shutdown_stops_sender_and_closes_api_after_json_reply(self):
        stopped = threading.Event()
        self.server.on_shutdown = stopped.set
        self.request("POST", "/api/sender/start")
        self.assertEqual(self.request("POST", "/api/shutdown"), (200, {"ok": True}))
        self.assertTrue(stopped.wait(1))
        self.assertTrue(self.controller.stop_event.is_set())
        self.assertFalse(self.controller.status()["running"])
        self.assertIsNone(self.server.thread)

    def test_stop_sets_event_before_join(self):
        event = threading.Event()
        self.controller.stop_event = event
        test = self
        class Thread:
            def join(self, timeout):
                test.assertTrue(event.is_set())
            def is_alive(self):
                return False
        self.controller.thread = Thread()
        self.controller.stop()
        self.assertTrue(event.is_set())

    def test_settings_write_failure_preserves_memory_file_and_worker(self):
        self.request("POST", "/api/sender/start")
        before = self.path.read_bytes()
        event = self.controller.stop_event
        with patch("deck.local_config.os.replace", side_effect=OSError("disk refused")):
            code, result = self.request("PUT", "/api/settings", {"device_id": "8"})
        self.assertEqual(code, 400)
        self.assertIn("disk refused", result["error"])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.controller.settings.device_id, "5")
        self.assertIs(self.controller.stop_event, event)
        self.assertFalse(event.is_set())

    def test_settings_replace_is_atomic_before_memory_publish(self):
        import os
        original = os.replace
        old_bytes = self.path.read_bytes()
        observed = []
        def replace_file(source, destination):
            observed.append(json.loads(Path(source).read_text()))
            self.assertEqual(Path(destination).read_bytes(), old_bytes)
            self.assertEqual(self.controller.settings.device_id, "5")
            original(source, destination)
        with patch("deck.local_config.os.replace", side_effect=replace_file):
            self.assertEqual(self.request("PUT", "/api/settings", {"device_id": "8"})[0], 200)
        self.assertEqual(observed[0]["device_id"], "8")
        self.assertEqual(load_runtime_settings(str(self.path)).device_id, "8")

    def test_active_clear_stops_legacy_single_selection_and_rename_follows_it(self):
        self.request("POST", "/api/targets/active", {"names": []})
        self.controller.start(single_target="PC")
        self.request("POST", "/api/targets/rename", {"old": "PC", "new": "Stage"})
        self.assertEqual(self.request("GET", "/api/status")[1]["active_targets"][0]["name"], "Stage")
        self.assertTrue(self.controller.status()["running"])
        self.request("POST", "/api/targets/active", {"names": []})
        self.assertFalse(self.controller.status()["running"])
        self.assertEqual(self.controller.status()["active_targets"], [])
        self.assertEqual(self.request("POST", "/api/sender/start")[0], 400)

    def test_token_rotation_is_live_and_listener_settings_wait_for_relaunch(self):
        self.controller.update_settings({"api_token": "old-token"})
        self.server.close()
        self.server = ControlServer(self.controller, bind="0.0.0.0", port=0)
        self.server.start()
        self.addCleanup(self.server.close)
        self.assertEqual(self.request("PUT", "/api/settings", {"api_token": "new-token"}, {"X-Deck-Token": "old-token"})[0], 200)
        self.assertEqual(self.request("GET", "/api/status", headers={"X-Deck-Token": "old-token"})[0], 401)
        self.assertEqual(self.request("GET", "/api/status", headers={"X-Deck-Token": "new-token"})[0], 200)
        self.assertEqual(self.request("PUT", "/api/settings", {"api_token": None}, {"X-Deck-Token": "new-token"})[0], 400)

    def test_settings_change_restarts_with_new_identity_and_bindings(self):
        self.request("POST", "/api/sender/start")
        self.assertTrue(self.entered.wait(1))
        event = self.controller.stop_event
        self.request("PUT", "/api/settings", {"device_id": "9", "profile_name": "new", "profile_hash": "hash"})
        self.assertTrue(event.is_set())
        self.assertEqual(self.runs[-1]["device_id"], "9")
        self.assertEqual(self.runs[-1]["profile_name"], "new")
        self.assertEqual(self.runs[-1]["profile_hash"], "hash")
        event = self.controller.stop_event
        self.request("PUT", "/api/settings", {"api_port": 9999})
        self.assertIs(self.controller.stop_event, event)
        self.assertEqual(self.server.server_address[1], self.server.socket.getsockname()[1])

    def test_worker_failure_status_and_retry(self):
        def fail(**kwargs):
            raise OSError("no capture device")
        self.controller.run = fail
        self.request("POST", "/api/sender/start")
        self.controller.thread.join(timeout=1)
        status = self.request("GET", "/api/status")[1]
        self.assertFalse(status["running"])
        self.assertEqual(status["last_error"], "no capture device")
        self.assertEqual(status["exit_code"], 2)
        self.assertTrue(self.controller.stop_event.is_set())

    def test_malformed_json_and_unsupported_method_are_json(self):
        for method, body in [("POST", "{"), ("POST", "null"), ("PATCH", "{}"), ("BOGUS", "{}")]:
            with self.subTest(method=method, body=body):
                conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=3)
                try:
                    conn.request(method, "/api/settings", body, {"Content-Type": "application/json"})
                    response = conn.getresponse()
                    self.assertGreaterEqual(response.status, 400)
                    self.assertIn("error", json.loads(response.read()))
                finally:
                    conn.close()

    def test_deckctl_uses_real_http_routes(self):
        from deck.deckctl import main
        url = f"http://127.0.0.1:{self.server.server_address[1]}"
        for args in [["status"], ["targets"], ["activate", "Mac,PC"], ["start"], ["restart"], ["stop"]]:
            with self.subTest(args=args), contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(main(["--url", url, *args]), 0)
                self.assertIsInstance(json.loads(out.getvalue()), dict)
        self.assertEqual(load_runtime_settings(str(self.path)).active_targets, ["Mac", "PC"])
        self.assertEqual(self.runs[-1]["targets"], [("192.0.2.2", 45124), ("pc.local", 45123)])
        self.assertTrue(self.controller.stop_event.is_set())
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(["--url", url, "activate", "missing"]), 1)
            self.assertIn("error", json.loads(out.getvalue()))

    def test_menu_and_api_share_live_state_and_reject_stale_edits(self):
        from deck.launch_send import prompt_for_preset, prompt_new_preset
        old = self.controller.snapshot()
        def choices():
            self.request("PUT", "/api/settings", {"device_id": "11"})
            self.request("POST", "/api/targets/add", {"name": "Third", "host": "third"})
            yield "1"  # Old rendered index must refresh instead of starting.
            yield "3"
        with patch("builtins.input", side_effect=choices()), contextlib.redirect_stdout(io.StringIO()):
            preset, settings = prompt_for_preset(str(self.path), old, "5", self.controller)
        self.assertEqual(preset.name, "Third")
        self.assertEqual(settings.device_id, "11")
        with patch("builtins.input", side_effect=["new-host", "Fourth"]), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "settings changed"):
                prompt_new_preset(str(self.path), old, self.controller)
        self.assertEqual(len(load_runtime_settings(str(self.path)).presets), 3)

    def test_menu_server_is_available_before_first_prompt_and_uses_same_event(self):
        from deck import launch_send
        servers = []
        def make_server(*args, **kwargs):
            server = ControlServer(*args, **kwargs)
            servers.append(server)
            return server
        def choices():
            original = self.server
            self.server = servers[0]
            try:
                self.assertEqual(self.request("POST", "/api/sender/start")[0], 200)
                self.assertTrue(self.entered.wait(1))
                event = servers[0].controller.stop_event
                yield "t"
                self.assertTrue(event.is_set())
                self.assertFalse(self.request("GET", "/api/status")[1]["running"])
                yield "q"
            finally:
                self.server = original
        with patch("deck.launch_send.ControlServer", side_effect=make_server), \
                patch("deck.launch_send.run_sender", side_effect=self.controller.run), \
                patch("builtins.input", side_effect=choices()), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(launch_send.main(["--settings", str(self.path), "--api-port", "0"]), 0)
        self.assertIsNone(servers[0].thread)

    def test_every_deck_route_is_documented(self):
        import re
        doc = (Path(__file__).resolve().parents[1] / "docs/api.md").read_text().split("## Deck sender\n", 1)[1].split("\n## ", 1)[0]
        documented = set(re.findall(r"\| (GET|POST|PUT|DELETE) \| `([^`]+)` \|", doc))
        self.assertEqual(documented, self.server.routes)

    def learn_listener(self):
        import socket
        import queue
        from deck.xinput_send import Xi2KeyEvent
        class Listener:
            def __init__(inner):
                # Windows select() accepts sockets, not POSIX pipe handles.
                inner.reader, inner.writer = socket.socketpair()
                inner.reader.setblocking(False)
                inner.queue = queue.Queue()
                inner.closed = threading.Event()
            def fileno(inner):
                return inner.reader.fileno()
            def read_event(inner):
                try:
                    inner.reader.recv(1)
                    return inner.queue.get_nowait()
                except BlockingIOError:
                    return None
            def emit(inner, token):
                inner.queue.put(Xi2KeyEvent(token, "down"))
                inner.writer.sendall(b"x")
            def close(inner):
                inner.reader.close()
                inner.writer.close()
                inner.closed.set()
        listener = Listener()
        self.addCleanup(lambda: self.controller.learn.cancel() if self.controller.learn else None)
        self.addCleanup(patch.stopall)
        patch("deck.control_learn.Xi2RawListener", return_value=listener).start()
        return listener

    def wait_candidate(self, token):
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            status = self.request("GET", "/api/learn")[1]
            if status.get("candidate") == token:
                return status
            time.sleep(0.005)
        self.fail(f"candidate {token} not captured: {status}")

    def test_learn_full_capture_confirm_duplicate_skip_and_save(self):
        listener = self.learn_listener()
        self.assertEqual(self.request("GET", "/api/actions"), (200, {"actions": ["BTN_A", "BTN_B"]}))
        self.assertEqual(self.request("GET", "/api/learn"), (200, {"active": False}))
        before = self.bindings.read_bytes()
        self.assertEqual(self.request("POST", "/api/learn/start")[0], 200)
        self.assertEqual(self.request("POST", "/api/learn/confirm")[0], 400)
        self.assertEqual(self.request("POST", "/api/sender/start")[0], 400)
        self.assertEqual(self.request("PUT", "/api/settings", {"device_id": "8"})[0], 400)
        listener.emit("18")
        self.assertEqual(self.wait_candidate("18")["action"], "BTN_A")
        self.assertEqual(self.request("POST", "/api/learn/confirm")[1]["action"], "BTN_B")
        self.assertEqual(self.bindings.read_bytes(), before)
        listener.emit("18")
        self.wait_candidate("18")
        self.assertEqual(self.request("POST", "/api/learn/confirm")[0], 400)
        self.assertEqual(self.request("POST", "/api/learn/skip")[1]["saved"], True)
        self.assertTrue(listener.closed.wait(1))
        document = {"profile_name": "default", "bindings": {"18": "BTN_A"}}
        self.assertEqual(json.loads(self.bindings.read_text()), document)
        self.assertEqual(self.request("GET", "/api/bindings")[1], document)

    def test_learn_single_action_preserves_siblings_and_cancel_does_not_write(self):
        listener = self.learn_listener()
        self.assertEqual(self.request("POST", "/api/learn/start", {"action": "BTN_B"})[0], 200)
        listener.emit("19")
        self.wait_candidate("19")
        self.assertEqual(self.request("POST", "/api/learn/confirm")[1]["saved"], True)
        self.assertEqual(json.loads(self.bindings.read_text())["bindings"], {"14": "BTN_A", "19": "BTN_B"})
        self.assertTrue(listener.closed.wait(1))
        before = self.bindings.read_bytes()
        listener = self.learn_listener()
        self.request("POST", "/api/learn/start")
        self.assertEqual(self.request("POST", "/api/learn/cancel")[1]["active"], False)
        self.assertTrue(listener.closed.wait(1))
        self.assertEqual(self.bindings.read_bytes(), before)

    def test_learn_single_skip_cancels_and_invalid_action_is_rejected(self):
        listener = self.learn_listener()
        self.assertEqual(self.request("POST", "/api/learn/start", {"action": "unknown"})[0], 400)
        before = self.bindings.read_bytes()
        self.request("POST", "/api/learn/start", {"action": "BTN_A"})
        self.assertEqual(self.request("POST", "/api/learn/skip")[1]["saved"], False)
        self.assertTrue(listener.closed.wait(1))
        self.assertEqual(self.bindings.read_bytes(), before)


class SenderStopTests(unittest.TestCase):
    def test_actual_select_stop_sends_no_late_packet_and_closes_resources(self):
        from deck import xinput_send
        event = threading.Event()
        with contextlib.ExitStack() as stack:
            listener = stack.enter_context(patch("deck.xinput_send.Xi2RawListener")).return_value
            selector = stack.enter_context(patch("deck.xinput_send.selectors.DefaultSelector")).return_value
            sock = stack.enter_context(patch("deck.xinput_send.socket.socket")).return_value.__enter__.return_value
            terminal = stack.enter_context(patch("deck.xinput_send.TerminalNoEcho"))
            axes = stack.enter_context(patch("deck.xinput_send.HidrawAxisReader"))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            def select(timeout):
                self.assertLessEqual(timeout, 1 / 60)
                event.set()
                return []
            selector.select.side_effect = select
            stack.enter_context(patch("deck.xinput_send.time.monotonic", side_effect=[0.0, 0.0, 1.0]))
            self.assertEqual(xinput_send.run_sender(device_id="5", bindings_path="unused", targets=[("pc", 1)],
                profile_name=None, profile_hash=None, stop_event=event, manage_terminal=False,
                bindings_document={"bindings": {"14": "BTN_A"}}), 0)
            sock.sendto.assert_not_called()
            selector.close.assert_called_once()
            listener.close.assert_called_once()
            axes.return_value.__exit__.assert_called_once()
            terminal.assert_not_called()

    def test_listener_closes_if_hid_open_fails(self):
        from deck import xinput_send
        with patch("deck.xinput_send.Xi2RawListener") as listener, \
             patch("deck.xinput_send.socket.socket"), patch("deck.xinput_send.HidrawAxisReader") as axes, \
             contextlib.redirect_stdout(io.StringIO()):
            axes.return_value.__enter__.side_effect = OSError("no HID")
            with self.assertRaisesRegex(OSError, "no HID"):
                xinput_send.run_sender(device_id="5", bindings_path="unused", targets=[("pc", 1)],
                    profile_name=None, profile_hash=None, manage_terminal=False, bindings_document={"bindings": {}})
            listener.return_value.close.assert_called_once()

    def test_http_controls_real_sender_udp_bytes_and_telemetry(self):
        import socket
        from deck import xinput_send
        with tempfile.TemporaryDirectory() as folder, contextlib.ExitStack() as stack:
            root = Path(folder)
            sink = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
            sink.bind(("127.0.0.1", 0))
            sink.settimeout(2)
            bindings = root / "bindings.json"
            bindings.write_text(json.dumps({"profile_name": "actual", "bindings": {"14": "BTN_A"}}))
            settings = root / "settings.json"
            settings.write_text(json.dumps({"bindings_path": str(bindings), "profile_hash": "abc",
                "presets": [{"name": "sink", "host": "127.0.0.1", "port": sink.getsockname()[1]}], "active_targets": ["sink"]}))
            listener = stack.enter_context(patch("deck.xinput_send.Xi2RawListener")).return_value
            listener.read_event.side_effect = [xinput_send.Xi2KeyEvent("14", "down"), None]
            axes = stack.enter_context(patch("deck.xinput_send.HidrawAxisReader")).return_value.__enter__.return_value
            axes.drain.side_effect = iter([{"YAW": 64}] + [{}] * 1000)
            selector = stack.enter_context(patch("deck.xinput_send.selectors.DefaultSelector")).return_value
            first = True
            def select(timeout):
                nonlocal first
                if first:
                    first = False
                    return [object()]
                time.sleep(timeout)
                return []
            selector.select.side_effect = select
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            controller = SenderController(str(settings))
            server = ControlServer(controller, port=0)
            server.start()
            stack.callback(server.close)
            stack.callback(controller.stop)
            def request(path):
                conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=3)
                try:
                    conn.request("GET" if path == "/api/status" else "POST", path)
                    response = conn.getresponse()
                    self.assertEqual(response.status, 200)
                    return json.loads(response.read())
                finally:
                    conn.close()
            request("/api/sender/start")
            packets = [json.loads(sink.recvfrom(4096)[0]) for _ in range(3)]
            self.assertEqual([p["kind"] for p in packets], ["action", "axis", "heartbeat"])
            self.assertEqual([p["seq"] for p in packets], [1, 2, 3])
            self.assertEqual(packets[0]["action"], "BTN_A")
            self.assertEqual(packets[1]["action"], "YAW")
            self.assertEqual(packets[2]["profile_name"], "actual")
            self.assertEqual(packets[2]["profile_hash"], "abc")
            status = request("/api/status")
            self.assertEqual(status["seq"], 3)
            self.assertLess(status["heartbeat_age"], 0.5)
            self.assertFalse(request("/api/sender/stop")["running"])
            self.assertTrue(controller.stop_event.is_set())
            selector.close.assert_called_once()
            listener.close.assert_called_once()


class DeckSettingsCompatibilityTests(unittest.TestCase):
    def test_all_existing_helpers_preserve_api_settings(self):
        from deck.local_config import (runtime_settings_from_dict, with_device_id, with_added_preset,
            with_renamed_preset, with_deleted_preset, with_active_targets, write_runtime_settings)
        settings = runtime_settings_from_dict({"api_bind": "0.0.0.0", "api_port": 8890, "api_token": "example-token",
            "presets": [{"name": "one", "host": "host"}]})
        for updated in [with_device_id(settings, "9"), with_added_preset(settings, name="two", host="host2"),
                with_renamed_preset(settings, 0, "renamed"), with_deleted_preset(settings, 0),
                with_active_targets(settings, ["one"])]:
            with self.subTest(updated=updated), tempfile.TemporaryDirectory() as folder:
                path = str(Path(folder) / "settings.json")
                write_runtime_settings(path, updated)
                saved = load_runtime_settings(path)
                self.assertEqual((saved.api_bind, saved.api_port, saved.api_token), ("0.0.0.0", 8890, "example-token"))
