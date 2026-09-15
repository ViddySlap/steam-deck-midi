GUARD GREEN: compare; protected state observed; pythonProcesses=0 (exit 0)
BASE OF LAP 14aa21824843dbe148dc3ac3d0bf58929ef34c3a

# sdlive E0 - Deck control API connection reset

Candidate code: `9fc224a7d1232042ab32575b02c61be510747fa2` on
`chain/steamdeck-20260914`. The final E0 commit adds evidence and this report;
its product and test bytes are the candidate bytes tested on Windows.
E0 initially wrote BASE as the first line before any source changes. This final
report puts the guard result first as required by the laptop rule.

## Result

The Deck sender control API closed rejected HTTP requests with unread body
bytes. W1 exposed this existing defect by making the Deck tests importable on
Windows. Draining the declared, bounded body before closing removes the reset
without changing HTTP responses or MIDI code.

| Windows observation | Runs with error / runs | Error kinds | Command / evidence |
| --- | ---: | --- | --- |
| Original test, BASE before edits | 55 / 300 | 65 WinError 10053 subtest errors | `flake.ps1 -N 300`; [log](evidence/base-initial.log) |
| Original test, pushed candidate | 0 / 300 | none | `run_python.ps1 -Label head-300`; [full command/log](evidence/head-300.log) |
| Original test, archived BASE after candidate | 66 / 300 | 70 WinError 10053 subtest errors | `run_python.ps1 -Label base-control-300`; [full command/log](evidence/base-control-300.log) |
| New byte-read regression, archived BASE | 300 / 300 | unread-byte assertions plus 95 WinError 10053 and 2 WinError 10054 | `run_python.ps1 -Label regression-base-300`; [full command/log](evidence/regression-base-300.log) |
| New byte-read regression, pushed candidate | 0 / 300 | none | `run_python.ps1 -Label regression-head-300`; [full command/log](evidence/regression-head-300.log) |

The original test's four subtests each run once per iteration; errors above
count subtests, not iterations. No retries occur. `repeat.py` is the gate's
one-process loop with explicit root/test/output arguments and a required
GREEN or RED outcome. Its exit 0 on a RED control means the required actual
failures were observed, not that the test passed. The JSON artifacts retain
runs-with-error, exception kinds and per-subtest counts.

The original `docs/sdfix-gate/evidence/ps/flake.ps1` and `flake_rate.py` links
were absent from Git. The gate's actual files were recovered at
`/tmp/sdfix-gate/ps/`, read, copied unchanged, and used for the initial Windows
reproduction. E0 preserves them under [scripts/](scripts/).

## Causal chain, observed before the fix

References below marked BASE refer to the pinned lap-base Git blob, not a
moving line number. Scratch instrumentation changed runtime observations only;
it did not repair the server or client.

1. `tests/test_deck_control_api.py:275-285` sends POST bodies `{` and `null`,
   PATCH `{}`, and BOGUS `{}` to `/api/settings`. `http.client` declares and
   sends exactly the body length. It then reads the complete response body.
   The shared helper at `tests/test_deck_control_api.py:46-57` does the same.
2. BASE `deck/control_api.py:370-373` rejects unsupported method/route pairs
   before the body read at BASE line 379. POST `/api/settings` is unsupported:
   this test's malformed JSON never reaches JSON parsing. PATCH also takes
   that 405 branch. BOGUS enters stdlib method rejection and BASE lines
   356-359 translate 501 to JSON 405.
3. BASE lines 347-354 write the JSON response. The inherited handler finish
   closes `rfile` without consuming those declared bytes. Windows stdlib
   `TCPServer.shutdown_request` already calls `shutdown(SHUT_WR)`, then closes
   immediately. Adding another SHUT_WR would not address the unread body.
