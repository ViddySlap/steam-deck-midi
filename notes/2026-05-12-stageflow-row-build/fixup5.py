"""Round 7: toggle look + cascade buttons, keep mode buttons one-shot.

  Look buttons (36 sf_r* + 6 sf_r0_groupvideo): toggle config
    buttonType=1, press=1, release=0
    Trigger: var=x condition=ANY
    Arg: VALUE x FLOAT (sends 0 or 1 based on toggle state)
    noDuplicates=0 (allow re-send if needed)
    receive=0 (no Resolume -> button sync, to avoid loops/state confusion)
    No Lua

  Mode buttons (3): keep r6 one-shot config (already working since no toggle)

  Pull from Deck first.
"""

import re
import zlib
from pathlib import Path

HERE = Path(__file__).parent
SRC = Path(r"C:/Users/Ben/Documents/ViddyVault/Projects/steam-deck-midi/notes/2026-05-12-post-ben-edit-3/STEAMDECK V2.tosc")  # post-r6
DST = HERE / "STEAMDECK V2.tosc.r7"


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


def set_look_button_toggle(data, name):
    """Apply toggle config to a single look-style button (1 or 5 OSC blocks)."""
    s, e = find_node_span(data, name)
    block = data[s:e]
    new_block = block

    # buttonType -> 1 (toggle)
    new_block = re.sub(
        rb"(<key><!\[CDATA\[buttonType\]\]></key><value>)\d(</value>)",
        rb"\g<1>1\g<2>",
        new_block,
    )

    # press -> 1, release -> 0
    new_block = re.sub(
        rb"(<key><!\[CDATA\[press\]\]></key><value>)\d(</value>)",
        rb"\g<1>1\g<2>",
        new_block,
    )
    new_block = re.sub(
        rb"(<key><!\[CDATA\[release\]\]></key><value>)\d(</value>)",
        rb"\g<1>0\g<2>",
        new_block,
    )

    # Trigger: var=touch -> var=x, condition=RISE/ANY -> ANY
    new_block = new_block.replace(
        b"<trigger><var><![CDATA[touch]]></var><condition>",
        b"<trigger><var><![CDATA[x]]></var><condition>",
    )
    new_block = re.sub(
        rb"<condition>[A-Z]+</condition>",
        b"<condition>ANY</condition>",
        new_block,
    )

    # noDuplicates -> 0
    new_block = re.sub(
        rb"<noDuplicates>\d</noDuplicates>",
        b"<noDuplicates>0</noDuplicates>",
        new_block,
    )

    # receive -> 0
    new_block = re.sub(
        rb"<receive>\d</receive>",
        b"<receive>0</receive>",
        new_block,
    )

    # Arg: CONSTANT FLOAT 1 -> VALUE FLOAT x (so it toggles based on state)
    new_block = re.sub(
        rb"<arguments><partial><type>CONSTANT</type><conversion>FLOAT</conversion><value><!\[CDATA\[1\]\]></value>",
        b"<arguments><partial><type>VALUE</type><conversion>FLOAT</conversion><value><![CDATA[x]]></value>",
        new_block,
    )

    return data.replace(block, new_block, 1) if new_block != block else data


def main():
    print(f"Reading {SRC}")
    raw = SRC.read_bytes()
    data = zlib.decompress(raw)

    # 36 existing look + 6 cascade
    look_names = []
    for row in (0, 1, 2, 3, 5, 6):
        for look in range(1, 7):
            look_names.append(f"sf_r{row}_look{look}")
    for look in range(1, 7):
        look_names.append(f"sf_r0_groupvideo_look{look}")

    for name in look_names:
        data = set_look_button_toggle(data, name)
    print(f"Set toggle on {len(look_names)} look + cascade buttons")

    # Mode buttons: leave as r6 one-shot
    print("Mode buttons: untouched (one-shot config)")

    out_raw = zlib.compress(data)
    DST.write_bytes(out_raw)
    print(f"Wrote {DST}  ({len(out_raw):,} compressed bytes)")


if __name__ == "__main__":
    main()
