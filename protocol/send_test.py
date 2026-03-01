"""CLI tool for sending test action events over UDP."""

from __future__ import annotations

import argparse
import socket
import sys
import time

from protocol.messages import encode_action_event


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send test action events over UDP")
    parser.add_argument(
        "--target",
        default="127.0.0.1:45123",
        help="target address in host:port form (default: 127.0.0.1:45123)",
    )
    parser.add_argument("--action", required=True, help="Action ID to send")
    parser.add_argument(
        "--state",
        choices=("down", "up", "tap"),
        default="tap",
        help="send a single state or a down/up tap sequence",
    )
    parser.add_argument(
        "--seq",
        type=int,
        default=1,
        help="sequence number for the first packet",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.1,
        help="delay between down/up when using tap",
    )
    parser.add_argument(
        "--profile-name",
        default="default",
        help="optional profile name to include in packets",
    )
    parser.add_argument(
        "--profile-hash",
        default=None,
        help="optional profile hash to include in packets",
    )
    return parser


def parse_target(value: str) -> tuple[str, int]:
    try:
        host, port_text = value.rsplit(":", 1)
        return host, int(port_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("target must be in host:port form") from exc


def send_event(sock: socket.socket, target: tuple[str, int], payload: bytes) -> None:
    sock.sendto(payload, target)
    print(f"sent {payload.decode('utf-8')} to udp://{target[0]}:{target[1]}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        target = parse_target(args.target)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
        return 2

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        if args.state == "tap":
            send_event(
                sock,
                target,
                encode_action_event(
                    action=args.action,
                    state="down",
                    seq=args.seq,
                    profile_name=args.profile_name,
                    profile_hash=args.profile_hash,
                ),
            )
            time.sleep(args.delay)
            send_event(
                sock,
                target,
                encode_action_event(
                    action=args.action,
                    state="up",
                    seq=args.seq + 1,
                    profile_name=args.profile_name,
                    profile_hash=args.profile_hash,
                ),
            )
            return 0

        send_event(
            sock,
            target,
            encode_action_event(
                action=args.action,
                state=args.state,
                seq=args.seq,
                profile_name=args.profile_name,
                profile_hash=args.profile_hash,
            ),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
