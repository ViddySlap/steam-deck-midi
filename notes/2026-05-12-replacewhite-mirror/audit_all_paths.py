"""Audit ALL OSC paths in the patch, grouped by widget type and column."""
from __future__ import annotations

import re
import zlib
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
d = zlib.decompress((HERE / "STEAMDECK V2.tosc.bak").read_bytes())

# All unique OSC path strings (anything starting with /).
paths = re.findall(rb"<value><!\[CDATA\[(/[^\]]+)\]\]></value>", d)
counter = Counter(p.decode() for p in paths)
print(f"Unique OSC paths: {len(counter)}, total occurrences: {sum(counter.values())}")
for path, count in sorted(counter.items()):
    print(f"  {count:>3}  {path}")
