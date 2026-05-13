"""STAGEFLOW BRIDGE TouchOSC patch surgery.

What this script does (one-shot):
  1. Decompress the source .tosc
  2. Shift existing 24 LAYER buttons (rows 0..3) down 200 px so:
     - row 0 (L4) y=150 -> y=350 (row 1)
     - row 1 (L3) y=350 -> y=550 (row 2)
     - row 2 (L2) y=550 -> y=750 (row 3)
     - row 3 (L1) y=750 -> y=950 (row 4)
  3. Swap existing LOGO rows so:
     - existing row 5 (layer 6 / LOGO 1) y=1150 -> y=1350 (now row 6)
     - existing row 6 (layer 7 / LOGO 2) y=1350 -> y=1150 (now row 5)
  4. Recolor LOGO buttons from cyan (0,1,1) to magenta (1,0,1).
  5. Append a NEW row 0 of 6 GROUP VIDEO buttons at y=150, gold (1,0.7,0).
     Each new button sends 5 OSC paths (cascade):
       /composition/groups/1/video/effects/stageflow/effect/lookN
       /composition/layers/{1,2,3,4}/video/effects/stageflow/effect/lookN
  6. Append 42 TEXT LABEL widgets (receive=1, transparent, click-through)
     positioned across the full button frame. Each subscribes to the
     STAGEFLOW BRIDGE Wire patch's matching String In via /params/lines.

Run from this directory:
    py build.py

In:  ../2026-05-12-pre-stageflow-text/STEAMDECK V2.tosc
Out: ./STEAMDECK V2.tosc.new
"""

import re
import uuid
import zlib
from pathlib import Path

HERE = Path(__file__).parent
SRC = Path(r"C:/Users/Ben/Documents/ViddyVault/Projects/steam-deck-midi/notes/2026-05-12-pre-stageflow-text/STEAMDECK V2.tosc")
DST = HERE / "STEAMDECK V2.tosc.new"

# ------------------------------------------------------------------
# Layout constants
# ------------------------------------------------------------------
LOOK_X = [210, 616, 1022, 1428, 1834, 2240]  # x per look 1..6
BTN_W = 396
BTN_H = 180

# After-surgery row y positions
NEW_ROW_Y = {
    "groupvideo": 150,
    "layer4": 350,
    "layer3": 550,
    "layer2": 750,
    "layer1": 950,
    "logo2": 1150,
    "logo1": 1350,
}

# Existing button position migrations
#   "sf_r<N>_look<M>"  ->  new y
#   row 0 (L4) y=150 -> y=350   (no logical change; same x; just shift)
#   row 1 (L3) y=350 -> y=550
#   row 2 (L2) y=550 -> y=750
#   row 3 (L1) y=750 -> y=950
#   row 5 (logo1 / layer 6) y=1150 -> y=1350
#   row 6 (logo2 / layer 7) y=1350 -> y=1150
ROW_SHIFTS = {
    0: 350,   # L4 -> 350
    1: 550,   # L3 -> 550
    2: 750,   # L2 -> 750
    3: 950,   # L1 -> 950
    5: 1350,  # logo1 -> 1350
    6: 1150,  # logo2 -> 1150
}

# Color tuple -> rgb fragment used in <color> elements
GOLD = "<r>1</r><g>0.7</g><b>0</b><a>1</a>"
CYAN = "<r>0</r><g>1</g><b>1</b><a>1</a>"        # unchanged for LAYER rows
MAGENTA = "<r>1</r><g>0</g><b>1</b><a>1</a>"      # new for LOGO rows
WHITE = "<r>1</r><g>1</g><b>1</b><a>1</a>"        # label textColor

# Tag -> recompiled regex finder
def re_b(pat):
    return re.compile(pat.encode())

# A button block uniquely identified by its name -> we'll regex on that.
NAME_TAG = b"<key><![CDATA[name]]></key><value><![CDATA[%s]]></value>"
FRAME_RE_TEMPLATE = (
    rb"(<key><!\[CDATA\[frame\]\]></key><value><x>)(\d+)(</x><y>)"
    rb"(\d+)(</y><w>)(\d+)(</w><h>)(\d+)(</h></value>)"
)
COLOR_RE_TEMPLATE = (
    rb"(<key><!\[CDATA\[color\]\]></key><value>)"
    rb"<r>[^<]+</r><g>[^<]+</g><b>[^<]+</b><a>[^<]+</a>"
    rb"(</value>)"
)


def find_node_span(data: bytes, name_value: str) -> tuple[int, int]:
    """Locate the byte range of <node ...>...</node> that has the given name."""
    needle = NAME_TAG % name_value.encode()
    idx = data.find(needle)
    if idx < 0:
        raise RuntimeError(f"name not found: {name_value!r}")
    start = data.rfind(b"<node ", 0, idx)
    if start < 0:
        raise RuntimeError(f"<node ...> tag not found before name {name_value!r}")
    # Walk forward, balance <node ...> with </node>
    depth = 0
    for m in re.finditer(rb"<node\s|</node>", data[start:]):
        if m.group().startswith(b"<node"):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return start, start + m.end()
    raise RuntimeError("unbalanced <node> for name " + repr(name_value))


def patch_button(data: bytes, name: str, new_y: int, new_color_xml: str | None) -> bytes:
    """Update a button's y position and (optionally) its color block."""
    s, e = find_node_span(data, name)
    block = data[s:e]
    # Replace frame y (use \g<N> to disambiguate from digit-bearing replacement)
    new_block = re.sub(
        FRAME_RE_TEMPLATE,
        rb"\g<1>\g<2>\g<3>" + str(new_y).encode() + rb"\g<5>\g<6>\g<7>\g<8>\g<9>",
        block,
        count=1,
    )
    # Replace color (only first occurrence in block — outer <color>)
    if new_color_xml is not None:
        new_block = re.sub(
            COLOR_RE_TEMPLATE,
            rb"\g<1>" + new_color_xml.encode() + rb"\g<2>",
            new_block,
            count=1,
        )
    if new_block == block:
        raise RuntimeError(f"patch had no effect for {name!r}")
    return data.replace(block, new_block, 1)


# ------------------------------------------------------------------
# New widget templates
# ------------------------------------------------------------------

def make_id() -> str:
    return str(uuid.uuid1())


def new_groupvideo_button(look_n: int, name: str, x: int, y: int) -> bytes:
    """A GROUP VIDEO row button with 5-path cascade.
    Sends to groups/1 + layers/1..4 stageflow look<N>.
    Gold colored. Same dimensions as existing buttons (396x180).
    """
    osc_paths = [
        f"/composition/groups/1/video/effects/stageflow/effect/look{look_n}",
        f"/composition/layers/1/video/effects/stageflow/effect/look{look_n}",
        f"/composition/layers/2/video/effects/stageflow/effect/look{look_n}",
        f"/composition/layers/3/video/effects/stageflow/effect/look{look_n}",
        f"/composition/layers/4/video/effects/stageflow/effect/look{look_n}",
    ]
    osc_blocks = "".join(_one_osc_block_for_button(p) for p in osc_paths)
    xml = (
        f"<node ID='{make_id()}' type='BUTTON'>"
        "<properties>"
        "<property type='b'><key><![CDATA[background]]></key><value>1</value></property>"
        "<property type='i'><key><![CDATA[buttonType]]></key><value>0</value></property>"
        f"<property type='c'><key><![CDATA[color]]></key><value>{GOLD}</value></property>"
        "<property type='f'><key><![CDATA[cornerRadius]]></key><value>10</value></property>"
        f"<property type='r'><key><![CDATA[frame]]></key><value><x>{x}</x><y>{y}</y><w>{BTN_W}</w><h>{BTN_H}</h></value></property>"
        "<property type='b'><key><![CDATA[grabFocus]]></key><value>1</value></property>"
        "<property type='b'><key><![CDATA[interactive]]></key><value>1</value></property>"
        "<property type='b'><key><![CDATA[locked]]></key><value>0</value></property>"
        f"<property type='s'><key><![CDATA[name]]></key><value><![CDATA[{name}]]></value></property>"
        "<property type='i'><key><![CDATA[orientation]]></key><value>0</value></property>"
        "<property type='b'><key><![CDATA[outline]]></key><value>1</value></property>"
        "<property type='i'><key><![CDATA[outlineStyle]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[pointerPriority]]></key><value>0</value></property>"
        "<property type='b'><key><![CDATA[press]]></key><value>1</value></property>"
        "<property type='b'><key><![CDATA[release]]></key><value>1</value></property>"
        "<property type='i'><key><![CDATA[shape]]></key><value>1</value></property>"
        "<property type='b'><key><![CDATA[valuePosition]]></key><value>0</value></property>"
        "<property type='b'><key><![CDATA[visible]]></key><value>1</value></property>"
        "</properties>"
        "<values>"
        "<value><key><![CDATA[x]]></key><locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent><default><![CDATA[0]]></default><defaultPull>0</defaultPull></value>"
        "<value><key><![CDATA[touch]]></key><locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent><default><![CDATA[false]]></default><defaultPull>0</defaultPull></value>"
        "</values>"
        f"<messages>{osc_blocks}</messages>"
        "</node>"
    )
    return xml.encode()


def _one_osc_block_for_button(path: str) -> str:
    """OSC block matching the existing button pattern (var=x, FLOAT)."""
    return (
        "<osc>"
        "<enabled>1</enabled>"
        "<send>1</send>"
        "<receive>0</receive>"
        "<feedback>0</feedback>"
        "<noDuplicates>1</noDuplicates>"
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


def new_label_widget(row_slug: str, look_n: int, name: str, x: int, y: int, text_color_xml: str) -> bytes:
    """Receive-only TEXT widget over a button.
    Subscribes to /composition/video/effects/stageflowbridge/effect/<row_slug>/<row_slug>lookNname/params/lines.
    Transparent background, click-through (interactive=0).
    Full button frame for max readability.
    """
    path = f"/composition/video/effects/stageflowbridge/effect/{row_slug}/{row_slug}look{look_n}name/params/lines"
    xml = (
        f"<node ID='{make_id()}' type='TEXT'>"
        "<properties>"
        "<property type='b'><key><![CDATA[background]]></key><value>0</value></property>"
        f"<property type='c'><key><![CDATA[color]]></key><value>{WHITE}</value></property>"
        "<property type='f'><key><![CDATA[cornerRadius]]></key><value>10</value></property>"
        "<property type='i'><key><![CDATA[font]]></key><value>0</value></property>"
        f"<property type='r'><key><![CDATA[frame]]></key><value><x>{x}</x><y>{y}</y><w>{BTN_W}</w><h>{BTN_H}</h></value></property>"
        "<property type='b'><key><![CDATA[grabFocus]]></key><value>0</value></property>"
        "<property type='b'><key><![CDATA[interactive]]></key><value>0</value></property>"
        "<property type='b'><key><![CDATA[locked]]></key><value>0</value></property>"
        f"<property type='s'><key><![CDATA[name]]></key><value><![CDATA[{name}]]></value></property>"
        "<property type='i'><key><![CDATA[orientation]]></key><value>0</value></property>"
        "<property type='b'><key><![CDATA[outline]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[outlineStyle]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[pointerPriority]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[shape]]></key><value>1</value></property>"
        "<property type='i'><key><![CDATA[textAlignH]]></key><value>2</value></property>"
        "<property type='i'><key><![CDATA[textAlignV]]></key><value>2</value></property>"
        "<property type='b'><key><![CDATA[textClip]]></key><value>1</value></property>"
        f"<property type='c'><key><![CDATA[textColor]]></key><value>{text_color_xml}</value></property>"
        "<property type='i'><key><![CDATA[textSize]]></key><value>32</value></property>"
        "<property type='b'><key><![CDATA[textWrap]]></key><value>1</value></property>"
        "<property type='b'><key><![CDATA[visible]]></key><value>1</value></property>"
        "</properties>"
        "<values>"
        "<value><key><![CDATA[text]]></key><locked>0</locked><lockedDefaultCurrent>1</lockedDefaultCurrent><default><![CDATA[0]]></default><defaultPull>0</defaultPull></value>"
        "<value><key><![CDATA[touch]]></key><locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent><default><![CDATA[false]]></default><defaultPull>0</defaultPull></value>"
        "</values>"
        "<messages><osc>"
        "<enabled>1</enabled><send>0</send><receive>1</receive>"
        "<feedback>0</feedback><noDuplicates>0</noDuplicates>"
        "<connections>1111111111</connections>"
        "<triggers><trigger><var><![CDATA[text]]></var><condition>ANY</condition></trigger></triggers>"
        f"<path><partial><type>CONSTANT</type><conversion>STRING</conversion><value><![CDATA[{path}]]></value><scaleMin>0</scaleMin><scaleMax>1</scaleMax></partial></path>"
        "<arguments><partial><type>VALUE</type><conversion>STRING</conversion><value><![CDATA[text]]></value><scaleMin>0</scaleMin><scaleMax>1</scaleMax></partial></arguments>"
        "</osc></messages>"
        "</node>"
    )
    return xml.encode()


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def delete_node(data: bytes, name: str) -> bytes:
    """Delete a <node>...</node> matching the given name attribute."""
    try:
        s, e = find_node_span(data, name)
    except RuntimeError:
        return data  # already gone
    return data[:s] + data[e:]


def new_row_title_label(name: str, y: int, text: str) -> bytes:
    """Title label at left margin (x=20) for a row."""
    xml = (
        f"<node ID='{make_id()}' type='TEXT'>"
        "<properties>"
        "<property type='b'><key><![CDATA[background]]></key><value>0</value></property>"
        f"<property type='c'><key><![CDATA[color]]></key><value>{WHITE}</value></property>"
        "<property type='f'><key><![CDATA[cornerRadius]]></key><value>10</value></property>"
        "<property type='i'><key><![CDATA[font]]></key><value>0</value></property>"
        f"<property type='r'><key><![CDATA[frame]]></key><value><x>20</x><y>{y}</y><w>180</w><h>180</h></value></property>"
        "<property type='b'><key><![CDATA[grabFocus]]></key><value>0</value></property>"
        "<property type='b'><key><![CDATA[interactive]]></key><value>0</value></property>"
        "<property type='b'><key><![CDATA[locked]]></key><value>0</value></property>"
        f"<property type='s'><key><![CDATA[name]]></key><value><![CDATA[{name}]]></value></property>"
        "<property type='i'><key><![CDATA[orientation]]></key><value>0</value></property>"
        "<property type='b'><key><![CDATA[outline]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[outlineStyle]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[pointerPriority]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[shape]]></key><value>1</value></property>"
        "<property type='i'><key><![CDATA[textAlignH]]></key><value>2</value></property>"
        "<property type='i'><key><![CDATA[textAlignV]]></key><value>2</value></property>"
        "<property type='b'><key><![CDATA[textClip]]></key><value>1</value></property>"
        f"<property type='c'><key><![CDATA[textColor]]></key><value>{WHITE}</value></property>"
        "<property type='i'><key><![CDATA[textSize]]></key><value>32</value></property>"
        "<property type='b'><key><![CDATA[textWrap]]></key><value>1</value></property>"
        "<property type='b'><key><![CDATA[visible]]></key><value>1</value></property>"
        "</properties>"
        "<values>"
        f"<value><key><![CDATA[text]]></key><locked>0</locked><lockedDefaultCurrent>1</lockedDefaultCurrent><default><![CDATA[{text}]]></default><defaultPull>0</defaultPull></value>"
        "<value><key><![CDATA[touch]]></key><locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent><default><![CDATA[false]]></default><defaultPull>0</defaultPull></value>"
        "</values>"
        "<messages></messages>"
        "</node>"
    )
    return xml.encode()


def main():
    print(f"Reading {SRC}")
    raw = SRC.read_bytes()
    data = zlib.decompress(raw)
    print(f"Decompressed: {len(raw):,} -> {len(data):,} bytes")

    # ----- Step 0: DELETE 45 zombie label widgets that conflict with new layout -----
    deletions = []
    for row in (0, 1, 2, 3, 5, 6):
        for look in range(1, 7):
            deletions.append(f"sf_r{row}_look{look}_lbl")
    for row in range(7):
        deletions.append(f"sf_row_{row}_label")
    deletions.append("sf_r4_group_lbl")  # the huge "STAGEFLOW ON GROUP (ALL VIDEO)" label
    deletions.append("sf_r6_look6_lbl")  # rogue "DJ ONLY"

    deleted = 0
    for name in deletions:
        new = delete_node(data, name)
        if new is not data and len(new) != len(data):
            deleted += 1
        data = new
    print(f"Step 0: deleted {deleted} of {len(deletions)} zombie labels")

    # ----- Step 1: shift existing button positions + recolor LOGOs -----
    PATCH_LOG = []
    for row in (0, 1, 2, 3, 5, 6):
        for look in range(1, 7):
            name = f"sf_r{row}_look{look}"
            new_y = ROW_SHIFTS[row]
            new_color = MAGENTA if row in (5, 6) else None  # LOGOs become magenta
            data = patch_button(data, name, new_y, new_color)
            PATCH_LOG.append((name, new_y, "magenta" if new_color else "cyan"))
    print(f"Step 1: patched {len(PATCH_LOG)} existing buttons (positions + LOGO color)")

    # ----- Step 2: build new widgets -----
    new_nodes = []

    # New GROUP VIDEO buttons (row 0)
    for look in range(1, 7):
        x = LOOK_X[look - 1]
        y = NEW_ROW_Y["groupvideo"]
        name = f"sf_r0_groupvideo_look{look}"  # NEW name (sf_r0 was taken by L4 before)
        new_nodes.append(new_groupvideo_button(look, name, x, y))
    print(f"Step 2a: built 6 GROUP VIDEO buttons")

    # 42 label widgets
    # Mapping: TouchOSC final row -> row_slug for stageflowbridge OSC path
    LABEL_TARGETS = [
        ("groupvideo", "groupvideo", NEW_ROW_Y["groupvideo"]),  # new row 0
        ("layer4",     "layer4",     NEW_ROW_Y["layer4"]),       # new row 1
        ("layer3",     "layer3",     NEW_ROW_Y["layer3"]),       # new row 2
        ("layer2",     "layer2",     NEW_ROW_Y["layer2"]),       # new row 3
        ("layer1",     "layer1",     NEW_ROW_Y["layer1"]),       # new row 4
        ("logo2",      "logo2",      NEW_ROW_Y["logo2"]),        # new row 5
        ("logo1",      "logo1",      NEW_ROW_Y["logo1"]),        # new row 6
    ]
    for row_slug, _, y in LABEL_TARGETS:
        for look in range(1, 7):
            x = LOOK_X[look - 1]
            name = f"sf_{row_slug}_look{look}_lbl"
            # Text color: black for readability over saturated colors? use WHITE for now.
            new_nodes.append(new_label_widget(row_slug, look, name, x, y, WHITE))
    print(f"Step 2b: built {len(LABEL_TARGETS) * 6} label widgets")

    # 7 new row title labels at the left margin (x=20)
    ROW_TITLES = [
        ("ALL VIDEO", NEW_ROW_Y["groupvideo"]),
        ("LAYER 4",   NEW_ROW_Y["layer4"]),
        ("LAYER 3",   NEW_ROW_Y["layer3"]),
        ("LAYER 2",   NEW_ROW_Y["layer2"]),
        ("LAYER 1",   NEW_ROW_Y["layer1"]),
        ("LOGO 2",    NEW_ROW_Y["logo2"]),
        ("LOGO 1",    NEW_ROW_Y["logo1"]),
    ]
    for idx, (text, y) in enumerate(ROW_TITLES):
        name = f"sf_row_title_{idx}"
        new_nodes.append(new_row_title_label(name, y, text))
    print(f"Step 2c: built {len(ROW_TITLES)} row title labels")

    # ----- Step 3: insert new widgets right before the closing </node> of the
    # parent that holds the existing sf_r3_look6 (the last button on the
    # bottom-row of the old layout). Use that as the anchor: find sf_r3_look6,
    # find the closing </node> of its parent. -----
    # Simpler: find the END of the LAST existing button (sf_r3_look6 -> at y=750
    # which is the last original row before our edits; we just shifted it to
    # y=950 but the byte order is unchanged so it's still the last by structural
    # position). Insert after its </node>.
    # Even simpler & robust: insert after sf_r6_look6 (which is what was the
    # original BOTTOM-most button at y=1350). That's the natural sibling-tail.
    anchor_name = "sf_r6_look6"
    s, e = find_node_span(data, anchor_name)
    print(f"Step 3: anchor {anchor_name!r} ends at byte {e}, inserting {len(new_nodes)} new nodes")
    insert_blob = b"".join(new_nodes)
    data = data[:e] + insert_blob + data[e:]

    # ----- Step 4: compress + write -----
    out_raw = zlib.compress(data)
    DST.write_bytes(out_raw)
    print(f"Wrote {DST}  ({len(data):,} bytes uncompressed, {len(out_raw):,} compressed)")


if __name__ == "__main__":
    main()
