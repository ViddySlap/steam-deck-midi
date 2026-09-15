E4 ENTRY HEAD b2ca727c0acdc710a9ae98b6e01b76f3d4f28914

# sdlive E4 - pinned short bar 3 timing workload

E4's instrument and workload are built. Qualifying bar 3 measurements are
OWED TO THE GATE. No laptop acts, real MIDI ports, hardware acts, deployment,
merge, vault writes or engine changes occurred. All timing observations here
are R=1 Python-client DIAGNOSTICS, UNVERIFIED-LOAD, at real pacing speed 1.
They do not authorize an upgrade. The original clean diagnostic's numeric
rule is RED; bytes match and all arms exceed the power floor.

## What E3 already supported

Read `docs/sdlive-e3/REPORT.md` in full, fetched
`GET /launches/sdlive-q001.E3` into `/tmp/sdlive-e4/predecessor-e3.json`, and
read the pinned generator, its generated JSON, recorder, driver, tests,
SHA256SUMS and README. E3 ALREADY had a required `--script <path>` argument.
It remains required; no default workload was silently changed. The new CLI
test observes the explicit path actually passed to `run()`.

E3 rejected all R<5 in its CLI and required R>=5 in sensitivity receipts.
E4 permits R>=1 diagnostics, requires R>=5 for clean qualification and the
approved R>=3 for sensitivity qualification. Mac Python-client runs are
explicitly diagnostic even with readable load. Windows retains the approved
Python fallback. Tests cover the exact R=3 receipt, R=2 rejection, R=1 CLI,
R=5 clean threshold, accelerated runs and host/client qualification.

E3's pacing helper required both 10 Hz and 60 Hz observations from consecutive
same-axis steps. E4 adds a timing-only pacing adapter: interleaved steps are
grouped by segment AND axis, all intervals must be observed and no interval
may be faster than scheduled. The full Deck script still uses E3's unchanged
pacing helper. No MIDI path, mapping, Deck sender, bar 1 generator/driver or
recorder logic changed. `--clock script` still controls receiver scheduling;
latencies and pacing still use real perf_counter time. These measurements do
not certify the ordinary Windows scheduler.

## Composition, provenance and subset proof

Commands producing the composition and digests:

```sh
.venv/bin/python -B scripts/showready/deck_script.py --out /tmp/sdlive-e4/deck-script.json
.venv/bin/python -B scripts/showready/timing_script.py /tmp/sdlive-e4/deck-script.json --out scripts/showready/timing_script.json
TMPDIR=/tmp/sdlive-e4 .venv/bin/python -B scripts/showready/timing_script.py /tmp/sdlive-e4/deck-script.json --out /tmp/sdlive-e4/regenerated-timing.json
cmp scripts/showready/timing_script.json /tmp/sdlive-e4/regenerated-timing.json
shasum -a 256 -c scripts/showready/SHA256SUMS
```

All exited 0. Regeneration is byte-identical and uses exclusive-create output;
the pinned timing file was written once. `evidence/composition.json` retains
the generator output. Full Deck JSON: 732 steps, 47,039 packets,
469.716666743 seconds. Its logical SHA256 is
`9256621abf62eb21e6c345ef286b6b7fcc087a2db87b8f682ce7fcf7703a993e`;
its file SHA256 is
`b642eee8ea7afeb5e965b3bb5e62c03cc130c8efaa611dcdb96d112d6942edba`.

Pinned timing file SHA256:
`ffd4e26716f660a98365e77bb5a159c15b6067dc4a824127245f267489913a12`.
Logical script SHA256:
`6be11d1086a3a918e2a272ec570e5015554a71d32ef5ce3d15289b4824fd19a8`.

| Kind | Events/packets |
| --- | ---: |
| action | 124: 62 button-like IDs, exactly one down and one up each |
| axis | 15,246 |
| heartbeat | 5,143 |
| total packets | 20,513 |
| non-heartbeat steps | 15,370 |

