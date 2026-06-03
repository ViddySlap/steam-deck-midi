"""PTZ VISCA engine — joystick -> VISCA-over-IP camera control.

One physical hand (left stick + analog trigger + bumper) drives one BirdDog
X5 Ultra camera over VISCA-over-IP. v1 ships a single control group (``left``)
on a single fixed target camera; the two-group / camera-select build-out
(specs ptz-two-control-groups onward) reuses these same per-group methods.

Design decisions implemented (locked 2026-06-02, workflow.md § Design decisions):

1. **Consume the raw axis, not a CC.** ``on_axis_event`` hands over the decoded
   action + raw signed int. The engine subtracts the per-axis calibrated center
   (sticks are NOT centered at 0), applies the deadzone + curve, scales the
   magnitude to a VISCA speed byte, and derives direction from the sign. There
   is NO ``windows_midi_map.json`` axis entry for the PTZ stick/trigger axes, so
   the engine is the sole emitter (no double-emit). Mirrors ``l_stick_layer``.

2. **Stop-safety inverts the freeze-at-last-value failsafe.** Pan/tilt and zoom
   are continuous with no camera-side timeout, so a frozen non-zero speed would
   run the camera to its mechanical limit. The engine instead STOPS on center
   (stick/trigger within deadzone, sent redundantly), on drop (a ``tick()``
   watchdog injects STOP when axis events stop arriving), and on shutdown /
   toggle-off. The watchdog is a local time check only — no polling
   (ADR-0001 clean).

3. **Zoom on the analog trigger, default IN, hold-bumper to invert to OUT.**
   Leased-hold modifier: the same-side bumper held = OUT while held (Note-Off
   clears). ``zoom_invert_note`` may be null until Ben assigns the bumper —
   then zoom is IN-only, a usable v1 fallback.

4. **One bound UDP socket, fire-and-forget** (the ``visca_sender`` module).

Camera/VISCA/byte facts: wiki/reference/ptz-cameras.md. The VISCA transport
lives in ``visca_sender.py``; this engine only decides *what* to send.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from windows.engines.base import Engine
from windows.engines.visca_sender import (
    PAN_LEFT,
    PAN_RIGHT,
    PT_STOP,
    TILT_DOWN,
    TILT_UP,
    PtzViscaSender,
)
from windows.midi import MidiOut

LOGGER = logging.getLogger(__name__)

# Per-axis calibrated centers (sticks are NOT centered at 0). Calibrated
# 2026-04-28 — wiki/design/v2-analog-input. Config-overridable via
# `axis_centers` since recalibration can shift these.
DEFAULT_AXIS_CENTERS: dict[str, int] = {
    "L_STICK_X_AXIS": 118,  # positive = right
    "L_STICK_Y_AXIS": 434,  # positive = up
    "R_STICK_X_AXIS": 280,  # positive = right
    "R_STICK_Y_AXIS": -336,  # positive = up
}

_SURFACES = ("pantilt", "zoom")


def apply_curve(t: float, curve: str) -> float:
    """Map a normalized magnitude 0..1 through the response curve.

    The same three curves the framework already knows (analog_settings).
    """
    if curve == "quadratic":
        return t * t
    if curve == "s_curve":
        return t * t * (3.0 - 2.0 * t)
    return t  # linear (default)


class PtzViscaEngine(Engine):
    """Drive one camera's pan/tilt/zoom from one hand, with full stop-safety."""

    type_name = "ptz_visca"

    def __init__(
        self,
        name: str,
        config: dict,
        midi_out: MidiOut,
        *,
        clock: Callable[[], float] = time.monotonic,
        sender: "PtzViscaSender | None" = None,
    ) -> None:
        super().__init__(name, config, midi_out, clock=clock)

        # --- transport / network (config-driven, never hardcoded) ----------
        self._camera_nic_ip = str(config.get("camera_nic_ip", "192.168.0.100"))
        self._visca_port = int(config.get("visca_port", 52381))
        self._cameras: dict[str, str] = {
            str(k): str(v) for k, v in config.get("cameras", {}).items()
        }

        # --- mapping knobs -------------------------------------------------
        self._deadzone = int(config.get("deadzone", 3500))
        self._input_max = int(config.get("input_max", 32767))
        self._curve = str(config.get("curve", "linear"))
        self._pan_speed_max = int(config.get("pan_speed_max", 24))
        self._tilt_speed_max = int(config.get("tilt_speed_max", 20))
        self._zoom_speed_max = int(config.get("zoom_speed_max", 7))
        self._invert_pan = bool(config.get("invert_pan", False))
        self._invert_tilt = bool(config.get("invert_tilt", False))
        self._zoom_deadzone = int(config.get("zoom_deadzone", self._deadzone))
        self._trigger_max = int(config.get("trigger_max", 32767))

        centers = dict(DEFAULT_AXIS_CENTERS)
        centers.update(
            {str(k): int(v) for k, v in config.get("axis_centers", {}).items()}
        )
        self._axis_centers = centers

        # --- stop-safety knobs ---------------------------------------------
        self._redundant_stops = int(config.get("redundant_stops", 3))
        self._drop_timeout_ms = int(config.get("drop_timeout_ms", 250))
        self._stream_hz = int(config.get("stream_hz", 60))

        # --- camera-select (locked + conflict-audited; UNUSED until v2) ----
        # select_channel/left/right CCs (14 / 94 / 95) live in the canonical
        # config from the start so the allocation stays self-documenting.
        self._select_channel = int(config.get("select_channel", 14))
        self._left_select_cc = int(config.get("left_select_cc", 94))
        self._right_select_cc = int(config.get("right_select_cc", 95))

        # --- global movement-speed control (spec ptz-global-speed) ----------
        # Two feedback CCs scale the *ceilings* the mapping math uses, leaving
        # the deflection curve and stop-safety untouched. The scales are
        # persistent state (NOT leased), default 1.0 = full configured ceiling
        # (identical to v1 until a TouchOSC fader / Deck control moves them).
        # Global across every group/camera. Floors are config so a venue can
        # set a higher minimum (e.g. never crawl below speed 4). CC 92/93 ch14
        # sit clear of the audited ch14 map (audio 100-109, autopilot 60-89,
        # sync 90-91, select 94/95, global_color 99).
        self._speed_control_channel = int(config.get("speed_control_channel", 14))
        self._pan_tilt_speed_cc = int(config.get("pan_tilt_speed_cc", 92))
        self._zoom_speed_cc = int(config.get("zoom_speed_cc", 93))
        self._pan_speed_floor = int(config.get("pan_speed_floor", 1))
        self._tilt_speed_floor = int(config.get("tilt_speed_floor", 1))
        self._zoom_speed_floor = int(config.get("zoom_speed_floor", 1))
        self._pan_tilt_scale = 1.0
        self._zoom_scale = 1.0

        # --- control groups -------------------------------------------------
        self._groups: dict[str, dict] = {
            str(gname): dict(gcfg) for gname, gcfg in config.get("groups", {}).items()
        }
        # Per-group current target camera IP (v1: fixed at startup_camera).
        self._targets: dict[str, "str | None"] = {}
        for gname, gcfg in self._groups.items():
            cam_key = str(gcfg.get("startup_camera", 1))
            self._targets[gname] = self._cameras.get(cam_key)

        # Axis-action -> (group, "x"/"y") and zoom-axis -> group lookups.
        self._stick_axis_to_group: dict[str, tuple[str, str]] = {}
        self._zoom_axis_to_group: dict[str, str] = {}
        for gname, gcfg in self._groups.items():
            if gcfg.get("stick_x"):
                self._stick_axis_to_group[str(gcfg["stick_x"])] = (gname, "x")
            if gcfg.get("stick_y"):
                self._stick_axis_to_group[str(gcfg["stick_y"])] = (gname, "y")
            if gcfg.get("zoom_axis"):
                self._zoom_axis_to_group[str(gcfg["zoom_axis"])] = gname

        # --- motion + safety state (per group) -----------------------------
        # _pan/_tilt hold (speed, direction-nibble); direction == PT_STOP when
        # the axis is within deadzone. _centered is the edge-latch for the
        # redundant stop burst; _moving feeds the drop watchdog; _last_axis_time
        # is the staleness clock per surface.
        self._pan: dict[str, tuple[int, int]] = {}
        self._tilt: dict[str, tuple[int, int]] = {}
        self._zoom_speed: dict[str, int] = {}
        self._zoom_inverted: dict[str, bool] = {}
        self._centered: dict[str, dict[str, bool]] = {}
        self._moving: dict[str, dict[str, bool]] = {}
        self._last_axis_time: dict[str, dict[str, float]] = {}
        for gname in self._groups:
            self._pan[gname] = (0, PT_STOP)
            self._tilt[gname] = (0, PT_STOP)
            self._zoom_speed[gname] = 0
            self._zoom_inverted[gname] = False
            self._centered[gname] = {s: True for s in _SURFACES}
            self._moving[gname] = {s: False for s in _SURFACES}
            self._last_axis_time[gname] = {s: 0.0 for s in _SURFACES}

        self._last_stop_reason: "str | None" = None
        self._streaming = False

        # --- VISCA sender (lazy-safe: degrade to None without the dongle) ---
        if sender is not None:
            self._sender: "PtzViscaSender | None" = sender
        else:
            try:
                self._sender = PtzViscaSender(self._camera_nic_ip, self._visca_port)
            except OSError:
                LOGGER.warning(
                    "ptz_visca: VISCA socket bind to %s failed (camera NIC absent?); "
                    "sender unbound — engine loads but sends nothing",
                    self._camera_nic_ip,
                )
                self._sender = None

    # ------------------------------------------------------------------
    # Helpers

    def _target_ip(self, group: str) -> "str | None":
        return self._targets.get(group)

    # ------------------------------------------------------------------
    # Global movement-speed scaling (CC-driven, persistent)

    @staticmethod
    def _lerp(floor: float, top: float, s: float) -> float:
        return floor + (top - floor) * s

    def _eff_pan_max(self) -> int:
        return max(1, round(self._lerp(self._pan_speed_floor, self._pan_speed_max, self._pan_tilt_scale)))

    def _eff_tilt_max(self) -> int:
        return max(1, round(self._lerp(self._tilt_speed_floor, self._tilt_speed_max, self._pan_tilt_scale)))

    def _eff_zoom_max(self) -> int:
        return max(1, round(self._lerp(self._zoom_speed_floor, self._zoom_speed_max, self._zoom_scale)))

    def on_midi_in(self, channel: int, cc: int, value: int, now: float) -> None:
        """Consume the two global speed-ceiling CCs on the feedback port.

        CC 0..127 -> 0..1 scale, lerped between the config floor and the
        configured ``*_speed_max`` to get the effective ceiling. Persistent
        state (holds until changed); ignores any other channel/CC. A held
        stick/trigger streams axis events at ``stream_hz``, so a new scale
        applies on the next event (<~16 ms) — no forced re-emit needed.
        Stop-safety is untouched: scaling to the floor is a crawl, never a
        disabled stop.
        """
        if channel != self._speed_control_channel:
            return
        scale = min(1.0, max(0.0, value / 127.0))
        if cc == self._pan_tilt_speed_cc:
            self._pan_tilt_scale = scale
        elif cc == self._zoom_speed_cc:
            self._zoom_scale = scale

    def axis_to_speed(self, raw: int, center: int, speed_max: int) -> tuple[int, int]:
        """Map a raw signed axis value to a (speed, sign) pair.

        Subtracts the calibrated center, applies deadzone + curve, scales to a
        1-based VISCA speed byte. Returns (0, 0) within the deadzone — the
        caller emits STOP for that axis. VISCA speed bytes are 1-based: just
        past the deadzone yields speed 1, full deflection yields ``speed_max``.
        """
        v = raw - center
        mag = abs(v)
        if mag <= self._deadzone:
            return 0, 0
        span = self._input_max - self._deadzone
        t = (mag - self._deadzone) / span if span > 0 else 1.0
        t = min(1.0, max(0.0, t))
        t = apply_curve(t, self._curve)
        speed = 1 + round(t * (speed_max - 1))
        sign = 1 if v > 0 else -1
        return speed, sign

    def trigger_to_zoom_speed(self, raw: int) -> int:
        """Map an unsigned trigger value (0..trigger_max, 0=released) to 0..max.

        0 means STOP; a moving zoom is 1..zoom_speed_max.
        """
        if raw <= self._zoom_deadzone:
            return 0
        span = self._trigger_max - self._zoom_deadzone
        t = min(1.0, (raw - self._zoom_deadzone) / span) if span > 0 else 1.0
        t = max(0.0, t)
        t = apply_curve(t, self._curve)
        return 1 + round(t * (self._eff_zoom_max() - 1))

    def _pan_dir(self, sign: int) -> int:
        # +x = right by default; invert_pan flips it.
        return PAN_RIGHT if ((sign > 0) ^ self._invert_pan) else PAN_LEFT

    def _tilt_dir(self, sign: int) -> int:
        # +y = up by default (direct tilt); invert_tilt flips it.
        return TILT_UP if ((sign > 0) ^ self._invert_tilt) else TILT_DOWN

    # ------------------------------------------------------------------
    # Axis handling (pan/tilt + zoom)

    def on_axis_event(self, action: str, value: int, now: float) -> None:
        stick = self._stick_axis_to_group.get(action)
        if stick is not None:
            group, axis = stick
            self._handle_stick_axis(group, axis, value, now)
            return
        zgroup = self._zoom_axis_to_group.get(action)
        if zgroup is not None:
            self._handle_zoom_axis(zgroup, value, now)

    def _handle_stick_axis(self, group: str, axis: str, value: int, now: float) -> None:
        gcfg = self._groups[group]
        if axis == "x":
            center = self._axis_centers.get(str(gcfg.get("stick_x")), 0)
            speed, sign = self.axis_to_speed(value, center, self._eff_pan_max())
            self._pan[group] = (0, PT_STOP) if speed == 0 else (speed, self._pan_dir(sign))
        else:
            center = self._axis_centers.get(str(gcfg.get("stick_y")), 0)
            speed, sign = self.axis_to_speed(value, center, self._eff_tilt_max())
            self._tilt[group] = (0, PT_STOP) if speed == 0 else (speed, self._tilt_dir(sign))
        self._emit_drive(group, now)

    def _emit_drive(self, group: str, now: float) -> None:
        """Emit a combined Pan-tiltDrive frame, or a latched STOP on center."""
        p_speed, p_dir = self._pan[group]
        t_speed, t_dir = self._tilt[group]
        if p_dir == PT_STOP and t_dir == PT_STOP:
            self._enter_center(group, "pantilt", "center")
            return
        ip = self._target_ip(group)
        self._centered[group]["pantilt"] = False
        self._moving[group]["pantilt"] = True
        self._last_axis_time[group]["pantilt"] = now
        if self._sender is not None and ip is not None:
            # speed `or 1` keeps a STOP-nibble axis's speed byte in range.
            self._sender.send_pantilt(ip, p_speed or 1, t_speed or 1, p_dir, t_dir)
        self._update_streaming()

    def _handle_zoom_axis(self, group: str, value: int, now: float) -> None:
        speed = self.trigger_to_zoom_speed(value)
        self._zoom_speed[group] = speed
        if speed == 0:
            self._enter_center(group, "zoom", "center")
            return
        self._centered[group]["zoom"] = False
        self._moving[group]["zoom"] = True
        self._last_axis_time[group]["zoom"] = now
        self._emit_zoom(group)
        self._update_streaming()

    def _emit_zoom(self, group: str) -> None:
        speed = self._zoom_speed[group]
        ip = self._target_ip(group)
        if self._sender is None or ip is None:
            return
        if speed == 0:
            self._sender.send_zoom(ip, "stop", 0)
        else:
            direction = "out" if self._zoom_inverted.get(group) else "in"
            self._sender.send_zoom(ip, direction, speed)

    # ------------------------------------------------------------------
    # Bumper hold-to-invert (leased-hold modifier)

    def on_note_in(self, channel: int, note: int, velocity: int, now: float) -> None:
        for group, gcfg in self._groups.items():
            n = gcfg.get("zoom_invert_note")
            if n is None or note != n:
                continue
            ch = gcfg.get("zoom_invert_channel")
            if ch is not None and channel != ch:
                continue
            self._zoom_inverted[group] = velocity > 0  # held = invert to OUT
            # Re-emit so a held trigger flips direction immediately, no re-move.
            if self._zoom_speed[group] > 0:
                self._emit_zoom(group)

    # ------------------------------------------------------------------
    # Stop-safety

    def _enter_center(self, group: str, surface: str, reason: str) -> None:
        """Latch a surface centered; send the redundant STOP burst on the edge."""
        was_centered = self._centered[group][surface]
        self._centered[group][surface] = True
        self._moving[group][surface] = False
        if not was_centered:
            self._send_stop_burst(group, surface, reason)
        self._update_streaming()

    def _send_stop_burst(self, group: str, surface: str, reason: str) -> None:
        ip = self._target_ip(group)
        if self._sender is not None and ip is not None:
            for _ in range(self._redundant_stops):
                if surface == "pantilt":
                    self._sender.send_stop(ip)
                else:
                    self._sender.send_zoom_stop(ip)
        self._last_stop_reason = reason

    def tick(self, now: float) -> None:
        """Drop watchdog: if a moving surface goes stale, inject STOP.

        Local time check only — no network reads, ADR-0001 clean.
        """
        for group in self._groups:
            for surface in _SURFACES:
                if not self._moving[group][surface]:
                    continue
                stale_ms = (now - self._last_axis_time[group][surface]) * 1000.0
                if stale_ms > self._drop_timeout_ms:
                    self._send_stop_burst(group, surface, "drop")
                    self._centered[group][surface] = True
                    self._moving[group][surface] = False
                    # Clear motion state so it doesn't re-fire until a fresh
                    # axis event restarts (and re-arms) the surface.
                    if surface == "pantilt":
                        self._pan[group] = (0, PT_STOP)
                        self._tilt[group] = (0, PT_STOP)
                    else:
                        self._zoom_speed[group] = 0
        self._update_streaming()

    def tick_interval_seconds(self) -> float:
        """Pull the loop at the stream cadence, capped to the watchdog window.

        Always advertised (the registry skips ticks for inactive engines), so
        the watchdog stays responsive whenever the engine is active.
        """
        base = 1.0 / self._stream_hz if self._stream_hz > 0 else 0.125
        watchdog = (self._drop_timeout_ms / 1000.0) / 2.0
        return min(base, watchdog)

    def set_active(self, active: bool) -> None:
        """Stop every camera on an active->inactive transition (toggle-off).

        The registry flips ``active`` without teardown, so a held stick at
        toggle-off would otherwise strand a moving camera. Analogous to
        ``l_stick_layer._release_active_ccs``.
        """
        was_active = self.active
        super().set_active(active)
        if was_active and not active:
            self._stop_all_groups("toggle")

    def shutdown(self) -> None:
        """Stop pan/tilt AND zoom on every group, then close the sender."""
        self._stop_all_groups("shutdown")
        if self._sender is not None:
            self._sender.close()

    def _stop_all_groups(self, reason: str) -> None:
        for group in self._groups:
            ip = self._target_ip(group)
            if self._sender is not None and ip is not None:
                for _ in range(self._redundant_stops):
                    self._sender.send_stop(ip)
                    self._sender.send_zoom_stop(ip)
            self._centered[group] = {s: True for s in _SURFACES}
            self._moving[group] = {s: False for s in _SURFACES}
            self._pan[group] = (0, PT_STOP)
            self._tilt[group] = (0, PT_STOP)
            self._zoom_speed[group] = 0
        self._last_stop_reason = reason
        self._streaming = False

    def _update_streaming(self) -> None:
        self._streaming = any(
            self._moving[g][s] for g in self._groups for s in _SURFACES
        )

    # ------------------------------------------------------------------
    # Status

    def status(self) -> dict:
        s = super().status()  # {"name", "type", "active"}
        s.update(
            {
                "camera_nic_ip": self._camera_nic_ip,
                "sender": "bound" if self._sender is not None else "unbound",
                "targets": dict(self._targets),
                "streaming": self._streaming,
                "moving": {g: dict(self._moving[g]) for g in self._groups},
                "last_stop_reason": self._last_stop_reason,
                "pan_tilt_speed_scale": self._pan_tilt_scale,
                "zoom_speed_scale": self._zoom_scale,
                "effective_speed_max": {
                    "pan": self._eff_pan_max(),
                    "tilt": self._eff_tilt_max(),
                    "zoom": self._eff_zoom_max(),
                },
            }
        )
        return s
