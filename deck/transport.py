"""Portable UDP send path shared by the Deck sender and its control surfaces."""

from __future__ import annotations

import ipaddress
import logging
import socket
import time

from deck.local_config import validate_target_host
from protocol.messages import (
    encode_action_event,
    encode_axis_event,
    encode_button_state_event,
    encode_heartbeat_event,
)


logger = logging.getLogger(__name__)
DNS_CACHE_SECONDS = 60.0
ERROR_LOG_INTERVAL_SECONDS = 30.0
# Cache failures too, so an unavailable hostname is not looked up for every axis event.
_address_cache: dict[tuple[str, int], tuple[float, tuple[str, int] | OSError]] = {}
_last_error_at: dict[tuple[str, int], float] = {}


def parse_target(value: str) -> tuple[str, int]:
    """Parse one receiver, preserving the original single-target public API."""
    host, port_text = value.rsplit(":", 1)
    host = validate_target_host(host)
    port = int(port_text)
    if not 1 <= port <= 65535:
        raise ValueError("target port must be between 1 and 65535")
    return host, port


def parse_targets(value: str) -> list[tuple[str, int]]:
    """Parse the CLI/legacy run_sender comma-separated spelling, without DNS."""
    return [parse_target(part.strip()) for part in value.split(",")]


def _resolve_target(target: tuple[str, int], now: float) -> tuple[str, int]:
    host, port = target
    try:
        return str(ipaddress.IPv4Address(host)), port
    except ipaddress.AddressValueError:
        pass
    cached = _address_cache.get(target)
    if cached is None or now >= cached[0]:
        try:
            answers = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_DGRAM)
            address = answers[0][4] if answers else OSError("no IPv4 address found")
        except OSError as exc:
            address = exc
        cached = (now + DNS_CACHE_SECONDS, address)
        _address_cache[target] = cached
    if isinstance(cached[1], OSError):
        raise cached[1]
    return cached[1]


def _send_payload(
    sock: socket.socket,
    target: tuple[str, int] | list[tuple[str, int]],
    payload: bytes,
) -> None:
    targets = [target] if isinstance(target, tuple) else target
    for receiver in targets:
        now = time.monotonic()
        try:
            sock.sendto(payload, _resolve_target(receiver, now))
        except OSError as exc:
            last_error = _last_error_at.get(receiver)
            if last_error is None or now - last_error >= ERROR_LOG_INTERVAL_SECONDS:
                _last_error_at[receiver] = now
                logger.warning("UDP send failed for %s: %s", receiver, exc)


def send_action(
    sock: socket.socket,
    target: tuple[str, int] | list[tuple[str, int]],
    *,
    action: str,
    state: str,
    seq: int,
    profile_name: str | None,
    profile_hash: str | None,
) -> None:
    payload = encode_action_event(
        action=action,
        state=state,
        seq=seq,
        profile_name=profile_name,
        profile_hash=profile_hash,
    )
    _send_payload(sock, target, payload)
    print(f"sent action={action} state={state} seq={seq}")


def send_axis(
    sock: socket.socket,
    target: tuple[str, int] | list[tuple[str, int]],
    *,
    action: str,
    value: int,
    seq: int,
) -> None:
    payload = encode_axis_event(action=action, value=value, seq=seq)
    _send_payload(sock, target, payload)


def send_button_state(
    sock: socket.socket,
    target: tuple[str, int] | list[tuple[str, int]],
    *,
    state,
    seq: int,
) -> None:
    payload = encode_button_state_event(
        seq=seq,
        deck_ms=state.deck_ms,
        buttons=state.buttons,
        left_pad_pressure=state.left_pad_pressure,
        right_pad_pressure=state.right_pad_pressure,
        left_pad_x=state.left_pad_x,
        left_pad_y=state.left_pad_y,
        right_pad_x=state.right_pad_x,
        right_pad_y=state.right_pad_y,
        left_trigger=state.left_trigger,
        right_trigger=state.right_trigger,
    )
    _send_payload(sock, target, payload)


def send_heartbeat(
    sock: socket.socket,
    target: tuple[str, int] | list[tuple[str, int]],
    *,
    seq: int,
    profile_name: str | None,
    profile_hash: str | None,
) -> None:
    payload = encode_heartbeat_event(
        seq=seq,
        profile_name=profile_name,
        profile_hash=profile_hash,
    )
    _send_payload(sock, target, payload)
