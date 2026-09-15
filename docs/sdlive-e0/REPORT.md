BASE OF LAP 14aa21824843dbe148dc3ac3d0bf58929ef34c3a

# sdlive E0 - candidate checkpoint

Windows guard snapshot GREEN. Final compare and post-push Windows proof are
pending; this checkpoint is not a claim of completion. The final report will
put the guard compare result first and retain E0's BASE immediately below it.

## Proven cause and history

The unchanged test repeated through the rail at BASE: `RUNS 300
RUNS_WITH_ERROR 55`, 65 ConnectionAbortedError WinError 10053 subtest errors.
Command: `scripts/showready/win_rail.sh run sdlive-e0
/tmp/sdlive-e0/flake.ps1 -N 300`. Launcher 279004 and worker 267200 were
verified absent by Get-Process. See evidence/base-initial.log.

Scratch-only trace: `run_python.ps1 -Label trace-base` ran `trace_close.py`
over the archived BASE for 30 iterations. Every method returned 405 with
zero body bytes read: POST declared 1 and 4; PATCH and BOGUS declared 2.
Two WinError 10053 errors remained observable with instrumentation.
At trace-base.json events 280-289, PATCH's server response, reader close,
SHUT_WR and socket close happen before the client's body send returns.
The stdlib already invokes SHUT_WR; its immediate close leaves the body unread.
The client sends exactly Content-Length and reads the declared response before
its final close. POST /api/settings is unsupported, so the original test's
malformed JSON never reaches JSON parsing. This is a server close defect.

`git show 62b0dc4 -- tests/test_deck_control_api.py deck/` changes only the
learning test's pipe fixture to a selectable socket pair.
`git show 08b426c -- tests/test_deck_control_api.py deck/` moves POSIX imports
inside hardware methods. Neither changes this HTTP handler or failing test.
`git blame` assigns the failing test to 32368bf; `git log -- deck/control_api.py`
assigns the API to the same commit today. W1 EXPOSED the pre-existing defect
by making these tests importable on Windows. The changes today in 62b0dc4 and
08b426c must not be described as old or unrelated historical code.
This is the Deck sender control API, not the Windows receiver or Friday's MIDI
show path. No mapping, MIDI, tray, or receiver code is changed by E0.

## Fix

_Handler.finish drains a bounded, declared body left unread by early replies
before the stdlib closes the reader and socket. Normal JSON reads mark the body
as consumed, including malformed JSON, to prevent a second read. Existing
1 MiB and 3 second bounds apply; invalid lengths and unsupported transfer
encoding do not trigger a drain. JSON status/body generation is unchanged.
No retries, sleeps, reset suppression, skips, or loosened assertions were added.
All existing test assertions remain intact.

New tests observe actual bytes read from the live HTTP socket before close,
check exact JSON errors, unchanged settings bytes, no double reads, and bounded
close for invalid framing. The byte-read detector is RED at BASE and GREEN at
the candidate on Mac; Windows repetitions follow after this push.

## Executed Mac proof

- Whole suite: `TMPDIR=/tmp/sdlive-e0 PYSTRAY_BACKEND=dummy BROWSER=/usr/bin/true
  .venv/bin/python -m unittest discover -s tests -p 'test_*.py'`.
  868 tests, OK (skipped=2); exact final line retained with final evidence.
- All four unchanged Node checks: `TMPDIR=/tmp/sdlive-e0 node tests/<check>`
  for ui_controller_check.cjs, ui_controller_macro_check.cjs,
  ui_reload_check.cjs and ui_sections_check.cjs: exit 0.
- Real Chromium: original pinned wrapper rejects the lap's required scratch
  prefix. A scratch copy changes only ROOT/import location and allowed scratch
  prefix to /tmp/sdlive-. The unchanged tests/ui_controller_geometry.cjs runs.
  Default browser launch fails. The same wrapper with --single-process:
  `SUMMARY 1048/1048 PASS`, exit 0; bridge PID 3583 gone. Default bridge 2418 gone.
- `contract.py BASE ...` versus `contract.py ROOT ... BASE.json`, with
  PYTHONHASHSEED=0: 120 client-read HTTP replies identical across all 21 routes
  and tested error paths. Only fixture paths and heartbeat age are normalized.
  A planted BOGUS JSON error change fails the comparator (exit 1), and the clean
  candidate passes again. Original assertions are executed in both arms.

## Windows proof pending

After the candidate push: pull the clean clone with --ff-only and verify SHA;
original test 300 at HEAD (required zero errors), then 300 at archived BASE
(required resets); new byte-read regression on BASE and HEAD; two consecutive
full Windows suite runs. Download artifacts, prove all owned PIDs gone, and run
the guard compare as the final laptop act. No Windows or hardware result that
has not yet run is credited here.

## Next link

E1 uses E0's BASE above as the lap base. E1, E2, and E3 do not touch the laptop.
This E0 changes only Deck API close ordering and its tests outside docs.
The live controller and SHOW-READY bars 1, 3, 4 and 5 remain for their assigned
links/gate; E0 performs no MIDI timing arm or hardware check.
