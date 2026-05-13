"""Pass 5 step 5: add Resync momentary button + Fade Time fader to the COLORS page.

Starts from `post-ben-polish.tosc` (just pulled from Deck after Ben's visual
restructuring). Preserves all existing widgets and their positions/frames.

Adds 4 new widgets in the empty right region (x > 1283):
- Resync momentary BUTTON + label overlay
- Fade Time horizontal FADER + label

Resync OSC target: /composition/video/effects/colorpalette/effect/control/resync
  (confirmed in 2026-05-12 wiki log; Trigger In on COLOR PALETTE Wire patch's
   CONTROL dashboard group)

Fade Time OSC target: /composition/video/effects/colorpalette/effect/control/fadetime
  (assumed slug — Wire Float In named "Fade Time"; auto-slug lowercases +
   removes spaces. If wrong, fader will appear but bridge fade_seconds won't
   change; we'll inspect and fix.)
"""

import re
import zlib
import uuid
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "post-ben-polish.tosc"
DST = HERE / "STEAMDECK V2.controls.tosc"

# placements in the right empty region (page is 2676 x 1600; columns end at x=1283)
RESYNC = dict(x=1400, y=200, w=400, h=300)
RESYNC_LBL = dict(x=1400, y=200, w=400, h=300)        # full overlay on button
FADE_LBL = dict(x=1400, y=600, w=900, h=80)
FADE = dict(x=1400, y=700, w=900, h=180)

RESYNC_OSC = "/composition/video/effects/colorpalette/effect/control/resync"
FADETIME_OSC = "/composition/video/effects/colorpalette/effect/control/fadetime"


def node_span(data: bytes, anchor_idx: int) -> tuple[int, int]:
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


def build_resync_button(node_id: str) -> bytes:
    """Big momentary button; OSC trigger is RISE-only so a tap fires exactly once."""
    f = RESYNC
    return (
        f"<node ID='{node_id}' type='BUTTON'>"
        "<properties>"
        "<property type='b'><key><![CDATA[background]]></key><value>1</value></property>"
        # buttonType=0 = Momentary: x = 1 while pressed, 0 on release
        "<property type='i'><key><![CDATA[buttonType]]></key><value>0</value></property>"
        # cyan, distinct from any color slot
        "<property type='c'><key><![CDATA[color]]></key><value><r>0</r><g>0.8</g><b>1</b><a>1</a></value></property>"
        "<property type='f'><key><![CDATA[cornerRadius]]></key><value>20</value></property>"
        f"<property type='r'><key><![CDATA[frame]]></key><value><x>{f['x']}</x><y>{f['y']}</y><w>{f['w']}</w><h>{f['h']}</h></value></property>"
        "<property type='b'><key><![CDATA[grabFocus]]></key><value>1</value></property>"
        "<property type='b'><key><![CDATA[interactive]]></key><value>1</value></property>"
        "<property type='b'><key><![CDATA[locked]]></key><value>0</value></property>"
        "<property type='s'><key><![CDATA[name]]></key><value><![CDATA[resync_button]]></value></property>"
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
        "<messages>"
        # OSC trigger condition RISE = fires once per tap (press only, no release double-fire)
        "<osc><enabled>1</enabled><send>1</send><receive>0</receive><feedback>0</feedback><noDuplicates>0</noDuplicates><connections>1111111111</connections>"
        "<triggers><trigger><var><![CDATA[x]]></var><condition>RISE</condition></trigger></triggers>"
        f"<path><partial><type>CONSTANT</type><conversion>STRING</conversion><value><![CDATA[{RESYNC_OSC}]]></value><scaleMin>0</scaleMin><scaleMax>1</scaleMax></partial></path>"
        "<arguments><partial><type>VALUE</type><conversion>FLOAT</conversion><value><![CDATA[x]]></value><scaleMin>0</scaleMin><scaleMax>1</scaleMax></partial></arguments>"
        "</osc>"
        "</messages>"
        "</node>"
    ).encode("utf-8")


def build_text(name: str, text: str, frame: dict, size: int, node_id: str, interactive: int = 0) -> bytes:
    f = frame
    return (
        f"<node ID='{node_id}' type='TEXT'>"
        "<properties>"
        "<property type='b'><key><![CDATA[background]]></key><value>0</value></property>"
        "<property type='c'><key><![CDATA[color]]></key><value><r>1</r><g>1</g><b>1</b><a>0</a></value></property>"
        "<property type='f'><key><![CDATA[cornerRadius]]></key><value>0</value></property>"
        f"<property type='r'><key><![CDATA[frame]]></key><value><x>{f['x']}</x><y>{f['y']}</y><w>{f['w']}</w><h>{f['h']}</h></value></property>"
        "<property type='b'><key><![CDATA[grabFocus]]></key><value>0</value></property>"
        f"<property type='b'><key><![CDATA[interactive]]></key><value>{interactive}</value></property>"
        "<property type='b'><key><![CDATA[locked]]></key><value>0</value></property>"
        f"<property type='s'><key><![CDATA[name]]></key><value><![CDATA[{name}]]></value></property>"
        "<property type='i'><key><![CDATA[orientation]]></key><value>0</value></property>"
        "<property type='b'><key><![CDATA[outline]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[outlineStyle]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[pointerPriority]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[shape]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[textAlignH]]></key><value>1</value></property>"
        "<property type='i'><key><![CDATA[textAlignV]]></key><value>1</value></property>"
        "<property type='c'><key><![CDATA[textColor]]></key><value><r>1</r><g>1</g><b>1</b><a>1</a></value></property>"
        f"<property type='i'><key><![CDATA[textSize]]></key><value>{size}</value></property>"
        "<property type='b'><key><![CDATA[visible]]></key><value>1</value></property>"
        "</properties>"
        "<values>"
        f"<value><key><![CDATA[text]]></key><locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent><default><![CDATA[{text}]]></default><defaultPull>0</defaultPull></value>"
        "<value><key><![CDATA[touch]]></key><locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent><default><![CDATA[false]]></default><defaultPull>0</defaultPull></value>"
        "</values>"
        "<messages></messages>"
        "</node>"
    ).encode("utf-8")


