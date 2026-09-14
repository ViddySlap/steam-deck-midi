"""S4 regression controls in a scratch copy, with pristine/restored gates."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = Path("/tmp/sdcore-s4/reversions")
SCRATCH.mkdir(parents=True, exist_ok=True)
COPY = Path(tempfile.mkdtemp(dir=SCRATCH, prefix="source-"))
for folder in ("deck", "protocol", "tests"):
    shutil.copytree(ROOT / folder, COPY / folder, ignore=shutil.ignore_patterns("__pycache__"))
ENV = {**os.environ, "TMPDIR": str(SCRATCH), "PYTHONDONTWRITEBYTECODE": "1"}
MODULES = ["tests.test_deck_transport", "tests.test_deck_local_config",
           "tests.test_deck_fanout_launch", "tests.test_deck_sender", "tests.test_learn_wizard"]
COMMAND = [sys.executable, "-B", "-m", "unittest", *MODULES]
TRANSPORT = "deck/transport.py"
CONFIG = "deck/local_config.py"
LAUNCH = "deck/launch_send.py"
SENDER = "deck/xinput_send.py"
originals = {p: (COPY / p).read_text() for p in (TRANSPORT, CONFIG, LAUNCH, SENDER)}


def case(module, name):
    return [sys.executable, "-B", "-m", "unittest", "tests." + module + "." + name]


def transport(name):
    return case("test_deck_transport", "DeckTransportTests." + name)


def config(name):
    return case("test_deck_local_config", "ActiveTargetsTests." + name)


def launch(name):
    return case("test_deck_fanout_launch", "DeckFanoutLaunchTests." + name)


controls = [
    ("fanout-first-only", TRANSPORT, "for receiver in targets:", "for receiver in targets[:1]:",
     transport("test_action_identical_bytes_and_seq_in_target_order")),
    ("fanout-two-only", TRANSPORT, "for receiver in targets:", "for receiver in targets[:2]:",
     transport("test_fanout_has_no_two_target_limit")),
    ("fanout-reversed", TRANSPORT, "for receiver in targets:", "for receiver in reversed(targets):",
     transport("test_action_identical_bytes_and_seq_in_target_order")),
    ("send-error-stops-later", TRANSPORT, '            last_error = _last_error_at.get(receiver)',
     '            return\n            last_error = _last_error_at.get(receiver)',
     transport("test_send_failure_does_not_block_later_target_for_any_event")),
    ("error-rate-limit-missing", TRANSPORT,
     "if last_error is None or now - last_error >= ERROR_LOG_INTERVAL_SECONDS:", "if True:",
     transport("test_errors_are_rate_limited_per_target_across_event_types")),
    ("error-rate-limit-too-long", TRANSPORT, "ERROR_LOG_INTERVAL_SECONDS = 30.0", "ERROR_LOG_INTERVAL_SECONDS = 31.0",
     transport("test_errors_are_rate_limited_per_target_across_event_types")),
    ("dns-cache-never-refreshes", TRANSPORT, "now >= cached[0]", "False",
     transport("test_hostname_resolves_on_send_and_refreshes_at_60_seconds")),
    ("dns-no-cache", TRANSPORT, "cached is None or now >= cached[0]", "True",
     transport("test_hostname_resolves_on_send_and_refreshes_at_60_seconds")),
    ("dns-failure-not-cached", TRANSPORT, "        _address_cache[target] = cached",
     "        if not isinstance(address, OSError):\n            _address_cache[target] = cached",
     transport("test_dns_failure_is_cached_and_does_not_block_then_recovers")),
    ("parse-first-only", TRANSPORT, 'value.split(",")', 'value.split(",")[:1]',
     transport("test_parse_comma_separated_targets_and_legacy_single")),
    ("axis-does-not-send", TRANSPORT, "    _send_payload(sock, target, payload)\n\n\ndef send_heartbeat",
     "    pass\n\n\ndef send_heartbeat", transport("test_axis_fans_out")),
    ("heartbeat-single-only", TRANSPORT,
     "    payload = encode_heartbeat_event(",
     "    target = target[:1]\n    payload = encode_heartbeat_event(",
     transport("test_heartbeat_fans_out")),
    ("eager-xi-load", SENDER, "_LIB_XI = None", '_LIB_XI = _load_library("Xi")',
     transport("test_sender_and_wizard_import_without_loading_shared_libraries")),
    ("lazy-load-omitted", SENDER, "        _ensure_x11_libraries()", "        pass",
     launch("test_native_libraries_loaded_on_listener_open_and_cached")),
    ("sender-discards-list", SENDER, "list(targets) if targets is not None", "list(targets[:1]) if targets is not None",
     launch("test_actual_sender_loop_all_events_share_seq_across_targets")),
    ("sender-seq-advances-per-host", SENDER, "seq += 1", "seq += len(resolved_targets)",
     launch("test_actual_sender_loop_all_events_share_seq_across_targets")),
    ("cli-new-spelling-omitted", SENDER, '"--targets", "--target",', '"--target",',
     launch("test_both_cli_spellings_reach_run_sender")),
    ("config-legacy-default-missing", CONFIG, 'raw.get("active_targets", [])', 'raw["active_targets"]',
     config("test_legacy_defaults_to_empty_without_rewriting_existing_file")),
    ("config-selection-not-persisted", CONFIG, '"active_targets": settings.active_targets,', '"active_targets": [],',
     config("test_round_trip_preserves_order_and_uses_atomic_replace")),
    ("config-unknown-accepted", CONFIG, "if matches != 1:", "if False:",
     config("test_unknown_repeated_and_malformed_names_refused_on_load_and_write")),
    ("config-repeated-accepted", CONFIG, "if len(names) != len(set(names)):", "if False:",
     config("test_unknown_repeated_and_malformed_names_refused_on_load_and_write")),
    ("config-replace-omitted", CONFIG, "    os.replace(temp_path, path)", "    pass",
     config("test_round_trip_preserves_order_and_uses_atomic_replace")),
    ("hostnames-rejected", CONFIG, "normalized_host = validate_target_host(host)",
     "normalized_host = validate_ipv4_address(host)", config("test_hostnames_accepted_by_add_and_loader")),
    ("host-invalid-accepted", CONFIG, '        raise ValueError(f"invalid IPv4 address or hostname: {value}")',
     "        pass", config("test_invalid_host_characters_and_ipv4_refused")),
    ("config-active-lost-other-edits", CONFIG, "active_targets=settings.active_targets,", "active_targets=[],",
     config("test_other_settings_edits_preserve_selection")),
    ("config-rename-loses-active", CONFIG,
     "active_targets=[normalized if name == settings.presets[index].name else name\n                        for name in settings.active_targets],",
     "active_targets=[],", config("test_rename_and_delete_keep_active_names_valid_on_disk")),
    ("config-delete-loses-survivor", CONFIG,
     "active_targets=[name for name in settings.active_targets\n                        if name != settings.presets[index].name],",
     "active_targets=[],", config("test_rename_and_delete_keep_active_names_valid_on_disk")),
    ("config-duplicate-add-accepted", CONFIG, "if any(preset.name == normalized_name for preset in settings.presets):",
     "if False:", config("test_new_duplicate_names_refused")),
    ("active-marker-omitted", CONFIG, 'marker = " [active]" if active else ""', 'marker = ""',
     config("test_describe_preset_marks_active")),
    ("menu-toggle-off-omitted", LAUNCH, "            names.remove(name)", "            pass",
     launch("test_empty_saved_selection_returns_to_single_menu")),
    ("menu-toggle-on-omitted", LAUNCH, "            names.append(name)", "            pass",
     launch("test_toggle_save_start_and_relaunch_use_all_saved_hosts")),
    ("menu-only-first-host", LAUNCH, "targets = [(p.host, p.port) for p in selected]",
     "targets = [(p.host, p.port) for p in selected[:1]]",
     launch("test_toggle_save_start_and_relaunch_use_all_saved_hosts")),
    ("menu-single-retains-set", LAUNCH, "settings = with_active_targets(settings, [])",
     "settings = settings", launch("test_single_selection_clears_previous_multi_selection")),
]
results = []


def run(name, cmd, red=False):
    proc = subprocess.run(cmd, cwd=COPY, env=ENV, capture_output=True, text=True, timeout=30)
    output = proc.stdout + proc.stderr
    (SCRATCH / (name + ".log")).write_text(output)
    passed = proc.returncode != 0 if red else proc.returncode == 0
    if red and any(error in output for error in ("SyntaxError:", "IndentationError:", "ModuleNotFoundError:")):
        passed = False
    result = {"name": name, "expected": "RED" if red else "GREEN",
              "exit": proc.returncode, "passed": passed}
    results.append(result)
    print(json.dumps(result), flush=True)
    if not passed:
        raise SystemExit("Unexpected control result: " + name)


run("pristine", COMMAND)
for name, path, before, after, cmd in controls:
    source = originals[path]
    assert before in source, name
    try:
        (COPY / path).write_text(source.replace(before, after))
        run(name, cmd, red=True)
    finally:
        (COPY / path).write_text(source)
run("restored", COMMAND)
(SCRATCH / "results.json").write_text(json.dumps(results, indent=2) + "\n")
print(f"{len(controls)} regressions caught; pristine and restored checks green")
