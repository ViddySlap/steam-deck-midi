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

5. **Bind the camera network only while active, and recover by itself.** No
   socket exists until the engine is active (the PTZ preset). While active and
   unbound, ``tick`` retries the bind every ``BIND_RETRY_SECONDS``; a send
   OSError (dongle pulled) drops the socket back into that loop. Deactivate /
   shutdown stops every camera, then closes the socket. ``camera_nic_ip`` is an
   explicit IPv4 (always wins) or ``auto`` / blank: the source address the OS
   routes to the first camera, accepted only inside that camera's /24.

Camera/VISCA/byte facts: wiki/reference/ptz-cameras.md. The VISCA transport
lives in ``visca_sender.py``; this engine only decides *what* to send.
"""

from __future__ import annotations

import errno
import ipaddress
import logging
import socket
from typing import Callable

from windows.engines.base import Engine, clamp_tick_hz
from windows.engines.osc_client import OscClient
from windows.engines.visca_sender import (
    PAN_LEFT,
    PAN_RIGHT,
    PT_STOP,
    TILT_DOWN,
    TILT_UP,
    PtzViscaSender,
)
from windows.midi import MidiOut
from windows.clock import now as clock_now

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

# Camera-network sender states (status()["sender"]).
SENDER_CONNECTED = "connected"
SENDER_WAITING = "waiting"
SENDER_INACTIVE = "inactive"

# While active and unbound, retry the camera-network bind this often.
BIND_RETRY_SECONDS = 2.0

# How long a speed value written to Resolume is remembered so its CC echo can
# be recognised and dropped (Resolume echoes within a few ms).
SPEED_ECHO_SECONDS = 1.0

AUTO_NIC = "auto"

# Send errors that mean this laptop's camera-network address is gone (dongle
# pulled, adapter down). Only these drop the socket into the rebind loop; a
# per-camera error (one BirdDog powered off: host unreachable) is swallowed so
# the other cameras keep their control. Windows reports WSA codes in errno.
_NETWORK_GONE_ERRNOS = frozenset({
    errno.EADDRNOTAVAIL, errno.ENETDOWN, errno.ENETUNREACH,
    10049, 10050, 10051,  # WSAEADDRNOTAVAIL, WSAENETDOWN, WSAENETUNREACH
})


def is_auto_nic(value: object) -> bool:
    """True for the ``auto`` setting; blank (or null) means auto too."""
    return value is None or str(value).strip().lower() in ("", AUTO_NIC)


def is_ipv4(value: object) -> bool:
    """A dotted-quad IPv4 string (``192.168.0.203``), nothing else."""
    if not isinstance(value, str) or value.count(".") != 3:
        return False
    try:
        ipaddress.IPv4Address(value)
    except ValueError:
        return False
    return True


def config_error(spec: dict) -> "str | None":
    """Name the first bad camera-network field in a stanza, or None.

    Used by ``engine_config_api.put_engine_config`` so a bad PUT answers 400
    before anything is written. The message starts with the field name.
    """
    if "camera_nic_ip" in spec:
        raw = spec["camera_nic_ip"]
        if raw is not None and not isinstance(raw, str):
            return f"camera_nic_ip must be an IPv4 address, auto, or blank (got {raw!r})"
        if not is_auto_nic(raw) and not is_ipv4(str(raw).strip()):
            return (f"camera_nic_ip must be an IPv4 address like 192.168.0.100, "
                    f"auto, or blank (got {raw!r})")
    if "cameras" in spec:
        cams = spec["cameras"]
        if not isinstance(cams, dict):
            return "cameras must be an object of camera number -> IPv4 address"
        for key, ip in cams.items():
            if not is_ipv4(ip):
                return (f"cameras.{key} must be an IPv4 address like "
                        f"192.168.0.203 (got {ip!r})")
    deadzone_keys = ("deadzone", "deadzone_untouched")
    for key in deadzone_keys:
        if key in spec and not _is_deadzone(spec[key]):
            return f"{key} must be a whole number from 0 to 32766 (got {spec[key]!r})"
    groups = spec.get("groups", {})
    if isinstance(groups, dict):
        for gname, gcfg in groups.items():
            if not isinstance(gcfg, dict):
                continue
            for key in deadzone_keys:
                if key in gcfg and not _is_deadzone(gcfg[key]):
                    return (f"groups.{gname}.{key} must be a whole number from 0 to "
                            f"32766 (got {gcfg[key]!r})")
            touch = gcfg.get("touch_action")
            if touch is not None and not (isinstance(touch, str) and touch):
                return f"groups.{gname}.touch_action must be an action name or null"
    return None


def _is_deadzone(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 32767


def route_source_ip(camera_ip: str, port: int = 52381) -> str:
    """The local address the OS would send from to reach ``camera_ip``.

    ``connect()`` on a UDP socket only picks a route; no packet is sent.
    Raises OSError when there is no route at all.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((camera_ip, int(port)))
        return str(sock.getsockname()[0])
    finally:
        sock.close()


