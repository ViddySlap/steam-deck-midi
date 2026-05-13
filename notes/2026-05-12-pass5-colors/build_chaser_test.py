"""Pass 5 step 1: convert existing chaser color row in COLORS page into
transparent-RADIO + 10-static-button + Lua pattern.

In:  ViddyVault/Projects/steam-deck-midi/backups/2026-05-12-0014-pre-colorpalette-rewire-STEAMDECK-V2.tosc
Out: notes/2026-05-12-pass5-colors/STEAMDECK V2.tosc.new

This is the chaser-only test build. After Ben validates, we clone the pattern
5x for video_hl / video_sh / logo_hl / logo_sh / global (build_full.py).
"""

import re, zlib, uuid
from pathlib import Path

SRC = Path(r"C:/Users/Ben/Documents/ViddyVault/Projects/steam-deck-midi/backups/2026-05-12-0014-pre-colorpalette-rewire-STEAMDECK-V2.tosc")
DST = Path(__file__).parent / "STEAMDECK V2.tosc.new"

CHASER_COLOR_NAMES = ["red","orange","yellow","green","cyan","blue","purple","magenta","white","black"]
# corrected per-slot colors. existing chaser_black is mis-tinted as red in source.
CHASER_COLOR_RGBA = [
    (1, 0, 0, 1),                # red
    (0.955556, 0.579699, 0, 1),  # orange
    (1, 1, 0, 1),                # yellow
    (0, 1, 0, 1),                # green
    (0, 1, 1, 1),                # cyan
    (0, 0, 1, 1),                # blue
    (0.535088, 0, 1, 1),         # purple
    (1, 0, 1, 1),                # magenta
    (1, 1, 1, 1),                # white
    (0, 0, 0, 1),                # black (fixed: source had (1,0,0,1))
]

# normalize chaser button frame stride. existing y positions are slightly irregular
# (56,187,314,444,579,706,836,969,1098,1235). Keep them as-is to minimize visual
# disruption; we just normalize chaser_black width/height/x to match siblings.
CHASER_FRAMES_Y = [56, 187, 314, 444, 579, 706, 836, 969, 1098, 1235]
CHASER_X = 296
CHASER_W = 235
CHASER_H = 126

RADIO_X = CHASER_X
RADIO_Y = CHASER_FRAMES_Y[0]                              # top of first button
RADIO_W = CHASER_W
RADIO_H = (CHASER_FRAMES_Y[-1] + CHASER_H) - CHASER_FRAMES_Y[0]   # full vertical span

OSC_CHANNEL_PATH = "/composition/video/effects/colorpalette/effect/channels/chaser"
ROW_PREFIX = "chaser"


def _btn_id_to_name(idx: int) -> str:
    return f"{ROW_PREFIX}_slot{idx}"


def _node_span(data: bytes, anchor_idx: int) -> tuple[int, int]:
    """Given a byte position inside a <node>, return the (start,end) of that node."""
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


def _build_button(idx: int, button_id: str) -> bytes:
    """Static, non-interactive colored BUTTON. Lua updates .values.x for highlight."""
    r, g, b, a = CHASER_COLOR_RGBA[idx]
    name = _btn_id_to_name(idx)
    y = CHASER_FRAMES_Y[idx]
    xml = f"""<node ID='{button_id}' type='BUTTON'><properties><property type='b'><key><![CDATA[background]]></key><value>1</value></property><property type='i'><key><![CDATA[buttonType]]></key><value>2</value></property><property type='c'><key><![CDATA[color]]></key><value><r>{r}</r><g>{g}</g><b>{b}</b><a>{a}</a></value></property><property type='f'><key><![CDATA[cornerRadius]]></key><value>10</value></property><property type='r'><key><![CDATA[frame]]></key><value><x>{CHASER_X}</x><y>{y}</y><w>{CHASER_W}</w><h>{CHASER_H}</h></value></property><property type='b'><key><![CDATA[grabFocus]]></key><value>0</value></property><property type='b'><key><![CDATA[interactive]]></key><value>0</value></property><property type='b'><key><![CDATA[locked]]></key><value>0</value></property><property type='s'><key><![CDATA[name]]></key><value><![CDATA[{name}]]></value></property><property type='i'><key><![CDATA[orientation]]></key><value>0</value></property><property type='b'><key><![CDATA[outline]]></key><value>1</value></property><property type='i'><key><![CDATA[outlineStyle]]></key><value>0</value></property><property type='i'><key><![CDATA[pointerPriority]]></key><value>0</value></property><property type='b'><key><![CDATA[press]]></key><value>1</value></property><property type='b'><key><![CDATA[release]]></key><value>1</value></property><property type='i'><key><![CDATA[shape]]></key><value>1</value></property><property type='b'><key><![CDATA[valuePosition]]></key><value>0</value></property><property type='b'><key><![CDATA[visible]]></key><value>1</value></property></properties><values><value><key><![CDATA[x]]></key><locked>0</locked><lockedDefaultCurrent>1</lockedDefaultCurrent><default><![CDATA[0]]></default><defaultPull>0</defaultPull></value><value><key><![CDATA[touch]]></key><locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent><default><![CDATA[false]]></default><defaultPull>0</defaultPull></value></values><messages></messages></node>"""
    return xml.encode("utf-8")


