GUARD GREEN at the gate's LAST laptop act: `win_guard.ps1 -Mode compare -Baseline wg\step0-snapshot.json` exit 0, and the independent step 0 vs step 7 record is byte-identical (`diff` exit 0, 49 lines each). W4's interrupted interval also compared GREEN against W4's ORIGINAL baseline (exit 0). No change to the tray, its ports, Program Files, installed user config, loopMIDI or the orphan checkout.

# sdwin GATE (WG) - independent measurement of W1..W4

Gate: claude-rc on the Mac, unsandboxed. Branch `chain/steamdeck-20260914`.
Entry HEAD `27e3ad0d48be2c93c6842952338b4d57359252f7` (evidence-only on W4's tested
code `b3b2861`; `git diff b3b2861 27e3ad0 -- scripts windows config deck protocol tests mac installer` = 0 lines).
Scratch: `/tmp/sdwin-gate/` on the Mac, `C:\Users\Ben\AppData\Local\Temp\sdwin\wg\` on the laptop.
Every laptop act went through the pinned `scripts/showready/win_rail.sh`. Evidence files are under
[evidence/](evidence/); the gate's own ps1 scripts are under [evidence/ps/](evidence/ps/).

Verdict in one line: BAR 2 HOLDS at HEAD on both OSes. BAR 1 HOLDS FOR DIRECT MAPPING MIDI
(every mapping, both OSes, every arm pair identical, recomputed from raw captures) but is
QUALIFIED: engines are off in the instrument, and EDM Show's mappings are identical to default's,
so the only EDM-Show-specific behaviour (its engines) is NOT COVERED. Details in 4b and For Ben.

## For Ben

1. **EDM Show as replayed is the same thing as default as replayed.** Its 56 mappings equal
   `default.json`'s 56 mappings exactly (`mappings equal: True`, python comparison of the fixtures);
   the only difference is the `engines` block (12 engines on). The instrument runs `--no-engines`,
   so bar 1 proves the candidate sends identical bytes for every mapping, but says NOTHING about
   engine behaviour. Engine code is unchanged since v0.4.9 (`git diff --stat e66ff44 HEAD -- windows/engines windows/midi.py config/engines.factory` empty), but the code that builds and shuts engines down did change (windows/win_recv.py, windows/receiver.py). NOT COVERED, by name:
   - **L_PAD_LEFT, L_PAD_LEFT_LONG_PRESS, L_PAD_RIGHT, L_PAD_RIGHT_LONG_PRESS (EDM Show, notes 82/86/83/87 ch0).** With autopilot loaded and a channel enabled, the receiver asks `should_emit_note` (windows/receiver.py:179-189 -> windows/engines/registry.py:86-100) and autopilot DEFERS the note to the next beat or DROPS a second one (windows/engines/autopilot.py:753-772), re-emitting it later (autopilot.py:775-785). Channel enable comes from ch14 CC60/70/80 feedback, not from the Deck. In PTZ autopilot is off, and an inactive owner's filter is skipped (registry.py:96-100).
   - **Engine-emitted MIDI on the same output (no mapping produces these bytes):** l_stick_layer sends CC110-113/118-121 on L_STICK axes (windows/engines/l_stick_layer.py:196-209), with LEFT_STICK_CLICK_L3 note 72 as its set toggle (l_stick_layer.py:89, 159). gyro_feedback sends CC122-124 on gyro axes after L4 (ch2 CC74) (windows/engines/gyro_feedback.py:336-353). global_color sends its resync CC99=127 on ch14 at bind (windows/engines/global_color.py:265-281, config/engines.factory/global_color.json channel 14, resync_cc 99). audio_opacity sends MIDI only when its protocol is not osc; the installed user `engines\audio_opacity.json` protocol is UNVERIFIED-BY-EXECUTION.
   - **The axis path differs from live:** with engines off, `_handle_axis_event` calls `self._engine_registry.on_axis_event` on None and logs a caught AttributeError on every axis event (windows/receiver.py:877-881) before mapping dispatch. Same on both arms, so bytes are unaffected, but the live path is not the replayed path.
   - Identity holds under the instrument's CONTROLLED clock (`--clock script`). W3's wall-clock A/A (`aa-wall-noise`) was NOT identical (1079 vs 1070 messages): real timing is bar 3, not bar 1.
   Every mapping type in EDM Show and PTZ WAS exercised (56/56 and 52/52); no mapping is unexercisable. The gap is the engines, and a later lap that touches them has to add coverage.
2. **Upgrade risk, OSC Sync (installed-build join, QUALIFIED-BY-NAME).** The installed tray's `config\engines.factory\osc_sync.json` sets `osc_preset_path` (shape `C:/Users/<user>/.../<name>.xml`, a real username, not the USERNAME placeholder), and there is NO user override `config\engines\osc_sync.json`. The installer copies `engines.factory\*.json` with `ignoreversion` (installer/windows/steamdeck-midi-receiver-2.iss:62), so installing a build from this branch replaces that file with the branch's `C:/Users/USERNAME/...` path. OSC Sync (CC90 on zero-based ch14) would then look for a file that does not exist, until lap sdauto fixes the defaults or the user config sets the key. `comp_path` is ABSENT from the installed stageflow_bridge configs, so the branch's code default applies; W4's source read says it is never read after assignment (UNVERIFIED-BY-EXECUTION).
3. **First-run launcher note (PRE-EXISTING, not show-relevant).** With NO `windows_receiver_settings.local.json`, all three launchers exit 1 at line 35 (`PropertyNotFoundStrict`), on HEAD and on the v0.4.9 copies alike. The installed tray starts from the Run key / shortcuts straight into the EXE with `--tray` (installer .iss:49, 66-67, 70), not through these launchers, and the laptop's settings file exists. So it does not touch Friday.
4. Bar 2 holds: Windows `Ran 840 tests` `OK (skipped=5)` exit 0 in the clone at HEAD.

## Step 00 - W4 debt (laptop lost during W4)

W4's envelope and REPORT say the final capture retrieval, final Windows suite, final guard compare and
global cleanup proof were UNPAID. The laptop answered ssh when the gate started (`ssh ... hostname` exit 0, `ViddySlaptop`).

| Act | Command | Exit | Result |
| --- | --- | ---: | --- |
| (a) process inventory | `win_rail.sh run wg evidence/ps/inventory.ps1` | 1 (a listing bug AFTER the process rows; the rows were complete) | CIM match on cmdline `*sdwin*` / `*steam-deck-midi-rc*` / exe under CLONE or WORK / W4's 15 recorded PIDs: 1 match, the gate's own cmd.exe. All python/pythonw on the machine: 0. All 15 W4 final PIDs (266512 ... 254412): alive=False. Nothing stopped, because nothing lane-owned was running. [00-inventory.txt](evidence/00-inventory.txt) |
| (b) guard vs W4 ORIGINAL baseline | `win_guard.ps1 -Mode compare -Baseline sdwin\w4\before.json -Out wg\compare-vs-w4-before.json` | 0 | `GUARD GREEN: compare; protected state observed; pythonProcesses=0` [00b-guard-vs-w4.txt](evidence/00b-guard-vs-w4.txt) |

W4's final QPC raw results still on the laptop were NOT retrieved by the gate. They are superseded by
the gate's complete HEAD matrix below (same code as b3b2861), and the post-matrix Windows suite is step 2.
Minor W4 wording finding: the committed `docs/sdwin-w4/evidence/before.json` (sha256 1b0c3c0d...) is
PARSED-EQUAL but not byte-identical to the laptop's `w4\before.json` (sha256 50aa227c..., CRLF and indentation);
W4 called it "identical".

## Step 0 and step 7 - guard plus independent record, side by side

Guard: `win_guard.ps1 -Mode snapshot -Out wg\step0-snapshot.json` exit 0 (GREEN); final
`-Mode compare -Baseline wg\step0-snapshot.json -Out wg\step7-final.json` exit 0 (GREEN), LAST laptop act at 19:47 MDT.
Independent record ([evidence/ps/indep.ps1](evidence/ps/indep.ps1)): netstat.exe, not Get-NetUDPEndpoint; Win32_Process, not Get-Process;
.NET EnumerateFiles, not Get-ChildItem; .NET SHA256, not Get-FileHash; raw `git --no-optional-locks`.

| Field | Step 0 | Step 7 |
| --- | --- | --- |
| UDP 0.0.0.0:45123 owner (netstat) | 23640 | 23640 |
| TCP 127.0.0.1:7723 LISTENING owner | 23640 | 23640 |
| STEAMDECK-MIDI-RECEIVER-2-Tray.exe | 5268 @2026-08-16T06:29:37.4311370Z; 23640 @06:29:37.8390240Z | same |
| loopMIDI.exe | 16020 @2026-08-16T06:29:31.9633500Z | same |
| Program Files file count / newest LastWriteTimeUtc | 44 / 2026-08-06T20:13:05.8036846Z config\osc_relay.json | same |
| Installed user config (38 files, .NET sha256) | e.g. presets\EDM Show.json 90b2d19e..., presets\PTZ.json 450f2edf..., windows_midi_map.json f55c0509..., presets\.active cc768739... | all 38 identical |
| Orphan HEAD / porcelain lines | d1367870b939... / 0 (exit 0) | same |
| python processes (all, machine-wide) | 0 | 0 |

`diff 0-indep.txt 7-indep.txt` (label lines excluded) exit 0. [0-indep.txt](evidence/0-indep.txt), [7-indep.txt](evidence/7-indep.txt).

## Step 1 - pins and fixture manifests

| Check | Command | Exit | Result |
| --- | --- | ---: | --- |
| Mac pins at HEAD | `shasum -a 256 -c scripts/showready/SHA256SUMS` | 0 | 7/7 OK |
| Laptop clone update | `git -C CLONE pull --ff-only` (in [pins.ps1](evidence/ps/pins.ps1)) | 0 | clone b3b2861 -> 27e3ad0, porcelain 0, v0.4.9 peeled e66ff44 |
| Laptop pins | Get-FileHash of every SHA256SUMS entry | 0 | 7/7 equal to the Mac hashes |
| Mac manifests | `python3 evidence/verify_manifest.py mac windows-installed` | 0 | 16/16 entries: before=after=copy and bytes |
| Mac manifest control | same, on a /tmp copy with one byte appended to PTZ.json | 1 | `BAD 458c4a48f3ef 16726 presets/PTZ.json` ([fxctl.txt](evidence/fxctl.txt)) |
| Laptop manifests | Get-FileHash vs MANIFEST under `sdwin\fixtures` | 0 | mac 5/5, windows-installed 11/11; the manifest files themselves hash 0c1b3014... and 7c6dad5b..., equal to the Mac copies |

Rig note: the first pins.ps1 run died on PowerShell's stderr-as-error handling during `git pull` (exit 1).
The pull itself had completed (the rerun showed clone_head_before=27e3ad0 and `Already up to date.`).

## Step 2 - BAR 2 (full suites at HEAD 27e3ad0)

| Host | Command | Ran line | Final line | Exit |
| --- | --- | --- | --- | ---: |
| Mac | `TMPDIR=/tmp/sdwin-gate/mactmp PYSTRAY_BACKEND=dummy BROWSER=true .venv/bin/python -m unittest discover -s tests -p "test_*.py"` | Ran 840 tests in 7.853s | OK (skipped=2) | 0 |
| Windows clone | `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"` via [suite.ps1](evidence/ps/suite.ps1), run AFTER W4's interrupted matrix | Ran 840 tests in 19.896s | OK (skipped=5) | 0 |

