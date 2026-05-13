"""Pass 5 step 3: clean up COLORS page + left-shift columns + add bottom labels.

- Source: before-cleanup.tosc (pulled fresh from Deck post-Ben-launch)
- Delete every direct child of the COLORS page EXCEPT my 6 picker rows (72 widgets)
- Left-shift every kept widget by 286px so chaser ends up at x=10
- Add 6 TEXT labels at y=1378 below each column for human-readable channel names
"""

import re
import zlib
import uuid
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "before-cleanup.tosc"
DST = HERE / "STEAMDECK V2.cleanup.tosc"

X_SHIFT = -286

CHANNELS = [
    # (slug, label, original_x)
    ("chaser",  "Chaser",    296),
    ("videohl", "Video HL",  491),
    ("videosh", "Video SH",  686),
    ("logohl",  "Logo HL",   881),
    ("logosh",  "Logo SH",  1076),
    ("global",  "All Color", 1271),
]

LABEL_Y = 1378
LABEL_W = 165
LABEL_H = 100


def keep_names() -> set[str]:
    s = set()
    for slug, _label, _ in CHANNELS:
        for i in range(10):
            s.add(f"{slug}_slot{i}")
        s.add(f"{slug}_picker")
        s.add(f"{slug}_slot9_blackbox")
    s.add("box70")  # chaser slot9 overlay (legacy name preserved)
    return s


def node_span_within(blob: bytes, anchor: int) -> tuple[int, int]:
    start = blob.rfind(b"<node ", 0, anchor)
    depth = 0
    end = None
    for m in re.finditer(rb"<node\s|</node>", blob):
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


def enumerate_page_children(page: bytes) -> tuple[int, int, list[dict]]:
    """Returns (children_start, children_end, [child_info]) where child_info has start,end,name,type."""
    depth = 0
    ch_start = None
    ch_end = None
    pos = 0
    while pos < len(page):
        no = page.find(b"<children>", pos)
        nc = page.find(b"</children>", pos)
        if nc == -1:
            break
        if no != -1 and no < nc:
            depth += 1
            if depth == 1:
                ch_start = no + len(b"<children>")
            pos = no + len(b"<children>")
        else:
            depth -= 1
            if depth == 0:
                ch_end = nc
                break
            pos = nc + len(b"</children>")
    if ch_start is None or ch_end is None:
        raise RuntimeError("page <children> block not found")

    children_blob = page[ch_start:ch_end]
    nodes = []
    i = 0
    node_open = re.compile(rb"<node\s+ID='([^']+)'\s+type='([A-Z]+)'")
    while i < len(children_blob):
        nm = node_open.search(children_blob, i)
        if not nm:
            break
        start = nm.start()
        nid = nm.group(1).decode()
        nt = nm.group(2).decode()
        depth = 0
        end = None
        for tm in re.finditer(rb"<node\s|</node>", children_blob[start:]):
            if tm.group().startswith(b"<node"):
                depth += 1
            else:
                depth -= 1
                if depth == 0:
                    end = start + tm.end()
                    break
        if end is None:
            break
        head = children_blob[start:start + 1500]
        nm2 = re.search(rb"\[name\]\]></key><value><!\[CDATA\[([^\]]*)\]\]>", head)
        nodes.append({
            "id": nid,
            "type": nt,
            "name": nm2.group(1).decode() if nm2 else "",
            "start_in_blob": start,
            "end_in_blob": end,
        })
        i = end
    return ch_start, ch_end, nodes


def shift_node_x(node_xml: bytes, dx: int) -> bytes:
    """Shift the node's frame x by dx."""
    def repl(m: re.Match) -> bytes:
        old_x = int(m.group(1))
        return f"[frame]]></key><value><x>{old_x + dx}</x>".encode()

    return re.sub(
        rb"\[frame\]\]></key><value><x>(-?\d+)</x>",
        repl, node_xml, count=1,
    )


