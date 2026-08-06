"""Deck-side raw keycode watcher for diagnosing Steam Input layer switching.

The sender translates X11 keycodes to action names via deck_bindings.json and
SILENTLY DROPS anything unmapped (`flush_block` returns None for an unknown
keycode, with no log line). That makes three very different failures look
identical from the Windows side:

  1. Steam Input is not switching action sets   -> same keycode on both layers
  2. Steam Input switches to the wrong keys     -> a keycode with no binding
  3. Steam Input sends nothing at all           -> no event

This prints EVERY raw keycode with its binding (or *** UNMAPPED ***), so the
three cases are told apart at a glance.

Safe to run while the sender is running: XI2 raw events are delivered to every
client that selects for them, so this observes without stealing input.

Usage (on the Deck, from the repo root):
    python3 scripts/keycode_watch.py
"""

from __future__ import annotations

import json
import os
import select
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deck.xinput_send import Xi2RawListener  # noqa: E402

SETTINGS_PATH = "config/deck_runtime_settings.local.json"
BINDINGS_PATH = "config/deck_bindings.json"

# Actions worth calling out loudly -- these are the ones the layer diagnosis
# turns on. Everything else still prints, just without the marker.
WATCHED = {
    "L1", "L1_LAYER_2", "R1", "R1_LAYER_2",
    "BTN_A", "BTN_A_LAYER_2", "BTN_B", "BTN_B_LAYER_2",
    "BTN_X", "BTN_X_LAYER_2", "BTN_Y", "BTN_Y_LAYER_2",
    "SELECT", "START", "L4",
}


def _load(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def main() -> int:
    settings = _load(SETTINGS_PATH, {})
    device_id = int(settings.get("device_id", "5"))

    raw_bindings = _load(BINDINGS_PATH, {})
    bindings = raw_bindings.get("bindings", raw_bindings)

    listener = Xi2RawListener(device_id)
    print(
        "keycode watcher: device_id=%s, %d bindings loaded"
        % (device_id, len(bindings)),
        flush=True,
    )
    print("waiting for input (Ctrl-C to stop)...", flush=True)
    print("-" * 64, flush=True)

    start = time.monotonic()
    try:
        while True:
            ready, _, _ = select.select([listener.fileno()], [], [], 0.5)
            if not ready:
                continue
            while True:
                event = listener.read_event()
                if event is None:
                    break
                if event.state != "down":
                    continue  # presses only; releases just double the noise
                action = bindings.get(event.keycode)
                label = action if action else "*** UNMAPPED KEYCODE ***"
                marker = "  <<<" if action in WATCHED else ""
                print(
                    "[%7.2fs] keycode %-5s -> %s%s"
                    % (time.monotonic() - start, event.keycode, label, marker),
                    flush=True,
                )
    except KeyboardInterrupt:
        print("\nstopped.", flush=True)
    finally:
        listener.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
