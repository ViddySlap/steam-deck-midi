"""Replace BEATS faders with 7-button radio rows on the autopilot ENGINES section.

Mirrors the COLORS-page pattern:
- Each row has 7 mutually-exclusive radio buttons (1/4/8/16/32/64/128)
- All 7 buttons in a row send to the SAME OSC path with constant fractional
  values: 0.0, 1/6, 2/6, 3/6, 4/6, 5/6, 1.0 (centers of 7 bands across 0-1)
- Resolume's Int In with max=6 snaps each fractional to int 0-6
- Each button clears the OTHER 6 siblings' x state via local messages
- Each button has a stacked TEXT label showing the beat count

Operates on the live .tosc rearrangement Ben pushed; reads .tosc.current,
removes the existing BEATS faders + labels by name, injects the new buttons.
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

BEAT_VALUES = [1, 4, 8, 16, 32, 64, 128]
# Float values 0-1 that map to ints 0-6 via Resolume's options-count snap.
BEAT_FRACTIONS = [round(i / 6, 6) for i in range(7)]
assert len(BEAT_VALUES) == len(BEAT_FRACTIONS) == 7


def gen_id() -> str:
    return str(uuid.uuid4())


def osc_path(group: str) -> str:
    return f"/composition/video/effects/{EFFECT_SLUG}/effect/{group}/{group}beats"


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
    # Source = release. Per Ben's COLORS-page comparison: each local clears one
    # sibling's x to 0 when this button releases (i.e. after the user finishes
    # tapping). Using release instead of press avoids re-firing OSC bindings
    # on the cleared siblings during the press phase.
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
    text_size: int = 32,
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
    """Locate <node>...<name>NAME</name>...</node> span by name. Returns (start, end_after_close)."""
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
    """Return (x, y, w, h) of an existing widget by its name."""
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
    src = Path("STEAMDECK V2.tosc.current")
    raw = src.read_bytes()
    print(f"reading {src}: {len(raw)} bytes")
    decompressed = zlib.decompress(raw)
    text = decompressed.decode("utf-8")
    print(f"decompressed: {len(text)} chars")

    # 1. Capture frames of existing BEATS widgets, plus the IDs of widgets we'll remove.
    channels = ["video", "fx", "logo"]
    frames: dict[str, tuple[int, int, int, int]] = {}
    to_remove_names = []
    for ch in channels:
        frames[ch] = get_frame(text, f"ap_{ch}_beats")
        to_remove_names.append(f"ap_{ch}_beats")
        to_remove_names.append(f"lbl_{ch}_beats")
        print(f"  {ch} BEATS frame: {frames[ch]}")

    # 2. Remove the existing BEATS fader + label nodes.
    # Sort by position descending so removals don't shift later offsets.
    spans = sorted(
        (find_node_by_name(text, name) for name in to_remove_names),
        reverse=True,
    )
    for start, end in spans:
        text = text[:start] + text[end:]
    print(f"removed {len(spans)} widgets; text now {len(text)} chars")

    # 3. Build replacement: 7 radio buttons + 7 labels per channel.
    #    Pre-allocate IDs so each button can reference its 6 siblings.
    new_widgets: list[str] = []
    for ch in channels:
        x_origin, y_origin, total_w, total_h = frames[ch]
        BTN_W = 84
        GAP = 2
        button_ids = [gen_id() for _ in range(7)]
        for i, (val, frac, btn_id) in enumerate(
            zip(BEAT_VALUES, BEAT_FRACTIONS, button_ids)
        ):
            bx = x_origin + i * (BTN_W + GAP)
            siblings = [bid for j, bid in enumerate(button_ids) if j != i]
            new_widgets.append(
                radio_button_xml(
                    node_id=btn_id,
                    name=f"ap_{ch}_beats_{val}",
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
                    name=f"lbl_{ch}_beats_{val}",
                    text=str(val),
                    x=bx,
                    y=y_origin,
                    w=BTN_W,
                    h=total_h,
                    text_size=28,
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
        # Each path should appear 7 times now (one per button).
        cnt = text.count(path)
        assert cnt == 7, f"{path} appears {cnt} times, expected 7"
    print("verified: each channel's beats path appears exactly 7 times")

    # No leftover BEATS faders.
    for name in to_remove_names:
        assert text.count(f"<![CDATA[{name}]]>") == 0, f"{name} still in text"
    print("verified: old BEATS fader + label widgets fully removed")

    # 6. Recompress + write .new.
    new_decompressed = text.encode("utf-8")
    new_compressed = zlib.compress(new_decompressed)
    out = Path("STEAMDECK V2.tosc.new")
    out.write_bytes(new_compressed)
    print(f"wrote {out}: {len(new_compressed)} bytes")


if __name__ == "__main__":
    main()
