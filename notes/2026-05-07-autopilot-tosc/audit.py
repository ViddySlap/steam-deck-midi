"""Decompress and audit the live .tosc to plan autopilot widget injection."""
import re
import zlib
from pathlib import Path

src = Path("STEAMDECK V2.tosc.bak")
raw = src.read_bytes()
print(f"compressed: {len(raw)} bytes")
decompressed = zlib.decompress(raw)
print(f"decompressed: {len(decompressed)} bytes")
Path("decompressed.xml").write_bytes(decompressed)

# Inventory ENGINES page
text = decompressed.decode("utf-8", errors="replace")

# Find every node tag's ID + name + type, focused on the ENGINES region
# We do a coarse scan for any GROUP or BUTTON/FADER/TEXT nodes
node_re = re.compile(
    r'<node[^>]*\bID="([^"]+)"[^>]*\btype="([A-Z_]+)"[^>]*>',
    re.DOTALL,
)
nodes = node_re.findall(text)
print(f"\nTotal nodes in patch: {len(nodes)}")
type_counts: dict[str, int] = {}
for _, t in nodes:
    type_counts[t] = type_counts.get(t, 0) + 1
for t, n in sorted(type_counts.items(), key=lambda kv: -kv[1]):
    print(f"  {t}: {n}")

# Find ENGINES page boundaries
print("\n--- ENGINES tab indicators ---")
for m in re.finditer(rb"ENGINES", decompressed):
    start = max(0, m.start() - 60)
    end = min(len(decompressed), m.end() + 60)
    snippet = decompressed[start:end].decode("utf-8", errors="replace").replace("\n", " ")
    print(f"@{m.start()}: ...{snippet}...")

# Inventory every OSC address used (rough)
osc_paths = sorted(set(re.findall(rb"/composition[^\s\"<>]*", decompressed)))
print(f"\nOSC paths in use: {len(osc_paths)}")
for p in osc_paths[:30]:
    print(f"  {decompressed.count(p)}x  {p.decode()}")
if len(osc_paths) > 30:
    print(f"  ... +{len(osc_paths)-30} more")
