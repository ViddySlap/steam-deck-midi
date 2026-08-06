"""Tests for the OSC fan-out relay (Resolume -> N control surfaces)."""

from __future__ import annotations

import json
import socket
import tempfile
import time
import unittest
from pathlib import Path

from windows.osc_relay import (
    OscRelay,
    OscRelayConfig,
    OscRelayError,
    load_osc_relay_config,
    parse_osc_relay_config,
)


def _free_udp_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class ConfigParsingTests(unittest.TestCase):
    def test_parses_listen_and_destinations(self) -> None:
        cfg = parse_osc_relay_config(
            {
                "enabled": True,
                "listen": "127.0.0.1:7010",
                "destinations": ["10.10.10.5:7002", "10.10.10.30:7002"],
            }
        )
        self.assertTrue(cfg.active)
        self.assertEqual(cfg.listen_host, "127.0.0.1")
        self.assertEqual(cfg.listen_port, 7010)
        self.assertEqual(
            cfg.destinations, (("10.10.10.5", 7002), ("10.10.10.30", 7002))
        )

    def test_defaults_are_inactive(self) -> None:
        """No destinations means the bridge behaves as if the relay didn't exist."""
        self.assertFalse(OscRelayConfig().active)
        self.assertFalse(parse_osc_relay_config({"destinations": []}).active)

    def test_enabled_false_wins_over_destinations(self) -> None:
        cfg = parse_osc_relay_config(
            {"enabled": False, "destinations": ["10.10.10.5:7002"]}
        )
        self.assertFalse(cfg.active)

    def test_rejects_self_referential_destination(self) -> None:
        """A destination equal to the listen socket would loop forever."""
        with self.assertRaises(OscRelayError):
            parse_osc_relay_config(
                {"listen": "127.0.0.1:7010", "destinations": ["127.0.0.1:7010"]}
            )

    def test_rejects_malformed_endpoints(self) -> None:
        for bad in ("no-port", "host:notaport", ":7002", "host:0", "host:99999"):
            with self.subTest(bad=bad):
                with self.assertRaises(OscRelayError):
                    parse_osc_relay_config({"destinations": [bad]})

    def test_drops_duplicate_destinations(self) -> None:
        cfg = parse_osc_relay_config(
            {"destinations": ["10.10.10.5:7002", "10.10.10.5:7002"]}
        )
        self.assertEqual(cfg.destinations, (("10.10.10.5", 7002),))

    def test_missing_file_disables_relay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_osc_relay_config(Path(tmp) / "nope.json")
            self.assertFalse(cfg.active)

    def test_loads_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "osc_relay.json"
            path.write_text(
                json.dumps(
                    {"listen": "127.0.0.1:7011", "destinations": ["127.0.0.1:7012"]}
                ),
                encoding="utf-8",
            )
            cfg = load_osc_relay_config(path)
            self.assertTrue(cfg.active)
            self.assertEqual(cfg.listen_port, 7011)

    def test_shipped_config_is_valid(self) -> None:
        """The config that actually ships must parse."""
        shipped = Path(__file__).resolve().parents[1] / "config" / "osc_relay.json"
        if not shipped.is_file():
            self.skipTest("config/osc_relay.json not present")
        cfg = load_osc_relay_config(shipped)
        self.assertTrue(cfg.active)


class RelayForwardingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.relay: OscRelay | None = None
        self.sockets: list[socket.socket] = []

    def tearDown(self) -> None:
        if self.relay is not None:
            self.relay.shutdown()
        for sock in self.sockets:
            try:
                sock.close()
            except OSError:
                pass

    def _listener(self) -> tuple[socket.socket, int]:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        sock.settimeout(2.0)
        self.sockets.append(sock)
        return sock, sock.getsockname()[1]

    def _start_relay(self, destinations: list[tuple[str, int]]) -> int:
        listen_port = _free_udp_port()
        self.relay = OscRelay(
            OscRelayConfig(
                enabled=True,
                listen_host="127.0.0.1",
                listen_port=listen_port,
                destinations=tuple(destinations),
            )
        )
        self.assertTrue(self.relay.start())
        return listen_port

    def test_forwards_bytes_verbatim_to_every_destination(self) -> None:
        """The relay must not parse or rewrite -- Resolume sends bundles."""
        deck, deck_port = self._listener()
        ipad, ipad_port = self._listener()
        listen_port = self._start_relay(
            [("127.0.0.1", deck_port), ("127.0.0.1", ipad_port)]
        )

        # A real OSC bundle: '#bundle', timetag, then one size-prefixed
        # message. Resolume sends these (sendBundles="1" in osc.xml).
        payload = (
            b"#bundle\x00"
            b"\x00\x00\x00\x00\x00\x00\x00\x01"
            b"\x00\x00\x00\x18"
            b"/composition/layers/1/video/opacity\x00"[:36]
            + b",f\x00\x00"
            + b"\x3f\x00\x00\x00"
        )

        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sockets.append(sender)
        sender.sendto(payload, ("127.0.0.1", listen_port))

        self.assertEqual(deck.recv(65535), payload)
        self.assertEqual(ipad.recv(65535), payload)

    def test_binary_payload_survives_intact(self) -> None:
        """Type 'r' packed colors and any other binary must pass untouched."""
        deck, deck_port = self._listener()
        listen_port = self._start_relay([("127.0.0.1", deck_port)])

        payload = bytes(range(256)) * 4
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sockets.append(sender)
        sender.sendto(payload, ("127.0.0.1", listen_port))

        self.assertEqual(deck.recv(65535), payload)

    def test_one_dead_destination_does_not_starve_the_other(self) -> None:
        """iPad asleep must not stop the Deck receiving feedback."""
        deck, deck_port = self._listener()
        dead_port = _free_udp_port()  # nothing bound here
        listen_port = self._start_relay(
            [("127.0.0.1", dead_port), ("127.0.0.1", deck_port)]
        )

        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sockets.append(sender)
        for _ in range(5):
            sender.sendto(b"/ping\x00\x00\x00", ("127.0.0.1", listen_port))
            time.sleep(0.02)

        # The live surface keeps receiving regardless of the dead one.
        self.assertEqual(deck.recv(65535), b"/ping\x00\x00\x00")

    def test_stats_track_throughput(self) -> None:
        deck, deck_port = self._listener()
        listen_port = self._start_relay([("127.0.0.1", deck_port)])

        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sockets.append(sender)
        sender.sendto(b"/x\x00\x00", ("127.0.0.1", listen_port))
        deck.recv(65535)

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if self.relay is not None and self.relay.stats()["packets_out"]:
                break
            time.sleep(0.01)

        stats = self.relay.stats() if self.relay is not None else {}
        self.assertEqual(stats["packets_in"], 1)
        self.assertEqual(stats["packets_out"], 1)
        self.assertTrue(stats["running"])

    def test_inactive_config_does_not_start(self) -> None:
        relay = OscRelay(OscRelayConfig())
        self.assertFalse(relay.start())
        self.assertFalse(relay.running)

    def test_shutdown_is_idempotent(self) -> None:
        _deck, deck_port = self._listener()
        self._start_relay([("127.0.0.1", deck_port)])
        assert self.relay is not None
        self.relay.shutdown()
        self.relay.shutdown()
        self.assertFalse(self.relay.running)


if __name__ == "__main__":
    unittest.main()