Schedule duration: 70.400000882 s. The named
`simultaneous-sticks-triggers-60hz` segment spans 24.05 s to 66.050000840 s:
42.000000840 s, 2,520 ticks, six axes per tick. It contains BOTH stick X/Y
pairs and BOTH trigger pressures, interleaved per tick. Each stick makes 126
source sweep passes; each trigger makes 140 source sweep passes. The other
seven axes sweep once each at 60 Hz. The source-derived sender interval is
16,666,667 ns from `AXIS_MIN_INTERVAL = 1.0 / 60.0`. One-nanosecond offsets
order simultaneous-tick packets in the existing strictly increasing format.
The actual sender preserves every gap; no catch-up or accelerated drain runs
at speed 1. Buttons dwell 100 ms down / 250 ms after up, with a further 2.25 s
timer-settling horizon before the worst case and after the final axis.

The power margin comes from additional source axis passes, never repeated
buttons. All three locked constraints (a), (b), (c) hold in the executed
validation; no timing-script conflict or NEEDS-MASTER lane-log write arose.

Mechanical subset checker commands and full receipts are in
`evidence/subset.json`:

```sh
.venv/bin/python -B scripts/showready/timing_subset_check.py scripts/showready/timing_script.json /tmp/sdlive-e4/deck-script.json
.venv/bin/python -B scripts/showready/timing_subset_check.py /tmp/sdlive-e4/foreign-value.json /tmp/sdlive-e4/deck-script.json
.venv/bin/python -B scripts/showready/timing_subset_check.py scripts/showready/timing_script.json /tmp/sdlive-e4/deck-script.json
```

Observed exits GREEN 0 / RED 1 / restored GREEN 0. The planted value 12345 on
L_STICK_X_AXIS exists in neither the pinned full script nor its encoding set.
The mutant updates BOTH step and wire packet, then reseals valid digests, so
RED is encoding membership, not a broken hash. The checker identified the
foreign encoding at packet 2396. Clean: 245 distinct non-heartbeat encodings,
all source members. It checks every packet and step, ignores only seq, and
refuses an empty script or inconsistent step/packet metadata.

## Power floor, segment statistics and revert proofs

`MIN_TIMED_MIDI_MESSAGES = 1000` is enforced in the capture result, arm result,
summary rows and verdict inputs. An underpowered arm is `INVALID`, even when
bytes and latency inequalities are otherwise green. Startup bytes have no
physical-input timestamp and cannot pay the floor. The worst-case p50/p95/p99/
max/count comes from only messages whose CAUSAL input step is in that segment;
zero segment observations fail. Both per-arm rows and separately pooled
worst-case statistics are retained. The locked overall timing inequality is
unchanged; segment stats are reported separately for inspection.

Commands:

```sh
.venv/bin/python -B -m unittest tests.test_showready_timing tests.test_showready_timing_script -v
TMPDIR=/tmp/sdlive-e4 .venv/bin/python -B docs/sdlive-e4/check_mutation.py
```

Focused suite: 18 tests, exit 0 (`evidence/focused.log.gz`). The mutation
runner copies the instrument and tests into unique `/tmp/sdlive-e4/` scratch
and executes the actual named unittest assertions. It never mutates the repo.
`evidence/mutations.json` contains command, stdout, stderr and exit for every
case. Three controls, each GREEN 0 / reverted RED 1 / restored GREEN 0:

- `test_power_floor_999_is_invalid_and_blocks_otherwise_green_verdict`:
  removing the INVALID classification fails the `INVALID` equality assertion.
- Same test: removing the verdict's valid-arm conjunction fails the assertion
  that an underpowered but byte-identical, numerically green run must fail.
- `test_segment_statistics_use_only_own_causal_messages`: removing the segment
  filter returns 1,000 samples instead of the expected four and fails. The
  synthetic current replay step deliberately disagrees with causal step.

