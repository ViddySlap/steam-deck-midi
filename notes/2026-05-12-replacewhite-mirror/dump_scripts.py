"""Dump each source-radio's existing Lua script verbatim."""
from __future__ import annotations

import re
import zlib
from pathlib import Path

HERE = Path(__file__).parent
d = zlib.decompress((HERE / "STEAMDECK V2.tosc.bak").read_bytes())

targets = ["chaser_picker", "videohl_picker", "logohl_picker",
           "chaserwhite_picker", "videowhite_picker", "logowhite_picker",
           "videosh_picker", "logosh_picker", "global_picker"]

# Split into RADIO node chunks.
chunks = re.split(rb"(<node ID='[^']+' type='RADIO'>)", d)
nodes = []
for i in range(1, len(chunks), 2):
    opener = chunks[i]
    content = chunks[i + 1] if i + 1 < len(chunks) else b""
    m = re.match(rb"<node ID='([^']+)' type='RADIO'>", opener)
    if m:
        nodes.append((m.group(1).decode(), content))

for node_id, content in nodes:
    name_match = re.search(
        rb"<property type='s'><key><!\[CDATA\[name\]\]></key><value><!\[CDATA\[([^\]]+)\]\]></value></property>",
        content,
    )
    if not name_match:
        continue
    name = name_match.group(1).decode()
    if name not in targets:
        continue

    script_match = re.search(
        rb"<property type='s'><key><!\[CDATA\[script\]\]></key><value><!\[CDATA\[(.+?)\]\]></value></property>",
        content,
        re.DOTALL,
    )
    print("=" * 80)
    print(f"name: {name}   ID: {node_id}")
    print("=" * 80)
    if script_match:
        script = script_match.group(1).decode()
        print(script)
    else:
        print("(no script)")
    print()
