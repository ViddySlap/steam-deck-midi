"""MIDI output abstractions for the Windows receiver."""

from __future__ import annotations

from dataclasses import dataclass


class MidiError(RuntimeError):
    """Raised when MIDI output cannot be initialized or used."""


class MidiOut:
    """Abstract MIDI output interface."""

    def note_on(self, channel: int, note: int, velocity: int) -> None:
        raise NotImplementedError

    def note_off(self, channel: int, note: int, velocity: int = 0) -> None:
        raise NotImplementedError

    def control_change(self, channel: int, control: int, value: int) -> None:
        raise NotImplementedError

    def panic(self) -> None:
        """Send a conservative reset where supported."""

    def close(self) -> None:
        """Release backend resources if needed."""


@dataclass
class DryRunMidiOut(MidiOut):
    """A no-op backend that records what would be sent."""

    port_name: str = "dry-run"

    def note_on(self, channel: int, note: int, velocity: int) -> None:
        print(f"MIDI note_on channel={channel} note={note} velocity={velocity}")

    def note_off(self, channel: int, note: int, velocity: int = 0) -> None:
        print(f"MIDI note_off channel={channel} note={note} velocity={velocity}")

    def control_change(self, channel: int, control: int, value: int) -> None:
        print(f"MIDI cc channel={channel} control={control} value={value}")

    def panic(self) -> None:
        print("MIDI panic")


class MidoMidiOut(MidiOut):
    """Optional `mido`-based MIDI output implementation."""

    def __init__(self, port_name: str):
        try:
            import mido
        except ImportError as exc:
            raise MidiError(
                "mido is not installed; use --dry-run or install a MIDI backend"
            ) from exc

        available = mido.get_output_names()
        if port_name not in available:
            joined = ", ".join(available) if available else "(none)"
            raise MidiError(
                f"MIDI port '{port_name}' not found; available ports: {joined}"
            )

        self._mido = mido
        self._port = mido.open_output(port_name)

    def note_on(self, channel: int, note: int, velocity: int) -> None:
        self._port.send(
            self._mido.Message("note_on", channel=channel, note=note, velocity=velocity)
        )

    def note_off(self, channel: int, note: int, velocity: int = 0) -> None:
        self._port.send(
            self._mido.Message("note_off", channel=channel, note=note, velocity=velocity)
        )

    def control_change(self, channel: int, control: int, value: int) -> None:
        self._port.send(
            self._mido.Message(
                "control_change", channel=channel, control=control, value=value
            )
        )

    def panic(self) -> None:
        for channel in range(16):
            self.control_change(channel, 123, 0)

    def close(self) -> None:
        self._port.close()


def open_midi_output(port_name: str | None, dry_run: bool) -> MidiOut:
    if dry_run:
        return DryRunMidiOut(port_name=port_name or "dry-run")
    if not port_name:
        raise MidiError("a MIDI port name is required unless --dry-run is enabled")
    return MidoMidiOut(port_name)
