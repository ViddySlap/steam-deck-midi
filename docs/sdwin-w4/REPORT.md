GUARD UNVERIFIED-BY-EXECUTION: final compare not run after pinned SSH hostname resolution failed; the initial snapshot was GREEN.
NEEDS-MASTER: restore the authorized LAN SSH route, then discharge the W4 process/guard and final-capture debt below. Possible W4 Python processes remain UNVERIFIED, not zero.

# sdwin W4 - Windows instrument repairs and interrupted final verification

No final bar 1 credit is claimed. All preliminary Windows byte comparisons
matched, but their timestamp clock was too coarse for rate credit. The
instrument was repaired, pushed, and passed both suites. The final matrix
was launched with the repaired clock. SSH then stopped resolving
`viddyslaptop.local`; final raw captures, global cleanup and guard comparison
could not be retrieved or executed. No alternate route or reconnect was
attempted after the failure.

Branch: `chain/steamdeck-20260914`. Entry:
`88c1a0b5e1834b44b0993b81c4161c0e82da7625`.
Final tested code and last verified clone HEAD:
`b3b28612c3be1a9e841c82c557a219e72b73eaea`.
This report's evidence-only commit follows. No merge, deployment, product
mapping change, UI change, MIDI send-path change or mac/ edit occurred.

## Stop-the-line finding and exact recovery debt

The single new status connection, executed through the pinned rail, failed:

```sh
scripts/showready/win_rail.sh run w4 /tmp/sdwin-w4/status.ps1
```

Exit 255. [status-final.txt](evidence/status-final.txt):

```text
ssh: Could not resolve hostname viddyslaptop.local: nodename nor servname provided, or not known
```

This establishes failed name resolution from this executor, not whether the
laptop slept, disconnected or is still running. All six existing matrix SSH sessions eventually ended with transport exit
255 and no final arm completion output. This is not a receiver exit code.
The pending dead-seam cleanup connection also ended with exit 255 and
`No route to host`. Neither result establishes remote exit or cleanup. No fresh laptop action followed
the observed failure. The installed tray's final state is UNKNOWN.

**OWED TO THE GATE / master, once the specified route is restored:**

1. Preserve the original W4 baseline at
   `C:\Users\Ben\AppData\Local\Temp\sdwin\w4\before.json`.
   The identical downloaded baseline is [before.json](evidence/before.json).
   Do not replace it with a new baseline and thereby erase the interval.
2. Inspect the owned W4 scripts, `*.observation.json`, result `*.json.gz`,
   and `qpc-*\ab-*\*.ready.json` under that same W4 work directory.
   Verify exact process command line, executable path and owned arm tree
   before stopping anything. Never stop the installed tray or other work.
3. Finish/stop every W4-owned process and prove every driver, venv launcher
   and actual receiver worker gone with Get-Process. The final live worker
   PIDs and UDP ports are listed below; launcher/driver identities are in
   the remote observation/result JSONs. The final wrapper also records all
   Python command-line descendants for its own scratch directory.
4. Run [prove-gone.ps1](evidence/prove-gone.ps1) for every final result, then
   [cleanup.ps1](evidence/cleanup.ps1). The latter checks Python executable
   paths under CLONE/WORK and also command lines, because a venv worker image
   may reside in the system Python directory. An absent result, missing PID
   observation, early exit or missing capture is RED, never a completed run.
5. Retrieve all final result/observation/gone JSONs to `docs/sdwin-w4/results/`
   and evidence. Raw results above 1 MB already use gzip. Require instrument
   pins from `preflight-final.json`, A=e66ff44 and B=b3b2861, complete identical
   packet streams, nonzero mapping-directed MIDI on both arms, all mappings
   exercised, and actual high-resolution pacing measurements. Re-run any
   incomplete arm with fresh scratch/output paths; `run.ps1` refuses an
   existing arm work directory. Never overwrite or refresh installed fixtures.
6. Recompute each final comparison and compare candidate bytes by step to
   W3's corresponding result. Finish the two A/A determinism runs and all
   three planted-fault controls from their raw artifacts. Console summaries
   alone do not pay this step.
7. Re-run the full Windows suite after all arms are gone, using the clone's
   venv at the pinned code. The same code already passed before the final
   matrix, as recorded below. Any later code change needs fresh checks.
