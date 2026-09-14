"""sdcore gate mutation spot-checks. Mutates ONLY /tmp/sdcore-gate/tree."""
import hashlib, subprocess, sys
from pathlib import Path

TREE = Path("/tmp/sdcore-gate/tree")
PY = "/Users/viddyslap/Documents/project-workspaces/steam-deck-midi/.venv/bin/python"

MUTANTS = [
    ("S1", "windows/config.py",
     'return {**selected, "mappings": {**shared.get("mappings", {}), **mappings}}',
     'return {**selected, "mappings": {**mappings, **shared.get("mappings", {})}}',
     "tests.test_windows_config.PresetSectionTests.test_shared_mappings_apply_everywhere_with_whole_action_override"),
    ("S2", "windows/ui_server.py",
     "                        if name == own:\n                            return jsonify({\"error\": \"cannot delete this machine's section\"}), 409\n",
     "",
     "tests.test_ui_server.SectionApiTests.test_crud_refusals_leave_file_and_reload_untouched"),
    ("S3", "windows/preset_watch.py",
     "paths.update((self.presets_dir / '.active', self.settings_path))",
     "paths.update(())",
     "tests.test_preset_watch.PresetWatcherTests.test_touch_add_delete_marker_and_local_settings"),
    ("S3b", "windows/receiver.py",
     "        self.state_version += 1\n",
     "",
     "tests.test_preset_watch.ReloadIntegrationTests.test_save_and_disk_reload_versions_and_real_midi"),
    ("S4", "deck/transport.py",
     "    for receiver in targets:\n",
     "    for receiver in targets[:1]:\n",
     "tests.test_deck_transport.DeckTransportTests.test_action_identical_bytes_and_seq_in_target_order"),
    ("S5", "deck/control_api.py",
     "if self.server.token_required and not hmac.compare_digest",
     "if False and self.server.token_required and not hmac.compare_digest",
     "tests.test_deck_control_api.DeckControlAPITests.test_off_loopback_requires_token_on_every_route"),
]


def run(test):
    p = subprocess.run([PY, "-B", "-m", "unittest", test], cwd=TREE, capture_output=True, text=True, timeout=120)
    tail = [l for l in p.stderr.splitlines() if l.startswith(("Ran ", "OK", "FAILED"))]
    return p.returncode, " | ".join(tail), p.stderr


ok = True
for link, rel, old, new, test in MUTANTS:
    path = TREE / rel
    original = path.read_bytes()
    sha = hashlib.sha256(original).hexdigest()
    text = original.decode()
    count = text.count(old)
    if count != 1:
        print(f"{link} ANCHOR count={count} in {rel} -- cannot mutate"); ok = False; continue
    rc0, s0, err0 = run(test)
    try:
        path.write_text(text.replace(old, new, 1))
        rc1, s1, err1 = run(test)
    finally:
        path.write_bytes(original)
    rc2, s2, _ = run(test)
    restored = hashlib.sha256(path.read_bytes()).hexdigest() == sha
    verdict = "BITES" if (rc0 == 0 and rc1 != 0 and rc2 == 0 and restored and "Ran 0 tests" not in s0) else "FINDING"
    if verdict != "BITES":
        ok = False
    print(f"{link} {rel} test={test}\n  pristine rc={rc0} [{s0}]\n  mutant   rc={rc1} [{s1}]\n  restored rc={rc2} [{s2}] sha_restored={restored}\n  => {verdict}")
    if rc1 != 0:
        fail = [l for l in err1.splitlines() if l.startswith(("AssertionError", "FAIL:", "ERROR:"))][:3]
        print("  mutant failure: " + " / ".join(fail))
print("ALL_BITE" if ok else "SOME_FINDING")
sys.exit(0 if ok else 1)
