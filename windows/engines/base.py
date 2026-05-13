"""Engine base class — the contract receiver-loop integration uses."""

from __future__ import annotations

import time
from typing import Callable

from windows.midi import MidiOut


class Engine:
    """Base class for bridge-side automation engines.

    Subclasses override `on_midi_in` and/or `tick` to react to feedback CCs
    and time-based work. Engines may emit MIDI via `self._midi_out` and may
    keep arbitrary internal state.
    """

    type_name: str = "engine"

    def __init__(
        self,
        name: str,
        config: dict,
        midi_out: MidiOut,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.name = name
        self._config = config
        self._midi_out = midi_out
        self._clock = clock

    def on_midi_in(self, channel: int, cc: int, value: int, now: float) -> None:
        """Called for every MIDI CC arriving on the feedback port."""

    def on_note_in(self, channel: int, note: int, velocity: int, now: float) -> None:
        """Called for every MIDI Note On arriving on the feedback port.

        Note Off arrives as `velocity == 0`. The receiver loop only dispatches
        this if its MIDI input backend exposes a note-poll path; backends that
        don't will leave this method un-called. Engines that need note input
        should also tolerate the no-call case (e.g. `steam_input_layer_tracker`
        accepts CC-encoded layer signals as a fallback).
        """

    def on_axis_event(self, action: str, value: int, now: float) -> None:
        """Called for every analog axis event arriving from the deck.

        `action` is the action ID (e.g. "L_STICK_X_AXIS", "GYRO_STATE_NOW").
        `value` is the integer value from the deck-side sender. Engines
        that care about specific axis-event broadcasts (state pings,
        deck-side absolute-state signals) override this. Default no-op.
        """

    def on_midi_clock(self, message_type: str, now: float) -> None:
        """Called for every MIDI System Real-Time clock message.

        `message_type` is one of: "clock", "start", "stop", "continue".
        Default no-op. Engines that need tempo derivation override this.
        """

    def tick(self, now: float) -> None:
        """Called periodically from the receiver event loop."""

    def tick_interval_seconds(self) -> float | None:
        """Return desired tick interval, or None if the engine is event-driven only."""
        return None

    def bind_registry(self, registry) -> None:
        """Called once after the engine is added to its registry.

        Engines that need registry-mediated hooks (e.g. note-emit filters)
        register them here. Default no-op.
        """

    def shutdown(self) -> None:
        """Called when the receiver is shutting down."""

    def refresh(self) -> None:
        """Re-pull any one-shot init-time state (e.g. REST tunables).

        Called by the dev `POST /api/engines/refresh` endpoint. Default
        no-op. Engines that read REST state once at `bind_registry`
        override this so dashboards can re-pull on demand without a
        full bridge restart. Per the "no REST after engine init unless
        user-triggered" rule, periodic REST polling is forbidden; this
        is the user-triggered escape hatch for development iteration.
        """

    def status(self) -> dict:
        """Return a JSON-serializable dict describing engine state for the UI."""
        return {"name": self.name, "type": self.type_name}
