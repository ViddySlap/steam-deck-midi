"""Expand STEAMDECK V2.tosc STAGEFLOW page from 6 to 15 button columns.

- Shrinks the 6 existing buttons + labels to fit new column width.
- Adds 9 new buttons + 9 new labels per row.
- Layer/Logo row buttons: 1 OSC out to `/composition/.../stageflow/effect/look<N>`.
- GROUP VIDEO row buttons: 1 OSC out + 4 LOCAL messages to mirror to sf_r0/r1/r2/r3 look<N>.
- Labels receive on `/.../stageflowbridge/effect/looks/look<N>name/params/lines`.
- Recenters labels exactly on their buttons.

Reads decompressed XML; emits a fresh .tosc.
"""
from __future__ import annotations
import re
import uuid
import zlib
from pathlib import Path

SRC_XML = Path(
    "C:/Users/Ben/Documents/project-workspaces/steam-deck-midi/scratch/"
    "2026-05-12-stageflow-rework/STEAMDECK V2.edited.xml"
)
OUT_TOSC = Path(
    "C:/Users/Ben/Documents/project-workspaces/steam-deck-midi/scratch/"
    "2026-05-12-stageflow-rework/STEAMDECK V2.expanded.tosc"
)

# Layout: 15 buttons in the original 6-button span.
X0 = 210
W = 152
GAP = 10
STEP = W + GAP  # 162
H = 153
NEW_X = [X0 + n * STEP for n in range(15)]

# Row info: (button_name_prefix, label_name_prefix, button_y, label_y, layer_for_layer_rows, is_groupvideo)
# Layer/group OSC path stems for the buttons:
#   group video: /composition/groups/1/video/effects/stageflow/effect/look<N>
#   layer rows: /composition/layers/<L>/video/effects/stageflow/effect/look<N>
ROWS = [
    # button_prefix, label_prefix, y, osc_layer (None=group, else layer index), is_groupvideo
    ("sf_r0_groupvideo_look", "sf_groupvideo_look_lbl", 150, None, True),
    ("sf_r0_look", "sf_layer4_look_lbl", 320, 4, False),
    ("sf_r1_look", "sf_layer3_look_lbl", 489, 3, False),
    ("sf_r2_look", "sf_layer2_look_lbl", 659, 2, False),
    ("sf_r3_look", "sf_layer1_look_lbl", 828, 1, False),
    ("sf_r6_look", "sf_logo2_look_lbl", 998, 7, False),
    ("sf_r5_look", "sf_logo1_look_lbl", 1167, 6, False),
]

NODE_BUTTON_RE = re.compile(
    r"<node ID='([^']+)' type='BUTTON'[^>]*>"
    r"(?:(?!</node>).)*?"
    r"CDATA\[(sf_[A-Za-z0-9_]+)\]"
    r"(?:(?!</node>).)*?</node>",
    re.DOTALL,
)
NODE_TEXT_RE = re.compile(
    r"<node ID='([^']+)' type='TEXT'[^>]*>"
    r"(?:(?!</node>).)*?"
    r"CDATA\[(sf_[A-Za-z0-9_]+_lbl)\]"
    r"(?:(?!</node>).)*?</node>",
    re.DOTALL,
)

FRAME_RE_TPL = re.compile(
    r"(<key><!\[CDATA\[frame\]\]></key><value>)"
    r"<x>\d+</x><y>\d+</y><w>\d+</w><h>\d+</h>"
    r"(</value>)"
)


def new_id() -> str:
    return str(uuid.uuid4())


def make_frame_xml(x: int, y: int, w: int, h: int) -> str:
    return f"<x>{x}</x><y>{y}</y><w>{w}</w><h>{h}</h>"


def replace_frame(block: str, x: int, y: int, w: int, h: int) -> str:
    return FRAME_RE_TPL.sub(
        lambda m: m.group(1) + make_frame_xml(x, y, w, h) + m.group(2),
        block,
        count=1,
    )


def replace_node_name(block: str, new_name: str) -> str:
    return re.sub(
        r"(<key><!\[CDATA\[name\]\]></key><value><!\[CDATA\[)[^\]]*(\]\]></value>)",
        lambda m: m.group(1) + new_name + m.group(2),
        block,
        count=1,
    )


def replace_node_id(block: str, new_uuid: str) -> str:
    return re.sub(
        r"^(<node ID=')[^']+(')",
        lambda m: m.group(1) + new_uuid + m.group(2),
        block,
        count=1,
    )


def replace_osc_path(block: str, new_path: str) -> str:
    return re.sub(
        r"(<path><partial><type>CONSTANT</type><conversion>STRING</conversion>"
        r"<value><!\[CDATA\[)[^\]]+(\]\]></value>)",
        lambda m: m.group(1) + new_path + m.group(2),
        block,
        count=1,
    )


def replace_receive_path(block: str, new_path: str) -> str:
    # First receive-enabled OSC block's path.
    return replace_osc_path(block, new_path)


