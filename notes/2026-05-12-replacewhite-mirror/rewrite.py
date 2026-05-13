"""Extend the chaser_picker / videohl_picker / logohl_picker Lua scripts to
mirror their x value to their corresponding REPLACE WHITE picker after the
visual cascade.

Mirror is ONE-WAY: source -> white. White pickers can still be tapped
independently to override.
"""
from __future__ import annotations

import hashlib
import zlib
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "STEAMDECK V2.tosc.bak"
DST = HERE / "STEAMDECK V2.tosc.new"


def make_script(slot_prefix: str, white_picker: str | None) -> str:
    """Build the picker's onValueChanged body."""
    lines = [
        "function onValueChanged(key)",
        '  if key ~= "x" then return end',
        "  local idx = math.floor(self.values.x + 0.5)",
        "  if idx < 0 then idx = 0 end",
        "  if idx > 9 then idx = 9 end",
        "  for i = 0, 9 do",
        f'    local btn = self.parent.children["{slot_prefix}_slot" .. i]',
        "    if btn ~= nil then",
        "      btn.values.x = (i == idx) and 1 or 0",
        "    end",
        "  end",
    ]
    if white_picker:
        lines += [
            f'  local mirror = self.parent.children["{white_picker}"]',
            "  if mirror ~= nil and mirror.values.x ~= idx then",
            "    mirror.values.x = idx",
            "  end",
        ]
    lines.append("end")
    return "\n".join(lines) + "\n"


# (slot_prefix, white_picker_to_mirror)  --  None means leave script untouched.
SCRIPT_PLAN = [
    ("chaser",   "chaserwhite_picker"),
    ("videohl",  "videowhite_picker"),
    ("logohl",   "logowhite_picker"),
]


raw = SRC.read_bytes()
decompressed = zlib.decompress(raw)

new_decompressed = decompressed
for slot_prefix, white_picker in SCRIPT_PLAN:
    old_script = make_script(slot_prefix, white_picker=None).encode()
    new_script = make_script(slot_prefix, white_picker).encode()
    before_count = new_decompressed.count(old_script)
    assert before_count == 1, (
        f"Expected exactly 1 occurrence of {slot_prefix} old script, got {before_count}"
    )
    new_decompressed = new_decompressed.replace(old_script, new_script)
    # Sanity: new script should now be present exactly once.
    after_count = new_decompressed.count(new_script)
    assert after_count == 1, (
        f"After replace, expected 1 occurrence of new {slot_prefix} script, got {after_count}"
    )
    print(f"  {slot_prefix}_picker -> mirrors to {white_picker}")
    print(f"    script bytes: {len(old_script)} -> {len(new_script)} (delta {len(new_script) - len(old_script)})")

# Make sure I didn't accidentally touch the other pickers' scripts.
for slot_prefix in ["videosh", "logosh", "global", "chaserwhite", "logowhite", "videowhite"]:
    untouched_old = make_script(slot_prefix, white_picker=None).encode()
    # global_picker has extra cascade body so the untouched_old won't match it (good).
    # videosh / logosh / *white have the plain script so they should still match exactly.
    if slot_prefix in ("videosh", "logosh", "chaserwhite", "logowhite", "videowhite"):
        assert new_decompressed.count(untouched_old) == 1, (
            f"{slot_prefix}_picker script appears to have been disturbed"
        )

# Size sanity.
print(f"\nDecompressed size: {len(decompressed)} -> {len(new_decompressed)} "
      f"(delta {len(new_decompressed) - len(decompressed)} bytes)")

recompressed = zlib.compress(new_decompressed)
DST.write_bytes(recompressed)
print(f"Compressed size:   {len(raw)} -> {len(recompressed)}")
print(f"md5 (decompressed): {hashlib.md5(new_decompressed).hexdigest()}")
print(f"md5 (compressed):   {hashlib.md5(recompressed).hexdigest()}")
print(f"\nWrote: {DST}")
