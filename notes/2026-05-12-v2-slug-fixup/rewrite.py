"""Rewrite V1 slug to V2 in the .tosc.

Single byte-replace `viddy-colorisf/` → `viddy-colorisfv2/`. This is safe because:
  - The 4 stale V1 OSC paths all end the slug with `/` (path separator).
  - The 3 live V2 OSC paths spell `viddy-colorisfv2` — substring `viddy-colorisf/`
    does NOT occur in them (the char after `viddy-colorisf` is `v`, not `/`).
  - The 8 widget-name TouchOSC IDs spell `viddycolor_...` (no hyphen in
    `viddy`+`color`, no `/` after) — out of scope and untouched.
"""
from __future__ import annotations

import hashlib
import re
import zlib
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "STEAMDECK V2.tosc.bak"
DST = HERE / "STEAMDECK V2.tosc.new"

raw = SRC.read_bytes()
decompressed = zlib.decompress(raw)

OLD = b"viddy-colorisf/"
NEW = b"viddy-colorisfv2/"

before_count = decompressed.count(OLD)
print(f"`{OLD.decode()}` occurrences before: {before_count}")
assert before_count == 4, f"Expected 4 V1 path occurrences, got {before_count}"

new_decompressed = decompressed.replace(OLD, NEW)
after_count = new_decompressed.count(OLD)
print(f"`{OLD.decode()}` occurrences after:  {after_count}")
assert after_count == 0, "V1 paths should be fully gone"

# Sanity: V2 path count should have jumped by 4.
v2_before = decompressed.count(b"viddy-colorisfv2/")
v2_after = new_decompressed.count(b"viddy-colorisfv2/")
print(f"`viddy-colorisfv2/` occurrences: {v2_before} -> {v2_after}  (delta = {v2_after - v2_before})")
assert v2_after - v2_before == 4

# Cross-check: dump every viddy-mentioning OSC path in the new file.
paths_new = re.findall(rb"/composition[^\s<>\"&]*viddy[^\s<>\"&]*", new_decompressed, re.IGNORECASE)
print(f"\nViddy-mentioning OSC paths in NEW file ({len(paths_new)} total):")
for path, count in sorted(Counter(p.decode() for p in paths_new).items()):
    print(f"  {count:>3}  {path}")

# Widget-name preservation check.
widget_names = decompressed.count(b"viddycolor_")
widget_names_after = new_decompressed.count(b"viddycolor_")
print(f"\nWidget-name preservation: viddycolor_ count {widget_names} -> {widget_names_after}")
assert widget_names == widget_names_after, "Widget names should be untouched"

# Re-compress and write out.
recompressed = zlib.compress(new_decompressed)
DST.write_bytes(recompressed)
print(f"\nWrote: {DST}")
print(f"  compressed size:   {len(recompressed)} bytes  (was {len(raw)})")
print(f"  decompressed size: {len(new_decompressed)} bytes  (was {len(decompressed)})")
print(f"  md5 of decompressed: {hashlib.md5(new_decompressed).hexdigest()}")
print(f"  md5 of compressed:   {hashlib.md5(recompressed).hexdigest()}")
