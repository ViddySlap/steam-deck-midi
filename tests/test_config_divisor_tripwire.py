"""P0(e): AST tripwire for unbounded config-derived divisors.

A division whose divisor is an instance attribute assigned straight from a
config lookup (``float(config.get("update_hz", 30))``) turns one hand-edited
config value into a ZeroDivisionError, a negative interval or a spin. Every
such attribute must be clamped WHERE IT IS ASSIGNED, through
``windows.engines.base.clamp_tick_hz`` or an explicit ``max``/``min``.

Declared before data (P0, lap sdpolish): this scan flags exactly the five
division sites in the four engines the master named at BASE OF LAP, and zero
sites at HEAD.  The scanner is the detector; ``scan_tree`` is importable so a
BASE archive can be scanned with HEAD's scanner.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WINDOWS_DIR = REPO_ROOT / "windows"

# Calls that make an assignment "bounded" for the purposes of this scan.
CLAMP_CALLS = frozenset({"clamp_tick_hz", "max", "min", "_clamp", "clamp"})


def _calls_named(node: ast.AST) -> set[str]:
    """Every function name called anywhere inside `node`."""
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def _reads_a_config_lookup(node: ast.AST) -> bool:
    """True if `node` pulls a value out of something named like a config."""
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if not isinstance(func, ast.Attribute) or func.attr != "get":
            continue
        base = func.value
        # config.get(...), self._config.get(...), spec.get(...), inputs.get(...)
        if isinstance(base, ast.Name):
            name = base.id
        elif isinstance(base, ast.Attribute):
            name = base.attr
        else:
            continue
        if any(tok in name.lower() for tok in ("config", "spec", "settings", "defaults",
                                               "inputs", "outputs", "tunables")):
            return True
    return False


def _self_attr_name(node: ast.AST) -> str | None:
    """`self._update_hz` -> `_update_hz`; anything else -> None."""
    if (isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"):
        return node.attr
    return None


def scan_module(source: str, path_label: str) -> list[dict]:
    """Flag divisions by unclamped config-derived `self` attributes."""
    tree = ast.parse(source)

    unclamped: set[str] = set()
    for node in ast.walk(tree):
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value = node.value
        else:
            continue
        for target in targets:
            attr = _self_attr_name(target)
            if attr is None:
                continue
            if not _reads_a_config_lookup(value):
                continue
            if _calls_named(value) & CLAMP_CALLS:
                continue  # bounded at the point of assignment
            unclamped.add(attr)

    findings: list[dict] = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # A function that clamps the value itself is allowed to divide by it.
        locally_clamped: set[str] = set()
        for node in ast.walk(func):
            if isinstance(node, ast.Assign) and _calls_named(node.value) & CLAMP_CALLS:
                for child in ast.walk(node.value):
                    attr = _self_attr_name(child)
                    if attr is not None:
                        locally_clamped.add(attr)
        for node in ast.walk(func):
            if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)):
                continue
            attr = _self_attr_name(node.right)
            if attr is None or attr not in unclamped or attr in locally_clamped:
                continue
            findings.append({
                "path": path_label,
                "line": node.lineno,
                "function": func.name,
                "divisor": f"self.{attr}",
            })
    return findings


def scan_tree(root: Path) -> list[dict]:
    """Scan every windows/**/*.py under `root` (a repo root)."""
    windows_dir = Path(root) / "windows"
    findings: list[dict] = []
    for path in sorted(windows_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        findings.extend(scan_module(path.read_text(encoding="utf-8"),
                                    str(path.relative_to(root))))
    return sorted(findings, key=lambda f: (f["path"], f["line"]))


class ConfigDivisorTripwireTests(unittest.TestCase):
    def test_no_unbounded_config_divisor_in_windows(self):
        findings = scan_tree(REPO_ROOT)
        self.assertEqual(
            findings, [],
            "unbounded config-derived divisor(s); clamp at assignment with "
            "windows.engines.base.clamp_tick_hz:\n"
            + "\n".join(f"  {f['path']}:{f['line']} in {f['function']}() divides by {f['divisor']}"
                        for f in findings),
        )

    def test_detector_fires_on_a_planted_unclamped_divisor(self):
        planted = (
            "class E:\n"
            "    def __init__(self, config):\n"
            "        self._update_hz = float(config.get('update_hz', 30))\n"
            "    def tick_interval_seconds(self):\n"
            "        return 1.0 / self._update_hz\n"
        )
        findings = scan_module(planted, "planted.py")
        self.assertEqual(len(findings), 1, findings)
        self.assertEqual(findings[0]["line"], 5)
        self.assertEqual(findings[0]["divisor"], "self._update_hz")

    def test_detector_is_silent_when_the_assignment_clamps(self):
        clamped = (
            "class E:\n"
            "    def __init__(self, config):\n"
            "        self._update_hz = clamp_tick_hz(config.get('update_hz', 30), default=30)\n"
            "    def tick_interval_seconds(self):\n"
            "        return 1.0 / self._update_hz\n"
        )
        self.assertEqual(scan_module(clamped, "clamped.py"), [])

    def test_detector_is_silent_when_the_dividing_function_clamps(self):
        local = (
            "class E:\n"
            "    def __init__(self, config):\n"
            "        self._tick_hz = float(config.get('tick_hz', 30))\n"
            "    def step(self):\n"
            "        tick_hz = max(1.0, self._tick_hz)\n"
            "        return 1.0 / tick_hz\n"
        )
        self.assertEqual(scan_module(local, "local.py"), [])

    def test_detector_ignores_a_divisor_that_is_not_config_derived(self):
        fixed = (
            "class E:\n"
            "    def __init__(self):\n"
            "        self._update_hz = 30.0\n"
            "    def tick_interval_seconds(self):\n"
            "        return 1.0 / self._update_hz\n"
        )
        self.assertEqual(scan_module(fixed, "fixed.py"), [])


if __name__ == "__main__":
    import json
    import sys
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT
    result = scan_tree(root)
    print(json.dumps({"root": str(root), "count": len(result), "findings": result}, indent=2))
