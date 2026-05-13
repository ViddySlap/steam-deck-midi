"""System tray icon for the Steam Deck MIDI receiver.

Two entry points live in this module:

* ``ReceiverTray`` — the legacy sidecar tray. Bridge owns the main thread,
  the tray runs in a daemon ``threading.Thread``. Used by the default
  ``win_recv`` path (no ``--tray`` flag). Menu: Open web UI + Quit.

* ``run_tray_mode`` — the v0.4.3 P4 auto-start tray mode. Tray owns the
  main thread (which is what pystray expects on Windows), bridge runs in
  a worker thread. Console output is teed to a rotating log file so the
  "View Terminal" menu item can tail it in a separate PowerShell window —
  closing that PowerShell does NOT stop the bridge. Menu: Open Web UI,
  View Terminal, Quit.

This module is import-safe on machines without a display: importing it
only pulls in pystray + PIL, which both work headless. Actually starting
the icon (``Icon.run``) is what requires a Windows session.
"""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
import threading
import time
import webbrowser
from ctypes import wintypes
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable, Optional

import pystray
from PIL import Image, ImageDraw

LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Single-instance lock
# ---------------------------------------------------------------------------

# Windows error code returned by CreateMutexW when the named mutex already
# exists in another process. We use this to detect "am I a second launch?"
# without needing pywin32 as a runtime dep.
_ERROR_ALREADY_EXISTS = 183

# Global namespace so the mutex is visible across user sessions on the same
# machine. The trailing identifier should change if the lock semantics ever
# change incompatibly.
DEFAULT_INSTANCE_MUTEX_NAME = "Global\\STEAMDECK-MIDI-RECEIVER-2-singleinstance-v1"


def acquire_single_instance_lock(
    name: str = DEFAULT_INSTANCE_MUTEX_NAME,
) -> tuple[Optional[int], bool]:
    """Acquire a Windows named mutex to enforce single-instance launches.

    Returns ``(handle, is_first)``:
        handle: opaque mutex HANDLE to keep alive until process exit
            (held implicitly by the kernel; we never release explicitly).
            ``None`` on non-Windows platforms or on failure.
        is_first: ``True`` if we are the first instance and acquired the
            lock. ``False`` if another process already holds it — caller
            should fall back to opening the UI in a browser and exiting.

    The OS releases the mutex automatically when the process exits, even
    on a hard crash, so there is no stuck-lock scenario.
    """
    if sys.platform != "win32":
        return (None, True)
    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = [
            wintypes.LPVOID,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        ]
        kernel32.GetLastError.restype = wintypes.DWORD
        handle = kernel32.CreateMutexW(None, False, name)
        last_error = int(kernel32.GetLastError())
    except Exception:  # noqa: BLE001 - lock is best-effort
        LOGGER.exception("single-instance: CreateMutexW raised; allowing launch")
        return (None, True)
    if not handle:
        LOGGER.warning(
            "single-instance: CreateMutexW returned null handle (last_error=%d); "
            "allowing launch",
            last_error,
        )
        return (None, True)
    return (int(handle), last_error != _ERROR_ALREADY_EXISTS)

# ---------------------------------------------------------------------------
# Icon
# ---------------------------------------------------------------------------

# On-disk placeholder icon path. Used when present; otherwise we draw an
# icon procedurally with PIL. Ben can drop a custom .ico/.png here later.
DEFAULT_ICON_PATH = Path(__file__).parent / "assets" / "tray.ico"


