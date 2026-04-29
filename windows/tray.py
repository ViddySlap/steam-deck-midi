"""System tray icon for the Steam Deck MIDI receiver."""

from __future__ import annotations

import threading
import webbrowser
from typing import Callable

import pystray
from PIL import Image, ImageDraw


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


class ReceiverTray:
    def __init__(
        self,
        ui_url: str,
        quit_callback: Callable[[], None],
    ) -> None:
        self._ui_url = ui_url
        self._quit_callback = quit_callback
        self._icon: pystray.Icon | None = None

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
            icon=_make_icon_image(),
            title="Steam Deck MIDI",
            menu=menu,
        )
        t = threading.Thread(target=self._icon.run, daemon=True, name="tray")
        t.start()
        return t

    def stop(self) -> None:
        if self._icon is not None:
            self._icon.stop()