4. [trace_close.py](scripts/trace_close.py), run through the rail in the
   archived BASE, observed all four response variants 30 times each:

   | Method | Declared bytes | Read at response and reader close | HTTP status |
   | --- | ---: | ---: | ---: |
   | POST | 1 | 0 | 405 |
   | POST | 4 | 0 | 405 |
   | PATCH | 2 | 0 | 405 |
   | BOGUS | 2 | 0 | 405 |

   Command and summary: [trace-base.log](evidence/trace-base.log). Full ordered
   events: [trace-base.json](evidence/trace-base.json). Instrumentation still
   observed two WinError 10053 errors in its 30 iterations.
5. In trace events 280-289 (iteration 5), the client starts sending the
   two-byte PATCH body; the server writes 405, closes its reader with zero
   body bytes read, calls SHUT_WR and closes the socket, all before the client
   send returns. The client then fails receiving the response. Event 303
   records that exact PATCH subtest's WinError 10053. This is the reset race.
   Successful cases read exactly the response Content-Length (31 or 41 bytes).
   `HTTPConnection.getresponse` may release its socket reference for HTTP/1.0
   before body reading; the HTTPResponse retains its makefile until read.
   That stdlib ownership handoff is not an early test-client close.

No test client repair was warranted. The HEAD/BASE repetition reversal and
actual read-before-close regression above establish the effect of the server
fix. Mac did not reproduce the original reset: `repeat.py BASE 300
 test_malformed_json_and_unsupported_method_are_json green ...` observed
0 errors in 300 runs ([log](evidence/mac-base-300.log)). The new byte-read test
fails against BASE on Mac and passes after, so it does not rely on Windows
scheduler luck to guard the repair.

## History: W1 exposed it

All changes discussed here occurred today, 2026-09-14.

- `git show 62b0dc4 -- tests/test_deck_control_api.py deck/` changes the
  unrelated learning fixture from POSIX pipes to a selectable socket pair.
- `git show 08b426c -- tests/test_deck_control_api.py deck/` moves fcntl,
  termios and tty imports into hardware methods. It does not change the
  HTTP request, response or client helper lines.
- `git blame -L 275,288 14aa218 -- tests/test_deck_control_api.py` attributes
  the failing test and its client to `32368bf`. `git log -- deck/control_api.py`
  attributes the original API to that same commit.
- `git show 08b426c^:deck/control_api.py` versus
  `git show 14aa218:deck/control_api.py`, compared with `cmp`, is byte-identical.
  SHA256 for both is recorded in [history.json](evidence/history.json).

Before W1, eager POSIX imports prevented these Deck tests from importing on
Windows. W1 EXPOSED the pre-existing close defect; it did not introduce the
relevant code. This API belongs to the Deck SENDER. The Windows receiver,
installed tray and Friday's MIDI show path are not implicated by this flake.

## Small fix and retained contract

- `deck/control_api.py:347-362` adds `_Handler.finish`: after an early reply,
  read the remaining declared body before the stdlib closes the reader/socket.
  Drain only a valid positive Content-Length up to the existing 1 MiB limit,
  with the existing 3 second timeout, and no unsupported Transfer-Encoding.
  Invalid framing still receives the same JSON error and closes without an
  unbounded read. The drain is outside the controller lock.
- `deck/control_api.py:396` marks the ordinary JSON read as consumed, including
  malformed JSON, so close does not attempt a second read.
- `tests/test_deck_control_api.py:287` observes bytes read from real HTTP
  sockets before close, exact JSON/status, unchanged settings on disk, and
  no double read. It covers 401, 404, supported and unknown-method 405,
  actual malformed PUT JSON and non-object JSON.
- `tests/test_deck_control_api.py:350` checks exact invalid-framing JSON and
  bounded close for invalid/negative/oversized length and transfer encoding.

No retries, sleeps, swallowed resets, Windows skips or weakened assertions.
The complete existing test methods remain AST-identical. `.venv/bin/python -B /tmp/sdlive-e0/verify_scope.py`
reports 30 unchanged test methods and 24 unchanged product methods except
for the single read marker; only the finish method is added. Its Git scope
check reports zero changes in windows/, protocol/, config/, mac/, the pinned
showready kit or docs/api.md. [Command/output](evidence/scope.log).

