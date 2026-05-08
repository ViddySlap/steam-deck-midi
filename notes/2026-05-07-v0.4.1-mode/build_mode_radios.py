"""Replace per-channel RANDOM toggle button with 3 horizontal MODE radio buttons.

Mirrors the BEATS-radio pattern from `notes/2026-05-07-autopilot-tosc/build_beats_radio.py`:
- Each row has 3 mutually-exclusive radio buttons (None / Linear / Random)
- All 3 buttons in a row send to the same OSC path with constant fractional
  values 0.0, 0.5, 1.0 — Resolume's Int In (max=2) snaps to 0/1/2 → ClipMode
- Each button clears the OTHER 2 siblings' x state via local messages on release
- Each button has a stacked TEXT label

Operates on STEAMDECK V2.tosc.current; produces STEAMDECK V2.tosc.new.
"""
from __future__ import annotations

import re
import uuid
import zlib
from pathlib import Path

EFFECT_SLUG = "autopilotenginev1"
CYAN = "<r>0</r><g>1</g><b>1</b><a>1</a>"
MAGENTA = "<r>1</r><g>0</g><b>1</b><a>1</a>"
TRANSPARENT = "<r>0</r><g>0</g><b>0</b><a>0</a>"

MODE_LABELS = ["None", "Linear", "Random"]
MODE_FRACTIONS = [0.0, 0.5, 1.0]
assert len(MODE_LABELS) == len(MODE_FRACTIONS) == 3


def gen_id() -> str:
    return str(uuid.uuid4())


def osc_path(group: str) -> str:
    return f"/composition/video/effects/{EFFECT_SLUG}/effect/{group}/{group}mode"


def radio_button_xml(
    *,
    node_id: str,
    name: str,
    x: int,
    y: int,
    w: int,
    h: int,
    osc_path: str,
    fraction: float,
    sibling_ids: list[str],
) -> str:
    locals_xml = "".join(
        f"<local><enabled>1</enabled>"
        f"<triggers>"
        f"<trigger><var><![CDATA[touch]]></var><condition>ANY</condition></trigger>"
        f"<trigger><var><![CDATA[x]]></var><condition>ANY</condition></trigger>"
        f"</triggers>"
        f"<type>PROPERTY</type><conversion>FLOAT</conversion>"
        f"<value><![CDATA[release]]></value>"
        f"<scaleMin>0</scaleMin><scaleMax>0</scaleMax>"
        f"<dstType>VALUE</dstType><dstVar><![CDATA[x]]></dstVar>"
        f"<dstID><![CDATA[{sib_id}]]></dstID>"
        f"</local>"
        for sib_id in sibling_ids
    )
    return (
        f"<node ID='{node_id}' type='BUTTON'>"
        f"<properties>"
        f"<property type='b'><key><![CDATA[background]]></key><value>1</value></property>"
        f"<property type='i'><key><![CDATA[buttonType]]></key><value>2</value></property>"
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
        f"<value><key><![CDATA[x]]></key><locked>0</locked><lockedDefaultCurrent>1</lockedDefaultCurrent><default><![CDATA[0]]></default><defaultPull>0</defaultPull></value>"
        f"<value><key><![CDATA[touch]]></key><locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent><default><![CDATA[false]]></default><defaultPull>0</defaultPull></value>"
        f"</values>"
        f"<messages>"
        f"<osc><enabled>1</enabled><send>1</send><receive>1</receive><feedback>0</feedback><noDuplicates>0</noDuplicates><connections>1111111111</connections>"
        f"<triggers><trigger><var><![CDATA[x]]></var><condition>ANY</condition></trigger></triggers>"
        f"<path><partial><type>CONSTANT</type><conversion>STRING</conversion><value><![CDATA[{osc_path}]]></value><scaleMin>0</scaleMin><scaleMax>1</scaleMax></partial></path>"
        f"<arguments><partial><type>VALUE</type><conversion>FLOAT</conversion><value><![CDATA[x]]></value><scaleMin>0</scaleMin><scaleMax>{fraction}</scaleMax></partial></arguments>"
        f"</osc>"
        f"{locals_xml}"
        f"</messages>"
        f"</node>"
    )


def label_xml(
    *,
    node_id: str,
    name: str,
    text: str,
    x: int,
    y: int,
    w: int,
    h: int,
    text_size: int = 24,
) -> str:
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


def find_node_by_name(text: str, name: str) -> tuple[int, int]:
    needle = f"<![CDATA[{name}]]>"
    pos = text.find(needle)
    if pos < 0:
        raise SystemExit(f"could not find widget named {name}")
    node_start = text.rfind("<node ", 0, pos)
    node_end = text.find("</node>", pos) + len("</node>")
    if node_start < 0 or node_end < 0:
        raise SystemExit(f"could not bracket node {name}")
    return node_start, node_end


