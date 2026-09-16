"""Receiver-side button decoding from the Deck's raw HID state (ADR 0003).

The Deck sends raw controller state (`ButtonStateEvent`); this module does
everything Steam Input used to do for buttons: bit decoding, the two latching
action layers, trigger soft/full pulls, pressure-based trackpad clicks and
long press. It emits the same Action IDs the Steam Input path produced, so
presets, engines, Resolume and TouchOSC see no difference.

Spec: Projects/steam-deck-midi/specs/hidraw-buttons-receiver.md. Bit positions
and every threshold default come from wiki/reference/hidraw-button-bits.md.

Timing rule: hold durations use the Deck's clock (`deck_ms`), never arrival
time, so a receive stall can delay a long press but cannot turn a tap into one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from protocol.messages import ButtonStateEvent

DecodedEvent = tuple[str, str]  # (action, "down" | "up")

# Physical input -> (HID report byte offset, mask). The datagram carries
# report bytes 8-15, so the index into ButtonStateEvent.buttons is offset - 8.
# Order is the press-emission order when several inputs change in one report.
BUTTON_BITS: dict[str, tuple[int, int]] = {
    "A": (8, 0x80),
    "B": (8, 0x20),
    "X": (8, 0x40),
    "Y": (8, 0x10),
    "L1": (8, 0x08),
    "R1": (8, 0x04),
    "L2_FULL": (8, 0x02),
    "R2_FULL": (8, 0x01),
    "DPAD_UP": (9, 0x01),
    "DPAD_DOWN": (9, 0x08),
    "DPAD_LEFT": (9, 0x04),
    "DPAD_RIGHT": (9, 0x02),
    "VIEW": (9, 0x10),  # left menu button (two squares); bit-table "SELECT"
    "MENU": (9, 0x40),  # right menu button (three lines); bit-table "START"
    "L5": (9, 0x80),
    "R5": (10, 0x01),
    "L3": (10, 0x40),
    "R3": (11, 0x04),
    "L4": (13, 0x02),
    "R4": (13, 0x04),
    "LEFT_STICK_TOUCH": (13, 0x40),
    "RIGHT_STICK_TOUCH": (13, 0x80),
    "QAM": (14, 0x04),
}

# Inputs that never change with a layer and never long-press.
# The menu buttons keep Steam Input's swapped names: the left button has
# always emitted START and the right one SELECT (steam-input-layers.md).
PLAIN_ACTIONS: dict[str, str] = {
    "VIEW": "START",
    "MENU": "SELECT",
    "L3": "LEFT_STICK_CLICK_L3",
    "R3": "RIGHT_STICK_CLICK_R3",
    "L4": "L4",
    "L5": "L5",
    "R4": "R4",
    "R5": "R5",
    "QAM": "QAM",
    "LEFT_STICK_TOUCH": "LEFT_STICK_TOUCH",
    "RIGHT_STICK_TOUCH": "RIGHT_STICK_TOUCH",
}
ABXY_ACTIONS: dict[str, str] = {"A": "BTN_A", "B": "BTN_B", "X": "BTN_X", "Y": "BTN_Y"}
BUMPER_ACTIONS: dict[str, str] = {
    "L1": "L1",
    "R1": "R1",
    "L2_SOFT": "L2_SOFT",
    "L2_FULL": "L2_FULL",
    "R2_SOFT": "R2_SOFT",
    "R2_FULL": "R2_FULL",
}
# Inputs that long-press when the active preset maps `<action>_LONG_PRESS`.
LONG_PRESS_ACTIONS: dict[str, str] = {
    "DPAD_UP": "DPAD_UP",
    "DPAD_DOWN": "DPAD_DOWN",
    "DPAD_LEFT": "DPAD_LEFT",
    "DPAD_RIGHT": "DPAD_RIGHT",
}
LAYER_SUFFIX = "_LAYER_2"
LONG_PRESS_SUFFIX = "_LONG_PRESS"

LAYER_TOGGLES = {"VIEW": "abxy", "MENU": "bumper"}


@dataclass(frozen=True)
class RawButtonConfig:
    long_press_ms: int = 500
    # No state for this long while anything is held -> release it all.
    stale_release_seconds: float = 0.5
    # Measured 2026-09-16: resting thumb <= 1,478, lowest real click 3,271.
    pad_click_on: int = 2500
    pad_click_off: int = 1500
    trigger_soft_on: int = 5000
    trigger_soft_off: int = 4000
    # The right pad is Ben's mouse; its state is carried but not mapped.
    right_pad_clicks: bool = False


@dataclass
class _Held:
    action: str
    long_action: str | None  # None: plain, emitted on press
    down_ms: int
    long_fired: bool = False


class RawButtonDecoder:
    def __init__(self, config: RawButtonConfig | None = None) -> None:
        self.config = config or RawButtonConfig()
        self.abxy_layer = False
        self.bumper_layer = False
        self.active = False  # True once any raw state has arrived
        self._held: dict[str, _Held] = {}
        self._analog_on: dict[str, bool] = {}
        self._last_state_at: float | None = None

    @property
    def layers(self) -> tuple[bool, bool]:
        return self.abxy_layer, self.bumper_layer

    def feed(
        self,
        event: ButtonStateEvent,
        now: float,
        has_mapping: Callable[[str], bool],
    ) -> list[DecodedEvent]:
        self.active = True
        self._last_state_at = now
        pressed = self._pressed_inputs(event)
        out: list[DecodedEvent] = []
        for name in [n for n in self._held if n not in pressed]:
            out.extend(self._release(name))
        for name in pressed:
            if name not in self._held:
                out.extend(self._press(name, event, has_mapping))
        for held in self._held.values():
            if (
                held.long_action is not None
                and not held.long_fired
                and event.deck_ms - held.down_ms >= self.config.long_press_ms
            ):
                held.long_fired = True
                out.append((held.long_action, "down"))
        return out

    def check_stale(self, now: float) -> list[DecodedEvent]:
        if self._last_state_at is None or not (self._held or any(self._analog_on.values())):
            return []
        if now - self._last_state_at < self.config.stale_release_seconds:
            return []
        out: list[DecodedEvent] = []
        for held in self._held.values():
            if held.long_action is None:
                out.append((held.action, "up"))
            elif held.long_fired:
                out.append((held.long_action, "up"))
        self._held.clear()
        self._analog_on.clear()
        return out

    def _pressed_inputs(self, event: ButtonStateEvent) -> list[str]:
        pressed = [
            name
            for name, (offset, mask) in BUTTON_BITS.items()
            if event.buttons[offset - 8] & mask
        ]
        cfg = self.config
        if self._hysteresis("L2_SOFT", event.left_trigger, cfg.trigger_soft_on, cfg.trigger_soft_off):
            pressed.append("L2_SOFT")
        if self._hysteresis("R2_SOFT", event.right_trigger, cfg.trigger_soft_on, cfg.trigger_soft_off):
            pressed.append("R2_SOFT")
        if self._hysteresis("LPAD", event.left_pad_pressure, cfg.pad_click_on, cfg.pad_click_off):
            pressed.append("LPAD")
        if cfg.right_pad_clicks and self._hysteresis(
            "RPAD", event.right_pad_pressure, cfg.pad_click_on, cfg.pad_click_off
        ):
            pressed.append("RPAD")
        return pressed

    def _hysteresis(self, name: str, value: int, on: int, off: int) -> bool:
        state = self._analog_on.get(name, False)
        state = value >= off if state else value >= on
        self._analog_on[name] = state
        return state

    def _press(
        self,
        name: str,
        event: ButtonStateEvent,
        has_mapping: Callable[[str], bool],
    ) -> list[DecodedEvent]:
        action = self._resolve(name, event)
        long_capable = name in LONG_PRESS_ACTIONS or name in ("LPAD", "RPAD")
        long_action = action + LONG_PRESS_SUFFIX
        if long_capable and has_mapping(long_action):
            self._held[name] = _Held(action, long_action, event.deck_ms)
            return []
        self._held[name] = _Held(action, None, event.deck_ms)
        toggle = LAYER_TOGGLES.get(name)
        if toggle == "abxy":
            self.abxy_layer = not self.abxy_layer
        elif toggle == "bumper":
            self.bumper_layer = not self.bumper_layer
        return [(action, "down")]

    def _release(self, name: str) -> list[DecodedEvent]:
        held = self._held.pop(name)
        if held.long_action is None:
            return [(held.action, "up")]
        if held.long_fired:
            return [(held.long_action, "up")]
        return [(held.action, "down"), (held.action, "up")]

    def _resolve(self, name: str, event: ButtonStateEvent) -> str:
        """Pick the action at press time; a hold keeps it even if a layer flips."""
        if name in PLAIN_ACTIONS:
            return PLAIN_ACTIONS[name]
        if name in ABXY_ACTIONS:
            return ABXY_ACTIONS[name] + (LAYER_SUFFIX if self.abxy_layer else "")
        if name in BUMPER_ACTIONS:
            return BUMPER_ACTIONS[name] + (LAYER_SUFFIX if self.bumper_layer else "")
        if name in LONG_PRESS_ACTIONS:
            return LONG_PRESS_ACTIONS[name]
        # Trackpads are halves: the side the thumb leans toward at click onset.
        if name == "LPAD":
            return "L_PAD_RIGHT" if event.left_pad_x >= 0 else "L_PAD_LEFT"
        if name == "RPAD":
            return "R_PAD_RIGHT" if event.right_pad_x >= 0 else "R_PAD_LEFT"
        raise KeyError(name)
