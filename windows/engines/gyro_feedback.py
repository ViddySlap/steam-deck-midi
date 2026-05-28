"""Gyro router engine (v2 — bridge-side OSC fan-out).

Routes the Steam Deck's three continuous gyro axes (PITCH / YAW / ROLL)
to Resolume targets over OSC, with an L4 tap-vs-hold gesture selecting
the routing mode. There is NO NestDrop coupling and NO REST: every
output is an OSC write to Resolume (ADR-0001 — REST on the live path
drops frames and loses MIDI).

## Inputs

Gyro axes arrive on `on_axis_event` as RAW bipolar integers (about
[-750, 750]); the bridge's axis-to-cc mapping is for the MIDI-out path
and is irrelevant here — engines see the pre-mapping raw value:

  GYRO_PITCH  (deck CC 122 ch15 on the MIDI-out side)
  GYRO_YAW    (deck CC 123 ch15)   -- spare in both modes
  GYRO_ROLL   (deck CC 124 ch15)

L4 arrives on `on_midi_in` as CC 74 ch2 (down=127, up=0), fanned out
from the receiver's `_emit_cc`. A short tap toggles feedback routing;
a hold past the tap threshold routes gyro to the PUNCH PACK V4 SHAKE
effect while held.

## State

  feedback_active : bool — gyro routes to the Layer-11 feedback layer.
  hold_mode_active: bool — L4 held past TAP_THRESHOLD; gyro routes to
                           SHAKE (overrides feedback routing while held).

## L4 tap-vs-hold (tick-driven, mirrors flash_blast)

  on L4 down (127): record _l4_down_time, arm a pending-hold timer.
  tick: if L4 still down and (now - _l4_down_time) >= tap_threshold and
        not yet in hold mode -> enter hold mode (start SHAKE routing).
  on L4 up (0):
        elapsed = now - _l4_down_time
        if hold_mode_active        -> exit hold (zero SHAKE, revert to
                                      feedback routing for the current
                                      feedback_active state).
        elif elapsed < tap_threshold -> TAP: toggle feedback_active.
        else (>= threshold but hold never entered, e.g. a missed tick)
                                   -> treat as hold-release: ensure SHAKE
                                      zeroed + revert. Defensive.

## Routing fan-out

  hold False + feedback True : PITCH -> Layer-11 master opacity
                               ROLL  -> Layer-11 transform-X position
  hold False + feedback False: outputs muted. On the toggle-OFF edge we
                               write opacity 0.0 ONCE so the layer is
                               cleanly hidden; we then stop writing.
  hold True                  : PITCH -> SHAKE distance
                               ROLL  -> SHAKE frequency  (YAW spare)
                               On hold EXIT, SHAKE distance + frequency
                               are explicitly zeroed so the effect does
                               not latch.

## Normalization

`/composition/...` paths take 0..1 floats. PITCH->opacity and
ROLL->transform-X are bipolar [-750, 750] mapped to [0, 1] centered at
0.5 (raw 0 -> 0.5). SHAKE distance/frequency reuse the same bipolar
mapping by default (config-overridable per target). All ranges and
target paths are config-driven because the live OSC paths get
verified/corrected on the rig (wave-3).

## Legacy GYRO_STATE_NOW tolerance

The not-yet-updated Deck sender still emits a GYRO_STATE_NOW axis
event. The bridge now owns feedback state via the L4 tap, so this
engine IGNORES GYRO_STATE_NOW entirely: it neither crashes nor lets
the legacy ping flip `feedback_active`.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from windows.engines.base import Engine
from windows.engines.osc_client import OscClient
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
TICK_INTERVAL_SECONDS = 0.02  # 50 Hz — fine-grained enough for a 200ms gate

# --- OSC output -------------------------------------------------------
DEFAULT_OSC_HOST = "127.0.0.1"
DEFAULT_OSC_PORT = 7000

# --- Default target paths (ALL UNVERIFIED placeholders for wave-3) ----
# Layer-11 master opacity. Believed correct (matches the v1 feedback
# layer path), but re-confirm against the live comp.
DEFAULT_FEEDBACK_OPACITY_PATH = "/composition/layers/11/master"
# Layer-11 transform-X position. UNVERIFIED — Resolume transform param
# naming varies by version (position-x vs anchor, etc.).
DEFAULT_FEEDBACK_TRANSFORM_X_PATH = (
    "/composition/layers/11/video/transform/position-x"
)
# SHAKE distance / frequency — Wire-dashboard OSC paths, UNKNOWN.
# Clearly-named placeholders to be discovered live.
DEFAULT_SHAKE_DISTANCE_PATH = "/shake/distance/UNVERIFIED"
DEFAULT_SHAKE_FREQUENCY_PATH = "/shake/frequency/UNVERIFIED"

# --- Default value mapping --------------------------------------------
# Raw bipolar gyro range. Centered map: raw_min -> out_min, 0 -> mid,
# raw_max -> out_max.
DEFAULT_RAW_MIN = -750.0
DEFAULT_RAW_MAX = 750.0
DEFAULT_OUT_MIN = 0.0
DEFAULT_OUT_MAX = 1.0


def _normalize_bipolar(
    raw: float, raw_min: float, raw_max: float, out_min: float, out_max: float
) -> float:
    """Map a raw bipolar value to [out_min, out_max], clamped.

    Linear shift-and-scale: raw_min -> out_min, raw_max -> out_max. With
    the symmetric default range a raw value of 0 lands exactly at the
    midpoint (0.5 for a 0..1 output), which is the documented PITCH=>0.5
    rest behaviour.
    """
    span = raw_max - raw_min
    if span == 0.0:
        return out_min
    frac = (raw - raw_min) / span
    frac = max(0.0, min(1.0, frac))
    return out_min + frac * (out_max - out_min)


class _Target:
    """One OSC output target: a path plus its raw->out mapping range.

    Caches the last value sent so the engine doesn't spam identical
    frames (mirrors flash_blast's opacity dedupe intent).
    """

    __slots__ = ("path", "raw_min", "raw_max", "out_min", "out_max", "last_sent")

    def __init__(
        self,
        path: str,
        raw_min: float,
        raw_max: float,
        out_min: float,
        out_max: float,
    ) -> None:
        self.path = path
        self.raw_min = raw_min
        self.raw_max = raw_max
        self.out_min = out_min
        self.out_max = out_max
        self.last_sent: float | None = None

    def value_for(self, raw: float) -> float:
        return _normalize_bipolar(
            raw, self.raw_min, self.raw_max, self.out_min, self.out_max
        )


def _target_from_config(
    cfg: dict, default_path: str, defaults: dict
) -> _Target:
    """Build a _Target from a config sub-dict.

    The sub-dict may carry `path` and any of raw_min/raw_max/out_min/
    out_max; anything missing falls back to the engine-level defaults.
    """
    return _Target(
        path=str(cfg.get("path", default_path)),
        raw_min=float(cfg.get("raw_min", defaults["raw_min"])),
        raw_max=float(cfg.get("raw_max", defaults["raw_max"])),
        out_min=float(cfg.get("out_min", defaults["out_min"])),
        out_max=float(cfg.get("out_max", defaults["out_max"])),
    )


class GyroFeedbackEngine(Engine):
    type_name = "gyro_feedback"

    def __init__(
        self,
        name: str,
        config: dict,
        midi_out: MidiOut,
        *,
        clock: Callable[[], float] = time.monotonic,
        osc_client: OscClient | None = None,
        # Back-compat: the v1 engine + old tests passed `resolume_osc`.
        # Accept it as an alias so nothing downstream breaks.
        resolume_osc: OscClient | None = None,
        **_legacy: Any,
    ) -> None:
        super().__init__(name, config, midi_out, clock=clock)

        # --- Inputs ---
        self._l4_cc = int(config.get("l4_cc", config.get("trigger_cc", DEFAULT_L4_CC)))
        self._l4_channel = int(
            config.get("l4_channel", config.get("trigger_channel", DEFAULT_L4_CHANNEL))
        )
        axes = config.get("axes", {})
        self._axis_pitch = str(axes.get("pitch", DEFAULT_AXIS_PITCH))
        self._axis_yaw = str(axes.get("yaw", DEFAULT_AXIS_YAW))
        self._axis_roll = str(axes.get("roll", DEFAULT_AXIS_ROLL))
        # Legacy deck-side state ping we must tolerate + ignore.
        self._legacy_state_axis = str(
            config.get("legacy_state_axis_action", "GYRO_STATE_NOW")
        )

        # --- Timing ---
        self._tap_threshold = (
            float(config.get("tap_threshold_ms", DEFAULT_TAP_THRESHOLD_MS)) / 1000.0
        )

        # --- OSC client ---
        osc_cfg = config.get("osc", {})
        self._osc = osc_client or resolume_osc or OscClient(
            host=str(osc_cfg.get("host", DEFAULT_OSC_HOST)),
            port=int(osc_cfg.get("port", DEFAULT_OSC_PORT)),
        )

        # --- Targets ---
        defaults = {
            "raw_min": float(config.get("raw_min", DEFAULT_RAW_MIN)),
            "raw_max": float(config.get("raw_max", DEFAULT_RAW_MAX)),
            "out_min": float(config.get("out_min", DEFAULT_OUT_MIN)),
            "out_max": float(config.get("out_max", DEFAULT_OUT_MAX)),
        }
        targets = config.get("targets", {})
        self._feedback_opacity = _target_from_config(
            targets.get("feedback_opacity", {}),
            DEFAULT_FEEDBACK_OPACITY_PATH,
            defaults,
        )
        self._feedback_transform_x = _target_from_config(
            targets.get("feedback_transform_x", {}),
            DEFAULT_FEEDBACK_TRANSFORM_X_PATH,
            defaults,
        )
        self._shake_distance = _target_from_config(
            targets.get("shake_distance", {}),
            DEFAULT_SHAKE_DISTANCE_PATH,
            defaults,
        )
        self._shake_frequency = _target_from_config(
            targets.get("shake_frequency", {}),
            DEFAULT_SHAKE_FREQUENCY_PATH,
            defaults,
        )

        # --- State ---
        self._feedback_active = bool(config.get("initial_feedback_active", False))
        self._hold_mode_active = False
        # L4 gesture bookkeeping.
        self._l4_down = False
        self._l4_down_time: float | None = None
        # Latest raw axis values (updated on every axis event).
        self._pitch_raw = 0.0
        self._roll_raw = 0.0

        # --- Counters (status/debugging) ---
        self._tap_count = 0
        self._hold_enter_count = 0
        self._hold_exit_count = 0
        self._ignored_legacy_count = 0

    # ------------------------------------------------------------------
    # Lifecycle

    def tick_interval_seconds(self) -> float | None:
        return TICK_INTERVAL_SECONDS

    def bind_registry(self, registry) -> None:
        """Establish the idle rest state.

        Feedback boots inactive, so write opacity 0.0 once so the layer
        starts hidden. SHAKE outputs are zeroed so a stale comp value
        doesn't latch.
        """
        self._send(self._feedback_opacity, self._feedback_opacity.out_min)
        self._zero_shake()

    def shutdown(self) -> None:
        try:
            self._osc.close()
        except Exception:
            pass

    def refresh(self) -> None:
        """Re-assert the idle rest state (dev escape hatch).

        Resets feedback OFF + zeroes SHAKE, matching boot. Lets a
        dashboard recover from any drift without a bridge restart. No
        REST is involved.
        """
        self._feedback_active = False
        self._hold_mode_active = False
        self._send(self._feedback_opacity, self._feedback_opacity.out_min, force=True)
        self._zero_shake(force=True)

    # ------------------------------------------------------------------
    # MIDI input — L4 tap/hold

    def on_midi_in(self, channel: int, cc: int, value: int, now: float) -> None:
        if channel != self._l4_channel or cc != self._l4_cc:
            return
        if value >= 64:  # L4 down (sender uses 127; tolerate any "on")
            self._on_l4_down(now)
        else:  # L4 up (0)
            self._on_l4_up(now)

    def _on_l4_down(self, now: float) -> None:
        # Idempotent: ignore a repeated down with no intervening up.
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
            # Release of a hold: exit SHAKE, revert to feedback routing.
            self._exit_hold()
            return
        if elapsed >= self._tap_threshold:
            # Threshold reached but hold never armed (e.g. tick missed
            # between down and up). Treat as hold-release defensively:
            # make sure SHAKE is zeroed and feedback routing is current.
            self._exit_hold()
            return
        # Genuine tap: toggle feedback routing.
        self._toggle_feedback()

    def tick(self, now: float) -> None:
        # Hold ENTRY is timer-driven: if L4 is still down past the tap
        # threshold and we haven't entered hold yet, enter it now.
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
        # Tolerate the legacy deck-side state ping: never crash, never
        # let it touch feedback state. The bridge owns feedback via L4.
        if action == self._legacy_state_axis:
            self._ignored_legacy_count += 1
            return

        if action == self._axis_pitch:
            self._pitch_raw = float(value)
        elif action == self._axis_roll:
            self._roll_raw = float(value)
        elif action == self._axis_yaw:
            # YAW is spare in both modes. Track nothing, route nothing.
            return
        else:
            return

        self._route_gyro()

    def _route_gyro(self) -> None:
        if self._hold_mode_active:
            # SHAKE routing: PITCH -> distance, ROLL -> frequency.
            self._send(self._shake_distance, self._shake_distance.value_for(self._pitch_raw))
            self._send(self._shake_frequency, self._shake_frequency.value_for(self._roll_raw))
            return
        if self._feedback_active:
            # Feedback routing: PITCH -> opacity, ROLL -> transform-X.
            self._send(
                self._feedback_opacity,
                self._feedback_opacity.value_for(self._pitch_raw),
            )
            self._send(
                self._feedback_transform_x,
                self._feedback_transform_x.value_for(self._roll_raw),
            )
            return
        # feedback OFF + not holding: outputs muted. Do nothing (the
        # toggle-OFF edge already wrote opacity 0.0 once).

    # ------------------------------------------------------------------
    # State transitions

    def _toggle_feedback(self) -> None:
        self._feedback_active = not self._feedback_active
        self._tap_count += 1
        if self._feedback_active:
            # Toggle ON: immediately route the current gyro position so
            # the layer reflects the live tilt without waiting for the
            # next axis event.
            self._route_gyro()
            LOGGER.info("%s: feedback toggled ON", self.name)
        else:
            # Toggle OFF: write opacity 0.0 ONCE so the layer is cleanly
            # hidden, then stop writing (muted).
            self._send(self._feedback_opacity, self._feedback_opacity.out_min)
            LOGGER.info("%s: feedback toggled OFF (opacity 0)", self.name)

    def _enter_hold(self) -> None:
        self._hold_mode_active = True
        self._hold_enter_count += 1
        # Start routing gyro to SHAKE from the current position.
        self._route_gyro()
        LOGGER.info("%s: hold mode ENTER (gyro -> SHAKE)", self.name)

    def _exit_hold(self) -> None:
        was_hold = self._hold_mode_active
        self._hold_mode_active = False
        if was_hold:
            self._hold_exit_count += 1
        # Explicitly zero SHAKE so the effect doesn't latch. Force the
        # write (bypass dedupe): a state-boundary guarantee that the
        # SHAKE floor lands is worth one extra packet, and protects
        # against any cached-value drift on the comp side.
        self._zero_shake(force=True)
        # Revert to feedback routing for the current feedback state.
        if self._feedback_active:
            self._route_gyro()
        else:
            # Feedback off: ensure the layer stays cleanly hidden.
            self._send(self._feedback_opacity, self._feedback_opacity.out_min)
        LOGGER.info("%s: hold mode EXIT (SHAKE zeroed)", self.name)

    # ------------------------------------------------------------------
    # OSC helpers

    def _send(self, target: _Target, value: float, *, force: bool = False) -> None:
        """Send a normalized float to an OSC target, deduped.

        Skips the write when the value is unchanged from the last sent
        value (unless `force`), to avoid spamming identical frames at
        the gyro's high event rate.
        """
        clamped = float(value)
        if not force and target.last_sent is not None and target.last_sent == clamped:
            return
        try:
            self._osc.send(target.path, clamped)
            target.last_sent = clamped
        except Exception:
            LOGGER.exception("%s: OSC send failed for %s", self.name, target.path)

    def _zero_shake(self, *, force: bool = False) -> None:
        self._send(self._shake_distance, self._shake_distance.out_min, force=force)
        self._send(self._shake_frequency, self._shake_frequency.out_min, force=force)

    # ------------------------------------------------------------------
    # Status

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type_name,
            "feedback_active": self._feedback_active,
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
            "targets": {
                "feedback_opacity": self._feedback_opacity.path,
                "feedback_transform_x": self._feedback_transform_x.path,
                "shake_distance": self._shake_distance.path,
                "shake_frequency": self._shake_frequency.path,
            },
            "tap_count": self._tap_count,
            "hold_enter_count": self._hold_enter_count,
            "hold_exit_count": self._hold_exit_count,
            "ignored_legacy_count": self._ignored_legacy_count,
        }
