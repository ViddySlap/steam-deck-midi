"""Round 10: ALL VIDEO buttons looks 3-6 -> LOCAL message cascade.

Ben's working design for ALL VIDEO look 1+2:
  - 1 OSC block to /composition/groups/1/.../look<N>
  - 4 LOCAL blocks targeting sf_r{0,1,2,3}_look<N> button IDs (sets their x)

The LOCAL trigger causes the 4 layer buttons to "press" themselves, which
fires their own OSC to layers 1-4. Plus the OSC directly handles the group
stageflow.

This file applies that pattern to looks 3, 4, 5, 6 on the ALL VIDEO row.
"""

import re
import zlib
from pathlib import Path

HERE = Path(__file__).parent
SRC = Path(r"C:/Users/Ben/Documents/ViddyVault/Projects/steam-deck-midi/notes/2026-05-12-post-ben-fix/STEAMDECK V2.tosc")
DST = HERE / "STEAMDECK V2.tosc.r10"


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


def get_node_id(data, name):
    s, e = find_node_span(data, name)
    block = data[s:e]
    m = re.search(rb"<node ID='([^']+)' type=", block)
    return m.group(1).decode() if m else None


def make_local_block(dst_id):
    """LOCAL message: copy this button's x to dst button's x."""
    return (
        "<local>"
        "<enabled>1</enabled>"
        "<triggers><trigger><var><![CDATA[x]]></var><condition>ANY</condition></trigger></triggers>"
        "<type>VALUE</type>"
        "<conversion>FLOAT</conversion>"
        "<value><![CDATA[x]]></value>"
        "<scaleMin>0</scaleMin><scaleMax>1</scaleMax>"
        "<dstType>VALUE</dstType>"
        "<dstVar><![CDATA[x]]></dstVar>"
        f"<dstID><![CDATA[{dst_id}]]></dstID>"
        "</local>"
    )


def make_group_osc_block(look_n):
    """OSC to /composition/groups/1/.../look<N> with VALUE x."""
    path = f"/composition/groups/1/video/effects/stageflow/effect/look{look_n}"
    return (
        "<osc>"
        "<enabled>1</enabled>"
        "<send>1</send>"
        "<receive>1</receive>"
        "<feedback>0</feedback>"
        "<noDuplicates>0</noDuplicates>"
        "<connections>1111111111</connections>"
        "<triggers><trigger><var><![CDATA[x]]></var><condition>ANY</condition></trigger></triggers>"
        "<path><partial>"
        "<type>CONSTANT</type><conversion>STRING</conversion>"
        f"<value><![CDATA[{path}]]></value>"
        "<scaleMin>0</scaleMin><scaleMax>1</scaleMax>"
        "</partial></path>"
        "<arguments><partial>"
        "<type>VALUE</type><conversion>FLOAT</conversion>"
        "<value><![CDATA[x]]></value>"
        "<scaleMin>0</scaleMin><scaleMax>1</scaleMax>"
        "</partial></arguments>"
        "</osc>"
    )


def rebuild_all_video_button(data, look_n, dst_ids):
    """Replace sf_r0_groupvideo_look<N>'s entire <messages>...</messages>."""
    name = f"sf_r0_groupvideo_look{look_n}"
    s, e = find_node_span(data, name)
    block = data[s:e]

    osc_block = make_group_osc_block(look_n)
    local_blocks = "".join(make_local_block(d) for d in dst_ids)
    new_messages = "<messages>" + osc_block + local_blocks + "</messages>"

    new_block = re.sub(
        rb"<messages>.*?</messages>",
        new_messages.encode(),
        block,
        count=1,
        flags=re.DOTALL,
    )
    if new_block == block:
        print(f"  WARNING: no replacement for {name!r}")
        return data
    return data.replace(block, new_block, 1)


def main():
    raw = SRC.read_bytes()
    data = zlib.decompress(raw)
    print(f"Decompressed: {len(data):,} bytes")

    # For each look 3-6, find the 4 layer button IDs (sf_r0_lookN..sf_r3_lookN)
    for look_n in (3, 4, 5, 6):
        dst_ids = []
        for row in (0, 1, 2, 3):  # the 4 layer rows
            nid = get_node_id(data, f"sf_r{row}_look{look_n}")
            if not nid:
                print(f"  MISSING ID for sf_r{row}_look{look_n}")
            else:
                dst_ids.append(nid)
        print(f"\nLOOK {look_n}: dst_ids = {dst_ids}")
        data = rebuild_all_video_button(data, look_n, dst_ids)
        print(f"  rebuilt sf_r0_groupvideo_look{look_n}")

    out_raw = zlib.compress(data)
    DST.write_bytes(out_raw)
    print(f"\nWrote {DST}  ({len(out_raw):,} compressed bytes)")


if __name__ == "__main__":
    main()