The existing `test_summary_rechecks_every_message_and_exposes_top_outlier_step`
fixture grew from 3 to 1,002 samples per arm so its legal GREEN case meets the
new floor. Its exact pooled OPEN count assertion changed from 15 to 5,010
(5 repeats * 1,002). No assertion was removed or bypassed; byte-difference,
zero-observation, outlier and pass assertions remain. This is the only changed
existing assertion and is named in the commit body. Every existing UI check
is byte-unchanged.

## Executed clean Mac validation

```sh
.venv/bin/python -B scripts/showready/timing_ab.py --candidate b2ca727c0acdc710a9ae98b6e01b76f3d4f28914 --script scripts/showready/timing_script.json --repeats 1 --allow-unverified-load --scratch /tmp/sdlive-e4/validation --out /tmp/sdlive-e4/validation.json.gz
TMPDIR=/tmp/sdlive-e4 .venv/bin/python -B docs/sdlive-e4/verify_validation.py /tmp/sdlive-e4/validation.json.gz --out docs/sdlive-e4/evidence/validation.json
```

Instrument exit 1: numeric timing RED, not an invalid arm. Raw verifier exit
0: every received packet count/digest, causal timestamp subtraction, exact
sample population, message sequence, per-arm percentile, nonempty pacing and
cleanup receipt verified. Full raw result is `evidence/validation.json.gz`;
compact independent receipt is `evidence/validation.json`.

| Arm | Replay s | Timed MIDI | Worst segment MIDI | Floor |
| --- | ---: | ---: | ---: | --- |
| CLOSED | 73.924602208 | 9638 | 9016 | VALID |
| OPEN | 73.953761792 | 9638 | 9016 | VALID |
| CLOSED-B | 74.041200917 | 9638 | 9016 | VALID |

All arms captured 9,644 total MIDI messages (six startup plus 9,638 timed),
byte-identical by step and byte sequence. OPEN observed 12807 real stream data events,
zero stream drops, positive client counts throughout and a joined stream
thread. Each arm observed 23,990 publisher overwrite drops; drops are permitted.

Statistics in milliseconds, produced by the exact validation command above:

| Arm / population | p50 | p95 | p99 | max |
| --- | ---: | ---: | ---: | ---: |
| CLOSED / all timed | 1.193604 | 195.494919 | 1964.508140 | 2456.832250 |
| CLOSED / worst segment | 1.171188 | 1.686271 | 2.028433 | 15.708708 |
| OPEN / all timed | 1.133437 | 172.940725 | 1893.404340 | 2341.836041 |
| OPEN / worst segment | 1.117166 | 1.621000 | 4.296681 | 27.703916 |
| CLOSED-B / all timed | 1.171125 | 195.213792 | 1993.492298 | 2445.737584 |
| CLOSED-B / worst segment | 1.150708 | 1.700490 | 8.679967 | 29.706667 |

The clean diagnostic failed the pooled p95 and p99 inequalities. The long
button fade/staged delays remain in the pooled population. R=1, unreadable
load and a Python client do not permit interpreting this as a qualifying
regression judgment; the RED is retained without weakening the rule.

Every before/after load command was `pgrep -f "while True: pass"`, invoked
serially (concurrency 1). All six checks exited 3 with empty stdout and stderr:

```text
sysmon request failed with error: sysmond service not found
pgrep: Cannot get process list
```

The exact load averages and checks are in `evidence/validation.json`; denied
process inventory was never called EMPTY. Every bridge was waited and proved
absent with kill(pid,0) immediately after termination:

| Arm | PID | Exit | Absent |
| --- | ---: | ---: | --- |
| CLOSED | 79257 | -15 | True |
| OPEN | 84932 | -15 | True |
| CLOSED-B | 89152 | -15 | True |

The first clean validation predates the final sensitivity-fault deadline
correction and outer wall-time field. Its embedded kit hashes identify exactly
what ran. The workload, capture/power-floor, pacing, percentile and clean
receiver paths are unchanged by that correction. The final sensitivity run
uses the final pinned kit and also exercises its ordinary CLOSED arms.

