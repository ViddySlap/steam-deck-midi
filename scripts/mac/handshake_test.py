#!/usr/bin/env python3
"""macOS bridge handshake verifier (no Steam Deck required).

Proves the host side of the rig stands up on this Mac by capturing the REAL
MIDI bytes the bridge writes to the IAC bus and the REAL OSC datagrams it
sends to Resolume's OSC input port — independent of Resolume itself.

Run it while a bridge is already listening on UDP 45123 (see scripts/mac/
run_receiver.command). It:

  1. Opens a MIDI input on "IAC Driver DECK_IN" (the same port Resolume reads)
     and captures everything the bridge emits there.
  2. Binds UDP :7000 (the port Resolume's OSC input uses) and captures OSC.
  3. Fires synthetic stimuli at the bridge:
       - a NOTE-mapped action  (BTN_A  -> note  ch0 #36)
       - a CC-mapped action    (START  -> cc    ch2 #78)
       - a feedback CC (ch14 cc90) into DECK_OUT to trip the osc_sync engine,
         which emits OSC to :7000 (the real event -> engine -> OSC path)
       - a direct OscClient send of /composition/master (OSC chokepoint baseline)
  4. Prints what landed on each wire, with PASS/FAIL per leg.

Usage:  python scripts/mac/handshake_test.py
"""
from __future__ import annotations

import socket
import sys
import threading
import time
from errno import EADDRINUSE
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import rtmidi

from protocol.messages import encode_action_event
from windows.engines.osc_client import OscClient

DECK_IN = "IAC Driver DECK_IN"   # bridge writes here; Resolume reads here
DECK_OUT = "IAC Driver DECK_OUT"  # Resolume writes feedback here; bridge reads
BRIDGE_UDP = ("127.0.0.1", 45123)
OSC_PORT = 7000

captured_midi: list[tuple[float, list[int]]] = []
captured_osc: list[tuple[float, str]] = []


def _find_port(midi, substr: str) -> int:
    for i, name in enumerate(midi.get_ports()):
        if name == substr:
            return i
    raise SystemExit(f"MIDI port not found: {substr!r}; have {midi.get_ports()}")


def _osc_address(datagram: bytes) -> str:
    end = datagram.find(b"\x00")
    return datagram[:end].decode("utf-8", "replace") if end >= 0 else "<malformed>"


def osc_listener(sock: socket.socket, stop: threading.Event) -> None:
    sock.settimeout(0.2)
    while not stop.is_set():
        try:
            data, _ = sock.recvfrom(4096)
        except socket.timeout:
            continue
        captured_osc.append((time.monotonic(), _osc_address(data)))


def midi_callback(event, _data=None) -> None:
    message, _delta = event
    captured_midi.append((time.monotonic(), list(message)))


def main() -> int:
    # --- MIDI capture on DECK_IN (what Resolume would receive) ---
    midi_in = rtmidi.MidiIn()
    midi_in.open_port(_find_port(midi_in, DECK_IN))
    midi_in.set_callback(midi_callback)

    # --- feedback sender on DECK_OUT (simulate Resolume's MIDI OUT) ---
    fb_out = rtmidi.MidiOut()
    fb_out.open_port(_find_port(fb_out, DECK_OUT))

    # --- OSC capture on :7000 (what Resolume's OSC input would receive) ---
    osc_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    osc_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        osc_sock.bind(("", OSC_PORT))
    except OSError as exc:
        if exc.errno == EADDRINUSE:
            raise SystemExit(
                f"OSC port :{OSC_PORT} is already in use. Close Resolume Arena "
                "or any other OSC listener before running this wire sniffer."
            ) from exc
        raise
    stop = threading.Event()
    t = threading.Thread(target=osc_listener, args=(osc_sock, stop), daemon=True)
    t.start()

    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def fire_action(action: str, state: str, seq: int) -> None:
        tx.sendto(encode_action_event(action=action, state=state, seq=seq), BRIDGE_UDP)

    time.sleep(0.3)  # let listeners settle

    print(">> firing BTN_A (note ch0 #36) ...")
    fire_action("BTN_A", "down", 1)
    time.sleep(0.15)
    fire_action("BTN_A", "up", 2)
    time.sleep(0.25)

    print(">> firing START (cc ch2 #78) ...")
    fire_action("START", "down", 3)
    time.sleep(0.15)
    fire_action("START", "up", 4)
    time.sleep(0.25)

    print(">> firing feedback CC ch14/cc90 into DECK_OUT (trips osc_sync) ...")
    fb_out.send_message([0xB0 | 14, 90, 127])  # rising edge -> osc_sync pass
    time.sleep(0.8)  # osc_sync indicator dance includes a 0.3s settle
    fb_out.send_message([0xB0 | 14, 90, 0])
    time.sleep(0.3)

    print(">> direct OscClient /composition/master 0.5 -> :7000 (chokepoint baseline) ...")
    OscClient(host="127.0.0.1", port=OSC_PORT).send("/composition/master", 0.5)
    time.sleep(0.4)

    stop.set()
    t.join(timeout=1.0)
    midi_in.close_port()
    fb_out.close_port()
    osc_sock.close()

    # --- report ---
    print("\n==== CAPTURED MIDI on", DECK_IN, "====")
    for ts, msg in captured_midi:
        print("   ", _describe_midi(msg), " raw=", msg)
    print("\n==== CAPTURED OSC on :%d ====" % OSC_PORT)
    for ts, addr in captured_osc:
        print("   ", addr)

    note_ok = any(m[0] & 0xF0 == 0x90 and m[1] == 36 and m[2] == 127 for _, m in captured_midi)
    cc_ok = any(m[0] & 0xF0 == 0xB0 and m[0] & 0x0F == 2 and m[1] == 78 for _, m in captured_midi)
    osc_ok = len(captured_osc) > 0

    print("\n==== HANDSHAKE RESULT ====")
    print(f"   MIDI note (BTN_A -> note36 ch0):   {'PASS' if note_ok else 'FAIL'}")
    print(f"   MIDI cc   (START -> cc78 ch2):     {'PASS' if cc_ok else 'FAIL'}")
    print(f"   OSC -> :7000 received:             {'PASS' if osc_ok else 'FAIL'}")
    return 0 if (note_ok and cc_ok and osc_ok) else 1


def _describe_midi(m: list[int]) -> str:
    if not m:
        return "<empty>"
    status, ch = m[0] & 0xF0, m[0] & 0x0F
    if status == 0x90 and len(m) >= 3:
        return f"note_on  ch{ch} note{m[1]} vel{m[2]}"
    if status == 0x80 and len(m) >= 3:
        return f"note_off ch{ch} note{m[1]} vel{m[2]}"
    if status == 0xB0 and len(m) >= 3:
        return f"cc       ch{ch} cc{m[1]} val{m[2]}"
    return f"status0x{m[0]:02X}"


if __name__ == "__main__":
    sys.exit(main())
