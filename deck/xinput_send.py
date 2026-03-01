"""Watch `xinput test` output and send mapped action events over UDP."""

from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
import sys

from protocol.messages import encode_action_event


KEY_EVENT_RE = re.compile(r"^key (press|release)\s+(\d+)$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Watch xinput key events and send mapped action events"
    )
    parser.add_argument("--device-id", required=True, help="xinput device id")
    parser.add_argument(
        "--bindings",
        required=True,
        help="path to deck_bindings.json containing keycode-to-action bindings",
    )
    parser.add_argument(
        "--target",
        required=True,
        help="receiver address in host:port form, for example 10.10.10.15:45123",
    )
    parser.add_argument(
        "--profile-name",
        default=None,
        help="override the profile_name sent over the network",
    )
    parser.add_argument(
        "--profile-hash",
        default=None,
        help="optional profile hash sent over the network",
    )
    return parser


def parse_target(value: str) -> tuple[str, int]:
    host, port_text = value.rsplit(":", 1)
    return host, int(port_text)


def load_bindings(path: str) -> tuple[str | None, dict[str, str]]:
    with open(path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)

    profile_name = raw.get("profile_name")
    bindings = raw.get("bindings")
    if profile_name is not None and not isinstance(profile_name, str):
        raise ValueError("profile_name must be a string when provided")
    if not isinstance(bindings, dict):
        raise ValueError("bindings file must contain an object at 'bindings'")

    validated: dict[str, str] = {}
    for token, action in bindings.items():
        if not isinstance(token, str) or not token:
            raise ValueError("binding tokens must be non-empty strings")
        if not isinstance(action, str) or not action:
            raise ValueError("binding actions must be non-empty strings")
        validated[token] = action
    return profile_name, validated


def parse_xinput_line(line: str) -> tuple[str, str] | None:
    match = KEY_EVENT_RE.match(line.strip())
    if match is None:
        return None
    state_name, keycode = match.groups()
    state = "down" if state_name == "press" else "up"
    return keycode, state


def send_action(
    sock: socket.socket,
    target: tuple[str, int],
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
    sock.sendto(payload, target)
    print(f"sent action={action} state={state} seq={seq}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        profile_name, bindings = load_bindings(args.bindings)
        target = parse_target(args.target)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
        return 2

    resolved_profile_name = args.profile_name or profile_name
    seq = 1

    try:
        process = subprocess.Popen(
            ["xinput", "test", str(args.device_id)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        parser.error(f"failed to start xinput: {exc}")
        return 2

    print(f"watching xinput device {args.device_id} and sending to {args.target}")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            assert process.stdout is not None
            for raw_line in process.stdout:
                parsed = parse_xinput_line(raw_line)
                if parsed is None:
                    continue
                keycode, state = parsed
                action = bindings.get(keycode)
                if action is None:
                    print(f"ignored keycode={keycode} state={state} (no binding)")
                    continue
                send_action(
                    sock,
                    target,
                    action=action,
                    state=state,
                    seq=seq,
                    profile_name=resolved_profile_name,
                    profile_hash=args.profile_hash,
                )
                seq += 1
        except KeyboardInterrupt:
            print("stopping sender")
        finally:
            process.terminate()
            process.wait(timeout=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
