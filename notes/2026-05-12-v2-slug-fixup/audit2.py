"""Find where the 8 `viddycolor` raw matches live (they're not in OSC paths)."""
import re
import zlib
from pathlib import Path

HERE = Path(__file__).parent
decompressed = zlib.decompress((HERE / "STEAMDECK V2.tosc.bak").read_bytes())

# Find every offset of `viddycolor` and dump 120 bytes of context.
needle = b"viddycolor"
offset = 0
hits = []
while True:
    idx = decompressed.find(needle, offset)
    if idx < 0:
        break
    hits.append(idx)
    offset = idx + 1

print(f"`viddycolor` raw substring hits: {len(hits)}")
for i, idx in enumerate(hits, 1):
    start = max(0, idx - 60)
    end = min(len(decompressed), idx + 80)
    ctx = decompressed[start:end].decode("utf-8", errors="replace")
    ctx = ctx.replace("\n", "\\n")
    print(f"\n[hit {i}]  offset {idx}")
    print(f"  ...{ctx}...")
