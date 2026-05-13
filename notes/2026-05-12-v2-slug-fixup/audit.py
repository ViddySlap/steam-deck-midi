"""Audit every viddy-colorisf reference in the .tosc.

Goal: distinguish V1 references (slug `viddy-colorisf` NOT followed by `v2`) from
V2 references (slug `viddy-colorisfv2`). Replace only the former.

Also print full OSC paths so we can spot any other variant slug forms.
"""
from __future__ import annotations

import re
import zlib
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "STEAMDECK V2.tosc.bak"

raw = SRC.read_bytes()
decompressed = zlib.decompress(raw)
print(f"file size compressed:   {len(raw)} bytes")
print(f"file size decompressed: {len(decompressed)} bytes")
print()

# 1. Raw substring counts on byte strings.
needles = [
    b"viddy-colorisf",
    b"viddy-colorisfv2",
    b"viddycolor",      # generic catch (in case label text leaked into OSC)
    b"VIDDY-COLOR",     # display label form (informational only — out of scope)
    b"VIDDYCOLOR",
    b"viddycolorisf",   # alt slug form, no hyphen
]
print("Raw substring counts:")
for n in needles:
    print(f"  {n.decode():<24} x {decompressed.count(n)}")
print()

# 2. Pull every OSC path containing "viddy" (case-insensitive) — paths are inside
#    <path>...</path> tags. Also grab attribute-style ones for safety.
osc_paths = re.findall(rb"/composition[^\s<>\"&]*viddy[^\s<>\"&]*", decompressed, re.IGNORECASE)
print(f"OSC paths mentioning viddy (case-insens): {len(osc_paths)} occurrences")
counter: Counter[str] = Counter(p.decode() for p in osc_paths)
for path, count in sorted(counter.items()):
    print(f"  {count:>3}  {path}")
print()

# 3. Identify V1-only matches: `viddy-colorisf` NOT immediately followed by `v2`.
v1_only = re.findall(rb"viddy-colorisf(?!v2)[^\s<>\"&/]*", decompressed)
v1_only_counter = Counter(b.decode() for b in v1_only)
print(f"`viddy-colorisf` tokens NOT followed by 'v2': {sum(v1_only_counter.values())}")
for tok, count in sorted(v1_only_counter.items()):
    print(f"  {count:>3}  {tok}")
print()

# 4. Also grab full OSC paths for V1 only (for the replacement table sanity-check).
v1_paths = re.findall(rb"/composition[^\s<>\"&]*viddy-colorisf(?!v2)[^\s<>\"&]*", decompressed)
v1_paths_counter = Counter(p.decode() for p in v1_paths)
print(f"V1-form full OSC paths: {sum(v1_paths_counter.values())}")
for path, count in sorted(v1_paths_counter.items()):
    print(f"  {count:>3}  {path}")
