"""NestDrop queue-advance engine (v0.4.4).

Maps Steam Deck buttons to NestDrop queue advances. Each configured
"button" pairs (a) one or more MIDI note numbers with (b) the OSC path
of a NestDrop queue and (c) the NestDrop deck that queue feeds. Pressing
the button activates that queue and fires `btSpace` on the target deck.

Default factory mapping (v0.4.4):

| Button       | Notes (ch 0) | NestDrop queue   | NestDrop deck |
|--------------|--------------|------------------|---------------|
| `x`          | 40, 41       | Queue1           | Deck 1        |
| `b`          | 38, 39       | Queue2           | Deck 1        |
| `lpad_up`    | 88           | Queue3 (chill)   | Deck 2        |
| `lpad_down`  | 89           | Queue4 (aggro)   | Deck 2        |

Notes 40+41 / 38+39 are the same physical button (X/B) on the two
SteamInput layers (CHASER/FLASH). Both are treated as the same logical
press.

## Press model

- **Immediate-fire on every press.** Each press triggers the queue's
  advance immediately so Resolume's flash visualises the new preset
  within ~`activate_delay_seconds` (~100ms by default).
- **Same-button cooldown.** If the SAME button is pressed again within
  `fade_window_seconds` of its last press (advance OR skip), the engine
  skips the advance. Every press extends the cooldown so sustained
  rapid tapping of one button never advances past the first press
  until idle for fade_window_seconds.
- **Cross-button always fires.** Pressing a different button resets the
  "last press button" tracker, so the next press of the original button
  also fires fresh.

OSC sequence per advance (2 messages, ~activate_delay_seconds apart):

1. `<button.queue_path> INT32(1)` — activate the queue
2. `/Controls/Deck<button.target_deck>/btSpace INT32(1)` — advance it

Spec: specs/nestdrop-integration.md

Bridge stays stateless: NestDrop owns each queue's current preset and
shuffle state. Bridge only tracks the last-pressed button + timestamp
for cooldown gating.

NestDrop OSC Input must be enabled in NestDrop UI for any of this to work.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from windows.engines._nestdrop_coordinator import fire_queue_advance
from windows.engines.base import Engine
from windows.engines.osc_client import OscClient
from windows.midi import MidiOut

LOGGER = logging.getLogger(__name__)

DEFAULT_CHANNEL = 0
DEFAULT_FADE_WINDOW_SECONDS = 1.25
DEFAULT_OSC_HOST = "127.0.0.1"
DEFAULT_OSC_PORT = 8000
DEFAULT_BTSPACE_PATH_TEMPLATE = "/Controls/Deck{deck}/btSpace"
DEFAULT_ACTIVATE_DELAY_SECONDS = 0.1

DEFAULT_BUTTONS: dict[str, dict[str, Any]] = {
    "x":         {"notes": [40, 41], "queue_path": "/Queue/Queue1", "target_deck": 1},
    "b":         {"notes": [38, 39], "queue_path": "/Queue/Queue2", "target_deck": 1},
    "lpad_up":   {"notes": [88],     "queue_path": "/Queue/Queue3", "target_deck": 2, "fade_window_seconds": 0},
    "lpad_down": {"notes": [89],     "queue_path": "/Queue/Queue4", "target_deck": 2, "fade_window_seconds": 0},
}


@dataclass
class ButtonState:
    name: str
    notes: frozenset[int]
    queue_path: str
    target_deck: int
    btspace_path: str
    fade_window: float = DEFAULT_FADE_WINDOW_SECONDS
    # Other queues assigned to the same deck. The engine deactivates
    # them before activating its own queue so NestDrop's btSpace
    # advances OUR queue rather than a stale-active sibling.
    deactivate_siblings: tuple[str, ...] = ()
    advance_count: int = 0
    skip_count: int = 0
    press_count: int = 0


class NestdropEngine(Engine):
    type_name = "nestdrop"

    def __init__(
        self,
        name: str,
        config: dict,
        midi_out: MidiOut,
        *,
        clock: Callable[[], float] = time.monotonic,
        osc_client: OscClient | None = None,
        sleep: Callable[[float], None] = time.sleep,
        spawn: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        super().__init__(name, config, midi_out, clock=clock)

        self._channel = int(config.get("channel", DEFAULT_CHANNEL))
        self._fade_window = float(
            config.get("fade_window_seconds", DEFAULT_FADE_WINDOW_SECONDS)
        )
        self._activate_delay = float(
            config.get("activate_delay_seconds", DEFAULT_ACTIVATE_DELAY_SECONDS)
        )

        osc_cfg = config.get("osc", {})
        self._osc = osc_client or OscClient(
            host=str(osc_cfg.get("host", DEFAULT_OSC_HOST)),
            port=int(osc_cfg.get("port", DEFAULT_OSC_PORT)),
        )

        self._btspace_template = str(
            config.get("btspace_path_template", DEFAULT_BTSPACE_PATH_TEMPLATE)
        )

        # Buttons can be configured as a nested dict; fall back to defaults
        # for keys the user didn't override (partial overrides supported).
        buttons_cfg = config.get("buttons", DEFAULT_BUTTONS)
        self._buttons: dict[str, ButtonState] = {}
        self._note_lookup: dict[int, str] = {}
        for btn_name, btn_cfg in buttons_cfg.items():
            notes = frozenset(int(n) for n in btn_cfg.get("notes", ()))
            if not notes:
                LOGGER.warning(
                    "%s: button %r has no notes; ignoring", self.name, btn_name
                )
                continue
            target_deck = int(btn_cfg.get("target_deck", 1))
            # Per-button fade_window override; 0 disables cooldown entirely
            # (every press fires). Defaults to the engine-global setting.
            btn_fade_window = float(
                btn_cfg.get("fade_window_seconds", self._fade_window)
            )
            deactivate_siblings = tuple(
                str(p) for p in btn_cfg.get("deactivate_siblings", ())
            )
            state = ButtonState(
                name=btn_name,
                notes=notes,
                queue_path=str(btn_cfg["queue_path"]),
                target_deck=target_deck,
                btspace_path=self._btspace_template.format(deck=target_deck),
                fade_window=btn_fade_window,
                deactivate_siblings=deactivate_siblings,
            )
            self._buttons[btn_name] = state
            for note in notes:
                if note in self._note_lookup:
                    LOGGER.warning(
                        "%s: note %d already mapped to %r; %r overrides",
                        self.name,
                        note,
                        self._note_lookup[note],
                        btn_name,
                    )
                self._note_lookup[note] = btn_name

        # Tracks the last *press* (fired or skipped), not the last advance.
        # Every press extends the cooldown.
        self._last_press_button: str | None = None
        self._last_press_time: float = float("-inf")

        self._sleep = sleep
        self._spawn = spawn or (
            lambda fn: threading.Thread(target=fn, daemon=True).start()
        )
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle

    def shutdown(self) -> None:
        try:
            self._osc.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # MIDI input

    def on_note_in(self, channel: int, note: int, velocity: int, now: float) -> None:
        if channel != self._channel or velocity == 0:
            return
        button = self._note_lookup.get(note)
        if button is not None:
            self._handle_press(button, now)

    # ------------------------------------------------------------------
    # Press handling

    def _handle_press(self, button: str, now: float) -> None:
        state = self._buttons.get(button)
        if state is None:
            return
        with self._lock:
            state.press_count += 1
            same_button_recent = (
                self._last_press_button == button
                and state.fade_window > 0
                and now - self._last_press_time < state.fade_window
            )
            # Update tracker BEFORE deciding so the next press sees this
            # one's timestamp regardless of fire/skip outcome.
            self._last_press_button = button
            self._last_press_time = now

            if same_button_recent:
                state.skip_count += 1
                LOGGER.info(
                    "%s: %s re-press within fade window; not advancing",
                    self.name,
                    button,
                )
                return
            state.advance_count += 1
        # OSC sends run outside the lock and (by default) on a daemon
        # thread so the activate_delay sleep doesn't block the receive loop.
        self._spawn(lambda: self._fire_osc(button))

    def _fire_osc(self, button: str) -> None:
        state = self._buttons.get(button)
        if state is None:
            return
        try:
            # Use the shared coordinator so this activate+btSpace pair
            # doesn't race against gyro_feedback (or any future engine)
            # firing the same pattern on the same deck. Also deactivates
            # sibling queues on this deck so the btSpace lands on our
            # queue, not a stale-active sibling.
            fire_queue_advance(
                self._osc.send,
                state.queue_path,
                state.btspace_path,
                self._activate_delay,
                self._sleep,
                deactivate_paths=state.deactivate_siblings,
            )
        except Exception:
            LOGGER.exception("%s: OSC advance send failed for %s", self.name, button)
            return
        LOGGER.info(
            "%s: %s advance (%s -> %s)",
            self.name,
            button,
            state.queue_path,
            state.btspace_path,
        )

    # ------------------------------------------------------------------
    # Status

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type_name,
            "fade_window_seconds": self._fade_window,
            "activate_delay_seconds": self._activate_delay,
            "last_press_button": self._last_press_button,
            "buttons": [
                {
                    "button": s.name,
                    "notes": sorted(s.notes),
                    "queue_path": s.queue_path,
                    "target_deck": s.target_deck,
                    "btspace_path": s.btspace_path,
                    "fade_window_seconds": s.fade_window,
                    "advance_count": s.advance_count,
                    "skip_count": s.skip_count,
                    "press_count": s.press_count,
                }
                for s in self._buttons.values()
            ],
        }
