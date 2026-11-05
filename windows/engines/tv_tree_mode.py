"""TV TREE mode engine: R3 swaps part of the Deck onto a Christmas look.

A "look" is a Wire source patch on a Resolume clip whose dashboard links
carry fixed slot jobs (see Projects/steam-deck-midi/tv-tree/spec.md and
ADR 0004). Arena maps this engine's CCs once, to
`/composition/selectedclip/dashboard/link1..8`, so whichever look is
selected answers the Deck.

R3 (`RIGHT_STICK_CLICK_R3`) toggles the mode. The TV TREE preset leaves R3
unmapped, so the toggle never reaches Resolume as a note. While the mode
is ON:

  R5 tap         -> link 1 BLACKOUT toggles
  R4 hold        -> link 1 BLACKOUT while held (momentary)
  Y / A / X / B  -> links 2-5 CHASE UP / DOWN / AROUND / TV (127 down, 0 up)
  left stick X/Y -> links 6-7 BALL X / BALL Y (centred, 64 = middle)
  gyro pitch     -> link 8 SPIN SPEED (tilt up/down; 64 = stopped, rest speed + tilt)

and the preset's own notes for ABXY, R4 and R5 are dropped (note-emit
filter), the left-stick layer engine and the gyro engine are paused so
the stick and gyro do only tree jobs. Everything else (L2/R2 flashes,
bumpers, pads) keeps its preset behaviour. With the mode OFF the engine
emits nothing and filters nothing, so the Deck behaves like EDM Show.

Gyro: GYRO_* axis values are an orientation accumulator (see
gyro_feedback), so the tilt from the pose at mode entry drives speed.

Mode state is published as a CC (`mode_cc`, 127 on / 0 off) for a
TouchOSC or STATE TRACKER indicator.
"""

from __future__ import annotations

import logging
from typing import Callable

from windows.engines.base import Engine
from windows.midi import MidiOut
from windows.clock import now as clock_now

LOGGER = logging.getLogger(__name__)

LAYER_SUFFIX = "_LAYER_2"
STICK_X = "L_STICK_X_AXIS"
STICK_Y = "L_STICK_Y_AXIS"

_DEFAULT_LINKS = {
    "blackout": 1,
    "chase_up": 2,
    "chase_down": 3,
    "chase_around": 4,
    "chase_tv": 5,
    "ball_x": 6,
    "ball_y": 7,
    "spin": 8,
}
_DEFAULT_CHASE_BUTTONS = {
    "BTN_Y": "chase_up",
    "BTN_A": "chase_down",
    "BTN_X": "chase_around",
    "BTN_B": "chase_tv",
}
# EDM Show notes on ch0 that the mode takes over: ABXY (both ABXY layers), R4, R5.
_DEFAULT_SUPPRESS_NOTES = [36, 37, 38, 39, 40, 41, 42, 43, 76, 77]


