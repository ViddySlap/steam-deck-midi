"""MIDI input/output abstractions for the Windows receiver."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import NamedTuple
from typing import Sequence


class MidiError(RuntimeError):
    """Raised when MIDI output cannot be initialized or used."""


class MidiPortSnapshot(NamedTuple):
    input_names: list[str]
    output_names: list[str]


class MidiControlChange(NamedTuple):
    channel: int
    control: int
    value: int


class MidiClockMessage(NamedTuple):
    """A MIDI System Real-Time clock message (clock / start / stop / continue)."""

    type: str  # one of: "clock", "start", "stop", "continue"
    received_at: float


class MidiOut:
    """Abstract MIDI output interface."""

    @property
    def port_name(self) -> str:
        raise NotImplementedError

    @property
    def port_index(self) -> int | None:
        return None

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


class MidiIn:
    """Abstract MIDI input interface."""

    @property
    def port_name(self) -> str:
        raise NotImplementedError

    @property
    def port_index(self) -> int | None:
        return None

    def poll_control_changes(self) -> list[MidiControlChange]:
        raise NotImplementedError

    def poll_clock_messages(self) -> list[MidiClockMessage]:
        """Drain MIDI System Real-Time clock messages (clock/start/stop/continue).

        Default implementation returns an empty list. Backends that want clock
        delivery override this. Note: each call drains pending messages, so
        callers should choose between `poll_control_changes` or
        `poll_clock_messages` depending on what the port carries — calling
        both on the same port in the same iteration is fine, but each message
        is yielded by exactly one of the two methods (the one matching the
        message type).
        """
        return []

    def close(self) -> None:
        """Release backend resources if needed."""


@dataclass
class DryRunMidiOut(MidiOut):
    """A no-op backend that records what would be sent."""

    selected_port_name: str = "dry-run"
    selected_port_index: int | None = None

    @property
    def port_name(self) -> str:
        return self.selected_port_name

    @property
    def port_index(self) -> int | None:
        return self.selected_port_index

    def note_on(self, channel: int, note: int, velocity: int) -> None:
        print(f"MIDI note_on channel={channel} note={note} velocity={velocity}")

    def note_off(self, channel: int, note: int, velocity: int = 0) -> None:
        print(f"MIDI note_off channel={channel} note={note} velocity={velocity}")

    def control_change(self, channel: int, control: int, value: int) -> None:
        print(f"MIDI cc channel={channel} control={control} value={value}")

    def panic(self) -> None:
        print("MIDI panic")


@dataclass
class DryRunMidiIn(MidiIn):
    """A no-op MIDI input backend."""

    selected_port_name: str = "dry-run"
    selected_port_index: int | None = None

    @property
    def port_name(self) -> str:
        return self.selected_port_name

    @property
    def port_index(self) -> int | None:
        return self.selected_port_index

    def poll_control_changes(self) -> list[MidiControlChange]:
        return []


class MidoMidiOut(MidiOut):
    """Optional `mido`-based MIDI output implementation."""

    def __init__(self, port_name: str):
        try:
            import mido
        except ImportError as exc:
            raise MidiError(
                "mido is not installed; use --dry-run or install a MIDI backend"
            ) from exc

        available = list_output_ports(mido.get_output_names())
        resolved_port_name = resolve_output_port_name(port_name, available)

        self._mido = mido
        self._port_index = available.index(resolved_port_name)
        self._port = mido.open_output(resolved_port_name)
        self._port_name = resolved_port_name
        self._failed = False

    @property
    def port_name(self) -> str:
        return self._port_name

    @property
    def port_index(self) -> int | None:
        return self._port_index

    def _send(self, message) -> None:
        if self._failed:
            raise MidiError(
                f"MIDI output '{self._port_name}' is unavailable after a previous send failure"
            )
        try:
            self._port.send(message)
        except Exception as exc:
            self._failed = True
            raise MidiError(
                f"failed to send MIDI message on '{self._port_name}': {exc}"
            ) from exc

    def note_on(self, channel: int, note: int, velocity: int) -> None:
        self._send(
            self._mido.Message("note_on", channel=channel, note=note, velocity=velocity)
        )

    def note_off(self, channel: int, note: int, velocity: int = 0) -> None:
        self._send(
            self._mido.Message("note_off", channel=channel, note=note, velocity=velocity)
        )

    def control_change(self, channel: int, control: int, value: int) -> None:
        self._send(
            self._mido.Message(
                "control_change", channel=channel, control=control, value=value
            )
        )

    def panic(self) -> None:
        for channel in range(16):
            self.control_change(channel, 123, 0)

    def close(self) -> None:
        self._port.close()


class MidoMidiIn(MidiIn):
    """Optional `mido`-based MIDI input implementation.

    Drains both control_change and System Real-Time clock messages. Each
    poll method returns only its own message kind; messages of other types
    are dropped. Mixing kinds on one port is supported because mido yields
    them all from `iter_pending()` regardless of type.
    """

    _CLOCK_TYPES = frozenset({"clock", "start", "stop", "continue"})

    def __init__(self, port_name: str):
        try:
            import mido
        except ImportError as exc:
            raise MidiError(
                "mido is not installed; use --dry-run or install a MIDI backend"
            ) from exc

        available = get_input_port_names()
        resolved_port_name = resolve_input_port_name(port_name, available)

        self._port = mido.open_input(resolved_port_name)
        # rtmidi backend ignores SysEx + active_sense + clock by default; reach
        # past the mido wrapper to enable clock delivery. Other backends will
        # raise AttributeError here, which we swallow — they either deliver
        # clock by default or this port simply won't carry it.
        try:
            self._port._rt.ignore_types(False, False, False)
        except (AttributeError, TypeError):
            pass
        self._port_index = available.index(resolved_port_name)
        self._port_name = resolved_port_name
        self._pending_clock: list[MidiClockMessage] = []
        self._pending_cc: list[MidiControlChange] = []
        self._clock = time.monotonic

    @property
    def port_name(self) -> str:
        return self._port_name

    @property
    def port_index(self) -> int | None:
        return self._port_index

    def _drain_into_queues(self) -> None:
        for message in self._port.iter_pending():
            if message.type == "control_change":
                self._pending_cc.append(
                    MidiControlChange(
                        channel=int(message.channel),
                        control=int(message.control),
                        value=int(message.value),
                    )
                )
            elif message.type in self._CLOCK_TYPES:
                self._pending_clock.append(
                    MidiClockMessage(type=message.type, received_at=self._clock())
                )

    def poll_control_changes(self) -> list[MidiControlChange]:
        self._drain_into_queues()
        out, self._pending_cc = self._pending_cc, []
        return out

    def poll_clock_messages(self) -> list[MidiClockMessage]:
        self._drain_into_queues()
        out, self._pending_clock = self._pending_clock, []
        return out

    def close(self) -> None:
        self._port.close()


def open_midi_output(port_name: str | None, dry_run: bool) -> MidiOut:
    if dry_run:
        return DryRunMidiOut(selected_port_name=port_name or "dry-run")
    if not port_name:
        raise MidiError("a MIDI port name is required unless --dry-run is enabled")
    return MidoMidiOut(port_name)


def open_midi_input(port_name: str | None, dry_run: bool) -> MidiIn | None:
    if not port_name:
        return None
    if dry_run:
        return DryRunMidiIn(selected_port_name=port_name)
    return MidoMidiIn(port_name)


def get_output_port_names() -> list[str]:
    try:
        import mido
    except ImportError as exc:
        raise MidiError(
            "mido is not installed; use --dry-run or install a MIDI backend"
        ) from exc

    return list_output_ports(mido.get_output_names())


def get_input_port_names() -> list[str]:
    try:
        import mido
    except ImportError as exc:
        raise MidiError(
            "mido is not installed; use --dry-run or install a MIDI backend"
        ) from exc

    return list_output_ports(mido.get_input_names())


def get_port_snapshot() -> MidiPortSnapshot:
    return MidiPortSnapshot(
        input_names=get_input_port_names(),
        output_names=get_output_port_names(),
    )


def resolve_available_output_port_name(port_name: str) -> str:
    return resolve_output_port_name(port_name, get_output_port_names())


def resolve_available_input_port_name(port_name: str) -> str:
    return resolve_input_port_name(port_name, get_input_port_names())


def list_output_ports(names: Sequence[str]) -> list[str]:
    return list(names)


def resolve_output_port_name(port_name: str, names: Sequence[str]) -> str:
    return resolve_input_port_name(port_name, names)


def resolve_input_port_name(port_name: str, names: Sequence[str]) -> str:
    available = list_output_ports(names)
    if port_name in available:
        return port_name

    folded_name = port_name.casefold()

    case_insensitive_exact = [
        candidate for candidate in available if candidate.casefold() == folded_name
    ]
    if len(case_insensitive_exact) == 1:
        return case_insensitive_exact[0]

    prefix_matches = [
        candidate for candidate in available if candidate.casefold().startswith(folded_name)
    ]
    if len(prefix_matches) == 1:
        return prefix_matches[0]
    if len(prefix_matches) > 1:
        joined_matches = ", ".join(prefix_matches)
        raise MidiError(
            f"MIDI port '{port_name}' matched multiple ports: {joined_matches}"
        )

    joined = format_output_port_list(available)
    raise MidiError(f"MIDI port '{port_name}' not found; available ports: {joined}")


def format_output_port_list(names: Sequence[str]) -> str:
    if not names:
        return "(none)"
    return ", ".join(f"[{index}] {name}" for index, name in enumerate(names))
