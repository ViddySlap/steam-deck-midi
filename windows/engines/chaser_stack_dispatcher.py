"""Chaser stack dispatcher engine.

Listens for the chaser-layer L2 analog (deck CC 1 ch0 = L_TRIGGER_PRESSURE)
at native deck rate and drives:

- HC Chaser.Step via 30Hz phase accumulator (deflection-curved rate)
- FeedbackPro Feedback Hue via OSC (deflection -> 0..1)
- FeedbackPro Feedback amount via OSC (deflection -> 0..FEEDBACK_MAX)

L2 is a pure ramp surface: ramp up + ramp down on Chaser.Step rate and
FeedbackPro contributions. No autoflash, no flash logic.

Spec: specs/vcb-engines-midi-only.md § "CHASER L2 (`chaser_stack_dispatcher`)"

Layer guard: only acts when `steam_input_layer_tracker.current_layer == 'chaser'`.

Tunables read from V-C-B Wire dashboard via one-shot REST GET at init
(re-pull on demand via `refresh()` / POST /api/engines/refresh):
- CHASER STACK MIN STEP   default 0.0
- CHASER STACK MAX STEP   default 0.5
- CHASER STACK FEEDBACK   default 0.7

The 30Hz `tick()` runs the chaser-step phase accumulator only; it does
NO REST work (per the "no REST after engine init unless user-triggered"
rule).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from windows.engines._resolume_lookup import find_effect_params, find_param_value
from windows.engines.base import Engine
from windows.engines.osc_client import OscClient
from windows.engines.resolume_rest import ResolumeRestClient, ResolumeRestError
from windows.midi import MidiOut

LOGGER = logging.getLogger(__name__)

DEFAULT_INPUT_CHANNEL = 0
DEFAULT_CC_AMOUNT = 1
DEFAULT_TICK_HZ = 30.0
DEFAULT_ENGAGE_THRESHOLD = 0.05
DEFAULT_DISENGAGE_THRESHOLD = 0.03
DEFAULT_LAYER_DEBOUNCE_SECONDS = 0.15
DEFAULT_MIN_STEP = 0.0
DEFAULT_MAX_STEP = 0.5
DEFAULT_FEEDBACK_MAX = 0.7
DEFAULT_RATE_CURVE_EXP = 2.0
DEFAULT_VCB_EFFECT_NAME = "VIDDY-COLOR-BUMP"
DEFAULT_OSC_CHASER_STEP_PATH = (
    "/composition/layers/8/video/effects/chaser/effect/step"
)
DEFAULT_OSC_FEEDBACK_HUE_PATH = (
    "/composition/layers/8/video/effects/feedbackpro/effect/feedbackhue"
)
DEFAULT_OSC_FEEDBACK_AMOUNT_PATH = (
    "/composition/layers/8/video/effects/feedbackpro/effect/feedback"
)
# Bumper + Chaser stomp on each other when both visible. Engine swaps
# bypass state on engage/disengage: Bumper is the chaser-layer default
# (active for R1/R2 plays); Chaser is bypassed at rest and unbypassed
# only while L2 is engaged.
DEFAULT_OSC_BUMPER_BYPASS_PATH = (
    "/composition/layers/8/video/effects/bumper/bypassed"
)
DEFAULT_OSC_CHASER_BYPASS_PATH = (
    "/composition/layers/8/video/effects/chaser/bypassed"
)

EXPECTED_LAYER = "chaser"


class ChaserStackDispatcherEngine(Engine):
    type_name = "chaser_stack_dispatcher"

    def __init__(
        self,
        name: str,
        config: dict,
        midi_out: MidiOut,
        *,
        clock: Callable[[], float] = time.monotonic,
        rest_client: ResolumeRestClient | None = None,
        osc_client: OscClient | None = None,
    ) -> None:
        super().__init__(name, config, midi_out, clock=clock)

        inputs = config.get("inputs", {})
        self._input_channel = int(inputs.get("channel", DEFAULT_INPUT_CHANNEL))
        self._cc_amount = int(inputs.get("cc_amount", DEFAULT_CC_AMOUNT))
        self._engage_threshold = float(
            inputs.get("engage_threshold", DEFAULT_ENGAGE_THRESHOLD)
        )
        self._disengage_threshold = float(
            inputs.get("disengage_threshold", DEFAULT_DISENGAGE_THRESHOLD)
        )

        self._tick_hz = float(config.get("tick_hz", DEFAULT_TICK_HZ))

        defaults = config.get("defaults", {})
        self._min_step = float(defaults.get("min_step", DEFAULT_MIN_STEP))
        self._max_step = float(defaults.get("max_step", DEFAULT_MAX_STEP))
        self._feedback_max = float(defaults.get("feedback_max", DEFAULT_FEEDBACK_MAX))
        self._rate_curve_exp = float(
            defaults.get("rate_curve_exp", DEFAULT_RATE_CURVE_EXP)
        )

        targets = config.get("targets", {})
        self._vcb_effect_name = str(
            targets.get("vcb_effect_name", DEFAULT_VCB_EFFECT_NAME)
        )

        outputs = config.get("outputs", {})
        osc_cfg = outputs.get("osc", {})
        self._osc = osc_client or OscClient(
            host=str(osc_cfg.get("host", "127.0.0.1")),
            port=int(osc_cfg.get("port", 7000)),
        )
        osc_paths = outputs.get("osc_paths", {})
        self._osc_chaser_step_path = str(
            osc_paths.get("chaser_step", DEFAULT_OSC_CHASER_STEP_PATH)
        )
        self._osc_feedback_hue_path = str(
            osc_paths.get("feedback_hue", DEFAULT_OSC_FEEDBACK_HUE_PATH)
        )
        self._osc_feedback_amount_path = str(
            osc_paths.get("feedback_amount", DEFAULT_OSC_FEEDBACK_AMOUNT_PATH)
        )
        self._osc_bumper_bypass_path = str(
            osc_paths.get("bumper_bypass", DEFAULT_OSC_BUMPER_BYPASS_PATH)
        )
        self._osc_chaser_bypass_path = str(
            osc_paths.get("chaser_bypass", DEFAULT_OSC_CHASER_BYPASS_PATH)
        )

        self._layer_debounce_seconds = float(
            config.get("layer_debounce_seconds", DEFAULT_LAYER_DEBOUNCE_SECONDS)
        )

        rest_cfg = config.get("rest", {})
        self._rest = rest_client or ResolumeRestClient(
            base_url=str(rest_cfg.get("base_url", "http://127.0.0.1:8080")),
            timeout_seconds=float(rest_cfg.get("timeout_seconds", 1.5)),
        )

        self._engaged = False
        self._last_amount = 0.0
        self._current_step = 0.0

        self._layer_tracker = None
        self._debounce_until = 0.0

        self._engage_count = 0
        self._disengage_count = 0
        self._step_writes = 0
        self._refresh_count = 0

    # ------------------------------------------------------------------
    # Lifecycle

    def bind_registry(self, registry) -> None:
        tracker = registry.get_by_type("steam_input_layer_tracker")
        if tracker is not None:
            self._layer_tracker = tracker
            tracker.add_observer(self._on_layer_change)
        self._refresh_tunables_from_dashboard()
        # Write Bumper/Chaser bypass rest state. Bumper is the chaser-layer
        # default (active so R1/R2 plays work); Chaser is bypassed and gets
        # unbypassed only while L2 is engaged.
        self._write_bypass_rest_state()

    def _write_bypass_rest_state(self) -> None:
        self._osc.send(self._osc_bumper_bypass_path, False)
        self._osc.send(self._osc_chaser_bypass_path, True)

    def refresh(self) -> None:
        """Re-pull V-C-B dashboard tunables. Called by /api/engines/refresh."""
        self._refresh_tunables_from_dashboard()

    def shutdown(self) -> None:
        try:
            self._osc.close()
        except Exception:
            pass

    def tick_interval_seconds(self) -> float | None:
        return 1.0 / self._tick_hz

    # ------------------------------------------------------------------
    # MIDI input

    def on_midi_in(self, channel: int, cc: int, value: int, now: float) -> None:
        if channel != self._input_channel or cc != self._cc_amount:
            return
        amount = max(0.0, min(1.0, value / 127.0))
        self._last_amount = amount

        if self._layer_tracker is not None:
            if self._layer_tracker.current_layer != EXPECTED_LAYER:
                if self._engaged:
                    self._do_disengage()
                return
        if now < self._debounce_until:
            return

        if not self._engaged and amount >= self._engage_threshold:
            self._do_engage()
        elif self._engaged and amount < self._disengage_threshold:
            self._do_disengage()

        if self._engaged:
            self._send_feedback(amount)

    def tick(self, now: float) -> None:
        # NO REST work in tick (per "no REST after engine init unless
        # user-triggered" rule). Only the 30Hz chaser-step animator runs.
        if not self._engaged:
            return
        if self._layer_tracker is not None:
            if self._layer_tracker.current_layer != EXPECTED_LAYER:
                return
        rate_hz = self._compute_step_rate(self._last_amount)
        tick_hz = max(1.0, self._tick_hz)
        self._current_step = (self._current_step + rate_hz / tick_hz) % 1.0
        self._osc.send(self._osc_chaser_step_path, float(self._current_step))
        self._step_writes += 1

    # ------------------------------------------------------------------
    # State transitions

    def _do_engage(self) -> None:
        self._engaged = True
        self._engage_count += 1
        self._current_step = 0.0
        # Swap chaser-layer effect visibility: bypass Bumper, unbypass
        # Chaser so the L2 stack renders without Bumper stomping.
        self._osc.send(self._osc_bumper_bypass_path, True)
        self._osc.send(self._osc_chaser_bypass_path, False)
        LOGGER.info("%s: engage", self.name)

    def _do_disengage(self) -> None:
        self._engaged = False
        self._disengage_count += 1
        # Relax FeedbackPro contributions to 0 so the layer settles.
        self._osc.send(self._osc_feedback_hue_path, 0.0)
        self._osc.send(self._osc_feedback_amount_path, 0.0)
        # Restore chaser-layer bypass rest state: Bumper active, Chaser
        # bypassed. R1/R2 chaser-layer plays are ready immediately.
        self._write_bypass_rest_state()
        LOGGER.info("%s: disengage", self.name)

    def _on_layer_change(self, new_layer: str) -> None:
        self._debounce_until = self._clock() + self._layer_debounce_seconds
        if new_layer != EXPECTED_LAYER and self._engaged:
            self._do_disengage()

    # ------------------------------------------------------------------
    # Output helpers

    def _remap_post_engage(self, amount: float) -> float:
        # Remap [engage_threshold, 1.0] -> [0.0, 1.0] so the visible
        # response starts at 0 the instant engagement crosses the
        # deadzone hysteresis buffer.
        span = 1.0 - self._engage_threshold
        if span <= 0.0:
            return 0.0
        return max(0.0, min(1.0, (amount - self._engage_threshold) / span))

    def _compute_step_rate(self, amount: float) -> float:
        remapped = self._remap_post_engage(amount)
        curved = remapped ** self._rate_curve_exp
        return self._min_step + (self._max_step - self._min_step) * curved

    def _send_feedback(self, amount: float) -> None:
        remapped = self._remap_post_engage(amount)
        self._osc.send(self._osc_feedback_hue_path, float(remapped))
        self._osc.send(
            self._osc_feedback_amount_path, float(self._feedback_max * remapped)
        )

    # ------------------------------------------------------------------
    # Tunable refresh

    def _refresh_tunables_from_dashboard(self) -> None:
        try:
            comp = self._rest.get_composition()
        except ResolumeRestError as exc:
            LOGGER.debug(
                "%s: tunable refresh skipped (REST unreachable: %s)",
                self.name,
                exc,
            )
            return
        params = find_effect_params(comp, self._vcb_effect_name)
        if not params:
            return
        v_min = find_param_value(
            params, ("CHASER STACK MIN STEP", "chaserstackminstep")
        )
        v_max = find_param_value(
            params, ("CHASER STACK MAX STEP", "chaserstackmaxstep")
        )
        v_fb = find_param_value(
            params, ("CHASER STACK FEEDBACK", "chaserstackfeedback")
        )
        if v_min is not None:
            self._min_step = float(v_min)
        if v_max is not None:
            self._max_step = float(v_max)
        if v_fb is not None:
            self._feedback_max = float(v_fb)
        self._refresh_count += 1
        LOGGER.debug(
            "%s: tunables refreshed (min_step=%.3f max_step=%.3f feedback=%.3f)",
            self.name,
            self._min_step,
            self._max_step,
            self._feedback_max,
        )

    # ------------------------------------------------------------------
    # Status

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type_name,
            "engaged": self._engaged,
            "last_amount": round(self._last_amount, 3),
            "current_step": round(self._current_step, 3),
            "engage_count": self._engage_count,
            "disengage_count": self._disengage_count,
            "step_writes": self._step_writes,
            "refresh_count": self._refresh_count,
            "min_step": round(self._min_step, 3),
            "max_step": round(self._max_step, 3),
            "feedback_max": round(self._feedback_max, 3),
            "layer_tracker_bound": self._layer_tracker is not None,
            "current_layer": (
                self._layer_tracker.current_layer
                if self._layer_tracker is not None
                else None
            ),
        }
