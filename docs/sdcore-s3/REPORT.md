# sdcore S3 report

S3 adds disk-triggered bridge reloads and a browser refresh that preserves
unsaved edits. Branch: `chain/steamdeck-20260914`. Predecessor:
`b91d24879b362e566f9965098273d9faa32919d8` (S2). S1 and S2 launch records were
fetched from the engine and both were done. No design change or runtime
dependency was introduced. No existing Python test or assertion was changed.

## Polling and last-good behavior

`windows/preset_watch.py` uses a daemon thread and stdlib file stats. It snapshots
`presets/*.json`, `presets/.active`, and `bridge.local.json` next to the base map.
Each signature is `(st_mtime_ns, st_size)`; additions, removals, and changed
signatures are changes. Touching a file without changing its bytes requests a
reload. A replacement that preserves both timestamp and size is not detectable
by this deliberately metadata-only watcher. Temporary non-JSON sync files are
ignored. There is one info line naming each detected changed file.

The default poll is 0.5 seconds, configurable with `--preset-poll-interval`.
Intervals must be positive and finite. A detected change starts a 150 ms quiet
period; another observed change resets it. The watcher re-stats at the quiet
boundary instead of adding another complete 0.5 second poll. The receiver's
existing 250 ms loop consumes the event without a loop timing change. Nominal
worst-case detection, debounce, and loop pickup total 0.9 seconds, excluding OS
scheduling and load time. Polling is not a hard real-time deadline.

Debounce coalesces temp/rename writes and short write bursts. It cannot guarantee
that an arbitrary external writer finishes within 150 ms. The loader remains
the validation boundary: a truncated JSON document that outlasts debounce is
rejected by the actual reload callback; the receiver keeps its last good mapping
and version. Completing that write produces another event and applies normally.
Every exception in scanning/signaling is logged and the thread retries. A failed
initial scan is retried without stopping bridge startup. The thread starts in
the common main path immediately after creation of the reload event, including
normal, no-UI, and tray modes, and is stopped/joined when their bridge loop exits.

Watching the local file also required reading it in the reload callback. A
changed signature loads and validates a candidate local section and its preset
before publishing the new live identity. Invalid settings or an absent section
keep the old identity and mappings. An unchanged local file preserves startup
argv precedence. Existing PUT settings updates still supersede argv live and
persist across startup. No preset or machine-local runtime file was edited in
the run root for S3.

## Applied version and HTTP controls

`ActionReceiver.state_version` starts at zero and increments at the end of each
successful `reload_mappings` application. The HTTP server receives a getter for
that same receiver, so watcher activity and successful writes alone cannot
claim application. Rejected reloads do not increment it. The existing reload
callback tuple and all public function names remain intact.

- GET `/api/state-version` returns the JSON integer with `Cache-Control: no-store`.
- POST `/api/reload` takes no body, sets the event, and returns `{"ok":true}`.
  It acknowledges a request; the next successful application increments version.

[api.md](../api.md) documents both endpoints, process-local counter lifetime,
request coalescing, possible duplicate reloads after API writes, and polling.
The registered route inventory now contains 29 method/path pairs including
Flask's generated static route. The HTML/API check recognizes 21 editor paths.

## Browser behavior

The shipped script polls every two seconds. A changed version refreshes through
`loadAll`, retaining the selected section and current action and re-rendering
the editor and Engines tab. If a selected remote section disappeared, a 422
falls back to this bridge's section. Failed fetches do not acknowledge an unseen
version and the next poll retries. Overlapping loads cannot apply an older
response after a newer load has begun.

Dirty mappings and engine drafts defer background refresh. Unapplied mapping
fields and raw JSON are also tracked without removing their existing Apply
step. Global Settings input changes update their draft and mark it dirty.
The persistent non-modal notice reads exactly:
`preset changed on disk - reload to see it`. Its Reload button uses
POST `/api/reload` and the existing unsaved-change confirmation. Cancelling
makes no request. Editing during an in-flight read or after confirming a reload
but before its POST completes retains the later edits and notice.

