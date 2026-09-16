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
{ find scripts/showready -type f ! -name SHA256SUMS -not -path '*/__pycache__/*' -exec shasum -a 256 {} \;; shasum -a 256 tests/ui_controller_geometry.cjs; } | LC_ALL=C sort > /tmp/sdwin-w1/SHA256SUMS
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

## Engine A/B instrument (sdauto A1)

The bar 1 A/B above runs `--no-engines`, so engine output is not covered there.
`engine_ab.py` covers every engine that writes to the shared MidiOut:
autopilot (with its note-emit filter that defers or drops L_PAD_LEFT,
L_PAD_LEFT_LONG_PRESS, L_PAD_RIGHT and L_PAD_RIGHT_LONG_PRESS on ch0),
l_stick_layer, gyro_feedback, global_color and audio_opacity (protocol midi).
Harness code is standard library plus ab_run/deck_script helpers; the arms use
the checkout venv. It verifies both fixture manifests before reading a preset.

Each arm is an untouched `git archive` tree in its own Python process (both
revisions are the `windows` package). Inside it, engines are built by THAT
revision's `load_engines` + `bind_registry` from the SAME five config stanzas:
the v0.4.9 factory configs with OSC/REST rewritten to loopback, audio_opacity
set to protocol midi, and the active flags from the preset's `engines` block.
OSC and REST clients are recording fakes, the RNG is seeded, any socket or
MIDI port open is refused and counted, and time is the script's fake clock.
The script calls the registry the way windows/receiver.py does (feedback CCs,
Deck CCs and notes through `should_emit_note`, note-offs, axis events, MIDI
clock start/stop/continue, ticks, refresh) with the preset's own note and L4
mappings. Arms: A = v0.4.9; B_nostate = candidate with `state_dir=None`;
B_state = candidate with the default `config/state/` present and empty (it must
end holding `autopilot_channels.local.json` whenever autopilot is active, or
persistence was not exercised). Both B arms must equal A event for event: MIDI
bytes, OSC address and value, and every filter decision.

Coverage: an engine the preset leaves active needs output on every arm (MIDI,
plus OSC for autopilot and global_color; autopilot also at least one re-emitted
and one dropped column note). An engine the preset turns off must emit nothing
outside `load` and `refresh`. Zero observations is RED, never a pass. The
result's `coverage` table names each engine, its per-arm counts and the input
kinds that produced output.

```bash
mkdir -p /tmp/sdauto-engine-ab
.venv/bin/python -B scripts/showready/engine_ab.py --candidate HEAD --preset '.showready/fixtures/mac/presets/EDM Show.json' --section windows --out /tmp/sdauto-engine-ab/mac-edm.json
.venv/bin/python -B scripts/showready/engine_ab.py --candidate HEAD --preset '.showready/fixtures/windows-installed/presets/EDM Show.json' --out /tmp/sdauto-engine-ab/windows-edm.json
.venv/bin/python -B scripts/showready/engine_ab.py --candidate HEAD --preset '.showready/fixtures/mac/presets/PTZ.json' --section windows --out /tmp/sdauto-engine-ab/mac-ptz.json
.venv/bin/python -B scripts/showready/engine_ab.py --candidate HEAD --preset '.showready/fixtures/windows-installed/presets/PTZ.json' --out /tmp/sdauto-engine-ab/windows-ptz.json
```

Exit 0 and `passed: true` only when both comparisons are identical, coverage
holds and no socket/port was attempted. Controls (expected exit 1 and
`control_expected: true`; exit 2 means the control did NOT behave):

```bash
.venv/bin/python -B scripts/showready/engine_ab.py --candidate HEAD --preset '.showready/fixtures/mac/presets/EDM Show.json' --section windows --control sensitivity-autopilot --out /tmp/sdauto-engine-ab/sens-autopilot.json
.venv/bin/python -B scripts/showready/engine_ab.py --candidate HEAD --preset '.showready/fixtures/mac/presets/EDM Show.json' --section windows --control sensitivity-l_stick_layer --out /tmp/sdauto-engine-ab/sens-lstick.json
```

