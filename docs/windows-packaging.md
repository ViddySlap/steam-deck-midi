# Windows Packaging

This project can now build a standalone Windows receiver executable with PyInstaller.

## Scope

This step builds the receiver into a console `.exe`.

It does not yet create a final installer. The executable still expects:

- `loopMIDI` to already be installed on the target machine
- a Windows MIDI map JSON file
- runtime arguments, just like `py -m windows.win_recv`

## Prerequisites

- Windows
- Python 3.12 available as `py -3.12`

## Build

From PowerShell in the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\build_exe.ps1 -RepoRoot (Get-Location).Path
```

The build script will:

- create `.venv-build`
- install `requirements-build.txt`
- run PyInstaller with `steam-deck-vj-receiver.spec`
- write the output executable to `dist\steam-deck-vj-receiver.exe`

## Run The EXE

From the repo root after building:

```powershell
.\dist\steam-deck-vj-receiver.exe --map .\config\windows_midi_map.json --midi-port "DECK_IN" --verbose
```

The executable uses the same CLI options as the Python module:

- `--listen`
- `--midi-port`
- `--map`
- `--timeout`
- `--dry-run`
- `--verbose`

## Notes

- `loopMIDI` remains a third-party prerequisite.
- The build bundles the Python runtime and receiver code into a standalone console executable.
- The next packaging step is to wrap this executable in a proper installer.
