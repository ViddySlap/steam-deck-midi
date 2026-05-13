"""Post-Ben-edit fixups for STAGEFLOW page.

Starts from the current saved-on-Deck .tosc (post-Ben edits) and applies:

  1. Press-only behavior on all 42 stageflow LOOK buttons.
     Changes each button's OSC <trigger> condition from ANY -> RISE so
     OSC fires only on press (x rising edge), not on release.

  2. sf_mode_on_layers: add 4 more OSC blocks so it covers layers 3, 4, 6, 7.
     Result: groups/1 bypassed=1, layers/{1,2,3,4} bypassed=0, layers/{6,7} bypassed=0
     (group OFF, all layers ON including logos).

  3. sf_mode_on_group: add 4 more OSC blocks so it covers layers 3, 4, 6, 7.
     Result: groups/1 bypassed=0, layers/{1,2,3,4} bypassed=1, layers/{6,7} bypassed=0
     (group ON, layers 1-4 OFF, logos ON).

  4. sf_mode_off: verify already 7 paths.

In:  ViddyVault/.../notes/2026-05-12-post-ben-edit/STEAMDECK V2.tosc
Out: ./STEAMDECK V2.tosc.fixed
"""

import re
import zlib
from pathlib import Path

HERE = Path(__file__).parent
SRC = Path(r"C:/Users/Ben/Documents/ViddyVault/Projects/steam-deck-midi/notes/2026-05-12-post-ben-edit/STEAMDECK V2.tosc")
DST = HERE / "STEAMDECK V2.tosc.fixed"


def find_node_span(data: bytes, name_value: str) -> tuple[int, int]:
    needle = (b"<value><![CDATA[" + name_value.encode() + b"]]></value>")
    idx = data.find(needle)
    if idx < 0:
        raise RuntimeError(f"name not found: {name_value!r}")
    start = data.rfind(b"<node ", 0, idx)
    if start < 0:
        raise RuntimeError(f"<node ...> not found before {name_value!r}")
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


def fix_button_to_rise(data: bytes, name: str) -> bytes:
    """Change all <condition>ANY</condition> in this button's OSC blocks to RISE."""
    s, e = find_node_span(data, name)
    block = data[s:e]
    new_block = block.replace(b"<condition>ANY</condition>", b"<condition>RISE</condition>")
    if new_block == block:
        return data  # no change (already RISE or no ANY)
    return data.replace(block, new_block, 1)


def make_osc_block(path: str, value: int) -> bytes:
    """An OSC block matching sf_mode_* format: trig x/RISE, arg CONSTANT/FLOAT/value."""
    xml = (
        "<osc>"
        "<enabled>1</enabled>"
        "<send>1</send>"
        "<receive>0</receive>"
        "<feedback>0</feedback>"
        "<noDuplicates>1</noDuplicates>"
        "<connections>1111111111</connections>"
        "<triggers><trigger><var><![CDATA[x]]></var><condition>RISE</condition></trigger></triggers>"
        "<path><partial>"
        "<type>CONSTANT</type><conversion>STRING</conversion>"
        f"<value><![CDATA[{path}]]></value>"
        "<scaleMin>0</scaleMin><scaleMax>1</scaleMax>"
        "</partial></path>"
        "<arguments><partial>"
        "<type>CONSTANT</type><conversion>FLOAT</conversion>"
        f"<value><![CDATA[{value}]]></value>"
        "<scaleMin>0</scaleMin><scaleMax>1</scaleMax>"
        "</partial></arguments>"
        "</osc>"
    )
    return xml.encode()


def add_osc_blocks_to_button(data: bytes, name: str, new_blocks: list[bytes]) -> bytes:
    """Insert new <osc> blocks right before </messages> of this button."""
    s, e = find_node_span(data, name)
    block = data[s:e]
    # Find the </messages> at the END (the button's outer messages closing tag).
    # In TouchOSC button format: <messages><osc>...</osc>...</messages></node>
    close_idx = block.rfind(b"</messages>")
    if close_idx < 0:
        raise RuntimeError(f"no </messages> in {name!r}")
    insert = b"".join(new_blocks)
    new_block = block[:close_idx] + insert + block[close_idx:]
    return data.replace(block, new_block, 1)


def main():
    print(f"Reading {SRC}")
    raw = SRC.read_bytes()
    data = zlib.decompress(raw)
    print(f"Decompressed: {len(raw):,} -> {len(data):,} bytes")

    # ----- Step 1: change ANY -> RISE on all 42 stageflow look buttons -----
    fixed = 0
    skipped = 0
    button_names = []
    # 36 existing sf_r<N>_look<M>
    for row in (0, 1, 2, 3, 5, 6):
        for look in range(1, 7):
            button_names.append(f"sf_r{row}_look{look}")
    # 6 my new ALL VIDEO buttons
    for look in range(1, 7):
        button_names.append(f"sf_r0_groupvideo_look{look}")
    for name in button_names:
        new_data = fix_button_to_rise(data, name)
        if new_data is not data and new_data != data:
            fixed += 1
            data = new_data
        else:
            skipped += 1
    print(f"Step 1: changed ANY->RISE on {fixed} buttons (skipped {skipped})")

    # ----- Step 2: sf_mode_on_layers — add 4 paths -----
    on_layers_extra = [
        make_osc_block("/composition/layers/3/video/effects/stageflow/bypassed", 0),
        make_osc_block("/composition/layers/4/video/effects/stageflow/bypassed", 0),
        make_osc_block("/composition/layers/6/video/effects/stageflow/bypassed", 0),
        make_osc_block("/composition/layers/7/video/effects/stageflow/bypassed", 0),
    ]
    data = add_osc_blocks_to_button(data, "sf_mode_on_layers", on_layers_extra)
    print(f"Step 2: added 4 OSC paths to sf_mode_on_layers")

    # ----- Step 3: sf_mode_on_group — add 4 paths -----
    on_group_extra = [
        make_osc_block("/composition/layers/3/video/effects/stageflow/bypassed", 1),
        make_osc_block("/composition/layers/4/video/effects/stageflow/bypassed", 1),
        make_osc_block("/composition/layers/6/video/effects/stageflow/bypassed", 0),  # logos stay ON
        make_osc_block("/composition/layers/7/video/effects/stageflow/bypassed", 0),  # logos stay ON
    ]
    data = add_osc_blocks_to_button(data, "sf_mode_on_group", on_group_extra)
    print(f"Step 3: added 4 OSC paths to sf_mode_on_group")

    # ----- Step 4: sf_mode_off — already has 7 paths, just verify -----
    s, e = find_node_span(data, "sf_mode_off")
    blk = data[s:e]
    print(f"Step 4: sf_mode_off has {blk.count(b'<osc>')} OSC blocks (expect 7)")

    # ----- Compress + write -----
    out_raw = zlib.compress(data)
    DST.write_bytes(out_raw)
    print(f"Wrote {DST}  ({len(data):,} bytes uncompressed, {len(out_raw):,} compressed)")


if __name__ == "__main__":
    main()