def _default_sender_factory(ip: str, port: int) -> PtzViscaSender:
    return PtzViscaSender(ip, port, raise_on_error=True)


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
        clock: Callable[[], float] = clock_now,
        sender: "PtzViscaSender | None" = None,
        osc_client: "OscClient | None" = None,
        sender_factory: "Callable[[str, int], PtzViscaSender] | None" = None,
        source_resolver: "Callable[[str], str] | None" = None,
    ) -> None:
        super().__init__(name, config, midi_out, clock=clock)

        # --- transport / network (config-driven, never hardcoded) ----------
        # camera_nic_ip: explicit IPv4 (always wins) or "auto" / blank.
        raw_nic = config.get("camera_nic_ip", "192.168.0.100")
        self._camera_nic_ip = "" if raw_nic is None else str(raw_nic).strip()
        self._nic_auto = is_auto_nic(self._camera_nic_ip)
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
        # Touch-aware stick deadzone: while the stick's touch sensor reads
        # untouched, the wider `deadzone_untouched` applies, so a stick that
        # springs back short of center (measured 4,178-4,517 on 2026-10-16)
        # stops the camera instead of creeping. Defaults to `deadzone`, so a
        # config without it behaves exactly as before.
        self._deadzone_untouched = int(config.get("deadzone_untouched", self._deadzone))
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
        self._stream_hz = clamp_tick_hz(config.get("stream_hz", 60), default=60.0)

        # --- camera-select (locked + conflict-audited; UNUSED until v2) ----
        # select_channel/left/right CCs (14 / 94 / 95) live in the canonical
        # config from the start so the allocation stays self-documenting.
        self._select_channel = int(config.get("select_channel", 14))
        self._left_select_cc = int(config.get("left_select_cc", 94))
        self._right_select_cc = int(config.get("right_select_cc", 95))

        # Physical Deck-button select (notes -> the same _select_camera core as
        # the TouchOSC/CC path). `discrete` maps one note per (group, index);
        # `cycle` advances a side through its cameras on each press. The notes
        # are placeholders until Ben assigns them in the PTZ SteamInput layout.
        self._physical_select: dict = dict(config.get("physical_select", {}))

        # --- per-side movement-speed control (spec ptz-global-speed;
        #     per-side build 2026-06-03) ---------------------------------------
        # Feedback CCs scale the *ceilings* the mapping math uses, leaving the
        # deflection curve and stop-safety untouched. The scales are persistent
        # state (NOT leased), default 1.0 = full configured ceiling (identical
        # to v1 until a TouchOSC fader / Deck control moves them). Each hand
        # scales independently: the left group (left stick + trigger) and the
        # right group own separate pan/tilt + zoom scales, so the two cameras
        # can run at different speeds and be MIDI-mapped separately. CC 92/93 =
        # left pan/tilt + zoom, CC 96/97 = right pan/tilt + zoom — all on ch14,
        # clear of the audited map (audio 100-109, autopilot 60-89, sync 90-91,
        # select 94/95, global_color 99). Floors are config so a venue can set a
        # higher minimum (e.g. never crawl below speed 4).
        self._speed_control_channel = int(config.get("speed_control_channel", 14))
        # Old global keys seed the left group for backward compatibility.
        self._left_pan_tilt_speed_cc = int(
            config.get("left_pan_tilt_speed_cc", config.get("pan_tilt_speed_cc", 92))
        )
        self._left_zoom_speed_cc = int(
            config.get("left_zoom_speed_cc", config.get("zoom_speed_cc", 93))
        )
        self._right_pan_tilt_speed_cc = int(config.get("right_pan_tilt_speed_cc", 96))
        self._right_zoom_speed_cc = int(config.get("right_zoom_speed_cc", 97))
        # CC -> (group, surface) dispatch for the speed-ceiling controls.
        self._speed_cc_map: dict[int, tuple[str, str]] = {
            self._left_pan_tilt_speed_cc: ("left", "pantilt"),
            self._left_zoom_speed_cc: ("left", "zoom"),
            self._right_pan_tilt_speed_cc: ("right", "pantilt"),
            self._right_zoom_speed_cc: ("right", "zoom"),
        }
        self._pan_speed_floor = int(config.get("pan_speed_floor", 1))
        self._tilt_speed_floor = int(config.get("tilt_speed_floor", 1))
        self._zoom_speed_floor = int(config.get("zoom_speed_floor", 1))
        # --- per-camera speed memory (Red West 2026-10-15) ------------------
        # The speed belongs to the CAMERA, not the stick: a speed CC sets the
        # scale of the camera its side is driving, and a side's ceilings come
        # from whichever camera it has selected. On a camera switch (and on a
        # periodic resync while nobody is touching that camera's fader) the
        # engine writes the camera's scales to the PTZ SELECT speed params, so
        # Resolume moves the TouchOSC faders to match. Each write comes back as
        # a speed CC (Wire On Change); those echoes are recognised by value and
        # dropped so they can never overwrite a camera or round it down.
        self._default_speed_scale = min(
            1.0, max(0.0, float(config.get("default_speed_scale", 0.5)))
        )
        self._speed_osc_base = str(
            config.get(
                "speed_osc_base",
                "/composition/video/effects/ptzselect/effect/speed",
            )
        )
        self._speed_resync_seconds = float(config.get("speed_resync_seconds", 2.0))
        self._speed_idle_seconds = float(config.get("speed_idle_seconds", 3.0))
        self._speed_cc_for: dict[tuple[str, str], int] = {
            v: k for k, v in self._speed_cc_map.items()
        }
        self._cam_pan_tilt_scale: dict[str, float] = {}
        self._cam_zoom_scale: dict[str, float] = {}
        self._cam_speed_touched: dict[str, float] = {}
        self._speed_echoes: dict[int, list[tuple[int, float]]] = {}
        self._next_speed_resync: "float | None" = None

        # --- per-side zoom-direction toggle (latching; spec ptz-zoom-dir-feedback
        #     2026-06-03) -------------------------------------------------------
        # Zoom direction (IN default / OUT) is a *latching* per-side state set
        # three ways that all funnel through `_set_zoom_inverted`: the same-side
        # bumper (L1/R1 note -> TAP toggle), a TouchOSC IN/OUT button pair (CC ->
        # absolute), and the engine's own broadcast. The engine is the source of
        # truth: on every *edge* it writes the absolute state out over OSC to the
        # PTZ SELECT effect param, which Resolume echoes to the TouchOSC indicator
        # (the osc_sync feedback pattern). Edge-triggered + idempotent absolute
        # set => the OSC->Resolume->Wire-CC->on_midi_in round-trip and the
        # TouchOSC echo cannot oscillate. CC 98/99 on ch14 are free of the active
        # PTZ engines (ptz 92-97, autopilot_ptz 47-52, osc_sync 90); they reuse a
        # disabled-in-PTZ global_color CC by the same intentional-conflict rule as
        # the speed CCs. Resolume OSC input is 127.0.0.1:7000 (mirrors osc_sync).
        self._left_zoom_dir_cc = int(config.get("left_zoom_dir_cc", 98))
        self._right_zoom_dir_cc = int(config.get("right_zoom_dir_cc", 99))
        self._zoom_dir_cc_map: dict[int, str] = {
            self._left_zoom_dir_cc: "left",
            self._right_zoom_dir_cc: "right",
        }
        self._zoom_dir_osc_base = str(
            config.get(
                "zoom_dir_osc_base",
                "/composition/video/effects/ptzselect/effect/zoomdir",
            )
        )
        # Physical (Deck-button) selects are echoed here so the TouchOSC Cam
        # buttons and the PTZ SELECT dashboard follow: <base>/<group>select.
        self._select_osc_base = str(
            config.get(
                "select_osc_base",
                "/composition/video/effects/ptzselect/effect/select",
            )
        )
        osc_cfg = config.get("osc", {})
        self._osc = osc_client or OscClient(
            str(osc_cfg.get("host", "127.0.0.1")),
            int(osc_cfg.get("port", 7000)),
        )

        # --- control groups -------------------------------------------------
        self._groups: dict[str, dict] = {
            str(gname): dict(gcfg) for gname, gcfg in config.get("groups", {}).items()
        }
        # Every camera starts at the default speed scale.
        self._cam_pan_tilt_scale = {c: self._default_speed_scale for c in self._cameras}
        self._cam_zoom_scale = {c: self._default_speed_scale for c in self._cameras}
        # Per-group current target camera IP + selected index. Startup is the
        # group's `startup_camera`; the select CCs (and physical buttons) flip
        # both at runtime via `_select_camera`.
        self._targets: dict[str, "str | None"] = {}
        self._selected_index: dict[str, int] = {}
        for gname, gcfg in self._groups.items():
            idx = int(gcfg.get("startup_camera", 1))
            self._selected_index[gname] = idx
            self._targets[gname] = self._cameras.get(str(idx))

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

        # Per-stick deadzones (group keys override the globals) and the
        # touch-aware switch. A group with no `touch_action` always uses its
        # touched deadzone, which is the pre-0.5.4 behaviour.
        self._touch_action_to_group: dict[str, str] = {}
        self._group_deadzone: dict[str, int] = {}
        self._group_deadzone_untouched: dict[str, int] = {}
        self._touched: dict[str, bool] = {}
        # After a release the wide deadzone stays latched until the stick is
        # back inside the touched deadzone or pushed past the untouched one,
        # so touching a stick parked at 4,500 does not start a creep.
        self._wide_latch: dict[str, bool] = {}
        self._last_stick_raw: dict[str, dict[str, "int | None"]] = {}
        for gname, gcfg in self._groups.items():
            dz = int(gcfg.get("deadzone", self._deadzone))
            self._group_deadzone[gname] = dz
            self._group_deadzone_untouched[gname] = int(
                gcfg.get("deadzone_untouched",
                         config.get("deadzone_untouched", dz)))
            if gcfg.get("touch_action"):
                self._touch_action_to_group[str(gcfg["touch_action"])] = gname
            self._touched[gname] = False
            self._wide_latch[gname] = True
            self._last_stick_raw[gname] = {"x": None, "y": None}

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

        # --- VISCA sender: bound only while active (see _try_bind) ----------
        # No socket in __init__: the PUT isolation probe and inactive presets
        # never touch the camera network. `sender` (tests) is a pre-built
        # sender: adopted as connected when active, and reused on rebind.
        if sender_factory is not None:
            self._sender_factory = sender_factory
        elif sender is not None:
            self._sender_factory = lambda _ip, _port: sender
        else:
            self._sender_factory = _default_sender_factory
        self._source_resolver = source_resolver or (
            lambda ip: route_source_ip(ip, self._visca_port)
        )
        self._sender: "PtzViscaSender | None" = None
        self._bound_ip: "str | None" = None
        self._last_bind_error: "str | None" = None
        self._last_bind_attempt: "float | None" = None
        self._announced_state: "str | None" = None
        self._releasing = False
        self._shut_down = False
        if not self.active:
            self._sender_state = SENDER_INACTIVE
        elif sender is not None:
            self._sender = sender
            self._bound_ip = None if self._nic_auto else self._camera_nic_ip
            self._sender_state = SENDER_CONNECTED
        else:
            # The first tick (or set_active(True)) binds immediately.
            self._sender_state = SENDER_WAITING

    # ------------------------------------------------------------------
    # Helpers

    def _target_ip(self, group: str) -> "str | None":
        return self._targets.get(group)

    # ------------------------------------------------------------------
    # Camera network (bind while active, retry, recover)

    def _first_camera_ip(self) -> "str | None":
        def order(key: str) -> tuple:
            return (0, int(key), key) if key.isdigit() else (1, 0, key)
        for key in sorted(self._cameras, key=order):
            if is_ipv4(self._cameras[key]):
                return self._cameras[key]
        return None

    def _resolve_source_ip(self) -> "tuple[str | None, str | None]":
        """(source ip, None) to bind, or (None, why not)."""
        if not self._nic_auto:
            return self._camera_nic_ip, None
        cam = self._first_camera_ip()
        if cam is None:
            return None, "auto: no camera address configured"
        try:
            src = self._source_resolver(cam)
        except (OSError, ValueError) as exc:
            return None, f"auto: no route to camera {cam} ({exc})"
        if not is_ipv4(src) or ipaddress.IPv4Address(src) not in ipaddress.IPv4Network(
            f"{cam}/24", strict=False
        ):
            return None, f"auto: no local address on the {cam} /24 network (route uses {src})"
        return src, None

    def _try_bind(self, now: float) -> bool:
        """One bind attempt. Never raises; logs only on a state change."""
        if self._shut_down or not self.active:
            return False
        self._last_bind_attempt = now
        ip, why = self._resolve_source_ip()
        if ip is None:
            self._set_sender_state(SENDER_WAITING, why)
            return False
        try:
            sender = self._sender_factory(ip, self._visca_port)
        except Exception as exc:  # noqa: BLE001 - OSError expected; never raise from a hook
            self._set_sender_state(SENDER_WAITING, f"{ip} not available: {exc}")
            return False
        self._sender = sender
        self._bound_ip = ip
        self._set_sender_state(SENDER_CONNECTED, None)
        return True

    def _set_sender_state(self, state: str, error: "str | None") -> None:
        self._sender_state = state
        self._last_bind_error = error
        if state == self._announced_state:
            return
        previous, self._announced_state = self._announced_state, state
        if state == SENDER_CONNECTED:
            LOGGER.info("ptz_visca: camera network connected via %s", self._bound_ip)
        elif state == SENDER_WAITING:
            LOGGER.warning("ptz_visca: waiting for camera network (%s)", error)
        elif previous is not None:
            LOGGER.info("ptz_visca: camera network released (PTZ inactive)")

    def _close_sender(self) -> None:
        sender, self._sender, self._bound_ip = self._sender, None, None
        if sender is not None:
            try:
                sender.close()
            except Exception:  # noqa: BLE001
                LOGGER.debug("ptz_visca: sender close failed", exc_info=True)

    def _send(self, method: str, *args) -> None:
        """Call one sender method; a send OSError drops back to the retry loop."""
        sender = self._sender
        if sender is None:
            return
        try:
            getattr(sender, method)(*args)
        except OSError as exc:
            if exc.errno not in _NETWORK_GONE_ERRNOS:
                LOGGER.debug("ptz_visca: %s failed for one camera: %s", method, exc)
                return
            via = self._bound_ip
            self._close_sender()
            if self._releasing:
                return
            # tick makes the next bind attempt BIND_RETRY_SECONDS from now.
            self._last_bind_attempt = self._clock()
            self._set_sender_state(SENDER_WAITING, f"send via {via} failed: {exc}")

    def _release_network(self, reason: str) -> None:
        """Stop every camera, then close the socket and go inactive."""
        self._releasing = True
        try:
            self._stop_all_groups(reason)
        finally:
            self._releasing = False
        self._close_sender()
        self._last_bind_attempt = None
        self._set_sender_state(SENDER_INACTIVE, None)

    # ------------------------------------------------------------------
    # Global movement-speed scaling (CC-driven, persistent)

    @staticmethod
    def _lerp(floor: float, top: float, s: float) -> float:
        return floor + (top - floor) * s

    def _selected_cam(self, group: str) -> str:
        return str(self._selected_index.get(group, 1))

    def _scale_table(self, surface: str) -> dict[str, float]:
        return self._cam_pan_tilt_scale if surface == "pantilt" else self._cam_zoom_scale

    def _group_scale(self, group: str, surface: str) -> float:
        """The scale of the camera ``group`` is driving, for ``surface``."""
        return self._scale_table(surface).get(
            self._selected_cam(group), self._default_speed_scale
        )

    @property
    def _pan_tilt_scale(self) -> dict[str, float]:
        """Per-side view of the per-camera pan/tilt scales (status + tests)."""
        return {g: self._group_scale(g, "pantilt") for g in self._groups}

    @property
    def _zoom_scale(self) -> dict[str, float]:
        """Per-side view of the per-camera zoom scales (status + tests)."""
        return {g: self._group_scale(g, "zoom") for g in self._groups}

    def _eff_pan_max(self, group: str) -> int:
        s = self._group_scale(group, "pantilt")
        return max(1, round(self._lerp(self._pan_speed_floor, self._pan_speed_max, s)))

    def _eff_tilt_max(self, group: str) -> int:
        s = self._group_scale(group, "pantilt")
        return max(1, round(self._lerp(self._tilt_speed_floor, self._tilt_speed_max, s)))

    def _eff_zoom_max(self, group: str) -> int:
        s = self._group_scale(group, "zoom")
        return max(1, round(self._lerp(self._zoom_speed_floor, self._zoom_speed_max, s)))

    def _set_camera_speed(self, group: str, surface: str, cc: int, value: int) -> None:
        """A speed CC sets the scale of the camera ``group`` is driving."""
        if group not in self._groups:
            return
        now = self._clock()
        if self._is_speed_echo(cc, value, now):
            return
        cam = self._selected_cam(group)
        self._scale_table(surface)[cam] = min(1.0, max(0.0, value / 127.0))
        self._cam_speed_touched[cam] = now

    def _is_speed_echo(self, cc: int, value: int, now: float) -> bool:
        """True (and consumed) if ``value`` is Resolume echoing our own write.

        Every value written in the last SPEED_ECHO_SECONDS is remembered per
        CC, so a late echo of an older write is caught too. +-1 covers the
        float -> CC rounding in the Wire patch.
        """
        pending = [(v, d) for v, d in self._speed_echoes.get(cc, []) if now <= d]
        hit = next((i for i, (v, _) in enumerate(pending) if abs(v - value) <= 1), None)
        if hit is not None:
            pending.pop(hit)
        self._speed_echoes[cc] = pending
        return hit is not None

    def _broadcast_speeds(self, group: str) -> None:
        """Write ``group``'s current camera speeds to the PTZ SELECT params."""
        if self._osc is None or group not in self._groups:
            return
        deadline = self._clock() + SPEED_ECHO_SECONDS
        for surface in ("pantilt", "zoom"):
            scale = self._group_scale(group, surface)
            self._osc.send(f"{self._speed_osc_base}/{group}{surface}speed", scale)
            cc = self._speed_cc_for.get((group, surface))
            if cc is not None:
                echoes = self._speed_echoes.setdefault(cc, [])
                echoes.append((round(scale * 127), deadline))
                del echoes[:-8]

    def _resync_speeds(self, now: float) -> None:
        """Re-assert every side's speeds unless its camera is being adjusted.

        Idempotent absolute state, so a Resolume restart or a dropped packet
        heals within one period. A camera whose fader moved in the last
        ``speed_idle_seconds`` is skipped so a drag is never fought.
        """
        for group in self._groups:
            touched = self._cam_speed_touched.get(self._selected_cam(group))
            if touched is not None and 0 <= now - touched < self._speed_idle_seconds:
                continue
            self._broadcast_speeds(group)

    def on_midi_in(self, channel: int, cc: int, value: int, now: float) -> None:
        """Consume the feedback-port CCs this engine owns (all on channel 14).

        Two CC families share the channel:

        * **Camera-select** (CC 94 LEFT / 95 RIGHT): ``value`` is the camera
          index 1/2/3; retarget that group via ``_select_camera`` (stop-then-
          retarget). The signal arrives on DECK_OUT (no loop — the engine emits
          VISCA over UDP, never MIDI).
        * **Per-side speed ceiling** (CC 92/93 left pan-tilt/zoom, 96/97 right):
          0..127 -> a persistent 0..1 scale for that group's surface, lerped
          between the config floor and the configured ``*_speed_max``. A held
          stick/trigger re-streams at ``stream_hz``, so a new scale applies on
          the next event (<~16 ms). Left and right scale independently.

        Anything else (other channel / unrelated CC) is ignored. Stop-safety is
        untouched: scaling to the floor is a crawl, never a disabled stop.
        """
        # --- camera-select (retarget a group) ---
        if channel == self._select_channel:
            if cc == self._left_select_cc:
                self._select_camera("left", value)
                return
            if cc == self._right_select_cc:
                self._select_camera("right", value)
                return
        # --- per-side speed-ceiling control ---
        if channel == self._speed_control_channel:
            entry = self._speed_cc_map.get(cc)
            if entry is not None:
                group, surface = entry
                self._set_camera_speed(group, surface, cc, value)
                return
            # --- per-side zoom-direction (absolute set from TouchOSC IN/OUT) ---
            dir_group = self._zoom_dir_cc_map.get(cc)
            if dir_group is not None:
                self._set_zoom_inverted(dir_group, value >= 64)
                return

    def _select_camera(self, group: str, index: int) -> None:
        """Shared select core (MIDI + physical buttons both call this).

        STOP the camera we're leaving *before* retargeting (pan/tilt and zoom
        are continuous — a mid-move switch would otherwise leave the deselected
        camera running away), then clear the group's surface latches so the new
        camera starts clean. No-op if the group is unknown, the index isn't a
        configured camera, or it's already the current target (no double-stop).
        """
        if group not in self._groups:
            return
        new_ip = self._cameras.get(str(index))
        if new_ip is None:
            return  # 0 / out-of-range / unconfigured index -> ignore
        old_ip = self._targets.get(group)
        if new_ip == old_ip:
            return  # already there -> no STOP, no state reset
        if old_ip is not None:
            for _ in range(self._redundant_stops):
                self._send("send_stop", old_ip)
                self._send("send_zoom_stop", old_ip)
        self._reset_surface_state(group)
        self._targets[group] = new_ip
        self._selected_index[group] = index
        self._last_stop_reason = "select"
        # The faders follow the camera: show the new camera's saved speeds.
        self._broadcast_speeds(group)

    def _reset_surface_state(self, group: str) -> None:
        """Clear a group's motion + stop-safety latches across a camera switch.

        The new camera receives nothing until the next axis event; a centered
        stick simply leaves it stopped. Clearing the watchdog timestamps stops
        a stale ``tick`` from firing a spurious drop-STOP at the new target.
        """
        self._pan[group] = (0, PT_STOP)
        self._tilt[group] = (0, PT_STOP)
        self._zoom_speed[group] = 0
        self._centered[group] = {s: True for s in _SURFACES}
        self._moving[group] = {s: False for s in _SURFACES}
        self._last_axis_time[group] = {s: 0.0 for s in _SURFACES}
        self._update_streaming()

    def axis_to_speed(self, raw: int, center: int, speed_max: int,
                      deadzone: "int | None" = None) -> tuple[int, int]:
        """Map a raw signed axis value to a (speed, sign) pair.

        Subtracts the calibrated center, applies deadzone + curve, scales to a
        1-based VISCA speed byte. Returns (0, 0) within the deadzone — the
        caller emits STOP for that axis. VISCA speed bytes are 1-based: just
        past the deadzone yields speed 1, full deflection yields ``speed_max``.
        ``deadzone`` defaults to the global ``deadzone``.
        """
        dz = self._deadzone if deadzone is None else deadzone
        v = raw - center
        mag = abs(v)
        if mag <= dz:
            return 0, 0
        span = self._input_max - dz
        t = (mag - dz) / span if span > 0 else 1.0
        t = min(1.0, max(0.0, t))
        t = apply_curve(t, self._curve)
        speed = 1 + round(t * (speed_max - 1))
        sign = 1 if v > 0 else -1
        return speed, sign

    def trigger_to_zoom_speed(self, raw: int, group: str) -> int:
        """Map an unsigned trigger value (0..trigger_max, 0=released) to 0..max.

        0 means STOP; a moving zoom is 1..zoom_speed_max, scaled by ``group``'s
        zoom-speed ceiling.
        """
        if raw <= self._zoom_deadzone:
            return 0
        span = self._trigger_max - self._zoom_deadzone
        t = min(1.0, (raw - self._zoom_deadzone) / span) if span > 0 else 1.0
        t = max(0.0, t)
        t = apply_curve(t, self._curve)
        return 1 + round(t * (self._eff_zoom_max(group) - 1))

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
        self._last_stick_raw[group][axis] = value
        self._update_wide_latch(group)
        self._apply_stick_axis(group, axis, value)
        self._emit_drive(group, now)

    def _apply_stick_axis(self, group: str, axis: str, value: int) -> None:
        gcfg = self._groups[group]
        dz = self._stick_deadzone(group)
        if axis == "x":
            center = self._axis_centers.get(str(gcfg.get("stick_x")), 0)
            speed, sign = self.axis_to_speed(value, center, self._eff_pan_max(group), dz)
            self._pan[group] = (0, PT_STOP) if speed == 0 else (speed, self._pan_dir(sign))
        else:
            center = self._axis_centers.get(str(gcfg.get("stick_y")), 0)
            speed, sign = self.axis_to_speed(value, center, self._eff_tilt_max(group), dz)
            self._tilt[group] = (0, PT_STOP) if speed == 0 else (speed, self._tilt_dir(sign))

    # ------------------------------------------------------------------
    # Touch-aware deadzone

    def _stick_deadzone(self, group: str) -> int:
        """The stick deadzone in force for ``group`` right now."""
        if group not in self._touch_action_to_group.values():
            return self._group_deadzone[group]
        if self._touched[group] and not self._wide_latch[group]:
            return self._group_deadzone[group]
        return self._group_deadzone_untouched[group]

    def _stick_offset(self, group: str) -> int:
        """Largest centered deflection of ``group``'s stick (0 if unknown)."""
        gcfg = self._groups[group]
        offset = 0
        for axis, key in (("x", "stick_x"), ("y", "stick_y")):
            raw = self._last_stick_raw[group][axis]
            if raw is not None:
                center = self._axis_centers.get(str(gcfg.get(key)), 0)
                offset = max(offset, abs(raw - center))
        return offset

    def _update_wide_latch(self, group: str) -> None:
        if not (self._touched[group] and self._wide_latch[group]):
            return
        offset = self._stick_offset(group)
        if (offset <= self._group_deadzone[group]
                or offset > self._group_deadzone_untouched[group]):
            self._wide_latch[group] = False

    def on_input_event(self, action: str, state: str, now: float) -> None:
        group = self._touch_action_to_group.get(action)
        if group is None:
            return
        touched = state == "down"
        if touched == self._touched[group]:
            return
        self._touched[group] = touched
        if touched:
            self._update_wide_latch(group)
        else:
            self._wide_latch[group] = True
        # The Deck sends no axis event while a released stick sits still, so
        # re-apply the new deadzone to the last position now. Only a moving
        # stick is re-evaluated: a touch change never starts motion (the drop
        # watchdog may have stopped it on purpose).
        if not self._moving[group]["pantilt"]:
            return
        before = (self._pan[group], self._tilt[group])
        for axis in ("x", "y"):
            raw = self._last_stick_raw[group][axis]
            if raw is not None:
                self._apply_stick_axis(group, axis, raw)
        if (self._pan[group], self._tilt[group]) == before:
            return
        stopping = self._pan[group][1] == PT_STOP and self._tilt[group][1] == PT_STOP
        if stopping:
            LOGGER.info("ptz_visca: %s stick %s, stopped at offset %d (deadzone %d)",
                        group, "touched" if touched else "released",
                        self._stick_offset(group), self._stick_deadzone(group))
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
        if ip is not None:
            # speed `or 1` keeps a STOP-nibble axis's speed byte in range.
            self._send("send_pantilt", ip, p_speed or 1, t_speed or 1, p_dir, t_dir)
        self._update_streaming()

    def _handle_zoom_axis(self, group: str, value: int, now: float) -> None:
        speed = self.trigger_to_zoom_speed(value, group)
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
            self._send("send_zoom", ip, "stop", 0)
        else:
            direction = "out" if self._zoom_inverted.get(group) else "in"
            self._send("send_zoom", ip, direction, speed)

    def _set_zoom_inverted(self, group: str, inverted: bool) -> None:
        """Single mutation point for the latched zoom direction.

        Edge-triggered: a no-op when the state is unchanged, so the OSC
        broadcast -> Resolume param -> Wire CC -> on_midi_in round-trip (and the
        TouchOSC echo) is idempotent and cannot oscillate. The bumper tap, the
        TouchOSC IN/OUT CCs, and any future surface all funnel through here, so
        every surface stays in sync with the engine as the source of truth.
        """
        if group not in self._zoom_inverted:
            return
        if self._zoom_inverted[group] == inverted:
            return
        self._zoom_inverted[group] = inverted
        # Flip a live zoom immediately (no need to re-press the trigger).
        if self._zoom_speed.get(group, 0) > 0:
            self._emit_zoom(group)
        # Broadcast the absolute state so the TouchOSC indicator follows whichever
        # surface changed it (Resolume echoes the effect param back to TouchOSC).
        self._broadcast_zoom_dir(group)

    def _broadcast_zoom_dir(self, group: str) -> None:
        """Write the latched direction (0.0 IN / 1.0 OUT) to the PTZ SELECT param."""
        if self._osc is None:
            return
        self._osc.send(
            f"{self._zoom_dir_osc_base}/{group}",
            1.0 if self._zoom_inverted.get(group) else 0.0,
        )

    # ------------------------------------------------------------------
    # Bumper zoom-direction toggle + physical select

    def on_note_in(self, channel: int, note: int, velocity: int, now: float) -> None:
        # Press-driven only (ignore Note-Off): the same-side bumper TAPS to
        # toggle the latched zoom direction; everything routes through
        # _set_zoom_inverted so bumper, TouchOSC, and broadcast stay consistent.
        if velocity <= 0:
            return
        for group, gcfg in self._groups.items():
            n = gcfg.get("zoom_invert_note")
            if n is None or note != n:
                continue
            ch = gcfg.get("zoom_invert_channel")
            if ch is not None and channel != ch:
                continue
            self._set_zoom_inverted(group, not self._zoom_inverted.get(group, False))
        # Physical camera-select shares this handler and the same _select_camera
        # core (currently config-disabled; harmless no-op when note maps empty).
        self._handle_physical_select(channel, note)

    def _handle_physical_select(self, channel: int, note: int) -> None:
        cfg = self._physical_select
        if not cfg:
            return
        sel_ch = cfg.get("channel")
        if sel_ch is not None and sel_ch != channel:
            return
        mode = cfg.get("mode", "discrete")
        group: "str | None" = None
        index = 0
        if mode == "discrete":
            entry = cfg.get("discrete_notes", {}).get(str(note))
            if entry:
                group, index = str(entry[0]), int(entry[1])
        elif mode == "cycle":
            group = cfg.get("cycle_notes", {}).get(str(note))
            if group:
                # 1 -> 2 -> 3 -> 1; _select_camera STOP-then-retargets each step.
                index = (self._selected_index.get(group, 1) % 3) + 1
        if not group:
            return
        before = self._selected_index.get(group)
        self._select_camera(group, index)
        if self._selected_index.get(group) != before:
            self._broadcast_select(group)

    def _broadcast_select(self, group: str) -> None:
        """Echo a button-driven select to the PTZ SELECT choice param.

        Resolume relays the param to TouchOSC, so the Cam buttons light for
        Deck-button selects too. Its MIDI echo (CC 94/95) lands on
        _select_camera as a no-op because the camera is already selected.
        Choice params take a normalized float: Cam 1/2/3 -> 0, 0.5, 1.
        """
        if self._osc is None:
            return
        steps = max(1, len(self._cameras) - 1)
        index = self._selected_index.get(group, 1)
        self._osc.send(f"{self._select_osc_base}/{group}select", (index - 1) / steps)

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
        if ip is not None:
            for _ in range(self._redundant_stops):
                if surface == "pantilt":
                    self._send("send_stop", ip)
                else:
                    self._send("send_zoom_stop", ip)
        self._last_stop_reason = reason

    def tick(self, now: float) -> None:
        """Drop watchdog: if a moving surface goes stale, inject STOP.

        Local time check only — no network reads, ADR-0001 clean. Also the
        camera-network retry: while active and unbound, one bind attempt every
        BIND_RETRY_SECONDS. An inactive engine does no retry work at all.
        """
        if not self.active:
            return
        if self._sender is None:
            last = self._last_bind_attempt
            if last is None or now < last or now - last >= BIND_RETRY_SECONDS:
                self._try_bind(now)
        if self._speed_resync_seconds > 0:
            due = self._next_speed_resync
            if due is None or now >= due or now < due - self._speed_resync_seconds:
                self._next_speed_resync = now + self._speed_resync_seconds
                self._resync_speeds(now)
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
        """Stop every camera and release the socket on toggle-off; bind on.

        The registry flips ``active`` without teardown, so a held stick at
        toggle-off would otherwise strand a moving camera. Analogous to
        ``l_stick_layer._release_active_ccs``. Activating tries the bind at
        once; a failure leaves ``tick`` retrying every BIND_RETRY_SECONDS.
        """
        was_active = self.active
        super().set_active(active)
        if was_active and not active:
            self._release_network("toggle")
            # Re-activating re-asserts the speeds on its first tick.
            self._next_speed_resync = None
        elif self.active and self._sender is None:
            self._try_bind(self._clock())

    def shutdown(self) -> None:
        """Stop pan/tilt AND zoom on every group, then close the sender."""
        self._release_network("shutdown")
        self._shut_down = True

    def _stop_all_groups(self, reason: str) -> None:
        for group in self._groups:
            ip = self._target_ip(group)
            if ip is not None:
                for _ in range(self._redundant_stops):
                    self._send("send_stop", ip)
                    self._send("send_zoom_stop", ip)
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
                "sender": self._sender_state,
                "bound_ip": self._bound_ip,
                "cameras": dict(self._cameras),
                "last_bind_error": self._last_bind_error,
                "targets": dict(self._targets),
                "selected": dict(self._selected_index),
                "streaming": self._streaming,
                "moving": {g: dict(self._moving[g]) for g in self._groups},
                "stick_deadzone": {
                    g: {
                        "touch_action": self._groups[g].get("touch_action"),
                        "touched": self._touched[g],
                        "deadzone": self._group_deadzone[g],
                        "deadzone_untouched": self._group_deadzone_untouched[g],
                        "in_force": self._stick_deadzone(g),
                    }
                    for g in self._groups
                },
                "last_stop_reason": self._last_stop_reason,
                "pan_tilt_speed_scale": dict(self._pan_tilt_scale),
                "zoom_speed_scale": dict(self._zoom_scale),
                "camera_speed_scale": {
                    c: {
                        "pan_tilt": self._cam_pan_tilt_scale.get(c),
                        "zoom": self._cam_zoom_scale.get(c),
                    }
                    for c in self._cameras
                },
                "zoom_direction": {
                    g: ("out" if self._zoom_inverted.get(g) else "in")
                    for g in self._groups
                },
                "effective_speed_max": {
                    g: {
                        "pan": self._eff_pan_max(g),
                        "tilt": self._eff_tilt_max(g),
                        "zoom": self._eff_zoom_max(g),
                    }
                    for g in self._groups
                },
            }
        )
        return s