## Dense-load sensitivity control repair and final diagnostic

The optional first R=1 2 ms sensitivity attempt, using E3's positive
`time.sleep(0.002)`, failed OPEN with `TimeoutError: Packet capture incomplete`.
It is retained as `evidence/initial-sensitivity-invalid.json.gz` and its log;
it is INVALID, never sensitivity proof. It took 161.804470375 s before
returning exit 1. The receiver was still draining when the bounded timeout
fired; no complete packet digest or final sample population was credited.
Both started bridge PIDs were terminated, waited and proved absent.

Producer command (exit 1):

```sh
TMPDIR=/tmp/sdlive-e4 .venv/bin/python -B scripts/showready/timing_ab.py --candidate b2ca727c0acdc710a9ae98b6e01b76f3d4f28914 --script scripts/showready/timing_script.json --repeats 1 --control sensitivity --allow-unverified-load --scratch /tmp/sdlive-e4/sensitivity --out /tmp/sdlive-e4/sensitivity.json.gz
TMPDIR=/tmp/sdlive-e4 .venv/bin/python -B docs/sdlive-e4/check_delay.py
```

The serial perf_counter_ns probe (`evidence/delay-probe.json`, exit 0) ran
20 calls of each method, still load-unverified. Observed milliseconds:

| Delay method | Minimum | Maximum |
| --- | ---: | ---: |
| positive-sleep | 2.563500 | 18.022250 |
| deadline-yield | 2.000292 | 2.021708 |

E4 corrects the planted fault only: inside the disposable sensitivity
publisher, wait until a perf_counter_ns deadline 2 ms away, yielding with
sleep(0). A positive short sleep can expand to an OS timer tick. The new
clock-boundary unit test observes all yields before 2 ms and completion at
the deadline. No production, clean-arm or MIDI mapping code changed. The
injected delay is a minimum; host scheduling can still extend it. The
script and worst-case load were not weakened to rescue the control.

Final commands:

```sh
TMPDIR=/tmp/sdlive-e4 .venv/bin/python -B scripts/showready/timing_ab.py --candidate b2ca727c0acdc710a9ae98b6e01b76f3d4f28914 --script scripts/showready/timing_script.json --repeats 1 --control sensitivity --allow-unverified-load --scratch /tmp/sdlive-e4/final-sensitivity --out /tmp/sdlive-e4/final-sensitivity.json.gz
TMPDIR=/tmp/sdlive-e4 .venv/bin/python -B docs/sdlive-e4/verify_validation.py /tmp/sdlive-e4/final-sensitivity.json.gz --out docs/sdlive-e4/evidence/final-sensitivity.json
```

Instrument exit 1 with all arms complete and VALID, identical raw MIDI, and
`sensitivity_timing_red:true`; raw verifier exit 0. The full matrix took
235.732971083 s. R=1 + Python + UNVERIFIED-LOAD still cannot qualify
sensitivity for the gate. Under sustained worst-case load the planted delay
accumulates a queue; the larger observed MIDI delays are not a claim that
each injected wait lasts that long. Both load checks per arm remain retained
and unreadable (exit 3), never EMPTY.

| Arm | Replay s | Timed MIDI | Worst-segment MIDI | p50 ms pooled | p95 ms pooled | p99 ms pooled | PID / gone |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| CLOSED | 73.792243833 | 9638 | 9016 | 1.215750 | 194.315470 | 1954.049581 | 21869 / True |
| OPEN | 74.135180041 | 9638 | 9016 | 5113.717917 | 10391.091173 | 10797.507738 | 25133 / True |
| CLOSED-B | 73.846858708 | 9638 | 9016 | 1.265063 | 204.406760 | 1894.740706 | 29464 / True |

All pooled sensitivity inequalities are RED, valid_arms=true;
bar3_counts=false. Full p50/p95/p99/max for each worst segment and all
before/after checks are in `evidence/final-sensitivity.json` and raw
`evidence/final-sensitivity.json.gz`. Their kit hashes match the final pins.

