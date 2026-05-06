"""Tiny stdlib OSC client.

Just enough to send a typed OSC message over UDP. Avoids pulling in
python-osc as a dependency for the bridge.
"""

from __future__ import annotations

import logging
import socket
import struct
from typing import Any

LOGGER = logging.getLogger(__name__)


def _pad4(b: bytes) -> bytes:
    return b + b"\x00" * (-len(b) % 4)


def _build_message(address: str, value: Any) -> bytes:
    """Build a single-argument OSC message. Supports float, int, bool, str."""
    addr = _pad4(address.encode("utf-8") + b"\x00")
    if isinstance(value, bool):
        # OSC has true/false types but they have no payload; we encode as int
        type_tag = b",T" if value else b",F"
        return addr + _pad4(type_tag + b"\x00")
    if isinstance(value, float):
        return addr + _pad4(b",f\x00\x00") + struct.pack(">f", value)
    if isinstance(value, int):
        return addr + _pad4(b",i\x00\x00") + struct.pack(">i", value)
    if isinstance(value, str):
        return addr + _pad4(b",s\x00\x00") + _pad4(value.encode("utf-8") + b"\x00")
    raise TypeError(f"Unsupported OSC value type: {type(value).__name__}")


class OscClient:
    """Connectionless UDP OSC sender. Cheap to construct, cheap to call."""

    def __init__(self, host: str = "127.0.0.1", port: int = 7000):
        self._host = host
        self._port = port
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, address: str, value: Any) -> None:
        try:
            data = _build_message(address, value)
            self._sock.sendto(data, (self._host, self._port))
        except OSError as exc:
            LOGGER.debug("OSC send failed for %s = %r: %s", address, value, exc)

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass
