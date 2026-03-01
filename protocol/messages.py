"""Protocol parsing and validation for action event datagrams."""

from __future__ import annotations

import json
from dataclasses import dataclass


VALID_STATES = {"down", "up"}


class ProtocolError(ValueError):
    """Raised when an incoming message does not match the protocol contract."""


@dataclass(frozen=True)
class ActionEvent:
    action: str
    state: str
    seq: int
    profile_name: str | None = None
    profile_hash: str | None = None


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
        "action": action,
        "state": state,
        "seq": seq,
    }
    if profile_name is not None:
        payload["profile_name"] = profile_name
    if profile_hash is not None:
        payload["profile_hash"] = profile_hash
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def parse_action_event(payload: bytes) -> ActionEvent:
    """Parse a UDP datagram into an ActionEvent."""

    try:
        raw = json.loads(payload.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ProtocolError("payload is not valid UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise ProtocolError("payload is not valid JSON") from exc

    if not isinstance(raw, dict):
        raise ProtocolError("payload must be a JSON object")

    action = raw.get("action")
    state = raw.get("state")
    seq = raw.get("seq")
    profile_name = raw.get("profile_name")
    profile_hash = raw.get("profile_hash")

    if not isinstance(action, str) or not action:
        raise ProtocolError("action must be a non-empty string")
    if not isinstance(state, str) or state not in VALID_STATES:
        raise ProtocolError("state must be 'down' or 'up'")
    if not isinstance(seq, int) or seq < 0:
        raise ProtocolError("seq must be a non-negative integer")
    if profile_name is not None and not isinstance(profile_name, str):
        raise ProtocolError("profile_name must be a string when provided")
    if profile_hash is not None and not isinstance(profile_hash, str):
        raise ProtocolError("profile_hash must be a string when provided")

    return ActionEvent(
        action=action,
        state=state,
        seq=seq,
        profile_name=profile_name,
        profile_hash=profile_hash,
    )
