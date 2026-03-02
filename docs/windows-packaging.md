# Windows Packaging

This project can now build a standalone Windows receiver executable with PyInstaller.

## Scope

This flow now has two layers:

- a standalone receiver `.exe`
- a final installer `.exe`

The standalone receiver still expects:

- `loopMIDI` to already be installed on the target machine
- a Windows MIDI map JSON file
- runtime arguments, just like `py -m windows.win_recv`

## Prerequisites

- Windows
- Python 3.12 available as `py -3.12`

## Build The Receiver EXE

From PowerShell in the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\build_exe.ps1 -RepoRoot (Get-Location).Path
```

The build script will:

- create `.venv-build`
- install `requirements-build.txt`
- run PyInstaller with `steamdeck-midi-receiver.spec`
- write the output executable to `dist\STEAMDECK-MIDI-RECEIVER.exe`

## Run The EXE

From the repo root after building:

```powershell
.\dist\STEAMDECK-MIDI-RECEIVER.exe --map .\config\windows_midi_map.json --midi-port "DECK_IN" --verbose
```

The executable uses the same CLI options as the Python module:

- `--listen`
- `--midi-port`
- `--map`
- `--timeout`
- `--dry-run`
- `--verbose`

## Build The Installer EXE

Install Inno Setup 6 on the Windows build machine.

Then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\build_installer.ps1 -RepoRoot (Get-Location).Path
```

This expects `dist\STEAMDECK-MIDI-RECEIVER.exe` to already exist.

The installer build will:

- package the receiver EXE
- include default config files
- include a launcher PowerShell script for the installed app
- create `installer-output\STEAMDECK-MIDI-RECEIVER-Setup.exe`

## What The Installer Produces

The installer EXE installs:

- `STEAMDECK-MIDI-RECEIVER.exe`
- `config\windows_midi_map.json`
- `config\windows_receiver_settings.example.json`
- `scripts\start_installed_receiver.ps1`
- desktop and Start Menu shortcuts

The installed shortcut launches the packaged EXE using the installed config files.

## Notes

- `loopMIDI` remains a third-party prerequisite.
- The PyInstaller build bundles the Python runtime and receiver code into a standalone console executable.
- The installer build wraps that executable into a single setup EXE for distribution.