8. Download all evidence before the final laptop act. Compare W1's guard
   against the ORIGINAL W4 before.json. A difference is stop-the-line.
   Record the final result and only then reassess bars 1 and 2.

The original user instruction says an executor-only outstanding item is
`OWED TO THE GATE` and uses a complete envelope. That is the terminal status
for this bounded instrument repair and handoff; it does not mean the final
Windows evidence, teardown or show-ready bar passed.

## Installed-build join: tag bar 1 must remain QUALIFIED

The laptop executed the required read-only commands in
[preflight.ps1](evidence/preflight.ps1) and again after code updates:

```powershell
git --no-optional-locks -C C:\Users\Ben\Documents\project-workspaces\steam-deck-midi rev-parse HEAD
git --no-optional-locks -C C:\Users\Ben\Documents\project-workspaces\steam-deck-midi status --porcelain -- windows config deck protocol
git --no-optional-locks -C C:\Users\Ben\Documents\project-workspaces\steam-deck-midi ls-tree -r d136787 -- windows config deck protocol
git -C C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc ls-tree -r e66ff44 -- windows config deck protocol
```

Observed orphan HEAD: `d1367870b93921b115b4c0972c13393792ea5307`.
Scoped dirty paths: none. Both listings contain 74 paths. Comparing blob SHA
per path finds exactly three changed paths, no extra paths and no missing
paths. [preflight-code.json](evidence/preflight-code.json) contains both complete
listings; [update-final.txt](evidence/update-final.txt) records the final repeat.
The final structured `preflight-final.json` remains on the laptop, uncollected.

| Path | Installed d136787 blob | Tag e66ff44 blob | Reach |
| --- | --- | --- | --- |
| config/engines.factory/osc_sync.json | 7d2d5ea85d9c36468e23a19c21ff22d17eefcc61 | 9d167d53309fdf5a51adeab570697948c0452a08 | Factory OSC XML path |
| windows/engines/osc_sync.py | a4d4a4a13fa0b8b94a83f6d681c0579267fb6fab | 0abd30abee0e532c854afa8e876dd539f4640478 | Fallback OSC XML path |
| windows/engines/stageflow_bridge.py | 2c49e061e0af201c03ffeda88593fc44c3710ae1 | 059f3312e34c0244536368f3481a1c731aa159c3 | Legacy composition-path field |

Each change substitutes `C:/Users/Ben/` with `C:/Users/USERNAME/`.
[installed-join.json](evidence/installed-join.json) records exact diffs and
blob checks. `archive-join.ps1` used `git --no-optional-locks archive` in the
orphan, writing only to W4 WORK. Windows archive CRLF conversion was
normalized to LF for Git blob SHA1 verification; all three matched ls-tree.

OSC Sync reads the XML path at `windows/engines/osc_sync.py:182`, reached
through its CC90 rising-edge input on zero-based channel 14 (MIDI channel 15)
or an explicit sync call. An engine config can override the fallback;
whether the installed user engine config does so is UNVERIFIED-BY-EXECUTION.
StageFlow assigns its differing `comp_path` at
`windows/engines/stageflow_bridge.py:143`; source search finds no later
`self._comp_path` read. Active rescan uses REST. This is source evidence;
neither engine was executed for this comparison.

No direct mapping definition, receiver dispatch, protocol or MIDI output
file differs in the join. Nevertheless, any successful tag-based bar 1
remains QUALIFIED under the master's ruling. Replay uses `--no-engines`,
so it cannot certify installed engine behavior.

## Final BAR 1 table: not credited

These are the final b3b2861 runs. Raw result and final cleanup evidence is
UNREAD from this executor after the route failure. UNKNOWN is not zero.

| Preset | OS | Arm pair | Steps | Mappings exercised/total | Identical | NOT COVERED |
| --- | --- | --- | --- | --- | --- | --- |
| Windows-installed EDM Show | Windows | v0.4.9 / b3b2861 B1 | UNREAD | UNREAD | UNREAD | UNKNOWN |
| Windows-installed PTZ | Windows | v0.4.9 / b3b2861 B1 | UNREAD | UNREAD | UNREAD | UNKNOWN |
| Windows-installed default | Windows | v0.4.9 / b3b2861 B1 | UNREAD | UNREAD | UNREAD | UNKNOWN |
| Tracked default.json | Windows | v0.4.9 / b3b2861 B1 | UNREAD | UNREAD | UNREAD | UNKNOWN |
| Sectioned EDM Show, windows | Windows | v0.4.9 / b3b2861 B1, B2 | UNREAD | UNREAD | UNREAD | UNKNOWN |
| Sectioned PTZ, windows | Windows | v0.4.9 / b3b2861 B1, B2 | UNREAD | UNREAD | UNREAD | UNKNOWN |

