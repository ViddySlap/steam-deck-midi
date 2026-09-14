"""Shutdown owns the real serve loop and waits for MIDI and HTTP teardown."""

import contextlib
import http.client
import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from windows.config import ControlChangeMapping, NoteMapping
from windows.midi import DryRunMidiOut
from windows.receiver import ActionReceiver, serve_forever
from windows.ui_server import MappingUIServer


class BridgeShutdownTests(unittest.TestCase):
    def test_real_receiver_shutdown_releases_notes_cc_and_udp_within_three_seconds(self):
        midi = DryRunMidiOut()
        midi.note_on = Mock()
        midi.note_off = Mock()
        midi.control_change = Mock()
        midi.panic = Mock()
        receiver = ActionReceiver(midi, {
            "BTN_A": NoteMapping(action="BTN_A", kind="note", channel=0, note=36),
            "BTN_B": ControlChangeMapping(action="BTN_B", kind="cc", channel=0,
                                          cc=22, on_value=127, off_value=0),
        }, timeout_seconds=10)
        ready = threading.Event()
        received = threading.Event()
        real_handle = receiver.handle_datagram

        def handle(payload, addr):
            real_handle(payload, addr)
            if len(receiver._active_actions) == 2:
                received.set()

        receiver.handle_datagram = handle
        real_socket = socket.socket

        class BoundSocket(real_socket):
            def bind(self, address):
                super().bind(address)
                ready.set()

        udp = BoundSocket(socket.AF_INET, socket.SOCK_DGRAM)
        errors = []

        def run():
            try:
                serve_forever("127.0.0.1", 0, receiver, poll_interval=0.02)
            except Exception as exc:
                errors.append(exc)

        worker = threading.Thread(target=run, daemon=True)
        with patch("windows.receiver.socket.socket", return_value=udp):
            worker.start()
            try:
                self.assertTrue(ready.wait(3), "receiver never bound UDP")
                port = udp.getsockname()[1]
                with real_socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                    for seq, action in enumerate(("BTN_A", "BTN_B"), 1):
                        sender.sendto(json.dumps({"action": action, "state": "down", "seq": seq}).encode(),
                                      ("127.0.0.1", port))
                self.assertTrue(received.wait(3), "receiver did not hold both controls")
                start = time.monotonic()
                receiver.request_shutdown()
                receiver.request_shutdown()
                worker.join(3)
                self.assertFalse(worker.is_alive(), "shutdown did not stop serve_forever")
                self.assertLess(time.monotonic() - start, 3)
                self.assertEqual(errors, [])
                self.assertEqual(udp.fileno(), -1)
                with real_socket(socket.AF_INET, socket.SOCK_DGRAM) as rebound:
                    rebound.bind(("127.0.0.1", port))
                midi.note_on.assert_called_once_with(0, 36, 127)
                midi.note_off.assert_called_once_with(0, 36, 0)
                self.assertEqual([c.args for c in midi.control_change.call_args_list],
                                 [(0, 22, 127), (0, 22, 0)])
                midi.panic.assert_called_once_with()
                self.assertEqual(receiver._active_actions, {})
            finally:
                receiver.stop_event.set()
                udp.close()
                worker.join(1)

    def test_shutdown_releases_before_engines_stop_and_closes_inputs(self):
        order = []
        receiver = Mock(stop_event=threading.Event())
        receiver.release_all.side_effect = lambda: order.append("release_all")
        engines = Mock(engines=[])
        engines.shutdown.side_effect = lambda: order.append("engines_stop")
        midi_in, pulse_in, udp = Mock(), Mock(), Mock()
        udp.close.side_effect = lambda: order.append("udp_close")
        midi_in.close.side_effect = lambda: order.append("midi_in_close")
        pulse_in.close.side_effect = lambda: order.append("pulse_in_close")
        ActionReceiver.request_shutdown(receiver)
        with patch("windows.receiver.socket.socket", return_value=udp):
            serve_forever("127.0.0.1", 0, receiver, engine_registry=engines,
                          midi_in=midi_in, pulse_in=pulse_in)
        self.assertEqual(order, ["release_all", "engines_stop", "udp_close",
                                 "midi_in_close", "pulse_in_close"])
        udp.recvfrom.assert_not_called()

    def test_http_stop_waits_for_shutdown_reply_and_releases_port(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            requested, finish_reply, closing, stopped = (threading.Event() for _ in range(4))
            server = MappingUIServer(root / "map.json", root / "presets", root / "macros.json",
                                     root / "actions.yaml", threading.Event(), port=0,
                                     shutdown_fn=requested.set)

            @server._app.after_request
            def hold_reply(response):
                if response.status_code == 202:
                    finish_reply.wait(3)
                return response

            http_thread = server.run_in_thread()
            port = server.port
            result, errors = [], []

            def call():
                try:
                    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
                    with contextlib.closing(conn):
                        conn.request("POST", "/api/shutdown")
                        response = conn.getresponse()
                        result.append((response.status, json.loads(response.read())))
                except Exception as exc:
                    errors.append(exc)

            def close():
                closing.set()
                server.stop()
                stopped.set()

            caller = threading.Thread(target=call, daemon=True)
            closer = threading.Thread(target=close, daemon=True)
            caller.start()
            try:
                self.assertTrue(requested.wait(3))
                closer.start()
                self.assertTrue(closing.wait(3))
                self.assertFalse(stopped.wait(0.15), "HTTP closed before the response finished")
            finally:
                finish_reply.set()
                caller.join(3)
                if closer.ident is not None:
                    closer.join(3)
                else:
                    server.stop()
            self.assertEqual(errors, [])
            self.assertEqual(result, [(202, {"stopping": True})])
            self.assertTrue(stopped.is_set())
            self.assertFalse(http_thread.is_alive())
            with socket.socket() as rebound:
                rebound.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                rebound.bind(("127.0.0.1", port))
                rebound.listen()
            server.stop()  # Owner teardown is safe to repeat.

    def test_main_wires_both_tray_modes_to_the_http_shutdown_function(self):
        from windows import win_recv
        for tray_mode in (False, True):
            with self.subTest(tray_mode=tray_mode), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp) / "map.json"
                base.write_text('{"mappings":{}}')
                servers = []
                tray_callback = []
                midi = DryRunMidiOut()
                midi.close = Mock()
                fake_tray = Mock()
                fake_tray.acquire_single_instance_lock.return_value = (None, True)
                fake_tray.ReceiverTray.side_effect = lambda **kw: (tray_callback.append(kw["quit_callback"]) or Mock())

                def run_tray(**kw):
                    tray_callback.append(kw["stop_bridge"])
                    kw["run_bridge"]()

                fake_tray.run_tray_mode.side_effect = run_tray

                def loop(host, port, receiver, **kw):
                    self.assertEqual(tray_callback, [receiver.request_shutdown])
                    self.assertEqual(servers[0].shutdown_fn, receiver.request_shutdown)
                    response = servers[0]._app.test_client().post("/api/shutdown")
                    self.assertEqual(response.status_code, 202)
                    self.assertTrue(receiver.stop_event.is_set())
                    tray_callback[0]()
                    self.assertTrue(receiver.stop_event.is_set())

                with patch.dict("sys.modules", {"windows.tray": fake_tray}), \
                     patch.object(win_recv, "open_midi_output", return_value=midi), \
                     patch.object(win_recv, "open_midi_input", return_value=None), \
                     patch.object(win_recv, "serve_forever", side_effect=loop), \
                     patch.object(win_recv, "_open_browser_delayed"), \
                     patch.object(MappingUIServer, "run_in_thread", lambda s: servers.append(s)), \
                     patch.object(MappingUIServer, "stop") as stop_http:
                    argv = ["--map", str(base), "--no-engines", "--no-pulse", "--no-osc-relay"]
                    self.assertEqual(win_recv.main(argv + (["--tray"] if tray_mode else [])), 0)
                midi.close.assert_called_once_with()
                stop_http.assert_called_once_with()

    def test_tray_quit_waits_for_bridge_cleanup_without_forced_exit(self):
        from windows.tray import TrayApp, ReceiverTray, build_tray_menu
        from windows import tray
        requested, release, done = (threading.Event() for _ in range(3))
        callback = Mock(side_effect=requested.set)
        icon = Mock()
        ReceiverTray("http://localhost", callback)._quit(icon, None)
        quit_item = next(item for item in build_tray_menu("http://localhost", callback)
                         if item.text == "Quit")
        quit_item(icon)
        self.assertEqual(callback.call_count, 2)
        self.assertEqual(icon.stop.call_count, 2)

        def bridge():
            requested.wait(3)
            release.wait(3)
            done.set()

        requested.clear()
        callback.reset_mock()
        app = TrayApp("http://localhost", bridge, callback, grace_seconds=0.01)
        icon.run.side_effect = lambda **kw: app._on_quit()
        errors = []

        def run():
            try:
                app.run()
            except Exception as exc:
                errors.append(exc)

        with patch.object(tray.pystray, "Icon", return_value=icon), \
             patch.object(tray, "_load_icon_image"), \
             patch.object(tray.os, "_exit") as force_exit:
            owner = threading.Thread(target=run, daemon=True)
            owner.start()
            try:
                self.assertTrue(requested.wait(3))
                owner.join(0.1)
                self.assertTrue(owner.is_alive(), "tray returned before MIDI cleanup")
                self.assertFalse(done.is_set())
            finally:
                release.set()
                owner.join(3)
            self.assertFalse(owner.is_alive())
            self.assertTrue(done.is_set())
            self.assertEqual(errors, [])
            callback.assert_called_once_with()
            force_exit.assert_not_called()


    def test_tray_stops_when_http_shutdown_finishes_the_bridge(self):
        from windows import tray
        receiver = ActionReceiver(DryRunMidiOut(), {})
        ready, stopped = threading.Event(), threading.Event()
        icon = Mock()
        icon.stop.side_effect = stopped.set

        def icon_run(setup):
            setup(icon)
            ready.set()
            stopped.wait(3)

        icon.run.side_effect = icon_run
        app = tray.TrayApp("http://localhost", lambda: receiver.stop_event.wait(3),
                           receiver.request_shutdown)
        with patch.object(tray.pystray, "Icon", return_value=icon), \
             patch.object(tray, "_load_icon_image"):
            owner = threading.Thread(target=app.run, daemon=True)
            owner.start()
            try:
                self.assertTrue(ready.wait(3))
                receiver.request_shutdown()
                self.assertTrue(stopped.wait(3))
                owner.join(3)
                self.assertFalse(owner.is_alive())
                self.assertFalse(app._bridge_thread.is_alive())
            finally:
                receiver.request_shutdown()
                stopped.set()
                owner.join(3)

    def test_tray_ready_after_early_bridge_exit_stops_immediately(self):
        from windows.tray import TrayApp
        app = TrayApp("http://localhost", lambda: None, lambda: None)
        app._bridge_thread = Mock()
        app._bridge_thread.is_alive.return_value = False
        icon = Mock()
        app._on_icon_ready(icon)
        icon.stop.assert_called_once_with()
        icon.notify.assert_not_called()
