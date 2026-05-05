# steam-deck-midi

Steam Deck MIDI is a show-focused Steam Deck to Windows MIDI bridge for Resolume.

The control contract is stable Action IDs:

- Steam Deck captures Steam Input-generated buttons.
- Deck sender maps button tokens to Action IDs and sends UDP JSON events.
- Windows receiver maps Action IDs to MIDI note/CC output for Resolume.

## Current status (v0.2.0 — in progress)

- Deck sender runtime uses direct X11/XI2 raw key listening (no `xinput test` subprocess parsing).
- Sender emits one `down`/`up` pair per press/release and heartbeat messages while held.
- Windows receiver supports:
  - action-to-note/CC/macro/axis mapping from named presets in `config/presets/`
  - `macro_cc` fades with feedback-aware manual override handling and per-mapping timing overrides
  - `relative_cc` repeat output for encoder-style controls
  - `staged_note_macro` for modifier+trigger two-channel note sequences
  - `axis_to_cc` for analog stick / gyro axis-to-CC with deadzone and curve shaping
  - duplicate suppression, timeout-based safety release, and panic/reset handling
  - separate MIDI output and feedback input port configuration
  - browser-based Mapping UI at `http://127.0.0.1:7723` with live hot-reload
  - preset system: named preset files, switch/save-as/rename/delete from the UI
  - macro library: saved behavior templates applied to any compatible mapping
  - system tray icon with UI shortcut and quit
- Steam Deck install flow provides branded desktop launchers:
  - `Learn Steam Input Map`
  - `STEAMDECK-MIDI-SENDER`
- Windows release flow includes PyInstaller + Inno Setup packaging.

See `TODO.md` for the remaining steps before the v0.2.0 release.

## Docs

- Receiver: `docs/windows-receiver.md`
- Windows install: `docs/windows-install.md`
- Windows packaging: `docs/windows-packaging.md`
- Windows release checklist: `docs/windows-release-checklist.md`
- GitHub release process: `docs/github-release.md`
- Steam Deck install: `docs/steamdeck-install.md`
- Deck sender behavior: `docs/deck-sender.md`
- Deck Learn Wizard: `docs/deck-learn-wizard.md`
- Deck release checklist: `docs/deck-release-checklist.md`
