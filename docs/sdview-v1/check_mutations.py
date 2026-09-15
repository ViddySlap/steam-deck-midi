"""Run V1 planted-fault proofs in copies, never in the working config tree."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
scratch = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/sdview-v1/mutations")
scratch.mkdir(parents=True, exist_ok=True)
copy_root = Path(tempfile.mkdtemp(prefix="proof-", dir=scratch))
for directory in ("windows", "tests"):
    shutil.copytree(ROOT / directory, copy_root / directory,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.png"))
for filename in ("docs/api.md", "config/actions.yaml"):
    destination = copy_root / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / filename, destination)

env = {**os.environ, "PYTHONPATH": str(copy_root), "TMPDIR": str(scratch.resolve())}
selectors = ["tests.test_controller_map", "tests.test_controller_routes",
             "tests.test_ui_server.BridgeSettingsApiTests.test_api_inventory_matches_registered_method_paths"]


def run(label, targets, expected):
    command = [sys.executable, "-B", "-m", "unittest", *targets]
    result = subprocess.run(command, cwd=copy_root, env=env, capture_output=True, text=True)
    (copy_root / (label + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
    assert result.returncode == expected, (label, result.returncode, result.stdout, result.stderr)
    if expected:
        assert "FAIL:" in result.stderr, (label, "must fail an assertion, not an import or execution error")
    return {"label": label, "command": command, "cwd": str(copy_root),
            "exit_code": result.returncode, "log": str(copy_root / (label + ".log"))}


results = [run("pristine", selectors, 0)]
mutants = [
    ("catalog-added-id", "config/actions.yaml", lambda s: s + "  - SCRATCH_NEW_ACTION\n",
     "tests.test_controller_map.ControllerMapTests.test_every_catalog_action_appears_exactly_once"),
    ("duplicate-map-action", "windows/static/controller/controller_map.json",
     lambda s: s.replace('"BTN_A_LAYER_2"', '"BTN_A"', 1),
     "tests.test_controller_map.ControllerMapTests.test_every_catalog_action_appears_exactly_once"),
    ("wrong-map-group", "windows/static/controller/controller_map.json",
     lambda s: s.replace('"layer_2":', '"long_press":', 1),
     "tests.test_controller_map.ControllerMapTests.test_groups_follow_action_names"),
    ("missing-api-row", "docs/api.md",
     lambda s: "\n".join(line for line in s.split("\n") if not line.startswith('| GET | `/api/controller-map`')),
     selectors[2]),
    ("skip-parser", "windows/ui_server.py", lambda s: s.replace("                load_midi_map(tmp_path, section)", "                pass", 1),
     "tests.test_controller_routes.ControllerRouteTests.test_bad_specs_return_parser_error_and_preserve_bytes_even_when_forced"),
    ("skip-conflict-guard", "windows/ui_server.py", lambda s: s.replace("before_replace=guard_conflicts", "before_replace=None", 1),
     "tests.test_controller_routes.ControllerRouteTests.test_conflict_409_and_force_200_include_shared_mappings"),
    ("ignore-force", "windows/ui_server.py", lambda s: s.replace('conflicts and request.args.get("force") != "1"', 'conflicts', 1),
     "tests.test_controller_routes.ControllerRouteTests.test_conflict_409_and_force_200_include_shared_mappings"),
    ("skip-disk-replace", "windows/ui_server.py", lambda s: s.replace("            os.replace(tmp_path, target)", "            pass", 1),
     "tests.test_controller_routes.ControllerRouteTests.test_put_all_mapping_types_flat_and_sectioned"),
    ("skip-revision", "windows/ui_server.py", lambda s: s.replace("self._mapping_revision += 1", "self._mapping_revision += 0", 1),
     "tests.test_controller_routes.ControllerRouteTests.test_version_keeps_receiver_reload_observations"),
    ("skip-delete", "windows/ui_server.py", lambda s: s.replace('document["mappings"].pop(action_id, None)', 'None', 1),
     "tests.test_controller_routes.ControllerRouteTests.test_delete_twice_and_shared_fallback_flat_and_sectioned"),
    ("macro-loses-target", "windows/ui_server.py", lambda s: s.replace("current if current is not None else defaults[kind]", "defaults[kind]", 1),
     "tests.test_controller_routes.ControllerRouteTests.test_macro_cc_and_staged_merge_preserve_targets_remove_optional_overrides"),
    ("macro-accepts-incompatible", "windows/ui_server.py", lambda s: s.replace('if current is not None and current.get("type") != macro["type"]:', 'if False:', 1),
     "tests.test_controller_routes.ControllerRouteTests.test_macro_incompatible_unknown_action_invalid_section_and_parser_error"),
]
for label, filename, mutate, selector in mutants:
    target = copy_root / filename
    original = target.read_text(encoding="utf-8")
    changed = mutate(original)
    assert changed != original, label
    try:
        target.write_text(changed, encoding="utf-8")
        results.append(run(label, [selector], 1))
    finally:
        target.write_text(original, encoding="utf-8")
        # Avoid same-second, same-size bytecode masking a restored source.
        for cache in copy_root.rglob("__pycache__"):
            shutil.rmtree(cache)
    results.append(run(label + "-restored", [selector], 0))
(copy_root / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"pristine_exit": 0, "mutants_red": len(mutants), "restored_green": len(mutants),
                  "evidence": str(copy_root / "results.json")}))
