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
find scripts/showready -type f ! -name SHA256SUMS -exec shasum -a 256 {} \; | LC_ALL=C sort > /tmp/sdwin-w1/SHA256SUMS
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
Every capture includes raw status/data bytes and time.monotonic_ns timestamps.

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