`sensitivity-autopilot` changes one byte of the candidate copy's column note set
(86 to 96); `sensitivity-l_stick_layer` flips the low bit of the positive CC
number it emits. Each must make the candidate differ from A with exactly that
engine family in `different_sources` (`receiver` may also differ when the
filter decides differently). Coverage in a control run is judged on arm A.
The copied trees, script, captures and arm logs stay in the reported work
folder; each arm process has exited before the result is written.

## Idle CPU and shutdown instrument (sdpolish P0)

`idle_smoke.py` is the rerunnable form of the tray CPU check. It boots the
NON-TRAY bridge as a real subprocess on loopback ports the installed tray does
not own, idles it, measures process CPU as a CPU-TIME DELTA as a percentage of
ONE core, then stops it twice - once by SIGINT and once by POST /api/shutdown -
and proves the process gone.

NEVER `--tray`. See "Never-touch rules": the installed tray owns UDP 45123 and
TCP 7723, and this instrument picks other ports and asserts it.

DECLARED BEFORE DATA: CPU <= 5% of one core, exit within 5 s, no new crash
report in `~/Library/Logs/DiagnosticReports`.

ON THE MAC IT RUNS WITHOUT `PYSTRAY_BACKEND=dummy` (MASTER 13, 14:28), so the
REAL tray path executes and the darwin no-sidecar line is asserted. Every other
load rule still applies, and `BROWSER` stays a no-op. This is the ONE exception
to the dummy-backend clause; do not copy it to another instrument.

The load preflight (spinners, load1, foreign_lines, the vault sync, free
memory) runs INSIDE the script, before and after every arm. An arm whose
preflight fails is INVALID - never PASS and never FAIL. A quiet gate waits for
load1 < 4.0 AND a quiet vault sync before each arm, because the sync is bursty
and a gate before the arm beats voiding it afterwards.

QUALIFYING commands (both machines, every gate):

```
# HEAD, no engines: the tray class
BROWSER=/usr/bin/true .venv/bin/python -B scripts/showready/idle_smoke.py \
  --scratch /tmp/sdpolish-p0/smoke --label mac-head --out /tmp/sdpolish-p0/mac-head.json

# HEAD, engines ON, from a loopback-rewritten scratch copy of the factory configs
BROWSER=/usr/bin/true .venv/bin/python -B scripts/showready/idle_smoke.py --engines \
  --scratch /tmp/sdpolish-p0/smoke --label mac-head-engines --out /tmp/sdpolish-p0/mac-head-engines.json
```

SENSITIVITY. `--engines-update-hz <hz>` forces that rate onto autopilot in the
scratch copy. Run it against a `git archive` extract of the BASE revision: the
BASE arm must FAIL and the HEAD arm must PASS. MEASURED IN P0 ON THE MAC:
`--engines-update-hz 0` fires (BASE dies with ZeroDivisionError, HEAD passes at
0.94%), while `--engines-update-hz 100000` DOES NOT (BASE 4.88%, HEAD 1.38%,
against a 5% bar) - and 1e9 at BASE reaches only 4.585%, so the huge-rate shape
is not a CPU-detectable event on this machine at any rate. Use 0.

ENGINES-ON RULE: the factory configs point at Ben's Resolume network and at
real PTZ cameras. `--engines` copies them to scratch, rewrites every address to
loopback, and REFUSES THE BOOT if the scan finds any non-loopback target. Record
the scan count (0) with every engines-on arm.

## Controller geometry (Mac, real Chromium)

```bash
scripts/showready/ui_geometry.sh --chromium '/Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell' --scratch /tmp/sdpolish-p1/geometry --single-process --mutations
```

SCRATCH is a PATTERN, not a lap name: any `/tmp/sd<lap>-<link>/...` (or the
`/private/tmp` form macOS resolves it to) is accepted and everything else is
refused, so a new lap needs no edit here. `deck_script.scratch_ok` owns the
predicate and `tests/test_showready_scratch_pattern.py` asserts both directions.
Create `.metadata_never_index` in the scratch BEFORE the first file is written.

