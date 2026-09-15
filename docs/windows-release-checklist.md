# Windows Release Checklist

Use this checklist when preparing a USB-friendly Windows release.

## Build Machine

- use a Windows machine
- ensure Python 3.12 is installed
- ensure Inno Setup 6 is installed
- ensure the repo is up to date

## Version Bump

Before building, set the new version in every touchpoint and commit it:

- `VERSION` - the single source: `build_exe_v2.ps1` and `build_installer_v2.ps1` read it, and
  the installer gets it as `/DAppVersion` (the `0.1.0` default in
  `installer/windows/steamdeck-midi-receiver-2.iss` is only a fallback; do not edit it).
- `windows/build_fingerprint.py` - set `APP_VERSION` to the same version; the checked-in copy
  keeps `GIT_COMMIT`, `GIT_COMMIT_SHORT` and `BUILD_TIME_UTC` at `source`. `build_exe_v2.ps1`
  rewrites the whole file from `VERSION` and `git rev-parse HEAD` at build time; do not commit
  the build-written copy. `tests/test_ui_server.py` fails if `VERSION` and `APP_VERSION` differ.
- `README.md` - the `Current status` heading and its version line.
- `TODO.md` - the version line in the status note at the top.

After the build, `GET /api/version` on the running bridge (and the editor status bar) must
report the new version with `frozen: true`.

## Build

From the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\build_exe_v2.ps1 -RepoRoot (Get-Location).Path
```

Verify:

- `dist\STEAMDECK-MIDI-RECEIVER-2.exe`

Then build the installer (it rebuilds the EXE first):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\build_installer_v2.ps1 -RepoRoot (Get-Location).Path
```

Verify:

- `installer-output\STEAMDECK-MIDI-RECEIVER-2-Setup-<version>.exe`

## USB Contents

Copy to the USB drive:

- `installer-output\STEAMDECK-MIDI-RECEIVER-2-Setup-<version>.exe`
- a short text note with setup steps if desired

## Target Machine Setup

On the target Windows machine:

1. Install `loopMIDI`.
2. Create a `DECK_IN` loopMIDI port.
3. Run `STEAMDECK-MIDI-RECEIVER-2-Setup-<version>.exe`.
4. Launch `STEAMDECK MIDI Receiver 2` from the desktop or Start Menu shortcut.
5. In Resolume, enable MIDI input on `DECK_IN`.
6. Keep Resolume MIDI output on that port disabled.

## Upgrade Behavior

- installer updates the packaged EXE and example config files
- installer preserves `config\windows_receiver_settings.local.json`

Edit `windows_receiver_settings.local.json` on installed machines for machine-specific settings.
