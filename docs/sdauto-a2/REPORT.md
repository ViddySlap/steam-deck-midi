# sdauto A2: agent API routes (engine config, OSC relay, MIDI ports, log tail)

Executor: claude-rc claude-opus-5 on the Mac, unsandboxed (Ben's fallback (b)). Branch chain/steamdeck-20260914. Scratch /tmp/sdauto-a2/. The laptop was NOT touched (A2 is Mac-only), so there is no guard compare and no browser listing.

Implementation commit: 0624f6a67787273e077e1c6ba68901016bd9a711 (pushed; `git ls-remote --heads origin chain/steamdeck-20260914` printed 0624f6a6...). This report, the tightened tests (section 5) and the evidence are committed on top of it; file:line references below are at 0624f6a; the report commit changes one comment line in windows/ui_server.py (ASCII, same line count) and no other file under windows/.

## 1. Route table

All six new routes refuse a non-loopback TCP peer with 403 before any work (`_remote_is_loopback`, windows/ui_server.py:164, the same check POST /api/shutdown now shares). Rows are in docs/api.md (inventory table plus the new section "Agent configuration routes").

| Route | 200 | Other status codes |
| --- | --- | --- |
| GET `/api/engines/<type_name>/config` (ui_server.py:933) | {type, source user/factory, path, user_files, spec, loaded, live_swappable, restart_required_reason} | 403 non-loopback; 404 no registry (--no-engines), unknown type, no stanza anywhere |
| PUT `/api/engines/<type_name>/config` (ui_server.py:940) | {ok, type, source "user", path, spec, active} | 403; 400 body not an object, type mismatch, or the class raised while built from the stanza; 404 as GET; 409 `restart_required` (7 types below, `enabled: false`, or type not loaded); 409 `config_file_conflict` (another user file declares the type); 503 no receiver loop (task not started within 5 s, cancelled, never runs); 500 write/build failure. Every refusal writes nothing. |
| GET `/api/osc-relay` (ui_server.py:950) | {path, config, load_error, running, stats} | 403; 404 --no-osc-relay |
| PUT `/api/osc-relay` (ui_server.py:958) | {ok, path, config, load_error, running, stats} | 403; 400 parse_osc_relay_config refusal (incl. destination == listen); 404 --no-osc-relay; 500 bind or write failure with the previous relay running again and the file unchanged |
| GET `/api/midi/ports` (ui_server.py:972) | {inputs, outputs, error, selected: {output, feedback, pulse: {requested, resolved}}} | 403; missing MIDI backend is 200 with null lists and `error` |
| GET `/api/logs/tail?lines=N` (ui_server.py:992) | {lines, count, log_file} | 403; 400 N not an ASCII integer 1..1000 (length <= 4); 503 no ring |

## 2. Swap mechanism (file:line)

- Receiver-thread path: new `ReceiverTaskQueue` (windows/receiver_tasks.py: `run` :45, `drain` :66). `serve_forever` takes `receiver_tasks` (windows/receiver.py:1010) and drains it at :1047-1050, immediately after the reload_event block, so a task runs between two datagrams exactly like a hot reload. A task not started within 5 s is cancelled under the lock and can never run later.
- Wiring: windows/win_recv.py:414 creates the queue; :436 passes it to MappingUIServer; :470 to serve_forever (tray and console both go through `_run_bridge_loop`).
- PUT flow, windows/engine_config_api.py `put_engine_config` :97: gates (404, 409 restart_required, 400 shape, 409 enabled false / conflict / not loaded, 503) -> isolation probe :128 (`build_engine` with a MidiOut that drops everything, no registry, no state dir; discarded WITHOUT shutdown because ptz_visca's shutdown sends VISCA stops) -> temp file written and fsynced in config/engines/ (suffix `.tmp`, never matched by the loader's `*.json`) -> `receiver_tasks.run(apply_on_receiver_thread)` :159.
- On the receiver thread (`apply_on_receiver_thread` :141): `current.flush_state()` :145 (new `Engine.flush_state`, windows/engines/base.py:89, no-op; autopilot :428 waits for its state writer so the replacement reads the last persisted intent) -> `os.replace(tmp, config/engines/<type>.json)` :147 -> build the new instance with the registry's real MidiOut and state dir (on failure the previous file bytes are restored, or the file removed, and the old instance is kept) -> `registry.replace(current, new)` :154 -> `new.set_active(active)` :155 (the preset-driven runtime flag, applied after bind as startup does).
- `EngineRegistry.replace` (windows/engines/registry.py:102): removes every note-emit filter whose `__self__` is the old instance via the new `remove_note_emit_filter` (:94), runs `old.shutdown()`, puts the new instance in the SAME list slot (dispatch order unchanged), then `new.bind_registry(self)`. `load_engines` records `user_dir`, `state_dir`, `midi_out` on the registry (:346) and now constructs through `build_engine` (:391), which is the same class lookup and kwargs as before. `effective_engine_spec` (:403) applies the loader's precedence for GET.
- The factory folder is never written (test asserts every factory file's sha256 unchanged).

Cost of the receiver-thread task (`.venv/bin/python -B docs/sdauto-a2/swap_cost.py`, 20 PUTs per type, loopback targets, REST refused instantly; result docs/sdauto-a2/swap_cost.json): p50 / max ms: audio_opacity 0.159 / 0.252, autopilot 0.264 / 0.413, autopilot_ptz 0.162 / 0.268, global_color 0.146 / 0.210, gyro_feedback 0.119 / 0.184, l_stick_layer 0.154 / 0.190, ptz_visca 0.238 / 0.292. NOT measured: a REST host that accepts but does not answer. autopilot's bind does one REST GET of the composition on the receiver thread, so in that case a PUT holds MIDI dispatch for up to `rest.timeout_seconds` (factory 1.5 s). Documented in docs/api.md. Windows cost: UNVERIFIED-BY-EXECUTION.

Behaviour after a swap equals a restart of that engine: bind runs (global_color sends its CC99 resync; autopilot re-reads the clip layout and replays restored intent on its first dispatch, A1 section 2), runtime state (cycle position, gyro polarity, held L-stick CC) starts fresh.

## 3. Live-swappable vs restart_required

Survey of all 14 engine classes (constructor, bind, shutdown, threads, cross references) by a read-only sub-agent, spot-checked by me at autopilot.py `bind_registry`/`shutdown`, osc_sync.py `shutdown` (join timeout 5.0), ptz_visca.py `set_active`/`shutdown`, global_color.py `bind_registry`.

Live-swappable (`LIVE_SWAPPABLE_TYPES`, engine_config_api.py:29): audio_opacity, autopilot, autopilot_ptz, global_color, gyro_feedback, l_stick_layer, ptz_visca. None starts a thread at construction (autopilot's writer only with a state dir, joined by shutdown), none binds a fixed port (ptz_visca's VISCA socket is port 0), none is referenced by another engine.

409 `restart_required` (`RESTART_REQUIRED_REASONS`, :39, same list in docs/api.md):

| Type | Why |
| --- | --- |
| steam_input_layer_tracker | bumper_blast, chaser_stack_dispatcher, flash_blast hold the instance; observer list has no unregister |
| bumper_blast, chaser_stack_dispatcher, flash_blast | each adds an observer to the tracker that cannot be unregistered, so the old instance would keep receiving layer changes |
| nestdrop | shutdown does not join in-flight per-press threads that take a process-wide lock |
| osc_sync | shutdown joins a running sync pass for up to 5 s on the receiver thread while the pass holds composition master at 0 |
| stageflow_bridge | shutdown is `pass`; OSC socket and rescan thread outlive the swap |

`test_every_engine_type_is_classified_exactly_once` fails if a new engine type is registered without a decision. Also refused with 409 (write nothing): `enabled: false` (would unload), a type that is not loaded, and a type declared by a user file other than `<type>.json`.

## 4. OSC relay, MIDI ports, log ring, Resolume defaults

- `OscRelayController` (windows/osc_relay.py:317), `apply` :355: parse (400 on error) -> temp file -> old relay shutdown -> new `OscRelay` on the requested listen address -> on `start()` False, `_restore` (:402) starts a fresh relay on the previous config and the temp file is discarded -> `os.replace` only after the new relay runs (on a write failure the new relay is stopped and the previous restored). `OscRelay.start` now records `last_error` (:206) for the 500 message. win_recv builds the controller whenever the relay is not disabled by flag (:410), including a missing or invalid file, and its shutdown replaces `osc_relay.shutdown()` in both teardown blocks, so a relay started by PUT is stopped at exit.
- MIDI ports: `get_port_snapshot()` names only; `requested` is argv (`--midi-port`, `--feedback-port`, `--pulse-port` or null with --no-pulse), `resolved` is the name of the port the bridge opened (null when not opened).
- Log ring: windows/log_ring.py, `RingLogHandler` deque(maxlen=1000), format `%(asctime)s %(levelname)s %(name)s %(message)s`, no stream, no file. Installed on the root logger at win_recv.py:209, right after `basicConfig` (installing before it would suppress basicConfig's console handler) and before tray mode's `setup_log_tee` (which strips only StreamHandlers). Tray mode returns the path from `setup_log_tee()` (:235).
- 5b: suffix pinned by construction from base 70cebd0 (`git show 70cebd0:windows/engines/osc_sync.py` line 101, `stageflow_bridge.py` lines 147-148, `config/engines.factory/osc_sync.json` line 5): osc_sync `OneDrive/Documents/Resolume Arena/Shortcuts/OSC/STEAMDECK V2.xml`; stageflow_bridge `OneDrive/Documents/Resolume Arena/Compositions/5-5-26 STEAMDECK V2.avc`. `default_osc_preset_path()` (osc_sync.py:68) and `default_comp_path()` (stageflow_bridge.py:67) return `Path.home()` joined with those parts; an explicit config value wins (osc_sync.py:112, stageflow_bridge.py:154). Factory choice: the key is OMITTED from config/engines.factory/osc_sync.json, because the installer overwrites that file and a home-relative form would need new loader expansion semantics; omission reaches the same code default with no new syntax.

## 5. Tests and revert proof

New modules (36 tests at the implementation commit; one test tightened and one assertion added after the first sweep, see below):

- tests/test_engine_config_api.py (14): remove_note_emit_filter; replace order (filter gone before shutdown, same slot, bind, dispatch order); classification covers every type once; GET factory then user source; PUT happy path asserts the file on disk, factory sha256s unchanged, the registry holds a new AutopilotEngine with the new update_hz; the swap runs on the draining thread; the replaced autopilot's filter is gone (a spy on `_note_emit_filter` records that `should_emit_note` consults only the new instance, and the registry's filter list is exactly `[new]`); active flag carried; invalid input (bad update_hz, non-object, type mismatch, enabled false, unknown type, osc_sync) writes nothing (sha256 unchanged, instance unchanged); restart_required types answer the exact reason with a LOADED tracker; conflicting user file; no receiver loop -> 503 and the cancelled task never runs; receiver-thread build failure restores the file; SWAP TEST: handle_datagram for 192 datagrams on one thread while PUT swaps autopilot from the HTTP thread, no exception, no ERROR log under `windows`, swap landed mid-traffic, recorded MIDI (192 events, asserted non-empty) equals the run without the PUT.
- tests/test_receiver_tasks.py (3): result from the draining thread and exception propagation; cancellation; the real `serve_forever` on a loopback UDP socket runs a queued task on its own thread.
- tests/test_agent_routes.py (14 + 1 assertion): relay GET; PUT writes the file, replaces the relay and a datagram through the relay reaches the new loopback sink and not the old; invalid config 400 with file sha256 and relay object unchanged and still forwarding; bind failure on a held port 500, previous relay running and forwarding, file unchanged, no temp left; 404 when disabled; MIDI ports with a fake `mido` module whose open_input/open_output/open_ioport record calls: zero opens; log tail newest-200 default, 1000 cap, memory bound, format, 400s, tray log path, no file created; 403 for all six routes from four non-loopback addresses with X-Forwarded-For 127.0.0.1 and zero calls on the registry, relay controller, ring and port snapshot; win_recv wiring (fake serve_forever): the same queue reaches the UI server and serve_forever, the ring is on the root logger and holds a line logged during main, requested/resolved ports, relay PUT through main's controller, and main's teardown stops that relay; tray mode returns the tee path; --no-osc-relay leaves the route 404.
- tests/test_resolume_home_defaults.py (5): HOME and USERPROFILE patched to a temp dir, a config missing the key resolves under it and `relative_to(home).as_posix()` equals the pinned suffix; explicit values verbatim; `USERNAME` absent from both modules and the factory file lacks the key; the real-user-home detector fires on a planted `c:\users\<name>\` path and not on `C:/Users/Benedict/` or another user; tracked files outside docs/ and scripts/ (more than 100 files, asserted) hold no match.

Revert proof: `.venv/bin/python -B docs/sdauto-a2/mutant_sweep.py` (22 one-site mutants, each in a fresh scratch copy of windows/, tests/, config/, protocol/, docs/api.md, running only the named test modules). Result: exit 0, `SWEEP GREEN`, rows in docs/sdauto-a2/mutant_sweep.json. M0 clean: exit 0, Ran 114, OK (skipped=1, the git-tree test, since the copy is not a checkout).

| Mutant | Result (failing tests) |
| --- | --- |
| M1 serve_forever does not drain | RED: serve_forever_runs_queued_tasks_on_its_own_thread |
| M2 PUT applies on the HTTP thread | RED: swap_runs_on_the_receiver_thread, no_receiver_loop... |
| M3 replace keeps old filters | RED: replace_removes_filters..., replaced_autopilot_filter_is_gone |
| M4 new engine appended, not slotted | RED: 2 |
| M5 replace skips old.shutdown() | RED: 1 |
| M6 active flag not carried | RED: 1 |
| M7 no isolation probe | RED: invalid_input..., build_failure... |
| M8 restart_required gate removed | RED: restart_required_types_answer_409 (SURVIVED the first sweep: the 409 came from "not loaded"; the test now loads a tracker and asserts the exact reason) |
| M9 no file restore on build failure | RED: 1 |
| M10 swap emits one MIDI CC (equality detector must fire) | RED: recorded_midi_equals_a_run_without_the_put |
| M11 relay bind failure not restored | RED: 1 |
| M12 relay file replaced before start | RED: 3 |
| M13 ports route opens an input | RED: 1 |
| M14 ring not installed by win_recv | RED: 2 |
| M15 log tail not loopback-only | RED: 1 |
| M16 ring memory unbounded | RED: 1 (the memory-bound assertion was added after I saw the reply cap alone would not catch it) |
| M17 lines upper bound 100000 | RED: 1 |
| M18 osc_sync placeholder default back | RED: 2 |
| M19 stageflow default ignores home | RED: 1 |
| M20 factory key re-added | RED: 1 |
| M21 docs/api.md row removed | RED: test_api_inventory_matches_registered_method_paths (the "fails when a row is removed" proof) |
| M22 serve_forever gets no task queue | RED: 1 |

Existing tests: no assertion changed. test_api_inventory_matches_registered_method_paths failed on the uncommitted code until the docs rows were added (run1 log: 944 tests, failures=1, only that test), then passed.

## 6. Instruments

Engine A/B (`.venv/bin/python -B scripts/showready/engine_ab.py --candidate 0624f6a67787273e077e1c6ba68901016bd9a711 ... --scratch /tmp/sdauto-a2/engine-ab/sN --out ...`, instrument sha256 b9b57438... as pinned; results copied to docs/sdauto-a2/engine-ab/):

| Preset | Exit | Result |
| --- | --- | --- |
| mac EDM Show --section windows | 0 | passed; A = B_nostate = B_state, events sha256 3dd96b189403... (identical to A1), filter decisions identical |
| windows-installed EDM Show | 0 | passed; 3dd96b189403... |
| mac PTZ --section windows | 0 | passed; e47e235d148b... (identical to A1) |
| windows-installed PTZ | 0 | passed; e47e235d148b... |
| mac EDM --control sensitivity-autopilot | 1 | control_expected true; different_sources [autopilot, receiver]; filter decisions differ |
| mac EDM --control sensitivity-l_stick_layer | 1 | control_expected true; different_sources [l_stick_layer], first difference bf7600 vs bf7700 |

engine_ab exercises engine output with no PUT; the live swap's effect on MIDI is covered by the swap test (section 5) only.

## 7. Bar 1 (Mac) and a live-bridge HTTP check

Script: `.venv/bin/python -B scripts/showready/deck_script.py --out /tmp/sdauto-a2/w3/deck-script.json` (exit 0; script_sha256 9256621abf62..., 732 steps, 47,039 packets, 469.7 s; same script sha as A1).

Both runs in a private tmux server (`tmux -L sdauto-a2`), sequential, 13:04:15-13:20:01 MDT, runner /tmp/sdauto-a2/w3/bar1.sh:

| Command (`.venv/bin/python -B scripts/showready/ab_run.py --candidate 0624f6a67787273e077e1c6ba68901016bd9a711 --section windows --script /tmp/sdauto-a2/w3/deck-script.json ...`) | Exit | Result |
| --- | --- | --- |
| `--preset '.showready/fixtures/mac/presets/EDM Show.json' --scratch /tmp/sdauto-a2/w3/scratch-edm --out /tmp/sdauto-a2/w3/mac-edm.json` | 0 | passed; B1 and B2 each 732 steps, 56 of 56 mappings exercised, 1,531 messages on A and B, different_mappings [], unexercised []; quiescent true; result .gz sha256 bc674479b638... |
| `--preset '.showready/fixtures/mac/presets/PTZ.json' --scratch /tmp/sdauto-a2/w3/scratch-ptz --out /tmp/sdauto-a2/w3/mac-ptz.json` | 0 | passed; B1 and B2 each 732 steps, 52 of 52 mappings exercised, 1,395 messages on A and B, different_mappings [], unexercised []; quiescent true; result .gz sha256 5a86d658febd... |

Afterwards `pgrep -fl "capture_runner|ab_run|engine_ab|win_recv"` exit 1 (none) and `tmux -L sdauto-a2 ls` reports no server. Bar 1 runs the bridge with `--no-engines --no-osc-relay --no-ui`, so it measures the receiver path including the new per-loop `drain()` of an empty queue and the ring handler, not the routes. Windows bar 1: OWED TO THE GATE.

Live bridge over real HTTP (`.venv/bin/python -B docs/sdauto-a2/e2e_http.py --out /tmp/sdauto-a2/e2e`, exit 0, `E2E PASSED`; evidence docs/sdauto-a2/e2e/e2e.json and bridge-log.txt, the bridge stdout/stderr renamed because `bridge.log` is git-ignored): scratch copy of the config tree with every engine host, IP, port and base_url rewritten to loopback (the script refuses to start if any non-loopback IPv4 literal remains; the repo's osc_relay.json is NOT copied, a loopback one is written), `python -m windows.win_recv --dry-run --no-pulse`, engines ON (14 loaded), non-default --listen and --ui-port, PYSTRAY_BACKEND=dummy, BROWSER=/usr/bin/true. Steps, all OK: GET autopilot config (factory, loaded); PUT update_hz 20 -> 200 and engines/autopilot.json equals the body; GET -> source user, 20; PUT osc_sync -> 409 restart_required, no file; PUT update_hz "fast" -> 400, file unchanged; GET osc-relay running; PUT osc-relay to a loopback sink -> 200, file equals body, one datagram sent to the relay listen port arrived at the sink; GET midi ports (names from CoreMIDI, pulse requested/resolved null); GET logs tail 41 lines incl. "mapping UI available", log_file null; lines=0 -> 400; POST /api/shutdown 202; process exit 0; `ps -p <pid>` exit 1. The bridge log shows a second autopilot clip-cache REST attempt after the PUT (the live swap's bind) and no traceback except `Exception in thread tray: NotImplementedError` from pystray's dummy backend on the non-tray ReceiverTray thread: PRE-EXISTING (the F5 path this lap fixes elsewhere), not from this change.

## 8. Suite

| Command | Result |
| --- | --- |
| first run on the uncommitted change, before the docs rows: `TMPDIR=/tmp/sdauto-a2/suite PYSTRAY_BACKEND=dummy BROWSER=/usr/bin/true .venv/bin/python -B -m unittest discover -s tests -p 'test_*.py'` | exit 1, Ran 944, failures=1 (test_api_inventory_matches_registered_method_paths only) |
| lane MAC SUITE exactly at 0624f6a (`.venv/bin/python -m unittest discover -s tests -p "test_*.py"`) | exit 0, `Ran 980 tests in 19.661s`, `OK (skipped=2)` |
| lane MAC SUITE exactly on the report-commit tree (tightened tests, ASCII comment) | exit 0, `Ran 980 tests in 19.535s`, `OK (skipped=2)`; the four node checks exit 0 again; mutant sweep re-run exit 0 SWEEP GREEN |
| `node tests/ui_controller_check.cjs` | exit 0, PASS |
| `node tests/ui_controller_macro_check.cjs` | exit 0, 48 disk writes match, 72 refused |
| `node tests/ui_reload_check.cjs` | exit 0, PASS |
| `node tests/ui_sections_check.cjs` | exit 0, PASS |
| `node tests/ui_controller_geometry.cjs` (no args) | exit 2, usage. PRE-EXISTING (needs a live URL and Chromium); no UI file changed in A2 |
| `shasum -a 256 -c scripts/showready/SHA256SUMS` | exit 0; no instrument changed |

980 = 944 + 14 (test_engine_config_api) + 3 (test_receiver_tasks) + 14 (test_agent_routes) + 5 (test_resolume_home_defaults). `git status --porcelain` empty after each commit.

## 9. Owed and notes for the next link

- OWED TO THE GATE: bar 2 (Windows suite; the held-port relay test uses SO_EXCLUSIVEADDRUSE on Windows, UNVERIFIED-BY-EXECUTION), bar 3 timing (the ring handler formats each INFO+ record and serve_forever checks an empty queue each loop; not measured by this link), Windows bar 1, and the live-bridge HTTP check on Windows (done on the Mac only, section 7). No UI affordance was added, so there is nothing for a browser to check.
- NOT DONE by design: `enabled: false` and adding a not-loaded engine return 409; osc_sync's `osc_preset_path` therefore cannot be changed live (osc_sync is restart_required).
- For the master (not stop-the-line): the Windows real-user home path this item forbids already exists in tracked files committed by earlier links: 217 under docs/ (lane evidence) and 3 under scripts/showready/ (README.md, win_guard.ps1, win_rail.sh: the pinned rail and guard name the laptop work root). Command: `git grep -l -i -E` with the test's pattern, counted by top-level dir, 13:11 MDT. Removing them would re-pin instruments and rewrite evidence, outside this item. The new tree test therefore excludes docs/ and scripts/ and covers every other tracked file (windows/, config/, installer/, tests/, mac/, notes/ ...). This report avoids the literal.
- The isolation probe is discarded without shutdown; its OSC socket closes on garbage collection (a ResourceWarning line in test output, not a failure). OscRelay.start's socket on a bind failure is left to GC as before this change.
- A1's sweep was not re-run; `load_engines` now builds through `build_engine` with the same class and kwargs (tests/test_autopilot_state.py passes in the full suite).
- Any instrument that loads factory ptz_visca must rewrite `camera_nic_ip`, `cameras` and `visca_port`, not only `osc`/`rest` (docs/sdauto-a2/swap_cost.py refuses to run if a non-loopback IPv4 literal remains).
