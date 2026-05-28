"""Left-stick dual-layer CC engine.

The left analog stick has two switchable X/Y CC sets, toggled by the L3
click (the left stick press). This lets one physical stick drive two
independent pairs of effect axes in Resolume without a SteamInput layer
remap on the deck.

The deck-side sender emits raw analog axis events `L_STICK_X_AXIS` and
`L_STICK_Y_AXIS` (see `deck/xinput_send.py`); the L3 click arrives as
MIDI Note 72 on channel 0 (`LEFT_STICK_CLICK_L3` in the map). This engine
consumes the axis events directly via `on_axis_event` and re-emits split
CCs for whichever set is currently active. Each L3 press toggles the set.

Two sets (channel 15 in the factory default):

  Set A — the legacy default:
    X right -> CC 118,  X left -> CC 120
    Y up    -> CC 119,  Y down -> CC 121
  Set B — confirmed-free CCs:
    X right -> CC 110,  X left -> CC 112
    Y up    -> CC 111,  Y down -> CC 113

Split-CC semantics mirror the receiver's `_handle_axis_split_event`: each
axis has a positive-direction CC and a negative-direction CC. While the
stick is pushed one way the positive (or negative) CC ramps 0..127 by
magnitude; crossing back through the deadzone zeroes the just-released
direction's CC. We track per-axis direction so a direction flip cleanly
zeroes the old CC before ramping the new one.

DOUBLE-EMIT AVOIDANCE: the receiver (`_handle_axis_event`) fans every
axis event to engines via `on_axis_event` BEFORE looking up the action's
MIDI mapping. If the mapping for `L_STICK_X_AXIS` / `L_STICK_Y_AXIS` is
neither `axis_to_cc` nor `axis_split_cc`, the receiver emits nothing and
returns. So as long as the tracked `windows_midi_map.json` carries NO
`axis_split_cc` (or `axis_to_cc`) entry for the two L_STICK axes, this
engine is the SOLE emitter of the L_STICK CCs and there is no double
emit. This mirrors how `steam_input_layer_tracker` coexists with the
map: it is a pure engine, not a map mapping.

Layer-toggle shape mirrors `steam_input_layer_tracker`: a note toggles a
state; the state changes which CC set the analog re-emit uses.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from windows.engines.base import Engine
from windows.midi import MidiOut

LOGGER = logging.getLogger(__name__)

LAYER_A = "a"
LAYER_B = "b"
_VALID_LAYERS = frozenset({LAYER_A, LAYER_B})

X_AXIS_ACTION = "L_STICK_X_AXIS"
Y_AXIS_ACTION = "L_STICK_Y_AXIS"
_AXIS_ACTIONS = frozenset({X_AXIS_ACTION, Y_AXIS_ACTION})

# Direction sentinels for per-axis split tracking.
_DIR_ZERO = "zero"
_DIR_POS = "pos"
_DIR_NEG = "neg"


class LStickLayerEngine(Engine):
    """Re-emit the left stick X/Y as one of two switchable split-CC sets."""

    type_name = "l_stick_layer"

    def __init__(
        self,
        name: str,
        config: dict,
        midi_out: MidiOut,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(name, config, midi_out, clock=clock)

        # Output channel for all emitted CCs (both sets share one channel).
        self._channel = int(config.get("channel", 15))

        # The L3 click that toggles the active set. Default: Note 72 ch0,
        # matching LEFT_STICK_CLICK_L3 in the map. channel None => any.
        self._toggle_note = int(config.get("toggle_note", 72))
        toggle_ch_raw = config.get("toggle_note_channel", 0)
        self._toggle_note_channel: int | None = (
            int(toggle_ch_raw) if toggle_ch_raw is not None else None
        )

        # Deadzone / input span for the split mapping. Matches the L_STICK
        # axis_split_cc deadzone (3500) and full-scale (32767) used live.
        self._deadzone = int(config.get("deadzone", 3500))
        self._input_max = int(config.get("input_max", 32767))

        # The two CC sets. Each is a dict of per-axis positive/negative CCs.
        # Keys: x_pos (right), x_neg (left), y_pos (up), y_neg (down).
        set_a = config.get("set_a", {})
        set_b = config.get("set_b", {})
        self._sets: dict[str, dict[str, int]] = {
            LAYER_A: {
                "x_pos": int(set_a.get("x_pos", 118)),
                "x_neg": int(set_a.get("x_neg", 120)),
                "y_pos": int(set_a.get("y_pos", 119)),
                "y_neg": int(set_a.get("y_neg", 121)),
            },
            LAYER_B: {
                "x_pos": int(set_b.get("x_pos", 110)),
                "x_neg": int(set_b.get("x_neg", 112)),
                "y_pos": int(set_b.get("y_pos", 111)),
                "y_neg": int(set_b.get("y_neg", 113)),
            },
        }

        default_layer = str(config.get("default_layer", LAYER_A)).lower()
        if default_layer not in _VALID_LAYERS:
            LOGGER.warning(
                "l_stick_layer: invalid default_layer %r; using %r",
                default_layer,
                LAYER_A,
            )
            default_layer = LAYER_A
        self._current_layer: str = default_layer

        # Per-axis last-emitted direction so a flip zeroes the old CC. Keyed
        # by axis action ("L_STICK_X_AXIS" / "L_STICK_Y_AXIS").
        self._axis_directions: dict[str, str] = {
            X_AXIS_ACTION: _DIR_ZERO,
            Y_AXIS_ACTION: _DIR_ZERO,
        }

        # Stats for status()/debugging.
        self._axis_events_total = 0
        self._toggle_count = 0
        self._last_toggle_at: float | None = None

    # ------------------------------------------------------------------
    # Public API

    @property
    def current_layer(self) -> str:
        return self._current_layer

    def active_set(self) -> dict[str, int]:
        """The currently active CC set (mapping of axis-direction -> CC)."""
        return self._sets[self._current_layer]

    # ------------------------------------------------------------------
    # MIDI / axis handlers

    def on_note_in(self, channel: int, note: int, velocity: int, now: float) -> None:
        if velocity == 0:
            # Note off — toggle is press-driven.
            return
        if note != self._toggle_note:
            return
        if (
            self._toggle_note_channel is not None
            and channel != self._toggle_note_channel
        ):
            return
        self._toggle_layer(now)

    def on_axis_event(self, action: str, value: int, now: float) -> None:
        if action not in _AXIS_ACTIONS:
            return
        self._axis_events_total += 1
        active = self._sets[self._current_layer]
        if action == X_AXIS_ACTION:
            pos_cc, neg_cc = active["x_pos"], active["x_neg"]
        else:
            pos_cc, neg_cc = active["y_pos"], active["y_neg"]
        self._emit_split(action, value, pos_cc, neg_cc)

    # ------------------------------------------------------------------
    # Split-CC emit (mirrors receiver._handle_axis_split_event polarity)

    def _emit_split(self, action: str, raw: int, pos_cc: int, neg_cc: int) -> None:
        last_direction = self._axis_directions.get(action, _DIR_ZERO)

        if abs(raw) <= self._deadzone:
            current_direction = _DIR_ZERO
        elif raw > 0:
            current_direction = _DIR_POS
        else:
            current_direction = _DIR_NEG

        transition = current_direction != last_direction
        if transition:
            # Zero the CC for the direction we just left.
            if last_direction == _DIR_POS:
                self._midi_out.control_change(self._channel, pos_cc, 0)
            elif last_direction == _DIR_NEG:
                self._midi_out.control_change(self._channel, neg_cc, 0)
            self._axis_directions[action] = current_direction

        if current_direction == _DIR_ZERO:
            return

        if current_direction == _DIR_POS:
            cc_value = self._split_to_cc_value(raw)
            self._midi_out.control_change(self._channel, pos_cc, cc_value)
        else:
            cc_value = self._split_to_cc_value(-raw)
            self._midi_out.control_change(self._channel, neg_cc, cc_value)

    def _split_to_cc_value(self, magnitude: int) -> int:
        if magnitude >= self._input_max:
            return 127
        span = self._input_max - self._deadzone
        if span <= 0:
            return 127
        t = (magnitude - self._deadzone) / span
        return max(0, min(127, round(t * 127)))

    # ------------------------------------------------------------------
    # State transitions

    def _toggle_layer(self, now: float) -> None:
        new_layer = LAYER_B if self._current_layer == LAYER_A else LAYER_A
        # Zero any CCs still active on the outgoing set so the switch is
        # clean — a held stick won't leave a stuck CC on the old set.
        self._release_active_ccs()
        self._current_layer = new_layer
        self._toggle_count += 1
        self._last_toggle_at = now
        LOGGER.info("l_stick_layer: set -> %s", new_layer)

    def _release_active_ccs(self) -> None:
        """Zero whichever direction CCs are currently non-centered, then
        reset per-axis direction so the next axis event re-ramps cleanly on
        the new set."""
        active = self._sets[self._current_layer]
        for action, dir_key, pos_key, neg_key in (
            (X_AXIS_ACTION, X_AXIS_ACTION, "x_pos", "x_neg"),
            (Y_AXIS_ACTION, Y_AXIS_ACTION, "y_pos", "y_neg"),
        ):
            direction = self._axis_directions.get(dir_key, _DIR_ZERO)
            if direction == _DIR_POS:
                self._midi_out.control_change(self._channel, active[pos_key], 0)
            elif direction == _DIR_NEG:
                self._midi_out.control_change(self._channel, active[neg_key], 0)
            self._axis_directions[dir_key] = _DIR_ZERO

    # ------------------------------------------------------------------
    # Engine lifecycle

    def status(self) -> dict:
        return {
            "name": self.name,
            "type": self.type_name,
            "current_layer": self._current_layer,
            "channel": self._channel,
            "toggle_note": self._toggle_note,
            "toggle_note_channel": self._toggle_note_channel,
            "deadzone": self._deadzone,
            "input_max": self._input_max,
            "set_a": dict(self._sets[LAYER_A]),
            "set_b": dict(self._sets[LAYER_B]),
            "axis_directions": dict(self._axis_directions),
            "axis_events_total": self._axis_events_total,
            "toggle_count": self._toggle_count,
            "last_toggle_at": self._last_toggle_at,
        }