## Retained preliminary byte results: no final rate credit

These captured results use candidate c4ba229 and the coarse Windows clock.
The complete raw JSONs are in [results/preliminary](results/preliminary/).
Their observation/PID records and raw summary are in `evidence/preliminary/`.
The producer was the clone's venv Python running `ab_run.py`; each
`*.observation.json` records the complete argv and exit code. The exact local recomputation command was:

```sh
.venv/bin/python -B docs/sdwin-w4/evidence/summarize_preliminary.py
```

It recomputes mapping coverage from raw MIDI/input records and verified
fixture mappings, compares nonempty `(step, bytes)` arrays, and writes
`evidence/preliminary/raw-summary.json`.

| Preset | Arm | Steps | Mappings exercised/total | MIDI messages A/B | Identical | NOT COVERED | Exit |
| --- | --- | ---: | ---: | ---: | --- | --- | ---: |
| windows-edm | B1 | 732 | 56/56 | 1531/1531 | yes | none | 0 |
| windows-ptz | B1 | 732 | 52/52 | 1395/1395 | yes | none | 0 |
| windows-default | B1 | 732 | 56/56 | 1531/1531 | yes | none | 0 |
| tracked-default | B1 | 732 | 56/56 | 1531/1531 | yes | none | 0 |
| sectioned-edm | B1 | 732 | 56/56 | 1531/1531 | yes | none | 0 |
| sectioned-edm | B2 | 732 | 56/56 | 1531/1531 | yes | none | 0 |
| sectioned-ptz | B1 | 732 | 52/52 | 1395/1395 | yes | none | 0 |
| sectioned-ptz | B2 | 732 | 52/52 | 1395/1395 | yes | none | 0 |

The first three captures' `pacing.A` fields report 229 intervals per sweep:
nominal 60 Hz min/median/max = 31/31/32 ms; nominal 10 Hz = 109/109/110 ms.
`replay_wall_seconds` is 476.375 for those runs. This is the observed pacing,
not a claim of actual 60 Hz or 10 Hz. The later clock probe identified the
cause; final QPC intervals remain UNVERIFIED-BY-EXECUTION here.

## Ports and processes

Before each run the wrapper listed Get-NetUDPEndpoint and
Get-NetTCPConnection. The instrument then bound free ephemeral ports,
excluded 45123/7723, and checked again before boot. Each ready artifact came
from the receiver's actual socket bind. No arm used --tray; every arm used
--no-ui, --no-engines, --no-pulse, --no-osc-relay and denied real MIDI APIs.
The unused UI port was non-default; no arm UI listener was requested.

Independent live rows in the downloaded preliminary observations show tray
PID 23640 retaining UDP 0.0.0.0:45123 and TCP 127.0.0.1:7723 while the arm
owned its separate loopback UDP port. Example rows:

| Preliminary arm | Worker PID | UDP port | Tray UDP/TCP owner | Teardown |
| --- | ---: | ---: | ---: | --- |
| windows-edm A | 273740 | 57725 | 23640 | Get-Process absent |
| windows-edm B1 | 276460 | 57727 | 23640 | Get-Process absent |
| windows-ptz A | 273948 | 57726 | 23640 | Get-Process absent |
| windows-ptz B1 | 273500 | 52360 | 23640 | Get-Process absent |
| windows-default A | 272376 | 52359 | 23640 | Get-Process absent |
| windows-default B1 | 270532 | 52362 | 23640 | Get-Process absent |

`prove-gone.ps1` read each result's venv launcher and ready worker PID and
checked both with Get-Process. Preliminary cleanup then made 59 recorded
PID checks and found all absent, no Python path under CLONE/WORK, and no
Python command line referring to W4/clone. These counts come from
[cleanup-preliminary.txt](evidence/cleanup-preliminary.txt), not from a final
cleanup claim.

