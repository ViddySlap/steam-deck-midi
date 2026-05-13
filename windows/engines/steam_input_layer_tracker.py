"""SteamInput layer tracker engine.

The Steam Deck MIDI sender remaps the physical L1/L2/R1/R2 buttons to
different MIDI events depending on the active SteamInput layer (chaser
vs flash). The Select button toggles between layers. The analog L2/R2
trigger axes, however, emit the SAME CC regardless of layer — so the
bridge has to remember "what layer am I in" from recent digital activity
to route the analog correctly.

This engine watches digital MIDI Note On (and CC, as a fallback for
backends that send CCs instead of notes) for the per-layer button
identifiers and exposes `current_layer` to other engines via the
EngineRegistry's `get_by_type('steam_input_layer_tracker')` lookup.

Default layer at boot: 'chaser'.

Three signals advance the state:

1. Digital chaser-layer button event  → current_layer = 'chaser'
2. Digital flash-layer button event   → current_layer = 'flash'
3. Select button event (optional)     → toggle (chaser ↔ flash)

Downstream engines (`flash_blast`, `bumper_blast`,
`chaser_stack_dispatcher`) consult `current_layer` before processing
their analog CCs and ignore events for the wrong layer.

Observer hook: callers can register `tracker.observers.append(callback)`;
each callback fires `callback(new_layer)` on every layer transition.
This is how downstream engines arm a debounce window after a layer change
so a held analog trigger doesn't immediately flash on the new layer.

Optional OSC observability: when `emit_osc=True`, every layer change is
broadcast as a string OSC message at `osc_path` (default
`/bridge/steaminput/currentlayer`).
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from windows.engines.base import Engine
from windows.engines.osc_client import OscClient
from windows.midi import MidiOut

LOGGER = logging.getLogger(__name__)

LAYER_CHASER = "chaser"
LAYER_FLASH = "flash"
_VALID_LAYERS = frozenset({LAYER_CHASER, LAYER_FLASH})


class SteamInputLayerTrackerEngine(Engine):
    type_name = "steam_input_layer_tracker"

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

        # Layer notes: SteamInput emits a different note per layer for
        # the same physical button. The bridge config mirrors whatever
        # Ben configured in his Steam Input mappings.
        chaser_notes = config.get("chaser_notes", [])
        flash_notes = config.get("flash_notes", [])
        self._chaser_notes: set[int] = {int(n) for n in chaser_notes}
        self._flash_notes: set[int] = {int(n) for n in flash_notes}
        select_raw = config.get("select_note")
        self._select_note: int | None = int(select_raw) if select_raw is not None else None

        # Optional CC fallback for environments where the receiver does
        # not surface note_on but does surface CCs for the same buttons
        # (e.g. via deck mapping that emits a CC instead of a note).
        chaser_ccs = config.get("chaser_ccs", [])
        flash_ccs = config.get("flash_ccs", [])
        self._chaser_ccs: set[int] = {int(c) for c in chaser_ccs}
        self._flash_ccs: set[int] = {int(c) for c in flash_ccs}
        select_cc_raw = config.get("select_cc")
        self._select_cc: int | None = int(select_cc_raw) if select_cc_raw is not None else None
        # The bumper layer publisher in receiver.py echoes the SELECT CC on
        # channels 0/1 to broadcast layer state. Without this per-CC channel
        # filter, those echoes are interpreted as additional SELECT presses
        # and double-toggle the tracker (net zero change). The real SELECT
        # button arrives on a distinct channel (2 in the factory map); set
        # this to that channel to ignore publisher echoes. None means
        # "any channel", which is only safe when the publisher cannot fire.
        select_cc_channel_raw = config.get("select_cc_channel")
        self._select_cc_channel: int | None = (
            int(select_cc_channel_raw) if select_cc_channel_raw is not None else None
        )

        # SteamInput's MIDI channel — engines that emit per-layer notes
        # all share one channel. None means "any channel" (useful while
        # Ben is still pinning down his Steam Input mappings).
        ch_raw = config.get("channel")
        self._channel: int | None = int(ch_raw) if ch_raw is not None else None

        # Default layer at boot. Configurable so future shows can flip
        # the cold-start layer without code changes.
        default_layer = str(config.get("default_layer", LAYER_CHASER))
        if default_layer not in _VALID_LAYERS:
            LOGGER.warning(
                "steam_input_layer_tracker: invalid default_layer %r; using %r",
                default_layer,
                LAYER_CHASER,
            )
            default_layer = LAYER_CHASER
        self._current_layer: str = default_layer

        # Observer callbacks: list of zero-arg-or-1-arg callables receiving
        # the new layer string. Used by downstream engines for change-event
        # debouncing.
        self._observers: list[Callable[[str], None]] = []

        # Optional OSC broadcast of current_layer for status display.
        self._emit_osc = bool(config.get("emit_osc", False))
        osc_cfg = config.get("osc", {})
        self._osc_path = str(config.get("osc_path", "/bridge/steaminput/currentlayer"))
        self._osc: OscClient | None = None
        if self._emit_osc:
            self._osc = osc_client or OscClient(
                host=str(osc_cfg.get("host", "127.0.0.1")),
                port=int(osc_cfg.get("port", 7000)),
            )

        # Stats for `status()` / debugging.
        self._note_events_total = 0
        self._cc_events_total = 0
        self._layer_change_count = 0
        self._last_change_at: float | None = None

    # ------------------------------------------------------------------
    # Public API for downstream engines

    @property
    def current_layer(self) -> str:
        return self._current_layer

    @property
    def observers(self) -> list[Callable[[str], None]]:
        """Mutable list of layer-change callbacks. Append your own here."""
        return self._observers

    def add_observer(self, callback: Callable[[str], None]) -> None:
        """Register a callback fired with the new layer string on every change."""
        self._observers.append(callback)

    # ------------------------------------------------------------------
    # MIDI handlers

    def on_note_in(self, channel: int, note: int, velocity: int, now: float) -> None:
        if velocity == 0:
            # Note off — layer state is press-driven, not held.
            return
        if self._channel is not None and channel != self._channel:
            return
        self._note_events_total += 1
        if note in self._chaser_notes:
            self._set_layer(LAYER_CHASER, now)
        elif note in self._flash_notes:
            self._set_layer(LAYER_FLASH, now)
        elif self._select_note is not None and note == self._select_note:
            self._toggle_layer(now)

    def on_midi_in(self, channel: int, cc: int, value: int, now: float) -> None:
        if value == 0:
            # CC release — same press-driven semantics as notes.
            return
        if self._channel is not None and channel != self._channel:
            return
        if not (self._chaser_ccs or self._flash_ccs or self._select_cc is not None):
            return
        self._cc_events_total += 1
        if cc in self._chaser_ccs:
            self._set_layer(LAYER_CHASER, now)
        elif cc in self._flash_ccs:
            self._set_layer(LAYER_FLASH, now)
        elif self._select_cc is not None and cc == self._select_cc:
            if (
                self._select_cc_channel is not None
                and channel != self._select_cc_channel
            ):
                return
            self._toggle_layer(now)

    # ------------------------------------------------------------------
    # State transitions

    def _toggle_layer(self, now: float) -> None:
        new_layer = LAYER_FLASH if self._current_layer == LAYER_CHASER else LAYER_CHASER
        self._set_layer(new_layer, now)

    def _set_layer(self, new_layer: str, now: float) -> None:
        if new_layer == self._current_layer:
            return
        self._current_layer = new_layer
        self._layer_change_count += 1
        self._last_change_at = now
        LOGGER.info("steam_input_layer_tracker: layer -> %s", new_layer)
        for callback in list(self._observers):
            try:
                callback(new_layer)
            except Exception:
                LOGGER.exception(
                    "steam_input_layer_tracker: observer raised on layer change to %r",
                    new_layer,
                )
        if self._osc is not None:
            try:
                self._osc.send(self._osc_path, new_layer)
            except Exception:
                LOGGER.debug(
                    "steam_input_layer_tracker: OSC broadcast failed", exc_info=True
                )

    # ------------------------------------------------------------------
    # Engine lifecycle

    def shutdown(self) -> None:
        if self._osc is not None:
            try:
                self._osc.close()
            except Exception:
                pass
            self._osc = None

    def status(self) -> dict:
        return {
            "name": self.name,
            "type": self.type_name,
            "current_layer": self._current_layer,
            "chaser_notes": sorted(self._chaser_notes),
            "flash_notes": sorted(self._flash_notes),
            "select_note": self._select_note,
            "chaser_ccs": sorted(self._chaser_ccs),
            "flash_ccs": sorted(self._flash_ccs),
            "select_cc": self._select_cc,
            "select_cc_channel": self._select_cc_channel,
            "channel": self._channel,
            "note_events_total": self._note_events_total,
            "cc_events_total": self._cc_events_total,
            "layer_change_count": self._layer_change_count,
            "last_change_at": self._last_change_at,
            "observer_count": len(self._observers),
        }
