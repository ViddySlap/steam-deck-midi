"""Round 6 fix: clean reset on all stageflow buttons.

Strip the toggle/Lua/radio complexity. Each button becomes a simple
momentary press-only OSC sender:
  - buttonType: 0 (momentary)
  - Trigger: var=touch condition=RISE (fires on user press only)
  - noDuplicates: 0 (allow re-sending same value)
  - Lua scripts removed (mode buttons)

Look buttons + ALL VIDEO: keep their existing OSC paths and constants.
Their arg stays VALUE x for look buttons (so they send 0 or 1 based on x).
Mode buttons: keep their 7-9 OSC paths with CONSTANT 0/1 per path.

Tradeoff: no visual latch, no radio behavior, no toggle off. User must
visually confirm state in Resolume. But all buttons fire reliably.

Pull from Deck before running so we apply on top of Ben's most recent saves.
"""

import re
import zlib
from pathlib import Path

HERE = Path(__file__).parent
SRC = Path(r"C:/Users/Ben/Documents/ViddyVault/Projects/steam-deck-midi/notes/2026-05-12-post-ben-edit-3/STEAMDECK V2.tosc")
DST = HERE / "STEAMDECK V2.tosc.r6"


def find_node_span(data, name):
    needle = b"<value><![CDATA[" + name.encode() + b"]]></value>"
    idx = data.find(needle)
    if idx < 0:
        raise RuntimeError(f"name not found: {name!r}")
    start = data.rfind(b"<node ", 0, idx)
    depth = 0
    for m in re.finditer(rb"<node\b|</node>", data[start:]):
        s, e = m.span()
        s += start; e += start
        if data[s:s+5] == b"<node":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return start, e
    raise RuntimeError("unbalanced <node>")


def reset_button(data, name, want_arg_value_x=False):
    """Reset a button's OSC blocks to simplest reliable config."""
    s, e = find_node_span(data, name)
    block = data[s:e]
    new_block = block

    # buttonType 1 -> 0 (momentary)
    new_block = re.sub(
        rb"(<key><!\[CDATA\[buttonType\]\]></key><value>)\d(</value>)",
        rb"\g<1>0\g<2>",
        new_block,
    )

    # release 1 -> 0 (only fire on press)
    new_block = re.sub(
        rb"(<key><!\[CDATA\[release\]\]></key><value>)\d(</value>)",
        rb"\g<1>0\g<2>",
        new_block,
    )

    # Trigger var=x -> var=touch
    new_block = new_block.replace(
        b"<trigger><var><![CDATA[x]]></var><condition>",
        b"<trigger><var><![CDATA[touch]]></var><condition>",
    )

    # All trigger conditions -> RISE
    new_block = re.sub(
        rb"<condition>[A-Z]+</condition>",
        b"<condition>RISE</condition>",
        new_block,
    )

    # noDuplicates 1 -> 0
    new_block = re.sub(
        rb"<noDuplicates>\d</noDuplicates>",
        b"<noDuplicates>0</noDuplicates>",
        new_block,
    )

    # Remove any Lua script property entirely
    new_block = re.sub(
        rb"<property type='s'><key><!\[CDATA\[script\]\]></key><value><!\[CDATA\[[\s\S]*?\]\]></value></property>",
        b"",
        new_block,
    )

    # For look + cascade buttons (want_arg_value_x=False): switch arg from VALUE x
    # to CONSTANT 1 so the look is always SET (not toggled). Keep mode buttons as-is.
    if not want_arg_value_x:
        new_block = re.sub(
            rb"<arguments><partial><type>VALUE</type><conversion>FLOAT</conversion><value><!\[CDATA\[x\]\]></value>",
            b"<arguments><partial><type>CONSTANT</type><conversion>FLOAT</conversion><value><![CDATA[1]]></value>",
            new_block,
        )

    return data.replace(block, new_block, 1) if new_block != block else data


def main():
    print(f"Reading {SRC}")
    raw = SRC.read_bytes()
    data = zlib.decompress(raw)

    # 36 existing look + 6 ALL VIDEO + 3 mode buttons
    look_names = []
    for row in (0, 1, 2, 3, 5, 6):
        for look in range(1, 7):
            look_names.append(f"sf_r{row}_look{look}")
    for look in range(1, 7):
        look_names.append(f"sf_r0_groupvideo_look{look}")

    for name in look_names:
        data = reset_button(data, name, want_arg_value_x=False)
    print(f"Reset {len(look_names)} look + cascade buttons")

    for name in ("sf_mode_on_layers", "sf_mode_on_group", "sf_mode_off"):
        data = reset_button(data, name, want_arg_value_x=False)  # mode args are CONSTANT already
    print("Reset 3 mode buttons")

    out_raw = zlib.compress(data)
    DST.write_bytes(out_raw)
    print(f"Wrote {DST}  ({len(out_raw):,} compressed bytes)")


if __name__ == "__main__":
    main()