The wrapper copies tracked working files and verified Mac fixtures into a unique
scratch tree. It boots the UI with dummy tray, no-op browser, dry-run MIDI,
engines/pulse/OSC relay off, and free loopback TCP 17841 / UDP 47841 (override
with --ui-port / --listen-port). It terminates and waits for its bridge PID,
then requires os.kill(pid, 0) to report absence. receipt.json records commands,
exit codes, scratch paths, effective settings, the pristine failure list, the
mutation table and teardown. No laptop acts.
Use --revision <sha> for a before-repair control with the current detector.

The standalone detector boots nothing:
`node tests/ui_controller_geometry.cjs URL CHROMIUM --single-process --out DIR
[--only-viewport WxH] [--closed-only]`.
Set PLAYWRIGHT_CORE to an installed playwright-core module if the gate's Mac
path differs.

LIVE-VIEW AWARE. It NEVER waits on `networkidle`: the Controller view holds an
open EventSource, so the network never goes idle. It waits for the 23
`.controller-label` elements AND `#controllerLiveStatus` reading `live`, then
drives real UDP axis packets at the bridge's own listen address so the stick
dots are off centre, both trigger bars are non-zero and the gyro dots are drawn.
`<tag>.stream-live-with-overlays-drawn` asserts that state per measurement, so a
run that lost the stream cannot pass the obstacle criteria vacuously.

VIEWPORTS AND STATES: 1024x768, 1366x768, 1440x900 and 1920x1080, card closed
and with EACH of the 23 cards opened in turn (P2 may move any control, so a
crowded card anywhere has to fail, not only the two an older loop happened to
open). 8,175 assertions per full run.

CRITERIA. Every sdfix criterion still binds: 23 labels/shapes/leaders/arrowheads,
all pairwise label overlaps, leader-segment intersections, each endpoint on its
own shape boundary (3 px), scene text against lines and arrowhead triangles,
pane containment, page/pane scroll, label centre hit-testing, card inside the
pane, and the drill-in action list against the owned map. Live-overlay text is
judged by criterion b2, not by `glyph-clear`, because it is an overlay and not
scene art. Added in sdpolish P1:

- `b.no-leader-through-other-control` - no leader segment, bend or arrowhead
  intersects or touches (distance 0) the geometry box of any OTHER control's
  `data-control` shape, live trigger track or live bar.
- `b2.no-live-overlay-over-card-or-label` - with a card open, no stick dot,
  trigger bar, track or gyro dot intersects the open card or any of the 23
  label boxes.
- `c.leader-clearance-6px` - the minimum distance between any two DIFFERENT
  leaders' segments, bends and arrowheads is >= 6.0 px. The measured minimum and
  the pair are reported for every viewport and card state, pass or fail.
- `d.drawer-rows-visible` - at 1024x768 ONLY, with each card open in turn, the
  card title, its tabs and the first two action rows (all rows if fewer) have
  their bounding boxes fully inside the card's visible area, with the card's own
  scrollTop at 0.

--mutations. m1-m3 are planted in the live DOM by the check; m4-m6 are planted
in the SERVED STATIC FILES of the scratch tree, so the fault reaches the browser
the way a real layout regression would, and the original bytes are written back
and re-compared after each. (m1) swap A/B leader targets, (m2) overlap A/B
labels, (m3) put A under the status bar, (m4) `controller_map.json` routes
dpad_up's leader through the L2 trigger track, (m5) `controller_map.json` drops
dpad_right's waypoint three scene pixels toward left_pad's leg - a deliberate
near miss, 4.63 px against the 6 px floor with `leader-intersections` still
GREEN, so only criterion c can catch it, (m6) `controller_view.css` pushes the
card header down for controls that own an analog group, which catches r2 and
leaves btn_a's line byte-identical. `--only-mutation mN` runs one.

A mutation is PROVEN by what it changed in its own assertion's line. A boolean
flip (PASS pristine -> FAIL mutated) is the strong case. Where an assertion is
ALREADY RED on today's picture a flip is unavailable and proves nothing, so the
mutation must instead put a planted MARKER into that assertion's detail that the
pristine detail does not carry (or, with a leading `!`, remove one the pristine
detail does), and the restored run must return the line to the pristine line
byte for byte. Assertions listed as `unchanged` must be identical to pristine,
which is how selectivity is shown. `--pristine-may-fail` records a RED pristine
run instead of aborting; it does NOT weaken any of the above. Drop it once the
picture is green - the gate runs without it.
A browser launch failure is a nonzero result, never geometry credit. Try default
launch first, then --single-process (one browser at a time), and record errors.