## Final suite and existing UI verification

```sh
TMPDIR=/tmp/sdlive-e4 PYSTRAY_BACKEND=dummy BROWSER=/usr/bin/true .venv/bin/python -B -m unittest discover -s tests -p 'test_*.py'
TMPDIR=/tmp/sdlive-e4 node tests/ui_controller_check.cjs
TMPDIR=/tmp/sdlive-e4 node tests/ui_controller_macro_check.cjs
TMPDIR=/tmp/sdlive-e4 node tests/ui_reload_check.cjs
TMPDIR=/tmp/sdlive-e4 node tests/ui_sections_check.cjs
TMPDIR=/tmp/sdlive-e4 .venv/bin/python -B docs/sdlive-e2/check_geometry.py --chromium /Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell --scratch /tmp/sdlive-e4/geometry --single-process
```

Final full Mac suite: Ran 901 tests in 18.331s; OK (skipped=2), exit 0.
Skips: the pre-existing anticipated global-color cc_base remap, and the
PowerShell-only guard test (no PowerShell on this Mac). Four standalone Node
checks exit 0, byte-unchanged. The fifth Node check is the real Chromium
geometry detector invoked by E2's existing wrapper: 1,048/1,048 PASS, exit 0,
bridge PID 2918 proved gone. Evidence: `mac-suite-final.log.gz`,
`node-results.json`, `geometry-adapted.log.gz`, `geometry-receipt.json`.

The first direct `scripts/showready/ui_geometry.sh` invocation with the same
arguments refused `/tmp/sdlive-e4/` before starting a bridge (exit 2); that
older wrapper only permits `/tmp/sdfix-<link>/`. E2's committed adapter
permits the authorized lap scratch prefix and runs the identical Node
detector. Its successful real-browser result, not the refused wrapper, pays
the check. No UI assertion or product file was changed.

## Qualifying gate handoff

OWED TO THE GATE: R=5 real Chromium clean matrix and R=3 2 ms sensitivity on
Mac with readable before/after load checks; Windows suite and equivalent
Edge matrix with guard and PID proof, or the approved Python fallback; bar 1
full A/B MIDI instrument; Ben's hardware check and rollback readiness. These
are UNVERIFIED-BY-EXECUTION in E4. The geometry browser run above is not a
browser timing matrix. If Windows uses Python, REPORT.md must say plainly:
"The real-browser case is measured on the Mac only." No release credit comes
from E4's diagnostic numeric results. Ben owns merge and upgrade.

The commands below are copied from the final pinned README. Expected runtime
is 19-21 minutes for each R=5 clean command, 12-14 for each R=3 control,
31-35 minutes per host/client pair, excluding load retries. Nominal floors
from `70.400000882 * 3 * R / 60` are 17.600000221 and 10.560000132 minutes.
Browser/Windows estimates are UNVERIFIED-BY-EXECUTION, not measured promises.

### QUALIFYING commands: Mac with real Chromium

Run from the Mac checkout, one command at a time. Use the same candidate,
script and client argv in both commands; keep the kit unchanged between them.
The earlier pin/subset verification must pass first. These commands have no
accelerated or unverified-load flags. Each repeat is CLOSED / OPEN / CLOSED-B.
The sensitivity command should exit 1 with complete valid arms, identical
bytes and `sensitivity_timing_red:true`. An invalid arm is not sensitivity proof.
The clean command validates that receipt itself; only `bar3_counts:true` earns
credit. Do not interpret the control's exit code alone as success.

