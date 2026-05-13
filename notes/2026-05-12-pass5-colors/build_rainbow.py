"""Pass 5 step 4: Lua math fix + All Color cascade + Rainbow button.

- Fix the script property on all 6 picker RADIOs: integer step, not normalized
- Add cascade Lua to global_picker that fans its x to the 5 other picker radios
- Replace global_slot9 button + global_slot9_blackbox overlay with a Rainbow
  toggle button that flips /composition/layers/10/video/effects/recolour/bypassed
"""

import re
import zlib
import uuid
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "post-rearrange.tosc"
DST = HERE / "STEAMDECK V2.rainbow.tosc"


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


def lua_highlight(slug: str, extra: str = "") -> str:
    return (
        "function onValueChanged(key)\n"
        '  if key ~= "x" then return end\n'
        "  local idx = math.floor(self.values.x + 0.5)\n"
        "  if idx < 0 then idx = 0 end\n"
        "  if idx > 9 then idx = 9 end\n"
        "  for i = 0, 9 do\n"
        f'    local btn = self.parent.children["{slug}_slot" .. i]\n'
        "    if btn ~= nil then\n"
        "      btn.values.x = (i == idx) and 1 or 0\n"
        "    end\n"
        "  end\n"
        + extra +
        "end\n"
    )


def lua_global() -> str:
    extra = (
        "  if idx <= 8 then\n"
        '    local siblings = {"chaser_picker","videohl_picker","videosh_picker","logohl_picker","logosh_picker"}\n'
        "    for _, name in ipairs(siblings) do\n"
        "      local other = self.parent.children[name]\n"
        "      if other ~= nil then\n"
        "        other.values.x = self.values.x\n"
        "      end\n"
        "    end\n"
        "  end\n"
    )
    return lua_highlight("global", extra=extra)


def rewrite_script(data: bytes, picker_name: str, new_script: str) -> bytes:
    """Replace the script property's value inside the named picker node."""
    needle = f"<![CDATA[{picker_name}]]>".encode()
    i = data.find(needle)
    s, e = node_span(data, i)
    node_xml = data[s:e]
    pattern = re.compile(
        rb"(\[script\]\]></key><value><!\[CDATA\[)(.*?)(\]\]></value>)", re.S,
    )
    new_xml, n = pattern.subn(
        lambda m: m.group(1) + new_script.encode("utf-8") + m.group(3),
        node_xml, count=1,
    )
    if n == 0:
        raise RuntimeError(f"script property not found in {picker_name}")
    return data[:s] + new_xml + data[e:]


def remove_node_by_name(data: bytes, name: str) -> bytes:
    needle = f"<![CDATA[{name}]]>".encode()
    i = data.find(needle)
    if i < 0:
        raise RuntimeError(f"node named {name!r} not found")
    s, e = node_span(data, i)
    return data[:s] + data[e:]


def build_rainbow_button(node_id: str) -> bytes:
    """Magenta toggle button at (x=985, y=1235) bound to recolour.bypassed."""
    osc_path = "/composition/layers/10/video/effects/recolour/bypassed"
    return (
        f"<node ID='{node_id}' type='BUTTON'>"
        "<properties>"
        "<property type='b'><key><![CDATA[background]]></key><value>1</value></property>"
        # buttonType=1 = Toggle Release: x flips 0<->1 on each release
        "<property type='i'><key><![CDATA[buttonType]]></key><value>1</value></property>"
        # magenta
        "<property type='c'><key><![CDATA[color]]></key><value><r>1</r><g>0</g><b>1</b><a>1</a></value></property>"
        "<property type='f'><key><![CDATA[cornerRadius]]></key><value>10</value></property>"
        "<property type='r'><key><![CDATA[frame]]></key><value><x>985</x><y>1235</y><w>165</w><h>126</h></value></property>"
        "<property type='b'><key><![CDATA[grabFocus]]></key><value>1</value></property>"
        "<property type='b'><key><![CDATA[interactive]]></key><value>1</value></property>"
        "<property type='b'><key><![CDATA[locked]]></key><value>0</value></property>"
        "<property type='s'><key><![CDATA[name]]></key><value><![CDATA[rainbow_button]]></value></property>"
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
        "<osc><enabled>1</enabled><send>1</send><receive>1</receive><feedback>0</feedback><noDuplicates>0</noDuplicates><connections>1111111111</connections>"
        "<triggers><trigger><var><![CDATA[x]]></var><condition>ANY</condition></trigger></triggers>"
        f"<path><partial><type>CONSTANT</type><conversion>STRING</conversion><value><![CDATA[{osc_path}]]></value><scaleMin>0</scaleMin><scaleMax>1</scaleMax></partial></path>"
        "<arguments><partial><type>VALUE</type><conversion>FLOAT</conversion><value><![CDATA[x]]></value><scaleMin>0</scaleMin><scaleMax>1</scaleMax></partial></arguments>"
        "</osc>"
        "</messages>"
        "</node>"
    ).encode("utf-8")


