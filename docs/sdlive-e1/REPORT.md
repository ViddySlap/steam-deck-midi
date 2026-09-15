BASE OF LAP 14aa21824843dbe148dc3ac3d0bf58929ef34c3a

# sdlive E1 - live bridge events

Entry HEAD: c406d6e60d268e79334da398168ff07ad94690a2 (E0 complete).
E0's final report places GUARD above BASE; the BASE value above is copied from
its BASE line. This link has made no laptop acts.

This candidate adds bounded live events, receive and forward-first MIDI hooks,
SSE and snapshot routes, and functional/revert controls. The final evidence
commit will record the A/B verdicts at this candidate. A/B is pending at this
initial candidate commit; it is not credited until the evidence is appended.

## Timing qualification

OWED TO THE GATE: execute ` .venv/bin/python -B docs/sdlive-e1/measure.py
/tmp/sdlive-e1/timing.json` on a host where the required CPU inventory works.
Serial `pgrep -f 'while True: pass'` returns exit 3, empty stdout and
`sysmon request failed with error: sysmond service not found` followed by
`pgrep: Cannot get process list`. The same failure occurred before and after
the guarded script's attempted first arm. No benchmark operation ran; the
script exits 78 with HARNESS-SKIP. Unreadable is not empty. No bar 3 timing
credit is claimed. E3/EG still own the final paced open/closed MIDI test.

The no-client path is O(1): a nonblocking writer try-lock, sequence/time and
bounded latest-state bookkeeping, and deque append. It does more work than a
literal bare append because snapshots must retain state after history loss.
It performs no reader lock, notification, client iteration, JSON or socket I/O.
The guarded benchmark records its complete cost; its thresholds are watchdogs
for accidental blocking, not an upgrade/latency acceptance threshold.