## Laptop bundle route (pinned)

Code reaches the laptop clone by bundle only, NEVER a GitHub fetch from the
laptop. `scripts/showready/pull_bundle.ps1` is docs/sdpick-k1's verified script
with `-Bundle <path>` in place of the hardcoded `sdpick.bundle` name; nothing
else differs, and `tests/test_showready_pull_bundle.py` asserts that line by
line together with both parameters and every exit code.

```bash
# On the Mac, from the run root:
git bundle create /tmp/sd<lap>-<link>/steamdeck.bundle <clone HEAD>..<Mac HEAD> chain/steamdeck-20260914
shasum -a 256 /tmp/sd<lap>-<link>/steamdeck.bundle
scripts/showready/win_rail.sh put /tmp/sd<lap>-<link>/steamdeck.bundle 'C:\Users\Ben\AppData\Local\Temp\sdwin\<link>\steamdeck.bundle'
scripts/showready/win_rail.sh put scripts/showready/pull_bundle.ps1 'C:\Users\Ben\AppData\Local\Temp\sdwin\<link>\pull_bundle.ps1'
scripts/showready/win_rail.sh run 'powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\Ben\AppData\Local\Temp\sdwin\<link>\pull_bundle.ps1 -Bundle C:\Users\Ben\AppData\Local\Temp\sdwin\<link>\steamdeck.bundle -Expected <full Mac HEAD sha>'
```

Record every output line and the exit code. EXIT CODES: 0 success only, 3 dirty
clone, 4 `git bundle verify`, 5 fetch, 6 FETCH_HEAD != -Expected, 7 `merge
--ff-only`, 8 HEAD or porcelain after the merge.

## Bar 3 timing instrument (sdlive E3)

`timing_ab.py` reuses the pinned Deck generator, recorder, archive, fixture
verification, byte coverage comparator and pacing helpers. It starts UI-enabled
archived candidate processes only, with dummy tray, no-op BROWSER, engines/pulse/
OSC relay off, disposable sectioned EDM Show (`--preset-section windows`), and
free non-default loopback UDP/TCP ports. No real MIDI constructor is available.
The candidate is resolved once. No installed bridge, port or preset is touched.

The arms run serially in INTERLEAVED order CLOSED, OPEN, CLOSED-B, repeated
R times. Default R=5; clean qualification requires R>=5 and sensitivity R>=3. CLOSED has no HTTP client at all during replay;
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

The injected 2 ms fault uses a perf_counter_ns deadline with sleep(0) yields
inside the disposable publisher. A positive sleep(0.002) can expand to an OS
timer tick and overrun this workload; no production code or clean arm is changed.
The deadline is a minimum, so host scheduling can still extend the delay.

The clean command needs `--sensitivity-result` from the same candidate, script,
preset, host/Python runtime, receiver clock, client command and pinned instrument. It must be a
qualified 2 ms timing RED with complete valid arms and identical bytes. This
receipt is hashed. A numeric pass without this proof is exit 78 with HARNESS-SKIP,
never bar 3 credit. Invalid arms/rule failure are exit 1. Qualified clean PASS is
exit 0. The sensitivity control is expected to exit 1; inspect
`sensitivity_timing_red`, not merely its exit. NULL is the nonempty identical
CLOSED/CLOSED-B comparison against its measured floor; that timing inequality
holds by construction and does not independently certify low host noise.

### Pinned short timing workload (sdlive E4)

`--script <path>` was already required in E3 and remains explicit. The full
Deck generator and bar 1 commands above are unchanged. For bar 3 use the
committed `scripts/showready/timing_script.json`; the gate does not edit or
regenerate the release workload in place.

The E4 generator selects events from the pinned full Deck script (logical
SHA256 `9256621abf62eb21e6c345ef286b6b7fcc087a2db87b8f682ce7fcf7703a993e`).
It changes only selection, order and pacing. Regeneration is exclusive-create:

