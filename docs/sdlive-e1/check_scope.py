"""Prove E1 preserved existing tests, handler bodies and the pinned capture kit."""
import ast
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
base = "c406d6e60d268e79334da398168ff07ad94690a2"
def blob(filename):
    return subprocess.check_output(["git", "-C", str(root), "show", base + ":" + filename])
def methods(source):
    return {n.name: n for cls in ast.parse(source).body
            if isinstance(cls, ast.ClassDef) and cls.name == "ActionReceiver"
            for n in cls.body if isinstance(n, ast.FunctionDef)}
a, b = methods(blob("windows/receiver.py")), methods((root / "windows/receiver.py").read_bytes())
changed = [name for name in a if ast.dump(ast.Module(body=a[name].body, type_ignores=[])) !=
           ast.dump(ast.Module(body=b[name].body, type_ignores=[]))]
assert changed == ["__init__", "handle_datagram", "release_all", "advance_fades",
                   "advance_relative_ccs", "advance_staged_note_macros"], changed
assert set(a) == set(b)
paths = ["windows/config.py", "windows/midi.py"]
paths += subprocess.check_output(["git", "-C", str(root), "ls-tree", "-r", "--name-only", base,
                                  "tests", "scripts/showready"], text=True).splitlines()
for filename in paths:
    assert (root / filename).read_bytes() == blob(filename), filename
result = {"command": [sys.executable, *sys.argv], "base": base,
          "receiver_methods_preserved": len(a), "unchanged_receiver_method_bodies": len(a) - len(changed),
          "changed_method_bodies": changed, "byte_identical_paths": paths, "status": "PASS"}
Path(sys.argv[1]).write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
print(json.dumps(result, indent=2))
