"""VISCA-over-IP UDP sender + Sony framing for the ptz_visca engine.

Mirrors the repo's existing UDP send idiom (``osc_client.py``): one reusable
connectionless ``SOCK_DGRAM`` socket, ``sendto`` per call, errors swallowed
with a debug log. Two differences from ``osc_client``:

1. **Bind the source interface.** ``osc_client`` targets loopback so it never
   binds; VISCA must pin egress to the ASIX camera-NIC dongle. The socket
   source is bound to ``(camera_nic_ip, 0)`` so packets leave 192.168.0.100,
   not the 10.10.10.x rig LAN.
2. **Sony framing + per-camera sequence.** Each VISCA payload is wrapped in the
   mandatory 8-byte header with a monotonic, per-destination sequence counter.

The verified command bytes and the framing spec are the canonical
``wiki/reference/ptz-cameras.md`` facts (probe 2026-06-02, physically verified).
Raw un-framed VISCA on UDP 52381 gets zero reply — the Sony header is required.

This module is pure transport: it decides *how* to put a command on the wire,
never *what* to send (that is the engine's job). Speed/direction inputs are
clamped defensively to the verified ranges. Sends are fire-and-forget: no
retry, no blocking, no reply read — ACK/completion (90 41 FF / 90 51 FF) are
ignored for motion (recon rate-stress: 60 cmds @ 49 Hz, 0 errors).
"""

from __future__ import annotations

import logging
import socket
import struct

LOGGER = logging.getLogger(__name__)

# --- Defaults (config-driven in the engine; mirrored here for direct use) ---
CAMERA_NIC_IP = "192.168.0.100"
VISCA_PORT = 52381

# --- Direction nibbles (verified — wiki/reference/ptz-cameras.md) ----------
PAN_LEFT, PAN_RIGHT, PT_STOP = 0x01, 0x02, 0x03
TILT_UP, TILT_DOWN = 0x01, 0x02  # PT_STOP (0x03) is shared by both axes

# --- Speed-byte ranges (verified) ------------------------------------------
PAN_SPEED_MIN, PAN_SPEED_MAX = 0x01, 0x18  # 1..24
TILT_SPEED_MIN, TILT_SPEED_MAX = 0x01, 0x14  # 1..20
ZOOM_SPEED_MIN, ZOOM_SPEED_MAX = 0, 7

# Sony VISCA-over-IP payload type for a VISCA command (the only type we send).
_PAYLOAD_TYPE_COMMAND = b"\x01\x00"


# ---------------------------------------------------------------------------
# Sony frame builder + VISCA payload builders (pure functions -> bytes)
# ---------------------------------------------------------------------------


def build_frame(payload: bytes, seq: int) -> bytes:
    """Wrap a VISCA payload in the mandatory Sony 8-byte header.

    ``[ payload-type (2) ][ length (2) ][ sequence (4) ][ payload ... ]``
    payload-type 0x0100 (VISCA command) | big-endian length | big-endian seq.
    """
    return (
        _PAYLOAD_TYPE_COMMAND
        + struct.pack(">H", len(payload))
        + struct.pack(">I", seq & 0xFFFFFFFF)
        + payload
    )


def pantilt_payload(pan_speed: int, tilt_speed: int, pan_dir: int, tilt_dir: int) -> bytes:
    """Pan-tiltDrive frame: ``81 01 06 01 VV WW 0p 0t FF``.

    Speed bytes must be in-range even for a STOP (the direction nibbles carry
    the stop), so they are clamped to the verified [1..max] ranges.
    """
    vv = max(PAN_SPEED_MIN, min(PAN_SPEED_MAX, int(pan_speed)))
    ww = max(TILT_SPEED_MIN, min(TILT_SPEED_MAX, int(tilt_speed)))
    return bytes([0x81, 0x01, 0x06, 0x01, vv, ww, pan_dir, tilt_dir, 0xFF])


def pantilt_stop_payload() -> bytes:
    """Pan/tilt STOP: ``81 01 06 01 06 06 03 03 FF`` (both nibbles 0x03)."""
    return bytes([0x81, 0x01, 0x06, 0x01, 0x06, 0x06, PT_STOP, PT_STOP, 0xFF])


def zoom_payload(direction: str, speed: int) -> bytes:
    """Zoom frame. ``in`` -> tele ``2p``; ``out`` -> wide ``3p``; ``stop`` -> ``00``.

    ``81 01 04 07 2p/3p/00 FF`` with ``p`` clamped to 0..7.
    """
    if direction == "stop":
        return bytes([0x81, 0x01, 0x04, 0x07, 0x00, 0xFF])
    p = max(ZOOM_SPEED_MIN, min(ZOOM_SPEED_MAX, int(speed)))
    nibble = 0x20 if direction == "in" else 0x30  # 2p tele / 3p wide
    return bytes([0x81, 0x01, 0x04, 0x07, nibble | p, 0xFF])


# ---------------------------------------------------------------------------
# Sender
# ---------------------------------------------------------------------------


class PtzViscaSender:
    """Fire-and-forget VISCA-over-IP sender bound to the camera NIC.

    Construction binds the egress socket to the camera-NIC source IP. On a dev
    box without the ASIX dongle the bind raises ``OSError`` — the caller
    (the engine) catches that and degrades to ``sender = None`` so the bridge
    still loads. Tests inject ``sock=`` to bypass the real bind.
    """

    def __init__(
        self,
        camera_nic_ip: str = CAMERA_NIC_IP,
        port: int = VISCA_PORT,
        *,
        sock: "socket.socket | None" = None,
    ) -> None:
        self._camera_nic_ip = camera_nic_ip
        self._port = int(port)
        # Per-camera-IP monotonic sequence counters (uint32, wrap at 0xFFFFFFFF).
        self._seq: dict[str, int] = {}
        if sock is not None:
            self._sock = sock
        else:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Pin egress to the camera-facing dongle, ephemeral source port.
            # Raises OSError if the NIC isn't present — propagated to the caller.
            self._sock.bind((camera_nic_ip, 0))

    # -- low-level send -----------------------------------------------------

    def _send(self, ip: str, payload: bytes) -> None:
        seq = self._seq.get(ip, 0)
        frame = build_frame(payload, seq)
        self._seq[ip] = (seq + 1) & 0xFFFFFFFF
        try:
            self._sock.sendto(frame, (ip, self._port))
        except OSError:
            # Swallow — never stall the receiver loop on a transient send error.
            LOGGER.debug("VISCA send failed to %s", ip)

    # -- command API (used by the engine) -----------------------------------

    def send_pantilt(
        self, ip: str, pan_speed: int, tilt_speed: int, pan_dir: int, tilt_dir: int
    ) -> None:
        self._send(ip, pantilt_payload(pan_speed, tilt_speed, pan_dir, tilt_dir))

    def send_zoom(self, ip: str, direction: str, speed: int) -> None:
        self._send(ip, zoom_payload(direction, speed))

    def send_stop(self, ip: str) -> None:
        """Pan/tilt STOP (03 03)."""
        self._send(ip, pantilt_stop_payload())

    def send_zoom_stop(self, ip: str) -> None:
        """Zoom STOP (00)."""
        self._send(ip, zoom_payload("stop", 0))

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass
