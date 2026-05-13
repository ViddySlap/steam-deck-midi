"""Pass 5 step 2: full 6-row COLORS page rewire.

Starts from Ben's tweaked file (after-ben-tweak.tosc, pulled post live-test) so
his manual OSC scaleMax=1 fix and any other edits are preserved.

Changes:
- Resize chaser column buttons w=235 -> w=165
- Resize chaser_picker radio w=235 -> w=165
- Restore chaser_slot9 button color to RED behind the existing box70 overlay
- Resize box70 w=193 -> w=137 (proportional to new button width)
- Add Lua script via correct <property type='s' key='script'> form on chaser_picker
- Delete dormant off-stride box72 / box74 / box75 (their X stride doesn't match
  the new 195px grid)
- Clone 5 more rows at button_x = 491, 686, 881, 1076, 1271
  for slugs videohl, videosh, logohl, logosh, global
- Each new row: 10 BUTTONs (slot0..slot9, slot9 RED) + 1 BOX black overlay on
  slot9 + 1 RADIO with embedded Lua script

In:  notes/2026-05-12-pass5-colors/after-ben-tweak.tosc
Out: notes/2026-05-12-pass5-colors/STEAMDECK V2.full.tosc
"""

import re
import zlib
import uuid
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "after-ben-tweak.tosc"
DST = HERE / "STEAMDECK V2.full.tosc"

# -- channel layout -----------------------------------------------------------

# slug -> button column x position (left edge). Stride 195, button width 165.
CHANNELS = [
    ("chaser",  296),
    ("videohl", 491),
    ("videosh", 686),
    ("logohl",  881),
    ("logosh", 1076),
    ("global", 1271),
]

BTN_W = 165
BTN_H = 126
SLOT_Y = [56, 187, 314, 444, 579, 706, 836, 969, 1098, 1235]

# slot9 black-box overlay geometry (relative to button frame)
OVL_DX, OVL_DY = 14, 21
OVL_W, OVL_H = 137, 88

# per-slot colors. slot9 is RED so the black BOX overlay paints the visible black.
SLOT_COLORS = [
    (1, 0, 0, 1),                # 0 red
    (0.955556, 0.579699, 0, 1),  # 1 orange
    (1, 1, 0, 1),                # 2 yellow
    (0, 1, 0, 1),                # 3 green
    (0, 1, 1, 1),                # 4 cyan
    (0, 0, 1, 1),                # 5 blue
    (0.535088, 0, 1, 1),         # 6 purple
    (1, 0, 1, 1),                # 7 magenta
    (1, 1, 1, 1),                # 8 white
    (1, 0, 0, 1),                # 9 RED (black-box overlay paints over it)
]

# -- helpers ------------------------------------------------------------------

def node_span(data: bytes, anchor_idx: int) -> tuple[int, int]:
    """Given a byte position inside a <node>, return (start, end) of the node."""
    start = data.rfind(b"<node ", 0, anchor_idx)
    depth = 0
    end = None
    for m in re.finditer(rb"<node\s|</node>", data):
        if m.start() < start:
            continue
        if m.group().startswith(b"<node"):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                end = m.end()
                break
    if end is None:
        raise RuntimeError("unbalanced <node>")
    return start, end


def fresh_id() -> str:
    return str(uuid.uuid1())


def lua_script(slug: str) -> str:
    """Radio's onValueChanged fans highlight to <slug>_slot0..<slug>_slot9 buttons."""
    return (
        "function onValueChanged(key)\n"
        '  if key ~= "x" then return end\n'
        "  local idx = math.floor(self.values.x * 9 + 0.5)\n"
        "  for i = 0, 9 do\n"
        f'    local btn = self.parent.children["{slug}_slot" .. i]\n'
        "    if btn ~= nil then\n"
        "      btn.values.x = (i == idx) and 1 or 0\n"
        "    end\n"
        "  end\n"
        "end\n"
    )


def build_button(slug: str, idx: int, x: int, y: int, node_id: str) -> bytes:
    r, g, b, a = SLOT_COLORS[idx]
    name = f"{slug}_slot{idx}"
    xml = (
        f"<node ID='{node_id}' type='BUTTON'>"
        "<properties>"
        "<property type='b'><key><![CDATA[background]]></key><value>1</value></property>"
        "<property type='i'><key><![CDATA[buttonType]]></key><value>2</value></property>"
        f"<property type='c'><key><![CDATA[color]]></key><value><r>{r}</r><g>{g}</g><b>{b}</b><a>{a}</a></value></property>"
        "<property type='f'><key><![CDATA[cornerRadius]]></key><value>10</value></property>"
        f"<property type='r'><key><![CDATA[frame]]></key><value><x>{x}</x><y>{y}</y><w>{BTN_W}</w><h>{BTN_H}</h></value></property>"
        "<property type='b'><key><![CDATA[grabFocus]]></key><value>0</value></property>"
        "<property type='b'><key><![CDATA[interactive]]></key><value>0</value></property>"
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
        "<value><key><![CDATA[x]]></key><locked>0</locked><lockedDefaultCurrent>1</lockedDefaultCurrent><default><![CDATA[0]]></default><defaultPull>0</defaultPull></value>"
        "<value><key><![CDATA[touch]]></key><locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent><default><![CDATA[false]]></default><defaultPull>0</defaultPull></value>"
        "</values>"
        "<messages></messages>"
        "</node>"
    )
    return xml.encode("utf-8")


def build_slot9_overlay(slug: str, btn_x: int, node_id: str) -> bytes:
    """Black BOX painted on top of slot9's RED button. Non-interactive."""
    x = btn_x + OVL_DX
    y = SLOT_Y[9] + OVL_DY
    name = f"{slug}_slot9_blackbox"
    xml = (
        f"<node ID='{node_id}' type='BOX'>"
        "<properties>"
        "<property type='b'><key><![CDATA[background]]></key><value>1</value></property>"
        "<property type='c'><key><![CDATA[color]]></key><value><r>0</r><g>0</g><b>0</b><a>1</a></value></property>"
        "<property type='f'><key><![CDATA[cornerRadius]]></key><value>10</value></property>"
        f"<property type='r'><key><![CDATA[frame]]></key><value><x>{x}</x><y>{y}</y><w>{OVL_W}</w><h>{OVL_H}</h></value></property>"
        "<property type='b'><key><![CDATA[grabFocus]]></key><value>0</value></property>"
        "<property type='b'><key><![CDATA[interactive]]></key><value>0</value></property>"
        "<property type='b'><key><![CDATA[locked]]></key><value>0</value></property>"
        f"<property type='s'><key><![CDATA[name]]></key><value><![CDATA[{name}]]></value></property>"
        "<property type='i'><key><![CDATA[orientation]]></key><value>0</value></property>"
        "<property type='b'><key><![CDATA[outline]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[outlineStyle]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[pointerPriority]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[shape]]></key><value>1</value></property>"
        "<property type='b'><key><![CDATA[visible]]></key><value>1</value></property>"
        "</properties>"
        "<values><value><key><![CDATA[touch]]></key><locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent><default><![CDATA[false]]></default><defaultPull>0</defaultPull></value></values>"
        "<messages></messages>"
        "</node>"
    )
    return xml.encode("utf-8")


def build_radio(slug: str, btn_x: int, node_id: str) -> bytes:
    """Transparent RADIO with Lua highlight script.

    Script lives as <property type='s'> with key=script inside <properties>,
    NOT as a node-level <script> element (verified against tosclib source).
    """
    y_top = SLOT_Y[0]
    h = (SLOT_Y[9] + BTN_H) - y_top
    osc_path = f"/composition/video/effects/colorpalette/effect/channels/{slug}"
    script_text = lua_script(slug)
    xml = (
        f"<node ID='{node_id}' type='RADIO'>"
        "<properties>"
        "<property type='b'><key><![CDATA[background]]></key><value>0</value></property>"
        "<property type='c'><key><![CDATA[color]]></key><value><r>1</r><g>1</g><b>1</b><a>0.25</a></value></property>"
        "<property type='f'><key><![CDATA[cornerRadius]]></key><value>10</value></property>"
        f"<property type='r'><key><![CDATA[frame]]></key><value><x>{btn_x}</x><y>{y_top}</y><w>{BTN_W}</w><h>{h}</h></value></property>"
        "<property type='b'><key><![CDATA[grabFocus]]></key><value>1</value></property>"
        "<property type='b'><key><![CDATA[interactive]]></key><value>1</value></property>"
        "<property type='b'><key><![CDATA[locked]]></key><value>0</value></property>"
        f"<property type='s'><key><![CDATA[name]]></key><value><![CDATA[{slug}_picker]]></value></property>"
        "<property type='i'><key><![CDATA[orientation]]></key><value>2</value></property>"
        "<property type='b'><key><![CDATA[outline]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[outlineStyle]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[pointerPriority]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[radioType]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[shape]]></key><value>1</value></property>"
        "<property type='i'><key><![CDATA[steps]]></key><value>10</value></property>"
        f"<property type='s'><key><![CDATA[script]]></key><value><![CDATA[{script_text}]]></value></property>"
        "<property type='b'><key><![CDATA[visible]]></key><value>1</value></property>"
        "</properties>"
        "<values>"
        "<value><key><![CDATA[x]]></key><locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent><default><![CDATA[0]]></default><defaultPull>0</defaultPull></value>"
        "<value><key><![CDATA[touch]]></key><locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent><default><![CDATA[false]]></default><defaultPull>0</defaultPull></value>"
        "</values>"
        "<messages>"
        "<osc><enabled>1</enabled><send>1</send><receive>1</receive><feedback>0</feedback><noDuplicates>0</noDuplicates><connections>1111111111</connections>"
        "<triggers><trigger><var><![CDATA[x]]></var><condition>ANY</condition></trigger></triggers>"
        f"<path><partial><type>CONSTANT</type><conversion>STRING</conversion><value><![CDATA[{osc_path}]]></value><scaleMin>0</scaleMin><scaleMax>1</scaleMax></partial></path>"
        # scaleMax=1 + INTEGER: TouchOSC sends the normalized 0..1 float to Resolume,
        # Resolume's Int In (max=9) rounds value*9 -> integer 0..9.
        "<arguments><partial><type>VALUE</type><conversion>INTEGER</conversion><value><![CDATA[x]]></value><scaleMin>0</scaleMin><scaleMax>1</scaleMax></partial></arguments>"
        "</osc>"
        "</messages>"
        "</node>"
    )
    return xml.encode("utf-8")


# -- main rewrite -------------------------------------------------------------

def remove_node(data: bytes, name: str) -> bytes:
    """Locate a node by its name property value, return data with that node removed."""
    needle = f"<![CDATA[{name}]]>".encode()
    i = data.find(needle)
    if i < 0:
        raise RuntimeError(f"node named {name!r} not found")
    s, e = node_span(data, i)
    return data[:s] + data[e:]


def resize_chaser_existing(data: bytes) -> bytes:
    """Mutate chaser_slot0..slot9 buttons + chaser_picker + box70 in-place to new geometry."""
    # 1. chaser_slot0..slot9: resize w from 235 -> 165, also restore slot9 color to RED.
    for i in range(10):
        name = f"chaser_slot{i}"
        needle = f"<![CDATA[{name}]]>".encode()
        idx = data.find(needle)
        if idx < 0:
            raise RuntimeError(f"{name} not found")
        s, e = node_span(data, idx)
        old = data[s:e]
        # rewrite frame: w=235 -> w=165
        new = re.sub(
            rb"(\[frame\]\]></key><value><x>296</x><y>\d+</y><w>)235(</w><h>126</h></value>)",
            lambda m: m.group(1) + b"165" + m.group(2),
            old,
        )
        if i == 9:
            # restore slot9 color to RED for the red-button + black-box overlay pattern
            new = re.sub(
                rb"\[color\]\]></key><value><r>[0-9.]+</r><g>[0-9.]+</g><b>[0-9.]+</b><a>[0-9.]+</a></value>",
                b"[color]]></key><value><r>1</r><g>0</g><b>0</b><a>1</a></value>",
                new, count=1,
            )
        if new == old:
            print(f"  WARN: {name} unchanged")
        data = data[:s] + new + data[e:]
    # 2. chaser_picker: w=235 -> 165
    idx = data.find(b"<![CDATA[chaser_picker]]>")
    s, e = node_span(data, idx)
    picker = data[s:e]
    picker_new = re.sub(
        rb"(\[frame\]\]></key><value><x>296</x><y>56</y><w>)235(</w><h>1305</h></value>)",
        lambda m: m.group(1) + b"165" + m.group(2),
        picker,
    )
    if picker_new == picker:
        print("  WARN: chaser_picker frame unchanged")
    data = data[:s] + picker_new + data[e:]

    # 2b. add the script property to chaser_picker (only if not already present)
    if b"[script]]>" not in picker_new:
        script_text = lua_script("chaser")
        script_prop = (
            f"<property type='s'><key><![CDATA[script]]></key><value><![CDATA[{script_text}]]></value></property>"
        ).encode("utf-8")
        # inject just before </properties> in the chaser_picker node
        # re-locate after the previous edit
        idx2 = data.find(b"<![CDATA[chaser_picker]]>")
        s2, e2 = node_span(data, idx2)
        picker2 = data[s2:e2]
        cut = picker2.index(b"</properties>")
        picker2_new = picker2[:cut] + script_prop + picker2[cut:]
        data = data[:s2] + picker2_new + data[e2:]

    # 3. box70 (chaser slot9 black-box overlay): w=193 -> 137, x stays at 316 (which is btn_x+20=296+20=316; but new btn_x for chaser is still 296 with new inset 14 -> box_x=310). Re-anchor to chaser column's new geometry.
    needle = b"<![CDATA[box70]]>"
    idx = data.find(needle)
    s, e = node_span(data, idx)
    box70 = data[s:e]
    # new geometry: x = 296 + OVL_DX, y = 1235 + OVL_DY, w = OVL_W, h = OVL_H
    new_x = 296 + OVL_DX
    new_y = SLOT_Y[9] + OVL_DY
    box70_new = re.sub(
        rb"\[frame\]\]></key><value><x>\d+</x><y>\d+</y><w>\d+</w><h>\d+</h></value>",
        f"[frame]]></key><value><x>{new_x}</x><y>{new_y}</y><w>{OVL_W}</w><h>{OVL_H}</h></value>".encode(),
        box70, count=1,
    )
    if box70_new == box70:
        print("  WARN: box70 frame unchanged")
    data = data[:s] + box70_new + data[e:]
    return data