Windows launcher PID 272668 and child 275496 proved gone; python processes after = 0. BAR 2 HOLDS.
Skips named from a separate `-v` run (Ran 840, OK skipped=5, exit 0; [skips](evidence/2-win-suite-verbose-skips.txt)):
- test_global_color.CcBaseOffsetTests.test_cc_base_override_remaps_channel_ccs: pre-existing deferred cc_base remap (also skipped on the Mac).
- test_section_launchers.MacSectionLauncherTests.test_local_section_is_passed_as_one_argument_and_missing_file_still_works: needs POSIX bash.
- test_showready_rail.ShowreadyTransportTests.test_remote_status_stderr_arguments_and_scp_failure: the Mac rail needs POSIX bash (runs on the Mac).
- test_showready_rail.ShowreadyTransportTests.test_unsafe_arguments_are_refused_before_transport: same.
- test_upgrade_boot.MacLauncherSnippetTests.test_section_snippet_creates_missing_file_and_preserves_existing_bytes: needs POSIX bash and paths.
Mac skips: the cc_base test, plus test_showready_rail.ShowreadyGuardTests.test_clean_changed_missing_and_python_observations (needs PowerShell; runs on Windows).

## Step 3 - mutations (each RED, restore, GREEN)

Mac mutations ran in a /tmp git clone of the run root (`/tmp/sdwin-gate/mut/repo`, `repo-d`) against the run root's verified
fixtures, `--speed 50` (accelerated control, not rate credit), windows-installed EDM Show fixture. Driver: [mutations.sh](evidence/mutations.sh); exits: [results/mutations/EXITS](results/mutations/EXITS).

