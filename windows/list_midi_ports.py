"""Print available MIDI input and output ports."""

from __future__ import annotations

import sys

from windows.midi import MidiError, get_port_snapshot


def main() -> int:
    try:
        snapshot = get_port_snapshot()
    except MidiError:
        print("mido is not installed. Run: pip install -r requirements.txt")
        return 1

    if not snapshot.input_names and not snapshot.output_names:
        print("No MIDI input or output ports found.")
        return 1

    print("Available MIDI input ports:")
    if snapshot.input_names:
        for index, port in enumerate(snapshot.input_names):
            print(f"- [{index}] {port}")
    else:
        print("- (none)")

    print("Available MIDI output ports:")
    if snapshot.output_names:
        for index, port in enumerate(snapshot.output_names):
            print(f"- [{index}] {port}")
    else:
        print("- (none)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
