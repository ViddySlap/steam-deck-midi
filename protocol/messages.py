"""Protocol parsing and validation for sender datagrams."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TypeAlias


VALID_STATES = {"down", "up"}
VALID_KINDS = {"action", "heartbeat", "axis", "buttons"}

# Raw button-state datagram field -> (min, max). See ButtonStateEvent.
_BUTTON_STATE_INT_FIELDS = {
    "lp": (0, 0xFFFF),
    "rp": (0, 0xFFFF),
    "lx": (-0x8000, 0x7FFF),
    "ly": (-0x8000, 0x7FFF),
    "rx": (-0x8000, 0x7FFF),
    "ry": (-0x8000, 0x7FFF),
    "lt": (0, 0xFFFF),
    "rt": (0, 0xFFFF),
}
BUTTON_STATE_BYTES = 8


class ProtocolError(ValueError):
    """Raised when an incoming message does not match the protocol contract."""


@dataclass(frozen=True)
class ActionEvent:
    kind: str
    action: str
    state: str
    seq: int
    profile_name: str | None = None
    profile_hash: str | None = None


@dataclass(frozen=True)
class HeartbeatEvent:
    kind: str
    seq: int
    profile_name: str | None = None
    profile_hash: str | None = None


@dataclass(frozen=True)
class AxisEvent:
    kind: str
    action: str
    value: int
    seq: int


@dataclass(frozen=True)
class ButtonStateEvent:
    """Raw controller state from the Deck's HID report (ADR 0003).

    `buttons` is report bytes 8-15 verbatim. Pad pressures and trigger values
    are the raw u16 fields, pad positions the raw s16 fields. `deck_ms` is the
    Deck's monotonic clock when the report was read, so hold durations are
    measured where the button was pressed, not from network arrival time.
    """

    kind: str
    seq: int
    deck_ms: int
    buttons: bytes
    left_pad_pressure: int
    right_pad_pressure: int
    left_pad_x: int
    left_pad_y: int
    right_pad_x: int
    right_pad_y: int
    left_trigger: int
    right_trigger: int


ProtocolEvent: TypeAlias = ActionEvent | HeartbeatEvent | AxisEvent | ButtonStateEvent


def encode_action_event(
    *,
    action: str,
    state: str,
    seq: int,
    profile_name: str | None = None,
    profile_hash: str | None = None,
) -> bytes:
    """Encode an ActionEvent payload for network transport."""

    payload: dict[str, str | int] = {
        "kind": "action",
        "action": action,
        "state": state,
        "seq": seq,
    }
    if profile_name is not None:
        payload["profile_name"] = profile_name
    if profile_hash is not None:
        payload["profile_hash"] = profile_hash
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def encode_axis_event(
    *,
    action: str,
    value: int,
    seq: int,
) -> bytes:
    """Encode an AxisEvent payload for network transport."""

    payload: dict[str, str | int] = {
        "kind": "axis",
        "action": action,
        "value": value,
        "seq": seq,
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def encode_button_state_event(
    *,
    seq: int,
    deck_ms: int,
    buttons: bytes,
    left_pad_pressure: int,
    right_pad_pressure: int,
    left_pad_x: int,
    left_pad_y: int,
    right_pad_x: int,
    right_pad_y: int,
    left_trigger: int,
    right_trigger: int,
) -> bytes:
    """Encode a ButtonStateEvent payload for network transport."""

    payload: dict[str, str | int] = {
        "kind": "buttons",
        "seq": seq,
        "t": deck_ms,
        "b": bytes(buttons).hex(),
        "lp": left_pad_pressure,
        "rp": right_pad_pressure,
        "lx": left_pad_x,
        "ly": left_pad_y,
        "rx": right_pad_x,
        "ry": right_pad_y,
        "lt": left_trigger,
        "rt": right_trigger,
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def encode_heartbeat_event(
    *,
    seq: int,
    profile_name: str | None = None,
    profile_hash: str | None = None,
) -> bytes:
    payload: dict[str, str | int] = {
        "kind": "heartbeat",
        "seq": seq,
    }
    if profile_name is not None:
        payload["profile_name"] = profile_name
    if profile_hash is not None:
        payload["profile_hash"] = profile_hash
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def parse_action_event(payload: bytes) -> ProtocolEvent:
    """Parse a UDP datagram into a protocol event."""

    try:
        raw = json.loads(payload.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ProtocolError("payload is not valid UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise ProtocolError("payload is not valid JSON") from exc

    if not isinstance(raw, dict):
        raise ProtocolError("payload must be a JSON object")

    kind = raw.get("kind", "action")
    action = raw.get("action")
    state = raw.get("state")
    seq = raw.get("seq")
    profile_name = raw.get("profile_name")
    profile_hash = raw.get("profile_hash")

    if not isinstance(kind, str) or kind not in VALID_KINDS:
        raise ProtocolError("kind must be 'action', 'heartbeat', 'axis', or 'buttons'")
    if not isinstance(seq, int) or seq < 0:
        raise ProtocolError("seq must be a non-negative integer")
    if profile_name is not None and not isinstance(profile_name, str):
        raise ProtocolError("profile_name must be a string when provided")
    if profile_hash is not None and not isinstance(profile_hash, str):
        raise ProtocolError("profile_hash must be a string when provided")

    if kind == "heartbeat":
        return HeartbeatEvent(
            kind=kind,
            seq=seq,
            profile_name=profile_name,
            profile_hash=profile_hash,
        )

    if kind == "buttons":
        return _parse_button_state(raw, seq)

    if kind == "axis":
        if not isinstance(action, str) or not action:
            raise ProtocolError("action must be a non-empty string")
        value = raw.get("value")
        if not isinstance(value, int):
            raise ProtocolError("value must be an integer for axis events")
        return AxisEvent(kind=kind, action=action, value=value, seq=seq)

    if not isinstance(action, str) or not action:
        raise ProtocolError("action must be a non-empty string")
    if not isinstance(state, str) or state not in VALID_STATES:
        raise ProtocolError("state must be 'down' or 'up'")

    return ActionEvent(
        kind=kind,
        action=action,
        state=state,
        seq=seq,
        profile_name=profile_name,
        profile_hash=profile_hash,
    )


def _parse_button_state(raw: dict, seq: int) -> ButtonStateEvent:
    deck_ms = raw.get("t")
    if not isinstance(deck_ms, int) or isinstance(deck_ms, bool) or deck_ms < 0:
        raise ProtocolError("t must be a non-negative integer for buttons events")
    hex_buttons = raw.get("b")
    if not isinstance(hex_buttons, str) or len(hex_buttons) != BUTTON_STATE_BYTES * 2:
        raise ProtocolError(f"b must be {BUTTON_STATE_BYTES * 2} hex characters")
    try:
        buttons = bytes.fromhex(hex_buttons)
    except ValueError as exc:
        raise ProtocolError("b must be hex") from exc
    values: dict[str, int] = {}
    for key, (low, high) in _BUTTON_STATE_INT_FIELDS.items():
        value = raw.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
            raise ProtocolError(f"{key} must be an integer in {low}..{high}")
        values[key] = value
    return ButtonStateEvent(
        kind="buttons",
        seq=seq,
        deck_ms=deck_ms,
        buttons=buttons,
        left_pad_pressure=values["lp"],
        right_pad_pressure=values["rp"],
        left_pad_x=values["lx"],
        left_pad_y=values["ly"],
        right_pad_x=values["rx"],
        right_pad_y=values["ry"],
        left_trigger=values["lt"],
        right_trigger=values["rt"],
    )
