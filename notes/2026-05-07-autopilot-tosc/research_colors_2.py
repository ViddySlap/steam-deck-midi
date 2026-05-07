"""Sample one full 9-local color button + see what OSC paths it uses."""
import re
import zlib
from pathlib import Path

src = Path("STEAMDECK V2.tosc.current")
d = zlib.decompress(src.read_bytes())
text = d.decode("utf-8", errors="replace")

m = re.search(r"<!\[CDATA\[tabLabel\]\]></key><value><!\[CDATA\[COLORS\]\]>", text)
colors_pos = m.start()
children_open = text.find("<children>", colors_pos)
# Find page </children>
depth = 1
cursor = children_open + len("<children>")
while depth > 0:
    no = text.find("<children>", cursor)
    nc = text.find("</children>", cursor)
    if 0 <= no < nc:
        depth += 1
        cursor = no + len("<children>")
    else:
        depth -= 1
        if depth == 0:
            children_close = nc
            break
        cursor = nc + len("</children>")

page = text[children_open + len("<children>"):children_close]

# Sample button388 — the smallest 9-local button
button_re = re.compile(r"<node ID='[^']+' type='BUTTON'>", re.DOTALL)
for m in button_re.finditer(page):
    s = m.start()
    e = page.find("</node>", s) + len("</node>")
    body = page[s:e]
    nm = re.search(r"<!\[CDATA\[name\]\]></key><value><!\[CDATA\[([^]]+)\]\]>", body)
    name = nm.group(1) if nm else "?"
    if name == "button388":
        print(f"=== {name} ({e-s} chars) ===")
        print(body)
        break

# Now extract all OSC paths from any 9-local button
print("\n\n=== OSC paths used by 9-local color buttons ===")
seen = set()
for m in button_re.finditer(page):
    s = m.start()
    e = page.find("</node>", s) + len("</node>")
    body = page[s:e]
    if body.count("<local>") != 9:
        continue
    nm = re.search(r"<!\[CDATA\[name\]\]></key><value><!\[CDATA\[([^]]+)\]\]>", body)
    osc_paths = re.findall(r"<value><!\[CDATA\[(/composition[^]]+)\]\]>", body)
    nm_str = nm.group(1) if nm else "?"
    for p in osc_paths:
        if p not in seen:
            seen.add(p)
            print(f"  ({nm_str:12s}) {p}")
