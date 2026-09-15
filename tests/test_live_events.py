"""Live observation controls use recording backends only, never MIDI ports."""
import http.client
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from protocol.messages import encode_action_event, encode_axis_event, encode_heartbeat_event
from windows.config import (AxisToCCMapping, MacroCCMapping, NoteMapping,
                            RelativeCCMapping, StagedNoteMacroMapping)
from windows.live_events import LiveEvents, LiveMidiOut, action_context
from windows.receiver import ActionReceiver, serve_forever
from windows.ui_server import MappingUIServer


class RecordingMidi:
    port_name = "recording-only"
    port_index = 7

    def __init__(self, order=None):
        self.order = order if order is not None else []

    def note_on(self, *args, **kwargs):
        self.order.append(("note_on", args, kwargs))
        return "note-on-result"

    def note_off(self, *args, **kwargs):
        self.order.append(("note_off", args, kwargs))

    def control_change(self, *args, **kwargs):
        self.order.append(("control_change", args, kwargs))

    def panic(self):
        self.order.append(("panic", (), {}))
        for channel in range(16):
            self.control_change(channel, 123, 0)

    def close(self):
        self.order.append(("close", (), {}))


def make_receiver(publisher=None, backend=None, mappings=None):
    backend = backend or RecordingMidi()
    mappings = mappings if mappings is not None else {"BTN_A": NoteMapping("BTN_A", "note", 2, 36)}
    midi = LiveMidiOut(backend, publisher) if publisher is not None else backend
    return ActionReceiver(midi, mappings, live_events=publisher,
                          dedupe_window_seconds=0, rate_limit_max_events=100000,
                          engine_registry=Mock()), backend


def press(receiver, seq=1, state="down", action="BTN_A", now=10):
    return receiver.handle_datagram(encode_action_event(action=action, state=state, seq=seq),
                                    ("127.0.0.1", 45678), now=now)