Final QPC live worker identities, from the already-open rail output:

| Final run | A PID / UDP | B1 PID / UDP | B2 PID / UDP | Final absence |
| --- | --- | --- | --- | --- |
| windows-edm | 266512 / 53919 | 262176 / 53921 | - | UNVERIFIED |
| windows-ptz | 278440 / 53920 | 250436 / 53924 | - | UNVERIFIED |
| windows-default | 277756 / 53923 | 267656 / 53927 | - | UNVERIFIED |
| tracked-default | 233432 / 53926 | 272232 / 53930 | - | UNVERIFIED |
| sectioned-edm | 274080 / 53929 | 251680 / 53933 | 275832 / 56828 | UNVERIFIED |
| sectioned-ptz | 274184 / 53932 | 278016 / 56827 | 262056 / 56830 | UNVERIFIED |

Final raw live port/tray observations remain on the laptop in the final
`*.observation.json`. The final Python process inventory and installed guard
comparison are UNVERIFIED-BY-EXECUTION. Do not substitute the preliminary
cleanup for them.

## Windows controls

Final controls use the repaired b3b2861 instrument with both code arms at
v0.4.9, the verified Mac default fixture, identical script, and explicit
`--speed 50`. These are accelerated detector controls. The exact rail
commands/exits are in [control-commands-final.json](evidence/control-commands-final.json).
Their final stdout is retained, but the final raw result JSONs were not
collected after the route loss. Therefore the following are execution/console
observations and do not claim independently verified final artifact credit.

| Control | Observed native exit | Console observation | Final raw artifact |
| --- | ---: | --- | --- |
| determinism-1 | 0 | 1531 messages per arm; pair identical | UNREAD |
| determinism-2 | 0 | 1531 messages per arm; pair identical | UNREAD |
| sensitivity | 1 | different_mappings=[BTN_A] | UNREAD |
| coverage | 1 | BTN_A unexercised; 55/56; 728 steps | UNREAD |
| dead seam | 1 | zero messages on both sides rejected | UNREAD |

Final cross-run A/A determinism is not established from console summaries.
The preliminary raw controls, including all PID evidence, are retained and
show the expected detector outcomes. The final dead-seam follow-up
Get-Process connection ended with transport exit 255 (`No route to host`),
so that follow-up does not establish absence.

## Windows-versus-Mac candidate comparison

For all six preliminary presets and all eight B1/B2 comparisons,
`summarize_preliminary.py` compared nonempty candidate `(step, bytes)` arrays
against W3 and found them identical. The generated step and packet arrays
were exactly equal too. These eight observations are in
`evidence/preliminary/raw-summary.json`. Script-document SHA differs because
source paths use Windows separators. These are preliminary comparisons; the
final QPC runs remain uncredited.

Final b3b2861 Windows-versus-Mac comparisons for every preset are
UNVERIFIED-BY-EXECUTION pending final capture retrieval. The runtime source
comparison `git diff e8a64f4 b3b2861 -- windows config deck protocol mac` is
empty, recorded in [scope.json](evidence/scope.json). That source equality
cannot replace the missing final Windows byte observations.

## Repairs, pins and fixtures

- `c4ba229`: the exact tracked `config/presets/default.json` is accepted only
  when it matches the candidate Git blob, allowing LF/CRLF conversion.
  Actual consumed bytes are hashed. Both W2 manifests remain mandatory;
  arbitrary unmanifested presets and changed tracked defaults are rejected.
  One new real-Git-tree test covers clean LF/CRLF, a changed mapping, a
  foreign path and restoration. Focused before: 11 tests, exit 1; after:
  11 tests, exit 0. Existing assertions were preserved.
- `b3b2861`: sender pacing and recorder timestamps use perf_counter_ns.
  The fields remain named monotonic_ns because this clock is monotonic.
  Result JSON records clock implementation/resolution. The actual Windows
  `clock-probe.ps1` measured GetTickCount64 resolution 0.015625 seconds and
  QueryPerformanceCounter resolution 0.0000001 seconds. Probe launcher PID
  276640 and worker 272396 were proved absent. The new test supplies
  disagreeing clocks and asserts the pacing and captured MIDI timestamps.
  Focused before: 12 tests, exit 1; after: 12 tests, exit 0.

