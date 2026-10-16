"""PTZ camera overlay: an on-top, click-through window drawn over Resolume's
three camera Layer Monitors.

It shows, per camera preview:
  - a soft yellow glow and a floating "LIVE CAM n" pill on the camera that
    Layer 4 (the cutting layer) is currently showing;
  - an L and an R circle in the band above the preview, lit when that stick
    is driving that camera, coloured by the stick's latched zoom direction
    (green = in, orange = out);
  - a fixed IN (top) / OUT (bottom) box pair next to each circle, so the
    zoom state reads from position as well as colour.

State comes from one place, the bridge: GET /api/ptz-overlay, polled on
localhost. The bridge works out the live camera from the Resolume OSC it
already relays (windows/ptz_overlay_host.py), and the stick state from the
ptz_visca engine. The bridge launches this process (`--ptz-overlay`) and
restarts it if it dies; it exits on its own when the bridge goes away.

The overlay is read-only: it never sends anything to the bridge, Resolume
or the cameras, so it cannot disturb the show path. If it crashes, nothing
else notices.

Show / hide: Ctrl+Alt+H toggles (hiding also locks, so an invisible
window can never swallow clicks). Every start comes up shown.

Lock / unlock: Ctrl+Alt+O toggles. Unlocked, the window takes the mouse:
drag inside to move, drag the handles to resize, click LOCK (or the hotkey)
to lock. Locked, every click passes straight through to Resolume. The box
is saved on lock and on every move/resize.

Windows only (ctypes Win32 + Pillow). Standalone: pythonw -m windows.ptz_overlay
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import http.client
import json
import logging
import argparse
import os
import sys
import threading
import time
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

LOGGER = logging.getLogger("ptz_overlay")

BRIDGE = ("127.0.0.1", 7723)
CUT_LAYER = 4
CAMERAS = (1, 2, 3)
BRIDGE_POLL_S = 0.15

# Default box (screen px): the three Layer Monitor images in Ben's RRU layout
# at 1920x1080, from the top of the indicator band to the bottom of the images.
DEFAULT_BOX = {"x": 21, "y": 517, "w": 1574, "h": 357}
MIN_W, MIN_H = 300, 120

# Reference geometry the drawing scales from (matches DEFAULT_BOX).
REF_W, REF_H = 1574.0, 357.0
REF_BAND = 80.0  # indicator band above the images
REF_GAP = 44.5  # gap between neighbouring previews
MARGIN = 34  # window margin around the box, room for the glow
TOOLBAR_H = 64  # space under the box for the unlocked toolbar

YEL = (255, 204, 0)
GRN = (34, 197, 94)
ORG = (255, 138, 0)
WHT = (255, 255, 255)
BLK = (10, 10, 10)
GRY = (72, 72, 72)
CYA = (0, 200, 255)

FONT_PATH = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arialbd.ttf")


def _state_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    d = Path(base) / "steamdeck-midi-overlay"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Shared state (poll threads write, UI thread reads)


class OverlayState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.bridge_ok = False
        self.ptz_active = False
        self.sticks = {"left": (None, "in"), "right": (None, "in")}
        self.live: int | None = None
        self.version = 0

    def snapshot(self) -> tuple:
        with self.lock:
            return (self.bridge_ok, self.ptz_active, dict(self.sticks), self.live)

    def update(self, **kw) -> None:
        with self.lock:
            changed = False
            for k, v in kw.items():
                if getattr(self, k) != v:
                    setattr(self, k, v)
                    changed = True
            if changed:
                self.version += 1


class JsonGetter:
    """Keep-alive GETs against one localhost server; reconnects on any error."""

    def __init__(self, host: str, port: int, timeout: float = 0.6) -> None:
        self.host, self.port, self.timeout = host, port, timeout
        self.conn: http.client.HTTPConnection | None = None

    def get(self, path: str):
        for attempt in (0, 1):
            try:
                if self.conn is None:
                    self.conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
                self.conn.request("GET", path)
                resp = self.conn.getresponse()
                body = resp.read()
                if resp.status != 200:
                    raise OSError(f"HTTP {resp.status} for {path}")
                return json.loads(body)
            except Exception:
                if self.conn is not None:
                    self.conn.close()
                self.conn = None
                if attempt:
                    raise


def poll_bridge(state: OverlayState, stop: threading.Event) -> None:
    api = JsonGetter(*BRIDGE)
    while not stop.is_set():
        try:
            st = api.get("/api/ptz-overlay")
            sticks = {}
            for g in ("left", "right"):
                stick = (st.get("sticks") or {}).get(g) or {}
                cam = stick.get("camera")
                sticks[g] = (int(cam) if cam is not None else None, str(stick.get("zoom", "in")))
            live = st.get("live_camera")
            state.update(bridge_ok=True, ptz_active=bool(st.get("visible")), sticks=sticks,
                         live=int(live) if live is not None else None)
        except Exception as exc:
            LOGGER.debug("bridge poll failed: %s", exc)
            state.update(bridge_ok=False)
        stop.wait(BRIDGE_POLL_S)


def parent_alive(pid: int) -> bool:
    handle = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if not handle:
        return False
    try:
        return kernel32.WaitForSingleObject(handle, 0) != 0  # 0 = exited
    finally:
        kernel32.CloseHandle(handle)


# ---------------------------------------------------------------------------
# Drawing


class Geometry:
    """Layout for a box of size (w, h), in box-local pixels."""

    def __init__(self, w: int, h: int) -> None:
        sx, sy = w / REF_W, h / REF_H
        self.k = min(sx, sy)
        self.band = REF_BAND * sy
        gap = REF_GAP * sx
        sw = (w - 2 * gap) / 3
        self.slots = {
            cam: (i * (sw + gap), self.band, i * (sw + gap) + sw, float(h))
            for i, cam in enumerate(CAMERAS)
        }


def _font(px: float) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(FONT_PATH, max(6, int(px)))
    except OSError:
        return ImageFont.load_default()


def render(win_w: int, win_h: int, box_w: int, box_h: int, snap: tuple, unlocked: bool) -> Image.Image:
    bridge_ok, ptz_active, sticks, live = snap
    show = unlocked or (bridge_ok and ptz_active)
    img = Image.new("RGBA", (win_w, win_h), (0, 0, 0, 1 if unlocked else 0))
    if not show:
        return img
    g = Geometry(box_w, box_h)
    k = g.k
    ox, oy = MARGIN, MARGIN

    def R(x0, y0, x1, y1):
        return [ox + x0, oy + y0, ox + x1, oy + y1]

    # Glow on the live preview (blurred, so a few px of misalignment is fine).
    if live in g.slots and not unlocked:
        x0, y0, x1, y1 = g.slots[live]
        glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.rounded_rectangle(R(x0 - 10 * k, y0 - 10 * k, x1 + 10 * k, y1 + 10 * k), radius=14 * k,
                             outline=YEL + (255,), width=max(2, int(10 * k)))
        glow = glow.filter(ImageFilter.GaussianBlur(9 * k))
        core = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(core).rounded_rectangle(R(x0 - 7 * k, y0 - 7 * k, x1 + 7 * k, y1 + 7 * k), radius=12 * k,
                                               outline=YEL + (200,), width=max(1, int(3 * k)))
        core = core.filter(ImageFilter.GaussianBlur(2 * k))
        img = Image.alpha_composite(img, glow)
        img = Image.alpha_composite(img, glow)
        img = Image.alpha_composite(img, core)

    # Crisp elements at 2x, downsampled for anti-aliasing.
    S = 2
    hi = Image.new("RGBA", (win_w * S, win_h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(hi)

    def s(*v):
        return [c * S for c in v]

    def F(px):
        return _font(px * k * S)

    for cam, (x0, y0, x1, y1) in g.slots.items():
        cy = oy + y0 - 52 * k
        r = 22 * k
        for side, group in (("L", "left"), ("R", "right")):
            stick_cam, zdir = sticks.get(group, (None, "in"))
            on = stick_cam == cam and not unlocked
            col = GRN if zdir == "in" else ORG
            cx = ox + (x0 + 24 * k if side == "L" else x1 - 24 * k)
            if on:
                d.ellipse(s(cx - r, cy - r, cx + r, cy + r), fill=col + (255,), outline=WHT + (255,), width=max(1, int(3 * k * S)))
                d.text(s(cx, cy), side, font=F(22), fill=BLK + (255,), anchor="mm")
            else:
                d.ellipse(s(cx - r, cy - r, cx + r, cy + r), fill=WHT + (18,), outline=WHT + (60,), width=max(1, int(2 * k * S)))
                d.text(s(cx, cy), side, font=F(22), fill=WHT + (80,), anchor="mm")
            bw = 46 * k
            bx = cx + r + 8 * k if side == "L" else cx - r - 8 * k - bw
            for lab, (t, b) in (("IN", (cy - 22 * k, cy - 1 * k)), ("OUT", (cy + 1 * k, cy + 22 * k))):
                lit = on and zdir == lab.lower()
                if lit:
                    fill, tc = col + (255,), BLK + (255,)
                elif on:
                    fill, tc = GRY + (255,), (150, 150, 150, 255)
                else:
                    fill, tc = GRY + (110,), (150, 150, 150, 90)
                d.rounded_rectangle(s(bx, t, bx + bw, b), radius=4 * k * S, fill=fill)
                d.text(s(bx + bw / 2, (t + b) / 2), lab, font=F(12), fill=tc, anchor="mm")
        if cam == live and not unlocked:
            mx = ox + (x0 + x1) / 2
            d.rounded_rectangle(s(mx - 62 * k, cy - 15 * k, mx + 62 * k, cy + 15 * k), radius=15 * k * S, fill=YEL + (255,))
            d.text(s(mx, cy), f"LIVE  CAM {cam}", font=F(15), fill=BLK + (255,), anchor="mm")

    if unlocked:
        bx0, by0, bx1, by1 = ox, oy, ox + box_w, oy + box_h
        d.rectangle(s(bx0, by0, bx1, by1), fill=CYA + (40,))
        _dashed(d, s(bx0, by0, bx1, by1), CYA + (255,), 2 * S, 10 * S, 7 * S)
        for cam, (x0, y0, x1, y1) in g.slots.items():
            _dashed(d, s(ox + x0, oy + y0, ox + x1, oy + y1), WHT + (140,), S, 6 * S, 6 * S)
            d.text(s(ox + (x0 + x1) / 2, oy + (y0 + y1) / 2), f"CAM {cam}", font=_font(30 * S), fill=WHT + (170,), anchor="mm")
        for hx, hy in _handles(box_w, box_h):
            d.rectangle(s(hx - 7, hy - 7, hx + 7, hy + 7), fill=WHT + (255,), outline=CYA + (255,), width=2 * S)
        tb = toolbar_rect(win_w, box_h)
        lk = lock_button_rect(win_w, box_h)
        d.rounded_rectangle(s(*tb), radius=23 * S, fill=(20, 28, 34, 240), outline=CYA + (255,), width=2 * S)
        d.text(s(tb[0] + 26, (tb[1] + tb[3]) / 2), "UNLOCKED", font=_font(16 * S), fill=CYA + (255,), anchor="lm")
        d.text(s(tb[0] + 126, (tb[1] + tb[3]) / 2), "drag to move, handles to resize, Ctrl+Alt+O", font=_font(13 * S), fill=WHT + (220,), anchor="lm")
        d.rounded_rectangle(s(*lk), radius=15 * S, fill=CYA + (255,))
        d.text(s((lk[0] + lk[2]) / 2, (lk[1] + lk[3]) / 2), "LOCK", font=_font(15 * S), fill=BLK + (255,), anchor="mm")

    hi = hi.resize((win_w, win_h), Image.LANCZOS)
    return Image.alpha_composite(img, hi)


def _dashed(d, r, col, w, dash, gap):
    x0, y0, x1, y1 = r
    for ax, ay, bx, by in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)):
        length = max(abs(bx - ax), abs(by - ay))
        t = 0.0
        while t < length:
            e = min(t + dash, length)
            d.line([ax + (bx - ax) * t / length, ay + (by - ay) * t / length,
                    ax + (bx - ax) * e / length, ay + (by - ay) * e / length], fill=col, width=int(w))
            t = e + gap


def _handles(box_w, box_h):
    xs = (MARGIN, MARGIN + box_w / 2, MARGIN + box_w)
    ys = (MARGIN, MARGIN + box_h / 2, MARGIN + box_h)
    return [(x, y) for x in xs for y in ys if not (x == xs[1] and y == ys[1])]


def toolbar_rect(win_w, box_h):
    cx = win_w / 2
    top = MARGIN + box_h + 14
    return (cx - 300, top, cx + 300, top + 44)


def lock_button_rect(win_w, box_h):
    x0, y0, x1, y1 = toolbar_rect(win_w, box_h)
    return (x1 - 108, y0 + 7, x1 - 8, y1 - 7)


# ---------------------------------------------------------------------------
# Win32 window


user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

WS_POPUP = 0x80000000
WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOPMOST = 0x80000, 0x20, 0x8
WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x80, 0x08000000
GWL_EXSTYLE = -20
WM_DESTROY, WM_CLOSE, WM_NCHITTEST, WM_LBUTTONUP = 0x0002, 0x0010, 0x0084, 0x0202
WM_WINDOWPOSCHANGED, WM_EXITSIZEMOVE, WM_TIMER, WM_HOTKEY = 0x0047, 0x0232, 0x0113, 0x0312
WM_GETMINMAXINFO = 0x0024
HTCLIENT, HTCAPTION, HTTRANSPARENT = 1, 2, -1
HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT, HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 10, 11, 12, 13, 14, 15, 16, 17
MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x1, 0x2, 0x4000
HWND_TOPMOST = wt.HWND(-1)
SWP_NOMOVE, SWP_NOSIZE, SWP_NOACTIVATE, SWP_FRAMECHANGED = 0x2, 0x1, 0x10, 0x20
ULW_ALPHA = 2


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("style", wt.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE),
                ("hIcon", wt.HICON), ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH),
                ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR), ("hIconSm", wt.HICON)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_byte), ("BlendFlags", ctypes.c_byte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_byte)]


class MINMAXINFO(ctypes.Structure):
    _fields_ = [("ptReserved", wt.POINT), ("ptMaxSize", wt.POINT), ("ptMaxPosition", wt.POINT),
                ("ptMinTrackSize", wt.POINT), ("ptMaxTrackSize", wt.POINT)]


user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
user32.CreateWindowExW.restype = wt.HWND
user32.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
user32.UpdateLayeredWindow.argtypes = [wt.HWND, wt.HDC, ctypes.POINTER(wt.POINT), ctypes.POINTER(wt.SIZE), wt.HDC,
                                       ctypes.POINTER(wt.POINT), wt.COLORREF, ctypes.POINTER(BLENDFUNCTION), wt.DWORD]
user32.GetDC.argtypes = [wt.HWND]
user32.GetDC.restype = wt.HDC
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.LoadCursorW.argtypes = [wt.HINSTANCE, wt.LPVOID]
user32.LoadCursorW.restype = wt.HANDLE
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateDIBSection.argtypes = [wt.HDC, ctypes.c_void_p, wt.UINT, ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD]
gdi32.CreateDIBSection.restype = wt.HBITMAP
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wt.HDC]
kernel32.GetModuleHandleW.restype = wt.HMODULE
kernel32.CreateMutexW.restype = wt.HANDLE
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
kernel32.CloseHandle.argtypes = [wt.HANDLE]


def _premultiplied_bgra(img: Image.Image) -> bytes:
    r, g, b, a = img.split()
    r, g, b = (ImageChops.multiply(c, a) for c in (r, g, b))
    return Image.merge("RGBA", (b, g, r, a)).tobytes()


class OverlayWindow:
    def __init__(self, state: OverlayState) -> None:
        self.state = state
        self.cfg_path = _state_dir() / "overlay.json"
        self.box = dict(DEFAULT_BOX)
        self.locked = True
        self.hidden = False
        self.parent_pid = 0
        self._load()
        self.rendered_version = -1
        self.rendered_key = None
        self.hwnd = None
        self._wndproc = WNDPROC(self._proc)

    # -- persistence
    def _load(self) -> None:
        try:
            data = json.loads(self.cfg_path.read_text(encoding="utf-8"))
            box = data.get("box", {})
            if all(isinstance(box.get(k), (int, float)) for k in ("x", "y", "w", "h")):
                self.box = {k: int(box[k]) for k in ("x", "y", "w", "h")}
        except (OSError, ValueError):
            pass

    def _save(self) -> None:
        tmp = self.cfg_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"box": self.box}, indent=2), encoding="utf-8")
        os.replace(tmp, self.cfg_path)

    # -- geometry
    def win_rect(self):
        b = self.box
        return (b["x"] - MARGIN, b["y"] - MARGIN, b["w"] + 2 * MARGIN, b["h"] + 2 * MARGIN + TOOLBAR_H)

    def _box_from_window(self) -> None:
        rc = wt.RECT()
        user32.GetWindowRect(self.hwnd, ctypes.byref(rc))
        w = max(MIN_W, rc.right - rc.left - 2 * MARGIN)
        h = max(MIN_H, rc.bottom - rc.top - 2 * MARGIN - TOOLBAR_H)
        self.box = {"x": rc.left + MARGIN, "y": rc.top + MARGIN, "w": w, "h": h}

    # -- window
    def create(self) -> None:
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = hinst
        wc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(32512))
        wc.lpszClassName = "SteamDeckMidiPtzOverlay"
        user32.RegisterClassExW(ctypes.byref(wc))
        x, y, w, h = self.win_rect()
        ex = WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT
        self.hwnd = user32.CreateWindowExW(ex, wc.lpszClassName, "PTZ Overlay", WS_POPUP, x, y, w, h,
                                           None, None, hinst, None)
        if not self.hwnd:
            raise OSError(f"CreateWindowExW failed: {ctypes.get_last_error()}")
        for hk_id, key in ((1, "O"), (2, "H")):
            if not user32.RegisterHotKey(self.hwnd, hk_id, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord(key)):
                LOGGER.warning("Ctrl+Alt+%s hotkey unavailable (error %s)", key, ctypes.get_last_error())
        user32.SetTimer(self.hwnd, 1, 50, None)
        user32.SetTimer(self.hwnd, 2, 2000, None)
        self.redraw(force=True)
        user32.ShowWindow(self.hwnd, 4)  # SW_SHOWNOACTIVATE

    def set_locked(self, locked: bool) -> None:
        self.locked = locked
        ex = user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE)
        if locked:
            ex |= WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
        else:
            ex &= ~(WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
        user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, ex)
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED)
        if locked:
            self._save()
        LOGGER.info("overlay %s; box=%s", "locked" if locked else "unlocked", self.box)
        self.redraw(force=True)

    def redraw(self, force: bool = False) -> None:
        version = self.state.version
        x, y, w, h = self.win_rect()
        key = (w, h, self.locked, self.hidden)
        if not force and version == self.rendered_version and key == self.rendered_key:
            return
        self.rendered_version, self.rendered_key = version, key
        if self.hidden:
            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        else:
            img = render(w, h, self.box["w"], self.box["h"], self.state.snapshot(), unlocked=not self.locked)
        self._blit(img, x, y)

    def _blit(self, img: Image.Image, x: int, y: int) -> None:
        w, h = img.size
        screen = user32.GetDC(None)
        mem = gdi32.CreateCompatibleDC(screen)
        bmi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        bits = ctypes.c_void_p()
        dib = gdi32.CreateDIBSection(screen, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        try:
            data = _premultiplied_bgra(img)
            ctypes.memmove(bits, data, len(data))
            old = gdi32.SelectObject(mem, dib)
            blend = BLENDFUNCTION(0, 0, 255, 1)
            user32.UpdateLayeredWindow(self.hwnd, screen, ctypes.byref(wt.POINT(x, y)), ctypes.byref(wt.SIZE(w, h)),
                                       mem, ctypes.byref(wt.POINT(0, 0)), 0, ctypes.byref(blend), ULW_ALPHA)
            gdi32.SelectObject(mem, old)
        finally:
            gdi32.DeleteObject(dib)
            gdi32.DeleteDC(mem)
            user32.ReleaseDC(None, screen)

    def _hit(self, sx: int, sy: int) -> int:
        rc = wt.RECT()
        user32.GetWindowRect(self.hwnd, ctypes.byref(rc))
        x, y = sx - rc.left, sy - rc.top
        bw, bh = self.box["w"], self.box["h"]
        lk = lock_button_rect(rc.right - rc.left, bh)
        if lk[0] <= x <= lk[2] and lk[1] <= y <= lk[3]:
            return HTCLIENT
        g = 10
        left, right = abs(x - MARGIN) <= g, abs(x - (MARGIN + bw)) <= g
        top, bottom = abs(y - MARGIN) <= g, abs(y - (MARGIN + bh)) <= g
        inside_x = MARGIN - g <= x <= MARGIN + bw + g
        inside_y = MARGIN - g <= y <= MARGIN + bh + g
        if top and left: return HTTOPLEFT
        if top and right: return HTTOPRIGHT
        if bottom and left: return HTBOTTOMLEFT
        if bottom and right: return HTBOTTOMRIGHT
        if left and inside_y: return HTLEFT
        if right and inside_y: return HTRIGHT
        if top and inside_x: return HTTOP
        if bottom and inside_x: return HTBOTTOM
        if inside_x and inside_y: return HTCAPTION
        return HTTRANSPARENT

    def _proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_TIMER:
                if wparam == 1:
                    self.redraw()
                else:
                    if self.parent_pid and not parent_alive(self.parent_pid):
                        LOGGER.info("bridge (pid %s) is gone; overlay exiting", self.parent_pid)
                        user32.DestroyWindow(hwnd)
                        return 0
                    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
                return 0
            if msg == WM_HOTKEY:
                if wparam == 2:
                    if not self.locked:
                        self.set_locked(True)
                    self.hidden = not self.hidden
                    LOGGER.info("overlay %s", "hidden" if self.hidden else "shown")
                    self.redraw(force=True)
                elif not self.hidden:
                    self.set_locked(not self.locked)
                return 0
            if msg == WM_NCHITTEST and not self.locked:
                sx = ctypes.c_short(lparam & 0xFFFF).value
                sy = ctypes.c_short((lparam >> 16) & 0xFFFF).value
                return self._hit(sx, sy)
            if msg == WM_LBUTTONUP and not self.locked:
                x = ctypes.c_short(lparam & 0xFFFF).value
                y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
                rc = wt.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rc))
                lk = lock_button_rect(rc.right - rc.left, self.box["h"])
                if lk[0] <= x <= lk[2] and lk[1] <= y <= lk[3]:
                    self.set_locked(True)
                return 0
            if msg == WM_GETMINMAXINFO:
                mmi = ctypes.cast(lparam, ctypes.POINTER(MINMAXINFO)).contents
                mmi.ptMinTrackSize.x = MIN_W + 2 * MARGIN
                mmi.ptMinTrackSize.y = MIN_H + 2 * MARGIN + TOOLBAR_H
                return 0
            if msg == WM_WINDOWPOSCHANGED and self.hwnd and not self.locked:
                self._box_from_window()
                self.redraw()
            if msg == WM_EXITSIZEMOVE:
                self._box_from_window()
                self._save()
                self.redraw(force=True)
                return 0
            if msg == WM_CLOSE:
                user32.DestroyWindow(hwnd)
                return 0
            if msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
        except Exception:
            LOGGER.exception("window proc error (msg 0x%x)", msg)
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def main(argv: "list[str] | None" = None) -> int:
    global BRIDGE
    parser = argparse.ArgumentParser(description="PTZ camera overlay")
    parser.add_argument("--ptz-overlay", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--parent-pid", type=int, default=0, help="exit when this process exits")
    parser.add_argument("--bridge-port", type=int, default=BRIDGE[1], help="bridge web UI port")
    args, _unknown = parser.parse_known_args(argv)
    BRIDGE = (BRIDGE[0], args.bridge_port)
    log_path = _state_dir() / "overlay.log"
    logging.basicConfig(filename=str(log_path), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    mutex = kernel32.CreateMutexW(None, False, "Local\\SteamDeckMidiPtzOverlay")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        LOGGER.info("another overlay is running; exiting")
        return 0
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
    except (OSError, AttributeError):
        user32.SetProcessDPIAware()

    state = OverlayState()
    stop = threading.Event()
    for target in (poll_bridge,):
        threading.Thread(target=target, args=(state, stop), daemon=True, name=target.__name__).start()

    win = OverlayWindow(state)
    win.parent_pid = args.parent_pid
    win.create()
    LOGGER.info("overlay started; box=%s; Ctrl+Alt+O toggles lock", win.box)
    msg = wt.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    stop.set()
    del mutex
    return 0


if __name__ == "__main__":
    sys.exit(main())
