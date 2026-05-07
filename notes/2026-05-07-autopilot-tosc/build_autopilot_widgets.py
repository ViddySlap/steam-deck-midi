"""Build autopilot widgets + text labels and inject them into the ENGINES page.

Widget set (top-right quadrant of the ENGINES page):
- VIDEO section: ENABLE, RANDOM, BEATS fader, TRANSITION fader, L1-L4 toggles
- FX section: ENABLE, RANDOM, BEATS fader, TRANSITION fader, L5 toggle
- LOGO section: ENABLE, RANDOM, BEATS fader, TRANSITION fader, L6-L7 toggles

19 control widgets + 19 stacked TEXT labels = 38 new widgets total.

Controls are cyan (#00FFFF) buttons / faders. Labels are magenta (#FF00FF)
text on transparent backgrounds, sit on top of controls (interactive=0 so taps
pass through to the underlying control).

OSC paths bind to /composition/video/effects/autopilotenginev1/effect/<group>/<param>.
"""
from __future__ import annotations

import uuid
import zlib
from pathlib import Path

EFFECT_SLUG = "autopilotenginev1"
CYAN = "<r>0</r><g>1</g><b>1</b><a>1</a>"
MAGENTA = "<r>1</r><g>0</g><b>1</b><a>1</a>"
TRANSPARENT = "<r>0</r><g>0</g><b>0</b><a>0</a>"

SECTION_X = 1340
SECTION_W = 600
BTN_W = 290
BTN_H = 110
FADER_H = 110
LAYER_W = 140
LAYER_H = 80
ROW_GAP = 10
SECTION_GAP = 30


def gen_id() -> str:
    return str(uuid.uuid4())


def button_xml(*, node_id: str, name: str, x: int, y: int, w: int, h: int, osc_path: str) -> str:
    return (
        f"<node ID='{node_id}' type='BUTTON'>"
        f"<properties>"
        f"<property type='b'><key><![CDATA[background]]></key><value>1</value></property>"
        f"<property type='i'><key><![CDATA[buttonType]]></key><value>1</value></property>"
        f"<property type='c'><key><![CDATA[color]]></key><value>{CYAN}</value></property>"
        f"<property type='f'><key><![CDATA[cornerRadius]]></key><value>10</value></property>"
        f"<property type='r'><key><![CDATA[frame]]></key><value><x>{x}</x><y>{y}</y><w>{w}</w><h>{h}</h></value></property>"
        f"<property type='b'><key><![CDATA[grabFocus]]></key><value>1</value></property>"
        f"<property type='b'><key><![CDATA[interactive]]></key><value>1</value></property>"
        f"<property type='b'><key><![CDATA[locked]]></key><value>0</value></property>"
        f"<property type='s'><key><![CDATA[name]]></key><value><![CDATA[{name}]]></value></property>"
        f"<property type='i'><key><![CDATA[orientation]]></key><value>0</value></property>"
        f"<property type='b'><key><![CDATA[outline]]></key><value>1</value></property>"
        f"<property type='i'><key><![CDATA[outlineStyle]]></key><value>0</value></property>"
        f"<property type='i'><key><![CDATA[pointerPriority]]></key><value>0</value></property>"
        f"<property type='b'><key><![CDATA[press]]></key><value>1</value></property>"
        f"<property type='b'><key><![CDATA[release]]></key><value>1</value></property>"
        f"<property type='i'><key><![CDATA[shape]]></key><value>1</value></property>"
        f"<property type='b'><key><![CDATA[valuePosition]]></key><value>0</value></property>"
        f"<property type='b'><key><![CDATA[visible]]></key><value>1</value></property>"
        f"</properties>"
        f"<values>"
        f"<value><key><![CDATA[x]]></key><locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent><default><![CDATA[0]]></default><defaultPull>0</defaultPull></value>"
        f"<value><key><![CDATA[touch]]></key><locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent><default><![CDATA[false]]></default><defaultPull>0</defaultPull></value>"
        f"</values>"
        f"<messages>"
        f"<osc><enabled>1</enabled><send>1</send><receive>1</receive><feedback>0</feedback><noDuplicates>0</noDuplicates><connections>1111111111</connections>"
        f"<triggers><trigger><var><![CDATA[x]]></var><condition>ANY</condition></trigger></triggers>"
        f"<path><partial><type>CONSTANT</type><conversion>STRING</conversion><value><![CDATA[{osc_path}]]></value><scaleMin>0</scaleMin><scaleMax>1</scaleMax></partial></path>"
        f"<arguments><partial><type>VALUE</type><conversion>FLOAT</conversion><value><![CDATA[x]]></value><scaleMin>0</scaleMin><scaleMax>1</scaleMax></partial></arguments>"
        f"</osc>"
        f"</messages>"
        f"</node>"
    )