def build_label(slug: str, label: str, x: int, node_id: str) -> bytes:
    """White text label, transparent background, non-interactive."""
    return (
        f"<node ID='{node_id}' type='TEXT'>"
        "<properties>"
        "<property type='b'><key><![CDATA[background]]></key><value>0</value></property>"
        "<property type='c'><key><![CDATA[color]]></key><value><r>1</r><g>1</g><b>1</b><a>1</a></value></property>"
        "<property type='f'><key><![CDATA[cornerRadius]]></key><value>0</value></property>"
        f"<property type='r'><key><![CDATA[frame]]></key><value><x>{x}</x><y>{LABEL_Y}</y><w>{LABEL_W}</w><h>{LABEL_H}</h></value></property>"
        "<property type='b'><key><![CDATA[grabFocus]]></key><value>0</value></property>"
        "<property type='b'><key><![CDATA[interactive]]></key><value>0</value></property>"
        "<property type='b'><key><![CDATA[locked]]></key><value>0</value></property>"
        f"<property type='s'><key><![CDATA[name]]></key><value><![CDATA[{slug}_label]]></value></property>"
        "<property type='i'><key><![CDATA[orientation]]></key><value>0</value></property>"
        "<property type='b'><key><![CDATA[outline]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[outlineStyle]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[pointerPriority]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[shape]]></key><value>0</value></property>"
        # text alignment: center horizontal, center vertical
        "<property type='i'><key><![CDATA[textAlignH]]></key><value>1</value></property>"
        "<property type='i'><key><![CDATA[textAlignV]]></key><value>1</value></property>"
        "<property type='c'><key><![CDATA[textColor]]></key><value><r>1</r><g>1</g><b>1</b><a>1</a></value></property>"
        "<property type='i'><key><![CDATA[textSize]]></key><value>32</value></property>"
        "<property type='b'><key><![CDATA[visible]]></key><value>1</value></property>"
        "</properties>"
        "<values>"
        f"<value><key><![CDATA[text]]></key><locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent><default><![CDATA[{label}]]></default><defaultPull>0</defaultPull></value>"
        "<value><key><![CDATA[touch]]></key><locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent><default><![CDATA[false]]></default><defaultPull>0</defaultPull></value>"
        "</values>"
        "<messages></messages>"
        "</node>"
    ).encode("utf-8")


def main() -> None:
    raw = SRC.read_bytes()
    data = zlib.decompress(raw)
    print(f"source: {SRC}  raw={len(raw)}  decompressed={len(data)}")

    KEEP = keep_names()

    # locate COLORS page
    i = data.find(b"<![CDATA[COLORS]]>")
    if i < 0:
        raise RuntimeError("COLORS page not found")
    page_s, page_e = node_span_within(data, i)
    page = data[page_s:page_e]

    ch_s, ch_e, nodes = enumerate_page_children(page)
    print(f"page children count: {len(nodes)}")

    # 1. drop unwanted children; shift kept ones by X_SHIFT
    new_children_chunks = []
    kept = 0
    dropped = 0
    children_blob = page[ch_s:ch_e]
    for n in nodes:
        chunk = children_blob[n["start_in_blob"]:n["end_in_blob"]]
        if n["name"] in KEEP:
            shifted = shift_node_x(chunk, X_SHIFT)
            new_children_chunks.append(shifted)
            kept += 1
        else:
            dropped += 1
    print(f"  kept: {kept}  dropped: {dropped}")

    # 2. add 6 column labels at the bottom
    for slug, label, orig_x in CHANNELS:
        new_x = orig_x + X_SHIFT
        new_children_chunks.append(build_label(slug, label, new_x, str(uuid.uuid1())))
    print(f"  added {len(CHANNELS)} bottom labels")

    new_children = b"".join(new_children_chunks)

    # 3. splice page back together
    new_page = page[:ch_s] + new_children + page[ch_e:]
    new_data = data[:page_s] + new_page + data[page_e:]

    # 4. verify
    print("\nverify markers:")
    must_have = [b"onValueChanged", b"[script]]>"]
    for slug, label, _ in CHANNELS:
        must_have += [
            f"{slug}_picker".encode(),
            f"{slug}_slot0".encode(),
            f"{slug}_slot9_blackbox".encode() if slug != "chaser" else b"box70",
            f"{slug}_label".encode(),
            label.encode(),
            f"/composition/video/effects/colorpalette/effect/channels/{slug}".encode(),
        ]
    must_not_have = [
        b"button379", b"button415", b"button449", b"button647",
        b"box94", b"box95", b"box96", b"box97",
        b"fader69", b"fader92", b"fader93",
        b"text178", b"text286", b"text235",
        b"viddylut",  # all 36 should now be gone (they were in the deleted faders/buttons)
    ]
    ok = True
    for s in must_have:
        c = new_data.count(s)
        flag = "OK" if c > 0 else "MISSING"
        if c == 0: ok = False
        print(f"  [{flag}]  expected: {s!r}  count={c}")
    for s in must_not_have:
        c = new_data.count(s)
        flag = "OK" if c == 0 else "STILL PRESENT"
        if c != 0: ok = False
        print(f"  [{flag}]  removed:  {s!r}  count={c}")

    out = zlib.compress(new_data)
    DST.write_bytes(out)
    print(f"\nwrote: {DST}  bytes: {len(out)}  decompressed: {len(new_data)}")
    if not ok:
        print("WARNING: some checks failed; do not push")


if __name__ == "__main__":
    main()
