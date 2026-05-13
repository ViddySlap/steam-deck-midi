"""Pass 5 step 6: fix resync button trigger condition RISE -> ANY.

Symptom (Ben 2026-05-12 PM): tapping Resync in TouchOSC made Resolume's Resync
event-param UI button stick down. OSC monitor confirmed: only int32:1 was sent,
never int32:0. Cause: my <condition>RISE</condition> fired OSC only on press,
not on release, so Resolume's button visually stayed pressed.

Fix: condition=ANY. Press sends 1, release sends 0. Resolume's event param edge-
triggers only on the rising 1 (no double-fire), and the trailing 0 visually
unpresses the UI button.

Starts from `post-controls-tweak.tosc` (just pulled from Deck after Ben moved
the resync/fadetime widgets to the bottom-right).
"""

import re
import zlib
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "post-controls-tweak.tosc"
DST = HERE / "STEAMDECK V2.resync-fix.tosc"


def main() -> None:
    raw = SRC.read_bytes()
    data = zlib.decompress(raw)
    print(f"source: {SRC}  raw={len(raw)}  decompressed={len(data)}")

    # locate the resync_button node
    needle = b"<![CDATA[resync_button]]>"
    i = data.find(needle)
    if i < 0:
        raise RuntimeError("resync_button not found")
    start = data.rfind(b"<node ", 0, i)
    depth = 0
    end = None
    for m in re.finditer(rb"<node\s|</node>", data):
        if m.start() < start:
            continue
        if m.group().startswith(b"<node"):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                end = m.end()
                break

    node = data[start:end]
    # swap RISE -> ANY inside this one node only
    new_node, n = re.subn(
        rb"<trigger><var><!\[CDATA\[x\]\]></var><condition>RISE</condition></trigger>",
        b"<trigger><var><![CDATA[x]]></var><condition>ANY</condition></trigger>",
        node, count=1,
    )
    if n == 0:
        raise RuntimeError("RISE trigger condition not found in resync_button")
    data = data[:start] + new_node + data[end:]
    print("  patched resync_button trigger condition RISE -> ANY")

    # verify only one node was changed, others untouched
    rise_count = data.count(b"<condition>RISE</condition>")
    any_count_resync = new_node.count(b"<condition>ANY</condition>")
    print(f"\nverify:")
    print(f"  RISE conditions remaining in file: {rise_count} (expect 0)")
    print(f"  ANY conditions in resync_button: {any_count_resync} (expect >= 1)")

    out = zlib.compress(data)
    DST.write_bytes(out)
    print(f"\nwrote: {DST}  bytes: {len(out)}  decompressed: {len(data)}")


if __name__ == "__main__":
    main()
