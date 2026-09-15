BAR 3 RED (QUALIFYING clean3 under MASTER 13 15:21 (3), 15:53:01-16:12:36): HEAD a8fec2a, declared M_bridge rule, Mac + real Chromium R=5, all 15 arms VALID under the whole-machine cap (max in-arm load1 4.79, no non-lane process > 50% for > 10 s), fresh R=3 sensitivity 9/9 VALID and RED on M_bridge: M_bridge |OPEN - CLOSED| p50 0.181 / p95 1868.469 / p99 1197.269 ms against floor + 1.0 = 1.036 / 2.904 / 295.099 ms -> p95 and p99 FAIL; locked rule beside it also FAILS (p95 964.456 vs 208.392, p99 934.492 vs 419.909). Bytes identical. The failure is receiver-side stalls of about 3.5 s followed by a linear drain, and they hit CLOSED arms too, which have no client (clean3: stalls in r1 CLOSED-B and r5 CLOSED; in r1, r2 and r5 OPEN), in quiet machine samples; cause UNVERIFIED. Run 1 (14:57:57, RED p99 2.204 ms, 8/15 arms INVALID under (3)) and clean2 (15:19:03, DIAGNOSTIC, RED with 3.6-7.0 s stalls) are reported beside it in 7c.

LAPTOP GUARD: GREEN first (14:25:55 snapshot) and last (14:51:00 compare): `GUARD GREEN: compare; protected state observed; pythonProcesses=0`, exit 0.

BASE OF LAP 70cebd0b6baed2ece86a2d218843e02b6298789d (docs/sdauto-a1/REPORT.md line 1). Gate HEAD a8fec2ad635e141b0634dc9a51c5442dad9fd966 (A4), equal to origin at entry (`git ls-remote --heads origin chain/steamdeck-20260914`).

# sdauto AG - independent gate

Executor: claude-rc claude-opus-5 on the Mac, unsandboxed. Scratch /tmp/sdauto-gate/. Laptop work dir `sdwin\sdauto-gate`. Every step below was re-run by this gate, not read from a predecessor report, unless it says otherwise. Scripts are committed under docs/sdauto-gate/scripts/, evidence under docs/sdauto-gate/evidence/.

## Verdict in plain words

