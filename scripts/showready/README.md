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
