"""Round 5 fix: sf_mode buttons trigger -> touch/RISE.

The `var=x condition=RISE` combined with buttonType=1 toggle + Lua-driven
sibling updates was somehow not firing OSC. Switching to `var=touch
condition=RISE` decouples OSC firing from the x state machine -- it
fires purely on user finger press, which is more reliable.

In:  ../2026-05-12-post-ben-edit-2/STEAMDECK V2.tosc  (Ben's last save = same as r4 md5)
Out: ./STEAMDECK V2.tosc.r5
"""

import re
import zlib
from pathlib import Path

HERE = Path(__file__).parent
# Use Ben's last saved file (same content as r4)
SRC = Path(r"C:/Users/Ben/Documents/ViddyVault/Projects/steam-deck-midi/notes/2026-05-12-post-ben-edit-2/STEAMDECK V2.tosc")
DST = HERE / "STEAMDECK V2.tosc.r5"


def find_node_span(data, name):
    needle = b"<value><![CDATA[" + name.encode() + b"]]></value>"
    idx = data.find(needle)
    if idx < 0:
        raise RuntimeError(f"name not found: {name!r}")
    start = data.rfind(b"<node ", 0, idx)
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


# We need to rebuild the fixup2 changes (toggle + Lua + 4 extra paths) since
# Ben's last save is post-fixup2. But re-applying them is idempotent.
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


def patch_sf_mode_trigger(data, name):
    """Change all <trigger><var><![CDATA[x]]></var><condition>RISE</condition></trigger>
    to use var=touch instead."""
    s, e = find_node_span(data, name)
    block = data[s:e]
    new_block = block.replace(
        b"<trigger><var><![CDATA[x]]></var><condition>RISE</condition></trigger>",
        b"<trigger><var><![CDATA[touch]]></var><condition>RISE</condition></trigger>",
    )
    if new_block == block:
        print(f"  NO trigger replacement made for {name!r} (already touch?)")
        return data
    count = block.count(b"<trigger><var><![CDATA[x]]></var><condition>RISE</condition></trigger>")
    print(f"  {name}: replaced {count} trigger(s) with touch/RISE")
    return data.replace(block, new_block, 1)


def main():
    print(f"Reading {SRC}")
    raw = SRC.read_bytes()
    data = zlib.decompress(raw)
    print(f"Decompressed: {len(raw):,} -> {len(data):,} bytes")

    for name in ("sf_mode_on_layers", "sf_mode_on_group", "sf_mode_off"):
        data = patch_sf_mode_trigger(data, name)

    out_raw = zlib.compress(data)
    DST.write_bytes(out_raw)
    print(f"Wrote {DST}")


if __name__ == "__main__":
    main()
