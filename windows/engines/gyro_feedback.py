"""Gyro MIDI-gate engine (v3 — L4-gated gyro MIDI emission).

Turns the Steam Deck's three continuous gyro axes (PITCH / YAW / ROLL)
into MIDI CC streams that the operator can MIDI-learn to ANY Resolume
parameter on the fly during a show. There is NO OSC and NO NestDrop
coupling: every output is a MIDI CC emitted on the bridge's MIDI-out
(DECK_IN), so Resolume's MIDI-learn sees it.

## Why L4 gates emission

The deck streams gyro continuously (always-on). If those CCs flowed to
Resolume all the time, MIDI-learn would always grab the gyro and the
gyro would constantly nudge every param it's mapped to. So the bridge
gates emission behind the L4 button: gyro CCs only flow when the
operator asks for them.

## Inputs

Gyro axes arrive on `on_axis_event` as RAW bipolar integers (about
[-750, 750] at the deadzone-scaled edges; the raw value is an unbounded
position accumulator, so it can drift well past that — see raw_max /
recenter tuning):

  GYRO_PITCH  (deck-side CC 122 ch15 historically)
  GYRO_YAW    (deck-side CC 123 ch15)
  GYRO_ROLL   (deck-side CC 124 ch15)

L4 arrives on `on_midi_in` as CC 74 ch2 (down>=64, up=0), fanned out
from the receiver. A short tap toggles the latched emission set; a hold
past the tap threshold emits a SECOND set while held.

## L4 gestures

  tap  (down then up < tap_threshold) : toggle `midi_active` (latched).
                                        While active, gyro emits SET 1.
  hold (down past tap_threshold)      : `hold_active` while held. Gyro
                                        emits SET 2 (different CCs /
                                        channel). Overrides SET 1 while
                                        held; on release reverts to the
                                        current `midi_active` state.

The two gestures are independent and composable: hold works whether or
not the toggle is latched on.

## Emission

  hold_active            : axes -> SET 2 CCs (config `hold`)
  midi_active (not hold) : axes -> SET 1 CCs (config `toggle`)
  neither                : nothing emitted. We do NOT reset the learned
                           param — it holds its last value, which is the
                           natural MIDI behaviour.

Each axis maps RAW -> [out_min, out_max] (default 0..127) with a
center-deadzone, and is deduped so we don't spam identical CC values at
the gyro's ~58 Hz event rate.

## Legacy GYRO_STATE_NOW tolerance

An older deck sender emitted a GYRO_STATE_NOW axis ping. This engine
ignores it entirely (never crashes, never lets it flip state).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from windows.engines.base import Engine
from windows.midi import MidiOut

LOGGER = logging.getLogger(__name__)

# --- Inputs -----------------------------------------------------------
DEFAULT_L4_CC = 74
DEFAULT_L4_CHANNEL = 2
DEFAULT_AXIS_PITCH = "GYRO_PITCH"
DEFAULT_AXIS_YAW = "GYRO_YAW"
DEFAULT_AXIS_ROLL = "GYRO_ROLL"

# --- Timing -----------------------------------------------------------
DEFAULT_TAP_THRESHOLD_MS = 200.0
TICK_INTERVAL_SECONDS = 0.02  # 50 Hz — fine enough for a 200ms gate

# --- Value mapping ----------------------------------------------------
DEFAULT_RAW_MIN = -750.0
DEFAULT_RAW_MAX = 750.0
DEFAULT_OUT_MIN = 0
DEFAULT_OUT_MAX = 127
DEFAULT_DEADZONE = 100.0

# --- Default CC sets (config-overridable) -----------------------------
# Set 1 = tap-toggle (latched). Set 2 = hold (momentary), on a dedicated
# free channel so its CC numbers can mirror set 1 without colliding.
DEFAULT_TOGGLE = {"channel": 15, "pitch": 122, "roll": 124, "yaw": 123}
DEFAULT_HOLD = {"channel": 13, "pitch": 122, "roll": 124, "yaw": 123}


def _scale_midi(
    raw: float,
    raw_min: float,
    raw_max: float,
    out_min: int,
    out_max: int,
    deadzone: float,
) -> int:
    """Map a raw bipolar gyro value to an integer MIDI value, clamped.

    A symmetric center-deadzone holds the output at its midpoint while the
    raw value is within +/-deadzone of 0, then remaps the remaining travel
    linearly to each half of the output range (no jump at the deadzone
    edge). Assumes a roughly symmetric raw range centered on 0.
    """
    center = (out_min + out_max) / 2.0
    span = max(raw_max - deadzone, 1e-6)
    if raw > deadzone:
        frac = min(1.0, (raw - deadzone) / span)
        out = center + frac * (out_max - center)
    elif raw < -deadzone:
        frac = min(1.0, (-raw - deadzone) / span)
        out = center - frac * (center - out_min)
    else:
        out = center
    return int(round(max(out_min, min(out_max, out))))


class _CcSet:
    """One channel + per-axis CC numbers, with per-CC last-sent dedupe and
    a per-axis center offset.

    The center offset is the raw gyro position captured when the set is
    activated (recenter). Emission scales `raw - center`, so "where the
    deck is at activation" maps to the output midpoint and the operator
    gets the full travel from there. This defeats the unbounded gyro
    accumulator's drift: a latched set can't slowly clamp itself off,
    because every activation re-zeros it.
    """

    __slots__ = ("channel", "pitch_cc", "roll_cc", "yaw_cc", "_last", "_center")

    def __init__(self, cfg: dict, defaults: dict) -> None:
        self.channel = int(cfg.get("channel", defaults["channel"]))
        self.pitch_cc = cfg.get("pitch", defaults["pitch"])
        self.roll_cc = cfg.get("roll", defaults["roll"])
        self.yaw_cc = cfg.get("yaw", defaults["yaw"])
        self._last: dict[int, int] = {}
        self._center: dict[str, float] = {"pitch": 0.0, "roll": 0.0, "yaw": 0.0}

    def cc_for(self, axis: str) -> int | None:
        return {"pitch": self.pitch_cc, "roll": self.roll_cc, "yaw": self.yaw_cc}.get(axis)

    def center_for(self, axis: str) -> float:
        return self._center.get(axis, 0.0)

    def recenter(self, pitch: float, roll: float, yaw: float) -> None:
        self._center = {"pitch": pitch, "roll": roll, "yaw": yaw}

    def changed(self, cc: int, value: int) -> bool:
        if self._last.get(cc) == value:
            return False
        self._last[cc] = value
        return True

    def clear_dedupe(self) -> None:
        self._last.clear()

    def as_dict(self) -> dict:
        return {"channel": self.channel, "pitch": self.pitch_cc,
                "roll": self.roll_cc, "yaw": self.yaw_cc,
                "center": dict(self._center)}


class GyroFeedbackEngine(Engine):
    type_name = "gyro_feedback"

    def __init__(
        self,
        name: str,
        config: dict,
        midi_out: MidiOut,
        *,
        clock: Callable[[], float] = time.monotonic,
        # Back-compat: older callers/tests passed an osc client. Accept and
        # ignore so construction never breaks; this engine emits MIDI only.
        osc_client: Any = None,
        resolume_osc: Any = None,
        **_legacy: Any,
    ) -> None:
        super().__init__(name, config, midi_out, clock=clock)

        # --- L4 input ---
        self._l4_cc = int(config.get("l4_cc", config.get("trigger_cc", DEFAULT_L4_CC)))
        self._l4_channel = int(
            config.get("l4_channel", config.get("trigger_channel", DEFAULT_L4_CHANNEL))
        )

        # --- Axis action names ---
        axes = config.get("axes", {})
        self._axis_pitch = str(axes.get("pitch", DEFAULT_AXIS_PITCH))
        self._axis_yaw = str(axes.get("yaw", DEFAULT_AXIS_YAW))
        self._axis_roll = str(axes.get("roll", DEFAULT_AXIS_ROLL))
        self._legacy_state_axis = str(
            config.get("legacy_state_axis_action", "GYRO_STATE_NOW")
        )

        # --- Timing ---
        self._tap_threshold = (
            float(config.get("tap_threshold_ms", DEFAULT_TAP_THRESHOLD_MS)) / 1000.0
        )

        # --- Value mapping ---
        self._raw_min = float(config.get("raw_min", DEFAULT_RAW_MIN))
        self._raw_max = float(config.get("raw_max", DEFAULT_RAW_MAX))
        self._out_min = int(config.get("out_min", DEFAULT_OUT_MIN))
        self._out_max = int(config.get("out_max", DEFAULT_OUT_MAX))
        self._deadzone = float(config.get("deadzone", DEFAULT_DEADZONE))
        # Recenter each set on activation so the drifting accumulator can't
        # clamp a latched set off. ON by default (matches the old deck's
        # re-zero-on-L4 behaviour).
        self._recenter = bool(config.get("recenter_on_activate", True))
        # Per-axis raw-range override. The same raw window feels different
        # per physical axis (forward/back tilt covers fewer raw units than a
        # left/right twist for a comfortable gesture), so each axis can carry
        # its own raw_min/raw_max. A smaller range = more sensitive = less
        # tilt for full travel. Applies to BOTH sets. Falls back to the
        # engine-level raw_min/raw_max.
        axis_raw = config.get("axis_raw", {})
        self._axis_raw: dict[str, tuple[float, float]] = {}
        for _ax in ("pitch", "roll", "yaw"):
            _o = axis_raw.get(_ax, {})
            self._axis_raw[_ax] = (
                float(_o.get("raw_min", self._raw_min)),
                float(_o.get("raw_max", self._raw_max)),
            )

        # --- CC sets ---
        self._toggle = _CcSet(config.get("toggle", {}), DEFAULT_TOGGLE)
        self._hold = _CcSet(config.get("hold", {}), DEFAULT_HOLD)

        # --- State ---
        self._midi_active = bool(config.get("initial_midi_active", False))
        self._hold_mode_active = False
        self._l4_down = False
        self._l4_down_time: float | None = None
        self._pitch_raw = 0.0
        self._roll_raw = 0.0
        self._yaw_raw = 0.0

        # --- Counters (status/debug) ---
        self._tap_count = 0
        self._hold_enter_count = 0
        self._hold_exit_count = 0
        self._ignored_legacy_count = 0
        self._emit_count = 0

    # ------------------------------------------------------------------
    # Lifecycle

    def tick_interval_seconds(self) -> float | None:
        return TICK_INTERVAL_SECONDS

    def refresh(self) -> None:
        """Dev escape hatch: force emission OFF (no MIDI), clear dedupe."""
        self._midi_active = False
        self._hold_mode_active = False
        self._toggle.clear_dedupe()
        self._hold.clear_dedupe()

    # ------------------------------------------------------------------
    # MIDI input — L4 tap/hold

    def on_midi_in(self, channel: int, cc: int, value: int, now: float) -> None:
        if channel != self._l4_channel or cc != self._l4_cc:
            return
        if value >= 64:
            self._on_l4_down(now)
        else:
            self._on_l4_up(now)

    def _on_l4_down(self, now: float) -> None:
        if self._l4_down:
            return
        self._l4_down = True
        self._l4_down_time = now

    def _on_l4_up(self, now: float) -> None:
        if not self._l4_down:
            return
        self._l4_down = False
        down_time = self._l4_down_time
        self._l4_down_time = None
        elapsed = (now - down_time) if down_time is not None else 0.0

        if self._hold_mode_active:
            self._exit_hold()
            return
        if elapsed >= self._tap_threshold:
            # Threshold reached but hold never armed (missed tick). Treat
            # defensively as a hold-release: ensure we're not stuck holding.
            self._exit_hold()
            return
        self._toggle_midi()

    def tick(self, now: float) -> None:
        if (
            self._l4_down
            and not self._hold_mode_active
            and self._l4_down_time is not None
            and (now - self._l4_down_time) >= self._tap_threshold
        ):
            self._enter_hold()

    # ------------------------------------------------------------------
    # Axis input — gyro routing

    def on_axis_event(self, action: str, value: int, now: float) -> None:
        if action == self._legacy_state_axis:
            self._ignored_legacy_count += 1
            return
        if action == self._axis_pitch:
            self._pitch_raw = float(value)
        elif action == self._axis_roll:
            self._roll_raw = float(value)
        elif action == self._axis_yaw:
            self._yaw_raw = float(value)
        else:
            return
        self._route_gyro()

    def _route_gyro(self) -> None:
        if self._hold_mode_active:
            self._emit_set(self._hold)
        elif self._midi_active:
            self._emit_set(self._toggle)
        # else: emit nothing (param holds its last learned value).

    def _emit_set(self, cc_set: _CcSet) -> None:
        for axis, raw in (
            ("pitch", self._pitch_raw),
            ("roll", self._roll_raw),
            ("yaw", self._yaw_raw),
        ):
            cc = cc_set.cc_for(axis)
            if cc is None:
                continue
            rmin, rmax = self._axis_raw.get(axis, (self._raw_min, self._raw_max))
            value = _scale_midi(
                raw - cc_set.center_for(axis), rmin, rmax,
                self._out_min, self._out_max, self._deadzone,
            )
            if cc_set.changed(cc, value):
                try:
                    self._midi_out.control_change(cc_set.channel, cc, value)
                    self._emit_count += 1
                except Exception:
                    LOGGER.exception(
                        "%s: MIDI emit failed ch%s cc%s", self.name, cc_set.channel, cc
                    )

    # ------------------------------------------------------------------
    # State transitions

    def _toggle_midi(self) -> None:
        self._midi_active = not self._midi_active
        self._tap_count += 1
        if self._midi_active:
            # Recenter on the current gyro position so "where the deck is
            # now" maps to the output midpoint, then emit it immediately so
            # the learned param settles at center without waiting for the
            # next axis event.
            if self._recenter:
                self._toggle.recenter(self._pitch_raw, self._roll_raw, self._yaw_raw)
            self._toggle.clear_dedupe()
            self._emit_set(self._toggle)
            LOGGER.info("%s: gyro MIDI toggled ON (set 1, ch%s)",
                        self.name, self._toggle.channel)
        else:
            self._toggle.clear_dedupe()
            LOGGER.info("%s: gyro MIDI toggled OFF", self.name)

    def _enter_hold(self) -> None:
        self._hold_mode_active = True
        self._hold_enter_count += 1
        if self._recenter:
            self._hold.recenter(self._pitch_raw, self._roll_raw, self._yaw_raw)
        self._hold.clear_dedupe()
        self._emit_set(self._hold)
        LOGGER.info("%s: hold mode ENTER (set 2, ch%s)", self.name, self._hold.channel)

    def _exit_hold(self) -> None:
        was_hold = self._hold_mode_active
        self._hold_mode_active = False
        if was_hold:
            self._hold_exit_count += 1
        self._hold.clear_dedupe()
        # Revert to the latched toggle state: if still active, re-emit the
        # current position on set 1 so it resumes cleanly.
        if self._midi_active:
            self._toggle.clear_dedupe()
            self._emit_set(self._toggle)
        LOGGER.info("%s: hold mode EXIT", self.name)

    # ------------------------------------------------------------------
    # Status

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type_name,
            "midi_active": self._midi_active,
            "hold_mode_active": self._hold_mode_active,
            "l4_down": self._l4_down,
            "l4_cc": self._l4_cc,
            "l4_channel": self._l4_channel,
            "tap_threshold_ms": round(self._tap_threshold * 1000.0, 1),
            "axes": {
                "pitch": self._axis_pitch,
                "yaw": self._axis_yaw,
                "roll": self._axis_roll,
            },
            "value_map": {
                "raw_min": self._raw_min,
                "raw_max": self._raw_max,
                "out_min": self._out_min,
                "out_max": self._out_max,
                "deadzone": self._deadzone,
                "axis_raw": {ax: {"raw_min": r[0], "raw_max": r[1]} for ax, r in self._axis_raw.items()},
            },
            "recenter_on_activate": self._recenter,
            "raw_now": {
                "pitch": self._pitch_raw,
                "roll": self._roll_raw,
                "yaw": self._yaw_raw,
            },
            "toggle_set": self._toggle.as_dict(),
            "hold_set": self._hold.as_dict(),
            "tap_count": self._tap_count,
            "hold_enter_count": self._hold_enter_count,
            "hold_exit_count": self._hold_exit_count,
            "ignored_legacy_count": self._ignored_legacy_count,
            "emit_count": self._emit_count,
        }