def replace_cascade_dstids(block: str, new_dstids: list[str]) -> str:
    # Replace the 4 dstID CDATA entries in their existing order.
    pattern = re.compile(
        r"(<dstID><!\[CDATA\[)[^\]]+(\]\]></dstID>)"
    )
    it = iter(new_dstids)

    def sub(m: re.Match) -> str:
        try:
            return m.group(1) + next(it) + m.group(2)
        except StopIteration:
            return m.group(0)

    return pattern.sub(sub, block)


def main() -> None:
    text = SRC_XML.read_text(encoding="utf-8")

    # Pass 1: index all sf_ buttons + labels with their blocks/uuids.
    buttons: dict[str, tuple[str, str, int, int]] = {}  # name -> (uuid, block, start, end)
    for m in NODE_BUTTON_RE.finditer(text):
        buttons[m.group(2)] = (m.group(1), m.group(0), m.start(), m.end())
    labels: dict[str, tuple[str, str, int, int]] = {}
    for m in NODE_TEXT_RE.finditer(text):
        labels[m.group(2)] = (m.group(1), m.group(0), m.start(), m.end())
    print(f"indexed {len(buttons)} sf_ buttons, {len(labels)} sf_*_lbl labels")

    # Pass 2: build new UUIDs for slot 7-15 buttons + labels per row.
    new_button_uuids: dict[tuple[int, int], str] = {}  # (row_idx, slot) -> uuid
    new_label_uuids: dict[tuple[int, int], str] = {}
    for ri, (btn_prefix, lbl_prefix, by, _layer, _gv) in enumerate(ROWS):
        for slot in range(7, 16):
            new_button_uuids[(ri, slot)] = new_id()
            new_label_uuids[(ri, slot)] = new_id()

    # Pass 3: build the full set of replacements.
    # We'll collect (start, end, new_block) tuples and apply them right-to-left
    # so byte offsets remain valid.
    edits: list[tuple[int, int, str]] = []
    inserts_after_last: list[str] = []  # new node blocks, appended at end
    last_node_end = 0

    for ri, (btn_prefix, lbl_prefix, y, layer, is_gv) in enumerate(ROWS):
        # Template button + label: use slot 1 as template (consistent path).
        # Resolve template names: the GROUP VIDEO row's labels are
        # `sf_groupvideo_look<N>_lbl`, not `sf_groupvideo_look_lbl<N>`.
        # Build name fn:
        def btn_name(slot: int) -> str:
            return f"{btn_prefix}{slot}"

        def lbl_name(slot: int) -> str:
            # lbl_prefix already encodes the row; replace trailing _lbl pattern.
            # Format: sf_<row>_look<N>_lbl
            return lbl_prefix.replace("_lbl", f"{slot}_lbl") if "_look_lbl" in lbl_prefix else lbl_prefix.replace("_look_lbl", f"_look{slot}_lbl")

        # Above is convoluted; canonicalize:
        # lbl_prefix is "sf_<row>_look_lbl" (placeholder). Use proper format:
        # actual label name is "sf_<row>_look<N>_lbl".
        # Recompute from row directly:
        row_tag = lbl_prefix.split("_look_lbl")[0]  # "sf_groupvideo" etc.

        def label_name_for_slot(slot: int) -> str:
            return f"{row_tag}_look{slot}_lbl"

        # Rewrite existing slot 1-6 buttons + labels (frame).
        for slot in range(1, 7):
            new_x = NEW_X[slot - 1]
            bn = btn_name(slot)
            if bn in buttons:
                uid, block, s, e = buttons[bn]
                new_block = replace_frame(block, new_x, y, W, H)
                edits.append((s, e, new_block))
                if e > last_node_end:
                    last_node_end = e
            ln = label_name_for_slot(slot)
            if ln in labels:
                uid, block, s, e = labels[ln]
                new_block = replace_frame(block, new_x, y, W, H)
                edits.append((s, e, new_block))
                if e > last_node_end:
                    last_node_end = e

        # Build new slot 7-15 buttons + labels.
        # Template button: take slot 6 (same OSC pattern as 1-6, just look6).
        template_btn_name = btn_name(6)
        if template_btn_name not in buttons:
            print(f"  warning: template {template_btn_name} not found, skipping row")
            continue
        tb_uid, tb_block, *_ = buttons[template_btn_name]
        template_lbl_name = label_name_for_slot(6)
        if template_lbl_name not in labels:
            print(f"  warning: template label {template_lbl_name} not found, skipping row labels")
            tl_uid, tl_block = None, None
        else:
            tl_uid, tl_block, *_ = labels[template_lbl_name]

        for slot in range(7, 16):
            new_x = NEW_X[slot - 1]
            new_btn_uuid = new_button_uuids[(ri, slot)]
            new_btn_name = btn_name(slot)
            # Clone the slot-6 button, replace name + uuid + frame + osc path.
            blk = replace_node_id(tb_block, new_btn_uuid)
            blk = replace_node_name(blk, new_btn_name)
            blk = replace_frame(blk, new_x, y, W, H)
            # OSC path: change look6 to look<slot>
            if is_gv:
                new_path = f"/composition/groups/1/video/effects/stageflow/effect/look{slot}"
            else:
                new_path = f"/composition/layers/{layer}/video/effects/stageflow/effect/look{slot}"
            blk = replace_osc_path(blk, new_path)
            # Cascade dstIDs (group-video only) — point at the new layer-row uuids.
            if is_gv:
                # The original cascade dstID order was r3, r2, r1, r0
                # (i.e., LAYER 1, LAYER 2, LAYER 3, LAYER 4).
                cascade_targets = [
                    new_button_uuids[(4, slot)],  # ROWS[4] = sf_r3_look (LAYER 1)
                    new_button_uuids[(3, slot)],  # ROWS[3] = sf_r2_look (LAYER 2)
                    new_button_uuids[(2, slot)],  # ROWS[2] = sf_r1_look (LAYER 3)
                    new_button_uuids[(1, slot)],  # ROWS[1] = sf_r0_look (LAYER 4)
                ]
                blk = replace_cascade_dstids(blk, cascade_targets)
            inserts_after_last.append(blk)

            # New label.
            if tl_block:
                new_lbl_uuid = new_label_uuids[(ri, slot)]
                new_lbl_name = label_name_for_slot(slot)
                lblk = replace_node_id(tl_block, new_lbl_uuid)
                lblk = replace_node_name(lblk, new_lbl_name)
                lblk = replace_frame(lblk, new_x, y, W, H)
                new_recv = (
                    f"/composition/video/effects/stageflowbridge/effect/"
                    f"looks/look{slot}name/params/lines"
                )
                lblk = replace_receive_path(lblk, new_recv)
                inserts_after_last.append(lblk)

    # Apply edits in reverse order to keep offsets valid.
    edits.sort(key=lambda t: t[0], reverse=True)
    new_text = text
    for s, e, repl in edits:
        new_text = new_text[:s] + repl + new_text[e:]

    # Append the new node blocks right after the last existing sf_ button
    # location. We re-find a stable anchor: insert AFTER the closing </node>
    # of `sf_logo1_look6_lbl` (the very last stageflow label in pre-edit XML).
    # Actually simpler: insert right before the closing tag of the parent
    # <children> that contains the existing stageflow page. Find that
    # parent by walking up from the last sf_ button block.
    # Heuristic: locate the closing </node> immediately after the highest-
    # offset sf_ button block in NEW_text and inject before next </children>.
    # We tracked last_node_end (pre-edit offset); apply offset adjustments.

    # Simpler approach: find a known sf_ node in new_text and insert
    # nodes right after its closing </node>. They'll be siblings.
    # Use sf_r5_look6 (the last LOGO 1 row button in DOM order before edits).
    # Pick whichever has the highest start offset post-edit. We have all 7 row
    # button6 names; find the one with the largest start in NEW text.
    candidates = [f"{p}{6}" for (p, _, _, _, _) in ROWS]
    insert_anchor_end = -1
    for name in candidates:
        # locate by name in new_text
        m = re.search(
            rf"<node ID='[^']+' type='BUTTON'[^>]*>(?:(?!</node>).)*?CDATA\[{name}\](?:(?!</node>).)*?</node>",
            new_text,
            re.DOTALL,
        )
        if m and m.end() > insert_anchor_end:
            insert_anchor_end = m.end()
    if insert_anchor_end == -1:
        raise SystemExit("no stageflow button found in new_text")
    print(f"inserting {len(inserts_after_last)} new node blocks after offset {insert_anchor_end}")

    final_text = (
        new_text[:insert_anchor_end]
        + "".join(inserts_after_last)
        + new_text[insert_anchor_end:]
    )

    # Sanity checks.
    new_btn_count = len(re.findall(r"CDATA\[sf_r\d+(?:_groupvideo)?_look\d+\]", final_text))
    new_lbl_count = len(re.findall(r"CDATA\[sf_\w+_look\d+_lbl\]", final_text))
    print(f"final sf_ buttons: {new_btn_count} (expected 105)")
    print(f"final sf_ labels: {new_lbl_count} (expected 105)")
    looks_paths = len(re.findall(r"looks/look\d+name/params/lines", final_text))
    print(f"final looks/lookNname/params/lines paths: {looks_paths} (expected 105)")

    # Compress to .tosc.
    xml_bytes = final_text.encode("utf-8")
    tosc_bytes = zlib.compress(xml_bytes)
    OUT_TOSC.write_bytes(tosc_bytes)
    print(f"wrote {OUT_TOSC} ({len(tosc_bytes)} bytes compressed)")


if __name__ == "__main__":
    main()
