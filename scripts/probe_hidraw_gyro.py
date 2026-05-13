"""Deck-side probe: read /dev/hidraw2 directly and print gyro velocity bytes.

Replicates HidrawAxisReader's feature-claim sequence, then reads N reports
and prints the signed-short values at bytes 30/32/34 (PITCH/YAW/ROLL velocity).

Run only when the main sender daemon is STOPPED (hidraw is exclusive).
"""

from __future__ import annotations

import array
import fcntl
import struct
import sys
import time

HIDRAW_DEVICE = "/dev/hidraw2"
_HIDIOCSFEATURE = 0xC0404806


def claim(fd: int) -> None:
    def send(payload):
        buf = array.array("B", [0] * 65)
        for i, b in enumerate(payload):
            buf[i] = b
        fcntl.ioctl(fd, _HIDIOCSFEATURE, buf)

    send([0x00, 0x81])
    send([
        0x00, 0x87, 15,
        7, 6, 0,
        8, 6, 0,
        52, 0xFF, 0xFF,
        53, 0xFF, 0xFF,
        71, 0, 0,
    ])


def main() -> int:
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0
    f = open(HIDRAW_DEVICE, "rb+", buffering=0)
    try:
        claim(f.fileno())
    except OSError as exc:
        print(f"feature claim failed: {exc}", file=sys.stderr)

    start = time.monotonic()
    reports = 0
    nonzero = 0
    peak_pitch = 0
    peak_yaw = 0
    peak_roll = 0
    last_print = start

    print(f"reading /dev/hidraw2 for {duration}s. tilt the deck.")
    print(f"{'pitch':>8} {'yaw':>8} {'roll':>8} | gyro velocity (signed short)")

    while time.monotonic() - start < duration:
        try:
            data = f.read(64)
        except OSError as exc:
            print(f"read failed: {exc}", file=sys.stderr)
            break
        if len(data) < 64:
            continue
        if data[0] != 0x01 or data[2] != 0x09:
            continue
        reports += 1
        pitch = struct.unpack_from("<h", data, 30)[0]
        yaw = struct.unpack_from("<h", data, 32)[0]
        roll = struct.unpack_from("<h", data, 34)[0]
        if pitch or yaw or roll:
            nonzero += 1
        peak_pitch = max(peak_pitch, abs(pitch))
        peak_yaw = max(peak_yaw, abs(yaw))
        peak_roll = max(peak_roll, abs(roll))
        now = time.monotonic()
        if now - last_print >= 0.25:
            print(f"{pitch:>8} {yaw:>8} {roll:>8}")
            last_print = now

    f.close()
    print()
    print(f"total reports: {reports}")
    print(f"reports with any nonzero gyro byte: {nonzero}")
    print(f"peak |pitch|: {peak_pitch}   peak |yaw|: {peak_yaw}   peak |roll|: {peak_roll}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