The final render and dirty/version publication do not yield between steps.
`renderEngines` has no asynchronous operations, so removing its redundant
`await` avoids a gap inside that publication. S2's historical reversion script
has an anchor containing that old `await`; use the equivalent S3 engine-render
control against this revision. S2's behavioral Node script still passes; only
its HTTP/timer test doubles were extended, and none of its assertions changed.

## Verification

Commands run from the run root with fixture scratch under `/tmp/sdcore-s3`.
[evidence.json](evidence.json) contains the final suite result, source-smoke
receipt, mutation results, and file hashes. Reproduction scripts are committed.

| Command/check | Observed result |
| --- | --- |
| Baseline `.venv/bin/python -m unittest discover -s tests -p "test_*.py"` | 691 tests; FAILED (errors=2, skipped=1). |
| Final full suite, same command | 706 tests in 6.459s; FAILED (errors=2, skipped=1), unchanged accepted errors/skip. |
| New watcher tests before implementation | RED: windows.preset_watch did not exist. |
| `.venv/bin/python -m unittest tests.test_preset_watch tests.test_win_recv_settings tests.test_ui_server tests.test_engine_states` | 110 tests, OK in pristine and restored scratch checks. |
| `node tests/ui_reload_check.cjs` | PASS: timer, clean editor/engines, drafts, notice/button, pending edits, removed-section fallback, retry. |
| `node tests/ui_sections_check.cjs` | S2 section/engine/save/CRUD assertions remain green. |
| `.venv/bin/python docs/sdcore-s3/reversions.py` | All 25 deliberate regressions caught; pristine/restored Python and both UI scripts pass. |
| `.venv/bin/python docs/sdcore-s3/smoke.py` | Source HTTP/UDP bridge applied second-process disk edit in 0.717965 seconds; version 1 and note 64 returned by HTTP; child exited 0 and was reaped. |
| Existing Python test comparison | No existing Python test file modified. |
| ASCII and diff checks | Added text is ASCII; git diff --check passes. |

The new Python tests use temporary files and a fake Event for detection and
exercise real `win_recv.main`, its `reload_config_fn`, `serve_forever`,
`ActionReceiver`, and `DryRunMidiOut` together. Only the UDP socket, MIDI opening,
and desktop side effects are substituted in those tests. They assert the note
arguments passed to the real dry-run backend, files, event state, and HTTP JSON.
The source smoke uses real HTTP and UDP binding and a separate editor process.
All smoke presets are scratch fixtures, not the user's active show files.
The quiet-window test uses controlled clock steps over real temporary files to
assert the 150 ms debounce/reset boundary without assuming the OS resumes a
short timed wait promptly. A separate actual daemon-thread test still asserts
file-change detection within one second using the default interval.

The two full-suite errors remain `test_deck_sender` and `test_learn_wizard`,
which cannot import Linux libXi on macOS. S4 owns them. This is baseline-relative
acceptance, not aggregate suite green. Node is used for separate development
checks only; unittest and the production bridge acquire no new dependency.

## Gate and next-link handoff

Native browser layout, real confirmation dialogs, and physical host/MIDI
acceptance are OWED TO THE GATE. The local UI proof executes the shipped script
with DOM/HTTP doubles, not a native browser. Port binding and the requested
source hot-reload smoke succeeded; there is no bind debt. No deployed bridge or
harness engine was restarted. The existing S1 analog-settings limitation remains:
`windows/win_recv.py` returns only mappings and macro settings from reload; S3
does not extend that public tuple.

The lane log is outside this executor's writable roots. This committed report
is the durable next-link baton; progress and completion go to the engine.
Only S3 is implemented. Ben still owns merging this branch.

## Delivery

Push with S1's command-local SSH override, without `-u`, and compare the remote
branch SHA to local HEAD. The final envelope records the commit and equality
check after push. No remote configuration, credential, or upstream tracking
write is needed. The worktree must be empty before the terminal envelope.