| Bar / step | Result |
| --- | --- |
| 0 Mac suite, node checks, pins | GREEN: 997 tests OK (skipped=2); 5 node checks exit 0; 16 pins OK |
| 1 Autopilot restart, real bridge | GREEN: five fields survive; restored transition push arrives with NO input 35.8 ms BEFORE the "engines loaded" line (first dispatch is the receiver's startup layer-state CC fan-out, not the tick); clear and corrupt-file behave |
| 2 New routes, real bridge | GREEN: 31/31 checks incl. only the NEW autopilot filter consulted after PUT (control: OLD one before) |
| 2b Resolume home defaults | GREEN for osc_sync (parses the file under HOME); stageflow_bridge resolves comp_path under HOME but never reads it at runtime (finding F4); `git grep -n "C:/Users/Ben"` is NOT empty (30 lines, 0 in product dirs; finding F2); laptop: installed suffix equal, file exists |
| 3 F5 and F2 on the Mac | GREEN: POST /api/shutdown 202 and exit 0 twice, no crash report, no Python window of any kind; F2 BASE 94.3% + SIGINT ignored, HEAD 0.3% + SIGINT exit 0 in 0.1 s; --no-browser 0 records, without it 1 |
| 4 F2 on Windows | GREEN: no spin at HEAD or v0.4.9 (<= 0.41% of one core); Ctrl-C exit 0 with MIDI panic at both when enabled; installed tray 1.198% of one core |
| 5 F4 and version in real Chromium | GREEN: 1440x900 header one row with Controller and with List (48 px; BASE 106 px, 3 rows); `v0.5.0 (source)`; GET /api/version 0.5.0 frozen false |
| 6 Mutations (a)-(f) | GREEN: all six RED, all restored GREEN |
| 7 Bar 1 | GREEN: EDM Show, PTZ, default byte-identical to v0.4.9 on the Mac AND on the laptop, independently re-checked from raw rows; seam below the wrapper 9,644 = 9,644, planted drop RED, dead seam RED |
| 7 engine_ab.py (Mac) | GREEN: 4 presets identical, both sensitivity controls RED. On Windows the instrument crashes (finding F5) |
| 7 Bar 2 Windows suite | GREEN: clone at HEAD, `Ran 997 tests`, `OK (skipped=6)`, exit 0 |
| 7 Bar 3 | **RED** on the qualifying clean3 (M_bridge p95 and p99; locked rule also RED), 15/15 arms VALID under (3); ~3.5 s receiver stalls in 2 CLOSED and 3 OPEN arms; run 1 RED and clean2 DIAGNOSTIC beside it (7c) |
| 8 Pick-up | Every link pushed, nothing excluded committed, Ben's files unchanged, all processes gone. config/engines.factory CHANGED by one intended line (A2 5b) |

## 0. Mac suite, node checks, pins (HEAD a8fec2a)

| Command | Result |
| --- | --- |
| `.venv/bin/python -m unittest discover -s tests -p "test_*.py"` | exit 0, `Ran 997 tests in 19.236s`, `OK (skipped=2)` |
| `node tests/ui_controller_check.cjs` | exit 0, `UI controller behavior: PASS (...)` |
| `node tests/ui_controller_macro_check.cjs` | exit 0, 48 disk writes match, 72 refused |
| `node tests/ui_reload_check.cjs` | exit 0, PASS |
| `node tests/ui_sections_check.cjs` | exit 0, PASS |
| `node tests/ui_version_check.cjs` | exit 0, `SUMMARY 29/29 PASS` |
| `tests/ui_controller_geometry.cjs` | not run: needs a live URL; PRE-EXISTING instrument defect (networkidle, sdlive-gate owed item); no geometry change in this lap beyond the header height, which A4 measured with geom_live 126/126 |
| `shasum -a 256 -c scripts/showready/SHA256SUMS` | exit 0, 16 OK |

## 1. Autopilot restart on a real bridge

Instrument: `.venv/bin/python -B docs/sdauto-gate/scripts/gate_bridge.py --out /tmp/sdauto-gate/s1/run` -> exit 0, `GATE BRIDGE PASSED 31 / 31` (evidence/bridge/gate_bridge.json, run.stdout, boot2.ring.txt, boot1..3-bridge-output.txt). The first run of the same script was 30/31: its no-input check wrongly required the push to come AFTER the "engines loaded" line; the push came 37.0 ms before it. The declared criterion is "no input, within 1 s", so the check was corrected to |delay| <= 1 s and the whole run repeated (second run numbers below). That was a defect in my check, not in the product.

Setup (all loopback, all mine):
- Scratch tree: `config/windows_midi_map.json`, `actions.yaml`, `macro_library.json`; the Mac fixture presets (EDM Show active, section `windows`); `config/engines.factory/*.json` AND Ben's `config/engines/*.json` copied with every `host`/`camera_nic_ip` -> 127.0.0.1, every integer `port`/`visca_port` -> a UDP listener I own (autopilot alone on its own listener, every other engine on a second one), every `base_url` -> a loopback HTTP stub I own, `cameras` -> 127.0.0.1, and `osc_preset_path`/`comp_path` removed (one occurrence: Ben's engines/osc_sync.json). A loopback osc_relay.json is written. Before boot the script greps every .json/.yaml in the copy for IPv4 literals other than 127.0.0.1, URLs and host values: zero (`PASS scratch engine configs name zero non-loopback addresses {"foreign": {}}`).
- Bridge: `hook_launch.py <control> -- --map <scratch> --preset-section windows --dry-run --no-pulse --no-browser --midi-port "IAC Driver DECK_IN" --feedback-port "IAC Driver DECK_OUT" --listen 127.0.0.1:<free> --ui-port <free>`, engines ON (14 loaded), PYSTRAY_BACKEND=dummy, BROWSER=/usr/bin/true, HOME and USERPROFILE = a scratch home. State dir = the scratch `config/state/` (the registry's derived default).
- Input path (stated, as asked): the DRY-RUN FEEDBACK PORT path. `hook_launch.py` replaces `DryRunMidiIn.poll_control_changes` (which returns [] in dry-run) with one that returns CCs queued over a loopback control socket, so each CC goes through the unchanged `receiver._drain_midi_feedback` -> `_handle_feedback_message` -> `registry.on_midi_in`. With nothing queued it returns [] like the original. The hook also observes (no product file changed): the registry reference, `AutopilotEngine._note_emit_filter` calls by instance id, and mido open_* calls.

Boot 1 sent 12 CCs on channel 14 (factory numbers): video layers 1,2 on (64,65=127), beats index 2 (61=2), transition 64 (62), mode LINEAR (63=1), enable (60=127); fx layer 5 on (74), beats index 4 (71), transition 127 (72), mode RANDOM (73=2), enable (70); logo layer 7 on (85). Hook delivered 12.

| Check | Observed | Result |
| --- | --- | --- |
| no state file before any CC | absent | PASS |
| GET /api/engines five fields after the CCs | video enabled, 8 beats, 2.51969 s, LINEAR, layers {1,2 on}; fx enabled, 32, 5.0 s, RANDOM, {5 on}; logo off, 16, 0.0, NONE, {7 on} | PASS (equal to the expected values computed from the config) |
| POST /api/shutdown | 202, exit 0, `ps -p` exit 1 | PASS |
| `config/state/autopilot_channels.local.json` | schema 1, engine "Autopilot", each channel has exactly enabled, beats_per_clip, transition_seconds, clip_mode, layer_enabled; none of the 8 runtime names appears anywhere in the file; values equal GET | PASS |
| Boot 2, NO UDP and NO MIDI sent (hook injected 0 CCs, gate sent 0 datagrams): first GET five fields | equal to boot 1 | PASS |
| runtime fields at the first GET | video visible_layer 1, target None, beat_in_clip 0, cycle_index 0; fx visible 5; logo visible None (logo not enabled) | fresh |
| restored push WITHOUT input | first autopilot datagram `/composition/layers/1/transition/duration` 0.251969 (= 2.51969 s / 10 s); then layer 2 0.251969, masters 1 = 1.0 and 2 = 0.0 (enable snap), fx layer 5 0.5, master 5 = 1.0, logo layer 7 0.0 | PASS |

The measurement (boot 2 of the passing run, same host clock: log ring `asctime` is `record.created` = time.time() at ms resolution; the listener stamps time.time(); offset 0):

| Event | Time |
| --- | --- |
| bridge spawned | 14:35:17.520 |
| `2026-09-15 14:35:17,589 INFO windows.engines.autopilot Autopilot: restored autopilot intent for video, fx, logo from .../config/state/autopilot_channels.local.json` | 14:35:17.589 |
| first restored transition push at the listener | 14:35:17.599 (10.2 ms after the restore line, 79.2 ms after spawn) |
| `2026-09-15 14:35:17,635 INFO windows.receiver engines loaded: Audio Engine(audio_opacity), Global Color(global_color), OSC Sync(osc_sync), Autopilot(autopilot), ...` | 14:35:17.635 |
| delay "engines loaded" -> first restored push | **-35.8 ms** (the push precedes the line; 10 autopilot datagrams arrived before it). First run: -37.0 ms |
| engine tick interval | 1 / update_hz 30 = 33.3 ms |

Declared before data: no input, within 1 s. HOLDS (|-35.8| ms). Why it precedes the line (code read, consistent with the ring order): `engines loaded` is logged inside `serve_forever` (windows/receiver.py:1030) after the UI server starts. Autopilot's first dispatch happens earlier, when `ActionReceiver.__init__` (receiver.py:169) calls `_publish_initial_layer_states` (:829) -> `_set_layer_state` (:778) -> `_publish_layer_state` (:802) -> `_emit_cc` (:212), which fans the startup layer-state CCs to `registry.on_midi_in`. That is a bridge-internal startup path present at v0.4.9, not external input, so A1's "first dispatch" replay fires at receiver construction. MASTER 12:47 expected the first tick; the push is earlier, not later. Not a finding against A1.

| Clear and corrupt | Observed | Result |
| --- | --- | --- |
| POST /api/engines/autopilot/state/clear (boot 2, after the routes) | 200, `persisted: true`; GET every channel enabled false, 16 beats, 0.0 s, NONE, all layers off; file equals the same | PASS |
| after boot 2 shutdown | file still defaults | PASS |
| boot 3 with the file replaced by 74 bytes of truncated JSON (sha256 c6051eb4...) | GET = defaults; exactly one `WARNING ... ignoring autopilot state file ... (not JSON: Expecting value: line 1 column 75 (char 74)); using config defaults` | PASS |
| file after boot 3 and shutdown | sha256 c6051eb4... unchanged, bytes equal | PASS |

## 2. New routes on the same real bridge (boot 2)

| Route / check | Observed | Result |
| --- | --- | --- |
| GET /api/engines/autopilot/config | 200, source factory, live_swappable true | PASS |
| detector control BEFORE the PUT: Deck UDP `L_PAD_LEFT` down/up (note 82 ch0) | filter calls from the OLD autopilot instance only (1 call) | fires as expected |
| PUT autopilot config update_hz 20 (live-swappable) | 200; engines/autopilot.json equals the body; registry holds a NEW autopilot instance (different id) with update_hz 20.0 | PASS |
| registry note-emit filters after the PUT | exactly one AutopilotEngine filter, owned by the NEW instance | PASS |
| same Deck note after the PUT | filter calls from the NEW instance only (1 call), none from the old | PASS |
| PUT update_hz "fast" | 400 `invalid autopilot config: could not convert string to float: 'fast'`; file sha256 7723428372b0... unchanged; instance unchanged | PASS |
| PUT osc_sync config (restart_required) | 409 `restart_required` with its reason; engines/osc_sync.json sha256 405fa738... unchanged; engines/ listing unchanged | PASS |
| GET /api/osc-relay | 200 running | PASS |
| PUT /api/osc-relay with two loopback destinations | 200; osc_relay.json equals the body; one datagram sent to the listen port arrived once at EACH destination | PASS |
| PUT /api/osc-relay destination == listen | 400 `... is the relay's own listen address; that would loop`; file unchanged | PASS |
| GET /api/midi/ports | 200 inputs = outputs = [IAC Driver DECK_IN, IAC Driver DECK_OUT, IAC Driver PULSE_OUT, ipMIDI Port 1], equal to a separate `rtmidi.MidiIn().get_ports()` / `MidiOut().get_ports()` listing; hook recorded 0 mido open_input/open_output/open_ioport calls | PASS |
| GET /api/logs/tail?lines=50 | 200, count 50, all 50 start with a timestamp; the boot line `2026-09-15 14:35:17,587 INFO root build fingerprint: version=0.5.0 commit=source built_utc=source` is in the ring (lines=1000) but NOT inside the newest 50 by the time of the call | PASS (stated) |
| 403 from a non-loopback peer | `.venv/bin/python -B -m unittest -v tests.test_agent_routes.LoopbackOnlyTests` -> `test_non_loopback_remote_is_403_before_any_work ... ok` | PASS |
| api-inventory test | `tests.test_ui_server.BridgeSettingsApiTests.test_api_inventory_matches_registered_method_paths` -> `Ran 1 test`, OK (my first invocation named the wrong class and errored on name lookup; re-run by the correct name) | PASS |
| HtmlApiBarTests | `test_external_static_api_detector_fires_and_restores ... ok`, `test_html_parses_and_all_api_paths_are_registered ... ok` | PASS |

The live bridge's 403 path was not exercised over the network: the UI server binds loopback, so no non-loopback peer can connect from this Mac; the route tests are the evidence, as the step says.

## 2b. Resolume file defaults

| Check | Observed | Result |
| --- | --- | --- |
| A2 home-resolution tests by name: `tests.test_resolume_home_defaults` | 5 tests ok (explicit value verbatim; missing key resolves under the running user's home; placeholder gone; detector fires/does not; tracked files outside docs/ and scripts/ hold no real home) | PASS |
| osc_sync on the engines-on bridge, HOME = scratch home holding `OneDrive/Documents/Resolume Arena/Shortcuts/OSC/STEAMDECK V2.xml` | POST /api/engines/osc-sync/resync 200 `target_count 2`; log tail `osc_sync: parsed 2 wigglable targets from /tmp/sdauto-gate/s1/run/home/OneDrive/Documents/Resolume Arena/Shortcuts/OSC/STEAMDECK V2.xml` | PASS |
| stageflow_bridge, same home holding `.../Compositions/5-5-26 STEAMDECK V2.avc` | instance `_comp_path` (hook read) = that scratch path. It logs nothing about the file: `_comp_path` is assigned at stageflow_bridge.py:153-154 and never read anywhere in windows/ (grep), so "reports loading" cannot be observed | resolution PASS; see F4 |
| `git grep -n "C:/Users/Ben"` at HEAD | NOT EMPTY: 30 lines (evidence/bridge/gitgrep.txt): 28 docs/, 1 scripts/showready/win_rail.sh (pinned rail work root), 1 tests/test_resolume_home_defaults.py (the string `C:/Users/Benedict/`, a negative control that substring-matches). 0 lines under windows/ config/ installer/ mac/ deck/ protocol/. 27 lines already at BASE; new since BASE: docs/sdauto-a2/REPORT.md (quotes the `C:/Users/Benedict/` control), docs/sdauto-a3/evidence/win/L2-pull-bundle.txt (rail output), the test above | FINDING F2 |
| LAPTOP, read-only, shape only (`shape2b.ps1`, `shape2b_home.ps1`) | installed `engines.factory\osc_sync.json` has `osc_preset_path` in home form; `suffix equal: true`, depth 9, `exists=True`; `equals_userprofile_join: true` (it equals the rail user's USERPROFILE joined with HEAD's suffix) and both tray pids are owned by that same user; no user `engines\osc_sync.json` | PASS: after an upgrade the omitted key resolves to the same file |
| laptop installed audio_opacity `protocol` | factory `outputs.protocol = osc`; the installed USER `engines\audio_opacity.json` has no protocol key (outputs keys: channel, cc_video_master, cc_logo_master), so the code default `osc` applies (same default at v0.4.9 and HEAD, audio_opacity.py:109; `git diff v0.4.9 HEAD -- windows/engines/audio_opacity.py` empty) | recorded; see F6 |
| engine_ab.py covers all five MIDI-emitting engines, per-engine controls RED | section 7b | PASS |

## 3. F5 and F2 on the Mac

Instrument: `.venv/bin/python -B /tmp/sdauto-gate/s3/f5f2.py --out /tmp/sdauto-gate/s3/run` (copy docs/sdauto-gate/scripts/f5f2.py; evidence/f5f2/). Each arm: `git archive <rev>` into scratch plus the Mac fixture presets, then the Mac launcher argv from scripts/mac/run_receiver.command with `--listen 127.0.0.1:<free>` and `--ui-port <free>`, plus `--dry-run --no-engines --no-pulse --no-osc-relay` (the load rules; the archived config/osc_relay.json names 10.10.10.x, so the relay must stay off). `BROWSER=/usr/bin/true`; PYSTRAY_BACKEND removed from the environment; SIGINT reset to default in the child (preexec).

Crash reports `ls ~/Library/Logs/DiagnosticReports/ | grep -c '^Python-'`: 9 before, 9 after all step 3 arms.

| Arm | Observed |
| --- | --- |
| HEAD shutdown 1 | POST /api/shutdown 202; `wait` exit code 0 after 0.27 s; no new crash report; 0 windows owned by the pid (any layer) 3 s after boot |
| HEAD shutdown 2 | 202; exit 0 after 0.22 s; no new crash report; 0 windows |

Status-item detector: `statusitems <pid>` (CGWindowListCopyWindowInfo, all windows, owner pid, layer; source scripts/statusitems.swift). Fires: SystemUIServer -> 1 layer-25 window; a throwaway Python process that creates a real NSStatusItem on its main thread (scripts/statusitem_control.py) -> `PID_WINDOWS 1 STATUS_LAYER_25 1`. At HEAD every probe (1, 3, 6, 10, 15, 20 s, statuswatch.json) shows 0 windows owned by the bridge. At BASE the same probes show 1 zero-size layer-0 window owned by Python and NO layer-25 window, and a system-wide layer-25 count per owner (layer25.swift, l25watch.json) is identical with the BASE bridge running and idle. So on this Mac today the BASE tray thread creates an NSApplication window but no visible status item; A3's "put a status item in the menu bar" is not reproduced by this detector (UNVERIFIED either way; the HEAD result does not depend on it).

The control script itself crashed at its cleanup (it removed the status item off the main thread: `Must only be used from the main thread`, exit 133) and wrote `Python-2026-09-15-144316.ips` (procLaunch 14:43:14.48, pid 18612, 2.2 s after launch, matching the control's probe delay; no bridge ran then, `pgrep -fl "statusitem_control|windows.win_recv"` exit 1). That report is the gate's own, not the bridge's; count now 10.

F2 (30 s window starting 2 s after boot; load check before and after the window):

| Rev | pgrep while True before/after | load1 before/after | foreign_lines before/after | CPU-s / wall s | % one core | ps %cpu mean of 30 | SIGINT | Exit | New crash report |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BASE 70cebd0 | empty / empty | 2.63 / 2.71 | 0 / 0 | 28.45 / 30.18 | **94.3** | 94.2 | not gone in 5 s | SIGTERM by pid -> -15 (pid gone) | none |
| HEAD a8fec2a | empty / empty | 2.81 / 2.42 | 0 / 0 | 0.08 / 30.35 | **0.3** | 0.1 | gone in 0.105 s | **0** | none |

--no-browser at HEAD, BROWSER = a script that appends its argv to a file and exits 0, 5 s run, SIGINT:

| argv | Records | SIGINT exit |
| --- | --- | --- |
| with `--no-browser` | 0 (no file) | 0 |
| without | 1 (`http://127.0.0.1:65426`) | 0 |

## 4. F2 on Windows (laptop, through the rail)

Guard snapshot first (L00), compare last (L12), both GREEN. Laptop acts in order (evidence/win/L*.txt): L00 guard snapshot; L01 read-only state (clone 38de0a4, porcelain 0, tray pids 5268 and 23640 in session 1, no browsers, no python); L02 bundle; L03 Windows suite; L04 Windows bar 1 + engine_ab; L05/L06/L09 2b shape reads; L07 F2 arms; L08 tray CPU; L10 final state; L11 browsers; L12 guard compare. ssh answered every call.

Code route: `git bundle create /tmp/sdauto-gate/win/bundle/sdpick.bundle 38de0a4..a8fec2a chain/steamdeck-20260914` (sha256 fe5eed2d0119740204cef47dbd06c66abfc1a635fd8a846cd91c7b07297c007a), put with a copy of `docs/sdpick-k1/scripts/pull_bundle.ps1` (sha256 d9be95406ee30937352c51a5713eaf6be827ae48b850870a00e7a1d42567833e), run with `-Expected a8fec2ad635e141b0634dc9a51c5442dad9fd966`: `BUNDLE_SHA256 fe5eed2d...` (same on the laptop), `... is okay`, `FETCH_HEAD a8fec2ad...`, `PINNED_HEAD a8fec2ad...`, `PORCELAIN_LINES 0`, RAIL_EXIT 0. No GitHub fetch.

Instrument: A3's committed `f2.ps1`, `win_f2.py`, `win_ctrl.py`, `tray_cpu.ps1`, `browsers.ps1`, copied unchanged (sha256 prefixes equal to the repo copies: 2dfc0dad, 1afcd5a9, b0a59c94, 595fca65, a7810f6b), run by me: `--dry-run --no-ui --no-engines --no-pulse --no-osc-relay`, loopback ports 47311-47314 / 17311-17314 checked free, BROWSER = the clone venv python `-c pass %s` (the 51b1d5b exit-0 form), `--no-browser` at HEAD (v0.4.9 has no such flag; `--no-ui` opens nothing at either). Parsed table: evidence/win/f2-parsed.txt.

| Arm | Rev | Ctrl-C processing | Tree CPU-s / wall s | % one core | % of 32 cores | CTRL_C_EVENT | CTRL_BREAK_EVENT | Final exit | Teardown in bridge log | Pids |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| g1 | HEAD a8fec2a | enabled | 0.1094 / 30.172 | 0.36 | 0.011 | gone in 0.313 s | not needed | 0 / 0 / 0 | `INFO shutdown requested`, `MIDI panic` | 4 recorded, all gone; python after 0 |
| g2 | v0.4.9 e66ff44 | enabled | 0.0312 / 30.349 | 0.10 | 0.003 | gone in 0.219 s | not needed | 0 / 0 / 0 | same | all gone; python after 0 |
| g3 | HEAD | inherited from the rail | 0.1250 / 30.192 | 0.41 | 0.013 | not gone in 5.11 s (259 = still active) | gone in 0.187 s | 0xC000013A on launcher and interpreter | none (abrupt) | all gone; python after 0 |
| g4 | v0.4.9 | inherited | 0.0156 / 30.284 | 0.05 | 0.002 | not gone in 5.06 s | gone in 0.140 s | 0xC000013A | none (abrupt) | all gone; python after 0 |

This reproduces A3's table at both revisions. No protected, unrecorded lane-path or foreign process was stopped; the fail-safe stop never ran. One oddity recorded, not graded: conhost pid 319884 appears in the g1 tree (gone=True after g1) and again in the g2 tree 40 s later, i.e. Windows reused the pid.

Installed v0.4.9 tray, READ-ONLY 60 s (`tray_cpu.ps1 -Seconds 60`, L08): pid 5268 0.0625 CPU-s (0.104% one core), pid 23640 0.6563 CPU-s (1.094%); total 0.7188 CPU-s over 60.006 s = **1.198% of one core**, 0.0374% of 32 cores. Not spinning (A3: 1.042%).

Browsers (BROWSER CLASS RULE b, L11 at 14:50:52, READ-ONLY Win32_Process): `BROWSER_PROCESSES 0`, `PYTHON_PROCESSES 0`. L01 at 14:26 listed none either. No NEEDS-MASTER browser line.

## 5. F4 and version in real Chromium (Mac)

Command: `.venv/bin/python -B docs/sdauto-gate/scripts/header_gate.py --out /tmp/sdauto-gate/s5 --engines-tree /tmp/sdauto-gate/s5-engines-tree/config --engines-state /tmp/sdauto-gate/s1/state_boot1.json --osc-ports 64657,52121 --rest-port 64923` -> exit 0, `STEP5 PASS` (evidence/browser/). chrome-headless-shell-1208 via playwright-core, 1440x900, `waitUntil: load` (never networkidle). BASE and HEAD arms: `git archive <rev> windows protocol config` + Mac fixtures, `--dry-run --no-engines --no-pulse --no-osc-relay` (+ `--no-browser` at HEAD), PYSTRAY_BACKEND=dummy, BROWSER=/usr/bin/true, free loopback ports. Engines arm: a copy of the step 1 loopback tree (IPv4 literals in its config: only 127.0.0.1, 29 occurrences; URLs only http://127.0.0.1:64923), autopilot state file written from boot 1's document, the OSC/REST ports held by the wrapper. Every bridge pid gone (`os.kill(pid, 0)` -> ProcessLookupError).

"One row" = every visible header child (logo, h1, each visible `.hdr-actions` child) shares one horizontal band: max(top) < min(bottom).

| Arm | View | Items | max top / min bottom (px) | One row | Header height | Section select width | Version label |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BASE 70cebd0 | Controller | 10 | 75 / 29.3 | no (detector fires) | 106 | 861 | none; /api/version 404 |
| BASE | List | 10 | 75 / 29.3 | no | 106 | 861 | none |
| HEAD a8fec2a | Controller | 10 | 13.8 / 33.3 | **yes** | 48 | 160 | `v0.5.0 (source)` |
| HEAD | List | 10 | 13.8 / 33.3 | **yes** | 48 | 160 | `v0.5.0 (source)` |

GET /api/version at HEAD: 200 `application/json` `{"build_time_utc": "source", "frozen": false, "git_commit": "source", "version": "0.5.0"}`. No page errors in any arm.

PNGs (docs/sdauto-gate/screenshots/ and ViddyVault/screenshots/sdauto-gate/), each opened:

| File | What it shows |
| --- | --- |
| before-header.png | BASE 1440x900 Controller view: header in three rows, Factory Reset/preset/Section on the first, a full-width "windows (this machine)" select on the second, section buttons and Save & Apply on the third; no version in the status bar |
| after-header.png | HEAD 1440x900 Controller view: logo, title, Factory Reset, EDM Show, Section + a content-width select, Add/Rename/Delete section and Save & Apply all on one 48 px row; status bar shows `v0.5.0 (source)` |
| before-header-list.png / after-header-list.png | the same two headers with the List view open (sidebar of mappings); HEAD still one row |
| after-engines.png | HEAD engines-on bridge, Engines tab: the 14 loaded engines with On checkboxes (Autopilot On). The UI shows engine on/off only, NOT autopilot channel intent (`engines_text_has_channel_state: false`); the restored intent is visible only through GET /api/engines, which this arm read: video enabled 8 beats 2.52 s LINEAR layers 1,2; fx enabled 32 beats 5.0 s RANDOM layer 5; logo off layer 7 |

Windows browser font metrics (A4 section 5 item 1): NOT measured by this gate (no Windows browser run; the laptop UI was not started). OWED to sdrc / Ben's hardware check.

## 6. Mutations (scratch copies; nothing in the run root changed)

Command: `.venv/bin/python -B docs/sdauto-gate/scripts/mutations.py --out /tmp/sdauto-gate/s6` -> exit 0, `MUTATIONS PASS` (evidence/mutations/). (a)-(e): `git archive HEAD` per mutant, one exact site replaced, named tests run from that tree, original bytes written back and required equal to HEAD's blob by sha256, tests re-run. (f): a `git clone --shared` scratch repo, a commit changing one byte (`frozenset({82, 86})` -> `{82, 96}` in windows/engines/autopilot.py), `engine_ab.py --repo <clone> --candidate <that commit>`, then `--candidate HEAD` in the same clone.

| Mutant | Tests | RED | Restored |
| --- | --- | --- | --- |
| (a) `self._restore_intent(path)` -> `pass` | tests.test_autopilot_state | exit 1, failures=5: five_fields_survive_restart_and_runtime_is_fresh, restored_enable_matches_a_live_enable_cc, inactive_engine_sends_nothing_until_active, channel_and_layer_removed_from_config_are_ignored, explicit_state_dir_restores_across_two_loads | 25 OK |
| (b) `crossfade_start_time` added to the persisted channel document | tests.test_autopilot_state | exit 1, failures=1: file_on_disk_has_schema_names_and_no_runtime_fields | 25 OK |
| (c) `EngineRegistry.replace` removes no filter and skips `old.shutdown()` | tests.test_engine_config_api | exit 1, failures=2: replaced_autopilot_filter_is_gone, replace_removes_filters_shuts_down_keeps_slot_and_binds | 14 OK |
| (d) `_should_start_receiver_tray` returns True (darwin starts the sidecar) | tests.test_win_recv_tray_platform | exit 1, failures=2: platform_rule, darwin_non_tray_never_constructs_or_stops_receiver_tray | 9 OK |
| (e) VERSION 0.5.1, APP_VERSION 0.5.0 | tests.test_ui_server.VersionAgreementTests | exit 1, failures=1: version_file_and_fingerprint_agree | 3 OK |
| (f) one-byte column-note change | engine_ab.py EDM Show (mac, windows section) | exit 1, different_sources [autopilot, receiver] on both comparisons | exit 0, passed true |

## 7. Bars at HEAD

### 7a. Bar 1 (byte-identical MIDI vs v0.4.9)

Mac: `.venv/bin/python -B scripts/showready/ab_run.py --candidate a8fec2ad... --script /tmp/sdauto-gate/bar1/deck-script.json ...` (deck script exit 0, script_sha256 9256621abf62..., 732 steps, 47,039 packets), four runs concurrent 14:25:37-14:33:30 in `tmux -L sdauto-gate` (runner docs/sdauto-gate/evidence/bar1/status.txt). Laptop: `ab.ps1` (sdpick K1's, re-pointed at sdwin\sdauto-gate), clone at a8fec2a, Windows-installed fixtures, laptop deck script f6611e7e (same packets as the Mac's, Windows path separators in parameters, as sdlive-gate recorded). Independent raw re-check of all six results: `.venv/bin/python -B docs/sdlive-gate/scripts/bar1_verify.py a8fec2ad... <6 results>` -> exit 0 (evidence/bar1/verify.txt; Windows results downloaded to evidence/win/ab-win-*.json.gz).

| Preset | Host | Instrument | Arms | Packets per arm | MIDI A / B (mapped) | Mappings exercised | Independent re-check | PIDs gone |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| EDM Show (sectioned, windows) | Mac | exit 0 passed | A v0.4.9, B1 flat, B2 section | 47,039 | 1531 / 1531 / 1531 (1525) | 56/56, different [] | passed | yes |
| PTZ (sectioned, windows) | Mac | exit 0 passed | A, B1, B2 | 47,039 | 1395 / 1395 / 1395 (1389) | 52/52 | passed | yes |
| default | Mac | exit 0 passed | A, B1 | 47,039 | 1531 / 1531 (1525) | 56/56 | passed | yes |
| EDM Show | laptop | exit 0 passed | A, B1 | 47,039 | 1531 / 1531 (1525) | 56/56 | passed | yes (23 pids gone=True in L04) |
| PTZ | laptop | exit 0 passed | A, B1 | 47,039 | 1395 / 1395 (1389) | 52/52 | passed | yes |
| default | laptop | exit 0 passed | A, B1 | 47,039 | 1531 / 1531 (1525) | 56/56 | passed | yes |

Recorder below the MidiOut wrapper, at HEAD: `docs/sdlive-gate/scripts/seam_probe.py run a8fec2ad... scripts/showready/timing_script.json <out>` -> recorded 9,644, forwarded 9,644, 9,644 recorder sends inside a wrapper forward, identical, 20,513 packets, passed true, pid gone. `--plant-drop 50` -> recorded 9,643 vs 9,644, first difference index 49, passed false (fires). Dead-seam control `ab_run.py --candidate a8fec2ad... --preset .../mac/presets/default.json --control dead-seam` -> exit 1, 0 MIDI on both arms, 56 unexercised; `bar1_verify.py` on it exit 1.

### 7b. engine_ab.py (Mac)

`.venv/bin/python -B scripts/showready/engine_ab.py --candidate a8fec2ad... --preset <p> [--section windows] --scratch ... --out ...` (instrument pinned; evidence/engine-ab/):

| Preset | Exit | A = B_nostate = B_state | events sha256 |
| --- | --- | --- | --- |
| mac EDM Show (windows section) | 0 | yes, different_sources [] | 3dd96b189403... (same as A1 and A2) |
| windows-installed EDM Show | 0 | yes | 3dd96b189403... |
| mac PTZ (windows section) | 0 | yes | e47e235d148b... |
| windows-installed PTZ | 0 | yes | e47e235d148b... |
| `--control sensitivity-autopilot` | 1 | control_expected true, different_sources [autopilot, receiver] | b 20c79c91... |
| `--control sensitivity-l_stick_layer` | 1 | control_expected true, different_sources [l_stick_layer] only, first difference bf7600 vs bf7700 | b 01c0730a... |

Coverage (EDM Show, every arm): autopilot 5 MIDI (re-emitted column notes) + 1,474 OSC, 6 deferred-or-dropped, 5 re-emitted, 1 dropped; global_color 3 MIDI + 424 OSC; gyro_feedback 60 MIDI; l_stick_layer 55 MIDI; audio_opacity MIDI covered (protocol midi forced by the instrument).

Windows: `engine_ab.py` was also run on the laptop for the installed EDM Show and PTZ (L04): exit 1 both, `arm A failed (exit 1)`; arm.log: `KeyError: 'LOCALAPPDATA'` at engine_ab_runner.py line 755 (`default_scratch` reads `os.environ["LOCALAPPDATA"]` before argument parsing, and the arm runs with an environment that lacks it). Instrument defect, finding F5. Windows engine A/B: UNVERIFIED-BY-EXECUTION.

### 7c. Bar 3 (Mac, real Chromium, declared M_bridge rule, locked rule beside it)

Commands exactly as scripts/showready/README.md "QUALIFYING commands" for `--rule m_bridge`, with gate scratch paths (runner /tmp/sdauto-gate/bar3/run.sh, copied to docs/sdauto-gate/scripts/bar3_run1.sh):

```
.venv/bin/python -B scripts/showready/timing_ab.py --rule m_bridge --candidate HEAD --script scripts/showready/timing_script.json --repeats 3 --control sensitivity --scratch /tmp/sdauto-gate/bar3/mac-mbridge-sensitivity --out /tmp/sdauto-gate/bar3/mac-mbridge-sensitivity.json.gz --client-cmd '["node",".../timing_browser.cjs","{url}","{stop}","{receipt}","<chromium-1208>","--single-process"]'
.venv/bin/python -B scripts/showready/timing_ab.py --rule m_bridge --candidate HEAD --script scripts/showready/timing_script.json --repeats 5 --scratch /tmp/sdauto-gate/bar3/mac-mbridge-clean --out /tmp/sdauto-gate/bar3/mac-mbridge-clean.json.gz --sensitivity-result /tmp/sdauto-gate/bar3/mac-mbridge-sensitivity.json.gz --client-cmd <same>
```

Candidate a8fec2a (archive sha256 5bfbdb76...), instrument timing_ab.py sha256 b9b7994a... (pinned), script clock, speed 1. Load: the instrument's own per-arm checks (pgrep `while True: pass` before and after, foreign_lines, load1) plus my sampler every 5 s (evidence/bar3/load.log). Independent recompute from raw samples: `.venv/bin/python -B docs/sdbar3-gate/gate_table.py <result>` -> exit 0 both; `rederived_m_bridge_mismatches 0`, `per_arm_stat_mismatches_vs_instrument []` (evidence/bar3/table-*.txt).

Sensitivity (14:45:40-14:57:57, exit 1 as expected, wall 731 s): all 9 arms load verified and VALID (9,638 timed each), bytes identical, M_bridge RED at p50/p95/p99 and per repeat (NNN, NNN, NNN):

| Sensitivity (ms) | p50 | p95 | p99 |
| --- | --- | --- | --- |
| M_bridge noise floor abs(CLOSED - CLOSED-B) | 0.003 | 0.023 | 0.057 |
| M_bridge abs(OPEN - CLOSED) | 5081.643 | 10241.455 | 10662.150 |
| M_total (locked) floor / delta | 0.001 / 5081.584 | 1.584 / 10122.519 | 2.297 / 9016.940 |

The 2 ms control is RED on M_bridge: the measurement is not blind, so this gate's bar 3 is VALID.

Clean run 1 (14:57:57-15:17:32, exit 1, wall 1165 s): 15/15 arms load verified (pgrep empty, foreign 0) and VALID (9,638 timed each; worst segment 9,016), bytes identical, stream dropped 0, clients [1,1], every browser and bridge pid gone.

| Clean run 1 pooled (ms) | p50 | p95 | p99 | max |
| --- | --- | --- | --- | --- |
| M_bridge CLOSED (n=48190) | 1.210 | 1.800 | 2.238 | 18.98 |
| M_bridge OPEN | 1.268 | 2.735 | 4.442 | 12.17 |
| M_bridge CLOSED-B | 1.198 | 1.736 | 1.950 | 14.37 |
| M_bridge floor / abs(OPEN - CLOSED) / within floor + 1.0 | 0.012 / 0.058 / yes | 0.064 / 0.936 / yes | 0.288 / **2.204 / NO** | - |
| M_total (locked) floor / delta / within | 0.008 / 0.064 / yes | 3.916 / 3.045 / yes | 1.952 / 1.390 / yes | - |
| worst-case six-axis segment M_bridge CLOSED / OPEN / CLOSED-B (n=45080) | 1.243 / 1.305 / 1.235 | 1.813 / 2.812 / 1.743 | 2.261 / 4.526 / 1.958 | - |
| worst segment M_bridge floor / delta | 0.008 / 0.062 | 0.070 / 0.999 | 0.303 / 2.265 | - |
| worst segment M_total floor / delta | 0.008 / 0.062 | 0.071 / 0.999 | 0.303 / 2.265 | - |

Per repeat, M_bridge arm p50/p95/p99 (ms) and load1 at arm start:

| Repeat | CLOSED | OPEN | CLOSED-B | load1 C/O/CB | M_bridge per-repeat rule |
| --- | --- | --- | --- | --- | --- |
| 1 | 1.176 / 1.696 / 1.893 | 1.201 / 1.731 / 1.936 | 1.200 / 1.720 / 1.894 | 3.08 / 4.02 / 3.31 | pass |
| 2 | 1.148 / 1.656 / 1.847 | 1.186 / 1.714 / 1.908 | 1.215 / 1.786 / 2.256 | 3.33 / 3.56 / 3.93 | pass |
| 3 | 1.381 / 2.160 / 3.080 | **1.696 / 4.378 / 6.717** | 1.170 / 1.684 / 1.835 | 7.52 / 6.57 / 6.36 | **FAIL p95, p99** |
| 4 | 1.156 / 1.662 / 1.812 | 1.216 / 1.765 / 1.994 | 1.165 / 1.676 / 1.833 | 5.39 / 9.27 / 5.37 | pass |
| 5 | 1.201 / 1.740 / 1.929 | 1.226 / 1.770 / 2.008 | 1.233 / 1.803 / 2.011 | 4.43 / 4.17 / 4.06 | pass |

**Run 1 result, reported as measured and not re-scored: RED on the declared M_bridge rule at p99.** MASTER 13 15:21 (1)-(2): it stands on the record, is not a PASS, and is not accepted as the product verdict (UNATTRIBUTED, environment-probable). Classification (not mitigation): the pooled RED comes from repeat 3, whose OPEN arm p99 is 6.7 ms against 1.9-2.0 in the other four OPEN arms. My sampler shows host load1 rising from about 3.7 to 8.15 at 15:05:14, 7.45 at 15:07:26 and 17.22 at 15:09:43 (repeat 3 ran from about 15:05 to 15:09), with foreign_lines 0 and pgrep empty in every sample, so the load came from something outside the load rules' definition. At 15:18:57 a foreign lane process was observed: `node /Users/viddyslap/Documents/project-workspaces/local-LLM-deepseek/qwen-bench/gates/browser-probe.mjs` with its own puppeteer chrome-headless-shell (not mine, not stopped). Its presence during repeat 3 is INFERENCE, not measured (the sampler did not record top processes during run 1). A lap cause is not excluded: A2 added a log ring that formats every INFO+ record, and every --no-engines timing arm logs one `engine_registry.on_axis_event failed` traceback per axis event (sdlive-gate), so formatting cost rose on both arms; whether it widens OPEN vs CLOSED is UNVERIFIED (a bar 3 run at 2811d25, before A2, would test it).

### 7c-2. MASTER 13 15:21 extended validity, applied

Ruling (3): a whole-machine sampler every <= 5 s (load1 and every process above 20% of one core, marked lane when it is in the arm's pid tree); an arm is INVALID if any in-arm sample has load1 > 5.0 or a non-lane process (WindowServer and kernel_task exempt) holds > 50% of one core for > 10 s; an INVALID arm voids the run; start only after load1 < 4.0 for 60 s; metric and floor + 1.0 unchanged. Ruling (4): clean2 stays DIAGNOSTIC; clean3 under (3) is bar 3 for sdauto.

Instruments (committed): `docs/sdauto-gate/scripts/machine_sampler.py` (lane = descendants of the supervisor pid), `docs/sdauto-gate/scripts/arm_validity.py` (arm window = mtime of `<arm>/start` to the newest file mtime in the arm directory, highest try per arm), `docs/sdauto-gate/scripts/bar3_supervised.sh` (quiet start, sensitivity then clean, validity after each, fresh run on INVALID, 90 min deadline).

Classifier proof, FIXTURE REPLAY only (MASTER 13 15:27: no CPU hog was ever started; every "hog" below is a line in a synthetic JSONL file replayed against the sensitivity run's real arm windows; evidence/bar3/val-*.out):

| Fixture | Exit | Invalid arms |
| --- | --- | --- |
| clean log (load1 3.0, no process) | 0 | 0 |
| non-lane process at 90% for 20 s inside r2 CLOSED | 1 | 1 |
| every sample load1 5.5 | 1 | 9 |
| lane-pid process at 90% for 20 s | 0 | 0 |
| non-lane process at 90% for 5 s | 0 | 0 |

Live sampler record of the qualifying runs (evidence/bar3q/samples.jsonl, 401 samples 15:39:14-16:12:36, max load1 4.79): the REAL lane processes appear above 20% marked `lane: true`: `timing_ab.py --rule m_bridge --candidate HEAD ...` (pid 7448, parent = supervisor 70428) at 99.5% in 28 samples, its child arm process `Python -B .../scripts/showready/...` (ppid 7448) at 99.9% in 236 samples, and the lane chrome-headless-shell at 24.6%.

Re-check of the earlier runs against the cap (5 s load.log, load1 only, so the process clause is NOT CHECKABLE for them):
- Sensitivity 14:45:40: r1 OPEN (14:47:25-14:48:43) had load1 5.19 at 14:47:44, 14:47:49, 14:47:54 -> INVALID, run void under (3). The master's 4.53 figure (from ~40 s reads) was RETRACTED by MASTER 13 15:27; this re-check stands. A fresh sensitivity was run under (3).
- Run 1 clean 14:57:57: 8 of 15 arms INVALID (r2 CLOSED-B, r3 all three, r4 all three, with load1 up to 17.22); 7 VALID.

Supervisor log (evidence/bar3q/supervisor.log): 15:39:14 start (deadline 17:09:14); 15:40:15 quiet (load1 2.94) START sens; 15:52:01 END exit 1, VALIDITY exit 0 `ALL VALID 9 arms`; 15:53:01 quiet (2.39) START clean; 16:12:36 END exit 1, VALIDITY exit 0 `ALL VALID 15 arms`; DONE. One try each: no run was voided.

Qualifying sensitivity (sens-try1, wall 701 s): 9/9 VALID, bytes identical; M_bridge floor 0.001 / 0.005 / 0.017 ms, |OPEN - CLOSED| 5114.619 / 10349.953 / 10774.030 ms: RED at p50, p95, p99 and in every repeat (NNN x3). The instrument is not blind; clean3's receipt is this run.

### 7c-3. The three clean runs side by side (M_bridge, pooled, ms; recomputed by gate_table.py with 0 mismatches)

| Run | Status | Arms valid under (3) | Floor p50 / p95 / p99 | abs(OPEN - CLOSED) p50 / p95 / p99 | Within floor + 1.0 | Locked rule (M_total) | Per-repeat M_bridge |
| --- | --- | --- | --- | --- | --- | --- | --- |
| run 1 (14:57:57-15:17:32) | on the record, RED, not the verdict | 7 / 15 | 0.012 / 0.064 / 0.288 | 0.058 / 0.936 / 2.204 | Y / Y / N | PASS | YYY YYY YNN YYY YYY |
| clean2 (15:19:03-15:39:06) | DIAGNOSTIC | not sampled per arm (top2.log: load1 > 5 in 36 of 236 samples) | 0.027 / 1597.894 / 3701.148 | 0.026 / 3812.625 / 4773.297 | Y / N / N | RED | NNN YYY YYN YYY YYY |
| **clean3 (15:53:01-16:12:36)** | **QUALIFYING = bar 3** | **15 / 15** | 0.036 / 1.904 / 294.099 | 0.181 / 1868.469 / 1197.269 | **Y / N / N** | RED (p95 964.456 vs 208.392; p99 934.492 vs 419.909) | YNN YNN YYY YYY YYY |

clean3 per repeat, arm M_bridge p50 / p95 / p99 / max (ms):

| Repeat | CLOSED | OPEN | CLOSED-B | Per-repeat rule |
| --- | --- | --- | --- | --- |
| 1 | 1.146 / 1.649 / 1.826 / 9.5 | 7.404 / 3131.216 / 3434.288 / 3542.5 | 6.507 / 1867.951 / 3250.982 / 3567.2 | YNN |
| 2 | 1.193 / 1.739 / 66.646 / 314.6 | 1.550 / 1925.528 / 3391.705 / 3759.5 | 1.158 / 1.669 / 1.813 / 4.2 | YNN |
| 3 | 1.200 / 1.754 / 1.988 / 27.1 | 1.197 / 1.723 / 1.931 / 11.1 | 1.200 / 1.726 / 1.922 / 18.1 | YYY |
| 4 | 1.457 / 12.911 / 20.956 / 130.7 | 1.315 / 10.870 / 16.438 / 165.7 | 1.175 / 1.714 / 3.654 / 154.1 | YYY |
| 5 | 1.644 / 2162.057 / 3448.349 / 3550.2 | 1.509 / 2210.803 / 3416.550 / 3530.8 | 1.412 / 12.231 / 19.426 / 112.1 | YYY |

Worst-case six-axis segment, clean3 pooled M_bridge: CLOSED 1.299 / 12.354 / 2258.443, OPEN 1.510 / 1990.004 / 3371.741, CLOSED-B 1.355 / 12.827 / 1989.182; floor 0.056 / 0.474 / 269.261; delta 0.211 / 1977.650 / 1113.298 (M_total identical to within 0.0001 ms on this segment). Every arm 9,638 timed MIDI (worst segment 9,016), stream dropped 0 except r2 OPEN 32, clients [1,1] in every OPEN arm, browser and bridge pids gone.

Raw timing results are 28-46 MB each and stay in /tmp (not committed); their sha256 are in evidence/bar3/result-sha256.txt (clean3 2203ad37..., qualifying sensitivity 1a762af4..., run 1 40f6c3e6..., clean2 a8f107a7..., sensitivity 1 878feca0...). Tables recomputed from them are committed (evidence/bar3/table-*.txt, evidence/bar3q/table-*.txt).

**Bar 3 for sdauto, per MASTER 13 15:21 (4): RED.**

What the RED is made of (measured, classification only, not mitigation):
- Stall census, arms with any M_bridge sample > 100 ms (evidence/bar3/stall-census.txt): run 1 none; clean2 r1 OPEN 7,018 ms, r1 CLOSED-B 6,228, r2 CLOSED 3,598; qualifying sensitivity CLOSED/CLOSED-B arms none; clean3 r1 OPEN 3,542, r1 CLOSED-B 3,567, r2 CLOSED 315, r2 OPEN 3,759, r4 all three 130-166, r5 CLOSED 3,550, r5 OPEN 3,531. Stalls of seconds hit arms with NO client (CLOSED, CLOSED-B) in clean2 and clean3.
- Shape (clean3 r1 OPEN, r1 CLOSED-B, r5 CLOSED): latency jumps to about 3.5 s at one moment (r1 OPEN at +36 s after the first send, r1 CLOSED-B at +46 s, r5 CLOSED at +50 s) and drains linearly over about 6 s. `t1_pre` is taken by the in-process sender, which kept its schedule, so the bridge's receive path stopped for about 3.5 s while the sender thread ran.
- Machine at those moments (samples.jsonl within +-12 s): load1 3.0-4.4, the only processes above 20% are the lane timing process (about 100%, the sender's designed yield loop) plus WindowServer 20-46% and the harness engine node 20-68% for one sample. No non-lane process near 50% for 10 s. Swap 0 MB, `memory_pressure` 26% free at 16:15 (not sampled during the arms).
- Log ring hypothesis (A2 formats every record into a ring; each --no-engines arm logs 15,246 `engine_registry.on_axis_event failed` tracebacks, 5.4 MB of stderr per arm): `logcost.py` (docs/sdauto-gate/scripts/logcost.py), 15,246 records x 5, stream to /dev/null: BASE tree 162.8 us per record, HEAD with the ring 165.6 us, HEAD without the ring 165.9 us. The ring adds no measurable cost: REFUTED as the cause. The stderr file writes themselves (to /tmp) are unmeasured.
- Time pattern: no stalls 14:45-15:17 (sensitivity 1, run 1) or 15:40-15:52 (qualifying sensitivity, CLOSED arms); stalls 15:19-15:27 and 15:53-16:12. The same code produced both.
- Cause: UNVERIFIED. A lap cause (A1-A4 product diff) is not excluded by anything above. The discriminating control this gate did NOT run: the same supervised R=5 at BASE 70cebd0 (with its own R=3 receipt) in the same session. sdbar3's gate measured 70cebd0 PASS with max about 19 ms, but that was a different session and the stalls here are time-varying.


## 8. Pick-up

| Row | Result |
| --- | --- |
| every link pushed | A1 2811d25, A2 5f35bbe, A3 ef5c20c, A4 a8fec2a in their envelopes; `git ls-remote --heads origin chain/steamdeck-20260914` = a8fec2a = `git rev-parse HEAD` at gate entry |
| porcelain | empty at entry; after this gate's commit: see the commit check in the envelope |
| excluded paths committed since BASE | `git diff --name-only 70cebd0 HEAD` filtered for windows_receiver_settings.local.json, bridge.local.json, config/engines/, config/state/, config/presets/, .showready/: none (grep exit 1) |
| config/engines.factory | CHANGED: `git diff --stat 70cebd0 HEAD -- config/engines.factory` = `osc_sync.json | 1 -`: the `"osc_preset_path": "C:/Users/USERNAME/..."` placeholder removed, which is A2's stated 5b choice. The laptop check (2b) shows the omitted key resolves to the file the installed build names today. Classified INTENDED, not a regression |
| mac/ | `git diff --stat 70cebd0 HEAD -- mac/` 0 lines |
| windows/midi.py, windows/config.py | 0 diff lines since BASE |
| windows/receiver.py hunks since BASE (5 insertions) | `serve_forever(..., receiver_tasks=None)` parameter; `if receiver_tasks is not None: receiver_tasks.drain()` after the reload block. A2's receiver-thread swap queue. No mapping logic, send condition or argument changed; cost on the MIDI path = one empty-queue check per loop (measured only through bars 1 and 3) |
| Ben's Mac files | `config/presets/EDM Show.json` 58e47bfd, `config/presets/PTZ.json` 11b37cd6, `config/bridge.local.json` 7476c269: unchanged |
| run root config/state/ | does not exist (`ls config/state`: No such file or directory) |
| Mac processes started | every bridge in steps 1, 3, 5 proved gone (ps -p / os.kill); step 3 BASE F2 bridge needed SIGTERM by its own pid; bar 1, seam, engine_ab and bar 3 runners exited; after DONE: `ps -A` for timing_ab, capture_runner, chrome-headless-shell-mac, machine_sampler, bar3_supervised, sampler scripts: none; `tmux -L sdauto-gate ls`: no server running |
| laptop processes started | every F2 arm, suite, A/B run and deck script proved its recorded pids gone by Get-Process; L10 and L11 `PYTHON_PROCESSES 0`; guard compare GREEN pythonProcesses=0 |

## Findings

- F1 (information for AJ, not a defect): the restored transition push arrives 35.8 ms BEFORE the "engines loaded" line, because autopilot's first dispatch is the receiver's startup layer-state CC fan-out at construction (receiver.py:169 -> :829 -> :802 -> :212), not the first tick. No input, within 1 s: holds.
- F2 (master decision; A2 already flagged it): `git grep -n "C:/Users/Ben"` at HEAD is not empty: 30 lines, none in product directories; 27 pre-date BASE; the 3 new ones are a negative-control string (`C:/Users/Benedict/`) in a test and in A2's report, and rail output in A3's evidence.
- F3 (intended): config/engines.factory/osc_sync.json lost its placeholder key (A2 5b); on the laptop the omitted key resolves to the same existing file.
- F4 (owner: whoever owns stageflow_bridge; not a HOLD): `comp_path` is resolved under HOME but never read at runtime (stageflow_bridge.py:153-154 is the only use), so the gate's "stageflow_bridge reports loading" cannot be observed. The home-relative default is dead configuration today.
- F5 (instrument, owner sdpolish or sdrc): `scripts/showready/engine_ab.py` cannot run on Windows: `KeyError: 'LOCALAPPDATA'` at line 755 in the arm process. Windows engine A/B is UNVERIFIED. Not fixed here: it is a pinned instrument and not a bar of this gate.
- F6 (coverage note): on the installed laptop config audio_opacity outputs over OSC (no protocol key; code default osc, unchanged since v0.4.9), while engine_ab forces protocol midi, so audio_opacity's OSC output is not A/B compared. The engine file is byte-unchanged since v0.4.9.
- F7 (detector note): on this Mac the BASE sidecar tray shows no layer-25 status window, only a zero-size Python window; the HEAD result (0 Python windows) stands with a detector proven on a real Python NSStatusItem.
- F8 (gate's own residue): the status-item control script wrote crash report Python-2026-09-15-144316.ips (count 9 -> 10); not the bridge.
- F9 (MASTER 13, recorded as instructed, not probed): PUT /api/engines/<type>/config accepts update_hz 0, negative or huge, and `tick_interval_seconds` (1.0/update_hz) runs outside try/except in `shortest_tick_interval`, so the receive loop can exit. Owner sdpolish P0; not a HOLD for sdauto.
- F10 (load rule gap): the load rules' foreign_lines definition names only local-LLM-h14 engine tests; a local-LLM-deepseek qwen-bench lane (node + puppeteer Chromium) runs outside it and host load1 reached 17 during bar 3 run 1 with foreign_lines 0.
- F11 (my own reporting slip): my first progress note said "started 14:30"; `date` at that moment read 14:23. The time was not measured when I wrote it.

## For Ben

1. The feature work in this lap holds up: autopilot remembers its channel settings across a restart and pushes them to Resolume on its own within 80 ms of starting; the new agent routes work on a real bridge; the Mac bridge no longer spins a CPU core or crashes on quit; the header is one row; the version reads 0.5.0.
2. MIDI output is byte-identical to v0.4.9 for EDM Show, PTZ and default, on the Mac and on the laptop, and the engines' output is identical on the Mac. The Windows suite passes at this commit.
3. Bar 3 (no added delay with the controller view open) came out RED in the first qualifying run: in one of five repeats the view-open arm was slower at the 99th percentile while the Mac was under heavy load from another project. Under the stricter load rule the master set at 15:21, the qualifying run on a quiet Mac was also RED. The cause is pauses of about 3.5 s in the bridge's input handling, and they happened with the controller view CLOSED as well as OPEN, so the view is not proven to be the cause, but nothing proves this lap's changes innocent either. It is a HOLD for the judge. Closing the view is NOT a proven mitigation here, because the pauses also happened with it closed. This measurement runs the bridge with engines off on the Mac; it says nothing yet about the installed v0.4.9 tray you plan to run Friday, which stays your fallback.
4. Your installed v0.4.9 tray is idle (about 1.2% of one core) and was not touched; the laptop guard was green before and after.
5. The Windows engine A/B tool does not run on Windows yet (a small tool bug), so engine output on Windows is only covered by the Mac comparison.
