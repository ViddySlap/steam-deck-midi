"""Inventory all RADIO widgets and their key properties."""
from __future__ import annotations

import re
import zlib
from pathlib import Path

HERE = Path(__file__).parent
d = zlib.decompress((HERE / "STEAMDECK V2.tosc.bak").read_bytes())

# Find every RADIO node opener — capture its ID + props.
# `<node ID='...' type='RADIO'>` ... we want the name + OSC path it sends to + script presence.

# Greedy split between consecutive `<node ID=...` markers so we get one chunk per node.
# Then filter to those with `type='RADIO'`.
chunks = re.split(rb"(<node ID='[^']+' type='[^']+'>)", d)

# chunks: [pre, opener1, content1, opener2, content2, ...]
nodes = []
for i in range(1, len(chunks), 2):
    opener = chunks[i]
    content = chunks[i + 1] if i + 1 < len(chunks) else b""
    m = re.match(rb"<node ID='([^']+)' type='([^']+)'>", opener)
    if not m:
        continue
    node_id, node_type = m.group(1).decode(), m.group(2).decode()
    nodes.append((node_id, node_type, content))

radios = [n for n in nodes if n[1] == "RADIO"]
print(f"Total RADIO nodes: {len(radios)}\n")

for node_id, node_type, content in radios:
    # Get name.
    name_match = re.search(rb"<property type='s'><key><!\[CDATA\[name\]\]></key><value><!\[CDATA\[([^\]]+)\]\]></value></property>", content)
    name = name_match.group(1).decode() if name_match else "(no name)"

    # Get OSC path.
    path_match = re.search(
        rb"<osc>.*?<path>.*?<value><!\[CDATA\[(/[^\]]+)\]\]></value>", content, re.DOTALL
    )
    path = path_match.group(1).decode() if path_match else "(no osc path)"

    # Has script?
    has_script = b"<key><![CDATA[script]]>" in content

    # frame
    frame_match = re.search(
        rb"<property type='r'><key><!\[CDATA\[frame\]\]></key><value><x>([^<]+)</x><y>([^<]+)</y><w>([^<]+)</w><h>([^<]+)</h></value></property>",
        content,
    )
    frame = (
        f"x={frame_match.group(1).decode()} y={frame_match.group(2).decode()} w={frame_match.group(3).decode()} h={frame_match.group(4).decode()}"
        if frame_match
        else "(no frame)"
    )

    print(f"  ID: {node_id}")
    print(f"    name:   {name}")
    print(f"    osc:    {path}")
    print(f"    script: {has_script}")
    print(f"    frame:  {frame}")
    print()