def _lua_script() -> str:
    """Radio's onValueChanged fans highlight to chaser_slot0..chaser_slot9 buttons.

    onValueChanged fires on both user taps AND incoming OSC, so Resolume echo
    will also drive the highlight (no feedback loop because the buttons are
    non-interactive and have no outbound messages).
    """
    return (
        "function onValueChanged(key)\n"
        '  if key ~= "x" then return end\n'
        "  local idx = math.floor(self.values.x * 9 + 0.5)\n"
        "  for i = 0, 9 do\n"
        '    local btn = self.parent.children["' + ROW_PREFIX + '_slot" .. i]\n'
        "    if btn ~= nil then\n"
        "      btn.values.x = (i == idx) and 1 or 0\n"
        "    end\n"
        "  end\n"
        "end\n"
    )


def _build_radio(radio_id: str) -> bytes:
    """Transparent overlay RADIO. background=0 + color alpha=0 + outline=0.

    Selection indicator still draws (TouchOSC RADIO paints a fill on the active
    segment using `color` with alpha — we want that subtle so the underlying
    button color dominates. We rely on the Lua-driven button.x highlight as
    the primary cue.

    `connections` set to 0000000000 disables all OSC/MIDI ports for paranoia;
    actual OSC send is controlled by the <osc> block's send/receive flags.
    """
    script = _lua_script()
    # XML must escape Lua's & and < if any. our script has none, so direct embed is fine.
    return (
        f"<node ID='{radio_id}' type='RADIO'>"
        "<properties>"
        "<property type='b'><key><![CDATA[background]]></key><value>0</value></property>"
        # outline color when active: white with low alpha so it's a subtle highlight,
        # not a strong overlay. underlying button.x=1 highlight is the primary cue.
        "<property type='c'><key><![CDATA[color]]></key><value><r>1</r><g>1</g><b>1</b><a>0.25</a></value></property>"
        "<property type='f'><key><![CDATA[cornerRadius]]></key><value>10</value></property>"
        f"<property type='r'><key><![CDATA[frame]]></key><value><x>{RADIO_X}</x><y>{RADIO_Y}</y><w>{RADIO_W}</w><h>{RADIO_H}</h></value></property>"
        "<property type='b'><key><![CDATA[grabFocus]]></key><value>1</value></property>"
        "<property type='b'><key><![CDATA[interactive]]></key><value>1</value></property>"
        "<property type='b'><key><![CDATA[locked]]></key><value>0</value></property>"
        f"<property type='s'><key><![CDATA[name]]></key><value><![CDATA[{ROW_PREFIX}_picker]]></value></property>"
        # orientation=2 → vertical slot stacking (matches existing chaser pattern select widget)
        "<property type='i'><key><![CDATA[orientation]]></key><value>2</value></property>"
        "<property type='b'><key><![CDATA[outline]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[outlineStyle]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[pointerPriority]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[radioType]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[shape]]></key><value>1</value></property>"
        "<property type='i'><key><![CDATA[steps]]></key><value>10</value></property>"
        "<property type='b'><key><![CDATA[visible]]></key><value>1</value></property>"
        "</properties>"
        "<values>"
        "<value><key><![CDATA[x]]></key><locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent><default><![CDATA[0]]></default><defaultPull>0</defaultPull></value>"
        "<value><key><![CDATA[touch]]></key><locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent><default><![CDATA[false]]></default><defaultPull>0</defaultPull></value>"
        "</values>"
        "<messages>"
        "<osc><enabled>1</enabled><send>1</send><receive>1</receive><feedback>0</feedback><noDuplicates>0</noDuplicates><connections>1111111111</connections>"
        "<triggers><trigger><var><![CDATA[x]]></var><condition>ANY</condition></trigger></triggers>"
        f"<path><partial><type>CONSTANT</type><conversion>STRING</conversion><value><![CDATA[{OSC_CHANNEL_PATH}]]></value><scaleMin>0</scaleMin><scaleMax>1</scaleMax></partial></path>"
        # INTEGER conversion + scaleMin=0 scaleMax=9 maps radio.x (0..1 in 10 steps)
        # to integer 0..9. Resolume's effect-panel Int In dropdown receives this directly.
        "<arguments><partial><type>VALUE</type><conversion>INTEGER</conversion><value><![CDATA[x]]></value><scaleMin>0</scaleMin><scaleMax>9</scaleMax></partial></arguments>"
        "</osc>"
        "</messages>"
        f"<script><![CDATA[{script}]]></script>"
        "</node>"
    ).encode("utf-8")


