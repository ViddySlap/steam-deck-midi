## v0.4.2 — autopilot transition/duration normalization + wall-clock crossfade

Hotfix following v0.4.1's live test, same evening. Two bugs fixed in the autopilot engine; everything else identical to v0.4.1.

### Layer 'Trans Time' no longer saturates to 10s
`_send_layer_transition` was sending raw seconds to `/composition/layers/N/transition/duration`, but Resolume normalizes that path 0-1 over a 0-10s range. So setting the autopilot's TRANSITION fader to 1 second pushed the layer's Trans Time to 10s in Resolume. Most visible after manual column triggers (where Resolume's transition param actually drives behavior; the autopilot's own master-fade was masking the bug for cycle-driven transitions).

Fix: divide by `RESOLUME_LAYER_TRANSITION_MAX_SECONDS = 10.0` before sending. A 1s autopilot setting now lands as Trans Time = 1.0s.

### Cross-fade no longer jitters over time
The cross-fade ramp was using tick-derived elapsed time (averaged over a 24-tick MIDI clock window). Windows MIDI clock has timing jitter; the per-tick estimate jumped frame-to-frame, producing stuttering progress.

Fix: replaced `crossfade_start_tick: int` with `crossfade_start_time: float` and now compute elapsed as `time.monotonic() - crossfade_start_time`. Cross-fades are smooth regardless of MIDI clock variance — and complete on schedule even if Pulse pauses mid-fade.

### Tests
- 3 new tests: transition normalization (1s -> 0.1, 50s clamp -> 1.0) and wall-clock progress mid-fade.
- All 76 engine tests pass.

## Install (Windows receiver)

Download `STEAMDECK-MIDI-RECEIVER-2-Setup-0.4.2.exe`. Drop-in upgrade over v0.4.1 (no comp/Wire patch/TouchOSC re-touch needed).

## Deck (sender)

No changes from v0.4.1. The sender bundle is unchanged — keep using whichever you've got.