def _make_icon_image(size: int = 64) -> Image.Image:
    """Draw a simple Steam Deck-style icon: dark rounded rect with a white D-pad cross."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background — dark blue-grey rounded rectangle
    pad = 2
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=12,
        fill=(30, 40, 60, 255),
    )

    # Horizontal bar of D-pad cross
    cx, cy = size // 2, size // 2
    arm = size // 5
    thick = size // 8
    draw.rectangle([cx - arm, cy - thick // 2, cx + arm, cy + thick // 2], fill=(200, 210, 230))
    # Vertical bar
    draw.rectangle([cx - thick // 2, cy - arm, cx + thick // 2, cy + arm], fill=(200, 210, 230))

    # Two small circles for ABXY buttons (right side)
    btn_x = cx + arm + 4
    r = thick // 2
    draw.ellipse([btn_x - r, cy - arm // 2 - r, btn_x + r, cy - arm // 2 + r], fill=(100, 180, 120))
    draw.ellipse([btn_x - r, cy + arm // 2 - r, btn_x + r, cy + arm // 2 + r], fill=(200, 100, 100))

    return img


def _load_icon_image() -> Image.Image:
    """Prefer the on-disk asset; fall back to the procedural icon."""
    if DEFAULT_ICON_PATH.exists():
        try:
            return Image.open(DEFAULT_ICON_PATH)
        except Exception as exc:  # noqa: BLE001 - icon is non-critical
            LOGGER.warning("could not load tray icon %s: %s", DEFAULT_ICON_PATH, exc)
    return _make_icon_image()


# ---------------------------------------------------------------------------
# Legacy sidecar tray (unchanged behavior; default --no-tray path)
# ---------------------------------------------------------------------------


class ReceiverTray:
    """Sidecar tray used by the default (non-``--tray``) ``win_recv`` path.

    Runs in a daemon thread alongside the bridge on the main thread.
    """

    def __init__(
        self,
        ui_url: str,
        quit_callback: Callable[[], None],
    ) -> None:
        self._ui_url = ui_url
        self._quit_callback = quit_callback
        self._icon: Optional[pystray.Icon] = None

    def _open_web_ui(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        webbrowser.open(self._ui_url)

    def _quit(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        icon.stop()
        self._quit_callback()

    def run_in_thread(self) -> threading.Thread:
        menu = pystray.Menu(
            pystray.MenuItem("Open web UI", self._open_web_ui, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )
        self._icon = pystray.Icon(
            name="steam-deck-midi",
            icon=_load_icon_image(),
            title="Steam Deck MIDI",
            menu=menu,
        )
        t = threading.Thread(target=self._icon.run, daemon=True, name="tray")
        t.start()
        return t

    def stop(self) -> None:
        if self._icon is not None:
            self._icon.stop()


# ---------------------------------------------------------------------------
# v0.4.3 P4 tray-mode: tray owns main thread, bridge in worker thread
# ---------------------------------------------------------------------------


def default_log_path() -> Path:
    """Return the rotating log path under ``%LOCALAPPDATA%``.

    Used both by the tee setup and by the View Terminal menu item.
    """
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        local_appdata = str(Path.home() / "AppData" / "Local")
    return (
        Path(local_appdata)
        / "STEAMDECK MIDI Receiver 2"
        / "logs"
        / "bridge.log"
    )


class _TeeStream:
    """Write-through stream that mirrors every write to a logging handler.

    Used to capture print() / direct sys.stdout.write() output into the
    rotating log file while keeping the console copy intact. logging
    output goes through the root handlers (we wire a FileHandler into
    those separately).
    """

    def __init__(self, original: Any, log_method: Callable[[str], None]) -> None:
        self._original = original
        self._log = log_method
        self._buffer = ""

    def write(self, data: str) -> int:
        try:
            n = self._original.write(data)
        except Exception:  # noqa: BLE001 - never let logging eat the real stream
            n = len(data)
        self._buffer += data
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line:
                try:
                    self._log(line)
                except Exception:  # noqa: BLE001
                    pass
        return n

    def flush(self) -> None:
        try:
            self._original.flush()
        except Exception:  # noqa: BLE001
            pass

    def __getattr__(self, name: str) -> Any:
        return getattr(self._original, name)


def setup_log_tee(log_path: Optional[Path] = None) -> Path:
    """Wire stdout/stderr + the root logger to a rotating file.

    Returns the path that was wired up. Safe to call once; idempotent
    enough that a second call attaches another handler but doesn't break
    anything (we de-dup by tag).
    """
    log_path = log_path or default_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    tag = f"tray-tee:{log_path}"
    for handler in root.handlers:
        if getattr(handler, "_tray_tee_tag", None) == tag:
            return log_path  # already wired

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    file_handler._tray_tee_tag = tag  # type: ignore[attr-defined]
    root.addHandler(file_handler)

    # PyInstaller windowed builds (console=False) have no stderr/stdout —
    # sys.stderr is None and any logging.StreamHandler attached by an
    # earlier logging.basicConfig() call will raise on emit, masking the
    # real startup error behind "--- Logging error ---" diagnostics. Strip
    # those handlers now so the file handler is the only sink. Console
    # builds have a real stderr and don't hit this; the strip is a no-op
    # for them because basicConfig's StreamHandler points at a valid
    # stream.
    if sys.stderr is None or sys.stdout is None:
        for handler in list(root.handlers):
            if isinstance(handler, logging.StreamHandler) and not isinstance(
                handler, RotatingFileHandler
            ):
                root.removeHandler(handler)

    # Also tee raw stdout/stderr (covers print() and any third-party libs
    # that bypass logging). _TeeStream tolerates a None original stream
    # gracefully, so this is safe in windowed mode where the original
    # streams are None.
    log = logging.getLogger("bridge.stdout")
    log_err = logging.getLogger("bridge.stderr")
    sys.stdout = _TeeStream(sys.stdout, log.info)  # type: ignore[assignment]
    sys.stderr = _TeeStream(sys.stderr, log_err.warning)  # type: ignore[assignment]

    LOGGER.info("tray-mode log tee active: %s", log_path)
    return log_path


def _open_view_terminal(log_path: Path) -> None:
    """Spawn a detached PowerShell that tails the log file.

    Closing that PowerShell window does NOT affect the bridge (separate
    process). The PowerShell uses ``Get-Content -Wait`` so new lines
    appear live.
    """
    if not log_path.exists():
        # Create an empty file so Get-Content -Wait has something to tail
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.touch()

    # CREATE_NEW_CONSOLE so the PowerShell gets its own window and stays
    # alive independently of the bridge process.
    CREATE_NEW_CONSOLE = 0x00000010
    DETACHED_PROCESS = 0x00000008
    flags = CREATE_NEW_CONSOLE | DETACHED_PROCESS

    ps_command = (
        f"$Host.UI.RawUI.WindowTitle = 'STEAMDECK MIDI bridge log'; "
        f"Write-Host 'Tailing {log_path}'; "
        f"Write-Host 'Closing this window will NOT stop the bridge.' "
        f"-ForegroundColor Yellow; "
        f"Get-Content -Path '{log_path}' -Wait -Tail 200"
    )

    try:
        subprocess.Popen(  # noqa: S603 - controlled command
            [
                "powershell.exe",
                "-NoExit",
                "-NoLogo",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps_command,
            ],
            creationflags=flags,
            close_fds=True,
        )
    except FileNotFoundError:
        LOGGER.error("powershell.exe not found; cannot open View Terminal window")
    except Exception as exc:  # noqa: BLE001 - menu items must not raise
        LOGGER.error("failed to spawn View Terminal: %s", exc)


def build_tray_menu(
    ui_url: str,
    on_quit: Callable[[], None],
    log_path: Optional[Path] = None,
) -> pystray.Menu:
    """Build the v0.4.3 P4 tray menu.

    Public so tests can assert on the menu structure without starting
    the icon.
    """
    resolved_log = log_path or default_log_path()

    def _open_ui(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        webbrowser.open(ui_url)

    def _view_terminal(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        _open_view_terminal(resolved_log)

    def _quit(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        icon.stop()
        on_quit()

    return pystray.Menu(
        pystray.MenuItem("Open Web UI", _open_ui, default=True),
        pystray.MenuItem("View Terminal", _view_terminal),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", _quit),
    )


class TrayApp:
    """Owns the main-thread tray icon and a background bridge thread.

    Lifecycle:
        app = TrayApp(ui_url=..., run_bridge=fn, ...)
        app.run()  # blocks on main thread until Quit

    ``run_bridge`` is a zero-arg callable that runs the bridge loop
    (typically a thin wrapper around ``serve_forever``). When Quit is
    selected we attempt a graceful shutdown via the stop callback, wait
    a short grace period, then ``os._exit(0)`` to ensure the process
    actually terminates — the underlying ``serve_forever`` doesn't
    currently honor a stop event (see ``installer-changes.md`` for the
    follow-up to plumb that through cleanly).
    """

    def __init__(
        self,
        ui_url: str,
        run_bridge: Callable[[], None],
        stop_bridge: Optional[Callable[[], None]] = None,
        log_path: Optional[Path] = None,
        grace_seconds: float = 1.5,
    ) -> None:
        self._ui_url = ui_url
        self._run_bridge = run_bridge
        self._stop_bridge = stop_bridge
        self._log_path = log_path or default_log_path()
        self._grace = grace_seconds
        self._icon: Optional[pystray.Icon] = None
        self._bridge_thread: Optional[threading.Thread] = None
        self._quit_requested = threading.Event()

    def _bridge_target(self) -> None:
        try:
            self._run_bridge()
        except Exception:  # noqa: BLE001 - log and exit thread
            LOGGER.exception("bridge thread crashed")
        finally:
            # If the bridge stops on its own (e.g. fatal MIDI error),
            # tear down the tray so the user notices.
            if not self._quit_requested.is_set() and self._icon is not None:
                LOGGER.warning("bridge exited unexpectedly; stopping tray")
                self._icon.stop()

    def _on_quit(self) -> None:
        self._quit_requested.set()
        if self._stop_bridge is not None:
            try:
                self._stop_bridge()
            except Exception:  # noqa: BLE001
                LOGGER.exception("stop_bridge callback failed")
        # Give the bridge a brief grace window to flush state, then
        # force-exit. The bridge thread is a non-daemon (so MIDI release
        # has a chance), but we own the process exit.
        threading.Thread(
            target=self._force_exit_after_grace,
            daemon=True,
            name="tray-quit",
        ).start()

    def _force_exit_after_grace(self) -> None:
        time.sleep(self._grace)
        LOGGER.info("tray-mode quit: forcing process exit")
        os._exit(0)

    def run(self) -> None:
        """Start the bridge thread, then run the tray on the main thread."""
        self._bridge_thread = threading.Thread(
            target=self._bridge_target,
            daemon=False,
            name="bridge",
        )
        self._bridge_thread.start()

        menu = build_tray_menu(
            ui_url=self._ui_url,
            on_quit=self._on_quit,
            log_path=self._log_path,
        )
        self._icon = pystray.Icon(
            name="steam-deck-midi",
            icon=_load_icon_image(),
            title="Steam Deck MIDI Receiver 2",
            menu=menu,
        )
        # First-run balloon: pystray notify is best-effort on Windows.
        try:
            self._icon.run(setup=self._on_icon_ready)
        except Exception:  # noqa: BLE001
            LOGGER.exception("tray icon crashed")
            raise

    def _on_icon_ready(self, icon: pystray.Icon) -> None:
        icon.visible = True
        try:
            icon.notify(
                "Bridge is running in the system tray.",
                "STEAMDECK MIDI Receiver 2",
            )
        except Exception:  # noqa: BLE001 - notifications are best-effort
            pass


def run_tray_mode(
    ui_url: str,
    run_bridge: Callable[[], None],
    stop_bridge: Optional[Callable[[], None]] = None,
    log_path: Optional[Path] = None,
) -> None:
    """Entry point for ``win_recv --tray``.

    Sets up the log tee, then hands off to ``TrayApp.run`` on the main
    thread. Blocks until Quit.
    """
    resolved_log = setup_log_tee(log_path)
    app = TrayApp(
        ui_url=ui_url,
        run_bridge=run_bridge,
        stop_bridge=stop_bridge,
        log_path=resolved_log,
    )
    app.run()
