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


def _build_color_message(address: str, r: int, g: int, b: int, a: int) -> bytes:
    """Build an OSC type 'r' message (32-bit packed RGBA).

    Resolume's OSC API uses OSC type 'r' for ParamColor inputs. String hex
    formats and 4-float RGBA are NOT accepted by Arena's OSC handler -- only
    type 'r'. Verified 2026-05-11 on Arena 7.26.0.
    """
    addr = _pad4(address.encode("utf-8") + b"\x00")
    type_tag = _pad4(b",r\x00\x00")
    payload = struct.pack(">BBBB", r & 0xFF, g & 0xFF, b & 0xFF, a & 0xFF)
    return addr + type_tag + payload


def hex_to_rgba(hex_str: str) -> tuple[int, int, int, int]:
    """Parse a Resolume-style #rrggbbaa or #rrggbb hex string into (r,g,b,a)."""
    s = hex_str.lstrip("#")
    if len(s) == 6:
        s += "ff"
    if len(s) != 8:
        raise ValueError(f"invalid hex color {hex_str!r}")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), int(s[6:8], 16))


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

    def send_color(self, address: str, hex_value: str) -> None:
        """Send a ParamColor using OSC type 'r' (Resolume's required format)."""
        try:
            r, g, b, a = hex_to_rgba(hex_value)
            data = _build_color_message(address, r, g, b, a)
            self._sock.sendto(data, (self._host, self._port))
        except (OSError, ValueError) as exc:
            LOGGER.debug(
                "OSC color send failed for %s = %r: %s", address, hex_value, exc
            )

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass
