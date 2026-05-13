"""Minimal stdlib OSC packet sniffer for ad-hoc reverse-engineering.

Binds to 127.0.0.1:<port> and prints every received OSC message in human-
readable form: address + typed args. Used here to capture NestDrop's
OSC Output broadcast when activating/deactivating sprites via the UI.

Usage:
    py scripts/osc_sniff.py [port]
"""

from __future__ import annotations

import socket
import struct
import sys
from datetime import datetime


def _read_string(buf: bytes, i: int) -> tuple[str, int]:
    end = buf.find(b"\x00", i)
    if end < 0:
        return buf[i:].decode("utf-8", errors="replace"), len(buf)
    s = buf[i:end].decode("utf-8", errors="replace")
    # Advance past the string + null terminator + padding to 4-byte boundary
    end += 1
    end += (-end) % 4
    return s, end


def parse_osc(data: bytes) -> tuple[str, list]:
    """Parse a single OSC message into (address, args).

    Bundles are not handled (NestDrop's output sends individual messages).
    """
    addr, i = _read_string(data, 0)
    args: list = []
    if i >= len(data) or data[i:i + 1] != b",":
        return addr, args
    type_tag, i = _read_string(data, i)
    for t in type_tag[1:]:  # skip leading ','
        if t == "i":
            args.append(struct.unpack(">i", data[i:i + 4])[0]); i += 4
        elif t == "f":
            args.append(struct.unpack(">f", data[i:i + 4])[0]); i += 4
        elif t == "s":
            s, i = _read_string(data, i); args.append(s)
        elif t == "T":
            args.append(True)
        elif t == "F":
            args.append(False)
        elif t == "N":
            args.append(None)
        elif t == "r":
            r, g, b, a = struct.unpack(">BBBB", data[i:i + 4]); i += 4
            args.append(f"#{r:02x}{g:02x}{b:02x}{a:02x}")
        else:
            args.append(f"<unknown type {t!r}>")
            break
    return addr, args


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    print(f"sniffing OSC on udp://0.0.0.0:{port} (Ctrl+C to stop)", flush=True)
    while True:
        data, addr_from = sock.recvfrom(65535)
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        try:
            osc_addr, args = parse_osc(data)
            print(f"{ts} from {addr_from[0]}:{addr_from[1]}  {osc_addr}  args={args}", flush=True)
        except Exception as exc:
            print(f"{ts} parse error: {exc} raw={data!r}", flush=True)


if __name__ == "__main__":
    main()