```bash
.venv/bin/python -B scripts/showready/timing_ab.py --candidate HEAD --script scripts/showready/timing_script.json --repeats 3 --control sensitivity --scratch /tmp/sdlive-gate/mac-sensitivity --out /tmp/sdlive-gate/mac-sensitivity.json.gz --client-cmd '["node","/Users/viddyslap/Documents/project-workspaces/steam-deck-midi/scripts/showready/timing_browser.cjs","{url}","{stop}","{receipt}","/Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell","--single-process"]'
.venv/bin/python -B scripts/showready/timing_ab.py --candidate HEAD --script scripts/showready/timing_script.json --repeats 5 --scratch /tmp/sdlive-gate/mac-clean --out /tmp/sdlive-gate/mac-clean.json.gz --sensitivity-result /tmp/sdlive-gate/mac-sensitivity.json.gz --client-cmd '["node","/Users/viddyslap/Documents/project-workspaces/steam-deck-midi/scripts/showready/timing_browser.cjs","{url}","{stop}","{receipt}","/Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell","--single-process"]'
```

Mac Python-client validation, DIAGNOSTIC only (about 4 minutes):

```bash
.venv/bin/python -B scripts/showready/timing_ab.py --candidate HEAD --script scripts/showready/timing_script.json --repeats 1 --allow-unverified-load --scratch /tmp/sdlive-gate/mac-diagnostic --out /tmp/sdlive-gate/mac-diagnostic.json.gz
```

### Real browser hook and owned process cleanup

`--client-cmd` is a JSON argv array, run directly without a shell.
`--client-cmd-file` reads the same array from a file for PowerShell.
`{url}`, `{stop}` and `{receipt}` placeholders are required. The foreground
adapter `timing_browser.cjs` creates a fresh profile, opens the real Controller,
enables Follow and consumes native EventSource events. Its ready receipt and
periodic page checks require Controller visible, live and Follow ON.
`PLAYWRIGHT_CORE` may point at an EXISTING playwright-core module.

The driver requests cooperative stop and waits for the adapter. The adapter
closes its owned browser server, then records `browser_pids`, `data_events`,
`dropped` and `error:null`. Playwright's Windows kill fallback addresses only
its launched PID tree (`taskkill /pid <owned pid> /T /F`), never an image name.
The driver independently checks each recorded PID with a file-backed
Get-Process script on Windows (kill(pid,0) on Mac). Missing receipts, early
exit or failed teardown invalidate an arm. Retain the final guard's Python
inventory as well. If any cleanup fails, stop, inspect the recorded owned PIDs
and clean up only those PID trees before the final guard; never kill Edge,
Python or the installed tray by process name.

### QUALIFYING commands: laptop with headless Edge

UNVERIFIED-BY-EXECUTION in E4. Only the gate touches the laptop. Run the guard
snapshot BEFORE the first act and compare AFTER the last act, including
artifact downloads and cleanup. Use `win_rail.sh`, the clone venv and existing
verified fixtures. Confirm pulled clone HEAD equals pushed Mac HEAD. Never
modify the orphan checkout. The sectioned Mac EDM Show fixture is consumed
with section `windows` on both hosts. No MIDI ports are available to the arms.

Save this body as `/tmp/sdlive-gate/timing.ps1`, then run the rail command below.
An existing Node/playwright-core installation is needed for the Edge adapter.
If dependencies are absent, select the Python fallback without any install.
If an existing Edge fails to launch, preserve the failed receipt, prove every
owned process gone, then rerun with `-PythonClient` to obtain BOTH a new
sensitivity receipt and clean result. A needed installer download instead is
NEEDS-MASTER and a stop, never a workaround.

When using the fallback, the gate's REPORT.md MUST state: "The real-browser
case is measured on the Mac only. Laptop timing used the Python streaming
client because <observed reason>." Do not claim Edge timing from Python data.
Both client modes require R=3 sensitivity then R=5 clean, with their own
matching receipt. Estimated wall time: 12-14 minutes then 19-21 minutes.

