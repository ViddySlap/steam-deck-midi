# agents.md — steam-deck-vj

## Project
- App name: `steam-deck-vj`
- Purpose: Provide a show-ready control bridge where Steam Deck inputs (mapped via Steam Input) become stable Action events that are sent over the network to a Windows machine, where they are converted into MIDI messages for Resolume.
- Primary users: VJs/live visual performers using a Steam Deck (SteamOS Desktop Mode) to control Resolume on a Windows machine over a dedicated 10.10.10.x network.
- Definition of done:
  - Steam Deck (SteamOS Desktop Mode / X11) has:
    - A **CLI Learn Wizard** that captures Steam Input–generated X11 key events and writes a profile mapping (token → Action ID).
    - A **sender** that captures key press/release events, translates to Action IDs using the profile, and transmits Action events over the network.
  - Windows has:
    - A **receiver** that listens for Action events, maps Action IDs → MIDI (Note/CC/etc), and outputs to a Windows virtual MIDI port visible to Resolume.
  - The system supports rapid prototyping:
    - Steam Input remains the only mapping UI.
    - After changing Steam Input, the user can re-run Learn Wizard to rebuild bindings without editing code.
  - The system is safe and reliable in a show context:
    - Clear connection/logging status.
    - No stuck notes/keys (failsafe on disconnect/timeouts).
    - Simple startup/shutdown procedures.
  - Documentation exists for setup, run commands, and troubleshooting.

## Product Goals
Top priorities:
1. **Reliability for shows**: predictable behavior, low latency, no stuck states, graceful reconnect.
2. **Rapid rebind workflow**: Steam Input changes require only rerunning Learn Wizard, not code edits.
3. **Clear contract**: Action IDs are the stable API; tokens/keys are disposable wiring.

Out of scope for v1:
- Steam Game Mode support (Desktop Mode only is acceptable).
- Full GUI configuration (CLI first; GUI later).
- Raw controller parsing (evdev/SDL analog interpretation) unless required later.
- Bi-directional feedback (Windows/Resolume → Deck).
- Programmatic modification of Steam Input configs.

## Development Environment
- This repo is edited in a **WSL (Ubuntu) environment on Windows**.
- The project targets two runtimes:
  - **Steam Deck**: SteamOS Desktop Mode, X11 session (captures Steam Input output as keyboard events).
  - **Windows**: receiver + MIDI output to a Windows virtual MIDI port.
- Constraint: WSL cannot fully validate Windows-native MIDI output behavior (virtual MIDI port presence, Windows MIDI stack). Windows receiver behavior must be tested on Windows proper.

## Tech Stack
- Language: Python 3 for both sides (v1).
- Steam Deck capture layer: X11 keyboard events (Steam Input → X11 keys).
- Network transport: small Action event messages over UDP (v1), with sequence numbers and timeouts.
- Windows MIDI output:
  - Primary target in v1: loopMIDI virtual port.
  - RTP-MIDI (AppleMIDI) is optional future work.
- Packaging (later milestone): PyInstaller for Windows; Deck runs as script/shortcut.

## Working Rules
- Preserve established patterns unless there is a strong reason to change them.
- Ask before making major architecture changes (protocol, file formats, switching MIDI backend).
- Ask before adding new dependencies unless clearly necessary.
- Prefer small, testable increments; avoid big rewrites.
- Keep logs concise and show-friendly.
- Do not introduce OS-wide hotkeys or destructive key combos.

## Scope Focus for This Agent
- Primary focus: **Windows receiver** (Action events → MIDI output).
- Secondary focus: **shared protocol and configuration formats** used by both Deck and Windows.
- Deck-side changes are allowed only when required to maintain protocol/config consistency, but avoid large Deck refactors here unless explicitly requested.

## Code Style
- Python style: `snake_case` for functions/modules/variables; type hints where helpful.
- Action IDs: `UPPER_SNAKE_CASE` (e.g., `BTN_A`, `RT_FULL`, `DPAD_UP`).
- Keep modules small and single-purpose (capture/learn/send/recv/midi/config/protocol).
- Validate config files and fail with actionable error messages.
- Avoid clever abstractions; prioritize debuggability.

## UX Guidelines (CLI-first)
- Learn Wizard should be guided, fast, and forgiving:
  - clear prompts (“Press control for BTN_A…”)
  - allow skip/back
  - warn on duplicates
  - write mappings atomically (avoid corrupting config)
- Provide a monitor/debug mode to show last-seen token/action and connection status.
- Default to safe verbosity; allow `--verbose`.

## Commands (initial expectations)
- Install: `pip install -r requirements.txt`
- Steam Deck:
  - Learn: `deck-learn --actions config/actions.yaml --out config/deck_bindings.json`
  - Send:  `deck-send --bindings config/deck_bindings.json --host 10.10.10.20 --port 45123`
- Windows:
  - Receive: `win-recv --listen 0.0.0.0:45123 --midi-port "SteamDeck VJ" --map config/windows_midi_map.json`

## Architecture
- Stable contract:
  - **Action IDs** = stable semantic API between Deck and Windows.
  - **Tokens** = disposable key identifiers captured from X11; mapped to Action IDs via Deck profile.
- Message format (v1):
  - Include: `action`, `state` (down/up), `seq`, optional `profile_name/profile_hash`.
- Failsafes:
  - Receiver must prevent “stuck” MIDI states on disconnect/timeouts (send note-offs / reset CCs as appropriate).
- Folder expectations (to be implemented):
  - `deck/` (learn + sender)
  - `windows/` (receiver + MIDI)
  - `protocol/` (message definitions/validation)
  - `config/` (actions list, deck bindings, windows midi map)
  - `docs/`

## Review Checklist
- Windows receiver:
  - Handles missing MIDI port gracefully with clear message.
  - Never produces stuck notes/controls.
  - Handles packet loss/out-of-order safely (sequence numbers/timeouts).
- Deck learn/sender:
  - Clear prompts and logs.
  - Writes config safely (atomic write).
- Any behavior changes are documented in `docs/`.
- No unnecessary dependencies added.

## Task Instructions
- Default: make reasonable assumptions and proceed unless a decision is risky.
- For larger changes: summarize the plan before editing.
- For bugs: identify root cause; add a small regression test if practical.
- For features: first version minimal and working; iterate.

## Notes For Codex
- Steam Input is the only mapping UI in v1.
- Learn Wizard only captures tokens and binds them to stable Action IDs.
- Prefer reliability and debuggability over fancy features.
- If chat instructions conflict with this file, follow the chat for that task.