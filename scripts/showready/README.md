# Windows show-ready rail

The installed v0.4.9 is frozen. This kit only transports scripts and observes
protected state. Run these commands from the Mac checkout on
`chain/steamdeck-20260914`.

## Transport

```bash
scripts/showready/win_rail.sh run w2 /tmp/sdwin-w2/check.ps1 -Example 'value with spaces'
scripts/showready/win_rail.sh put w2 /tmp/sdwin-w2/input.json
scripts/showready/win_rail.sh get 'C:\Users\Ben\AppData\Local\Temp\sdwin\w2\result.json' /tmp/sdwin-w2/result.json
```

`run` and `put` copy the local basename into
`C:\Users\Ben\AppData\Local\Temp\sdwin\<tag>\`. Tags contain letters,
numbers, underscores and hyphens, starting with a letter or number. `run`
streams stdout/stderr unchanged and exits with the SSH/remote process exit
code. Stderr alone does not imply failure. The script always uses PowerShell
`-NoProfile -ExecutionPolicy Bypass -File`. Every SSH and SCP call uses the
pinned LAN host, key, identity-only, batch, strict-host-key, and timeout options.
If SSH fails, stop; do not try another network route.

Arguments preserve spaces, commas and literal wildcards. Remote arguments
containing double quotes, percent, exclamation, caret, ampersand, pipe, angle
brackets, CR or LF are refused before upload to prevent cmd.exe expansion.
Put complex inputs in a JSON file and pass its path. No inline PowerShell.

## Guard: first and last laptop acts

```bash
scripts/showready/win_rail.sh run w2 scripts/showready/win_guard.ps1 -Mode snapshot -Out 'C:\Users\Ben\AppData\Local\Temp\sdwin\w2\before.json'
# Authorized work, including process teardown and artifact downloads.
scripts/showready/win_rail.sh run w2 scripts/showready/win_guard.ps1 -Mode compare -Baseline 'C:\Users\Ben\AppData\Local\Temp\sdwin\w2\before.json' -Out 'C:\Users\Ben\AppData\Local\Temp\sdwin\w2\after.json'
```

The final compare must be the last laptop act. Its exit 0 means every field
matched, all required protected observations were nonempty, and Get-Process
found no python/pythonw executable under the clone or sdwin work root.
It prints each changed JSON field and exits 1 for differences/leaks/missing
observations, or 2 for read/parse errors. Stop the line on any nonzero exit.
A snapshot containing a leaked Python process also exits 1. The guard writes
only `-Out`; its parent must exist under the sdwin work directory. It refuses
to overwrite the baseline. Do not place timestamps in the compared schema.

The guard covers UDP 45123, TCP 7723 listeners, tray and loopMIDI process
identities/start times, installed file metadata/count, config file SHA256s,
orphan HEAD/status, and clone/work Python processes. Missing/unreadable data
cannot become a successful empty comparison. Orphan status is hashed as
UTF-8 porcelain lines joined by LF without a trailing LF. Installed metadata
is hashed as compact JSON sorted by full path, with relative path, length
and UTC modification time. Config hashes include hidden files and subfolders.

Installed user config is `C:\Program Files\STEAMDECK MIDI Receiver 2\config`.
Evidence: installer v2 `[Dirs]` makes it user-writable and `[Icons]` supplies
that `--map`; `start_installed_receiver_v2.ps1` derives settings from InstallRoot.
`windows/tray.py:default_log_path` uses LOCALAPPDATA for logs. The guard also
records config directory presence/hashes at Local, Roaming and VirtualStore
alternatives. See `docs/sdwin-w1/REPORT.md` for live command-line confirmation.

## Isolated clone and suite

Clone: `C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc`.
It has its own Python 3.12 `.venv`. No system package installs.
Put a `.ps1` in Mac scratch, then execute it through `win_rail.sh run`.
The Windows full-suite command from the clone is:

```powershell
Set-Location 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$env:PYSTRAY_BACKEND = 'dummy'
$env:BROWSER = 'C:/Windows/System32/cmd.exe /c rem %s'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
exit $LASTEXITCODE
```

Record the exact command, `Ran N tests`, result and exit code. If console
encoding requires `-X utf8`, record why and use it before `-m`.
Use Start-Process with PassThru when running Python so its PID can be recorded,
waited for and checked with Get-Process after exit. Test scratch/logs belong
under the link's sdwin work directory. Real socket tests request port 0, letting
Windows atomically allocate a free port. CLI tests mock socket/tray/MIDI edges.

Update the clone only after a Mac commit is pushed and verified:

```powershell
git -C 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc' pull --ff-only
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
git -C 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc' rev-parse HEAD
exit $LASTEXITCODE
```

Compare that SHA to the Mac HEAD. v0.4.9 is an annotated tag; compare its
peeled commit with `git rev-parse 'v0.4.9^{commit}'` (e66ff44...).

## Never-touch rules

- Never stop/restart/reconfigure the installed tray, its files, or user config.
- Never touch loopMIDI ports or Resolume; no real MIDI input or output may open.
- Never start a receiver with `--tray`. Use `--no-ui`, dry-run/stub MIDI and
  non-default UDP/UI ports checked free first. Any UI-enabled test must use
  PYSTRAY_BACKEND=dummy, a no-op BROWSER and a non-default UI port.
- Never change the orphan checkout at
  `C:\Users\Ben\Documents\project-workspaces\steam-deck-midi`.
  Read it only with `git --no-optional-locks`.
- Every started process must be stopped and its PID proved gone. Final guard
  compare rejects any python/pythonw still under the clone/work paths.
- No installer download or system-wide install; report NEEDS-MASTER and stop.
- No scripts, logs or test arms inside the clone. Mac scratch: /tmp/sdwin-<link>/.
- Presets are copied to ignored fixtures, never changed or committed.

## Pin verification

`tests/test_showready_rail.py` checks the exact file set and SHA256 bytes plus
the rail transport contract. After an intentional reviewed kit change:

```bash
{ find scripts/showready -type f ! -name SHA256SUMS -exec shasum -a 256 {} \;; shasum -a 256 tests/ui_controller_geometry.cjs; } | LC_ALL=C sort > /tmp/sdwin-w1/SHA256SUMS
cp /tmp/sdwin-w1/SHA256SUMS scripts/showready/SHA256SUMS
```

Pinning detects drift; it does not replace live rail and guard controls.

## A/B MIDI instrument (W3)

Harness code uses only the Python standard library. The bridge arms use the
checkout venv. Run from the Mac run root. The generator verifies BOTH W2
fixture manifests before reading any presets; ab_run repeats that verification
and refuses a preset that is absent from those manifests.

The sole additional accepted path is the repository's tracked
`config/presets/default.json`. Its content must equal the candidate Git blob
(allowing LF/CRLF checkout conversion only); the result hashes the actual
consumed bytes. Arbitrary unmanifested files and edited defaults are refused.
W4 uses this path for its separate tracked-default replay on Windows.

Generate ONE script, shared by every comparison (create scratch first):

```bash
mkdir -p /tmp/sdwin-w3
.venv/bin/python -B scripts/showready/deck_script.py --out /tmp/sdwin-w3/deck-script.json
```

Each line below is a complete later-gate command. Replace HEAD with the
candidate commit when pinning a release. Outputs over 1 MB get a .gz suffix.
Sectioned fixtures automatically run A(flat), B1(same flat), and B2(sectioned
with --preset-section windows); both candidate arms must equal A.

```bash
.venv/bin/python -B scripts/showready/ab_run.py --candidate HEAD --preset '.showready/fixtures/mac/presets/EDM Show.json' --section windows --script /tmp/sdwin-w3/deck-script.json --out /tmp/sdwin-w3/mac-edm.json
.venv/bin/python -B scripts/showready/ab_run.py --candidate HEAD --preset '.showready/fixtures/mac/presets/PTZ.json' --section windows --script /tmp/sdwin-w3/deck-script.json --out /tmp/sdwin-w3/mac-ptz.json
.venv/bin/python -B scripts/showready/ab_run.py --candidate HEAD --preset '.showready/fixtures/mac/presets/default.json' --script /tmp/sdwin-w3/deck-script.json --out /tmp/sdwin-w3/mac-default.json
.venv/bin/python -B scripts/showready/ab_run.py --candidate HEAD --preset '.showready/fixtures/windows-installed/presets/EDM Show.json' --script /tmp/sdwin-w3/deck-script.json --out /tmp/sdwin-w3/windows-edm.json
.venv/bin/python -B scripts/showready/ab_run.py --candidate HEAD --preset '.showready/fixtures/windows-installed/presets/PTZ.json' --script /tmp/sdwin-w3/deck-script.json --out /tmp/sdwin-w3/windows-ptz.json
.venv/bin/python -B scripts/showready/ab_run.py --candidate HEAD --preset '.showready/fixtures/windows-installed/presets/default.json' --script /tmp/sdwin-w3/deck-script.json --out /tmp/sdwin-w3/windows-default.json
.venv/bin/python -B scripts/showready/ab_run.py --candidate HEAD --preset '.showready/fixtures/windows-installed/presets/test 1.json' --script /tmp/sdwin-w3/deck-script.json --out /tmp/sdwin-w3/windows-test1.json
.venv/bin/python -B scripts/showready/ab_run.py --candidate HEAD --preset '.showready/fixtures/windows-installed/presets/v1 Default.json' --script /tmp/sdwin-w3/deck-script.json --out /tmp/sdwin-w3/windows-v1-default.json
```

The same capture_runner.py runs both untouched archived code trees. It replaces
open_midi_output with a raw-byte recorder, denies MIDI input and all mido/rtmidi
port constructors, validates loopback/non-default ports, and runs that arm's
windows.win_recv.main with --no-engines --no-pulse --no-osc-relay --no-ui.
No --tray. The config argument must be inside its disposable arm. Both the
runner and driver check ports by binding before boot. The receiver's actual
socket bind writes the ready file; logs are never used as readiness evidence.
Every received packet is checked against the script, in order, and hashed.
Every capture includes raw status/data bytes and time.perf_counter_ns
timestamps (stored in monotonic_ns fields). Sender and recorder use the same
monotonic high-resolution clock. On Windows Python 3.12, time.monotonic_ns
uses GetTickCount64 at 15.625 ms resolution; perf_counter uses
QueryPerformanceCounter. Each result records its timestamp clock properties.

The default --clock script injects the receiver's EXISTING clock argument,
advancing it at each actual UDP receipt to the script timestamp. It does not
replace dispatch, fades, staged notes, relative CC, timeout or release logic.
Legal heartbeat packets every 10 ms drive delayed work to fixed instants in
both arms. Wall pacing defaults to --speed 1. Each full stream takes at least
470 seconds; delayed wakes extend the run. The sender preserves every
Deck-event gap after a delay, so mapped inputs never arrive in catch-up
bursts. Heartbeat timer probes use offsets within each event dwell. Axis
waits yield until due to avoid short-sleep coalescing; button waits sleep. Measured
axis interval counts/minimum/median/maximum are retained per arm and phase;
any interval below the scripted minimum makes the run fail. This is synthetic Deck input and controlled receiver time, with
real loopback UDP and real MIDI-backend calls. It proves byte regression under
that schedule; it does not certify live scheduler timing or physical MIDI.
--clock wall uses the ordinary receiver clock for diagnosing A/A timer noise.
--speed other than 1 is explicitly an accelerated control, not real-rate credit.

The script has all 75 Action IDs: 62 button IDs at 100 ms and 1.6 s dwell;
13 axes, nine evenly spaced range points plus zero, out and back, at 60 Hz
and 10 Hz. HID representable ranges include stick center offsets, unsigned
16-bit triggers, signed pad positions, and clamped integrated gyro positions.
This is source-derived, not a measurement of physical end stops. Explicit zero
probes include centers that the current HID reader suppresses. LONG_PRESS and
LAYER_2 are already separate IDs on the wire, not derived by a bridge hold
threshold. relative_cc does repeat while held. The 2.25 s isolation gap is the
longest preset fade/staged delay (2 s) plus one 250 ms receiver poll. Gaps are
between button trials and completed axis sweeps; intra-sweep events keep the
specified rate. The result embeds parameters, sources, and the entire script.

All steps, including startup output and unmapped IDs, must compare byte-for-
byte. A mapping earns coverage only with received inputs and mapping-directed
MIDI on BOTH sides; startup bytes cannot pay coverage. Missing mappings, dropped
packets, zero capture, early death and cleanup failure are nonzero. No mapping
in these presets needs an engine to emit its direct MIDI; engine subscriptions,
feedback-driven behavior and real hardware remain outside this instrument.
No missing mapping is silently labeled NOT COVERED. An unknown/new unsupported
mapping remains red until explicitly investigated.

Controls (same preset/script; A against A uses --candidate v0.4.9):

```bash
.venv/bin/python -B scripts/showready/ab_run.py --candidate v0.4.9 --preset '.showready/fixtures/mac/presets/default.json' --script /tmp/sdwin-w3/deck-script.json --out /tmp/sdwin-w3/aa.json
.venv/bin/python -B scripts/showready/ab_run.py --candidate v0.4.9 --preset '.showready/fixtures/mac/presets/default.json' --script /tmp/sdwin-w3/deck-script.json --control sensitivity --mapping BTN_A --out /tmp/sdwin-w3/sensitivity.json
.venv/bin/python -B scripts/showready/ab_run.py --candidate v0.4.9 --preset '.showready/fixtures/mac/presets/default.json' --script /tmp/sdwin-w3/deck-script.json --control coverage --mapping BTN_A --out /tmp/sdwin-w3/coverage.json
.venv/bin/python -B scripts/showready/ab_run.py --candidate v0.4.9 --preset '.showready/fixtures/mac/presets/default.json' --script /tmp/sdwin-w3/deck-script.json --control dead-seam --out /tmp/sdwin-w3/dead-seam.json
```

Run A/A twice. Sensitivity increments only BTN_A's note in the disposable
candidate config; expected exit 1 and different_mappings=[BTN_A]. Coverage
removes BTN_A input packets; expected exit 1 and unexercised_mappings=[BTN_A].
Dead seam records no MIDI on either arm; expected exit 1 even if bytes match.
The result retains process IDs, terminate/wait method and PID absence proof.
Raw captures, arm stdout and copied trees remain in the unique reported scratch
folder, with no running processes. The driver never calls an HTTP shutdown API.

## Controller geometry (Mac, real Chromium)

```bash
scripts/showready/ui_geometry.sh --chromium '/Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell' --scratch /tmp/sdfix-u1/geometry --single-process --mutations
```

The wrapper copies tracked working files and verified Mac fixtures into a unique
scratch tree. It boots the UI with dummy tray, no-op browser, dry-run MIDI,
engines/pulse/OSC relay off, and free loopback TCP 17841 / UDP 47841 (override
with --ui-port / --listen-port). It terminates and waits for its bridge PID,
then requires os.kill(pid, 0) to report absence. receipt.json records commands,
exit codes, scratch paths, effective settings and teardown. No laptop acts.
Use --revision <sha> for a before-repair control with the current detector.

The standalone detector boots nothing:
`node tests/ui_controller_geometry.cjs URL CHROMIUM --single-process --out DIR`.
Set PLAYWRIGHT_CORE to an installed playwright-core module if the gate's Mac
path differs. It measures 23 labels/shapes/leaders, all pairwise label overlaps
and leader-segment intersections, each endpoint's own shape boundary (3 px),
all SVG text against lines/arrowhead triangles, pane containment/scroll and
label centre hit-testing at four viewport sizes, closed, A open, and the label
nearest the open card. It also clicks every label and compares drill-in actions
with the owned map. PNGs and raw page-coordinate geometry accompany assertions.
The check is deliberately outside unittest discovery; unittest pins its bytes.

--mutations requires pristine GREEN, then each planted DOM fault to exit 1 at
its named real-geometry assertion, then restored GREEN in a fresh browser page:
(m1) swap A/B leader targets, (m2) overlap A/B labels, (m3) put A under the status
bar. All mutations live in browser DOMs served from the scratch fixture copy;
no production file or preset is mutated. Each mutant's log retains its RED.
A browser launch failure is a nonzero result, never geometry credit. Try default
launch first, then --single-process (one browser at a time), and record errors.

## Bar 3 timing instrument (sdlive E3)

`timing_ab.py` reuses the pinned Deck generator, recorder, archive, fixture
verification, byte coverage comparator and pacing helpers. It starts UI-enabled
archived candidate processes only, with dummy tray, no-op BROWSER, engines/pulse/
OSC relay off, disposable sectioned EDM Show (`--preset-section windows`), and
free non-default loopback UDP/TCP ports. No real MIDI constructor is available.
The candidate is resolved once. No installed bridge, port or preset is touched.

The arms run serially in INTERLEAVED order CLOSED, OPEN, CLOSED-B, repeated
R times. Default R=5, minimum 5. CLOSED has no HTTP client at all during replay;
its in-process publisher snapshots must show zero clients. OPEN's Python client
fetches snapshot, subscribes from its sequence, drains SSE as fast as it can,
and refreshes/reconnects on drops as the page does. An additional 250 ms HTTP
snapshot monitor proves client presence throughout OPEN. It is the same monitor
for an external browser. Headers/keepalives alone cannot pay stream coverage:
at least one real data event, positive client counts and an explicit dropped
count are required. Snapshot overwrite counts and stream missed counts are
reported separately; coalescing is not counted as dropping.

### Clock and origin of each MIDI message

Sending is a thread INSIDE the bridge process. Sender and the existing Recorder
both timestamp with `time.perf_counter_ns()` in that SAME PID; no cross-process
offset or resolution assumption is needed. The old recorder field name
`monotonic_ns` is retained for W3 compatibility, and the timing record additionally
names it `perf_counter_ns`. Latency is recorded minus sent, in milliseconds.
W4 measured Python 3.12 on the laptop: `monotonic_ns` used GetTickCount64 at
15.625 ms, while `perf_counter_ns` used QueryPerformanceCounter at 100 ns.
These coarse monotonic values must never be subtracted for this instrument.
Clock implementation and resolution are captured separately in every arm.

The recorder uses E1's current Action ID plus accepted-input publication to
associate output with input. Immediate note/CC releases belong to UP; fades,
relative repeats and staged outputs retain their initiating DOWN through UP.
Timer heartbeats are not credited as physical inputs. Each MIDI row retains
both current replay step and causal input step. Unknown attribution, a negative
latency or zero samples fails. Startup MIDI has no causal input: its bytes are
compared but it has no fabricated latency. Intentional hold/fade/staged delays
are INCLUDED in the latency distribution, not subtracted. Top outliers identify
the initiating step, action, phase, exact MIDI bytes and both timestamps.

`--clock script` (default) retains W3's deterministic receiver scheduling so
identical timer output can be required. Latencies and UDP pacing still use real
perf_counter time. `--clock wall` is an additional diagnostic of the ordinary
bridge scheduler; all comparisons and controls must use the same mode. The
script-clock test measures observer overhead under the pinned schedule; it does
not certify ordinary Windows scheduler behavior. E3's report separately audits
that scheduler, without changing it.

### Locked verdict rule

Compute p50, p95, p99 and max of latency per arm (pooled over repeats) and per
repeat. The NOISE FLOOR is |CLOSED - CLOSED-B| per statistic. Bar 3 PASSES when,
for p50, p95 and p99, |OPEN - CLOSED| <= NOISE FLOOR + 1.0 ms AND the byte sequence
of every arm is identical to CLOSED (the bar 1 property, re-checked), AND the
stream's dropped count is reported (drops are allowed; delay is not). Report max
separately, not as a pass criterion, with the top 5 outliers and their steps.

The tolerance is ONE named constant: `BAR3_TOLERANCE_MS = 1.0` in timing_ab.py.
Percentiles use linear interpolation at `(N-1)*p/100`. The pooled rule determines
the numeric outcome; per-repeat rules are also retained, including noisy reds.
A floor wide enough to admit a synthetic +2 ms shift makes the measurement
invalid. The real sensitivity run must additionally fail the timing inequality;
a byte difference, client death or packet loss alone does not prove sensitivity.
If the NOISE FLOOR is wide enough that the 2 ms sensitivity control passes,
bar 3 does not count and the report says so.

The clean command needs `--sensitivity-result` from the same candidate, script,
preset, host/Python runtime, receiver clock, client command and pinned instrument. It must be a
qualified 2 ms timing RED with complete valid arms and identical bytes. This
receipt is hashed. A numeric pass without this proof is exit 78 with HARNESS-SKIP,
never bar 3 credit. Invalid arms/rule failure are exit 1. Qualified clean PASS is
exit 0. The sensitivity control is expected to exit 1; inspect
`sensitivity_timing_red`, not merely its exit. NULL is the nonempty identical
CLOSED/CLOSED-B comparison against its measured floor; that timing inequality
holds by construction and does not independently certify low host noise.

### Duration and load qualification

The FULL pinned script lasts 469.716666743 seconds before scheduling overhead.
Five interleaved triplets need at least 7045.750001145 seconds (117.43 minutes),
plus startup/cleanup. R=5 minimizes this mandatory cost. A roughly ten-minute
full-rate run is mathematically incompatible with this script and R>=5.
Do not truncate it or accelerate it for release credit.

Before AND after every attempted arm, Mac runs `pgrep -f "while True: pass"`
and records stdout, stderr, exit code and `os.getloadavg()`. Only exit 1 with
empty output/error is EMPTY. Present load discards the attempt, waits 30 seconds
and re-runs it, with at most `--load-retries 3` attempts. Exhaustion fails.
Unreadable inventory fails closed unless `--allow-unverified-load` is explicitly
set: then every affected arm is UNVERIFIED-LOAD and cannot earn bar 3 credit.
Windows records `not applicable` for pgrep and load average.

For executor diagnostics ONLY, `--speed 15 --allow-unverified-load` compresses
wall pacing, retaining the complete script and its receiver logical time.
It also drains the preceding bridge loop before each accelerated packet to
prevent compressed timer probes overflowing UDP in the sleep mutant. Neither
acceleration nor this drain exists at speed 1. This mode targets approximately
ten minutes per five-triplet run; wall time is recorded, not promised. It is
never a timing qualification. The gate's unaccelerated load-verified run is
authoritative. Hardware and Windows suite remain separate show-ready bars.

### Gate commands: Mac

From this checkout, generate once, then run sensitivity followed by clean:

```bash
mkdir -p /tmp/sdlive-gate
.venv/bin/python -B scripts/showready/deck_script.py --out /tmp/sdlive-gate/deck-script.json
.venv/bin/python -B scripts/showready/timing_ab.py --candidate HEAD --script /tmp/sdlive-gate/deck-script.json --scratch /tmp/sdlive-gate/sensitivity --out /tmp/sdlive-gate/sensitivity.json.gz --control sensitivity
.venv/bin/python -B scripts/showready/timing_ab.py --candidate HEAD --script /tmp/sdlive-gate/deck-script.json --scratch /tmp/sdlive-gate/clean --out /tmp/sdlive-gate/clean.json.gz --sensitivity-result /tmp/sdlive-gate/sensitivity.json.gz
.venv/bin/python -B scripts/showready/timing_ab.py --candidate HEAD --script /tmp/sdlive-gate/deck-script.json --scratch /tmp/sdlive-gate/dead --out /tmp/sdlive-gate/dead.json.gz --control dead-client
```

### Real browser hook (Mac and Windows)

`--client-cmd` is a JSON argv array, run directly without a shell.
`--client-cmd-file` reads that array from a JSON file, avoiding PowerShell
native-argument quote stripping. `{url}`,
`{stop}` and `{receipt}` placeholders are required. The command stays foreground,
owns its browser, never daemonizes, and writes an atomic JSON receipt with
`ready:true` after Controller is visible, live, and Follow is ON. It polls the
stop-file path and gracefully closes every owned child before exiting 0. The
final receipt reports `browser_pids`, `data_events`, `dropped`, and `error:null`.
The driver requests stop, waits, checks its process handle and checks each
reported browser PID (kill(pid,0) on Mac; a file-backed Get-Process script on
Windows). A missing receipt/PID, early exit or failed teardown invalidates the
arm. Gate must additionally retain the Windows guard's final Python inventory.

The pinned adapter `timing_browser.cjs` creates a fresh browser profile, opens
the real Controller page, enables Follow, consumes native EventSource events,
and samples actual visibility/live/Follow state. It closes the browser server
and reports the browser PID for the driver's independent absence check.
`PLAYWRIGHT_CORE` may identify an existing playwright-core installation.

Add this identical option to BOTH sensitivity and clean commands on the Mac:

```bash
--client-cmd '["node","/Users/viddyslap/Documents/project-workspaces/steam-deck-midi/scripts/showready/timing_browser.cjs","{url}","{stop}","{receipt}","/Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell","--single-process"]'
```

### Gate commands: laptop (UNVERIFIED-BY-EXECUTION in E3)

Only the gate runs these, with the existing win_rail.sh guard snapshot BEFORE
its first laptop act and guard compare AFTER its last, including downloads.
Use the clone venv, verify clone HEAD after pull, and put this body in a local
.ps1 carried by `scripts/showready/win_rail.sh run sdlive-gate <local.ps1>`.
No inline PowerShell. Do not change/install dependencies if absent: escalate.
The sectioned EDM Show fixture is the verified MAC fixture on both hosts.

```powershell
$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$work = 'C:\Users\Ben\AppData\Local\Temp\sdwin\sdlive-gate'
New-Item -ItemType Directory -Force -Path $work | Out-Null
$python = (Resolve-Path '.\.venv\Scripts\python.exe').Path
$env:PYSTRAY_BACKEND = 'dummy'
$env:BROWSER = 'C:/Windows/System32/cmd.exe /c rem %s'
function Invoke-TrackedPython([string[]]$PythonArgs) {
  $child = Start-Process -FilePath $python -ArgumentList $PythonArgs -PassThru -NoNewWindow
  $child.Id | Add-Content -Encoding ascii -Path "$work\python-pids.txt"
  $child.WaitForExit()
  $code = $child.ExitCode
  if (Get-Process -Id $child.Id -ErrorAction SilentlyContinue) { throw 'Python PID still exists' }
  return $code
}
$code = Invoke-TrackedPython @('-B', 'scripts/showready/deck_script.py', '--out', "$work\deck-script.json")
if ($code -ne 0) { exit $code }
# Set PLAYWRIGHT_CORE to the gate's already installed module. Verify Edge exists.
$edge = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
if (-not (Test-Path $edge)) { throw 'NEEDS-MASTER: existing browser required' }
$client = @('node', "$PWD\scripts\showready\timing_browser.cjs", '{url}', '{stop}', '{receipt}', $edge) | ConvertTo-Json -Compress
$client | Set-Content -Encoding ascii -Path "$work\client-command.json"
$common = @('-B', 'scripts/showready/timing_ab.py', '--candidate', 'HEAD', '--script', "$work\deck-script.json", '--client-cmd-file', "$work\client-command.json")
$code = Invoke-TrackedPython ($common + @('--scratch', "$work\sensitivity", '--out', "$work\sensitivity.json.gz", '--control', 'sensitivity'))
if ($code -ne 1) { throw 'Expected sensitivity exit 1; inspect JSON timing inequality before continuing' }
$cleanExit = Invoke-TrackedPython ($common + @('--scratch', "$work\clean", '--out', "$work\clean.json.gz", '--sensitivity-result', "$work\sensitivity.json.gz"))
$code = Invoke-TrackedPython @('-B', 'scripts/showready/timing_ab.py', '--candidate', 'HEAD', '--script', "$work\deck-script.json", '--scratch', "$work\dead", '--out', "$work\dead.json.gz", '--control', 'dead-client')
if ($code -ne 1) { throw 'Dead client was not rejected' }
exit $cleanExit
```

Wrap this work using the rail's Start-Process/PassThru PID recording convention,
then Get-Process checks, downloads, and final guard compare. Do the Python-reader
matrix separately by omitting `--client-cmd` from BOTH runs. The browser matrix
must use its own sensitivity receipt. No E3 laptop command was executed.
