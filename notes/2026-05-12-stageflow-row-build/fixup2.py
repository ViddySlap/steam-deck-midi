"""Round 4 fixups for STAGEFLOW page.

  1. All 42 stageflow LOOK buttons:
     - buttonType: 0 (momentary) -> 1 (toggle)
     - Trigger condition: RISE -> ANY (so both presses fire: on AND off)

     Result: press once -> send VALUE x = 1 (look on). Press again -> send 0
     (look off). Looks can stack. Receive=1 still in place so Resolume
     broadcasts update button state.

  2. 3 sf_mode_* buttons (on_layers / on_group / off):
     - buttonType: 0 -> 1 (toggle for visual latch)
     - Trigger condition: already RISE, keep it
     - Add Lua script: when this button's x goes to 1, set the other two
       mode buttons' x to 0 (radio behavior). Modeled on chaser_picker
       pattern from COLORS page.

In:  ViddyVault/.../notes/2026-05-12-post-ben-edit-2/STEAMDECK V2.tosc
Out: ./STEAMDECK V2.tosc.r4
"""

import re
import zlib
from pathlib import Path

HERE = Path(__file__).parent
SRC = Path(r"C:/Users/Ben/Documents/ViddyVault/Projects/steam-deck-midi/notes/2026-05-12-post-ben-edit-2/STEAMDECK V2.tosc")
DST = HERE / "STEAMDECK V2.tosc.r4"


def find_node_span(data: bytes, name_value: str) -> tuple[int, int]:
    needle = (b"<value><![CDATA[" + name_value.encode() + b"]]></value>")
    idx = data.find(needle)
    if idx < 0:
        raise RuntimeError(f"name not found: {name_value!r}")
    start = data.rfind(b"<node ", 0, idx)
    if start < 0:
        raise RuntimeError(f"<node ...> not found before {name_value!r}")
    depth = 0
    for m in re.finditer(rb"<node\b|</node>", data[start:]):
        s, e = m.span()
        s += start; e += start
        if data[s:s+5] == b"<node":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return start, e
    raise RuntimeError("unbalanced <node>")


def modify_button(data: bytes, name: str,
                  toggle_type: bool = True,
                  trigger_condition: str | None = None,
                  add_script: str | None = None) -> bytes:
    """Modify a button's properties.

    - toggle_type=True: set buttonType to 1 (toggle).
    - trigger_condition: if set, replace ALL <condition>X</condition> within
      this node with <condition>new</condition>.
    - add_script: append a Lua script property if not already present.
    """
    s, e = find_node_span(data, name)
    block = data[s:e]
    new_block = block

    if toggle_type:
        # change <key>buttonType</key><value>0</value> -> ...<value>1</value>
        new_block = re.sub(
            rb"(<key><!\[CDATA\[buttonType\]\]></key><value>)\d(</value>)",
            rb"\g<1>1\g<2>",
            new_block,
            count=1,
        )

    if trigger_condition:
        new_block = re.sub(
            rb"<condition>[A-Z]+</condition>",
            ("<condition>" + trigger_condition + "</condition>").encode(),
            new_block,
        )

    if add_script:
        # Avoid double-adding
        if b"<key><![CDATA[script]]>" not in new_block:
            script_prop = (
                "<property type='s'><key><![CDATA[script]]></key>"
                f"<value><![CDATA[{add_script}]]></value></property>"
            ).encode()
            # Insert just before </properties>
            new_block = new_block.replace(
                b"</properties>",
                script_prop + b"</properties>",
                1,
            )

    if new_block == block:
        return data  # no change applied
    return data.replace(block, new_block, 1)


MODE_RADIO_SCRIPT = """function onValueChanged(key)
  if key ~= "x" then return end
  if self.values.x < 0.5 then return end
  local me = self.name
  local siblings = {"sf_mode_on_layers", "sf_mode_on_group", "sf_mode_off"}
  for _, n in ipairs(siblings) do
    if n ~= me then
      local sib = self.parent.children[n]
      if sib ~= nil and sib.values.x > 0.5 then
        sib.values.x = 0
      end
    end
  end
end"""


def main():
    print(f"Reading {SRC}")
    raw = SRC.read_bytes()
    data = zlib.decompress(raw)
    print(f"Decompressed: {len(raw):,} -> {len(data):,} bytes")

    # ----- Step 1: look buttons -> toggle + ANY trigger -----
    look_names = []
    for row in (0, 1, 2, 3, 5, 6):
        for look in range(1, 7):
            look_names.append(f"sf_r{row}_look{look}")
    for look in range(1, 7):
        look_names.append(f"sf_r0_groupvideo_look{look}")

    changed = 0
    for name in look_names:
        new_data = modify_button(data, name, toggle_type=True, trigger_condition="ANY")
        if new_data is not data:
            changed += 1
        data = new_data
    print(f"Step 1: 42 look buttons -> toggle+ANY trigger ({changed} modified)")

    # ----- Step 2: 3 sf_mode buttons -> toggle + Lua radio -----
    for name in ("sf_mode_on_layers", "sf_mode_on_group", "sf_mode_off"):
        before_len = len(data)
        data = modify_button(data, name,
                             toggle_type=True,
                             trigger_condition="RISE",  # keep RISE
                             add_script=MODE_RADIO_SCRIPT)
        delta = len(data) - before_len
        print(f"Step 2: {name} modified (delta={delta} bytes)")

    # ----- Compress + write -----
    out_raw = zlib.compress(data)
    DST.write_bytes(out_raw)
    print(f"Wrote {DST}  ({len(data):,} bytes uncompressed, {len(out_raw):,} compressed)")


if __name__ == "__main__":
    main()
