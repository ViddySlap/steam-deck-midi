"""OSC fan-out relay: one inbound UDP port, N outbound destinations.

Resolume Arena's OSC output (Preferences -> OSC -> Output) accepts exactly
one target address and one target port -- see `Preferences/osc.xml`, which
has a single `<Output>` element. That is fine with one control surface and
a hard blocker with two (Steam Deck + iPad both running TouchOSC).

This relay is the fix. Resolume points at the bridge on localhost; the
bridge re-sends every datagram, byte for byte, to every configured
destination.

**It deliberately does not parse OSC.** Resolume sends with
`sendBundles="1"`, so the wire carries `#bundle` packets with timetags,
and the payloads include OSC type 'r' (packed RGBA) that the bridge's
other OSC parser (`engines/_nestdrop_listener.parse_osc`) does not
handle. Forwarding raw bytes means bundles, colors, blobs and any future
Resolume message type pass through untouched and cannot be corrupted by a
parser that did not anticipate them.

This is core receiver infrastructure, NOT an engine. Engines carry a
per-preset on/off toggle, and a toggle left off here would silently kill
feedback on *both* surfaces at once, mid-show, with no visible symptom.
The relay runs whenever destinations are configured.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
from dataclasses import dataclass, field
from pathlib import Path

LOGGER = logging.getLogger(__name__)

DEFAULT_LISTEN_HOST = "127.0.0.1"
DEFAULT_LISTEN_PORT = 7010

# OSC bundles from a busy composition stay well under this, but a UDP
# datagram can carry ~64 KB and truncating one would corrupt the bundle.
MAX_DATAGRAM_BYTES = 65535

# Poll cadence for the shutdown flag. Matches the NestDrop listener.
_RECV_TIMEOUT_SECONDS = 0.5


class OscRelayError(ValueError):
    """Raised when the OSC relay config is malformed."""


@dataclass(frozen=True)
class OscRelayConfig:
    """Relay wiring. `enabled` false or an empty `destinations` = no relay."""

    enabled: bool = False
    listen_host: str = DEFAULT_LISTEN_HOST
    listen_port: int = DEFAULT_LISTEN_PORT
    destinations: tuple[tuple[str, int], ...] = field(default_factory=tuple)

    @property
    def active(self) -> bool:
        return self.enabled and bool(self.destinations)


def _parse_endpoint(value: object, *, what: str) -> tuple[str, int]:
    if not isinstance(value, str):
        raise OscRelayError(f"{what} must be a string in host:port form")
    try:
        host, port_text = value.rsplit(":", 1)
        port = int(port_text)
    except ValueError as exc:
        raise OscRelayError(f"{what} must be in host:port form, got {value!r}") from exc
    if not host:
        raise OscRelayError(f"{what} is missing a host: {value!r}")
    if not 1 <= port <= 65535:
        raise OscRelayError(f"{what} port out of range: {port}")
    return host, port


def parse_osc_relay_config(spec: object) -> OscRelayConfig:
    """Build a config from an already-decoded JSON object."""
    if not isinstance(spec, dict):
        raise OscRelayError("osc_relay config must be a JSON object")

    listen_host, listen_port = _parse_endpoint(
        spec.get("listen", f"{DEFAULT_LISTEN_HOST}:{DEFAULT_LISTEN_PORT}"),
        what="osc_relay.listen",
    )

    raw_destinations = spec.get("destinations", [])
    if not isinstance(raw_destinations, list):
        raise OscRelayError("osc_relay.destinations must be a list")

    destinations: list[tuple[str, int]] = []
    for entry in raw_destinations:
        dest = _parse_endpoint(entry, what="osc_relay.destinations[]")
        # A destination equal to the listen socket would feed the relay its
        # own output forever. Cheap to check, impossible to debug live.
        if dest == (listen_host, listen_port):
            raise OscRelayError(
                f"osc_relay destination {entry!r} is the relay's own listen "
                "address; that would loop"
            )
        if dest in destinations:
            LOGGER.warning("osc_relay: duplicate destination %s:%s ignored", *dest)
            continue
        destinations.append(dest)

    enabled = spec.get("enabled", True)
    if not isinstance(enabled, bool):
        raise OscRelayError("osc_relay.enabled must be true or false")

    return OscRelayConfig(
        enabled=enabled,
        listen_host=listen_host,
        listen_port=listen_port,
        destinations=tuple(destinations),
    )


def load_osc_relay_config(path: str | Path) -> OscRelayConfig:
    """Load relay config from JSON. A missing file means 'no relay'.

    Absent config is the safe default: the bridge behaves exactly as it did
    before the relay existed, so an install that never ships this file is
    unchanged rather than broken.
    """
    config_path = Path(path)
    if not config_path.is_file():
        LOGGER.debug("osc_relay: no config at %s; relay disabled", config_path)
        return OscRelayConfig()
    try:
        spec = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OscRelayError(f"could not read {config_path}: {exc}") from exc
    return parse_osc_relay_config(spec)


def _silence_windows_connreset(sock: socket.socket) -> None:
    """Stop Windows turning an ICMP Port Unreachable into a socket error.

    On Windows, when a UDP datagram provokes an ICMP Port Unreachable from
    the far end, the *next* operation on the sending socket fails with
    WSAECONNRESET (10054) -- even though UDP is connectionless. In this
    relay that would mean: iPad sleeps or drops off the network, and the
    relay thread starts erroring instead of feeding the Deck.

    SIO_UDP_CONNRESET disables that behavior. Windows-only ioctl, so it is
    guarded; on other platforms there is nothing to disable.
    """
    if not hasattr(socket, "SIO_UDP_CONNRESET"):
        return
    try:
        sock.ioctl(socket.SIO_UDP_CONNRESET, False)  # type: ignore[attr-defined]
    except OSError as exc:
        LOGGER.debug("osc_relay: SIO_UDP_CONNRESET not applied: %s", exc)


class OscRelay:
    """Background thread that fans inbound datagrams out to N destinations."""

    def __init__(self, config: OscRelayConfig) -> None:
        self._config = config
        self._recv_sock: socket.socket | None = None
        self._send_sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()
        # Observability: "the iPad went dark" is otherwise unfalsifiable.
        self.packets_in = 0
        self.packets_out = 0
        self.send_errors = 0
        self._logged_first_packet = False

    @property
    def config(self) -> OscRelayConfig:
        return self._config

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> bool:
        """Bind and start relaying. Returns False if the relay stays off.

        A bind failure is logged and swallowed rather than raised: losing
        OSC feedback to the control surfaces should never stop the bridge
        from delivering MIDI, which is the show-critical path.
        """
        if not self._config.active:
            LOGGER.debug("osc_relay: not configured; skipping")
            return False

        try:
            recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            _silence_windows_connreset(recv_sock)
            recv_sock.bind((self._config.listen_host, self._config.listen_port))
            recv_sock.settimeout(_RECV_TIMEOUT_SECONDS)
        except OSError as exc:
            LOGGER.warning(
                "osc_relay: could not bind %s:%s (%s); OSC feedback to the "
                "control surfaces is DISABLED. Is another process holding "
                "that port?",
                self._config.listen_host,
                self._config.listen_port,
                exc,
            )
            return False

        send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        _silence_windows_connreset(send_sock)

        self._recv_sock = recv_sock
        self._send_sock = send_sock
        self._running = True
        self._thread = threading.Thread(
            target=self._run, name="osc-relay", daemon=True
        )
        self._thread.start()
        LOGGER.info(
            "osc_relay: listening on udp://%s:%s -> %s",
            self._config.listen_host,
            self._config.listen_port,
            ", ".join(f"{h}:{p}" for h, p in self._config.destinations),
        )
        return True

    def _run(self) -> None:
        recv_sock = self._recv_sock
        send_sock = self._send_sock
        assert recv_sock is not None and send_sock is not None
        destinations = self._config.destinations

        while self._running:
            try:
                data, _src = recv_sock.recvfrom(MAX_DATAGRAM_BYTES)
            except socket.timeout:
                continue
            except OSError:
                if self._running:
                    LOGGER.exception("osc_relay: receive failed; relay stopping")
                break

            with self._lock:
                self.packets_in += 1

            if not self._logged_first_packet:
                self._logged_first_packet = True
                # Confirms Resolume is actually pointed at the relay. Without
                # this you cannot tell "Resolume misconfigured" from "relay
                # broken" without a packet sniffer.
                LOGGER.info(
                    "osc_relay: first datagram received (%d bytes); "
                    "Resolume -> relay path is live",
                    len(data),
                )

            for host, port in destinations:
                try:
                    send_sock.sendto(data, (host, port))
                except OSError as exc:
                    # One unreachable surface must never starve the other.
                    with self._lock:
                        self.send_errors += 1
                    LOGGER.debug(
                        "osc_relay: send to %s:%s failed: %s", host, port, exc
                    )
                else:
                    with self._lock:
                        self.packets_out += 1

    def stats(self) -> dict[str, object]:
        with self._lock:
            return {
                "running": self._running,
                "listen": f"{self._config.listen_host}:{self._config.listen_port}",
                "destinations": [
                    f"{h}:{p}" for h, p in self._config.destinations
                ],
                "packets_in": self.packets_in,
                "packets_out": self.packets_out,
                "send_errors": self.send_errors,
            }

    def shutdown(self) -> None:
        self._running = False
        for sock in (self._recv_sock, self._send_sock):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
        self._recv_sock = None
        self._send_sock = None
