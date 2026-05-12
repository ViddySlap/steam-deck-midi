"""Bumper blast bridge engine (Pass 2 rewrite, OSC-only).

Drives HC Bumper's NATIVE Sustain + Blast Speed parameters in response
to the deck's R_TRIGGER_PRESSURE (CC 2 ch0) when the SteamInput layer is
'chaser'. Bumper handles burst cadence natively; the engine only handles
engage/disengage edges + continuous Blast Speed mapping.

Spec: specs/vcb-engines-midi-only.md § "CHASER R2 (`bumper_blast` engine)"

Outputs are OSC writes only. REST is used solely for a one-shot tunable
read at engine init -- never on the keypress path, never periodic.
Re-read via `refresh()` (POST /api/engines/refresh dev endpoint).

The pre-Pass-2 engine PUT REST writes on every keypress, which choked
Arena's UI thread by 4-10 seconds (2026-05-09 hot-path hazard). Pass 2
removed those keypress-path PUTs. The 2026-05-11 EVENING REST-elimination
work then removed the 30s periodic tunable refresh that was still doing
GET /composition every refresh interval and contributing ~10% MIDI-input
drop rate via single-threaded REST handler contention.

Layer guard: when `steam_input_layer_tracker.current_layer != 'chaser'`,
the engine drops events and releases any held sustain.

Tunables read from V-C-B Wire dashboard via one-shot REST GET at init:
- BUMPER BLAST MIN SPEED  (default 0.10)
- BUMPER BLAST MAX SPEED  (default 1.00)
- BUMPER BLAST CURVE EXP  (default 2.0)

Note: Bumper.Next (chaser R1 click) is no longer dispatched here. It's a
direct MIDI Learn binding on note 62 ch0 -> Bumper.Next in the Resolume
MIDI shortcut preset (uniqueId 1778510000003).
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
DEFAULT_CC_AMOUNT = 2
DEFAULT_ENGAGE_THRESHOLD = 0.05
DEFAULT_DISENGAGE_THRESHOLD = 0.03
DEFAULT_LAYER_DEBOUNCE_SECONDS = 0.15
DEFAULT_MIN_SPEED = 0.10
DEFAULT_MAX_SPEED = 0.95
DEFAULT_CURVE_EXP = 2.0
DEFAULT_SUSTAIN_CURVE_EXP = 2.0
# Sustain ramps from 0 with trigger pull. Capped at 0.95 because
# Sustain=1.0 fills the entire screen visually.
SUSTAIN_MAX = 0.95
DEFAULT_VCB_EFFECT_NAME = "VIDDY-COLOR-BUMP"
DEFAULT_OSC_SUSTAIN_PATH = (
    "/composition/layers/8/video/effects/bumper/effect/sustain"
)
DEFAULT_OSC_BLAST_SPEED_PATH = (
    "/composition/layers/8/video/effects/bumper/effect/blastspeed"
)
DEFAULT_OSC_BLAST_PATH = "/composition/layers/8/video/effects/bumper/effect/blast"
DEFAULT_BLAST_SPEED_DEDUPE = 0.005
DEFAULT_SUSTAIN_DEDUPE = 0.005

EXPECTED_LAYER = "chaser"


class BumperBlastEngine(Engine):
    type_name = "bumper_blast"

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

        defaults = config.get("defaults", {})
        self._min_speed = float(defaults.get("min_speed", DEFAULT_MIN_SPEED))
        self._max_speed = float(defaults.get("max_speed", DEFAULT_MAX_SPEED))
        self._curve_exp = float(defaults.get("curve_exp", DEFAULT_CURVE_EXP))
        self._sustain_curve_exp = float(
            defaults.get("sustain_curve_exp", DEFAULT_SUSTAIN_CURVE_EXP)
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
        self._osc_sustain_path = str(
            osc_paths.get("sustain", DEFAULT_OSC_SUSTAIN_PATH)
        )
        self._osc_blast_speed_path = str(
            osc_paths.get("blast_speed", DEFAULT_OSC_BLAST_SPEED_PATH)
        )
        self._osc_blast_path = str(osc_paths.get("blast", DEFAULT_OSC_BLAST_PATH))

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
        self._last_blast_speed_sent: float | None = None
        self._last_sustain_sent: float | None = None

        self._layer_tracker = None
        self._debounce_until = 0.0

        self._engage_count = 0
        self._disengage_count = 0
        self._blast_speed_writes = 0
        self._refresh_count = 0

    # ------------------------------------------------------------------
    # Lifecycle

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
        self._refresh_tunables_from_dashboard()

    def refresh(self) -> None:
        """Re-pull V-C-B dashboard tunables. Called by /api/engines/refresh."""
        self._refresh_tunables_from_dashboard()

    def shutdown(self) -> None:
        if self._engaged:
            try:
                self._osc.send(self._osc_sustain_path, 0.0)
            except Exception:
                pass
        try:
            self._osc.close()
        except Exception:
            pass

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
            self._do_engage(amount)
        elif self._engaged and amount < self._disengage_threshold:
            self._do_disengage()
        elif self._engaged:
            self._send_sustain(amount)
            self._send_blast_speed(amount)

    # ------------------------------------------------------------------
    # State transitions

    def _do_engage(self, amount: float) -> None:
        self._engaged = True
        self._engage_count += 1
        LOGGER.info("%s: engage at amount=%.3f", self.name, amount)
        self._send_sustain(amount)
        self._send_blast_speed(amount)
        self._osc.send(self._osc_blast_path, 1.0)

    def _do_disengage(self) -> None:
        self._engaged = False
        self._disengage_count += 1
        LOGGER.info("%s: disengage", self.name)
        self._osc.send(self._osc_sustain_path, 0.0)
        # Release the held Blast trigger so the Resolume UI button returns
        # to rest. Mirrors the bump=0 release pattern in flash_blast.
        self._osc.send(self._osc_blast_path, 0.0)
        self._last_blast_speed_sent = None
        self._last_sustain_sent = None

    def _on_layer_change(self, new_layer: str) -> None:
        if new_layer != EXPECTED_LAYER:
            # Departing chaser: gate brief CC flutter during the layer
            # transition + release the held sustain.
            self._debounce_until = self._clock() + self._layer_debounce_seconds
            if self._engaged:
                self._do_disengage()
            return
        # Arriving on chaser: no arrival debounce -- a held trigger from
        # the previous layer should engage immediately instead of waiting
        # for the next deck CC change.
        if not self._engaged and self._last_amount >= self._engage_threshold:
            self._do_engage(self._last_amount)

    # ------------------------------------------------------------------
    # Output helpers

    def _remap_post_engage(self, amount: float) -> float:
        # Remap [engage_threshold, 1.0] -> [0.0, 1.0]. Eliminates the
        # visible "jump" at the moment engagement crosses the deadzone
        # hysteresis buffer; usable trigger range becomes 0..1 from the
        # engagement edge instead of 0.1..1.
        span = 1.0 - self._engage_threshold
        if span <= 0.0:
            return 0.0
        return max(0.0, min(1.0, (amount - self._engage_threshold) / span))

    def _send_sustain(self, amount: float) -> None:
        remapped = self._remap_post_engage(amount)
        sustain = (remapped ** self._sustain_curve_exp) * SUSTAIN_MAX
        if (
            self._last_sustain_sent is not None
            and abs(self._last_sustain_sent - sustain) < DEFAULT_SUSTAIN_DEDUPE
        ):
            return
        self._osc.send(self._osc_sustain_path, float(sustain))
        self._last_sustain_sent = sustain

    def _send_blast_speed(self, amount: float) -> None:
        speed = self._compute_blast_speed(amount)
        if (
            self._last_blast_speed_sent is not None
            and abs(self._last_blast_speed_sent - speed) < DEFAULT_BLAST_SPEED_DEDUPE
        ):
            return
        self._osc.send(self._osc_blast_speed_path, float(speed))
        self._last_blast_speed_sent = speed
        self._blast_speed_writes += 1

    def _compute_blast_speed(self, amount: float) -> float:
        remapped = self._remap_post_engage(amount)
        curved = remapped ** self._curve_exp
        speed = self._min_speed + (self._max_speed - self._min_speed) * curved
        return max(0.0, min(1.0, speed))

    # ------------------------------------------------------------------
    # Tunable refresh

    def _refresh_tunables_from_dashboard(self) -> None:
        try:
            comp = self._rest.get_composition()
        except ResolumeRestError as exc:
            LOGGER.debug(
                "%s: tunable refresh skipped (REST unreachable: %s)", self.name, exc
            )
            return
        params = find_effect_params(comp, self._vcb_effect_name)
        if not params:
            return
        v_min = find_param_value(
            params, ("BUMPER BLAST MIN SPEED", "bumperblastminspeed")
        )
        v_max = find_param_value(
            params, ("BUMPER BLAST MAX SPEED", "bumperblastmaxspeed")
        )
        v_exp = find_param_value(
            params, ("BUMPER BLAST CURVE EXP", "bumperblastcurveexp")
        )
        if v_min is not None:
            self._min_speed = float(v_min)
        if v_max is not None:
            self._max_speed = float(v_max)
        if v_exp is not None:
            self._curve_exp = float(v_exp)
        self._refresh_count += 1
        LOGGER.debug(
            "%s: tunables refreshed (min=%.3f max=%.3f curve=%.3f)",
            self.name,
            self._min_speed,
            self._max_speed,
            self._curve_exp,
        )

    # ------------------------------------------------------------------
    # Status

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type_name,
            "engaged": self._engaged,
            "last_amount": round(self._last_amount, 3),
            "last_blast_speed_sent": (
                round(self._last_blast_speed_sent, 3)
                if self._last_blast_speed_sent is not None
                else None
            ),
            "engage_count": self._engage_count,
            "disengage_count": self._disengage_count,
            "blast_speed_writes": self._blast_speed_writes,
            "refresh_count": self._refresh_count,
            "min_speed": round(self._min_speed, 3),
            "max_speed": round(self._max_speed, 3),
            "curve_exp": round(self._curve_exp, 3),
            "sustain_curve_exp": round(self._sustain_curve_exp, 3),
            "layer_tracker_bound": self._layer_tracker is not None,
            "current_layer": (
                self._layer_tracker.current_layer
                if self._layer_tracker is not None
                else None
            ),
        }