def build_rainbow_label(node_id: str) -> bytes:
    """Transparent TEXT overlay stacked at the rainbow button frame, says 'Rainbow'."""
    return (
        f"<node ID='{node_id}' type='TEXT'>"
        "<properties>"
        "<property type='b'><key><![CDATA[background]]></key><value>0</value></property>"
        "<property type='c'><key><![CDATA[color]]></key><value><r>1</r><g>1</g><b>1</b><a>0</a></value></property>"
        "<property type='f'><key><![CDATA[cornerRadius]]></key><value>0</value></property>"
        "<property type='r'><key><![CDATA[frame]]></key><value><x>985</x><y>1235</y><w>165</w><h>126</h></value></property>"
        "<property type='b'><key><![CDATA[grabFocus]]></key><value>0</value></property>"
        # interactive=0 so taps pass through to the magenta button beneath
        "<property type='b'><key><![CDATA[interactive]]></key><value>0</value></property>"
        "<property type='b'><key><![CDATA[locked]]></key><value>0</value></property>"
        "<property type='s'><key><![CDATA[name]]></key><value><![CDATA[rainbow_label]]></value></property>"
        "<property type='i'><key><![CDATA[orientation]]></key><value>0</value></property>"
        "<property type='b'><key><![CDATA[outline]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[outlineStyle]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[pointerPriority]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[shape]]></key><value>0</value></property>"
        "<property type='i'><key><![CDATA[textAlignH]]></key><value>1</value></property>"
        "<property type='i'><key><![CDATA[textAlignV]]></key><value>1</value></property>"
        "<property type='c'><key><![CDATA[textColor]]></key><value><r>1</r><g>1</g><b>1</b><a>1</a></value></property>"
        "<property type='i'><key><![CDATA[textSize]]></key><value>40</value></property>"
        "<property type='b'><key><![CDATA[visible]]></key><value>1</value></property>"
        "</properties>"
        "<values>"
        "<value><key><![CDATA[text]]></key><locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent><default><![CDATA[Rainbow]]></default><defaultPull>0</defaultPull></value>"
        "<value><key><![CDATA[touch]]></key><locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent><default><![CDATA[false]]></default><defaultPull>0</defaultPull></value>"
        "</values>"
        "<messages></messages>"
        "</node>"
    ).encode("utf-8")


def append_to_colors_page(data: bytes, new_xml: bytes) -> bytes:
    """Inject new_xml just before the COLORS page's own </children>."""
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

    # 1. fix scripts on all 6 radios (drop the *9 multiplication)
    for slug in ("chaser", "videohl", "videosh", "logohl", "logosh"):
        data = rewrite_script(data, f"{slug}_picker", lua_highlight(slug))
    data = rewrite_script(data, "global_picker", lua_global())
    print("  rewrote 6 scripts (fixed math + added cascade on global)")

    # 2. remove global_slot9 button + global_slot9_blackbox overlay
    data = remove_node_by_name(data, "global_slot9")
    data = remove_node_by_name(data, "global_slot9_blackbox")
    print("  removed global_slot9 + global_slot9_blackbox")

    # 3. append Rainbow button + label (AFTER global_picker so it intercepts slot9 taps)
    btn_id = str(uuid.uuid1())
    lbl_id = str(uuid.uuid1())
    new_xml = build_rainbow_button(btn_id) + build_rainbow_label(lbl_id)
    data = append_to_colors_page(data, new_xml)
    print("  appended rainbow_button + rainbow_label")

    # 4. verify
    print("\nverify markers:")
    must_have = [
        b"rainbow_button", b"rainbow_label", b"Rainbow",
        b"/composition/layers/10/video/effects/recolour/bypassed",
        b"chaser_picker", b"global_picker",
    ]
    must_not_have = [
        b"global_slot9_blackbox",
        # the literal lua bug pattern (only the buggy form; the correct form has no *9)
        b"values.x * 9 + 0.5",
    ]
    # also: global_slot9 button is removed but the substring "global_slot9" still
    # appears as a prefix of nothing else, so it should be 0 now.
    must_not_have.append(b"<![CDATA[global_slot9]]>")
    for x in must_have:
        c = data.count(x)
        print(f"  [{'OK' if c > 0 else 'MISSING'}]  expected: {x!r}  count={c}")
    for x in must_not_have:
        c = data.count(x)
        print(f"  [{'OK' if c == 0 else 'STILL PRESENT'}]  removed:  {x!r}  count={c}")

    out = zlib.compress(data)
    DST.write_bytes(out)
    print(f"\nwrote: {DST}  bytes: {len(out)}  decompressed: {len(data)}")


if __name__ == "__main__":
    main()