def append_to_colors_page(data: bytes, new_xml: bytes) -> bytes:
    """Insert new_xml into the COLORS page's <children> just before its closing.

    COLORS page is a GROUP node with name='COLORS'. Walk to its matching </children>.
    """
    # find the COLORS page node
    needle = b"<![CDATA[COLORS]]>"
    idx = data.find(needle)
    s, e = node_span(data, idx)
    page = data[s:e]
    # find the LAST </children> inside the page (the page's own, after all its children)
    # but children of nested groups also have </children>. Use depth tracking on <children>.
    depth = 0
    last_open_idx = None
    pos = 0
    children_close_idx = None
    while pos < len(page):
        next_open = page.find(b"<children>", pos)
        next_close = page.find(b"</children>", pos)
        if next_close == -1:
            break
        if next_open != -1 and next_open < next_close:
            depth += 1
            pos = next_open + len(b"<children>")
        else:
            depth -= 1
            if depth == 0:
                # this </children> closes the page's own <children>
                children_close_idx = next_close
                break
            pos = next_close + len(b"</children>")
    if children_close_idx is None:
        raise RuntimeError("COLORS page </children> not found")
    new_page = page[:children_close_idx] + new_xml + page[children_close_idx:]
    return data[:s] + new_page + data[e:]


def main() -> None:
    raw = SRC.read_bytes()
    data = zlib.decompress(raw)
    print(f"source: {SRC}  raw={len(raw)}  decompressed={len(data)}")

    # 1. remove dormant boxes (off-stride)
    for nm in ("box72", "box74", "box75"):
        data = remove_node(data, nm)
        print(f"  removed dormant {nm}")

    # 2. resize chaser column in place + restore slot9 color + resize box70 + add script
    data = resize_chaser_existing(data)
    print("  chaser column resized + box70 re-anchored + script property added")

    # 3. append 5 new rows (videohl, videosh, logohl, logosh, global)
    for slug, x in CHANNELS[1:]:
        chunks = []
        # 10 buttons
        for i in range(10):
            chunks.append(build_button(slug, i, x, SLOT_Y[i], fresh_id()))
        # slot9 black-box overlay
        chunks.append(build_slot9_overlay(slug, x, fresh_id()))
        # radio with embedded script
        chunks.append(build_radio(slug, x, fresh_id()))
        row_xml = b"".join(chunks)
        data = append_to_colors_page(data, row_xml)
        print(f"  appended row: slug={slug}  x={x}")

    # 4. verify
    print("\nverify markers:")
    must_have = []
    for slug, _ in CHANNELS:
        must_have += [
            f"{slug}_slot0".encode(),
            f"{slug}_slot9".encode(),
            f"{slug}_picker".encode(),
            f"/composition/video/effects/colorpalette/effect/channels/{slug}".encode(),
        ]
    must_have.append(b"onValueChanged")
    must_have.append(b"[script]]>")
    must_have.append(b"box70")
    must_have.append(b"_slot9_blackbox")
    must_not_have = [
        b"box72", b"box74", b"box75",            # dormant removed
        b"chaser red", b"chaser orange",         # old names gone
        b"/composition/layers/8/dashboard/link1",
    ]
    for s in must_have:
        c = data.count(s)
        print(f"  [{'OK' if c > 0 else 'MISSING'}]  expected: {s!r}  count={c}")
    for s in must_not_have:
        c = data.count(s)
        print(f"  [{'OK' if c == 0 else 'STILL PRESENT'}]  removed:  {s!r}  count={c}")

    # 5. recompress + write
    out = zlib.compress(data)
    DST.write_bytes(out)
    print(f"\nwrote: {DST}  bytes: {len(out)}  decompressed: {len(data)}")


if __name__ == "__main__":
    main()