def main() -> None:
    raw = SRC.read_bytes()
    data = zlib.decompress(raw)
    print(f"source: {SRC}")
    print(f"  raw bytes: {len(raw)}  decompressed: {len(data)}")

    # 1. find each chaser color button node, replace with new static button
    button_ids = []
    new_data_chunks = []
    cursor = 0
    chaser_nodes = []
    for c in CHASER_COLOR_NAMES:
        name_bytes = f"chaser {c}".encode()
        i = data.find(name_bytes)
        if i < 0:
            raise RuntimeError(f"chaser {c} not found")
        s, e = _node_span(data, i)
        # extract id from this span
        m = re.match(rb"<node ID='([^']+)'", data[s:s+200])
        bid = m.group(1).decode()
        chaser_nodes.append((s, e, bid))

    chaser_nodes.sort()
    for idx, (s, e, bid) in enumerate(chaser_nodes):
        if cursor < s:
            new_data_chunks.append(data[cursor:s])
        new_data_chunks.append(_build_button(idx, bid))
        cursor = e
        button_ids.append(bid)
    if cursor < len(data):
        tail = data[cursor:]
    else:
        tail = b""

    # 2. insert new RADIO node into the COLORS page children, right after the last chaser button
    # last chaser button's parent's </children> sits somewhere in tail; we want to inject
    # the radio AS a sibling, i.e. immediately after the last chaser button node closing tag.
    # That position is exactly `cursor` (end of last chaser button) in the rebuilt stream.
    radio_id = str(uuid.uuid1())
    radio_xml = _build_radio(radio_id)

    rebuilt = b"".join(new_data_chunks) + radio_xml + tail
    print(f"  rebuilt bytes: {len(rebuilt)}  delta: {len(rebuilt) - len(data)}")

    # 3. verify expected strings
    must_have = [
        b"chaser_slot0", b"chaser_slot9", b"chaser_picker",
        OSC_CHANNEL_PATH.encode(),
        b"onValueChanged",
    ]
    must_not_have = [
        b"chaser red", b"chaser orange", b"chaser black",
        b"viddylut",                                         # old chaser-row OSC path target
        b"/composition/layers/8/dashboard/link1",            # old chaser-row OSC path
    ]
    for s in must_have:
        c = rebuilt.count(s)
        flag = "OK" if c > 0 else "MISSING"
        print(f"  [{flag}] expected: {s!r}  count={c}")
    for s in must_not_have:
        c = rebuilt.count(s)
        flag = "OK" if c == 0 else "STILL PRESENT"
        print(f"  [{flag}] removed:  {s!r}  count={c}")

    # 4. recompress and write
    out = zlib.compress(rebuilt)
    DST.write_bytes(out)
    print(f"wrote: {DST}  bytes: {len(out)}")


if __name__ == "__main__":
    main()