class TvTreeModeEngine(Engine):
    """Toggle (R3) between the preset's behaviour and the selected look's slot jobs."""

    type_name = "tv_tree_mode"

    def __init__(
        self,
        name: str,
        config: dict,
        midi_out: MidiOut,
        *,
        clock: Callable[[], float] = clock_now,
    ) -> None:
        super().__init__(name, config, midi_out, clock=clock)
        # Loaded in every preset (enabled=true, a disabled engine is never loaded) but
        # inert until a preset's engines map turns it on: only the TV TREE preset does.
        self.active = bool(config.get("start_active", False))
        self._channel = int(config.get("channel", 3))
        self._toggle_action = str(config.get("toggle_action", "RIGHT_STICK_CLICK_R3"))
        self._blackout_toggle_action = str(config.get("blackout_toggle_action", "R5"))
        self._blackout_hold_action = str(config.get("blackout_hold_action", "R4"))
        links = dict(_DEFAULT_LINKS)
        links.update({k: int(v) for k, v in (config.get("link_ccs") or {}).items()})
        self._links = links
        self._mode_cc = int(config.get("mode_cc", 20))
        self._chase_buttons = dict(config.get("chase_buttons") or _DEFAULT_CHASE_BUTTONS)

        self._suppress_channel = int(config.get("suppress_channel", 0))
        self._suppress_notes = frozenset(
            int(n) for n in config.get("suppress_notes", _DEFAULT_SUPPRESS_NOTES)
        )

        self._stick_deadzone = int(config.get("stick_deadzone", 3500))
        self._stick_max = int(config.get("stick_max", 32767))
        self._stick_invert_y = bool(config.get("stick_invert_y", False))

        self._gyro_axis = str(config.get("gyro_axis", "GYRO_PITCH"))
        self._gyro_span = max(1.0, float(config.get("gyro_span", 450)))
        self._gyro_deadzone = float(config.get("gyro_deadzone", 25))
        self._gyro_invert = bool(config.get("gyro_invert", False))
        self._spin_rest = float(config.get("spin_rest", 0.15))
        self._spin_gain = float(config.get("spin_gain", 1.0))

        self._paused_types = [str(t) for t in config.get("pause_engines", ["l_stick_layer", "gyro_feedback"])]

        self._registry = None
        self._mode = False
        self._blackout_latched = False
        self._blackout_held = False
        self._gyro_last: float | None = None
        self._gyro_zero = 0.0
        self._paused_prev: dict[str, bool] = {}
        self._sent: dict[int, int] = {}
        self._toggle_count = 0

    # ------------------------------------------------------------------
    # Registry hooks

    def bind_registry(self, registry) -> None:
        self._registry = registry
        registry.add_note_emit_filter(self._note_filter)

    def _note_filter(self, channel: int, note: int, velocity: int, now: float) -> bool:
        if self._mode and channel == self._suppress_channel and note in self._suppress_notes:
            return False
        return True

    def set_active(self, active: bool) -> None:
        if not active and self._mode:
            self._exit_mode()
        super().set_active(active)

    # ------------------------------------------------------------------
    # Inputs

    @property
    def mode(self) -> bool:
        return self._mode

    def on_input_event(self, action: str, state: str, now: float) -> None:
        down = state == "down"
        if action.endswith(LAYER_SUFFIX):
            action = action[: -len(LAYER_SUFFIX)]
        if action == self._toggle_action:
            if down:
                self._toggle_count += 1
                if self._mode:
                    self._exit_mode()
                else:
                    self._enter_mode()
            return
        if not self._mode:
            return
        if action == self._blackout_toggle_action:
            if down:
                self._blackout_latched = not self._blackout_latched
                self._send_blackout()
        elif action == self._blackout_hold_action:
            self._blackout_held = down
            self._send_blackout()
        elif action in self._chase_buttons:
            job = self._chase_buttons[action]
            self._send(self._links[job], 127 if down else 0)

    def on_axis_event(self, action: str, value: int, now: float) -> None:
        if action == self._gyro_axis:
            self._gyro_last = float(value)
            if self._mode:
                self._send_spin()
            return
        if not self._mode:
            return
        if action == STICK_X:
            self._send(self._links["ball_x"], self._stick_cc(value, invert=False))
        elif action == STICK_Y:
            self._send(self._links["ball_y"], self._stick_cc(value, invert=self._stick_invert_y))

    # ------------------------------------------------------------------
    # Mode transitions

    def _enter_mode(self) -> None:
        self._mode = True
        self._gyro_zero = self._gyro_last if self._gyro_last is not None else 0.0
        self._pause_others()
        self._sent.clear()
        self._send(self._mode_cc, 127)
        self._send_rest()
        LOGGER.info("tv_tree_mode: ON")

    def _exit_mode(self) -> None:
        self._send_rest()
        self._send(self._mode_cc, 0)
        self._mode = False
        self._resume_others()
        LOGGER.info("tv_tree_mode: OFF")

    def _send_rest(self) -> None:
        """Chases released, ball centred, spin at rest. Blackout keeps its latched state."""
        for job in ("chase_up", "chase_down", "chase_around", "chase_tv"):
            self._send(self._links[job], 0)
        self._send(self._links["ball_x"], 64)
        self._send(self._links["ball_y"], 64)
        self._blackout_held = False
        self._send_blackout()
        self._send(self._links["spin"], self._spin_to_cc(self._spin_rest))

    def _pause_others(self) -> None:
        self._paused_prev = {}
        if self._registry is None:
            return
        for type_name in self._paused_types:
            engine = self._registry.get_by_type(type_name)
            if engine is None:
                continue
            self._paused_prev[type_name] = engine.active
            release = getattr(engine, "_release_active_ccs", None)
            if callable(release) and engine.active:
                release()
            engine.set_active(False)

    def _resume_others(self) -> None:
        if self._registry is None:
            return
        for type_name, was_active in self._paused_prev.items():
            engine = self._registry.get_by_type(type_name)
            if engine is not None:
                engine.set_active(was_active)
        self._paused_prev = {}

    # ------------------------------------------------------------------
    # Value shaping

    def _send(self, cc: int, value: int) -> None:
        value = max(0, min(127, int(value)))
        if self._sent.get(cc) == value:
            return
        self._sent[cc] = value
        self._midi_out.control_change(self._channel, cc, value)

    def _send_blackout(self) -> None:
        on = self._blackout_latched or self._blackout_held
        self._send(self._links["blackout"], 127 if on else 0)

    def _stick_cc(self, raw: int, *, invert: bool) -> int:
        if abs(raw) <= self._stick_deadzone:
            return 64
        span = max(1, self._stick_max - self._stick_deadzone)
        t = min(1.0, (abs(raw) - self._stick_deadzone) / span)
        sign = 1.0 if raw > 0 else -1.0
        if invert:
            sign = -sign
        return round(64 + sign * t * 63)

    def _spin_to_cc(self, speed: float) -> int:
        speed = max(-1.0, min(1.0, speed))
        return round(64 + speed * 63)

    def _send_spin(self) -> None:
        if self._gyro_last is None:
            return
        tilt = self._gyro_last - self._gyro_zero
        if abs(tilt) <= self._gyro_deadzone:
            tilt = 0.0
        else:
            tilt -= self._gyro_deadzone if tilt > 0 else -self._gyro_deadzone
        norm = max(-1.0, min(1.0, tilt / self._gyro_span))
        if self._gyro_invert:
            norm = -norm
        self._send(self._links["spin"], self._spin_to_cc(self._spin_rest + self._spin_gain * norm))

    # ------------------------------------------------------------------

    def status(self) -> dict:
        return {
            "name": self.name,
            "type": self.type_name,
            "active": self.active,
            "mode": self._mode,
            "channel": self._channel,
            "links": dict(self._links),
            "mode_cc": self._mode_cc,
            "blackout": self._blackout_latched or self._blackout_held,
            "gyro_axis": self._gyro_axis,
            "paused_engines": sorted(self._paused_prev),
            "toggle_count": self._toggle_count,
        }