```bash
mkdir -p /tmp/sdlive-gate
shasum -a 256 -c scripts/showready/SHA256SUMS
.venv/bin/python -B scripts/showready/deck_script.py --out /tmp/sdlive-gate/deck-script.json
.venv/bin/python -B scripts/showready/timing_subset_check.py scripts/showready/timing_script.json /tmp/sdlive-gate/deck-script.json
.venv/bin/python -B scripts/showready/timing_script.py /tmp/sdlive-gate/deck-script.json --out /tmp/sdlive-gate/regenerated-timing.json
cmp scripts/showready/timing_script.json /tmp/sdlive-gate/regenerated-timing.json
```

The generator command reports composition and duration: 124 button events
(62 IDs, exactly one down/up pair each), 15,246 axis events and 5,143 legal
heartbeat timer probes. Schedule: 70.400000882 seconds. Button down dwell is
100 ms, release gap 250 ms; an additional 2.25 s settles timers before the
worst case, and after the last axis. Button timers may overlap during the
button segment; attribution retains their initiating input. Bar 1 still uses
its full, isolated-timer workload.

The named `simultaneous-sticks-triggers-60hz` segment contains 2,520 ticks,
42.000000840 seconds: L/R stick X/Y plus L/R trigger pressure every tick,
interleaved in that order. Per-axis tick interval is 16,666,667 ns, rounded
from `deck/xinput_send.py`'s `AXIS_MIN_INTERVAL = 1.0 / 60.0`. One-nanosecond
ordering offsets represent each tick's batch in the existing strictly ordered
packet format. Real sends take measurable time, retain every scheduled gap,
and never catch up. Pacing evidence follows EACH axis across interleaved ticks;
zero intervals or overspeed fail. Remaining seven axes also sweep at 60 Hz.
The mechanical subset check examines every decoded wire packet and step,
ignores only sequence numbers, rejects foreign encodings and mismatched
step/packet metadata, and refuses an empty script.

Each arm reports `timed_midi_messages` and `timing_status`. Fewer than 1,000
causally timed MIDI messages is `INVALID`, even with identical bytes and green
latency inequalities. Startup output cannot pay this floor. Both per-repeat
and pooled verdicts refuse an invalid arm. Rows include the worst segment's
own p50/p95/p99/max/count; `summary.worst_case.pooled_ms` pools only that
segment's messages across repeats, selected by causal input step. An empty
worst-case population fails. The locked inequality still uses the full pooled
population; separate segment statistics remain visible for inspection.

### Duration and load qualification

Clean qualification requires R>=5. The approved 2 ms sensitivity control
requires R>=3. Smaller R (including R=1) runs diagnostically and can never
qualify. Speed must remain 1. Mac Python-client runs are always DIAGNOSTIC;
Mac qualification requires the real Chromium client through `--client-cmd`.
Windows may use the Python client only under the fallback described below.

Nominal schedule costs, computed as `70.400000882 * 3 * R / 60`:
R=5 clean = 17.600000221 minutes; R=3 sensitivity = 10.560000132 minutes.
E4's R=1 Python validation measured about 74 seconds of replay per arm.
Budget about 19-21 minutes for each qualifying clean command, 12-14 minutes
for each sensitivity command, and 31-35 minutes total per host/client pair.
These are estimates, UNVERIFIED-BY-EXECUTION for Chromium/Edge qualification;
startup, browser cleanup, host scheduling and load retries add wall time.
A one-triplet Python diagnostic is about 4 minutes. Every actual replay
retains `wall_seconds`; the outer result also records total wall time.

Before AND after every attempted arm, Mac runs `pgrep -f "while True: pass"`
and records stdout, stderr, exit code and `os.getloadavg()`. Only exit 1 with
empty output/error is EMPTY. Present load discards the attempt, waits 30 seconds
and re-runs it, with at most `--load-retries 3` attempts. Exhaustion fails.
Unreadable inventory fails closed unless `--allow-unverified-load` is explicitly
set: then every affected arm is UNVERIFIED-LOAD and cannot earn bar 3 credit.
Windows records `not applicable` for pgrep and load average.

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

### Declared M_bridge rule (sdbar3 B1)

