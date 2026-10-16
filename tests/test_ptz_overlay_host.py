"""Tests for the bridge side of the PTZ camera overlay."""

from __future__ import annotations

import socket
import struct
import time
import unittest

from windows.osc_relay import OscRelay, OscRelayConfig
from windows.ptz_overlay_host import PtzOverlayHost, live_camera_from, osc_messages


def _osc_str(text: str) -> bytes:
    raw = text.encode() + b"\x00"
    return raw + b"\x00" * ((-len(raw)) % 4)


def _osc_int(addr: str, value: int) -> bytes:
    return _osc_str(addr) + _osc_str(",i") + struct.pack(">i", value)


def _bundle(*msgs: bytes) -> bytes:
    out = _osc_str("#bundle") + b"\x00" * 8
    for m in msgs:
        out += struct.pack(">i", len(m)) + m
    return out


class FakeEngine:
    type_name = "ptz_visca"

    def __init__(self, active=True):
        self.active = active

    def status(self):
        return {"selected": {"left": 1, "right": 3}, "zoom_direction": {"left": "in", "right": "out"}}


class FakeRegistry:
    def __init__(self, engines):
        self.engines = engines


class ParseTests(unittest.TestCase):
    def test_bundle_of_a_real_cut(self) -> None:
        # The exact sequence Resolume sent on a cut to cam 2 (rig, 2026-10-16).
        pkt = _bundle(
            _osc_int("/composition/layers/4/clips/2/connect", 1),
            _osc_int("/composition/layers/4/clips/1/connected", 1),
            _osc_int("/composition/layers/4/clips/2/connected", 3),
        )
        msgs = list(osc_messages(pkt))
        self.assertEqual(len(msgs), 3)
        self.assertEqual([live_camera_from(a, v) for a, v in msgs], [2, None, 2])

    def test_ignores_other_layers_releases_and_non_cameras(self) -> None:
        self.assertIsNone(live_camera_from("/composition/layers/5/clips/1/connected", [3]))
        self.assertIsNone(live_camera_from("/composition/layers/4/clips/2/connect", [0]))
        self.assertIsNone(live_camera_from("/composition/layers/4/clips/7/connected", [3]))
        self.assertIsNone(live_camera_from("/composition/layers/4/clips/1/name", ["x"]))
        self.assertEqual(live_camera_from("/composition/layers/4/clips/3/connected", [4]), 3)


class HostStateTests(unittest.TestCase):
    def test_visible_needs_enabled_and_active_engine(self) -> None:
        engine = FakeEngine(active=True)
        host = PtzOverlayHost(FakeRegistry([engine]))
        self.assertTrue(host.state()["visible"])
        host.set_enabled(False)
        self.assertFalse(host.state()["visible"])
        host.set_enabled(True)
        engine.active = False
        self.assertFalse(host.state()["visible"])

    def test_sticks_and_live_camera(self) -> None:
        host = PtzOverlayHost(FakeRegistry([FakeEngine()]))
        host.observe_osc(_osc_int("/composition/layers/4/clips/3/connected", 3))
        st = host.state()
        self.assertEqual(st["live_camera"], 3)
        self.assertEqual(st["sticks"]["left"], {"camera": 1, "zoom": "in"})
        self.assertEqual(st["sticks"]["right"], {"camera": 3, "zoom": "out"})

    def test_no_ptz_engine(self) -> None:
        st = PtzOverlayHost(FakeRegistry([])).state()
        self.assertFalse(st["visible"])
        self.assertEqual(st["sticks"], {})


def _free_udp_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class RelayObserverTests(unittest.TestCase):
    def test_observer_sees_packets_and_its_errors_do_not_stop_forwarding(self) -> None:
        dest = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        dest.bind(("127.0.0.1", 0))
        dest.settimeout(2)
        listen_port = _free_udp_port()
        seen = []

        def observer(data):
            seen.append(data)
            raise RuntimeError("boom")

        relay = OscRelay(
            OscRelayConfig(enabled=True, listen_host="127.0.0.1", listen_port=listen_port,
                           destinations=(dest.getsockname(),)),
            observer=observer,
        )
        self.assertTrue(relay.start())
        try:
            sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            for i in range(2):
                sender.sendto(b"pkt%d" % i, ("127.0.0.1", listen_port))
                self.assertEqual(dest.recvfrom(100)[0], b"pkt%d" % i)
            deadline = time.time() + 2
            while len(seen) < 2 and time.time() < deadline:
                time.sleep(0.01)
            self.assertEqual(seen, [b"pkt0", b"pkt1"])
            sender.close()
        finally:
            relay.shutdown()
            dest.close()


if __name__ == "__main__":
    unittest.main()
