"""Shared UDP listener for NestDrop OSC OUTPUT broadcasts.

NestDrop broadcasts state changes (sprite activations, queue active
toggles, BPM, etc.) over OSC out (default port 8001). Engines that want
to stay in sync with NestDrop's actual state subscribe here.

One singleton listener per port; multiple engines can register their
own callbacks. Lazy-start on first subscribe.

OSC parsing is the same minimal stdlib parser as `scripts/osc_sniff.py`.
"""

from __future__ import annotations

import logging
import socket
import struct
import threading
from typing import Callable

LOGGER = logging.getLogger(__name__)

OSCCallback = Callable[[str, list], None]
"""Signature: (address, args) -> None. Called for every OSC message received."""


def _read_string(buf: bytes, i: int) -> tuple[str, int]:
    end = buf.find(b"\x00", i)
    if end < 0:
        return buf[i:].decode("utf-8", errors="replace"), len(buf)
    s = buf[i:end].decode("utf-8", errors="replace")
    end += 1
    end += (-end) % 4
    return s, end


def parse_osc(data: bytes) -> tuple[str, list]:
    """Parse a single OSC message into (address, args). Bundles not handled."""
    addr, i = _read_string(data, 0)
    args: list = []
    if i >= len(data) or data[i:i + 1] != b",":
        return addr, args
    type_tag, i = _read_string(data, i)
    for t in type_tag[1:]:
        if t == "i":
            args.append(struct.unpack(">i", data[i:i + 4])[0]); i += 4
        elif t == "f":
            args.append(struct.unpack(">f", data[i:i + 4])[0]); i += 4
        elif t == "s":
            s, i = _read_string(data, i); args.append(s)
        elif t == "T":
            args.append(True)
        elif t == "F":
            args.append(False)
        elif t == "N":
            args.append(None)
        else:
            break
    return addr, args


class _Listener:
    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._callbacks: list[OSCCallback] = []
        self._lock = threading.Lock()
        self._running = False

    def add(self, callback: OSCCallback) -> None:
        with self._lock:
            self._callbacks.append(callback)
            if not self._running:
                self._start()

    def _start(self) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self._host, self._port))
            sock.settimeout(0.5)
        except OSError as exc:
            LOGGER.warning(
                "NestDrop listener could not bind %s:%s (%s); broadcasts won't be received",
                self._host,
                self._port,
                exc,
            )
            return
        self._sock = sock
        self._running = True
        self._thread = threading.Thread(target=self._run, name="nestdrop-listener", daemon=True)
        self._thread.start()
        LOGGER.info("NestDrop listener bound to %s:%s", self._host, self._port)

    def _run(self) -> None:
        sock = self._sock
        assert sock is not None
        while self._running:
            try:
                data, _ = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                addr, args = parse_osc(data)
            except Exception:
                LOGGER.debug("malformed OSC from NestDrop; skipping", exc_info=True)
                continue
            with self._lock:
                callbacks = list(self._callbacks)
            for cb in callbacks:
                try:
                    cb(addr, args)
                except Exception:
                    LOGGER.exception("NestDrop listener callback raised")

    def shutdown(self) -> None:
        self._running = False
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass


# Singleton per (host, port). The expected case is one shared listener
# on 127.0.0.1:8001; this dict is here for the rare case of multiple
# NestDrop instances on different ports.
_LISTENERS: dict[tuple[str, int], _Listener] = {}
_REGISTRY_LOCK = threading.Lock()


def subscribe(host: str, port: int, callback: OSCCallback) -> None:
    """Register `callback` to receive every OSC message arriving on host:port.

    The first subscriber lazy-starts a background thread bound to that
    UDP socket. Additional subscribers share the socket.
    """
    key = (host, port)
    with _REGISTRY_LOCK:
        listener = _LISTENERS.get(key)
        if listener is None:
            listener = _Listener(host, port)
            _LISTENERS[key] = listener
    listener.add(callback)


def shutdown_all() -> None:
    """Used by tests and engine shutdown for clean teardown."""
    with _REGISTRY_LOCK:
        listeners = list(_LISTENERS.values())
        _LISTENERS.clear()
    for l in listeners:
        l.shutdown()
