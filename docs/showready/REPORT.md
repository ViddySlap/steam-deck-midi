GUARD COMPARE (last laptop act, 2026-09-16T10:49:04Z): `GUARD GREEN: compare; protected state observed; pythonProcesses=0`, rail exit 0 (evidence/G13-guard-compare.txt). Snapshot before the first laptop act (09:30:0xZ): `GUARD GREEN: snapshot; protected state observed; pythonProcesses=0`, exit 0 (evidence/G00-guard-snapshot.txt). Independent record identical at both ends (step 7).

FINDING FIRST (not a bar, a ruling for the master): WINDOWS IDLE CPU OF THE BUILT EXE, CANDIDATE vs v0.4.9, mean of paired differences **0.494 points** of one core against the 0.2-point rule, and the 0.4-point TRIPWIRE fires on 2 of 3 pairs (0.494, 0.598). Absolute figures are small (candidate 0.49-0.65%, v0.4.9 0.05-0.16% of one core, 5% bar) and the self-test reader was proved live beside them. Section 7e.

# sdrc GATE (CG) - the show-ready evidence report for 0.5.0

Executor: claude-rc claude-opus-5 on the Mac, unsandboxed. Branch `chain/steamdeck-20260914`. Scratch `/tmp/sdrc-gate/` (Mac), `C:\Users\Ben\AppData\Local\Temp\sdwin\sdrc-gate\` and `...\sdwin\sdrc-gate-w100\` (laptop). Every laptop act went through `scripts/showready/win_rail.sh`; ssh answered every call. Nothing was installed, no installer ran, the running v0.4.9 tray, loopMIDI, Resolume and the orphan checkout were not touched. No tag, no release, no merge, no main push.

## VERDICT IN ONE PARAGRAPH

0.5.0 is built from CANDIDATE 2e4292a, staged at `C:\Users\Ben\Documents\steamdeck-midi-showready\candidate-2e4292a\` and never run; nothing was installed. **Bar 1 QUALIFIED**: every mapping in EDM Show (56) and PTZ (52), and default (56), sends byte-identical MIDI to v0.4.9 on the Mac and on the laptop (0 different, 0 not covered), and the five MIDI-emitting engines are identical in process; the qualification is only the three username hunks by which your installed build (orphan d136787) differs from the v0.4.9 tag, none on a MIDI path. **Bar 2 PASS**: the laptop clone at CANDIDATE ran `1099 tests OK (skipped=6)`, exit 0. **Bar 3 NOT COUNTED**: on the Mac with real Chromium the view open added 0.028-0.034 ms at p50 and 0.067-0.094 ms at p99 on M_bridge against about 1.02 ms allowed, in two fresh qualifying runs whose 2 ms controls went RED by over 5 seconds, but BOTH runs are void under the extended load cap because another lane's local-LLM bench and the vault sync were busy during arms; the laptop cannot count (its 2 ms control goes INVALID on Windows, as before). **Bar 5 PASS**: the v0.4.9 installer (43,881,072 bytes, sha256 = GitHub's digest) and byte copies of the program (44/44) and your config (38/38) are on the laptop, re-verified from a fresh read, and the installed program is still byte-identical. An install from STAGING keeps OSC Sync working with or without the override (207 targets, same file). One finding for the master, not a bar: the built exe idles 0.494 points of one core above v0.4.9 (0.2 rule; absolute 0.5-0.65%).

| Bar | Verdict | The number that decides it |
| --- | --- | --- |
| 1 MIDI byte-identical to v0.4.9 | **QUALIFIED (by name)** | EDM Show 56/56 and PTZ 52/52 mappings exercised, 0 different, on the Mac AND the laptop; 5 engines identical in process. QUALIFIED only because the installed build came from orphan d136787, which differs from tag e66ff44 in exactly 3 username hunks (below) |
| 2 Full suite on Windows | **PASS** | laptop clone at CANDIDATE: `Ran 1099 tests`, `OK (skipped=6)`, exit 0; Mac `Ran 1099 tests`, `OK (skipped=2)`, exit 0 |
| 3 No added delay, view open vs closed | **NOT COUNTED** | M_bridge abs(OPEN-CLOSED) p99 0.094 ms (run 1) and 0.067 ms (run 2) vs floor + 1.0 = 1.045 / 1.019 ms, PASS by the instrument with sensitivity RED both times; both runs VOID under the extended load cap (foreign bench + vault sync); laptop sensitivity INVALID |
| 5 Rollback ready | **PASS** | v0.4.9 installer 43881072 bytes, sha256 05a46159...51a5 = GitHub digest, re-read on the laptop; rollback manifests 44/44, 38/38, 4/4; installed program 44/44 still equal (installer never ran) |
| 4 Ben's 15 minutes | OWED TO BEN | checklist at the end |

## IDENTITY

| Item | Value |
| --- | --- |
| CANDIDATE | `2e4292a75f08674fdf5c78358485b27c2d3bd913` (docs/sdrc-c1/REPORT.md line 1) |
| VERSION | 0.5.0 |
| Mac HEAD at gate start / origin | `a26a881c1165ef5c12364e174feacf79e215b8ae` = `git ls-remote --heads origin chain/steamdeck-20260914`; `git diff --name-only 2e4292a HEAD` lists only `docs/` (grep -v '^docs/' exit 1, zero lines) |
| Laptop clone HEAD | `2e4292a75f08674fdf5c78358485b27c2d3bd913`, porcelain 0 (G01, G12) |
| STAGING | `C:\Users\Ben\Documents\steamdeck-midi-showready\candidate-2e4292a\` ; BUILD-INFO.txt line 1 `CANDIDATE 2e4292a75f08674fdf5c78358485b27c2d3bd913` (G04) |
| Installer | `STEAMDECK-MIDI-RECEIVER-2-Setup-0.5.0.exe`, 43981989 bytes, sha256 `9232d8c4a2673dd1c3ec1bc35c9f87b9bc00c528114d71dec88892065c1565a1` |
| Staged console exe | sha256 `2fcb2868d847615b5dd8b78732b654c857d48872f7125ab014a51253797f9b1c` |
| Frozen exe `/api/version` (step 4, 4 boots) | `{"build_time_utc":"2026-09-16T09:12:21Z","frozen":true,"git_commit":"2e4292a75f08674fdf5c78358485b27c2d3bd913","version":"0.5.0"}` |

## 1. BAR 2 - SUITES

| Check | Command | Result |
| --- | --- | --- |
| Windows suite, clone at CANDIDATE | `.venv\Scripts\python.exe -m unittest discover -v -s tests -p "test_*.py"` (PYSTRAY_BACKEND=dummy, BROWSER = venv python `-c pass %s`, TMP under LAPTOP WORK) via rail | **`Ran 1099 tests in 77.083s`, `OK (skipped=6)`, exit 0**, launcher 361952 and child 127932 gone, python after 0 (G02) |
| Mac suite at HEAD (docs-only after CANDIDATE) | `.venv/bin/python -m unittest discover -s tests -p "test_*.py"` | **`Ran 1099 tests in 31.867s`, `OK (skipped=2)`, exit 0** |
| node checks | `node tests/ui_{controller,controller_macro,reload,sections,version}_check.cjs` | all five exit 0 |
| pin | `shasum -a 256 -c scripts/showready/SHA256SUMS` | 19 OK, 0 not OK |

Windows skips, every one named with its reason (from the -v run):

| Test | Reason |
| --- | --- |
| test_autopilot_state.WriteFailureTests.test_read_only_state_dir_never_raises | POSIX non-root permission check |
| test_global_color.CcBaseOffsetTests.test_cc_base_override_remaps_channel_ccs | cc_base remap anticipated for a future channel-CC move; not wired yet |
| test_section_launchers.MacSectionLauncherTests.test_local_section_is_passed_as_one_argument_and_missing_file_still_works | Mac launcher execution requires POSIX bash and executable shebangs |
| test_showready_rail.ShowreadyTransportTests.test_remote_status_stderr_arguments_and_scp_failure | Mac rail execution requires POSIX bash |
| test_showready_rail.ShowreadyTransportTests.test_unsafe_arguments_are_refused_before_transport | Mac rail execution requires POSIX bash |
| test_upgrade_boot.MacLauncherSnippetTests.test_section_snippet_creates_missing_file_and_preserves_existing_bytes | Mac launcher execution requires POSIX bash and paths |

## 2. BAR 1 - BYTES

### The seam, at CANDIDATE, first

| Control | Command | Result |
| --- | --- | --- |
| dead seam | `ab_run.py --candidate 2e4292a... --preset .showready/fixtures/mac/presets/default.json --script /tmp/sdrc-gate/bar1/deck-script.json --control dead-seam` | **exit 1, RED**: 0 messages on both arms, mappings_exercised 0 of 56, all 56 listed unexercised |
| recorder below the MidiOut wrapper | `docs/sdlive-gate/scripts/seam_probe.py run 2e4292a... scripts/showready/timing_script.json /tmp/sdrc-gate/seam/clean` | exit 0: recorded 9,644 = forwarded 9,644, 9,644 recorder sends inside a wrapper forward, identical, 20,513 packets, bridge pid gone |
| planted drop | same with `--plant-drop 50` | **exit 1, RED**: recorded 9,643 vs forwarded 9,644, first difference index 49 |

### The A/B table

Deck script: `deck_script.py` (Mac `/tmp/sdrc-gate/bar1/deck-script.json`, laptop `sdwin\sdrc-gate\deck-script.json`: 732 steps, 47,039 packets, 469.7 s, all 75 Action IDs). Both fixture manifests are verified by `ab_run.py` before any preset is read. The Mac sectioned fixtures run A (flat v0.4.9), B1 and B2 (sectioned, `--section windows`).

| Preset | OS | Steps | Mappings exercised / total | Messages A / B | Identical | NOT COVERED |
| --- | --- | --- | --- | --- | --- | --- |
| EDM Show (mac fixture, sectioned) | Mac | 732 | 56 / 56 (B1 and B2) | 1531 / 1531 | yes, exit 0 | none |
| PTZ (mac fixture, sectioned) | Mac | 732 | 52 / 52 (B1 and B2) | 1395 / 1395 | yes, exit 0 | none |
| default (mac fixture) | Mac | 732 | 56 / 56 | 1531 / 1531 | yes, exit 0 | none |
| EDM Show (windows-installed fixture) | laptop | 732 | 56 / 56 | 1531 / 1531 | yes, exit 0 | none |
| PTZ (windows-installed fixture) | laptop | 732 | 52 / 52 | 1395 / 1395 | yes, exit 0 | none |
| default (windows-installed fixture) | laptop | 732 | 56 / 56 | 1531 / 1531 | yes, exit 0 | none |

Commands: `ab_run.py --candidate 2e4292a75f08674fdf5c78358485b27c2d3bd913 --preset <fixture> [--section windows] --script <deck-script> --out ...` (Mac, /tmp/sdrc-gate/bar1_mac.sh) and the same with `--fixtures C:\...\sdwin\fixtures --scratch ...` on the laptop (G03). Every laptop pid proved gone.

### Engines in process (engine_ab.py)

A = v0.4.9, B_nostate and B_state = CANDIDATE. All runs `env -u LOCALAPPDATA`.

| Preset | OS fixture | audio_opacity protocol | Result | Per-engine output on every arm (MIDI / OSC) |
| --- | --- | --- | --- | --- |
| EDM Show | mac, `--section windows` | osc (instrument default since F6) | exit 0, identical | audio_opacity 0/58, autopilot 5/1474 (6 filter deferred-or-dropped, 5 re-emitted, 1 dropped), global_color 3/424, gyro_feedback 60/0, l_stick_layer 55/0 |
| EDM Show | mac, `--section windows` | **midi** | exit 0, identical | audio_opacity **58**/0, others as above |
| EDM Show | windows-installed | osc | exit 0, identical | as the mac EDM row |
| EDM Show | windows-installed | **midi** | exit 0, identical | audio_opacity **58**/0, others as above |
| PTZ | mac, `--section windows` | osc | exit 0, identical | autopilot, l_stick_layer, audio_opacity inactive and silent; global_color 3/0 (load/refresh); gyro_feedback 60/0 |
| PTZ | windows-installed | osc | exit 0, identical | same as the mac PTZ row |
| default | mac | osc | exit 0, identical | same as EDM |
| control `sensitivity-autopilot` | EDM mac | osc | **exit 1, control_expected true**: different_sources `autopilot`, `receiver` at index 203 | |
| control `sensitivity-l_stick_layer` | EDM mac | osc | **exit 1, control_expected true**: different_sources `l_stick_layer`, `bf7600` vs `bf7700` at step 1783 | |

The five MIDI-emitting engines (autopilot with its L_PAD note filter, l_stick_layer, gyro_feedback, global_color, audio_opacity) are identical in process. Note: since sdpolish P0 (F6) the instrument's default audio_opacity protocol is `osc`, the installed laptop's effective setting; this gate ran BOTH protocols so audio_opacity's MIDI surface (58 MIDI on every arm) is compared too.

### Bar 1 reads

**"Mappings identical, engines identical in process"**, plus the three d136787 username hunks by name. The sdwin gate's d136787-vs-e66ff44 comparison, VERBATIM (docs/sdwin-gate/REPORT.md, Step 4c):

> orphan HEAD d1367870b939...; `status --porcelain -- windows config deck protocol` = 0 lines; `ls-tree -r d136787` 74 paths, `ls-tree -r e66ff44` 74 paths;
> `diff` of the listings (exit 1) shows exactly 3 differing blobs:
>
> | Path | d136787 blob | e66ff44 blob | Differing line | Orphan with `C:/Users/Ben/` -> `C:/Users/USERNAME/` equals tag |
> | --- | --- | --- | ---: | --- |
> | config/engines.factory/osc_sync.json | 7d2d5ea8 | 9d167d53 | 5 (`osc_preset_path`) | True |
> | windows/engines/osc_sync.py | a4d4a4a1 | 0abd30ab | 101 (default path) | True |
> | windows/engines/stageflow_bridge.py | 2c49e061 | 059f3312 | 147 (`comp_path` default) | True |
>
> The raw line comparison differs at exactly one line per file; with the username substituted the whole files are equal. That is the control,
> and it confirms MASTER 18:23. Join recorded as QUALIFIED-BY-NAME with those three hunks. Mappings are unaffected (no MIDI path).

That comparison was NOT clean (3 differing blobs), so bar 1 is **QUALIFIED**, with the named paths `config/engines.factory/osc_sync.json`, `windows/engines/osc_sync.py`, `windows/engines/stageflow_bridge.py`. None is on a MIDI path. Today the orphan checkout is still `d1367870b93921b115b4c0972c13393792ea5307`, porcelain 0 (G01, G12).

## 3. BAR 3 - TIMING

**Bar 3 on the Mac is a PASS by the instrument in TWO fresh qualifying runs, and BOTH runs are VOID under the extended load cap (MASTER 13, 15:21 (3) and 17:18/19:42), so bar 3 is NOT COUNTED by this gate.** The void comes from named foreign load: other lanes' processes and the vault sync. It does not come from this lane's work and it does not come from the candidate. The sensitivity control went RED on M_bridge in both runs, so the rule is valid and the instrument resolves 2 ms. The Mac could not hold a quiet 32 minutes within 90 minutes; NEEDS-MASTER written.

Commands, run exactly as scripts/showready/README.md gives them, sensitivity first, one at a time, nothing else of this lane in flight (the laptop was idle; its guard compare ran BEFORE run 2):

```
.venv/bin/python -B scripts/showready/timing_ab.py --rule m_bridge --candidate 2e4292a75f08674fdf5c78358485b27c2d3bd913 --script scripts/showready/timing_script.json --repeats 3 --control sensitivity --scratch /tmp/sdrc-gate/timing2/mac-mbridge-sensitivity --out /tmp/sdrc-gate/timing2/mac-mbridge-sensitivity.json.gz --client-cmd '["node",".../scripts/showready/timing_browser.cjs","{url}","{stop}","{receipt}",".../chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell","--single-process"]'
.venv/bin/python -B scripts/showready/timing_ab.py --rule m_bridge --candidate 2e4292a75f08674fdf5c78358485b27c2d3bd913 --script scripts/showready/timing_script.json --repeats 5 --scratch /tmp/sdrc-gate/timing2/mac-mbridge-clean --out /tmp/sdrc-gate/timing2/mac-mbridge-clean.json.gz --sensitivity-result /tmp/sdrc-gate/timing2/mac-mbridge-sensitivity.json.gz --client-cmd <same>
```

Run 1 used `/tmp/sdrc-gate/timing/...`, identical otherwise. Every scratch had `.metadata_never_index` created before the first file. Pins 19/19 OK before each run. Per-arm quiet gate: load1 < 4.0 for 60 s immediately before each command (waited 60 s, 60 s, 60 s, 61 s; load1 2.10, 2.26, 2.06, 2.09). `pgrep -f "while True: pass"` exit 1, empty, before and after every command and inside the instrument before and after every arm (all 48 arms `empty`). Instrument `foreign_lines` 0 before and after every arm. Tables recomputed independently from raw samples with `docs/sdbar3-gate/gate_table.py` (0 re-derived M_bridge mismatches, 0 per-arm stat mismatches against the instrument, in all four results).

### M_bridge and M_total side by side (pooled, ms)

| Run | Command | M_bridge floor p50/p95/p99 | M_bridge abs(OPEN-CLOSED) | M_bridge rule | M_total floor | M_total abs(OPEN-CLOSED) | Locked rule (BESIDE) | exit, bar3_counts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 sens R=3 | 04:15-04:27 | 0.007 / 0.013 / 0.002 | 5007.416 / 10158.499 / 10574.606 | **RED** | 0.009 / 1.588 / 0.291 | 5007.355 / 10038.466 / 8919.530 | RED | 1, false; `m_bridge_sensitivity_timing_red: true` |
| 1 clean R=5 | 04:28-04:47 | 0.011 / 0.017 / 0.045 | **0.034 / 0.048 / 0.094** | **PASS** (<= 1.011 / 1.017 / 1.045) | 0.011 / 0.123 / 1.971 | 0.028 / 0.189 / 2.326 | PASS | 0, true |
| 2 sens R=3 | 04:50-05:02 | 0.008 / 0.009 / 0.038 | 5153.207 / 10442.217 / 10857.613 | **RED** | 0.003 / 1.510 / 2.380 | 5153.143 / 10323.796 / 9212.363 | RED | 1, false; `m_bridge_sensitivity_timing_red: true` |
| 2 clean R=5 | 05:03-05:22 | 0.000 / 0.000 / 0.019 | **0.028 / 0.039 / 0.067** | **PASS** (<= 1.000 / 1.000 / 1.019) | 0.004 / 0.109 / 0.807 | 0.023 / 1.457 / 1.166 | **RED at p95** (1.457 > 1.109) | 0, true |

Pooled per arm, run 2 clean (n = 48,190 every-message timed MIDI per arm type): M_bridge CLOSED 1.134 / 1.632 / 1.816 (max 13.065), OPEN 1.162 / 1.671 / 1.883 (max 31.831), CLOSED-B 1.134 / 1.632 / 1.797 (max 24.922). M_total CLOSED 1.199 / 120.360 / 1655.308, OPEN 1.222 / 121.817 / 1654.142, CLOSED-B 1.203 / 120.251 / 1654.501. (M_total includes the rig's own pacing between an input and the heartbeat that releases a delayed output: that is why its p99 is 1.6 s in every arm, open or closed, and why the declared metric is M_bridge.)

### Worst-case six-axis segment `simultaneous-sticks-triggers-60hz` (pooled, ms, n = 45,080 per arm type)

| Run 2 clean | CLOSED p50/p95/p99/max | OPEN | CLOSED-B | floor | abs(OPEN-CLOSED) | within |
| --- | --- | --- | --- | --- | --- | --- |
| M_bridge | 1.176 / 1.640 / 1.822 / 13.065 | 1.199 / 1.678 / 1.884 / 31.831 | 1.180 / 1.639 / 1.803 / 24.922 | 0.004 / 0.001 / 0.019 | 0.022 / 0.038 / 0.061 | yes |
| M_total | 1.176 / 1.641 / 1.822 | 1.199 / 1.678 / 1.884 | 1.180 / 1.639 / 1.803 | 0.004 / 0.001 / 0.019 | 0.022 / 0.038 / 0.061 | yes |

Run 1 clean, same segment: M_bridge abs(OPEN-CLOSED) 0.026 / 0.046 / 0.084 vs floor 0.011 / 0.017 / 0.051, within; M_total the same values.

### Arms, drops, client

Every arm of all four results: accepted, passed, load `verified`, 9,638 timed MIDI (every-message and first-packet sets), 20,513 packets with t1_pre and t1_post, bridge pid gone, bytes identical to CLOSED. OPEN arms: live client proven, snapshot client count exactly 1 throughout, stream dropped **0**, 16,015-16,095 data events per clean OPEN arm, Chromium pids gone. Publisher snapshot overwrite count 23,990 per arm (coalescing, not dropping, and equal in every arm incl. CLOSED).

### Why both runs are VOID (whole-machine sampler every 5 s, `docs/sdauto-gate/scripts/machine_sampler.py`; `arm_validity.py` per arm)

| Run | arm_validity.py | Counted foreign load inside an arm window |
| --- | --- | --- |
| 1 | ALL VALID 9 + 15 arms, max in-arm load1 3.88 | `node .../local-LLM-h14/qwen-bench/../sandbox/broker.mjs prove-gate` **79.3%** at 04:18:12 in sens r1 CLOSED-B: a local-LLM-* bench process above 5% in-arm COUNTS, so the sensitivity run is void and the clean run's receipt with it |
| 2 | **INVALID PRESENT** (sens and clean), max in-arm load1 4.61 | the vault sync `obsidian-headless/cli.js sync` 88-100% for > 10 s in sens r3 CLOSED-B, clean r1 CLOSED-B, clean r3 CLOSED and CLOSED-B; `grep -rl --exclude-dir=workspace build-spec-null /Users/viddyslap/.pi-harness-sc...` (not this lane) 56-76% for ~95 s across sens r1 OPEN and CLOSED-B; the same qwen-bench broker **98.0%** at 04:56:21 in sens r2 OPEN; `git clone --no-hardlinks` 96.2% once in sens r2 OPEN |

Recorded, not counted (lane infrastructure): the engine `local-LLM-engine/engine/server.mjs` above 25% in 67 (run 1) and 66 (run 2) in-arm samples, max 85.7% and 90.2%, and `local-LLM-engine/ops/harness-advance.mjs` up to 51.6%: both NEEDS-MASTER lines in the LANE LOG. WindowServer and kernel_task recorded only.

What this does and does not say: in four qualifying results the view open added 0.03 to 0.09 ms at p99 on M_bridge, the same order as the noise floor, and the planted 2 ms fault was seen as a 5-second jump both times. The measurement is not in doubt; the validity stamp is, because another lane's bench and the vault sync were busy during arms. sdbar3's LANDED M_bridge PASS at 70cebd0 (0.017 / 0.004 / 0.009 ms against 1.018 / 1.064 / 1.073 ms) stands on its own run.

### Laptop

Laptop timing used headless Edge 153.0.4234.32 through the pinned `timing_browser.cjs` and `--rule m_bridge` (`timing.ps1 -Phase sensitivity`, README body with the 51b1d5b BROWSER). The pinned 2 ms sensitivity control at R=3: r1 CLOSED VALID (9,638 timed), r1 OPEN **INVALID**, `URLError: <urlopen error timed out>` from the snapshot monitor; the instrument printed `M_BRIDGE RULE INVALID: sensitivity control did not go RED` and exited 3 (G09). This is the Windows limit sdlive EG measured (the planted whole-stream delay overflows Windows UDP intake, with Edge and with Python). Without its own failing control no laptop timing counts, so the laptop clean R=5 was not run and the Python client was not run (it failed the same way in sdlive EG). The laptop's M_bridge numbers this gate DID take are the eight CLOSED arms in 7e (p50 5.9-7.2 ms, p99 101-303 ms, no sample over 1,000 ms): diagnostic, closed view only.

## 4. THE CONTROLLER VIEW FROM THE BUILT EXE (laptop, headless Edge)

Staged console exe, never the installer, never `--tray`: `STEAMDECK-MIDI-RECEIVER-2.exe --listen 127.0.0.1:46411 --map <LAPTOP WORK>\pfcopy3\config\windows_midi_map.json --dry-run --no-pulse --no-osc-relay --no-browser --no-engines --ui-port 47411`, scratch config = a read-only byte copy of the installed config (38/38 equal to C2's manifest). Ports checked free first. `PYSTRAY_BACKEND=dummy` (C1 proved `pystray._dummy` bundled and honoured; the tray thread raised `NotImplementedError` again here, no icon), BROWSER = venv python `-c pass %s`. Session 0. Client: Microsoft Edge 153.0.4234.32 headless (existing, `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`) driven over DevTools by the existing playwright-core 1.58.2 under Node `C:\Program Files\nodejs\node.exe`, 1440x900, fresh context. The five stills were all taken through that DevTools-driven Edge (not the `--screenshot` flag), so the page was live for every shot.

| Check | Result |
| --- | --- |
| front door ready: 23 labels, live | PASS |
| drill-in L2 card | PASS, title `L2`, rows `L2_SOFT, L2_FULL, L2_SOFT_LAYER_2, L2_FULL_LAYER_2, L_TRIGGER_PRESSURE` |
| List view | PASS, `#viewList` aria-pressed true |
| back to Controller, live | PASS |
| A held (real UDP `BTN_A down` to the exe) lights A | PASS |
| left stick pushed (`L_STICK_X_AXIS 32767`) moves the dot | PASS, cx 305 -> 335 |
| page errors | 0 |
| exe stop | `POST /api/shutdown` 202, exit code 0 in 0.667 s; pids 361012 and 350360 gone; ports free |
| owned browser tree | node and every Edge descendant seen (10 pids) all gone |
| browsers before / after | 0 / 0 in any session, equal |

