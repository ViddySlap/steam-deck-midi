## Highlights

Autopilot engine: bumped from v0.4.0 to v0.4.1 with four bug fixes and one feature change. Audio Engine and OSC Sync engines unchanged from v0.3.3.

### MODE selector replaces RANDOM toggle
Per-channel `RANDOM` Bool is now a tri-state `MODE` dropdown:
- **NONE** - cycle layer masters only; clips don't change. Use this while dialing in settings.
- **LINEAR** - cycle layer masters AND advance clips left-to-right (+1, wrap to 1).
- **RANDOM** - cycle layer masters AND draw clips from a per-layer shuffled bag (no immediate repeats).

### Bug fixes
- **LINEAR clip advance now works** - replaced the bogus `/composition/layers/N/connect_next_clip` OSC path with the indexed `/composition/layers/N/clips/M/connect`. Previously LINEAR silently no-op'd; only RANDOM actually changed clips.
- **Single-layer channels no longer flicker** - when a channel has exactly one selected layer (e.g. FX with only L5), the engine skips the cross-fade entirely and holds master at 1.0. Previously it wrote master=0 then master=1 every cycle, causing visible flicker.
- **Steam Deck column triggers now defer to next beat** - the note-emit filter was on the wrong channel (1 instead of 0) and only intercepted long-press notes (86/87). Now intercepts both short-press (82/83) and long-press (86/87) on channel 0, deferring all four to the next beat boundary and resetting autopilot to the lowest-indexed selected layer.
- **Resolume UI input lag reduced** - `override_poll_hz` dropped from 5.0 to 1.0 so the autopilot's REST poll no longer chokes Arena's single-threaded REST handler. Manual clip clicks now register reliably while autopilot is running.

### Wire patch + TouchOSC
- 3 MODE Int In dropdowns replace the 3 RANDOM Bool Ins. CCs unchanged (63/73/83). Inputs are placed inside the VIDEO/FX/LOGO Wire dashboard groups (group membership is required for Resolume's OSC routing - a root-level dashboard input is silently ignored by OSC).
- TouchOSC ENGINES page: 9 new mutually-exclusive MODE radio buttons (3 horizontal per channel x 3 channels) replace the 3 RANDOM toggles.

### Tests
- 9 new tests added to `tests/test_engines.py`, 7 existing tests refactored to match the new code paths. All 215 Windows tests pass.

## Install (Windows receiver)

Download `STEAMDECK-MIDI-RECEIVER-2-Setup-0.4.1.exe` and run it. The installer creates a fresh install at `C:\Program Files\STEAMDECK MIDI Receiver 2\` (separate from any v1 install).

After install, on first launch with a previous v0.4.0 dev config: legacy `cc_random` JSON keys are accepted (backwards-compatible read), so no manual migration needed. Factory defaults will auto-merge the new `clip_mode` field.

If you saved a comp during a v0.4.0 dev session, **remove + re-add the comp-level Autopilot Engine V1 effect after upgrading** to refresh Resolume's OSC route table.

## Deck (sender)

No changes to the sender side. Existing v0.2.0+ installs continue to work - but `STEAMDECK-MIDI-SENDER-SETUP-2.tar.gz` is included for fresh Deck setups.