```powershell
param([switch]$PythonClient)
$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$work = 'C:\Users\Ben\AppData\Local\Temp\sdwin\sdlive-gate'
New-Item -ItemType Directory -Force -Path $work | Out-Null
$python = (Resolve-Path '.\.venv\Scripts\python.exe').Path
$env:PYSTRAY_BACKEND = 'dummy'
$env:BROWSER = 'C:/Windows/System32/cmd.exe /c rem %s'
$env:TMP = $work
$env:TEMP = $work
function Invoke-TrackedPython([string[]]$PythonArgs) {
  # Paths passed here have no embedded quotes; quote EACH argument for Windows.
  $quoted = $PythonArgs | ForEach-Object { '"' + $_ + '"' }
  $child = Start-Process -FilePath $python -ArgumentList $quoted -PassThru -NoNewWindow
  $child.Id | Add-Content -Encoding ascii -Path "$work\python-pids.txt"
  $null = $child.Handle
  $child.WaitForExit()
  $code = $child.ExitCode
  if (Get-Process -Id $child.Id -ErrorAction SilentlyContinue) { throw 'Python PID still exists' }
  return $code
}
$code = Invoke-TrackedPython @('-B', '-m', 'unittest', 'tests.test_showready_rail.ShowreadyPinTests.test_pins_match_exact_file_set_and_bytes')
if ($code -ne 0) { exit $code }
$code = Invoke-TrackedPython @('-B', 'scripts/showready/deck_script.py', '--out', "$work\deck-script.json")
if ($code -ne 0) { exit $code }
$code = Invoke-TrackedPython @('-B', 'scripts/showready/timing_subset_check.py', 'scripts/showready/timing_script.json', "$work\deck-script.json")
if ($code -ne 0) { exit $code }
$common = @('-B', 'scripts/showready/timing_ab.py', '--candidate', 'HEAD', '--script', 'scripts/showready/timing_script.json')
$edge = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
if (-not (Test-Path $edge)) { $edge = 'C:\Program Files\Microsoft\Edge\Application\msedge.exe' }
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $PythonClient -and ((-not (Test-Path $edge)) -or (-not $node) -or (-not $env:PLAYWRIGHT_CORE) -or (-not (Test-Path $env:PLAYWRIGHT_CORE)))) {
  $PythonClient = $true
  'Python fallback: existing Edge/Node/PLAYWRIGHT_CORE unavailable; real-browser case measured on Mac only.' | Set-Content -Encoding ascii "$work\client-choice.txt"
}
if (-not $PythonClient) {
  $client = @($node.Source, "$PWD\scripts\showready\timing_browser.cjs", '{url}', '{stop}', '{receipt}', $edge) | ConvertTo-Json -Compress
  $client | Set-Content -Encoding ascii -Path "$work\client-command.json"
  $common += @('--client-cmd-file', "$work\client-command.json")
  $label = 'edge'
} else {
  $label = 'python'
}
$code = Invoke-TrackedPython ($common + @('--repeats', '3', '--scratch', "$work\$label-sensitivity", '--out', "$work\$label-sensitivity.json.gz", '--control', 'sensitivity'))
if ($code -ne 1) { throw 'Expected sensitivity exit 1; inspect JSON before continuing' }
$cleanExit = Invoke-TrackedPython ($common + @('--repeats', '5', '--scratch', "$work\$label-clean", '--out', "$work\$label-clean.json.gz", '--sensitivity-result', "$work\$label-sensitivity.json.gz"))
exit $cleanExit
```

```bash
scripts/showready/win_rail.sh run sdlive-gate scripts/showready/win_guard.ps1 -Mode snapshot -Out 'C:\Users\Ben\AppData\Local\Temp\sdwin\sdlive-gate\before.json'
# Clone sync, suite, fixture/pin checks, and any existing module selection belong here.
scripts/showready/win_rail.sh run sdlive-gate /tmp/sdlive-gate/timing.ps1
# Fallback only after failed browser cleanup is proved: same command with -PythonClient.
# Download results and prove every recorded PID gone BEFORE final compare.
scripts/showready/win_rail.sh run sdlive-gate scripts/showready/win_guard.ps1 -Mode compare -Baseline 'C:\Users\Ben\AppData\Local\Temp\sdwin\sdlive-gate\before.json' -Out 'C:\Users\Ben\AppData\Local\Temp\sdwin\sdlive-gate\after.json'
```
