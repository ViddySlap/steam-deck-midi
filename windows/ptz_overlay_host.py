"""Bridge side of the PTZ camera overlay (see windows/ptz_overlay.py).

Three jobs:
  - track the live camera: the OSC relay hands every datagram from Resolume
    to `observe_osc`, which watches Layer 4 clip connects;
  - answer the overlay's poll (GET /api/ptz-overlay) with one state dict:
    visible, live camera, and each stick's camera + zoom direction;
  - launch the overlay as its own process and restart it if it dies, so an
    overlay crash can never take the bridge (or MIDI) down with it.

`enabled` is the web UI switch. It is not persisted: every bridge start
comes up with the overlay on. The overlay is visible only while it is
enabled AND the ptz_visca engine is active, which is what makes it follow
the PTZ preset.
"""

from __future__ import annotations

import logging
import os
import struct
import subprocess
import sys
import threading
import time
from typing import Any

LOGGER = logging.getLogger(__name__)

CUT_LAYER = 4
CAMERAS = (1, 2, 3)
_CLIP_PREFIX = f"/composition/layers/{CUT_LAYER}/clips/"
RESTART_DELAY_SECONDS = 3.0
CREATE_NO_WINDOW = 0x08000000


def _osc_string(buf: bytes, i: int) -> tuple[str, int]:
    end = buf.find(b"\x00", i)
    if end < 0:
        raise ValueError("unterminated OSC string")
    text = buf[i:end].decode("utf-8", "replace")
    end += 1
    return text, end + (-end) % 4


def osc_messages(buf: bytes):
    """Yield (address, args) from an OSC packet, recursing into bundles.

    Only int/float/string args are decoded; any other type ends the message.
    That is all the Layer 4 clip messages need.
    """
    if buf.startswith(b"#bundle\x00"):
        i = 16
        while i + 4 <= len(buf):
            (n,) = struct.unpack(">i", buf[i:i + 4])
            yield from osc_messages(buf[i + 4:i + 4 + n])
            i += 4 + n
        return
    addr, i = _osc_string(buf, 0)
    args: list = []
    if i < len(buf) and buf[i:i + 1] == b",":
        tags, i = _osc_string(buf, i)
        for t in tags[1:]:
            if t == "i":
                args.append(struct.unpack(">i", buf[i:i + 4])[0])
                i += 4
            elif t == "f":
                args.append(struct.unpack(">f", buf[i:i + 4])[0])
                i += 4
            elif t == "s":
                value, i = _osc_string(buf, i)
                args.append(value)
            else:
                break
    yield addr, args


def live_camera_from(addr: str, args: list) -> "int | None":
    """The camera a Layer 4 clip message makes live, else None.

    Resolume sends `.../clips/N/connect 1` on a cut and `.../clips/N/connected`
    with 3 (connected) or 4 (connected and previewing) for the new clip.
    Verified on the Red West rig 2026-10-16.
    """
    if not addr.startswith(_CLIP_PREFIX) or not args:
        return None
    parts = addr[len(_CLIP_PREFIX):].split("/")
    if len(parts) != 2 or not parts[0].isdigit():
        return None
    cam, leaf, value = int(parts[0]), parts[1], args[0]
    if cam not in CAMERAS:
        return None
    if (leaf == "connect" and value) or (leaf == "connected" and value in (3, 4)):
        return cam
    return None


class PtzOverlayHost:
    def __init__(self, engine_registry: Any = None, ui_port: int = 7723) -> None:
        self._registry = engine_registry
        self._ui_port = ui_port
        self._lock = threading.Lock()
        self.enabled = True
        self.live_camera: "int | None" = None
        self._proc: "subprocess.Popen | None" = None
        self._stopping = threading.Event()
        self._thread: "threading.Thread | None" = None

    # -- live camera (called on the OSC relay thread)
    def observe_osc(self, data: bytes) -> None:
        for addr, args in osc_messages(data):
            cam = live_camera_from(addr, args)
            if cam is not None:
                self.live_camera = cam

    # -- state for the overlay and the web UI
    def _ptz_engine(self) -> Any:
        if self._registry is None:
            return None
        return next((e for e in self._registry.engines if getattr(e, "type_name", None) == "ptz_visca"), None)

    def state(self) -> dict:
        engine = self._ptz_engine()
        active = bool(engine is not None and engine.active)
        sticks: dict = {}
        if engine is not None:
            status = engine.status()
            selected = status.get("selected") or {}
            zoom = status.get("zoom_direction") or {}
            for group in ("left", "right"):
                sticks[group] = {
                    "camera": selected.get(group),
                    "zoom": zoom.get(group, "in"),
                }
        return {
            "enabled": self.enabled,
            "ptz_active": active,
            "visible": self.enabled and active,
            "live_camera": self.live_camera,
            "sticks": sticks,
            "overlay_running": self.running,
        }

    def set_enabled(self, enabled: bool) -> dict:
        self.enabled = bool(enabled)
        LOGGER.info("ptz overlay %s from the web UI", "enabled" if self.enabled else "disabled")
        return self.state()

    # -- overlay process
    @property
    def running(self) -> bool:
        proc = self._proc
        return proc is not None and proc.poll() is None

    def _command(self) -> list[str]:
        args = ["--ptz-overlay", "--parent-pid", str(os.getpid()), "--bridge-port", str(self._ui_port)]
        if getattr(sys, "frozen", False):
            return [sys.executable, *args]
        exe = sys.executable
        windowed = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(windowed):
            exe = windowed
        return [exe, "-m", "windows.ptz_overlay", *args]

    def _spawn(self) -> None:
        env = dict(os.environ)
        # A PyInstaller onefile child must unpack its own copy; inheriting the
        # parent's extraction dir breaks when the parent exits.
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        for key in list(env):
            if key == "_MEIPASS2" or key.startswith("_PYI_"):
                env.pop(key)
        flags = CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self._proc = subprocess.Popen(self._command(), env=env, creationflags=flags,
                                      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL)
        LOGGER.info("ptz overlay process started (pid %s)", self._proc.pid)

    def _supervise(self) -> None:
        while not self._stopping.is_set():
            if not self.running:
                if self._proc is not None:
                    LOGGER.warning("ptz overlay process exited (code %s); restarting", self._proc.returncode)
                try:
                    self._spawn()
                except OSError as exc:
                    LOGGER.warning("ptz overlay could not start: %s", exc)
            self._stopping.wait(RESTART_DELAY_SECONDS)

    def start(self) -> None:
        if sys.platform != "win32":
            LOGGER.info("ptz overlay is Windows-only; not started on %s", sys.platform)
            return
        self._thread = threading.Thread(target=self._supervise, name="ptz-overlay", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