### HTTP contract comparison and detector control

`PYTHONHASHSEED=0 TMPDIR=/tmp/sdlive-e0 .venv/bin/python -B
/tmp/sdlive-e0/contract.py <ROOT> <OUTPUT.json>
/tmp/sdlive-e0/contract-tests.json [BASE.json]` runs the original Deck API tests
plus invalid-framing checks and captures real client-read HTTP responses.
BASE uses `/tmp/sdlive-e0/base`; HEAD uses the run root. The initial
unauthorized-route set order differed across Python processes; a fixed hash
seed makes the same test input order reproducible in both arms.

Both arms executed 23 test methods and captured 120 responses, covering
successful replies from all 21 routes plus authentication, routing, unknown
method, validation, persistence, token rotation, learning, and framing errors.
Only fixture paths and volatile heartbeat age are normalized; no status,
error body, route or content type is filtered. The server's dispatch and JSON
serialization functions are unchanged, as the AST comparison also verifies.

- BASE versus HEAD: exact status, JSON and Content-Type equality, exit 0.
  [BASE JSON](evidence/contract-base.json), [HEAD JSON](evidence/contract-head.json).
- Scratch mutant: replace `send_error`'s JSON error text with
  `planted E0 contract fault`. The same comparator detects the BOGUS body
  difference at response 59, exit 1, with all 120 responses still observed.
  [RED](evidence/contract-mutant.log).
- Clean HEAD repeated after the mutant: equality, exit 0.
  [Restored GREEN](evidence/contract-restored.log).

## Full suites and unchanged UI checks

| Host / run | Exact suite line | Result | Exit | Evidence |
| --- | --- | --- | ---: | --- |
| Windows candidate run 1 | Ran 868 tests in 26.165s | OK (skipped=5) | 0 | [runner](evidence/windows-suite1.log), [full stderr](evidence/suite1.stderr.log) |
| Windows candidate run 2, consecutive | Ran 868 tests in 24.764s | OK (skipped=5) | 0 | [runner](evidence/windows-suite2.log), [full stderr](evidence/suite2.stderr.log) |

Windows uses exactly [scripts/suite.ps1](scripts/suite.ps1), copied from the
prior gate, through `scripts/showready/win_rail.sh run sdlive-e0 ... -Label
suite1` and then `suite2`. Each runs from the isolated clone:
`.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"`,
with PYSTRAY_BACKEND=dummy and BROWSER=`C:/Windows/System32/cmd.exe /c rem %s`.
No installer, pip install, MIDI port, tray restart or clone configuration edit.

Mac command: `TMPDIR=/tmp/sdlive-e0 PYSTRAY_BACKEND=dummy BROWSER=/usr/bin/true
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'`:
`Ran 868 tests in 13.726s`, `OK (skipped=2)`, exit 0.
[Full log](evidence/mac-suite.log).

All unchanged standalone Node checks ran as `TMPDIR=/tmp/sdlive-e0 node
 tests/<name>` and exited 0:

| Check | Observed result |
| --- | --- |
| ui_controller_check.cjs | UI controller behavior: PASS |
| ui_controller_macro_check.cjs | 48 disk writes match page Save; 72 incompatible writes refused without byte changes |
| ui_reload_check.cjs | UI reload behavior: PASS |
| ui_sections_check.cjs | UI section behavior: PASS |

Real-browser command: `.venv/bin/python -B /tmp/sdlive-e0/ui_geometry.py
--chromium /Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell
--scratch /tmp/sdlive-e0/geometry-single --single-process`.
The pinned wrapper only allows `/tmp/sdfix-*`; E0's scratch copy changes only
that prefix to the required `/tmp/sdlive-*`, ROOT and the helper import path.
The exact unchanged `tests/ui_controller_geometry.cjs` executes against the
scratch bridge. Default Chromium fails at MachPortRendezvousServer permission;
single-process succeeds: `SUMMARY 1048/1048 PASS`, exit 0.
[Receipts](evidence/geometry-single-receipt.json) and [log](evidence/geometry-single.log).
Both bridges (2418 and 3583) and failed browser 2423 were verified gone.
All UI-enabled bridge runs used dummy tray, no-op browser, dry-run MIDI and
free loopback TCP 17841 / UDP 47841, with config/presets copied to scratch.
No UI change in E0 is owed to the gate for lack of a browser execution.

