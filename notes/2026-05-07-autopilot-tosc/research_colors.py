"""Research: how do COLORS-page mutually-exclusive buttons work?

Find a color button on the COLORS page, dump its full XML including the
local messages that clear the other color buttons.
"""
import re
import zlib
from pathlib import Path

src = Path("STEAMDECK V2.tosc.current")
d = zlib.decompress(src.read_bytes())
text = d.decode("utf-8", errors="replace")

# Find the COLORS page tab
m = re.search(rb"<!\[CDATA\[tabLabel\]\]></key><value><!\[CDATA\[COLORS\]\]>", d)
if not m:
    raise SystemExit("COLORS tab not found")
colors_pos = m.start()
print(f"COLORS tabLabel at offset {colors_pos}")

# Walk backward to enclosing <node ... type='GROUP'>
node_start = d.rfind(b"<node ", 0, colors_pos)
print(f"COLORS page <node> opens at {node_start}")

# Find the page's </children>
children_open = d.find(b"<children>", colors_pos)
depth = 1
cursor = children_open + len(b"<children>")
while depth > 0:
    next_open = d.find(b"<children>", cursor)
    next_close = d.find(b"</children>", cursor)
    if 0 <= next_open < next_close:
        depth += 1
        cursor = next_open + len(b"<children>")
    else:
        depth -= 1
        if depth == 0:
            children_close = next_close
            break
        cursor = next_close + len(b"</children>")
print(f"COLORS page <children>: {children_open} .. {children_close}")
print()

# Find every BUTTON inside the COLORS page
page_xml = d[children_open + len(b"<children>"):children_close].decode("utf-8", errors="replace")

button_re = re.compile(r"<node ID='[^']+' type='BUTTON'>", re.DOTALL)
buttons = []
for m in button_re.finditer(page_xml):
    start = m.start()
    end = page_xml.find("</node>", start) + len("</node>")
    name_match = re.search(
        r"<!\[CDATA\[name\]\]></key><value><!\[CDATA\[([^]]+)\]\]>",
        page_xml[start:start+1500],
    )
    name = name_match.group(1) if name_match else "?"
    buttons.append((name, start, end, end - start))

print(f"Found {len(buttons)} BUTTONs on COLORS page")
for name, s, e, sz in buttons[:15]:
    print(f"  {name:25s}  {sz:5d} chars")

# Find a button that has <local> messages — that's the radio pattern
print("\n--- buttons with <local> messages ---")
for name, s, e, sz in buttons:
    body = page_xml[s:e]
    if "<local>" in body:
        n_local = body.count("<local>")
        print(f"  {name:25s}  {n_local} local messages")

print("\n--- find the smallest button WITH locals as a template ---")
candidates = [
    (name, s, e, sz) for (name, s, e, sz) in buttons
    if "<local>" in page_xml[s:e]
]
candidates.sort(key=lambda x: x[3])
if candidates:
    name, s, e, sz = candidates[0]
    print(f"\nSAMPLE: {name} ({sz} chars)")
    print(page_xml[s:e])