def fader_xml(*, node_id: str, name: str, x: int, y: int, w: int, h: int, osc_path: str, grid_steps: int = 11) -> str:
    return (
        f"<node ID='{node_id}' type='FADER'>"
        f"<properties>"
        f"<property type='b'><key><![CDATA[background]]></key><value>1</value></property>"
        f"<property type='b'><key><![CDATA[bar]]></key><value>1</value></property>"
        f"<property type='i'><key><![CDATA[barDisplay]]></key><value>0</value></property>"
        f"<property type='c'><key><![CDATA[color]]></key><value>{CYAN}</value></property>"
        f"<property type='f'><key><![CDATA[cornerRadius]]></key><value>10</value></property>"
        f"<property type='b'><key><![CDATA[cursor]]></key><value>1</value></property>"
        f"<property type='i'><key><![CDATA[cursorDisplay]]></key><value>0</value></property>"
        f"<property type='r'><key><![CDATA[frame]]></key><value><x>{x}</x><y>{y}</y><w>{w}</w><h>{h}</h></value></property>"
        f"<property type='b'><key><![CDATA[grabFocus]]></key><value>1</value></property>"
        f"<property type='b'><key><![CDATA[grid]]></key><value>1</value></property>"
        f"<property type='c'><key><![CDATA[gridColor]]></key><value><r>0</r><g>0</g><b>0</b><a>0.25</a></value></property>"
        f"<property type='i'><key><![CDATA[gridSteps]]></key><value>{grid_steps}</value></property>"
        f"<property type='b'><key><![CDATA[interactive]]></key><value>1</value></property>"
        f"<property type='b'><key><![CDATA[locked]]></key><value>0</value></property>"
        f"<property type='s'><key><![CDATA[name]]></key><value><![CDATA[{name}]]></value></property>"
        f"<property type='i'><key><![CDATA[orientation]]></key><value>1</value></property>"
        f"<property type='b'><key><![CDATA[outline]]></key><value>1</value></property>"
        f"<property type='i'><key><![CDATA[outlineStyle]]></key><value>1</value></property>"
        f"<property type='i'><key><![CDATA[pointerPriority]]></key><value>0</value></property>"
        f"<property type='i'><key><![CDATA[response]]></key><value>0</value></property>"
        f"<property type='i'><key><![CDATA[responseFactor]]></key><value>100</value></property>"
        f"<property type='i'><key><![CDATA[shape]]></key><value>1</value></property>"
        f"<property type='b'><key><![CDATA[visible]]></key><value>1</value></property>"
        f"</properties>"
        f"<values>"
        f"<value><key><![CDATA[x]]></key><locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent><default><![CDATA[0]]></default><defaultPull>0</defaultPull></value>"
        f"<value><key><![CDATA[touch]]></key><locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent><default><![CDATA[false]]></default><defaultPull>0</defaultPull></value>"
        f"</values>"
        f"<messages>"
        f"<osc><enabled>1</enabled><send>1</send><receive>1</receive><feedback>0</feedback><noDuplicates>0</noDuplicates><connections>1111111111</connections>"
        f"<triggers><trigger><var><![CDATA[x]]></var><condition>ANY</condition></trigger></triggers>"
        f"<path><partial><type>CONSTANT</type><conversion>STRING</conversion><value><![CDATA[{osc_path}]]></value><scaleMin>0</scaleMin><scaleMax>1</scaleMax></partial></path>"
        f"<arguments><partial><type>VALUE</type><conversion>FLOAT</conversion><value><![CDATA[x]]></value><scaleMin>0</scaleMin><scaleMax>1</scaleMax></partial></arguments>"
        f"</osc>"
        f"</messages>"
        f"</node>"
    )