class LiveMidiTests(unittest.TestCase):
    def test_all_methods_forward_exact_arguments_before_publish_including_panic(self):
        order = []
        publisher = Mock()
        publisher.publish.side_effect = lambda e: order.append(("publish", e))
        backend = RecordingMidi(order)
        midi = LiveMidiOut(backend, publisher)
        self.assertEqual((midi.port_name, midi.port_index), ("recording-only", 7))
        with action_context("BTN_A"):
            self.assertEqual(midi.note_on(2, note=60, velocity=90), "note-on-result")
            midi.note_off(channel=2, note=60)
            midi.control_change(3, 11, value=45)
            midi.panic()
        midi.close()
        expected = [
            ("note_on", (2,), {"note": 60, "velocity": 90}),
            ("publish", {"kind": "midi", "bytes": [0x92, 60, 90], "action": "BTN_A"}),
            ("note_off", (), {"channel": 2, "note": 60}),
            ("publish", {"kind": "midi", "bytes": [0x82, 60, 0], "action": "BTN_A"}),
            ("control_change", (3, 11), {"value": 45}),
            ("publish", {"kind": "midi", "bytes": [0xB3, 11, 45], "action": "BTN_A"}),
            ("panic", (), {}),
        ]
        for channel in range(16):
            expected.extend([("control_change", (channel, 123, 0), {}),
                             ("publish", {"kind": "midi", "bytes": [0xB0 | channel, 123, 0], "action": None})])
        expected.append(("close", (), {}))
        self.assertEqual(order, expected)

    def test_real_mido_backend_panic_and_partial_failure_publish_only_sent_bytes(self):
        from windows.midi import MidoMidiOut, MidiError
        backend = object.__new__(MidoMidiOut)
        backend._failed = False
        backend._port_name = "fake-port"
        sent = []
        class Message:
            def __init__(self, kind, **values):
                self.kind, self.values = kind, values
        backend._mido = Mock(Message=Message)
        def send(message):
            if message.values["channel"] == 3:
                raise RuntimeError("planted port failure")
            sent.append(message.values)
        backend._port = Mock()
        backend._port.send.side_effect = send
        p = LiveEvents()
        wrapper = LiveMidiOut(backend, p)
        with self.assertRaises(MidiError):
            wrapper.panic()
        self.assertEqual(sent, [{"channel": c, "control": 123, "value": 0} for c in range(3)])
        self.assertEqual([r["bytes"] for r in p.snapshot()["midi"]],
                         [[0xB0 + c, 123, 0] for c in range(3)])

    def test_raising_publisher_does_not_stop_forward_and_backend_error_is_preserved(self):
        publisher = Mock()
        publisher.publish.side_effect = RuntimeError("planted observer fault")
        receiver, backend = make_receiver(publisher)
        self.assertTrue(press(receiver))
        self.assertTrue(press(receiver, 2, "up"))
        receiver.release_all()
        self.assertEqual(backend.order[:2], [("note_on", (2, 36, 127), {}),
                                           ("note_off", (2, 36, 0), {})])
        self.assertEqual(len([x for x in backend.order if x[0] == "control_change"]), 16)
        backend = RecordingMidi()
        backend.note_on = Mock(side_effect=ValueError("backend failed"))
        publisher = Mock()
        midi = LiveMidiOut(backend, publisher)
        with self.assertRaisesRegex(ValueError, "backend failed"):
            midi.note_on(0, 1, 2)
        publisher.publish.assert_not_called()

    def test_release_and_timed_paths_keep_action_context_and_reset_it(self):
        publisher = LiveEvents()
        receiver, _ = make_receiver(publisher, mappings={
            "BTN_A": NoteMapping("BTN_A", "note", 2, 36),
            "FADE": MacroCCMapping("FADE", "macro_cc", 0, 20, "long_press", 1),
            "REL": RelativeCCMapping("REL", "relative_cc", 0, 21, 1, 100),
            "STAGE": StagedNoteMacroMapping("STAGE", "staged_note_macro", 42,
                                             macro_delay_ms=50, modifier_hold_ms=150),
            "AXIS": AxisToCCMapping("AXIS", "axis_cc", 0, 22, (-100, 100), (0, 127), 0, "linear"),
        })
        press(receiver)
        press(receiver, 2, "up")
        for seq, action in enumerate(("FADE", "REL", "STAGE"), 3):
            press(receiver, seq, action=action)
        publisher._events.clear()  # Observe delayed calls in isolation from the initiating datagram.
        receiver.advance_fades(10.5)
        receiver.advance_relative_ccs(10.11)
        receiver.advance_staged_note_macros(10.2)
        receiver.handle_datagram(encode_axis_event(action="AXIS", value=100, seq=6),
                                 ("127.0.0.1", 45678), now=10.5)
        rows = list(publisher._events)
        for raw, action in (([0xB0, 20, 64], "FADE"), ([0xB0, 21, 1], "REL"),
                            ([0x91, 42, 127], "STAGE"), ([0x80, 42, 0], "STAGE"),
                            ([0xB0, 22, 127], "AXIS")):
            self.assertTrue(any(r.get("bytes") == raw and r["action"] == action for r in rows), (raw, rows))
        receiver._midi_out.note_on(0, 99, 1)
        self.assertIsNone(publisher.snapshot()["midi"][-1]["action"])
        press(receiver, 7, action="BTN_A", now=11)
        receiver.release_all()
        self.assertEqual(publisher.snapshot()["midi"][-17]["action"], "BTN_A")
        self.assertTrue(all(r["action"] is None for r in publisher.snapshot()["midi"][-16:]))

    def test_rejected_packets_heartbeat_and_duplicate_publish_nothing(self):
        publisher = LiveEvents()
        receiver, _ = make_receiver(publisher)
        press(receiver, 10)
        snapshot = publisher.snapshot()
        self.assertFalse(press(receiver, 9, "up"))
        self.assertTrue(receiver.handle_datagram(encode_heartbeat_event(seq=11), ("127.0.0.1", 45678)))
        self.assertFalse(receiver.handle_datagram(b"invalid", ("127.0.0.1", 45678)))
        self.assertEqual(publisher.snapshot(), snapshot)
        receiver._dedupe_window_seconds = 1
        self.assertFalse(press(receiver, 12, now=10.01))
        self.assertEqual(publisher.snapshot(), snapshot)


