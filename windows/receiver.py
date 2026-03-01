"""Core Windows receiver logic."""

from __future__ import annotations

import logging
import socket
import time
from dataclasses import dataclass
from typing import Callable

from protocol.messages import ActionEvent, ProtocolError, parse_action_event
from windows.config import ControlChangeMapping, MidiMapping, NoteMapping
from windows.midi import MidiOut


LOGGER = logging.getLogger(__name__)


@dataclass
class SenderState:
    last_seq: int = -1
    last_seen: float = 0.0


class ActionReceiver:
    """Receive action messages and emit mapped MIDI output."""

    def __init__(
        self,
        midi_out: MidiOut,
        mappings: dict[str, MidiMapping],
        *,
        timeout_seconds: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._midi_out = midi_out
        self._mappings = mappings
        self._timeout_seconds = timeout_seconds
        self._clock = clock
        self._sender_states: dict[tuple[str, int], SenderState] = {}
        self._active_actions: dict[str, MidiMapping] = {}

    def handle_datagram(
        self, payload: bytes, addr: tuple[str, int], now: float | None = None
    ) -> bool:
        timestamp = self._clock() if now is None else now

        try:
            event = parse_action_event(payload)
        except ProtocolError as exc:
            LOGGER.warning("ignored invalid packet from %s:%s: %s", addr[0], addr[1], exc)
            return False

        sender = self._sender_states.setdefault(addr, SenderState())
        if event.seq <= sender.last_seq:
            LOGGER.warning(
                "ignored out-of-order packet from %s:%s seq=%s last_seq=%s",
                addr[0],
                addr[1],
                event.seq,
                sender.last_seq,
            )
            return False

        sender.last_seq = event.seq
        sender.last_seen = timestamp
        return self._dispatch_event(event)

    def check_timeouts(self, now: float | None = None) -> bool:
        timestamp = self._clock() if now is None else now
        if not self._sender_states:
            return False

        timed_out = all(
            (timestamp - sender.last_seen) >= self._timeout_seconds
            for sender in self._sender_states.values()
        )
        if not timed_out:
            return False

        if self._active_actions:
            LOGGER.warning("input timeout reached; releasing active MIDI state")
            self.release_all()
        return True

    def release_all(self) -> None:
        for action, mapping in list(self._active_actions.items()):
            self._release_mapping(action, mapping)
        self._active_actions.clear()
        self._midi_out.panic()

    def _dispatch_event(self, event: ActionEvent) -> bool:
        mapping = self._mappings.get(event.action)
        if mapping is None:
            LOGGER.warning("no MIDI mapping for action %s", event.action)
            return False

        if event.state == "down":
            self._apply_down(mapping)
            self._active_actions[event.action] = mapping
            LOGGER.info("action=%s state=down seq=%s", event.action, event.seq)
            return True

        self._release_mapping(event.action, mapping)
        self._active_actions.pop(event.action, None)
        LOGGER.info("action=%s state=up seq=%s", event.action, event.seq)
        return True

    def _apply_down(self, mapping: MidiMapping) -> None:
        if isinstance(mapping, NoteMapping):
            self._midi_out.note_on(mapping.channel, mapping.note, mapping.velocity)
            return
        if isinstance(mapping, ControlChangeMapping):
            self._midi_out.control_change(mapping.channel, mapping.cc, mapping.on_value)
            return
        raise TypeError(f"unsupported mapping type: {type(mapping)!r}")

    def _release_mapping(self, action: str, mapping: MidiMapping) -> None:
        if isinstance(mapping, NoteMapping):
            self._midi_out.note_off(mapping.channel, mapping.note, 0)
            LOGGER.info("released note mapping for %s", action)
            return
        if isinstance(mapping, ControlChangeMapping):
            self._midi_out.control_change(mapping.channel, mapping.cc, mapping.off_value)
            LOGGER.info("released CC mapping for %s", action)
            return
        raise TypeError(f"unsupported mapping type: {type(mapping)!r}")


def serve_forever(
    listen_host: str,
    listen_port: int,
    receiver: ActionReceiver,
    *,
    poll_interval: float = 0.25,
) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((listen_host, listen_port))
    sock.settimeout(poll_interval)

    LOGGER.info("listening on udp://%s:%s", listen_host, listen_port)
    try:
        while True:
            try:
                payload, addr = sock.recvfrom(4096)
            except socket.timeout:
                receiver.check_timeouts()
                continue
            receiver.handle_datagram(payload, addr)
            receiver.check_timeouts()
    except KeyboardInterrupt:
        LOGGER.info("shutdown requested")
    finally:
        receiver.release_all()
        sock.close()
