"""Fix the re-tap-doesn't-cascade bug on the 4 cascading pickers.

Old gate:  `if key ~= "x" then return end`  -- only fires when x value changes.
New gate:  fire on touch release (whether x changed or not), and on
           programmatic x-writes that happen while the widget isn't being touched.

Touch lifecycle for a user tap:
  press   -> key="touch", self.values.touch == true   -- skip
  drag    -> key="x"     while touch == true           -- skip (wait for release)
  release -> key="touch", self.values.touch == false  -- CASCADE

Programmatic write (e.g. global cascade -> chaser.values.x = N):
  -> key="x", self.values.touch == false              -- CASCADE
"""
from __future__ import annotations

import hashlib
import zlib
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "STEAMDECK V2.tosc.bak"
DST = HERE / "STEAMDECK V2.tosc.new"


# (old gate line, new gate lines) used as the prefix substring for the byte replace.
# Same change applied to all 4 picker scripts; we rely on each script's slot prefix
# being unique to disambiguate which one we're touching.
OLD_GATE = '  if key ~= "x" then return end\n'
NEW_GATE = (
    '  if key ~= "x" and key ~= "touch" then return end\n'
    "  if self.values.touch then return end\n"
)


def patch_script(decompressed: bytes, slot_prefix: str) -> bytes:
    """Find the script that uses `<slot_prefix>_slot` and patch its gate line.

    To make the replacement uniquely targeted, we match a context window that
    includes the slot lookup (which is unique per picker). We replace ONLY the
    gate line within that picker's script.
    """
    # Unique marker: the script's slot-lookup line.
    marker = f'    local btn = self.parent.children["{slot_prefix}_slot" .. i]'
    marker_bytes = marker.encode()
    marker_count = decompressed.count(marker_bytes)
    assert marker_count == 1, f"Expected exactly 1 {slot_prefix} marker, got {marker_count}"

    marker_pos = decompressed.index(marker_bytes)

    # The gate line we want to replace lives BEFORE the marker, between the
    # `function onValueChanged(key)` opener and the slot loop. Find the gate
    # line by looking backwards from the marker.
    gate_bytes = OLD_GATE.encode()
    # Search the 400 bytes immediately preceding the marker for the gate line.
    window_start = max(0, marker_pos - 400)
    window = decompressed[window_start:marker_pos]
    rel_idx = window.find(gate_bytes)
    assert rel_idx >= 0, (
        f"Could not find gate line in script preceding {slot_prefix}_slot marker"
    )
    abs_start = window_start + rel_idx
    abs_end = abs_start + len(gate_bytes)

    new = decompressed[:abs_start] + NEW_GATE.encode() + decompressed[abs_end:]
    return new


raw = SRC.read_bytes()
decompressed = zlib.decompress(raw)

new_decompressed = decompressed
for slot_prefix in ["chaser", "videohl", "logohl", "global"]:
    new_decompressed = patch_script(new_decompressed, slot_prefix)
    print(f"  Patched {slot_prefix}_picker gate")

# Sanity: OLD_GATE should now appear in the OTHER 5 pickers (videosh, logosh,
# chaserwhite, logowhite, videowhite) but NOT in the 4 we just fixed.
remaining = new_decompressed.count(OLD_GATE.encode())
print(f"\nRemaining OLD_GATE occurrences: {remaining} (should be 5 = videosh/logosh/3 whites)")
assert remaining == 5

new_gate_count = new_decompressed.count(NEW_GATE.encode())
print(f"NEW_GATE occurrences: {new_gate_count} (should be 4)")
assert new_gate_count == 4

# Size sanity.
delta = len(new_decompressed) - len(decompressed)
expected = 4 * (len(NEW_GATE) - len(OLD_GATE))
print(f"\nSize delta: {delta} bytes (expected {expected})")
assert delta == expected

recompressed = zlib.compress(new_decompressed)
DST.write_bytes(recompressed)
print(f"\nCompressed: {len(raw)} -> {len(recompressed)}")
print(f"md5 (decompressed): {hashlib.md5(new_decompressed).hexdigest()}")
print(f"md5 (compressed):   {hashlib.md5(recompressed).hexdigest()}")
print(f"Wrote: {DST}")
