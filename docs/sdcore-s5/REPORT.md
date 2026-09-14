# sdcore S5 report

S5 adds a stdlib-only Deck control API and CLI. Branch:
`chain/steamdeck-20260914`. Predecessor S4 is
`e360646bac14404bfdd9e5a587c9a038ed63de20`; its launch record and committed
transport report were read before implementation. This link implements only S5.
Ben owns merge and installed-machine rollout.

## Delivered behavior

`deck/control_api.py` owns a serialized sender controller and a daemon-thread
HTTP server. Default address is `127.0.0.1:7724`; `--api-bind` and `--api-port`
override the listener without rewriting settings. Off-loopback binds require a
shared `api_token` from Deck machine-local settings and authenticate every route
with `X-Deck-Token`. Token rotation is live; token values are omitted from GET
settings. Invalid requests return JSON errors with 4xx status.

All requested status, target CRUD/replace/activation, sender start/stop/restart,
bindings read/reload, and settings routes are implemented. `deck/deckctl.py`
provides status, targets, activate, start, stop, and restart commands. Both
`python3 -m deck.launch_send` and `python3 -m deck.control_api` start the same
service. The menu starts HTTP before its first input prompt and remains usable
while sending. It shares the controller with HTTP, rejects stale edits, and
provides stop/restart controls. `/api/shutdown` replies, stops capture, closes
HTTP, and quits either launcher, including one blocked at a TTY input prompt.

The lane-wide parity requirement also covers `deck.launch_learn`. S5 therefore
adds actions and learn endpoints for full learning, single-action re-learning,
candidate inspection, confirmation, skip, and cancellation. The new
`deck/control_learn.py` reuses existing action loading, XI2 capture and atomic
binding writing, while the original TTY wizard/public functions remain intact.
Drafts are only written when complete. Single-action saves preserve siblings;
skip cancels a single-action session. Sender and learning capture are mutually
exclusive inside this controller. An independently launched legacy learn wizard
is a separate process; operators must not run two capture tools simultaneously.

See [deck-api.md](../deck-api.md) for commands, request/response bodies, travel
router bind/token instructions, and telemetry semantics. [api.md](../api.md)
lists all 21 Deck method/path pairs separately from the bridge inventory.

## Sender and settings contracts

S4's transport and wire protocol are unchanged. `run_sender` now accepts an
optional stop Event, telemetry callback, loaded bindings snapshot and terminal
management flag, while retaining all old arguments. Its select loop checks the
Event with the existing 1/60-second timeout and checks again immediately after
select. Stop closes selector, listener, HID reader and UDP socket. Listener
cleanup now also covers failures while opening later resources. API workers do
not change TTY echo while the main menu is reading input.

`seq` is the last attempted event sequence; heartbeat age measures the last
heartbeat attempt, not delivery or bridge feedback. Unknown hashes remain null.
Start is asynchronous: status reports actual worker liveness, errors and exit
code. Stop waits up to 3 seconds and refuses an overlapping restart if an OS
operation delays exit. Real targets and running targets are separately visible.
Target or sender-identity changes restart a running worker; removing its entire
selection stops it. API-only configuration changes do not restart sending.
Bind/port settings take effect at process relaunch.

The settings loader defaults missing API fields for old installed files, and
existing TTY helpers retain the new fields. API writes use the existing atomic
`write_runtime_settings`, validating before file replacement and publishing
memory afterwards. A failed disk write preserves the prior settings and worker.
A stop timeout after successful persistence reports an error with the new
settings retained; poll status before retrying start. Old files with no active
set still work through single-target menu selection without being rewritten.
HTTP clients explicitly activate names before start.

No runtime dependency, requirements, PyInstaller spec, installer, protocol,
show preset, or ignored machine-local configuration was changed. All original
public functions/classes remain available.

## Verification

All verification runs from the run root. Temporary settings, copied sources and
logs live under `/tmp/sdcore-s5`. Reproduce with the committed smoke and mutation
scripts. [evidence.json](evidence.json) records counts, hashes and commands.

| Check | Result |
| --- | --- |
| Baseline full unittest suite | 769 tests, OK (skipped=1). S4 removed both historical Xi import errors. |
| New HTTP tests before implementation | RED: `deck.control_api` absent. |
| Final full unittest suite | 795 tests in 10.065s, OK (skipped=1); 26 new tests. |
| New HTTP/controller tests | Real `http.client` against ephemeral in-process servers, with a fake sender worker. Every registered route exercised. |
| Actual sender integration | HTTP starts/stops real sender loop with hardware substituted; real UDP receiver observes action/axis/heartbeat seq 1/2/3, profile fields, and status telemetry. |
| System Python smoke | Both standalone and menu launchers serve HTTP, accept CLI activation, persist the file, and exit 0 through HTTP shutdown; child processes reaped. |
| Copy-only reversion controls | 35 deliberate regressions caught; pristine/restored 35-test Deck controls pass. |
| Existing public API/assertion audit | No public names removed; two existing tests adapted as described below. |
| ASCII and whitespace | Authored docs, strings and additions are ASCII; git diff --check passes. |

The new HTTP tests inspect response JSON, persisted files and the atomic
replacement boundary, worker Events, target order, binding snapshots, and real
socket bytes. Learning tests use an OS pipe with a real selector and a substituted
XI2 listener: injected key events must become visible candidates and then the
correct on-disk bindings. They cover duplicate refusal, partial-draft retention,
full save, single save, skip and cancel. The full suite's one prior skip remains.

Two existing test adaptations preserve their original contracts:

- `test_api_inventory_matches_registered_method_paths` compares only the bridge
  portion of docs/api.md to Flask. A new test independently compares the Deck
  portion to the HTTP server's complete route set.
- `test_toggle_save_start_and_relaunch_use_all_saved_hosts` compares each original
  sender argument across launches. Per-launch Events and bound telemetry
  callbacks necessarily differ. The menu fixture adds quit after its scripted
  actions because the menu now stays available, and uses an ephemeral API port.
  Its original target, file, marker and legacy-compatibility assertions remain.

During control development, removing Event.set made an all-tests mutant exceed
its process deadline. The final Event control uses a deterministic assertion
that the Event is set before joining the worker. No timeout is counted as green
or as a final mutation pass. The initial activation-order control survived
because the test's input was already sorted; the test now asserts an unsorted
order on disk and at the running sender. No behavior was weakened to pass.

## Gate handoff and delivery

Native Steam Deck XI2/HID operation, physical-control capture in both TTY and HTTP
learn workflows, travel-router LAN/token reachability, and physical multi-bridge
MIDI acceptance are OWED TO THE GATE. Local HTTP/UDP binding worked; there is no
sandbox port-bind debt. The source smoke is not an installed-app deployment.
Neither the running bridge nor the harness engine was restarted.

The lane log is outside this executor's writable roots and was not written.
This committed report is the durable next-link baton. No file under the vault,
private paths, or harness state root was changed by this link.

Push with S1's command-local SSH transport overrides, with no upstream config
write. Before the terminal envelope, require `ls-remote --heads origin
chain/steamdeck-20260914` under the same overrides to equal `git rev-parse HEAD`
and require empty `git status --porcelain`. The envelope records the published
SHA. Only the harness advancer starts the next link.
