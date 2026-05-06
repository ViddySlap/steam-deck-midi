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

    def tick(self, now: float) -> None:
        """Called periodically from the receiver event loop."""

    def tick_interval_seconds(self) -> float | None:
        """Return desired tick interval, or None if the engine is event-driven only."""
        return None

    def shutdown(self) -> None:
        """Called when the receiver is shutting down."""

    def status(self) -> dict:
        """Return a JSON-serializable dict describing engine state for the UI."""
        return {"name": self.name, "type": self.type_name}