def find_engines_page_close(text: str) -> int:
    tab = text.find("<![CDATA[tabLabel]]></key><value><![CDATA[ENGINES]]>")
    if tab < 0:
        raise SystemExit("ENGINES tab not found")
    children_open = text.find("<children>", tab)
    depth = 1
    cursor = children_open + len("<children>")
    while depth > 0:
        no = text.find("<children>", cursor)
        nc = text.find("</children>", cursor)
        if 0 <= no < nc:
            depth += 1
            cursor = no + len("<children>")
        else:
            depth -= 1
            if depth == 0:
                return nc
            cursor = nc + len("</children>")
    raise SystemExit("did not converge")


def get_frame(text: str, name: str) -> tuple[int, int, int, int]:
    s, e = find_node_by_name(text, name)
    body = text[s:e]
    fr = re.search(
        r"\[CDATA\[frame\]\]></key><value><x>(-?\d+)</x><y>(-?\d+)</y><w>(\d+)</w><h>(\d+)</h>",
        body,
    )
    if not fr:
        raise SystemExit(f"could not parse frame for {name}")
    return int(fr.group(1)), int(fr.group(2)), int(fr.group(3)), int(fr.group(4))


def main() -> None:
    src = Path(__file__).parent / "STEAMDECK V2.tosc.current"
    raw = src.read_bytes()
    print(f"reading {src.name}: {len(raw)} bytes")
    decompressed = zlib.decompress(raw)
    text = decompressed.decode("utf-8")
    print(f"decompressed: {len(text)} chars")

    channels = ["video", "fx", "logo"]

    # 1. Capture frames of existing RANDOM widgets and label IDs to remove.
    frames: dict[str, tuple[int, int, int, int]] = {}
    to_remove_names: list[str] = []
    for ch in channels:
        frames[ch] = get_frame(text, f"ap_{ch}_random")
        to_remove_names.append(f"ap_{ch}_random")
        to_remove_names.append(f"lbl_{ch}_random")
        print(f"  {ch} RANDOM frame: {frames[ch]}")

    # 2. Remove the existing RANDOM button + label nodes (sort desc so offsets stay valid).
    spans = sorted(
        (find_node_by_name(text, name) for name in to_remove_names),
        reverse=True,
    )
    for start, end in spans:
        text = text[:start] + text[end:]
    print(f"removed {len(spans)} widgets; text now {len(text)} chars")

    # 3. Build replacement: 3 horizontal radio buttons + 3 labels per channel.
    new_widgets: list[str] = []
    for ch in channels:
        x_origin, y_origin, total_w, total_h = frames[ch]
        GAP = 2
        BTN_W = (total_w - 2 * GAP) // 3  # 3 buttons + 2 gaps fit in total_w
        button_ids = [gen_id() for _ in range(3)]
        for i, (label, frac, btn_id) in enumerate(
            zip(MODE_LABELS, MODE_FRACTIONS, button_ids)
        ):
            bx = x_origin + i * (BTN_W + GAP)
            siblings = [bid for j, bid in enumerate(button_ids) if j != i]
            new_widgets.append(
                radio_button_xml(
                    node_id=btn_id,
                    name=f"ap_{ch}_mode_{label.lower()}",
                    x=bx,
                    y=y_origin,
                    w=BTN_W,
                    h=total_h,
                    osc_path=osc_path(ch),
                    fraction=frac,
                    sibling_ids=siblings,
                )
            )
            new_widgets.append(
                label_xml(
                    node_id=gen_id(),
                    name=f"lbl_{ch}_mode_{label.lower()}",
                    text=label,
                    x=bx,
                    y=y_origin,
                    w=BTN_W,
                    h=total_h,
                    text_size=24,
                )
            )

    new_xml = "".join(new_widgets)
    print(f"new widgets: {len(new_widgets)} ({len(new_xml)} chars)")

    # 4. Inject before the ENGINES page </children>.
    close_offset = find_engines_page_close(text)
    text = text[:close_offset] + new_xml + text[close_offset:]
    print(f"text after injection: {len(text)} chars")

    # 5. Sanity checks.
    for ch in channels:
        path = osc_path(ch)
        cnt = text.count(path)
        assert cnt == 3, f"{path} appears {cnt} times, expected 3"
    print("verified: each channel's mode path appears exactly 3 times")

    for name in to_remove_names:
        assert text.count(f"<![CDATA[{name}]]>") == 0, f"{name} still in text"
    print("verified: old RANDOM widgets fully removed")

    # 6. Recompress + write .new.
    out = Path(__file__).parent / "STEAMDECK V2.tosc.new"
    out.write_bytes(zlib.compress(text.encode("utf-8")))
    print(f"wrote {out.name}: {out.stat().st_size} bytes")


if __name__ == "__main__":
    main()