| Mutation | How | RED exit and what it named | Restore | GREEN exit |
| --- | --- | --- | --- | --- |
| (a) EDM Show mapping note +1 in the candidate tree | commit `8e27e05` on clone branch mut-a: windows/receiver.py `_emit_note_on` sends note 41 for ch0 note 40 (BTN_X) | `ab_run --candidate mut-a` exit 1, `different_mappings=["BTN_X"]`, 56/56 exercised | candidate 27e3ad0 | 0 |
| (a') same, instrument's own config mutation | `--control sensitivity --mapping BTN_X` | exit 1, `different_mappings=["BTN_X"]` | - | (a) GREEN |
| (b) recorder records nothing | clone capture_runner.py `if not self.dead:` -> `if False:` | exit 1, messages 0/0, mappings_exercised 0, all 56 unexercised (not a vacuous pass) | `git checkout`, `cmp` equal | 0 |
| (c) one Action ID removed from the script | clone deck_script.py skips BTN_X (script 728 steps, 46419 packets) | exit 1, `unexercised_mappings=["BTN_X"]`, 55/56 | `git checkout`, regenerated script sha 9256621a... | 0 |
| (d) win_rail.sh exits 0 regardless | `repo-d` rail: `ssh ... \|\| true; exit 0` | live exit-7 proof (`win_rail.sh run wg exit7.ps1`) returned **0**; `python -m unittest tests.test_showready_rail` exit 1 (3 failures incl. pins); re-pinned so only behaviour differs: exit 1, `test_remote_status_stderr_arguments_and_scp_failure` `AssertionError: 0 != 7` | `git checkout` rail and SHA256SUMS, pins exit 0 | exit-7 proof returned **7**; rail tests exit 0 (OK, skipped=1) |
| (e) guard vs baseline with tray pid altered | [mkmutant.ps1](evidence/ps/mkmutant.ps1): step0 snapshot copy, protectedProcesses pid 23640 -> 23641 | exit 1, `DIFF $.protectedProcesses[2].pid baseline=23641 current=23640` (only line) | compare against the unaltered step0 snapshot | 0 |
| (f) candidate opens a real MIDI port | commit `2d732f0` on clone branch mut-f: `mido.open_output('SDWIN_GATE_MUTANT_PORT')` at the start of `win_recv.main` | exit 1, `RuntimeError: Arm exited early: 70`; arm B1 capture holds 1 `forbidden_midi_open` record, 0 midi | candidate 27e3ad0 | 0 |

Rig errors, disclosed: the first mutation sweep called deck_script.py without `--fixtures` in the clone, so every row
failed with exit 1 (all 9 ab_run rows were refused for a missing script; kept locally as mutations-rigerror-1, not used).
The first (e) RED ran while the Windows matrix was live and was confounded by 14 matrix python processes (exit 1 with
the pid DIFF plus the python DIFFs, [e-red.txt](evidence/e-red.txt)); it was rerun on the idle laptop ([e-red-2.txt](evidence/e-red-2.txt)).

## Step 4 - BAR 1, re-run by the gate (README commands, --speed 1, --clock script)

Arm pair: A = v0.4.9 (e66ff44) vs candidate HEAD (27e3ad0). Script: Mac `9256621a...`, packet stream `c06cfa67469f...`
(equal to W3's script); laptop script document `f6611e7e...` (Windows path separators in delay_sources) with the SAME packet
stream `c06cfa67469f...`. Every result's `sent_packet_stream_sha256` equals it. Tables recomputed from raw
capture records by [table.py](evidence/table.py) (`raw` = the A and B `(step, bytes)` lists equal and non-empty),
not from ab_run's summary. Results: [results/mac](results/mac/), [results/windows](results/windows/).
NOT COVERED column: direct mapping MIDI only; the engine-dependent list in 4b applies to every EDM Show and PTZ row.

### Mac (driver [mac-matrix.sh](evidence/mac-matrix.sh), 7 concurrent runs, all exit 0)

| Preset | OS | Arm pair | Steps | Mappings exercised/total | Msgs A/B | Identical (summary / raw) | 60 Hz min ns | NOT COVERED |
| --- | --- | --- | ---: | ---: | ---: | --- | ---: | --- |
| mac fixture EDM Show (sectioned) | Mac | A / B1 flat | 732 | 56/56 | 1531/1531 | yes / yes | 16682833 | engines (4b) |
| mac fixture EDM Show (sectioned) | Mac | A / B2 --preset-section windows | 732 | 56/56 | 1531/1531 | yes / yes | 16683125 | engines (4b) |
| mac fixture PTZ (sectioned) | Mac | A / B1 flat | 732 | 52/52 | 1395/1395 | yes / yes | 16683459 | engines (4b) |
| mac fixture PTZ (sectioned) | Mac | A / B2 --preset-section windows | 732 | 52/52 | 1395/1395 | yes / yes | 16683167 | engines (4b) |
| mac fixture default | Mac | A / B1 | 732 | 56/56 | 1531/1531 | yes / yes | 16679041 | none |
| windows-installed EDM Show | Mac | A / B1 | 732 | 56/56 | 1531/1531 | yes / yes | 16678583 | engines (4b) |
| windows-installed PTZ | Mac | A / B1 | 732 | 52/52 | 1395/1395 | yes / yes | 16678500 | engines (4b) |
| windows-installed default | Mac | A / B1 | 732 | 56/56 | 1531/1531 | yes / yes | 16679834 | none |
| tracked config/presets/default.json | Mac | A / B1 | 732 | 56/56 | 1531/1531 | yes / yes | 16679875 | none |

### Windows laptop (driver [winmatrix.ps1](evidence/ps/winmatrix.ps1), batches of 4 and 3, both exit 0)

| Preset | OS | Arm pair | Steps | Mappings exercised/total | Msgs A/B | Identical (summary / raw) | 60 Hz min ns | NOT COVERED |
| --- | --- | --- | ---: | ---: | ---: | --- | ---: | --- |
| mac fixture EDM Show (sectioned) | Windows | A / B1 flat | 732 | 56/56 | 1531/1531 | yes / yes | 16816400 | engines (4b) |
| mac fixture EDM Show (sectioned) | Windows | A / B2 --preset-section windows | 732 | 56/56 | 1531/1531 | yes / yes | 16813500 | engines (4b) |
| mac fixture PTZ (sectioned) | Windows | A / B1 flat | 732 | 52/52 | 1395/1395 | yes / yes | 16809500 | engines (4b) |
| mac fixture PTZ (sectioned) | Windows | A / B2 --preset-section windows | 732 | 52/52 | 1395/1395 | yes / yes | 16813200 | engines (4b) |
| mac fixture default | Windows | A / B1 | 732 | 56/56 | 1531/1531 | yes / yes | 16776400 | none |
| windows-installed EDM Show | Windows | A / B1 | 732 | 56/56 | 1531/1531 | yes / yes | 16774700 | engines (4b) |
| windows-installed PTZ | Windows | A / B1 | 732 | 52/52 | 1395/1395 | yes / yes | 16770800 | engines (4b) |
| windows-installed default | Windows | A / B1 | 732 | 56/56 | 1531/1531 | yes / yes | 16763900 | none |
| tracked config/presets/default.json (clone) | Windows | A / B1 | 732 | 56/56 | 1531/1531 | yes / yes | 16781500 | none |

Every run: `passed: true`, error null, `no_overspeed` true for both axis phases on every arm, and every arm `pid_gone` true.
Windows timestamp clock `QueryPerformanceCounter()` (W4's repair in effect): 60 Hz median about 16.82 ms, 10 Hz median about 100.16 ms.
Replay wall time was 470.2-470.3 s on both hosts.

### Comparison with W3 and W4

The candidate `(step, bytes)` digest is `8d72c54f636e` for every 56-mapping run and `d4bdd41f4449` for every 52-mapping run.
That holds for the gate Mac, the gate Windows, W3 (candidate e8a64f4, 6 matching presets) and W4 preliminary (c4ba229, 8 comparisons), and it equals
the A-arm digest. Identical columns, steps, exercised/total and message totals AGREE with W3's and W4's result JSONs; there are
no disagreements. The EDM Show and default digests are equal because their mappings are equal (For Ben 1).

### Instrument findings (reported, not fixed)

- `compare()` always returns `'not_covered': []` (scripts/showready/ab_run.py:136), and the README's "No mapping in these presets needs an engine to emit its direct MIDI" is true only for direct bytes. Neither the result JSON nor the table records that engines were off for a preset whose engines block is its whole difference. A result for a preset with any `engines: true` should carry the 4b NOT COVERED list.
- In the port rows the driver's sender socket shows as `UDP 0.0.0.0:<ephemeral>` (four in batch 1, three in batch 2). This is `sendto` auto-binding the unbound socket (ab_run.py:282-303), not a listener bound on purpose. It never used 45123/7723.

## Step 4b - engine dependence (with engines off)

Source read by the gate plus a read-only subagent; the gate re-read these lines itself: windows/win_recv.py:337-346, receiver.py:167-208 and 872-884,
registry.py:86-100, autopilot.py:58-64 and 750-786, l_stick_layer.py:196-209, gyro_feedback.py:336-353, global_color.py:262-282.

- `--no-engines` leaves `engine_registry = None` (win_recv.py:337-338). Otherwise engines load from `<map dir>/engines` (win_recv.py:340-343) and preset engine states are applied AFTER loading (win_recv.py:346).
- Notes: engines can change the bytes of a mapped note. `_emit_note_on` asks `should_emit_note` and returns without sending when a filter says so (receiver.py:179-189). Only autopilot registers such a filter: ch0 notes 82/83/86/87 (autopilot.py:60-63, 753-772), re-emitted on the beat (775-785). This affects note and staged_note_macro modifier notes for L_PAD_LEFT/RIGHT and their _LONG_PRESS mappings in EDM Show.
- CC types (cc, macro_cc, relative_cc, axis_to_cc, axis_split_cc): the bytes are sent before the engine fan-out (receiver.py:206-208), so the mapped bytes do not depend on engines. The OUTPUT STREAM still gains engine bytes: l_stick_layer, gyro_feedback, global_color resync, and audio_opacity if not OSC (For Ben 1).
- Axis events reach engines first (receiver.py:874-881). With engines off this raises a caught AttributeError per event.
- ptz_visca (PTZ) sends VISCA UDP and OSC, not MIDI. osc_sync, stageflow_bridge, autopilot_ptz, nestdrop, bumper_blast, flash_blast, chaser_stack_dispatcher and steam_input_layer_tracker are OSC/REST/state only by the subagent's read (UNVERIFIED line by line by the gate).
- Program Files attribution: no Program Files or user-config digest changed during the lap window the gate observed (step 0 = step 7), so no edit by Ben needed attributing.

## Step 4c - installed-build join

Laptop, read-only ([join.ps1](evidence/ps/join.ps1), [joindiff.ps1](evidence/ps/joindiff.ps1), both exit 0):
orphan HEAD d1367870b939...; `status --porcelain -- windows config deck protocol` = 0 lines; `ls-tree -r d136787` 74 paths, `ls-tree -r e66ff44` 74 paths;
`diff` of the listings (exit 1) shows exactly 3 differing blobs:

| Path | d136787 blob | e66ff44 blob | Differing line | Orphan with `C:/Users/Ben/` -> `C:/Users/USERNAME/` equals tag |
| --- | --- | --- | ---: | --- |
| config/engines.factory/osc_sync.json | 7d2d5ea8 | 9d167d53 | 5 (`osc_preset_path`) | True |
| windows/engines/osc_sync.py | a4d4a4a1 | 0abd30ab | 101 (default path) | True |
| windows/engines/stageflow_bridge.py | 2c49e061 | 059f3312 | 147 (`comp_path` default) | True |

The raw line comparison differs at exactly one line per file; with the username substituted the whole files are equal. That is the control,
and it confirms MASTER 18:23. Join recorded as QUALIFIED-BY-NAME with those three hunks. Mappings are unaffected (no MIDI path).

Installed engine configs under `C:\Program Files\STEAMDECK MIDI Receiver 2\config`:

| File | osc_preset_path | comp_path |
| --- | --- | --- |
| engines\osc_sync.json | FILE ABSENT | FILE ABSENT |
| engines\stageflow_bridge.json | FILE ABSENT | FILE ABSENT |
| engines.factory\osc_sync.json | PRESENT, shape `C:/Users/<user>/.../<name>.xml`, not the USERNAME placeholder | ABSENT |
| engines.factory\stageflow_bridge.json | ABSENT | ABSENT |

Disclosure: the first join.ps1 printed the full `osc_preset_path` value to the gate session's console output through a formatting
slip. The local evidence file was redacted before commit ([4c-join.txt](evidence/4c-join.txt) shows `[VALUE REDACTED BY GATE]`), and
`grep -rl OneDrive docs/sdwin-gate` exit 1. The value is not in any committed file. Upgrade risk: For Ben 2.

## Step 5 - laptop process and port rows

While the arms ran (batch 1 at t=63 s, [5-winmatrix-b1.txt](evidence/5-winmatrix-b1.txt); batch 2 at t=63 s and t=313 s):

| Endpoint | Owner pid | Owner |
| --- | ---: | --- |
| UDP 0.0.0.0:45123 | 23640 | STEAMDECK-MIDI-RECEIVER-2-Tray |
| TCP 127.0.0.1:7723 | 23640 | STEAMDECK-MIDI-RECEIVER-2-Tray |
| UDP 127.0.0.1:61591 / 61596 / 63818 | 276500 / 267128 / 235416 | mac-edm arms A / B1 / B2 (each equals its result's `ready.pid` and `bound`) |
| UDP 127.0.0.1:61593 / 61595 / 63817 | 269656 / 264552 / 278288 | mac-ptz A / B1 / B2 |
| UDP 127.0.0.1:61592 / 61598 | 265868 / 269604 | win-edm A / B1 |
| UDP 127.0.0.1:61594 / 61597 | 278096 / 278216 | win-ptz A / B1 |
| UDP 127.0.0.1:55239 / 55243 | 268316 / 264552 | mac-default A / B1 (batch 2) |
| UDP 127.0.0.1:55240 / 55242 | 277692 / 278352 | win-default A / B1 |
| UDP 127.0.0.1:55241 / 55244 | 278568 / 273180 | tracked-default A / B1 |
| UDP 0.0.0.0:60317, 60318, 63819, 63820 (b1); 55245-55247 (b2) | drivers | ab_run sender sockets (see instrument findings) |

Afterwards: each batch walked the full CIM descendant tree of its ab_run launchers every 20 s and proved every seen pid gone with
Get-Process (batch 1: 28/28 gone; batch 2: 18/18 gone), with `PYTHON_LEFT 0`. The back-fill arms were proved gone by their own checks.
At step 7 [inventory.ps1](evidence/ps/inventory.ps1) found 0 python/pythonw machine-wide and no process whose command line or exe
refers to sdwin or the clone other than its own cmd.exe; the final guard's clone/work python check was empty. Mac side: `pgrep -fl "ab_run.py|capture_runner.py"` exit 1.

## Step 6 - launcher back-fill

[backfill.ps1](evidence/ps/backfill.ps1) is W2's arms.ps1 with the plan changed: same argv-capture stub, isolated layout under `wg\gate-backfill`, no receiver.
Launcher shas on the laptop: v0.4.9 copies 36574ec8 / 5aeaed4f / bad60c86, equal to `git show v0.4.9:scripts/windows/<name>.ps1` on the Mac. Script exit 0; [arms JSON](evidence/6-backfill-arms.json).

| Version | Launcher | Arm | Exit | Settings sha before -> after | Captured argv |
| --- | --- | --- | ---: | --- | --- |
| HEAD | start_installed_receiver_v2.ps1 | (a) settings without preset_section | 0 | 5e5989f6 -> 34837d23; saved `preset_section: "windows"` | 1: `--check-midi-port --midi-port SDWIN_ARGV_ONLY_NO_MIDI`; 2: `--listen 127.0.0.1:45282 --map ...\config\windows_midi_map.json --midi-port SDWIN_ARGV_ONLY_NO_MIDI --timeout 2.0 --preset-section windows --verbose --no-ui --ui-port 7782` |
| HEAD | start_receiver.ps1 | absent file | 1 | ABSENT -> ABSENT | none; `start_receiver.ps1:35` PropertyNotFoundStrict |
| HEAD | start_installed_receiver.ps1 | absent file | 1 | ABSENT -> ABSENT | none; line 35 PropertyNotFoundStrict |
| HEAD | start_installed_receiver_v2.ps1 | absent file | 1 | ABSENT -> ABSENT | none; line 35 PropertyNotFoundStrict |
| v0.4.9 | start_receiver.ps1 | absent file | 1 | ABSENT -> ABSENT | none; line 35 PropertyNotFoundStrict |
| v0.4.9 | start_installed_receiver.ps1 | absent file | 1 | ABSENT -> ABSENT | none; line 35 PropertyNotFoundStrict |
| v0.4.9 | start_installed_receiver_v2.ps1 | absent file | 1 | ABSENT -> ABSENT | none; line 35 PropertyNotFoundStrict |

Classification: PRE-EXISTING (v0.4.9 also exits 1 at the same line; the branch's only launcher change, d20f195, adds the preset_section block after it).
Not show-relevant: the installed tray starts from the Run key and shortcuts into the EXE (installer .iss:49, 66-67, 70), and the laptop's settings file exists.

## Step 8 - pick-up

| Check | Command | Result |
| --- | --- | --- |
| Pushed | `git ls-remote --heads origin chain/steamdeck-20260914` (SSH override) | at gate start: equals HEAD 27e3ad0; after the gate commit: see envelope |
| Clean root | `git status --porcelain` | 0 lines before the gate's evidence; empty after commit (envelope) |
| Nothing excluded committed | `git log --name-only --format= 1b12b59..HEAD` into grep for `.showready/`, `config/presets/`, `bridge.local.json`, `windows_receiver_settings.local.json`, `config/engines/`, `config/state/` | grep exit 1 across 233 paths (control: a config/presets path matches, exit 0) |
| mac/ untouched | `git diff --stat 1b12b59 HEAD -- mac/` | empty (0 diff lines) |
| MIDI send path | `git diff 1b12b59 HEAD -- windows/midi.py windows/receiver.py` | empty (0 lines); no hunk to classify |
| Ben's Mac files | `shasum -a 256` | EDM Show.json 58e47bfd, PTZ.json 11b37cd6, EDM Show.json.v049.bak 3b2ef2e5, PTZ.json.v049.bak 3d5b996a, bridge.local.json 7476c269, windows_receiver_settings.local.json 41e28828: all equal to the orchestrator's 16:1x hashes |
| .showready ignored | `git check-ignore -v .showready/fixtures/mac/MANIFEST.sha256` | `.gitignore:65:.showready/` |

## Leftovers on the laptop (inert files, no processes)

`sdwin\wg\` holds gate scripts, the step 0 / step 7 / mutant guard JSONs, result JSONs, arm scratch and the back-fill layout.
The clone is at 27e3ad0 and clean. Mac: `/tmp/sdwin-gate/` (including the mutation clones).