def label_xml(*, node_id: str, name: str, text: str, x: int, y: int, w: int, h: int, text_size: int = 28) -> str:
    return (
        f"<node ID='{node_id}' type='TEXT'>"
        f"<properties>"
        f"<property type='b'><key><![CDATA[background]]></key><value>0</value></property>"
        f"<property type='c'><key><![CDATA[color]]></key><value>{TRANSPARENT}</value></property>"
        f"<property type='f'><key><![CDATA[cornerRadius]]></key><value>10</value></property>"
        f"<property type='i'><key><![CDATA[font]]></key><value>0</value></property>"
        f"<property type='r'><key><![CDATA[frame]]></key><value><x>{x}</x><y>{y}</y><w>{w}</w><h>{h}</h></value></property>"
        f"<property type='b'><key><![CDATA[grabFocus]]></key><value>0</value></property>"
        f"<property type='b'><key><![CDATA[interactive]]></key><value>0</value></property>"
        f"<property type='b'><key><![CDATA[locked]]></key><value>0</value></property>"
        f"<property type='s'><key><![CDATA[name]]></key><value><![CDATA[{name}]]></value></property>"
        f"<property type='i'><key><![CDATA[orientation]]></key><value>0</value></property>"
        f"<property type='b'><key><![CDATA[outline]]></key><value>0</value></property>"
        f"<property type='i'><key><![CDATA[outlineStyle]]></key><value>0</value></property>"
        f"<property type='i'><key><![CDATA[pointerPriority]]></key><value>0</value></property>"
        f"<property type='i'><key><![CDATA[shape]]></key><value>1</value></property>"
        f"<property type='i'><key><![CDATA[textAlignH]]></key><value>2</value></property>"
        f"<property type='i'><key><![CDATA[textAlignV]]></key><value>2</value></property>"
        f"<property type='b'><key><![CDATA[textClip]]></key><value>1</value></property>"
        f"<property type='c'><key><![CDATA[textColor]]></key><value>{MAGENTA}</value></property>"
        f"<property type='i'><key><![CDATA[textSize]]></key><value>{text_size}</value></property>"
        f"<property type='b'><key><![CDATA[textWrap]]></key><value>1</value></property>"
        f"<property type='b'><key><![CDATA[visible]]></key><value>1</value></property>"
        f"</properties>"
        f"<values>"
        f"<value><key><![CDATA[text]]></key><locked>0</locked><lockedDefaultCurrent>1</lockedDefaultCurrent><default><![CDATA[{text}]]></default><defaultPull>0</defaultPull></value>"
        f"<value><key><![CDATA[touch]]></key><locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent><default><![CDATA[false]]></default><defaultPull>0</defaultPull></value>"
        f"</values>"
        f"</node>"
    )


def osc(group: str, param: str) -> str:
    return f"/composition/video/effects/{EFFECT_SLUG}/effect/{group}/{param}"


def build_section(group: str, base_y: int, layer_indices: list[int]) -> tuple[str, int]:
    """Build one channel's widgets + labels. Controls first, then labels stacked on top."""
    controls: list[str] = []
    labels: list[str] = []
    label_upper = group.upper()
    y = base_y

    # Row 1: ENABLE + RANDOM toggles (side-by-side)
    enable_x = SECTION_X
    random_x = SECTION_X + BTN_W + 20
    controls.append(button_xml(
        node_id=gen_id(), name=f"ap_{group}_enable",
        x=enable_x, y=y, w=BTN_W, h=BTN_H,
        osc_path=osc(group, f"{group}enable"),
    ))
    labels.append(label_xml(
        node_id=gen_id(), name=f"lbl_{group}_enable",
        text=f"{label_upper} ENABLE",
        x=enable_x, y=y, w=BTN_W, h=BTN_H, text_size=32,
    ))
    controls.append(button_xml(
        node_id=gen_id(), name=f"ap_{group}_random",
        x=random_x, y=y, w=BTN_W, h=BTN_H,
        osc_path=osc(group, f"{group}random"),
    ))
    labels.append(label_xml(
        node_id=gen_id(), name=f"lbl_{group}_random",
        text=f"{label_upper} RANDOM",
        x=random_x, y=y, w=BTN_W, h=BTN_H, text_size=32,
    ))
    y += BTN_H + ROW_GAP

    # Row 2: BEATS fader (7-step grid)
    controls.append(fader_xml(
        node_id=gen_id(), name=f"ap_{group}_beats",
        x=SECTION_X, y=y, w=SECTION_W, h=FADER_H,
        osc_path=osc(group, f"{group}beats"), grid_steps=7,
    ))
    labels.append(label_xml(
        node_id=gen_id(), name=f"lbl_{group}_beats",
        text=f"{label_upper} BEATS  1 / 4 / 8 / 16 / 32 / 64 / 128",
        x=SECTION_X, y=y, w=SECTION_W, h=FADER_H, text_size=28,
    ))
    y += FADER_H + ROW_GAP

    # Row 3: TRANSITION fader
    controls.append(fader_xml(
        node_id=gen_id(), name=f"ap_{group}_transition",
        x=SECTION_X, y=y, w=SECTION_W, h=FADER_H,
        osc_path=osc(group, f"{group}transition"), grid_steps=11,
    ))
    labels.append(label_xml(
        node_id=gen_id(), name=f"lbl_{group}_transition",
        text=f"{label_upper} TRANSITION  0 - 5 sec",
        x=SECTION_X, y=y, w=SECTION_W, h=FADER_H, text_size=28,
    ))
    y += FADER_H + ROW_GAP

    # Row 4: per-layer toggles
    if layer_indices:
        for i, layer in enumerate(layer_indices):
            lx = SECTION_X + i * (LAYER_W + 10)
            controls.append(button_xml(
                node_id=gen_id(), name=f"ap_{group}_l{layer}",
                x=lx, y=y, w=LAYER_W, h=LAYER_H,
                osc_path=osc(group, f"{group}l{layer}"),
            ))
            labels.append(label_xml(
                node_id=gen_id(), name=f"lbl_{group}_l{layer}",
                text=f"L{layer}",
                x=lx, y=y, w=LAYER_W, h=LAYER_H, text_size=36,
            ))
        y += LAYER_H + ROW_GAP

    # Controls first so labels render on top.
    return "".join(controls + labels), y - base_y