Suite elapsed times are test-run records, not MIDI timing evidence. E0 ran no
bar 3 timing arm, so no CPU-load-contaminated measurement is offered for bar 3.

## Laptop guard and cleanup

All laptop acts used the pinned `scripts/showready/win_rail.sh` and saved
PowerShell `-File` scripts. Snapshot was the first act; the final compare was
the last. There were no laptop acts after that compare.

- First: `win_rail.sh run sdlive-e0 scripts/showready/win_guard.ps1 -Mode
  snapshot -Out C:\Users\Ben\AppData\Local\Temp\sdwin\sdlive-e0\before.json`:
  exit 0, [snapshot log](evidence/guard-before.log), [observed JSON](evidence/before.json).
- Clone preparation and candidate pull both require empty porcelain,
  `git pull --ff-only`, and the expected full SHA. BASE was archived with
  `git archive` and extracted under LAPTOP WORK, never over the clone.
  Original BASE repetitions finished before HEAD tests were copied to the
  archived BASE for the regression control. BASE server bytes stayed unchanged.
- Every Python launcher and observed worker was checked with Get-Process after
  its run. The short stdlib inspection also prints its own Python PID, which
  the final inventory checks. [Final inventory](evidence/final-inventory.log)
  checks all 17 distinct recorded PIDs absent and Python under clone/work = 0.
  Source SHA256s normalized only for CRLF match the Mac candidate. Both full
  suite runners also observed zero Python processes machine-wide after exit.
- Last: `win_rail.sh run sdlive-e0 scripts/showready/win_guard.ps1 -Mode
  compare -Baseline C:\Users\Ben\AppData\Local\Temp\sdwin\sdlive-e0\before.json
  -Out C:\Users\Ben\AppData\Local\Temp\sdwin\sdlive-e0\after.json`:
  exit 0, `GUARD GREEN: compare; protected state observed; pythonProcesses=0`.
  [Final compare log](evidence/guard-after.log). The after.json remains at that
  laptop path because downloading it after comparison would break the final-act rule.

The guard compared installed metadata, user-config hashes, protected listener
and tray/loopMIDI process identities, and orphan checkout HEAD/status. It found
no differences. No installer or package install was needed. No real MIDI port,
Resolume, installed tray, orphan tracked file, or user preset was touched.
Committed evidence is ASCII/LF with trailing spaces removed; CP1252 Windows logs
are decoded before escaping
non-ASCII characters. Original raw logs remain in /tmp/sdlive-e0 and LAPTOP WORK.

Windows stdlib source was inspected via `run_python.ps1 -Label stdlib-source`:
[saved source/command](evidence/windows-stdlib-source.log). The Python 3.12
`socketserver.py` close paths start at lines 513 and 822; `http/client.py`
getresponse and read start at lines 1386 and 463. That inspection's launcher
285460 and interpreter 289652 were verified absent in the final inventory.

## Next link / remaining show-ready work

E1 must use E0's BASE above as the lap base; it may also record its own entry
SHA. E1, E2 and E3 do not touch the laptop. The final evidence commit does not
alter the product/test bytes validated at candidate 9fc224a.

E0 repairs the unreliable Windows test and establishes consecutive green
Windows suites at this candidate. It does not certify the future live UI.
Bars 1 and 3 at the eventual candidate, Ben's hardware check, and rollback
readiness remain assigned to the gate/master. E0 did not run the A/B MIDI
instrument, measure MIDI timing, or touch the offline Deck. Those results are
UNVERIFIED-BY-EXECUTION in E0, not inferred from suite success.
