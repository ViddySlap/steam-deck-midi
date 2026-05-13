"""Find a 'chaser' column button and dump its XML structure to understand the schema."""
from __future__ import annotations

import re
import zlib
from pathlib import Path

HERE = Path(__file__).parent
d = zlib.decompress((HERE / "STEAMDECK V2.tosc.bak").read_bytes())

# Find all occurrences of "chaser" path.
for needle in [b"channels/chaser]]", b"channels/chaserwhite]]", b"channels/videohl]]", b"channels/videowhite]]"]:
    n = d.count(needle)
    print(f"  `{needle.decode()}` x {n}")

print()

# Find one chaser path and dump a wide context.
idx = d.find(b"channels/chaser]]")
print(f"chaser path at offset {idx}")
print(f"Context (3000 bytes before, 200 after):")
start = max(0, idx - 3000)
end = min(len(d), idx + 200)
print(d[start:end].decode("utf-8", errors="replace"))