No receiver clock injection, mapping dispatch or MIDI send-path code changed.
Both instrument commits were pushed with the required SSH transport overrides;
ls-remote exactly matched each local HEAD. The parked mac/ tree is unchanged.

The first laptop act was W1 guard snapshot to W4 before.json, exit 0.
Preflight and each code update pulled the clone with --ff-only, checked clean
porcelain and exact Mac SHA, peeled v0.4.9 to e66ff44, and used Get-FileHash
on every file named in SHA256SUMS. All seven final pins matched on the laptop.
All 11 installed-fixture entries matched every manifest hash and byte count;
manifest SHA256 remained
`7c6dad5b30ab05f1d005d1d722964ec847e6db19726bf0eb500d8bbcf10e331d`.
No mismatch or installed-fixture recapture occurred.

The Mac W2 fixtures were absent on the laptop. `prepare.ps1` copied that
existing ignored set once into `sdwin\fixtures\mac`, refused an existing
destination, and made the copies read-only. The generator and each ab_run
verified both manifests. The clone's venv reports Python 3.12.10. All arms
were archived under W4 WORK; no system install, real MIDI port, loopMIDI,
Resolume, installed config, orphan mutation, or deployment was performed.

Probe errors: the initial PowerShell native text decoder mangled non-ASCII
source comments, so the join uses archive bytes and verified blobs instead.
A raw archive SHA1 check detected Windows CRLF conversion; LF normalization
then matched all three blob IDs. A partial Compress-Archive attempt refused
a still-open stderr log, exit 1; the completed preliminary archive was
collected only after teardown. These are retained, resolved recorder errors.

## Full suites

Mac, from the run root, using scratch under /tmp/sdwin-w4:

```sh
TMPDIR=/tmp/sdwin-w4 PYSTRAY_BACKEND=dummy BROWSER=true .venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

Windows, from the isolated clone, via W1's suite.ps1 and its venv:

```powershell
C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

| Host / run | Exact summary | Exit |
| --- | --- | ---: |
| Mac entry | Ran 838 tests in 11.762s; OK (skipped=2) | 0 |
| Mac c4ba229 | Ran 839 tests in 11.399s; OK (skipped=2) | 0 |
| Windows c4ba229 | Ran 839 tests in 19.380s; OK (skipped=5) | 0 |
| Mac clock fix | Ran 840 tests in 11.290s; OK (skipped=2) | 0 |
| Windows b3b2861 before final replay | Ran 840 tests in 17.931s; OK (skipped=5) | 0 |
| Mac final code, after route loss | Ran 840 tests in 12.468s; OK (skipped=2) | 0 |


The Windows suite at the final code SHA passed before the final matrix;
its launcher PID 254412 was proved gone and its path inventory was empty.
A post-matrix Windows suite was not executed. Dummy pystray and the W1
no-op BROWSER were set for the existing suite's UI tests. Skips retain W1's
platform boundaries and the pre-existing cc_base skip. No test assertion
was removed or relaxed. The final Mac suite passed after the route failure.
The missing final Windows guard/cleanup prevents aggregate laptop safety
credit, regardless of the earlier suite result.

## One-line bar 1 verdicts

- Windows EDM Show: NOT CREDITED at final b3b2861; final raw/cleanup evidence owed; any tag pass remains QUALIFIED by the installed-build join.
- Windows PTZ: NOT CREDITED at final b3b2861; final raw/cleanup evidence owed; any tag pass remains QUALIFIED by the installed-build join.
- Windows installed default: NOT CREDITED at final b3b2861; final raw/cleanup evidence owed; any tag pass remains QUALIFIED by the installed-build join.
- Tracked default: NOT CREDITED at final b3b2861; final raw/cleanup evidence owed; any tag pass remains QUALIFIED by the installed-build join.
- Sectioned EDM Show, Windows section: NOT CREDITED for final B1/B2; final raw/cleanup evidence owed; installed-build join QUALIFIED.
- Sectioned PTZ, Windows section: NOT CREDITED for final B1/B2; final raw/cleanup evidence owed; installed-build join QUALIFIED.

Controller-view timing, Ben's hardware check and rollback remain later bars.
No complete show-ready verdict is implied by this W4 handoff.
