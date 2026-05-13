"""Quick UDP packet sniffer for diagnosing deck → bridge traffic.

Binds 0.0.0.0:45123 and prints every datagram payload with action name + kind.
Counts events by action name. Runs until Ctrl-C or --duration seconds elapsed.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from collections import Counter


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=45123)
    parser.add_argument("--duration", type=float, default=15.0)
    parser.add_argument("--show", action="store_true", help="print each packet")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", args.port))
    sock.settimeout(0.5)

    counts: Counter[str] = Counter()
    samples: dict[str, str] = {}
    start = time.monotonic()
    total = 0

    print(f"listening on udp://0.0.0.0:{args.port} for {args.duration}s")
    while time.monotonic() - start < args.duration:
        try:
            data, addr = sock.recvfrom(4096)
        except socket.timeout:
            continue
        total += 1
        try:
            obj = json.loads(data.decode("utf-8"))
        except Exception:
            counts["<unparseable>"] += 1
            continue
        kind = obj.get("kind", "?")
        action = obj.get("action", "")
        key = f"{kind}:{action}" if action else kind
        counts[key] += 1
        if key not in samples:
            samples[key] = data.decode("utf-8", "replace")
        if args.show:
            print(f"  {addr[0]}:{addr[1]} {data.decode('utf-8', 'replace')}")

    print(f"\ntotal packets: {total}")
    print("by kind:action:")
    for key, n in counts.most_common():
        print(f"  {n:>5}  {key}")
    print("\nsample payload per category:")
    for key, sample in samples.items():
        print(f"  {key}: {sample}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