class LiveEventsTests(unittest.TestCase):
    def test_snapshot_survives_history_overflow_and_tracks_release_axis_last_twenty(self):
        publisher = LiveEvents(capacity=3)
        receiver, _ = make_receiver(publisher)
        press(receiver)
        receiver.handle_datagram(encode_axis_event(action="AXIS", value=-12345, seq=2),
                                 ("127.0.0.1", 45678), now=10)
        for n in range(30):
            receiver._midi_out.control_change(0, 1, n)
        snapshot = publisher.snapshot()
        self.assertEqual(snapshot["pressed"], ["BTN_A"])
        self.assertEqual(snapshot["axes"], {"AXIS": -12345})
        self.assertEqual([r["bytes"][-1] for r in snapshot["midi"]], list(range(10, 30)))
        self.assertEqual((snapshot["seq"], snapshot["dropped"]), (33, 30))
        press(receiver, 3, "up")
        self.assertEqual(publisher.snapshot()["pressed"], [])
        self.assertEqual(publisher.snapshot()["midi"][-1]["bytes"], [0x82, 36, 0])
        rows = list(publisher._events)
        self.assertEqual([r["seq"] for r in rows], [33, 34, 35])
        self.assertEqual(sorted(r["timestamp"] for r in rows), [r["timestamp"] for r in rows])

    def test_drop_count_resume_and_axis_latest_at_most_thirty_hz(self):
        now = [0.0]
        p = LiveEvents(capacity=8, clock=lambda: now[0])
        sub = p.subscribe(0)
        for n in range(10):
            p.publish({"kind": "input", "action": "A", "state": "down"})
        rows = sub.read()
        self.assertEqual(rows[0]["kind"], "dropped")
        self.assertEqual(rows[0]["count"], 2)
        self.assertEqual([r["seq"] for r in rows[1:]], list(range(3, 11)))
        self.assertEqual(p.snapshot()["dropped"], 2)
        p = LiveEvents(clock=lambda: now[0])
        sub = p.subscribe(0)
        emitted = []
        for frame in range(60):
            now[0] = frame / 60
            p.publish({"kind": "axis", "action": "X", "value": frame})
            p.publish({"kind": "axis", "action": "X", "value": frame + 100})
            rows = sub.read()
            if rows:
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["value"], frame + 100)
                emitted.append(now[0])
        self.assertGreater(len(emitted), 20)
        self.assertLessEqual(len(emitted), 30)
        self.assertTrue(all(b - a >= 1 / 30 - 1e-12 for a, b in zip(emitted, emitted[1:])))
        resumed = p.subscribe(118)
        self.assertEqual([r["seq"] for r in resumed.read()], [120])
        self.assertEqual(p.subscribe().read(), [])
        p.close()
        self.assertEqual(p.snapshot()["clients"], 0)
        self.assertIsNone(p.subscribe())

    def test_publisher_contention_drops_without_wait_and_reports_sequence_gap(self):
        p = LiveEvents()
        sub = p.subscribe(0)
        p.publish({"kind": "input", "action": "A", "state": "down"})
        p._publish_lock.acquire()
        worker = threading.Thread(target=p.publish,
                                  args=({"kind": "input", "action": "A", "state": "up"},),
                                  daemon=True)
        try:
            worker.start()
            worker.join(1)
            self.assertFalse(worker.is_alive(), "publisher waited for a busy writer")
        finally:
            p._publish_lock.release()
            worker.join(1)
        p.publish({"kind": "input", "action": "A", "state": "up"})
        rows = sub.read()
        self.assertEqual([r["kind"] for r in rows], ["input", "dropped", "input"])
        self.assertEqual([r["seq"] for r in rows], [1, 2, 3])
        self.assertEqual(rows[1]["count"], 1)
        self.assertEqual(p.snapshot()["dropped"], 1)
        self.assertEqual(p.snapshot()["pressed"], [])

    def test_full_buffer_and_stalled_stream_leave_all_thousand_midi_calls_identical(self):
        p = LiveEvents(capacity=8)
        sub = p.subscribe()
        stream = sub.stream()
        next(stream)  # Deliberately never consume another frame.
        receiver, observed = make_receiver(p)
        plain, expected = make_receiver()
        errors = []
        def run():
            try:
                for seq in range(1000):
                    state = "down" if seq % 2 == 0 else "up"
                    press(receiver, seq, state, now=10 + seq * .001)
                    press(plain, seq, state, now=10 + seq * .001)
            except Exception as exc:
                errors.append(repr(exc))
        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(2)
        self.assertFalse(worker.is_alive(), "stalled consumer blocked publication")
        self.assertEqual(errors, [])
        self.assertEqual(len(observed.order), 1000)
        self.assertEqual(observed.order, expected.order)
        self.assertEqual(len(p._events), 8)
        self.assertEqual(p.snapshot()["dropped"], 1992)
        stream.close()
        self.assertEqual(p.snapshot()["clients"], 0)

    def test_client_and_unknown_action_storage_are_bounded(self):
        p = LiveEvents(capacity=8)
        subs = [p.subscribe() for _ in range(p.MAX_CLIENTS)]
        self.assertTrue(all(subs))
        self.assertIsNone(p.subscribe())
        for n in range(1000):
            p.publish({"kind": "axis", "action": str(n), "value": n})
            p.publish({"kind": "input", "action": str(n), "state": "down"})
        self.assertEqual(len(p.snapshot()["axes"]), p.MAX_ACTIONS)
        self.assertEqual(len(p.snapshot()["pressed"]), p.MAX_ACTIONS)
        self.assertEqual(len(p._events), 8)
        subs[0].close()
        self.assertIsNotNone(p.subscribe())


class LiveRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.p = LiveEvents()
        self.server = MappingUIServer(root / "map.json", root / "presets", root / "macros.json",
                                      root / "actions.yaml", threading.Event(), port=0, live_events=self.p)
        self.client = self.server._app.test_client()
        self.addCleanup(self.server.stop)
        self.addCleanup(self.p.close)

    def test_sse_framing_since_snapshot_and_close(self):
        receiver, _ = make_receiver(self.p)
        press(receiver)
        response = self.client.get("/api/live/events?since=1", buffered=False)
        self.assertEqual(response.mimetype, "text/event-stream")
        iterator = iter(response.response)
        self.assertEqual(next(iterator), b": live events\n\n")
        frame = next(iterator).decode()
        self.assertTrue(frame.startswith("id: 2\nevent: midi\ndata: "))
        self.assertTrue(frame.endswith("\n\n"))
        self.assertEqual(json.loads(frame.split("data: ")[1])["bytes"], [0x92, 36, 127])
        snapshot = self.client.get("/api/live/snapshot").get_json()
        self.assertEqual((snapshot["pressed"], snapshot["clients"], snapshot["seq"]), (["BTN_A"], 1, 2))
        response.close()
        self.assertEqual(self.p.snapshot()["clients"], 0)
        resumed = self.client.get("/api/live/events", headers={"Last-Event-ID": "1"}, buffered=False)
        it = iter(resumed.response)
        next(it)
        self.assertIn(b"id: 2\n", next(it))
        resumed.close()
        for invalid in ("-1", "abc", "1.5", "1" * 21):
            self.assertEqual(self.client.get("/api/live/events?since=" + invalid).status_code, 400)
        self.p.close()
        self.assertEqual(self.client.get("/api/live/events").status_code, 503)

    def test_real_main_wires_receive_midi_snapshot_and_quit_with_stream_open(self):
        import os
        import subprocess
        import sys
        import urllib.request
        root = Path(self.tmp.name)
        config = root / "config"
        config.mkdir()
        (config / "map.json").write_text(json.dumps({"mappings": {
            "BTN_A": {"type": "note", "channel": 2, "note": 36}}}))
        def free_port(kind):
            with socket.socket(socket.AF_INET, kind) as probe:
                probe.bind(("127.0.0.1", 0))
                return probe.getsockname()[1]
        ui, udp = free_port(socket.SOCK_STREAM), free_port(socket.SOCK_DGRAM)
        self.assertNotIn(ui, (7723, 45123))
        self.assertNotIn(udp, (7723, 45123))
        command = [sys.executable, "-B", "-m", "windows.win_recv", "--map", str(config / "map.json"),
                   "--listen", f"127.0.0.1:{udp}", "--ui-port", str(ui), "--dry-run",
                   "--no-engines", "--no-pulse", "--no-osc-relay"]
        log = (root / "process.log").open("w")
        self.addCleanup(log.close)
        proc = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1],
                                env={**os.environ, "PYSTRAY_BACKEND": "dummy", "BROWSER":
                                     "C:/Windows/System32/cmd.exe /c rem %s" if os.name == "nt" else "/usr/bin/true"},
                                stdout=log, stderr=subprocess.STDOUT)
        stream = None
        try:
            for _ in range(100):
                self.assertIsNone(proc.poll(), (root / "process.log").read_text())
                try:
                    stream = urllib.request.urlopen(f"http://127.0.0.1:{ui}/api/live/events", timeout=.5)
                    break
                except OSError:
                    time.sleep(.02)
            self.assertIsNotNone(stream)
            self.assertEqual(stream.readline(), b": live events\n")
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                for seq in range(1, 101):
                    sender.sendto(encode_action_event(action="BTN_A", state="down", seq=seq),
                                  ("127.0.0.1", udp))
                    with urllib.request.urlopen(f"http://127.0.0.1:{ui}/api/live/snapshot", timeout=1) as response:
                        snap = json.load(response)
                    if snap["pressed"] and snap["midi"]:
                        break
                    time.sleep(.02)
            self.assertEqual(snap["clients"], 1)
            self.assertEqual(snap["pressed"], ["BTN_A"])
            self.assertEqual(snap["midi"][-1]["bytes"], [0x92, 36, 127])
            self.assertEqual(snap["midi"][-1]["action"], "BTN_A")
            request = urllib.request.Request(f"http://127.0.0.1:{ui}/api/shutdown", method="POST")
            with urllib.request.urlopen(request, timeout=3) as response:
                self.assertEqual(response.status, 202)
                self.assertEqual(json.load(response), {"stopping": True})
            self.assertEqual(proc.wait(timeout=3), 0)
            if os.name == "posix":
                with self.assertRaises(ProcessLookupError):
                    os.kill(proc.pid, 0)
            else:
                # Popen.wait above proves the Windows process handle is signaled.
                self.assertEqual(proc.poll(), 0)
        finally:
            if stream is not None:
                stream.close()
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=3)

    def test_post_shutdown_with_open_stream_stops_serve_and_http_within_three_seconds(self):
        receiver, backend = make_receiver(self.p)
        self.server.shutdown_fn = receiver.request_shutdown
        http_thread = self.server.run_in_thread()
        # Use a bound socket supplied to the real serve loop to prove UDP readiness.
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.bind(("127.0.0.1", 0))
        port = udp.getsockname()[1]
        udp.close()
        started = threading.Event()
        real_socket = socket.socket
        class BoundSocket(real_socket):
            def bind(self, address):
                super().bind(address)
                started.set()
        errors = []
        def run():
            try:
                serve_forever("127.0.0.1", port, receiver, poll_interval=0.02)
            except Exception as exc:
                errors.append(repr(exc))
            finally:
                self.server.stop()
        with patch("windows.receiver.socket.socket", BoundSocket):
            worker = threading.Thread(target=run, daemon=True)
            worker.start()
            self.assertTrue(started.wait(2))
        conn = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=3)
        self.addCleanup(conn.close)
        conn.request("GET", "/api/live/events")
        stream = conn.getresponse()
        self.assertEqual(stream.status, 200)
        self.assertEqual(stream.readline(), b": live events\n")
        self.assertEqual(stream.readline(), b"\n")
        self.assertEqual(self.p.snapshot()["clients"], 1)
        # Leave the consumer stalled while Quit runs through the real HTTP route.
        quit_conn = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=3)
        self.addCleanup(quit_conn.close)
        start = time.monotonic()
        quit_conn.request("POST", "/api/shutdown")
        reply = quit_conn.getresponse()
        self.assertEqual(reply.status, 202)
        self.assertEqual(json.loads(reply.read()), {"stopping": True})
        worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertFalse(http_thread.is_alive())
        self.assertLess(time.monotonic() - start, 3)
        self.assertEqual(errors, [])
        self.assertEqual(self.p.snapshot()["clients"], 0)
        self.assertIn(("panic", (), {}), backend.order)
        remaining = stream.read()
        self.assertTrue(not remaining or remaining.endswith(b"\n\n"))
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as rebound:
            rebound.bind(("127.0.0.1", port))