Copied to the Mac and committed under `docs/showready/screenshots/`, and to `/Users/viddyslap/Documents/ViddyVault/screenshots/sdrc-gate/`. Each was opened after the copy:

| PNG | What it shows |
| --- | --- |
| `laptop-exe-1-controller-front-door.png` | The built 0.5.0 exe's Mappings tab on EDM Show: the Deck picture with all 23 labelled controls and counts (56 / 75 mapped), status `live`, Follow off |
| `laptop-exe-2-drill-in-l2.png` | L2 clicked: its label and trigger outlined in blue, the L2 card open on the right with L2_SOFT note 64, L2_FULL note 66, L2_SOFT_LAYER_2 note 65, L2_FULL_LAYER_2 note 67 |
| `laptop-exe-3-list-view.png` | List view: the action sidebar (BTN_A note 36 ... D-pad macros) with the empty editor pane |
| `laptop-exe-4-a-held-lit.png` | A held by a real UDP press to the exe: the A button filled blue on the picture and the A label highlighted with the live tag `tap` |
| `laptop-exe-5-left-stick-dot.png` | Left stick pushed full right: the L3 dot sits at the right edge of the stick circle (cx 305 -> 335) |

## 5. BAR 5 - ROLLBACK, FROM A FRESH READ ON THE LAPTOP (G04)