def build_fader(node_id: str) -> bytes:
    """Horizontal fader; x value 0..1 sent as FLOAT to fadetime OSC path."""
    f = FADE
    return (
        f"<node ID='{node_id}' type='FADER'>"
        "<properties>"
        "<property type='b'><key><![CDATA[background]]></key><value>1</value></property>"
        # dark grey track, value indicator paints in textColor
        "<property type='c'><key><![CDATA[color]]></key><value><r>0.3</r><g>0.3</g><b>0.3</b><a>1</a></value></property>"
        "<property type='f'><key><![CDATA[cornerRadius]]></key><value>10</value></property>"
        f"<property type='r'><key><![CDATA[frame]]></key><value><x>{f['x']}</x><y>{f['y']}</y><w>{f['w']}</w><h>{f['h']}</h></value></property>"
        "<property type='b'><key><![CDATA[grabFocus]]></key><value>1</value></property>"
        "<property type='b'><key><![CDATA[interactive]]></key><value>1</value></property>"
        "<property type='b'><key><![CDATA[locked]]></key><value>0</value></property>"
        "<property type='s'><key><![CDATA[name]]></key><value><![CDATA[fadetime_fader]]></value></property>"
        # orientation=1 = horizontal
        "<property type='i'><key><![CDATA[orientation]]></key><value>1</value></property>"
        "<property type='b'><key><![CDATA[outline]]></key><value>1</value></property>"
        "<property type='i'><key><![CDATA[outlineStyle]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[pointerPriority]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[response]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[shape]]></key><value>1</value></property>"
        # 0.2 default = 1.0s on a 0..5s scale (matches bridge default fade_seconds=1.0)
        "<property type='b'><key><![CDATA[visible]]></key><value>1</value></property>"
        "</properties>"
        "<values>"
        "<value><key><![CDATA[x]]></key><locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent><default><![CDATA[0.2]]></default><defaultPull>0</defaultPull></value>"
        "<value><key><![CDATA[touch]]></key><locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent><default><![CDATA[false]]></default><defaultPull>0</defaultPull></value>"
        "</values>"
        "<messages>"
        "<osc><enabled>1</enabled><send>1</send><receive>1</receive><feedback>0</feedback><noDuplicates>0</noDuplicates><connections>1111111111</connections>"
        "<triggers><trigger><var><![CDATA[x]]></var><condition>ANY</condition></trigger></triggers>"
        f"<path><partial><type>CONSTANT</type><conversion>STRING</conversion><value><![CDATA[{FADETIME_OSC}]]></value><scaleMin>0</scaleMin><scaleMax>1</scaleMax></partial></path>"
        "<arguments><partial><type>VALUE</type><conversion>FLOAT</conversion><value><![CDATA[x]]></value><scaleMin>0</scaleMin><scaleMax>1</scaleMax></partial></arguments>"
        "</osc>"
        "</messages>"
        "</node>"
    ).encode("utf-8")


def append_to_colors_page(data: bytes, new_xml: bytes) -> bytes:
    i = data.find(b"<![CDATA[COLORS]]>")
    s, e = node_span(data, i)
    page = data[s:e]
    depth = 0
    pos = 0
    ch_close = None
    while pos < len(page):
        no = page.find(b"<children>", pos)
        nc = page.find(b"</children>", pos)
        if nc == -1:
            break
        if no != -1 and no < nc:
            depth += 1
            pos = no + len(b"<children>")
        else:
            depth -= 1
            if depth == 0:
                ch_close = nc
                break
            pos = nc + len(b"</children>")
    if ch_close is None:
        raise RuntimeError("COLORS </children> not found")
    new_page = page[:ch_close] + new_xml + page[ch_close:]
    return data[:s] + new_page + data[e:]


def main() -> None:
    raw = SRC.read_bytes()
    data = zlib.decompress(raw)
    print(f"source: {SRC}  raw={len(raw)}  decompressed={len(data)}")

    chunks = [
        build_resync_button(str(uuid.uuid1())),
        build_text("resync_label", "Resync", RESYNC_LBL, size=64, node_id=str(uuid.uuid1())),
        build_text("fadetime_label", "Fade Time", FADE_LBL, size=48, node_id=str(uuid.uuid1())),
        build_fader(str(uuid.uuid1())),
    ]
    data = append_to_colors_page(data, b"".join(chunks))
    print("  appended: resync_button, resync_label, fadetime_label, fadetime_fader")

    # verify
    must_have = [
        b"resync_button", b"resync_label", b"Resync",
        b"fadetime_fader", b"fadetime_label", b"Fade Time",
        RESYNC_OSC.encode(), FADETIME_OSC.encode(),
    ]
    print("\nverify:")
    for x in must_have:
        c = data.count(x)
        print(f"  [{'OK' if c > 0 else 'MISSING'}]  {x!r}  count={c}")

    out = zlib.compress(data)
    DST.write_bytes(out)
    print(f"\nwrote: {DST}  bytes: {len(out)}  decompressed: {len(data)}")


if __name__ == "__main__":
    main()
