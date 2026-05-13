"""Round 8: Revert look buttons to the r4 KNOWN-WORKING config.

Ben reported toggle behavior worked on r4. Examining post-r4 file shows
r4 look buttons actually had: buttonType=0 momentary, press=1, release=1,
trigger=x/RISE, arg=VALUE x. Most likely Resolume's stageflow look<N> param
treats each 1-send as a toggle (1 -> selected; another 1 -> deselected).

Apply r4 config to all 42 look + cascade buttons. Leave mode buttons alone
(currently at r6 one-shot config).

Source: most recent Deck pull (post-r7).
"""

import re
import zlib
from pathlib import Path

HERE = Path(__file__).parent
SRC = Path(r"C:/Users/Ben/Documents/ViddyVault/Projects/steam-deck-midi/notes/2026-05-12-post-ben-edit-3/STEAMDECK V2.tosc")
DST = HERE / "STEAMDECK V2.tosc.r8"


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


def r4_config(data, name):
    s, e = find_node_span(data, name)
    block = data[s:e]
    new_block = block

    # buttonType -> 0 (momentary)
    new_block = re.sub(
        rb"(<key><!\[CDATA\[buttonType\]\]></key><value>)\d(</value>)",
        rb"\g<1>0\g<2>", new_block,
    )
    # press -> 1, release -> 1
    new_block = re.sub(
        rb"(<key><!\[CDATA\[press\]\]></key><value>)\d(</value>)",
        rb"\g<1>1\g<2>", new_block,
    )
    new_block = re.sub(
        rb"(<key><!\[CDATA\[release\]\]></key><value>)\d(</value>)",
        rb"\g<1>1\g<2>", new_block,
    )
    # noDuplicates -> 1
    new_block = re.sub(
        rb"<noDuplicates>\d</noDuplicates>", b"<noDuplicates>1</noDuplicates>",
        new_block,
    )
    # receive -> 1
    new_block = re.sub(
        rb"<receive>\d</receive>", b"<receive>1</receive>", new_block,
    )
    # Trigger: var=touch -> var=x, condition -> RISE
    new_block = new_block.replace(
        b"<trigger><var><![CDATA[touch]]></var><condition>",
        b"<trigger><var><![CDATA[x]]></var><condition>",
    )
    new_block = re.sub(
        rb"<condition>[A-Z]+</condition>", b"<condition>RISE</condition>", new_block,
    )
    # Arg CONSTANT 1 -> VALUE x
    new_block = re.sub(
        rb"<arguments><partial><type>CONSTANT</type><conversion>FLOAT</conversion><value><!\[CDATA\[1\]\]></value>",
        b"<arguments><partial><type>VALUE</type><conversion>FLOAT</conversion><value><![CDATA[x]]></value>",
        new_block,
    )

    return data.replace(block, new_block, 1) if new_block != block else data


def main():
    raw = SRC.read_bytes()
    data = zlib.decompress(raw)

    look_names = []
    for row in (0, 1, 2, 3, 5, 6):
        for look in range(1, 7):
            look_names.append(f"sf_r{row}_look{look}")
    for look in range(1, 7):
        look_names.append(f"sf_r0_groupvideo_look{look}")

    for name in look_names:
        data = r4_config(data, name)
    print(f"Applied r4 config to {len(look_names)} buttons")

    out_raw = zlib.compress(data)
    DST.write_bytes(out_raw)
    print(f"Wrote {DST}  ({len(out_raw):,} compressed bytes)")


if __name__ == "__main__":
    main()
