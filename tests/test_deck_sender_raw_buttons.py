"""Deck sender raw button mode (button_source="hidraw", ADR 0003)."""

from __future__ import annotations

import contextlib
import io
import json
import socket
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from deck.xinput_send import HidrawAxisReader, raw_button_state_from_report, run_sender


def report(
    buttons: bytes = bytes(8),
    *,
    lx: int = 0,
    ly: int = 0,
    rx: int = 0,
    ry: int = 0,
    lt: int = 0,
    rt: int = 0,
    lp: int = 0,
    rp: int = 0,
) -> bytes:
    data = bytearray(64)
    data[0], data[2] = 0x01, 0x09
    data[8:16] = buttons
    struct.pack_into("<hhhh", data, 16, lx, ly, rx, ry)
    struct.pack_into("<HH", data, 44, lt, rt)
    struct.pack_into("<HH", data, 56, lp, rp)
    return bytes(data)


QAM_DOWN = bytes([0, 0, 0, 0, 0, 0, 0x04, 0])  # byte 14 is index 6
A_DOWN = bytes([0x80, 0, 0, 0, 0, 0, 0, 0])


class RawStateFromReportTests(unittest.TestCase):
    def test_reads_documented_offsets(self) -> None:
        state = raw_button_state_from_report(
            report(A_DOWN, lx=-32766, ly=29016, rx=5, ry=-6, lt=32767, rt=7, lp=3612, rp=8),
            now=12.3456,
        )
        self.assertEqual(state.deck_ms, 12345)
        self.assertEqual(state.buttons, A_DOWN)
        self.assertEqual(
            (state.left_pad_x, state.left_pad_y, state.right_pad_x, state.right_pad_y),
            (-32766, 29016, 5, -6),
        )
        self.assertEqual((state.left_trigger, state.right_trigger), (32767, 7))
        self.assertEqual((state.left_pad_pressure, state.right_pad_pressure), (3612, 8))

    def test_same_inputs_ignores_time_only(self) -> None:
        a = raw_button_state_from_report(report(lp=10), now=1.0)
        self.assertTrue(a.same_inputs(raw_button_state_from_report(report(lp=10), now=2.0)))
        self.assertFalse(a.same_inputs(raw_button_state_from_report(report(lp=11), now=1.0)))
        self.assertFalse(a.same_inputs(None))


class ReaderRawModeTests(unittest.TestCase):
    def test_queues_only_button_changes_in_order(self) -> None:
        reader = HidrawAxisReader(raw_buttons=True)
        reader._parse_report(report())
        reader._parse_report(report(lp=900))
        reader._parse_report(report(A_DOWN))
        reader._parse_report(report())
        changes = reader.drain_raw_button_changes()
        self.assertEqual([c.buttons for c in changes], [bytes(8), A_DOWN, bytes(8)])
        self.assertEqual(reader.drain_raw_button_changes(), [])
        reader._parse_report(report(lp=4000))
        self.assertEqual(reader.drain_raw_button_changes(), [])
        self.assertEqual(reader.latest_raw_button_state().left_pad_pressure, 4000)

    def test_raw_mode_suppresses_sender_side_button_actions(self) -> None:
        reader = HidrawAxisReader(raw_buttons=True)
        reader._parse_report(report(QAM_DOWN))
        self.assertEqual(reader.drain_buttons(), [])

    def test_keys_mode_is_unchanged(self) -> None:
        reader = HidrawAxisReader()
        reader._parse_report(report(QAM_DOWN))
        self.assertEqual([(b.action, b.state) for b in reader.drain_buttons()], [("QAM", "down")])
        self.assertIsNone(reader.latest_raw_button_state())

    def test_change_wakes_waiter(self) -> None:
        reader = HidrawAxisReader(raw_buttons=True)
        reader._parse_report(report())
        reader.drain_raw_button_changes()
        timer = threading.Timer(0.05, lambda: reader._parse_report(report(A_DOWN)))
        timer.start()
        reader.wait_raw_button_change(2.0)
        timer.join()
        self.assertEqual(len(reader.drain_raw_button_changes()), 1)


class RunSenderRawModeTests(unittest.TestCase):
    def test_sends_button_state_without_an_x11_listener(self) -> None:
        with tempfile.TemporaryDirectory() as folder, contextlib.ExitStack() as stack:
            sink = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
            sink.bind(("127.0.0.1", 0))
            sink.settimeout(2)
            bindings = Path(folder) / "bindings.json"
            bindings.write_text(json.dumps({"bindings": {}}), encoding="utf-8")

            listener_cls = stack.enter_context(patch("deck.xinput_send.Xi2RawListener"))
            reader = HidrawAxisReader(raw_buttons=True)
            reader.enable_gyro = MagicMock()
            reader.drain = MagicMock(return_value={})
            reader_cls = stack.enter_context(patch("deck.xinput_send.HidrawAxisReader"))
            reader_cls.return_value.__enter__.return_value = reader
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))

            stop = threading.Event()
            worker = threading.Thread(
                target=run_sender,
                kwargs=dict(
                    device_id="3",
                    bindings_path=str(bindings),
                    targets=[("127.0.0.1", sink.getsockname()[1])],
                    profile_name=None,
                    profile_hash=None,
                    stop_event=stop,
                    manage_terminal=False,
                    button_source="hidraw",
                ),
            )
            worker.start()
            stack.callback(worker.join, 3)
            stack.callback(stop.set)

            reader._parse_report(report(A_DOWN, lp=3000))
            reader._parse_report(report())
            # Real hardware delivers a report every 4 ms; resends carry the
            # newest one, so keep idle reports flowing like the controller.
            feeding = threading.Event()

            def feed_idle_reports() -> None:
                while not feeding.wait(0.004):
                    reader._parse_report(report())

            feeder = threading.Thread(target=feed_idle_reports)
            feeder.start()
            stack.callback(feeder.join, 3)
            stack.callback(feeding.set)
            packets = []
            while len(packets) < 3:
                packet = json.loads(sink.recvfrom(4096)[0])
                if packet["kind"] == "buttons":
                    packets.append(packet)

            listener_cls.assert_not_called()
            reader_cls.assert_called_once_with(raw_buttons=True)
            # press then release in order, then a periodic resend of the release
            self.assertEqual(
                [p["b"] for p in packets], ["8000000000000000", "0000000000000000", "0000000000000000"]
            )
            self.assertEqual(packets[0]["lp"], 3000)
            self.assertLess(packets[1]["seq"], packets[2]["seq"])
            self.assertGreater(packets[2]["t"], packets[1]["t"])


if __name__ == "__main__":
    unittest.main()