C2 downloaded the installer (one laptop curl.exe, exit 0 in 5.2 s), so this gate did not download it again.

| Check | Result |
| --- | --- |
| v0.4.9 installer | 43881072 bytes, sha256 `05a46159b762f33a757218817830666beaa07a629d121a89b75debaa6de351a5` = C2's = GitHub's digest |
| ROLLBACK manifests, fresh re-hash | installed-program 44 rows ok 44 bad 0 extra 0; config 38/38/0/0; localappdata 4/4/0/0 |
| Installed program folder vs C2 manifest | 44 rows, ok 44, bad 0, extra 0: the installer never ran |
| ROLLBACK-STEPS.txt | present, sha256 `4d57354adf99a3dc0c377d1c73c0668035da022b32192e5389f73a369d046d83` (= C2's) |
| Every path in the steps | exists, except three the steps describe as created LATER by Ben or by 0.5.0: `PROGRAM\config\engines\osc_sync.json` (step B creates it), `PROGRAM\config\state\` and `PROGRAM\config\bridge.local.json` (step E, 0.5.0 creates them). The two paths with spaces were re-checked literally: `C:\Program Files\STEAMDECK MIDI Receiver 2` True, `C:\Users\Ben\AppData\Local\STEAMDECK MIDI Receiver 2` True (G11) |
| Location | ROLLBACK and STAGING are under `C:\Users\Ben\Documents\`, no reparse point, no `OneDrive` in the path; `C:\Users\Ben\OneDrive\Documents\steamdeck-midi-showready` does NOT exist. Explorer's Documents known folder is `C:\Users\Ben\OneDrive\Documents`, so **in Explorer, "Documents" is NOT where the pack is**: open `C:\Users\Ben\Documents\steamdeck-midi-showready` by typing the path |

Reading the steps as Ben would, three places could trip him:
1. B2 "Create a new file ... osc_sync.json": Notepad saves as `osc_sync.json.txt` unless "Save as type: All files" is chosen. A `.txt` file is silently ignored (the engine loader reads `*.json`).
2. Every "ROLLBACK\..." and "Documents" mention: Explorer's Documents is the OneDrive one (above). The steps do give the full `C:\Users\Ben\Documents\...` path at the top; use it.
3. B is now OPTIONAL in practice (5c below): the 0.5.0 home default resolves to the same OSC preset file on this laptop. Doing B is still safe and still recommended as a belt.

### 5c. Emulated install on a scratch copy (never the installer, never the real tree)

`C:\Program Files\STEAMDECK MIDI Receiver 2\config` was read (FileShare ReadWrite, read access only) into `LAPTOP WORK\pfcopy3\config` (38/38 equal to C2's manifest), copied to `emulated-install3\config`, and the 0.5.0 installer's `[Files]` flags (installer/windows/steamdeck-midi-receiver-2.iss) applied from the clone at CANDIDATE:

| Target | Flag | Action on this laptop's config |
| --- | --- | --- |
| windows_midi_map.json, windows_receiver_settings.example.json, actions.yaml, engines.factory\*.json (14) | ignoreversion | WRITTEN (overwritten) |
| windows_receiver_settings.local.json, presets\default.json, macro_library.json, engines\README.md | onlyifdoesntexist | KEPT (all four already exist) |

After it, `engines.factory\osc_sync.json` has no `osc_preset_path` and `engines\osc_sync.json` does not exist. A second copy (`emulated-override3`) got the ROLLBACK-STEPS B file (`name`, `type`, `enabled`, `osc_preset_path` from the installed factory file, value never printed). Both trees: every engine except osc_sync and stageflow_bridge `enabled:false`; those two pointed at my own loopback sinks (REST 127.0.0.1:48180, OSC 127.0.0.1:48170, a python listener with recorded pids); the non-loopback scan found **0** IPv4, **0** URLs, **0** host keys in each tree before boot. The override copy therefore also carries `rest`/`osc` keys pointing at the sinks (a declared addition to the four keys in step B; it does not touch `osc_preset_path`).

Run: staged console exe, engines ON, `--dry-run --no-pulse --no-osc-relay --no-browser --ui-port 47411 --listen 127.0.0.1:46411`, then `POST /api/engines/osc-sync/resync` and `GET /api/logs/tail` (G06).

| Arm | Engines loaded | OSC Sync resolved path SHAPE | exists | targets parsed |
| --- | --- | --- | --- | --- |
| WITHOUT the user override (install as is) | OSC Sync, StageFlow Bridge, active | `<home>\OneDrive\Documents\Resolume Arena\Shortcuts\OSC\STEAMDECK V2.xml` | **true** | 207 |
| WITH the ROLLBACK-STEPS override | same | `C:/Users/<user>/OneDrive/Documents/Resolume Arena/Shortcuts/OSC/STEAMDECK V2.xml` | **true** | 207 |

**An install from STAGING keeps OSC Sync working on this laptop, with or without the override**: both resolve to the same existing preset file and parse 207 wigglable targets. Every run: shutdown 202, exit 0 in 0.6-0.8 s, exe and sink pids gone, ports free, browsers 0/0, sink received 0 TCP and 0 UDP (nothing was sent anywhere).

### 5b. Resolume files from the staged build, engines ON, path keys removed

Tree `b53\config` = installed config copy with `osc_preset_path` removed (the installed files carry no `comp_path`), same enable and loopback rewrite, scan 0/0/0.

| Engine | Found and loaded | Resolved path SHAPE | exists |
| --- | --- | --- | --- |
| osc_sync | loaded, active; resync parsed **207** targets from its file | `<home>\OneDrive\Documents\Resolume Arena\Shortcuts\OSC\STEAMDECK V2.xml` | true |
| stageflow_bridge | loaded, active; it NEVER reads comp_path at runtime (F4, pre-existing), so "loaded its file" cannot be observed; the home default was computed the same way (`Path.home()` + suffix) | `<home>\OneDrive\Documents\Resolume Arena\Compositions\5-5-26 STEAMDECK V2.avc` | true |

No file-not-found finding. The Resolume files were read (osc_sync) or only stat'ed (comp), never written.

### 5d. Interpreter match

| Build | Bundled interpreter (read-only byte search for `python3NN.dll`) |
| --- | --- |
| installed v0.4.9 console exe (FileVersion 0.4.9) | `python312.dll` x2, nothing else |
| staged 0.5.0 console exe (FileVersion 0.5.0) | `python312.dll` x2 |
| staged 0.5.0 tray exe | `python312.dll` x2 |

Both builds bundle **Python 3.12** (C1 built with 3.12.10; C1's archive viewer lists `python312.dll`). No mismatch. On the laptop, Python 3.12.10 (the clone venv, same minor) reports: `monotonic` = GetTickCount64(), resolution **0.015625 s (15.6 ms)**; `perf_counter` = QueryPerformanceCounter(), resolution **1e-07 s (0.1 microsecond)**. In plain words: both versions run the same Python, so their clocks behave the same; the everyday "monotonic" clock on this laptop only ticks every 15.6 thousandths of a second, which is why every timing number in this lane uses the fine perf_counter clock instead.

## 6. STAGED, NOT RUN

| Check | Result |
| --- | --- |
| STAGING SHA256SUMS.txt | 3 entries, 0 bad (G04) |
| processes running from STAGING or ROLLBACK | 0 (G04, G11) |
| installed program folder = C2 MANIFEST | 44/44 (G04) |
| `git ls-remote --tags origin v0.5.0` | empty (11:23:54Z) |
| GitHub releases API tag v0.5.0 | HTTP 404 (11:23:54Z); v0.4.9 asset re-read: 43881072 bytes, `sha256:05a46159...51a5` |
| `git ls-remote origin main` | `5d778eb90a2baa85b98ffa9ff11571a9aca0ce39`: unchanged; this lap did not move it |

## 7. LAPTOP STATE, BOTH ENDS (G01 at 09:30:10Z, G12 at 10:48:58Z)

| Field | Start | End |
| --- | --- | --- |
| tray 5268 | session 1, created 2026-08-16T06:29:37.4311370Z | same |
| tray 23640 | session 1, created 2026-08-16T06:29:37.8390240Z | same |
| loopMIDI 16020 | created 2026-08-16T06:29:31.9633500Z | same |
| UDP 45123 / TCP 7723 owner | 23640 / 23640 | same |
| Program Files file count, newest LastWriteTimeUtc | 44, 2026-08-06T20:13:05.8036846Z `\config\osc_relay.json` | same |
| orphan HEAD, porcelain | d1367870b939..., 0 | same |
| clone HEAD, porcelain | 2e4292a..., 0 | same |
| browsers (chrome/msedge/firefox), any session | 0 | 0 |
| python processes | 0 | 0 |

No config change to attribute. PROCESS-CLASS ORDER listing at the end (G11): PROTECTED 100, RECORDED alive 0, LANE PATH UNRECORDED 0, NOT LANE 170; no NEEDS-MASTER browser or process line. (My final listing script read 0 recorded pids from the record files, an instrument slip of mine; every pid this gate started was proved gone by the script that started it: G03, G06, G07, G08, G09 via Invoke-TrackedPython, G10, and the w100 arms.)

## 7e. THE FOUR ITEMS OWED FROM sdpolish

### Idle smoke against the BUILT exe

`idle_smoke.py` cannot boot an exe: it boots `windows.win_recv` from a source tree with a Python (`--tree`, `--python`; no exe option). So its method was replicated for the frozen exe in `exe_run.ps1 -Mode Idle` (declared deviation): the exe's whole process tree (PyInstaller bootloader + child) is sampled with `Get-Process ... TotalProcessorTime` before and after a 60 s idle; CPU-time delta / wall time, as a percentage of ONE core. `--dry-run --no-ui --no-engines --no-pulse --no-osc-relay`, non-default UDP port, scratch config. v0.4.9 is a byte copy of the installed console exe taken from ROLLBACK (sha256 equal to the installed manifest), run from LAPTOP WORK, never from Program Files.

Beside it, same session, same machine: `idle_smoke.py --cpu-self-test` exit 0, **busy 86.18% of one core (3.6094 s)**, **idle 0.0% (0.0 s)**, passed true. The reader is live.

| Pair | Candidate 0.5.0 exe | v0.4.9 exe | Difference (points) |
| --- | --- | --- | --- |
| 1 | 0.650% (0.3906 s / 60.14 s) | 0.156% (0.0938 s / 60.28 s) | **0.494** (over the 0.4 tripwire) |
| 2 | 0.650% (0.3906 s / 60.13 s) | 0.052% (0.0312 s / 60.13 s) | **0.598** (over the 0.4 tripwire) |
| 3 | 0.494% (0.2969 s / 60.13 s) | 0.104% (0.0625 s / 60.13 s) | 0.390 |
| **mean of paired differences** | | | **0.494 points vs the 0.2 bar: OVER** |

Reader resolution: Windows CPU time advances in 15.625 ms quanta, 0.026 points over 60 s; the differences are 15-23 quanta, not a quantisation artefact. All six arms far under the 5% bar. The UI-on shutdown arm: candidate `POST /api/shutdown` 202, exit 0 in 0.763 s; v0.4.9 has no `/api/version` or `/api/shutdown` (404, as ROLLBACK-STEPS A3 says), so it was stopped by its recorded pid tree. All 16 pids gone, browsers 0/0 (G08). This frozen figure is NOT comparable to sdpolish P0's source-run 0.19: different process shape (onefile bootloader + child). UNATTRIBUTED: no profiler was run on the frozen exe. For the master to rule on; it does not touch bars 1, 2, 3 or 5.

### The laptop over-100 ms rate, BASE vs CANDIDATE, arm order AND reverse order

Declared before the data (master 13, 19:23 (3)): if reversing the order moves the asymmetry it was ORDER; if not, it is the REVISION. BASE = 70cebd0 (sdauto's base of lap, the BASE sdstall measured), HEAD = CANDIDATE 2e4292a. Instrument: sdstall's CLOSED-only wrapper (docs/sdstall-s1/scripts/closed_only.py, unchanged, sha256 44b8fb1f...) driving the pinned timing_ab arm code; `git archive` zips railed and re-verified on the laptop (base.zip 438e0491..., head.zip bc27903c..., fixtures.zip a806a8b8...: SHA256_MATCH). Every arm accepted and passed, 9,638 timed messages each, no sample over 1,000 ms.

| Order | Arm | Rev | over 100 ms | max ms | p50 / p95 / p99 ms |
| --- | --- | --- | --- | --- | --- |
| forward | a01 | BASE | 634 (6.58%) | 352.2 | 5.90 / 117.07 / 205.22 |
| forward | a02 | HEAD | 1071 (11.11%) | 290.0 | 6.65 / 173.04 / 247.07 |
| forward | a03 | BASE | 100 (1.04%) | 181.0 | 7.24 / 51.52 / 100.69 |
| forward | a04 | HEAD | 553 (5.74%) | 355.0 | 6.22 / 109.60 / 223.74 |
| reverse | a05 | HEAD | 573 (5.95%) | 303.6 | 6.32 / 110.73 / 199.88 |
| reverse | a06 | BASE | 865 (8.97%) | 392.3 | 5.87 / 161.99 / 303.12 |
| reverse | a07 | HEAD | 697 (7.23%) | 294.2 | 6.58 / 130.37 / 201.16 |
| reverse | a08 | BASE | 887 (9.20%) | 394.0 | 6.30 / 159.12 / 284.39 |

Forward order (BASE first in each pair): BASE mean 3.81%, HEAD mean 8.43%, HEAD worse. Reverse order (HEAD first): HEAD mean 6.59%, BASE mean 9.09%, BASE worse. **Reversing the order moved the asymmetry: by the declared rule it is ORDER, not the REVISION.** In both orders the second arm of each pair ran worse.

### F5, three unguarded LOCALAPPDATA subscripts

`grep -n "LOCALAPPDATA\['\|environ\['LOCALAPPDATA" -r scripts tests windows` at CANDIDATE: **3 hits**, the known three:
- `scripts/showready/ab_run.py:28`
- `scripts/showready/ab_run.py:33`
- `tests/test_showready_instrument.py:74`

engine_ab with LOCALAPPDATA UNSET: Mac, every run above under `env -u LOCALAPPDATA`, exit 0. Laptop (G10, `Remove-Item Env:\LOCALAPPDATA`, then `engine_ab.py --candidate 2e4292a... --preset <windows-installed EDM Show>`): **exit 1, `"error": "KeyError: 'LOCALAPPDATA'"`**, pid gone. The KNOWN state, not a gate failure.

### The no-push form

| Reading | Gate start (09:29:52Z) | Gate end |
| --- | --- | --- |
| `git ls-remote origin main` | `5d778eb90a2baa85b98ffa9ff11571a9aca0ce39 refs/heads/main` | same at 11:23:54Z |
| `git ls-remote --tags origin` | 42 tag refs, newest v0.4.9 -> e66ff44 | identical, `diff` exit 0 (no v0.5.0) |
| `git tag --list 'v0.5*'` (local) | 0 | 0 |

## 8. MUTATIONS - THE INSTRUMENTS STILL BITE AT CANDIDATE

| Mutation | RED | Restored |
| --- | --- | --- |
| (a) EDM Show BTN_A note +1 in the candidate arm's copy (`ab_run.py --candidate 2e4292a... --preset <mac EDM Show> --section windows --control sensitivity --mapping BTN_A`) | **exit 1**, `different_mappings: ["BTN_A"]` in B1 and B2, 56/56 exercised | unmutated `mac-edm` run: exit 0, 0 different |
| (b) 2 ms publisher delay (`timing_ab.py --rule m_bridge ... --control sensitivity`, R=3) | **exit 1**, `m_bridge_sensitivity_timing_red: true`, M_bridge abs(OPEN-CLOSED) p99 10574.606 ms (run 1) and 10857.613 ms (run 2) | clean R=5 without the delay: exit 0, p99 0.094 / 0.067 ms, within (both runs load-VOID, see bar 3) |
| (c) one byte flipped (offset 10499312, XOR 0xFF) in a COPY of the staged tray exe, checked against its SHA256SUMS line | **RED**: `SUMS_BAD STEAMDECK-MIDI-RECEIVER-2-Tray.exe` | byte written back: 1 entry, 0 bad |
| (d) `actions.yaml` sha256 set to 64 zeros in a COPY of MANIFEST-config.sha256.tsv | **RED**: `MANIFEST_BAD actions.yaml`, 37 ok 1 bad | line restored: 38 ok, 0 bad |

(My verify script prints the BAD line inside the count tuple, which shifts the printed fields by one in the RED rows of G04; the BAD line itself is the verdict and the counts above are read correctly.)

## WHAT CHANGED SINCE v0.4.9, IN BEN'S WORDS

`git log --oneline e66ff44..2e4292a` 80 commits; `windows/ config/` 42 files, +4396 -334.

| Change | What you will see | Proved by |
| --- | --- | --- |
| Controller view | Mappings opens on a picture of the Deck with 23 labelled controls and counts; click one for its card; List is one click away | sdview gate (every edit lands on disk exactly), sdfix and sdpolish gates (layout geometry 8175/8175), this gate on the BUILT exe in Edge |
| Live view | While the page is open, pressed controls light up, stick and trackpad dots move, trigger bars fill; Follow (off by default) opens the card of what you press | sdlive gate (34/34 in real Chromium), this gate on the built exe |
| Preset sections | One preset file can hold a Windows and a MacBook section; the header shows which is in use | sdcore and sdcore2 gates |
| Fan-out | The Deck can send to two receivers at once with identical bytes | sdcore gate |
| Autopilot persistence | Autopilot remembers its channel choices across a bridge restart (config\state\) | sdauto A1 and AG |
| API routes | /api/version, controller-map, live snapshot and stream, engine config and autopilot state routes | sdview gate API bar, sdauto AG 31/31 |
| F5 | Quitting from the web page (/api/shutdown) exits cleanly | sdauto AG, this gate (exit 0 in 0.6-0.8 s, 6 boots) |
| F2 | The bridge no longer spins a core and Ctrl-C works | sdauto AG, sdpolish P0 |
| F4 | The header is one row at 1440x900 | sdauto AG |

## KNOWN LIMITS

- **Nothing unexpected on the laptop's screen:** Ben confirmed at about 11:06 on 2026-09-15 that nothing unexpected appeared on the laptop's desktop ("No, nothing unexpected"), and sdpick's K1 and KJ session-aware listings found 0 browsers in all sessions. This gate's listings: 0 browsers in any session at every check (G01, G07, G08, G11, G12).
- **NOT COVERED mappings:** none. Every mapping in EDM Show (56), PTZ (52) and default (56) was exercised on both machines.
- **Windows skips:** the six named in section 1, all POSIX-only or a not-yet-wired remap.
- **Bar 1 QUALIFIED:** by the three d136787 username hunks (section 2); no MIDI path.
- **The laptop rig's over-100 ms rate:** on the laptop, in the closed-arm rig where the sender shares the bridge's process, 3 to 7 percent of messages take over 100 ms from send to MIDI record, at BOTH revisions, never reaching 1,000 ms. UNATTRIBUTED between bridge receive lag and in-process sender contention; separating them needs a receive-seam timestamp the instrument does not take. It is present at BASE as strongly as at HEAD, so the installed v0.4.9 has it too and nothing in the candidate introduces it; the one topology difference that could explain it is the one the show does not have, because on Friday the sender is the Steam Deck across a network, not a thread inside the bridge's own process (master 13, 19:23 (1) and (2)). THIS GATE'S READING: 1.04% to 11.11% per arm today (section 7e), and the BASE/HEAD asymmetry followed arm ORDER, not revision.
- **AG finding F4, PRE-EXISTING:** `stageflow_bridge` resolves `comp_path` under HOME but never reads it at runtime (docs/sdauto-gate/REPORT.md; master 13, 16:32).
- **Bar 3 history:** sdauto's bar 3 RED stands on its own run and is HELD owner sdstall; sdstall measured NOT REPRODUCED on a quiet Mac and a quiet laptop (59 CLOSED arms, zero samples over 1,000 ms at BASE and HEAD, both readings agreeing) with the INFERENCE-ACTIVE case UNTESTED because the lms split went degenerate.
- **Windows bar 3 does not count:** the pinned 2 ms sensitivity control cannot produce a valid OPEN arm on the laptop (this gate: `URLError timed out`, exit 3; sdlive EG: UDP intake overflow), so laptop timing is diagnostic only; Mac bar 3 is NOT COUNTED this gate by foreign load (section 3). Your bar 4 hardware check cannot see millisecond delay.
- **The Windows UI sidecar visibility limit (a limit of the ARM, not the product; source docs/sdpolish-p0/REPORT.md):** "the UI sidecar arm proves the sidecar constructs without raising in a session-0 service context; it does NOT prove a tray icon is visible, and the bridge logged neither a tray start nor the `system tray unavailable:` warning that windows/win_recv.py emits on failure." sdpolish PG did not measure visibility (its report says only that the sidecar is available in the rail session), so this limit ships as written. In THIS gate's exe runs the sidecar was the dummy backend on purpose (no icon possible).
- **GET /api/midi/ports** is tested on the Mac only, because on the laptop it would enumerate loopMIDI.
- **Windows idle CPU of the built exe:** 0.494-point mean paired difference vs v0.4.9 (section 7e), over the 0.2 rule, tripwire on 2 pairs; unattributed; for the master.
- **engine_ab on Windows with LOCALAPPDATA unset** exits 1 with KeyError (F5 residue, 3 sites, instrument only).
- **F2 log noise with `--no-engines`:** every axis datagram logs `engine_registry.on_axis_event failed ... NoneType` (C1 F2, pre-existing since v0.4.4, visible again in step 4). The show runs engines ON and never reaches it.
- **Build script F1 (C1):** a fresh clone needs an empty `build\` before `build_exe_v2.ps1`; it does not change what is built.
- **UNVERIFIED-BY-EXECUTION:** the staged Tray exe was not started; the installers were not run (by rule); real MIDI to loopMIDI and Resolume's reaction (that is bar 4).

## BAR 4 CHECKLIST - BEN, ABOUT 15 MINUTES, REAL DECK AND RESOLUME

Before you start: everything lives in `C:\Users\Ben\Documents\steamdeck-midi-showready\` (type that path into Explorer; Explorer's "Documents" is the OneDrive one and does not have it).

1. **Backup is fresh?** If you changed presets, macros or settings since 2026-09-16 03:23, copy `C:\Program Files\STEAMDECK MIDI Receiver 2\config\` to a new folder in `rollback-v0.4.9\` (for example `config-2026-09-18\`) now.
2. **OSC Sync override (ROLLBACK-STEPS B), while still on v0.4.9:** open `PROGRAM\config\engines.factory\osc_sync.json` in Notepad, copy the path after `"osc_preset_path":`, close without saving. Create `PROGRAM\config\engines\osc_sync.json` exactly as step B shows, pasting the path. In Notepad's Save dialog choose **Save as type: All files**, or it becomes `osc_sync.json.txt` and is ignored. (This gate measured that 0.5.0 finds the same preset file even without this step; it is a belt.)
3. **Install:** quit the tray from its menu, then run `candidate-2e4292a\STEAMDECK-MIDI-RECEIVER-2-Setup-0.5.0.exe` (sha256 9232d8c4...65a1).
4. **Confirm version:** open `http://127.0.0.1:7723/api/version` - it must say `"version":"0.5.0"` and `"git_commit":"2e4292a75f08674fdf5c78358485b27c2d3bd913"`. The status bar bottom right shows v0.5.0.
5. **Press through the controller view, one group at a time,** with the Mappings tab on Controller and the status reading `live`: face buttons A B X Y; D-pad; L1 R1; L2 R2 soft and full (watch the bar fill); L4 L5 R4 R5; both sticks (dots move, L3/R3 clicks light); both trackpads (dot appears while you touch); gyro; SELECT and START. Each press should light that control, and in Resolume the same thing should happen as on v0.4.9.
6. **OSC Sync:** press your OSC Sync control (or Engines tab, OSC Sync resync). It should report the same target count as before (this gate read 207 from your file) and wiggle as usual.
7. **Scenes:** switch to EDM Show, run a few scene changes and confirm Resolume reacts; switch to PTZ and confirm the PTZ scenes and cameras react.
8. **Closed page:** close the browser tab and press a few buttons; Resolume should react exactly the same.
9. **If anything is wrong, roll back:** follow `rollback-v0.4.9\ROLLBACK-STEPS.txt` section C (quit tray, run the v0.4.9 installer from `installer\`, copy `config\` back over PROGRAM\config, start the tray, check `/api/version` says 404). Section D is the fallback copy of the whole program folder.

## APPROVALS THAT REMAIN BEN'S

- Installing 0.5.0 on the laptop.
- Creating the v0.5.0 tag and GitHub release.
- Merging `chain/steamdeck-20260914` to main.

## EVIDENCE

`docs/showready/evidence/` holds every laptop transcript G00-G13 (the one carrying a Resolume path was redacted to `<home>` / `<user>`), the Mac suite output, and the bar 3 tables. Scripts that ran on the laptop are not committed (docs only); their full outputs are the G files.