def find_engines_page_close(decompressed: bytes) -> int:
    tab_marker = b"<![CDATA[tabLabel]]></key><value><![CDATA[ENGINES]]>"
    pos = decompressed.find(tab_marker)
    if pos < 0:
        raise SystemExit("ENGINES tab not found")
    children_open = decompressed.find(b"<children>", pos)
    if children_open < 0:
        raise SystemExit("could not find <children> open for ENGINES page")
    depth = 1
    cursor = children_open + len(b"<children>")
    while depth > 0:
        next_open = decompressed.find(b"<children>", cursor)
        next_close = decompressed.find(b"</children>", cursor)
        if next_close < 0:
            raise SystemExit("unbalanced <children> tags inside ENGINES page")
        if 0 <= next_open < next_close:
            depth += 1
            cursor = next_open + len(b"<children>")
        else:
            depth -= 1
            if depth == 0:
                return next_close
            cursor = next_close + len(b"</children>")
    raise SystemExit("did not converge")


def main() -> None:
    src = Path("STEAMDECK V2.tosc.bak")
    raw = src.read_bytes()
    print(f"reading {src}: {len(raw)} bytes")
    decompressed = zlib.decompress(raw)
    print(f"decompressed: {len(decompressed)} bytes")

    sections: list[str] = []
    y = 20
    for group, layers in (("video", [1, 2, 3, 4]), ("fx", [5]), ("logo", [6, 7])):
        section_xml, height = build_section(group, y, layers)
        sections.append(section_xml)
        y += height + SECTION_GAP

    autopilot_xml = "".join(sections).encode("utf-8")
    print(f"generated autopilot XML: {len(autopilot_xml)} bytes (controls + labels), footprint y=20..{y}")

    close_offset = find_engines_page_close(decompressed)
    print(f"injecting before ENGINES </children> at offset {close_offset}")

    new_decompressed = decompressed[:close_offset] + autopilot_xml + decompressed[close_offset:]
    print(f"new decompressed: {len(new_decompressed)} bytes (delta +{len(autopilot_xml)})")

    expected_paths: list[str] = []
    for group, layers in (("video", [1, 2, 3, 4]), ("fx", [5]), ("logo", [6, 7])):
        for suffix in ("enable", "beats", "transition", "random"):
            expected_paths.append(osc(group, f"{group}{suffix}"))
        for layer in layers:
            expected_paths.append(osc(group, f"{group}l{layer}"))
    assert len(expected_paths) == 19
    for path in expected_paths:
        assert new_decompressed.count(path.encode()) == 1, f"unexpected count for {path}"
    expected_labels = [
        b"VIDEO ENABLE", b"VIDEO RANDOM", b"VIDEO BEATS  1 / 4",
        b"FX ENABLE", b"FX RANDOM", b"FX TRANSITION  0 - 5 sec",
        b"LOGO ENABLE", b"LOGO RANDOM",
    ]
    for lbl in expected_labels:
        assert new_decompressed.count(lbl) >= 1, f"missing label {lbl}"
    print(f"verified: 19 OSC paths + sample labels present")

    new_compressed = zlib.compress(new_decompressed)
    out = Path("STEAMDECK V2.tosc.new")
    out.write_bytes(new_compressed)
    print(f"wrote {out}: {len(new_compressed)} bytes")


if __name__ == "__main__":
    main()
