BASE OF LAP 70cebd0b6baed2ece86a2d218843e02b6298789d

# sdauto A1: autopilot channel state survives a bridge restart

Executor: claude-rc claude-opus-5 on the Mac, unsandboxed (Ben's fallback (b)). Branch chain/steamdeck-20260914. Scratch /tmp/sdauto-a1/ and /tmp/sdauto-engine-ab/. The laptop was NOT touched (A1 is Mac-only), so there is no guard compare and no browser listing.

Implementation commit: 6b69bb77693c33f1d0481ce7ec5b4d4afe40da9b (pushed; `git ls-remote --heads origin chain/steamdeck-20260914` = 6b69bb77...). This report and its evidence are committed on top of it.

## 1. Fields persisted

File `config/state/autopilot_channels.local.json` (git-ignored; `.gitignore` line `config/state/`). Schema 1, keyed by engine instance name, then channel key:

| Field | On disk |
| --- | --- |
| enabled | boolean |
| beats_per_clip | integer (looked-up beats) |
| transition_seconds | number (seconds) |
| clip_mode | NAME (`NONE`/`LINEAR`/`RANDOM`) |
| layer_enabled | object, string layer keys -> boolean |

Never stored: cycle_index, beat_in_clip, visible_layer, target_layer, crossfade_start_time, bag, last_clip, clip_count_cache (asserted absent from the JSON on disk by `test_file_on_disk_has_schema_names_and_no_runtime_fields`). Rationale and clear instructions: docs/autopilot-state.md.

Setters found with `grep` for the five fields in windows/engines/autopilot.py: only `on_midi_in` (enable, beats, transition, mode, layer branches) plus the new `clear_intent`. Each value-changing branch calls `_persist_intent()` (autopilot.py:327 enable, :335 beats, :341 transition, :353 mode, :369 layer; :610 clear). A CC that does not change the value writes nothing (`test_no_change_means_no_write`).

Write path: `_persist_intent` (autopilot.py:574) builds the snapshot under a lock and calls `AutopilotStateWriter.submit` (autopilot_state.py:140), which only stores it and wakes a daemon writer thread. `_write` (autopilot_state.py:201): temp file in the same dir, fsync, `os.replace`. No debounce timer: the writer always writes the newest snapshot, so rapid changes coalesce. `shutdown` (autopilot.py:428) calls `close`, which waits for the last submitted snapshot. Failures are logged at most once per `FAILURE_LOG_INTERVAL_SECONDS` = 60 (autopilot_state.py:36, :220) and never raise into on_midi_in.

Debounce proof (the item allows coalescing only with this): `test_last_change_before_teardown_is_on_disk_even_with_a_slow_disk` sends 128 transition CCs with fsync slowed to 50 ms each, calls shutdown, and reads the final value (5.0 s) from the file.

Cost on the receiver thread (`.venv/bin/python -B docs/sdauto-a1/on_midi_in_cost.py`, 20,000 value-changing transition CCs, measured while the bar 1 A/B was running): on_midi_in p50 0.75 us / p99 1.71 us without a state dir, 2.54 us / 3.58 us with one; shutdown flush 0.52 ms. Only autopilot-channel CCs that change intent pay this. Windows cost: UNVERIFIED-BY-EXECUTION.

## 2. Restore

`_init_persistence` (autopilot.py:483) creates the writer and calls `_restore_intent` (autopilot.py:488): persisted fields overlay the config-built states for channels and layers still in config. Unknown channels and layers are ignored and logged in ONE warning. `read_state_file` (autopilot_state.py:82) raises `StateFileInvalid` for bad JSON, a wrong type, a missing field, or schema != 1; the engine then keeps defaults and the file stays byte-identical until the next valid change (tests: malformed, future schema, wrong field type).

Side effects: `_apply_restored_intent` (autopilot.py:542) runs on the engine's FIRST dispatch (top of on_midi_in :315, on_midi_clock :373, tick :404), in config channel order: `_apply_transition` (the transition branch's code, now shared, autopilot.py:477) pushes the restored transition to the selected layers, then `_apply_enable(ch, True)` (the enable branch's code, now shared, autopilot.py:468) runs `_snap_to_first_selected`. DEVIATION from "on construction", stated: the values are overlaid at construction (so the note-emit filter and GET /api/engines see them at once), but the Resolume writes wait for the first dispatch. Reason: load_engines constructs every engine before the preset's `apply_engine_states` runs, and the registry dispatches nothing to an inactive engine. Replaying at construction would make a PTZ preset (autopilot off) write layer masters at startup from an EDM show's saved state, which a live enable CC to an inactive engine never does. Mutant M3 (replay at construction) is RED on `test_inactive_engine_sends_nothing_until_active` and `test_restored_enable_matches_a_live_enable_cc`.

Equivalence: `test_restored_enable_matches_a_live_enable_cc` drives layers, beats, transition, mode and enable through real on_midi_in with the factory CC numbers, restarts, ticks once, and requires the restored engine's recorded OSC list to equal the live engine's (non-empty), then defers note 82 through `registry.should_emit_note` in both and requires identical MIDI (`note_on 0 82 127`) and runtime fields after the beat.

## 3. state_dir plumbing (file:line at 6b69bb7)

- windows/win_recv.py:345 `load_engines(engines_path, midi_out)`: unchanged; takes the default.
- windows/engines/registry.py:233-238 `load_engines(config_path, midi_out, *, state_dir=_DERIVE_STATE_DIR)`; :294-295 default `user_dir.parent / "state"` (config/state beside config/engines); :296-305 a state dir equal to or inside the engines dir is refused and persistence disabled; :323-327 passes `state_dir` only to classes with `accepts_state_dir`.
- windows/engines/autopilot.py:137 `accepts_state_dir = True`; :149 `state_dir` kwarg; :293-294 `_init_persistence`.
- Installed Windows path: `C:\Program Files\STEAMDECK MIDI Receiver 2\config\state\`; installer/windows/steamdeck-midi-receiver-2.iss:40 grants users-modify on `{app}\config`, so the bridge can create `state\`. UNVERIFIED-BY-EXECUTION on Windows: OWED TO THE GATE (or a later laptop link) to observe the file appear after a CC.

## 4. Route

GET /api/engines already carried the five fields per channel in `AutopilotEngine.status()` (clip_mode by name, layer keys as strings); `test_get_engines_reports_the_five_fields_per_channel` pins it. New `POST /api/engines/autopilot/state/clear` (windows/ui_server.py:897) calls `clear_intent` (autopilot.py:584): resets the five fields to config defaults with the same runtime rules as the equivalent CCs, persists, flushes, returns `{"ok": true, "persisted": bool, "channels": {...}}`; 404 when autopilot is not loaded. docs/api.md row added; `test_api_inventory_matches_registered_method_paths` is green with it.

## 5. Revert proof and mutant sweep

Command: `.venv/bin/python -B docs/sdauto-a1/mutant_sweep.py` (copy of /tmp/sdauto-a1/mutants/sweep.py). Each mutant is a one-site edit in a fresh scratch copy of the run root, then `python -B -m unittest tests.test_autopilot_state` from that copy. Result at the committed code (windows/ and tests/ equal HEAD 6b69bb7): exit 0, `SWEEP GREEN`; full per-mutant rows in docs/sdauto-a1/mutant_sweep.json.

| Mutant | Result |
| --- | --- |
| M0 clean | exit 0, Ran 25, OK |
| M1 restore call commented out (`# self._restore_intent(path)`) | exit 1, failures=5: five_fields_survive_restart, restored_enable_matches_live, inactive_engine_sends_nothing_until_active, channel_and_layer_removed_ignored, explicit_state_dir_restores_across_two_loads |
| M2 no replay in tick | exit 1, failures=3 |
| M3 replay at construction | exit 1, failures=4 |
| M4 shutdown skips writer close | exit 1, failures=5 errors=9 |
| M5 transition change not persisted | exit 1, failures=2 errors=2 |
| M6 crossfade_start_time written | exit 1, failures=1 |
| M7 registry drops state_dir | exit 1, failures=1 errors=1 |
| M8 state dir inside engines dir allowed | exit 1, failures=1 |
| M9 write on calling thread, unguarded | exit 1, failures=3 errors=1 |
| M10 failure log not rate limited | exit 1, failures=1 |
| M11 invalid file rewritten at startup | exit 1, failures=4 |
| M12 clear route path changed | exit 1, failures=1 errors=1 |
| M13 unknown layer not ignored | exit 1, failures=1 |
| M14 future schema accepted | exit 1, failures=1 |
| M15 mode change not persisted | exit 1, errors=1 |
| M16 clear does not persist | exit 1, failures=1 |

M15 SURVIVED the first sweep (a mode change was only ever persisted by a later enable CC's snapshot); `test_each_field_change_alone_is_persisted` was added and M15 is now RED.

## 6. Engine A/B (scripts/showready/engine_ab.py)

In-process engines, one process per arm (both revisions are the `windows` package). Each arm: untouched `git archive`, that revision's own `load_engines` + `bind_registry`, the same five config stanzas (v0.4.9 factory configs, OSC/REST rewritten to loopback, audio_opacity protocol midi), active flags from the preset's `engines` block, fake OSC/REST, seeded RNG, byte recorder on the shared MidiOut, sockets and MIDI port opens refused and counted, fake time. The 3,219-step script calls the registry as windows/receiver.py does (feedback CCs, Deck CC `_emit_cc`, Deck notes through `should_emit_note`, note-offs including staged long-press modifier/trigger/off, axis events, clock start/stop/continue with the fallback clock taking over, ticks, refresh), with note and L4 numbers taken from the preset's mappings. Arms: A = v0.4.9 (e66ff44); B_nostate = candidate with `state_dir=None`; B_state = candidate with an empty `config/state/`.

Instrument sha256 b9b5743824137226e9f05007a9efe28503fa620808b614d7a9c22a2793f6f734 (pinned in SHA256SUMS). Candidate 6b69bb7. Results copied to docs/sdauto-a1/engine-ab/.

| Command (all `.venv/bin/python -B scripts/showready/engine_ab.py --candidate 6b69bb77...`) | Exit | Result |
| --- | --- | --- |
| `--preset '.showready/fixtures/mac/presets/EDM Show.json' --section windows` | 0 | passed; A = B_nostate = B_state, 2,106 events, events sha256 3dd96b189403...; filter decisions identical; 0 sockets, 0 ports; B_state wrote autopilot_channels.local.json |
| `--preset '.showready/fixtures/windows-installed/presets/EDM Show.json'` | 0 | passed; same 2,106 events, sha 3dd96b189403... |
| `--preset '.showready/fixtures/mac/presets/PTZ.json' --section windows` | 0 | passed; 96 events identical (e47e235d148b...); autopilot, l_stick_layer, audio_opacity silent; global_color only load/refresh resync; gyro_feedback 60 MIDI |
| `--preset '.showready/fixtures/windows-installed/presets/PTZ.json'` | 0 | passed; same as Mac PTZ |
| `... EDM Show --section windows --control sensitivity-autopilot` | 1 | control_expected true: both comparisons differ, different_sources [autopilot, receiver], filter decisions differ (2,225 vs 2,106 events) |
| `... EDM Show --section windows --control sensitivity-l_stick_layer` | 1 | control_expected true: different_sources [l_stick_layer] only; first difference bf7600 vs bf7700 |

Coverage (Mac EDM Show, identical on all three arms):

| Engine | MIDI | OSC | Input kinds that produced output |
| --- | --- | --- | --- |
| autopilot | 5 (re-emitted column notes) | 1,474 | clock, feedback_cc, tick; filter deferred-or-dropped 6, re-emitted 5, dropped 1 |
| l_stick_layer | 55 | 0 | axis, deck_note_on (L3 toggle) |
| gyro_feedback | 60 | 0 | axis, deck_cc (L4), tick (hold) |
| global_color | 3 (CC99 resync at bind and 2 refreshes) | 424 | load, feedback_cc, refresh, tick |
| audio_opacity | 58 | 0 | feedback_cc, tick |

Detector tests: tests/test_engine_ab.py (9 tests) plants a one-byte difference, a missing trailing event, a changed filter decision, zero observations per engine, an inactive engine that speaks, and an autopilot run with no drop: each RED; identical captures GREEN.

Development runs against a dangling working-tree commit (not the candidate) found and fixed two instrument gaps before the commit: no column note was ever dropped while one was pending (a drop case is now in the script and required), and the autopilot control's first expectation wrongly demanded `receiver` not differ.

## 7. Bar 1 (EDM Show, Mac)

Script: `.venv/bin/python -B scripts/showready/deck_script.py --out /tmp/sdauto-a1/w3/deck-script.json` (exit 0; script_sha256 9256621abf62..., 732 steps, 47,039 packets, 469.7 s).

Command: `.venv/bin/python -B scripts/showready/ab_run.py --candidate 6b69bb77693c33f1d0481ce7ec5b4d4afe40da9b --preset '.showready/fixtures/mac/presets/EDM Show.json' --section windows --script /tmp/sdauto-a1/w3/deck-script.json --scratch /tmp/sdauto-a1/w3/scratch --out /tmp/sdauto-a1/w3/mac-edm.json` run 12:36:42-12:44:36 MDT in a private tmux server: exit 0, `passed: true`. B1 and B2 each: 732 steps, 56 of 56 mappings exercised, 1,531 messages on A and on B, different_mappings [], unexercised_mappings []. Result /tmp/sdauto-a1/w3/mac-edm.json.gz sha256 39eb33884f35610c1382e27e261dd07bdf9213174316a4dbfd02353906bf74e9. Afterwards `pgrep -fl "capture_runner|ab_run|engine_ab"` exit 1 (none) and the tmux server is gone. Bar 1 runs `--no-engines`, so it is not sensitive to this change by construction; section 6 is the engine coverage. PTZ bar 1 and the Windows bar 1 were not run by this link (OWED TO THE GATE).

## 8. Suite

| Command | Result |
| --- | --- |
| baseline before any change: `TMPDIR=/tmp/sdauto-a1/suite PYSTRAY_BACKEND=dummy BROWSER=/usr/bin/true .venv/bin/python -B -m unittest discover -s tests -p 'test_*.py'` | exit 0, `Ran 910 tests`, `OK (skipped=2)` |
| same, at the committed code | exit 0, `Ran 944 tests in 15.218s`, `OK (skipped=2)` |
| lane MAC SUITE exactly (`.venv/bin/python -m unittest discover -s tests -p "test_*.py"`) | exit 0, `Ran 944 tests in 15.346s`, `OK (skipped=2)`; no __pycache__ appeared under scripts/showready |
| `node tests/ui_controller_check.cjs` | exit 0, PASS |
| `node tests/ui_controller_macro_check.cjs` | exit 0, 48 disk writes match, 72 refused |
| `node tests/ui_reload_check.cjs` | exit 0, PASS |
| `node tests/ui_sections_check.cjs` | exit 0, PASS |
| `node tests/ui_controller_geometry.cjs` (no args) | exit 2, usage. PRE-EXISTING: needs a live URL and Chromium (sdbar3 gate section 0); no UI file changed |
| `shasum -a 256 -c scripts/showready/SHA256SUMS` | exit 0 (re-pinned for engine_ab.py and README.md only) |

944 = 910 + 25 (tests/test_autopilot_state.py) + 9 (tests/test_engine_ab.py). No existing test assertion changed.

## 9. Bars 2 and 3

Bar 2 (suite on Windows) and bar 3 (timing with the controller view) were not run by this link: OWED TO THE GATE. Bar 3's instrument runs the bridge with engines off, so this change is outside what it measures; the receiver path (windows/receiver.py, windows/midi.py) is untouched.

## 10. autopilot_ptz (for a later lap)

Same hazard, not fixed here. windows/engines/autopilot_ptz.py:122-131 builds `_enabled`, `_beats_per_clip`, `_clip_mode` and `_cam_enabled` from config `defaults` on every construction (`enabled` defaults False); the only setters are on_midi_in :150-192 (enable :152-161, beats :163-169, mode :171-182, cam include :184-192). Nothing persists, so a restart mid-show stops camera cutting silently. It shares no ChannelState; the same writer (`AutopilotStateWriter`) and `accepts_state_dir` plumbing would carry it, with its own entry and restore replay rules (its enable edge resets `_beat_in_clip`, no OSC).

## 11. For the next link

- Push: plain `git push origin chain/steamdeck-20260914` failed here (`could not read Username for 'https://github.com'`); the SSH transport override worked.
- `load_engines` now takes `state_dir`; any instrument or test that loads engines from a real config tree will write `config/state/` beside it on the first autopilot intent CC. Pass `state_dir=None` where that must not happen.
- engine_ab.py needs the candidate COMMITTED (it archives a revision). Runs take about 2 s each on the Mac; scratch is about 170 MB per run (three archived trees).
- Windows: engine_ab.py has not been run on the laptop (UNVERIFIED-BY-EXECUTION); its default scratch there is `%LOCALAPPDATA%\Temp\sdwin\engine-ab`.
