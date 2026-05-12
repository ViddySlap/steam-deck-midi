"""Flash blast bridge engine (6-effect tap/build/fade architecture).

Per FLASH lane (R2 = WHITE, L2 = COLOR), the engine drives two separate
Color Bump effects:

  BUILD  (Decay=0, held pulse): opacity ramps with deck deflection
         during slow pulls. Engine writes opacity 0->1 and holds
         Bump=1 while building. Hidden via opacity=0 at all times
         outside BUILDING.

  FADE   (Decay=0.04, natural fade): fires once on slow-pull release
         (norm crossed 0.95) AND on confirmed quick tap. Provides
         the visible 1-sec fade-out flash. Opacity=1.0 always.

A third per-lane SHORT effect (Decay=1.0) exists in the comp but is
NOT touched by this engine -- R1/L1 deck clicks fire SHORT.Bump via
direct MIDI Learn for the always-available "quick flash".

State machine per lane:

  IDLE
    on norm > engage_floor (tolerance):
      -> PENDING (start tap window timer + track peak_norm)

  PENDING
    on release within tap_window AND peak > tap_peak_threshold:
      -> fire FADE.Bump -> IDLE   (quick tap)
    on release within tap_window AND peak <= tap_peak_threshold:
      -> IDLE   (accidental brush, no visual)
    on tap_window expires while still engaged:
      -> BUILDING (fire BUILD.Bump=1, start opacity ramp)

  BUILDING
    each update: BUILD.opacity = min(1, norm / SATURATION_NORM)
    on norm >= RELEASE_NORM:
      -> RELEASING (hide BUILD, release BUILD.Bump, fire FADE.Bump)
    on norm <= engage_floor:
      -> IDLE (hide BUILD, release BUILD.Bump, NO FADE fire)
              clean disappear (fixes partial-pull-fires-fade bug)

  RELEASING
    on norm <= engage_floor:
      -> IDLE (re-arm; FADE has decayed on its own)

Cross-surface contracts preserved:
- OPACITY STROBE rest state (bypass=on, opacity=1.0) for Y-button.
  Engine writes at init/shutdown/layer-change-away only; not touched
  during build/release.
- SHORT effects untouched by engine. R1/L1 MIDI Learn fires SHORT.Bump.

Locked constants:
  SATURATION_NORM       = 0.60
  RELEASE_NORM          = 0.95
  TAP_WINDOW_SECONDS    = 0.08
  TAP_PEAK_THRESHOLD    = 0.50
  STROBE_REST_OPACITY   = 1.0

Config-tunable:
  tolerance                  (default 0.10; engage floor)
  tap_window_seconds         (default 0.08)
  tap_peak_threshold         (default 0.50)
  fade_release_delay_seconds (default 0.05; when to send FADE.Bump=0 after
                              firing 1, so UI button releases visibly)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

from windows.engines.base import Engine
from windows.engines.osc_client import OscClient
from windows.midi import MidiOut

LOGGER = logging.getLogger(__name__)

# Deck analog channels (SteamInput does not layer-remap analog CCs).
DEFAULT_INPUT_CHANNEL = 0
DEFAULT_CC_WHITE_AMOUNT = 2   # R2 = R_TRIGGER_PRESSURE
DEFAULT_CC_COLOR_AMOUNT = 1   # L2 = L_TRIGGER_PRESSURE

# Locked constants (NOT config-tunable).
SATURATION_NORM = 0.60
RELEASE_NORM = 0.95
TAP_WINDOW_SECONDS = 0.08
TAP_PEAK_THRESHOLD = 0.50
STROBE_REST_OPACITY = 1.0
DEFAULT_TOLERANCE = 0.10
DEFAULT_FADE_RELEASE_DELAY = 0.05
DEFAULT_LAYER_DEBOUNCE_SECONDS = 0.15
DEFAULT_OPACITY_DEDUPE = 0.005
TICK_INTERVAL_SECONDS = 0.033  # ~30Hz

# Default OSC paths (slugs probed against Arena 7.26.0 + 6-effect comp).
#   colorbump   = Color Bump WHITE-long (BUILD)
#   colorbump2  = Color Bump COLOR-long (BUILD)
#   colorbump3  = Color Bump WHITE SHORT (untouched by engine)
#   colorbump4  = Color Bump COLOR SHORT (untouched by engine)
#   colorbump5  = Color Bump WHITE FADE
#   colorbump6  = Color Bump COLOR FADE
#   strobe      = OPACITY STROBE
DEFAULT_OSC_WHITE_BUILD_OPACITY = "/composition/layers/10/video/effects/colorbump/opacity"
DEFAULT_OSC_WHITE_BUILD_BUMP    = "/composition/layers/10/video/effects/colorbump/effect/bump"
DEFAULT_OSC_WHITE_BUILD_DECAY   = "/composition/layers/10/video/effects/colorbump/effect/decay"
DEFAULT_OSC_WHITE_FADE_OPACITY  = "/composition/layers/10/video/effects/colorbump5/opacity"
DEFAULT_OSC_WHITE_FADE_BUMP     = "/composition/layers/10/video/effects/colorbump5/effect/bump"
DEFAULT_OSC_COLOR_BUILD_OPACITY = "/composition/layers/10/video/effects/colorbump2/opacity"
DEFAULT_OSC_COLOR_BUILD_BUMP    = "/composition/layers/10/video/effects/colorbump2/effect/bump"
DEFAULT_OSC_COLOR_BUILD_DECAY   = "/composition/layers/10/video/effects/colorbump2/effect/decay"
DEFAULT_OSC_COLOR_FADE_OPACITY  = "/composition/layers/10/video/effects/colorbump6/opacity"
DEFAULT_OSC_COLOR_FADE_BUMP     = "/composition/layers/10/video/effects/colorbump6/effect/bump"
DEFAULT_OSC_STROBE_OPACITY      = "/composition/layers/10/video/effects/strobe/opacity"
DEFAULT_OSC_STROBE_BYPASS       = "/composition/layers/10/video/effects/strobe/bypassed"

EXPECTED_LAYER = "flash"

STATE_IDLE = "idle"
STATE_PENDING = "pending"
STATE_BUILDING = "building"
STATE_RELEASING = "releasing"


@dataclass
class LaneState:
    name: str
    # BUILD effect paths (engine writes opacity ramp + holds bump during build).
    build_opacity_path: str
    build_bump_path: str
    build_decay_path: str
    # FADE effect paths (engine fires bump on tap or release).
    fade_opacity_path: str
    fade_bump_path: str
    # Live state.
    state: str = STATE_IDLE
    last_norm: float = 0.0
    ramp: float = 0.0
    last_build_opacity_sent: float | None = None
    # PENDING-state bookkeeping.
    pending_engage_time: float = 0.0
    pending_peak_norm: float = 0.0
    # Deferred FADE-bump release scheduling.
    fade_bump_fire_time: float | None = None
    # Pending refire: a tap arrived while previous FADE.Bump still held.
    # Tick will release the held 1.0 then fire 1.0 again on the NEXT tick
    # so Resolume sees a clean 1->0->1 cycle across frames.
    fade_pending_refire: bool = False


class FlashBlastEngine(Engine):
    type_name = "flash_blast"

    def __init__(
        self,
        name: str,
        config: dict,
        midi_out: MidiOut,
        *,
        clock: Callable[[], float] = time.monotonic,
        osc_client: OscClient | None = None,
    ) -> None:
        super().__init__(name, config, midi_out, clock=clock)

        inputs = config.get("inputs", {})
        self._input_channel = int(inputs.get("channel", DEFAULT_INPUT_CHANNEL))
        self._cc_white_amount = int(
            inputs.get("cc_white_amount", DEFAULT_CC_WHITE_AMOUNT)
        )
        self._cc_color_amount = int(
            inputs.get("cc_color_amount", DEFAULT_CC_COLOR_AMOUNT)
        )

        self._tolerance = float(config.get("tolerance", DEFAULT_TOLERANCE))
        self._tap_window_seconds = float(
            config.get("tap_window_seconds", TAP_WINDOW_SECONDS)
        )
        self._tap_peak_threshold = float(
            config.get("tap_peak_threshold", TAP_PEAK_THRESHOLD)
        )
        self._fade_release_delay = float(
            config.get("fade_release_delay_seconds", DEFAULT_FADE_RELEASE_DELAY)
        )
        self._layer_debounce_seconds = float(
            config.get("layer_debounce_seconds", DEFAULT_LAYER_DEBOUNCE_SECONDS)
        )

        outputs = config.get("outputs", {})
        osc_cfg = outputs.get("osc", {})
        self._osc = osc_client or OscClient(
            host=str(osc_cfg.get("host", "127.0.0.1")),
            port=int(osc_cfg.get("port", 7000)),
        )
        osc_paths = outputs.get("osc_paths", {})

        self._white_lane = LaneState(
            name="white",
            build_opacity_path=str(osc_paths.get(
                "white_build_opacity", DEFAULT_OSC_WHITE_BUILD_OPACITY)),
            build_bump_path=str(osc_paths.get(
                "white_build_bump", DEFAULT_OSC_WHITE_BUILD_BUMP)),
            build_decay_path=str(osc_paths.get(
                "white_build_decay", DEFAULT_OSC_WHITE_BUILD_DECAY)),
            fade_opacity_path=str(osc_paths.get(
                "white_fade_opacity", DEFAULT_OSC_WHITE_FADE_OPACITY)),
            fade_bump_path=str(osc_paths.get(
                "white_fade_bump", DEFAULT_OSC_WHITE_FADE_BUMP)),
        )
        self._color_lane = LaneState(
            name="color",
            build_opacity_path=str(osc_paths.get(
                "color_build_opacity", DEFAULT_OSC_COLOR_BUILD_OPACITY)),
            build_bump_path=str(osc_paths.get(
                "color_build_bump", DEFAULT_OSC_COLOR_BUILD_BUMP)),
            build_decay_path=str(osc_paths.get(
                "color_build_decay", DEFAULT_OSC_COLOR_BUILD_DECAY)),
            fade_opacity_path=str(osc_paths.get(
                "color_fade_opacity", DEFAULT_OSC_COLOR_FADE_OPACITY)),
            fade_bump_path=str(osc_paths.get(
                "color_fade_bump", DEFAULT_OSC_COLOR_FADE_BUMP)),
        )
        self._osc_strobe_opacity_path = str(
            osc_paths.get("strobe_opacity", DEFAULT_OSC_STROBE_OPACITY)
        )
        self._osc_strobe_bypass_path = str(
            osc_paths.get("strobe_bypass", DEFAULT_OSC_STROBE_BYPASS)
        )

        self._last_strobe_opacity: float | None = None
        self._last_strobe_bypass: bool | None = None

        self._layer_tracker = None
        self._debounce_until = 0.0

        self._engage_count = 0
        self._tap_count = 0
        self._release_count = 0
        self._abort_count = 0

    # ------------------------------------------------------------------
    # Lifecycle

    def tick_interval_seconds(self) -> float | None:
        return TICK_INTERVAL_SECONDS

    def bind_registry(self, registry) -> None:
        tracker = registry.get_by_type("steam_input_layer_tracker")
        if tracker is not None:
            self._layer_tracker = tracker
            tracker.add_observer(self._on_layer_change)
            LOGGER.info(
                "%s: bound to steam_input_layer_tracker (current=%s)",
                self.name,
                tracker.current_layer,
            )
        # IDLE rest state:
        #   STROBE: bypass=on + opacity=1.0  (Y-button contract)
        #   BUILD: Decay=0 (held), Opacity=0 (hidden), Bump=0
        #   FADE:  Opacity=1 (always ready), Bump=0
        self._write_strobe_rest()
        for lane in (self._white_lane, self._color_lane):
            self._osc.send(lane.build_decay_path, 0.0)
            self._osc.send(lane.build_opacity_path, 0.0)
            self._osc.send(lane.build_bump_path, 0.0)
            self._osc.send(lane.fade_opacity_path, 1.0)
            self._osc.send(lane.fade_bump_path, 0.0)
            lane.last_build_opacity_sent = 0.0

    def shutdown(self) -> None:
        try:
            self._write_strobe_rest()
        except Exception:
            pass
        try:
            self._osc.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # MIDI input

    def on_midi_in(self, channel: int, cc: int, value: int, now: float) -> None:
        if channel != self._input_channel:
            return
        if cc == self._cc_white_amount:
            lane = self._white_lane
        elif cc == self._cc_color_amount:
            lane = self._color_lane
        else:
            return

        norm = max(0.0, min(1.0, value / 127.0))
        lane.last_norm = norm

        if self._layer_tracker is not None:
            if self._layer_tracker.current_layer != EXPECTED_LAYER:
                self._force_lane_idle(lane)
                return

        if now < self._debounce_until:
            return

        self._process_norm(lane, norm, now)

    def tick(self, now: float) -> None:
        for lane in (self._white_lane, self._color_lane):
            # Phase 1: release any held FADE.Bump that has aged out.
            if (
                lane.fade_bump_fire_time is not None
                and (now - lane.fade_bump_fire_time) >= self._fade_release_delay
            ):
                self._osc.send(lane.fade_bump_path, 0.0)
                lane.fade_bump_fire_time = None
                # Do NOT fire pending refire in the same tick -- defer to
                # next tick so Resolume sees the 0 land before the next 1.
                continue
            # Phase 2: fire pending refire if bump is now clear.
            if lane.fade_pending_refire and lane.fade_bump_fire_time is None:
                self._osc.send(lane.fade_bump_path, 1.0)
                lane.fade_bump_fire_time = now
                lane.fade_pending_refire = False

        # PENDING -> BUILDING transition by timer (user holds at
        # constant norm with no further CC events).
        for lane in (self._white_lane, self._color_lane):
            if lane.state == STATE_PENDING:
                if (now - lane.pending_engage_time) >= self._tap_window_seconds:
                    if lane.last_norm > self._engage_floor():
                        self._enter_building(lane, lane.last_norm)
                        # Cascade: if last_norm is already past RELEASE_NORM
                        # (deck stuck at peak, or just very fast pull),
                        # immediately chain through RELEASING so the visual
                        # doesn't hang in BUILDING with no incoming CC events.
                        self._process_norm(lane, lane.last_norm, now)
                    else:
                        # Past window AND already below floor -- accidental.
                        lane.state = STATE_IDLE

    # ------------------------------------------------------------------
    # State machine

    def _engage_floor(self) -> float:
        # Effective engage threshold = ENGAGE_THRESHOLD (0.0) + tolerance.
        return self._tolerance

    def _build_ramp(self, norm: float) -> float:
        # BUILD opacity ramp uses post-engage-remapped norm so the visible
        # ramp starts at 0 right at the engage floor (no jump from the
        # deadzone hysteresis buffer). SATURATION_NORM is preserved as a
        # raw-norm anchor: at norm=SATURATION_NORM, ramp=1.0.
        span = 1.0 - self._tolerance
        if span <= 0.0:
            return 0.0
        remapped = max(0.0, (norm - self._tolerance) / span)
        sat_remapped = (SATURATION_NORM - self._tolerance) / span
        if sat_remapped <= 0.0:
            return 1.0
        return min(1.0, remapped / sat_remapped)

    def _process_norm(self, lane: LaneState, norm: float, now: float) -> None:
        engage_floor = self._engage_floor()

        if lane.state == STATE_IDLE:
            if norm > engage_floor:
                self._enter_pending(lane, norm, now)
            return

        if lane.state == STATE_PENDING:
            lane.pending_peak_norm = max(lane.pending_peak_norm, norm)
            window_elapsed = (
                (now - lane.pending_engage_time) >= self._tap_window_seconds
            )
            # Fast-tap rule: if norm crosses RELEASE_NORM within the tap
            # window, fire FADE immediately. The user pulled hard and
            # fast -- give them instant feedback (no waiting for release).
            # Also bypasses the stuck-at-peak edge case: we don't depend
            # on the release CC arriving to fire the flash.
            if not window_elapsed and norm >= RELEASE_NORM:
                self._fire_fade(lane, now)
                lane.state = STATE_RELEASING
                self._tap_count += 1
                LOGGER.info(
                    "%s lane %s: PENDING -> RELEASING (fast tap, norm=%.3f)",
                    self.name, lane.name, norm,
                )
                return
            if norm <= engage_floor:
                if lane.pending_peak_norm > self._tap_peak_threshold:
                    self._fire_tap(lane, now)
                else:
                    lane.state = STATE_IDLE
                return
            if window_elapsed:
                self._enter_building(lane, norm)
                return
            return

        if lane.state == STATE_BUILDING:
            if norm >= RELEASE_NORM:
                self._enter_releasing(lane, now)
            elif norm <= engage_floor:
                self._abort_build(lane)
            else:
                ramp = self._build_ramp(norm)
                lane.ramp = ramp
                self._send_build_opacity(lane, ramp)
                self._update_strobe()
            return

        if lane.state == STATE_RELEASING:
            if norm <= engage_floor:
                lane.state = STATE_IDLE

    def _enter_pending(self, lane: LaneState, norm: float, now: float) -> None:
        lane.state = STATE_PENDING
        lane.pending_engage_time = now
        lane.pending_peak_norm = norm

    def _enter_building(self, lane: LaneState, norm: float) -> None:
        lane.state = STATE_BUILDING
        ramp = self._build_ramp(norm)
        lane.ramp = ramp
        self._engage_count += 1
        # Ensure clean rising edge for BUILD.Bump.
        self._osc.send(lane.build_bump_path, 0.0)
        self._osc.send(lane.build_bump_path, 1.0)
        self._send_build_opacity(lane, ramp)
        self._update_strobe()
        LOGGER.info(
            "%s lane %s: PENDING -> BUILDING (norm=%.3f)",
            self.name, lane.name, norm,
        )

    def _enter_releasing(self, lane: LaneState, now: float) -> None:
        lane.state = STATE_RELEASING
        lane.ramp = 0.0
        # Hide BUILD; release its held bump.
        self._send_build_opacity(lane, 0.0)
        self._osc.send(lane.build_bump_path, 0.0)
        # Fire FADE (single pulse, Decay fades naturally).
        self._fire_fade(lane, now)
        self._update_strobe()
        self._release_count += 1
        LOGGER.info(
            "%s lane %s: BUILDING -> RELEASING", self.name, lane.name
        )

    def _abort_build(self, lane: LaneState) -> None:
        lane.state = STATE_IDLE
        lane.ramp = 0.0
        # Hide BUILD + release its held bump. NO FADE on partial pull.
        self._send_build_opacity(lane, 0.0)
        self._osc.send(lane.build_bump_path, 0.0)
        self._update_strobe()
        self._abort_count += 1
        LOGGER.info(
            "%s lane %s: BUILDING -> IDLE (abort, clean disappear)",
            self.name, lane.name,
        )

    def _fire_tap(self, lane: LaneState, now: float) -> None:
        lane.state = STATE_IDLE
        self._tap_count += 1
        self._fire_fade(lane, now)
        LOGGER.info(
            "%s lane %s: PENDING -> IDLE (tap, peak=%.3f)",
            self.name, lane.name, lane.pending_peak_norm,
        )

    def _fire_fade(self, lane: LaneState, now: float) -> None:
        if lane.fade_bump_fire_time is not None:
            # Previous fire still held. Mark refire pending so tick can
            # release-then-fire across separate frames (avoids Resolume
            # collapsing rapid 1->0->1 messages in a single frame).
            lane.fade_pending_refire = True
            return
        self._osc.send(lane.fade_bump_path, 1.0)
        lane.fade_bump_fire_time = now

    def _send_build_opacity(self, lane: LaneState, opacity: float) -> None:
        clamped = max(0.0, min(1.0, opacity))
        if (
            lane.last_build_opacity_sent is not None
            and abs(lane.last_build_opacity_sent - clamped) < DEFAULT_OPACITY_DEDUPE
        ):
            return
        self._osc.send(lane.build_opacity_path, float(clamped))
        lane.last_build_opacity_sent = clamped

    def _update_strobe(self) -> None:
        """Cross-lane STROBE state machine.

        While ANY lane is BUILDING: STROBE bypass=off, opacity=max(ramps).
        When no lane is BUILDING: rest state (bypass=on, opacity=1.0) for
        cross-surface Y-button contract.
        """
        any_building = (
            self._white_lane.state == STATE_BUILDING
            or self._color_lane.state == STATE_BUILDING
        )
        if any_building:
            target_bypass = False
            target_opacity = max(
                self._white_lane.ramp if self._white_lane.state == STATE_BUILDING else 0.0,
                self._color_lane.ramp if self._color_lane.state == STATE_BUILDING else 0.0,
            )
        else:
            target_bypass = True
            target_opacity = STROBE_REST_OPACITY

        if self._last_strobe_bypass != target_bypass:
            self._osc.send(self._osc_strobe_bypass_path, target_bypass)
            self._last_strobe_bypass = target_bypass

        if (
            self._last_strobe_opacity is None
            or abs(self._last_strobe_opacity - target_opacity) >= DEFAULT_OPACITY_DEDUPE
        ):
            self._osc.send(self._osc_strobe_opacity_path, float(target_opacity))
            self._last_strobe_opacity = target_opacity

    def _force_lane_idle(self, lane: LaneState) -> None:
        if lane.state == STATE_IDLE:
            return
        self._send_build_opacity(lane, 0.0)
        self._osc.send(lane.build_bump_path, 0.0)
        lane.state = STATE_IDLE
        lane.ramp = 0.0
        self._update_strobe()

    def _write_strobe_rest(self) -> None:
        self._osc.send(self._osc_strobe_bypass_path, True)
        self._last_strobe_bypass = True
        self._osc.send(
            self._osc_strobe_opacity_path, float(STROBE_REST_OPACITY)
        )
        self._last_strobe_opacity = STROBE_REST_OPACITY

    def _on_layer_change(self, new_layer: str) -> None:
        self._debounce_until = self._clock() + self._layer_debounce_seconds
        if new_layer != EXPECTED_LAYER:
            for lane in (self._white_lane, self._color_lane):
                self._force_lane_idle(lane)
            self._write_strobe_rest()

    # ------------------------------------------------------------------
    # Status

    def status(self) -> dict:
        return {
            "name": self.name,
            "type": self.type_name,
            "current_layer": (
                self._layer_tracker.current_layer
                if self._layer_tracker is not None
                else None
            ),
            "white_state": self._white_lane.state,
            "color_state": self._color_lane.state,
            "white_norm": round(self._white_lane.last_norm, 4),
            "color_norm": round(self._color_lane.last_norm, 4),
            "white_ramp": round(self._white_lane.ramp, 4),
            "color_ramp": round(self._color_lane.ramp, 4),
            "strobe_opacity": self._last_strobe_opacity,
            "strobe_bypassed": self._last_strobe_bypass,
            "tolerance": self._tolerance,
            "tap_window_seconds": self._tap_window_seconds,
            "tap_peak_threshold": self._tap_peak_threshold,
            "engage_count": self._engage_count,
            "tap_count": self._tap_count,
            "release_count": self._release_count,
            "abort_count": self._abort_count,
        }
