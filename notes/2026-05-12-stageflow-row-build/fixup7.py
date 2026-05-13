"""Round 9: V1 WORKING config.

V1 patch reference (from notes/_backups/2026-05-05/STEAMDECK V1.tosc)
shows the working stageflow look button config:
  buttonType: 2  (Toggle on Press!) <- THIS is the key
  press: 1, release: 1
  noDuplicates: 0  (allow re-sending)
  receive: 1
  trigger: var=x condition=ANY
  arg: VALUE/FLOAT/x

Apply to look + cascade buttons. Leave mode buttons alone.
"""

import re
import zlib
from pathlib import Path

HERE = Path(__file__).parent
SRC = Path(r"C:/Users/Ben/Documents/ViddyVault/Projects/steam-deck-midi/notes/2026-05-12-post-ben-edit-3/STEAMDECK V2.tosc")
DST = HERE / "STEAMDECK V2.tosc.r9"


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


def v1_config(data, name):
    s, e = find_node_span(data, name)
    block = data[s:e]
    new_block = block

    # buttonType -> 2 (Toggle on Press)
    new_block = re.sub(
        rb"(<key><!\[CDATA\[buttonType\]\]></key><value>)\d(</value>)",
        rb"\g<1>2\g<2>", new_block,
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
    # noDuplicates -> 0
    new_block = re.sub(
        rb"<noDuplicates>\d</noDuplicates>", b"<noDuplicates>0</noDuplicates>",
        new_block,
    )
    # receive -> 1
    new_block = re.sub(
        rb"<receive>\d</receive>", b"<receive>1</receive>", new_block,
    )
    # Trigger var=touch -> var=x, condition -> ANY
    new_block = new_block.replace(
        b"<trigger><var><![CDATA[touch]]></var><condition>",
        b"<trigger><var><![CDATA[x]]></var><condition>",
    )
    new_block = re.sub(
        rb"<condition>[A-Z]+</condition>", b"<condition>ANY</condition>",
        new_block,
    )
    # Arg: VALUE x FLOAT
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
        data = v1_config(data, name)
    print(f"Applied V1 config to {len(look_names)} buttons (buttonType=2)")

    out_raw = zlib.compress(data)
    DST.write_bytes(out_raw)
    print(f"Wrote {DST}  ({len(out_raw):,} compressed bytes)")


if __name__ == "__main__":
    main()
