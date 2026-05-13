"""Edit STEAMDECK V2.tosc: collapse 42 stageflow label paths to 6 shared
paths + recenter labels over their buttons.

Inputs:
- C:/Users/Ben/Documents/project-workspaces/steam-deck-midi/scratch/2026-05-12-stageflow-rework/STEAMDECK V2.xml
  (decompressed source)

Output:
- C:/Users/Ben/Documents/project-workspaces/steam-deck-midi/scratch/2026-05-12-stageflow-rework/STEAMDECK V2.edited.tosc
  (zlib-compressed)
"""
from __future__ import annotations
import re
import zlib
from pathlib import Path

SRC_XML = Path(
    "C:/Users/Ben/Documents/project-workspaces/steam-deck-midi/scratch/"
    "2026-05-12-stageflow-rework/STEAMDECK V2.xml"
)
OUT_TOSC = Path(
    "C:/Users/Ben/Documents/project-workspaces/steam-deck-midi/scratch/"
    "2026-05-12-stageflow-rework/STEAMDECK V2.edited.tosc"
)

# Target receive path template: all 7 rows share the same 6 OSC paths.
NEW_PATH_TPL = (
    "/composition/video/effects/stageflowbridge/effect/looks/"
    "look{n}name/params/lines"
)

# Map label-row prefix -> (button-name-prefix, y).
# Row prefixes are from current sf_<prefix>_look<N>_lbl naming.
# Button-name prefixes come from current sf_r<R>(_<groupvideo>)_look<N>.
ROW_INFO = {
    # label_prefix: (button_x_pattern, y)
    "groupvideo": 150,
    "layer4": 320,
    "layer3": 489,
    "layer2": 659,
    "layer1": 828,
    "logo2": 998,
    "logo1": 1167,
}
# All buttons share these x positions and (w=396, h=153).
X_BY_SLOT = {1: 210, 2: 616, 3: 1022, 4: 1428, 5: 1834, 6: 2240}
W, H = 396, 153


LABEL_NODE_RE = re.compile(
    r"<node ID='([^']+)' type='TEXT'[^>]*>(.*?)</node>", re.DOTALL
)
NAME_RE = re.compile(
    r"<key><!\[CDATA\[name\]\]></key><value><!\[CDATA\[([^\]]*)\]\]></value>"
)
FRAME_RE = re.compile(
    r"(<key><!\[CDATA\[frame\]\]></key><value>)"
    r"<x>\d+</x><y>\d+</y><w>\d+</w><h>\d+</h>"
    r"(</value>)"
)
RECEIVE_PATH_RE = re.compile(
    r"(<path><partial><type>CONSTANT</type><conversion>STRING</conversion>"
    r"<value><!\[CDATA\[)"
    r"/composition/video/effects/stageflowbridge/effect/"
    r"[^]]+"
    r"(\]\]></value>)"
)


def edit_label_block(block: str, name: str) -> str:
    m = re.match(r"sf_(\w+)_look(\d+)_lbl$", name)
    if not m:
        return block
    row_prefix = m.group(1)
    slot = int(m.group(2))
    y = ROW_INFO.get(row_prefix)
    x = X_BY_SLOT.get(slot)
    if y is None or x is None:
        return block
    new_frame = (
        f"<x>{x}</x><y>{y}</y><w>{W}</w><h>{H}</h>"
    )
    new_path = NEW_PATH_TPL.format(n=slot)
    # Replace frame
    new_block = FRAME_RE.sub(
        lambda mm: mm.group(1) + new_frame + mm.group(2), block, count=1
    )
    # Replace receive path
    new_block = RECEIVE_PATH_RE.sub(
        lambda mm: mm.group(1) + new_path + mm.group(2), new_block, count=1
    )
    return new_block


def main() -> None:
    text = SRC_XML.read_text(encoding="utf-8")

    edits = 0
    skipped = 0

    def repl(m: re.Match) -> str:
        nonlocal edits, skipped
        block = m.group(0)
        if "stageflowbridge" not in block:
            return block
        name_m = NAME_RE.search(block)
        if not name_m:
            skipped += 1
            return block
        name = name_m.group(1)
        new_block = edit_label_block(block, name)
        if new_block != block:
            edits += 1
        else:
            skipped += 1
        return new_block

    new_text = LABEL_NODE_RE.sub(repl, text)
    print(f"edits={edits} skipped={skipped}")
    # Sanity: no remaining old stageflowbridge paths in receive blocks
    remaining_old = len(
        re.findall(
            r"/composition/video/effects/stageflowbridge/effect/"
            r"(?:groupvideo|layer[1-4]|logo[12])/",
            new_text,
        )
    )
    print(f"remaining old stageflowbridge paths: {remaining_old}")

    new_paths = len(re.findall(r"/effects/stageflowbridge/effect/looks/look\dname", new_text))
    print(f"new 'looks/look<N>name' paths in xml: {new_paths}")

    # Compress and write .tosc
    xml_bytes = new_text.encode("utf-8")
    tosc_bytes = zlib.compress(xml_bytes)
    OUT_TOSC.write_bytes(tosc_bytes)
    print(f"wrote {OUT_TOSC} ({len(tosc_bytes)} bytes compressed, "
          f"{len(xml_bytes)} bytes xml)")


if __name__ == "__main__":
    main()