In plain terms: the locked rule times each MIDI message from the send stamp of
the input step that caused it, so the test rig's own pacing between that input
and the timer heartbeat that actually releases a delayed output sits inside the
number. M_bridge times each MIDI message from the send of the datagram the
bridge was handling when it wrote that message: `t1_pre`, a perf_counter_ns
taken IMMEDIATELY BEFORE `sendto()` for EVERY packet. It therefore excludes only
the rig's pacing and includes the send syscall, kernel delivery, bridge wake-up
and processing. A stamp after `sendto()` (`t1_post`) would shrink the number
exactly when a loaded sender is descheduled after the send, a bias toward PASS
with the view open, so `M_post = t3 - t1_post` is reported as a diagnostic only.
`M_total = t3 - t0` is the locked metric, computed by the same function and
printed beside M_bridge in every run (the `BESIDE` line), so the locked-rule RED
stays visible; the default `--rule locked` is unchanged.

`--rule m_bridge` PASSES when M_bridge's pooled |OPEN - CLOSED| <= |CLOSED - CLOSED-B| + 1.0 ms at p50,
p95 AND p99, on the pinned `timing_script.json`, R=5 interleaved CLOSED / OPEN /
CLOSED-B, Mac + Chromium, bytes identical, the live client proven, every arm
with >= 1000 timed MIDI messages in the every-message set and a clean load
check. Under `--rule m_bridge` the load check also counts `foreign_lines`
(`ps -A -o pid=,command=` rows of zsh/bash/sh/node running a script under the
harness engine tests or `run-all.sh`, excluding `codex exec`) and records
sysctl load1; any foreign line is present load. The locked rule's "floor must
resolve 2 ms" clause is reported but not required: the declared rule proves
resolution only through its own sensitivity run. The six-axis worst-case segment
is reported on its own (`m_bridge.worst_case`). Each arm row reports BOTH counts:
`first_packet_join` (messages timed against a step's first-packet stamp, the
locked set) and `every_message` (messages timed against their own packet's
t1), plus how many of the latter were caused by a step's first packet or by a
later packet (timer heartbeat or axis follow-on).

The sensitivity control is the existing 2 ms publisher delay at R=3. If its
M_bridge inequality is not RED, the tool prints
`M_BRIDGE RULE INVALID: sensitivity control did not go RED` and exits 3, never a
pass. A RED control exits 1 with `m_bridge_sensitivity_timing_red:true`. The clean command accepts only
an `--rule m_bridge` receipt with that RED from the same candidate, host, client,
script and pinned instrument.

QUALIFYING commands, Mac + real Chromium, one at a time, sensitivity first. The
gate also records load1 and foreign_lines around each command. Measured wall
time for the same workload in the sdlive gate: sensitivity R=3 691 s (11.5 min),
clean R=5 1135 s (18.9 min); budget 12-14 and 19-21 minutes plus load retries.

```bash
.venv/bin/python -B scripts/showready/timing_ab.py --rule m_bridge --candidate HEAD --script scripts/showready/timing_script.json --repeats 3 --control sensitivity --scratch /tmp/sdbar3-gate/mac-mbridge-sensitivity --out /tmp/sdbar3-gate/mac-mbridge-sensitivity.json.gz --client-cmd '["node","/Users/viddyslap/Documents/project-workspaces/steam-deck-midi/scripts/showready/timing_browser.cjs","{url}","{stop}","{receipt}","/Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell","--single-process"]'
.venv/bin/python -B scripts/showready/timing_ab.py --rule m_bridge --candidate HEAD --script scripts/showready/timing_script.json --repeats 5 --scratch /tmp/sdbar3-gate/mac-mbridge-clean --out /tmp/sdbar3-gate/mac-mbridge-clean.json.gz --sensitivity-result /tmp/sdbar3-gate/mac-mbridge-sensitivity.json.gz --client-cmd '["node","/Users/viddyslap/Documents/project-workspaces/steam-deck-midi/scripts/showready/timing_browser.cjs","{url}","{stop}","{receipt}","/Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell","--single-process"]'
```

M_bridge Python-client diagnostic, never qualifying (about 4 minutes):

```bash
.venv/bin/python -B scripts/showready/timing_ab.py --rule m_bridge --candidate HEAD --script scripts/showready/timing_script.json --repeats 1 --scratch /tmp/sdbar3-b1/diagnostic --out /tmp/sdbar3-b1/diagnostic.json.gz
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
