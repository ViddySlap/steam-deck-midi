BASE OF LAP 14aa21824843dbe148dc3ac3d0bf58929ef34c3a

# sdlive E1 - live bridge events

Entry HEAD: c406d6e60d268e79334da398168ff07ad94690a2 (E0 complete).
E0's final report places GUARD above BASE; the BASE value above is copied from
its BASE line. This link has made no laptop acts.

Candidate code: 91e1b01708aa6f9de184b7f79de8286f32d42485. It adds bounded live
events, receive and forward-first MIDI hooks, SSE and snapshot routes. All three
Mac A/B presets pass at this code. The final evidence commit adds this report,
receipts, audit scripts and the stalled-TCP regression; product bytes match the
candidate. No Windows candidate suite, live latency, hardware or upgrade claim.

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

## Hook points and attribution

- `windows/win_recv.py:289`: one LiveEvents instance; `:290` wraps the backend
  returned by open_midi_output. Receiver (`:374`) and UI (`:415`) share it.
  The pinned recorder remains underneath the wrapper. Engine output using
  that same backend is observed too. No MIDI backend or config parser changed.
- `windows/receiver.py:260`: accepted axis event publishes its unscaled value
  after parsing/sequence/heartbeat checks, before axis dispatch. `:266` publishes
  accepted buttons after `_allow_event`, before layer-state update and dispatch.
  Unknown mappings still light their received control. Rejected packets do not
  publish input; timed work advanced at the existing beginning of handle_datagram
  can independently produce MIDI even when the incoming packet is rejected.
- `windows/live_events.py:215`: wrapper taps the backend's three bound message
  methods. `:229` forwards the original positional/keyword arguments and return
  value before constructing/publishing the byte event. Tapping backend methods
  also sees panic's internal control_change calls without inventing resets.
  A failed send propagates the backend error and publishes no success event.
  A partial Mido panic publishes only the messages actually sent before failure.
- `windows/receiver.py:551`: `_dispatch_event` has an observer-only ContextVar
  scope. Axis dispatch (`:891`), layer-state updates (`:739`), and releases
  (`:603`) also carry the Action ID. Each scope restores its previous context
  in finally, including failures and nested calls. Handler bodies are unchanged.
- `windows/receiver.py:81`: a fade captures only its originating action as new
  metadata, via a dataclass default factory; the mapping handler is unchanged.
  `advance_fades :386`, relative repeats `:473`, staged triggers `:484`, staged
  note-offs `:489` and staged teardown `:313` apply their saved action context.
  The delayed scheduling, values, loop conditions and call arguments are intact.
- `windows/live_events.py:257`: panic clears action context to null; its actual
  backend CC messages are still individually observed. Startup and otherwise
  unattributable engine sends are null. DryRunMidiOut.panic only prints a marker
  and sends no MIDI messages, so there are no fabricated dry-run panic bytes.

` .venv/bin/python -B docs/sdlive-e1/check_scope.py /tmp/sdlive-e1/scope.json`
asserts all 40 receiver methods remain; 34 complete bodies are AST-identical.
The six changed bodies are initialization, accepted-input publication, and
attribution scopes in release/timed paths. All existing test files, every
scripts/showready file, windows/config.py and windows/midi.py are byte-identical
to entry HEAD. See [scope.json](evidence/scope.json) for the exact path list.
No existing test assertion was changed. No mac/ or Deck code was changed.

## Buffer, loss and coalescing policy

`windows/live_events.py:54` defines shared history capacity 1024, last MIDI
capacity 20, latest input/axis state capacity 512 distinct IDs each and a maximum
of 16 clients. These are asserted by the new tests. Normal controller IDs fit
within the state caps; excess distinct IDs evict the oldest state entry.

Publication tries the writer lock once and drops on contention. It never takes
any reader/client lock. Sequence tickets make contention losses visible as
holes, while history overwrites drop oldest and increment the cumulative
counter. Snapshot state is retained independently of history, so normal buffer
overflow cannot lose a held button or a stationary axis value. A publication
that itself is dropped cannot update state. Readers can retry an overlapping
copy; writers cannot be held up by reader code. Input/MIDI payloads are never
coalesced. Each reader keeps only the latest axis event per ID for each poll,
at most once per 1/30 second. Each stream holds at most one bounded batch.

Snapshot dropped counts all overwritten history and contended publications,
including history overwritten with no clients. A stream emits `dropped` for
holes after its own cursor; an up-to-date client does not get false frame-loss
alerts solely because old history is overwritten. Coalescing does not increment
dropped. Event IDs remain increasing after coalescing and after a loss marker.

## HTTP routes

| Method | Route | Contract | Hook |
| --- | --- | --- | --- |
| GET | /api/live/snapshot | pressed, axes, last 20 midi, seq, dropped, clients; no-store JSON | windows/ui_server.py:353 |
| GET | /api/live/events | SSE id/event/data; optional since or Last-Event-ID; now when absent; invalid cursor 400; client limit/stopping 503 | windows/ui_server.py:359 |
| POST | /api/shutdown | Existing loopback-only 202 and owner teardown; closes streams before HTTP join | windows/ui_server.py:388, :957 |

Full schema and recovery steps are in [docs/api.md](../api.md), `Live events`.
E2 should GET snapshot, apply it, then subscribe with `since=snapshot.seq`.
On `dropped`, refresh snapshot and reconnect from its sequence. `clients` is the
stream registration count; polling snapshot does not open a live client. Explicit
response close removes a registration. Keepalives detect disconnected idle
sockets. The streaming request handler bounds stalled socket writes to 0.5 s.
Other HTTP route socket timeouts are unchanged. Owner stop signals stream close
before waiting for non-daemon request threads, retaining the shutdown 202 reply.

## Executed functional and detector controls

Command for the focused controls:
`TMPDIR=/tmp/sdlive-e1 PYSTRAY_BACKEND=dummy BROWSER=/usr/bin/true
.venv/bin/python -B -m unittest tests.test_live_events -v`.
[Focused log](evidence/focused.log): 14 tests, OK. The final whole suite below
also runs these tests, including their platform-aware process cleanup branch.
Windows execution of the new tests is UNVERIFIED-BY-EXECUTION, owed to EG.

- Exact ordered trace covers note_on, default-velocity note_off, control_change,
  panic, close and port properties. Each byte event follows its actual backend
  call; mixed positional/keyword arguments are preserved. Injected publisher
  exceptions cannot stop the backend. Injected backend failure is still raised.
- A real MidoMidiOut with a fake port fails on its fourth panic send. The exact
  three successfully sent CCs and three published byte events match.
- Receiver tests observe press/release and all delayed fade/repeat/staged sends,
  including raw axis CCs, action restoration, teardown release and null panic.
  Malformed, out-of-order, heartbeat and dedupe-rejected packet controls emit no
  new input events. The snapshot has a nonzero accepted press first.
- The stalled stream control sends 1000 accepted datagrams and compares all
  1000 backend calls, in order, against the plain receiver. History stays at 8;
  dropped is exactly 1992 for its 2000 input/MIDI publications. A watchdog
  requires the worker to finish within 2 s. This is a blocking/byte control,
  not a qualified open-minus-closed latency measurement.
- A deliberately held writer lock makes another publisher return within a
  1 s watchdog. The next successful event exposes the sequence hole and exact
  drop count. The clean no-contention case preserves pressed/released state.
- A fake clock runs 60 frame opportunities; emitted axis values are the latest
  in each batch, at most 30 updates, with at least 20 nonempty observations.
  Snapshot retains the latest axis and press beyond history eviction, then
  shows release, and retains exactly the last 20 MIDI events.
- Flask clients assert id/event/data framing, integer bytes, resume with both
  cursor forms, default cursors, bad-cursor status and client accounting.
- A real UDP serve thread and HTTP server stop after POST with a held-open SSE
  response, within the 3 s shutdown contract, with panic and released UDP.
  A separate real win_recv.main subprocess proves the live wiring through JSON
  snapshots, then exits 0 with the stream still open. Mac PID absence uses
  os.kill(pid, 0); Windows uses Popen.wait's signaled process handle. The subprocess and UI bridge runs
  use disposable config, dummy tray, no-op browser and free non-default ports.

Mutation command:
` .venv/bin/python -B docs/sdlive-e1/check_mutations.py /tmp/sdlive-e1`.
[Results](evidence/mutation-results.json) retain exact selectors and scratch paths.

| Fault in scratch | Required actual failure | Pristine / fault / restored exits |
| --- | --- | --- |
| Publish MIDI to None | Ordered forward/publish trace differs | 0 / 1 / 0 |
| Append all axis values instead of coalescing | Latest-value/one-event batch assertion | 0 / 1 / 0 |
| Omit the streaming socket timeout | Stalled TCP write holds server_close beyond the shutdown bound | 0 / 1 / 0 |
| Omit live_events.close during server stop | Serve/HTTP worker remains alive | 0 / 1 / 0 |

Every RED has an AssertionError; an import error or timeout is not accepted.
Scratch sources are restored byte-for-byte and the same selector reruns GREEN.

The additional TCP control stops reading after headers, shrinks its receive
buffer to 1024 bytes and queues 1024 events with a 4000-character Action ID.
Server stop must finish within 3 s while that client remains unread. Removing
the socket timeout produces the named shutdown assertion failure; restoring it
passes. This is a teardown watchdog, not a MIDI timing measurement.

## Whole Mac suite and unchanged Node checks

`TMPDIR=/tmp/sdlive-e1 PYSTRAY_BACKEND=dummy BROWSER=/usr/bin/true
.venv/bin/python -B -m unittest discover -s tests -p 'test_*.py'`
-> `Ran 882 tests in 14.307s`, `OK (skipped=2)`, exit 0.
[Full log](evidence/mac-suite.log). Duration is suite bookkeeping, not MIDI timing.
The skips are the existing global-color expected remap and missing Mac pwsh
for the Windows guard. No new test skip was introduced.

All standalone checks execute as `TMPDIR=/tmp/sdlive-e1 node tests/<name>`:

| Check | Executed result | Evidence |
| --- | --- | --- |
| ui_reload_check.cjs | PASS | [log](evidence/ui_reload_check.log) |
| ui_sections_check.cjs | PASS | [log](evidence/ui_sections_check.log) |
| ui_controller_check.cjs | Both controller editing and behavior PASS | [log](evidence/ui_controller_check.log) |
| ui_controller_macro_check.cjs | 48 matching disk writes; 72 incompatible writes refused | [log](evidence/ui_controller_macro_check.log) |

Real-browser geometry command:
` .venv/bin/python -B /tmp/sdlive-e1/ui_geometry.py --chromium
/Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell
--scratch /tmp/sdlive-e1/geometry --single-process`.
The scratch wrapper changes the pinned wrapper's scratch prefix, ROOT and import
path only. It runs unchanged tests/ui_controller_geometry.cjs against the scratch
bridge: `SUMMARY 1048/1048 PASS`, exit 0. [Log](evidence/geometry.log),
[receipt](evidence/geometry-receipt.json). The wrapper's initial attempt omitted
untracked live_events.py from its git ls-files copy and the bridge failed import;
after staging the owned module, the same command passed. Failed bridge PID 65351
and successful bridge PID 68730 were both verified gone. No pinned kit changed.

E1 adds backend routes, not the Controller animations/FOLLOW UI. E2 owns that
work and its real-browser proof. No E1 UI behavior is credited only by node:vm.

## Bar 1 at candidate code 91e1b01

Generation command:
` .venv/bin/python -B scripts/showready/deck_script.py --out
/tmp/sdlive-e1/deck-script.json` (exit 0). The script has 732 steps and 47039
packets. SHA256 and parameters: [generator output](evidence/deck-script.log).

These exact commands ran concurrently on the Mac, all exit 0. Defaults are
`--clock script --speed 1`; no accelerated control was used:

```sh
.venv/bin/python -B scripts/showready/ab_run.py --candidate 91e1b01708aa6f9de184b7f79de8286f32d42485 --preset '.showready/fixtures/mac/presets/EDM Show.json' --section windows --script /tmp/sdlive-e1/deck-script.json --scratch /tmp/sdlive-e1/ab-edm --out /tmp/sdlive-e1/ab-edm.json
.venv/bin/python -B scripts/showready/ab_run.py --candidate 91e1b01708aa6f9de184b7f79de8286f32d42485 --preset '.showready/fixtures/mac/presets/PTZ.json' --section windows --script /tmp/sdlive-e1/deck-script.json --scratch /tmp/sdlive-e1/ab-ptz --out /tmp/sdlive-e1/ab-ptz.json
.venv/bin/python -B scripts/showready/ab_run.py --candidate 91e1b01708aa6f9de184b7f79de8286f32d42485 --preset '.showready/fixtures/mac/presets/default.json' --script /tmp/sdlive-e1/deck-script.json --scratch /tmp/sdlive-e1/ab-default --out /tmp/sdlive-e1/ab-default.json
```

The pinned instrument compresses full outputs as .json.gz. Committed artifacts
retain all packets, timestamps, raw recorder bytes, mappings and arm cleanup:
[EDM](evidence/ab-edm.json.gz), [PTZ](evidence/ab-ptz.json.gz),
[default](evidence/ab-default.json.gz). Their stdout is alongside each artifact.

Independent raw check:
` .venv/bin/python -B docs/sdlive-e1/summarize_ab.py /tmp/sdlive-e1
/tmp/sdlive-e1/ab-summary.json` -> exit 0, [summary](evidence/ab-summary.json).
It requires nonempty exact (step, bytes) arrays, complete per-mapping coverage,
exact packet count/hash, clean process teardown and the instrument's paced
input checks. It does not accept a passed log line as byte proof.

| Preset | Arm comparison | Mappings exercised | MIDI messages A / B | Raw bytes |
| --- | --- | --- | --- | --- |
| EDM Show | v0.4.9 / candidate flat | 56 / 56 | 1531 / 1531 | identical |
| EDM Show | v0.4.9 / candidate windows section | 56 / 56 | 1531 / 1531 | identical |
| PTZ | v0.4.9 / candidate flat | 52 / 52 | 1395 / 1395 | identical |
| PTZ | v0.4.9 / candidate windows section | 52 / 52 | 1395 / 1395 | identical |
| default | v0.4.9 / candidate flat | 56 / 56 | 1531 / 1531 | identical |

Every arm received all 47039 packets with the generator's exact stream hash.
All eight arm processes were terminated, waited and proven absent by PID;
individual IDs, exit codes and proof methods are in the summary. Captures are
nonempty on both sides. No differences or unexercised mappings were reported.
The recorder still sees every backend message under the wrapper, including
panic internal sends. SHA256SUMS and the entire showready kit are unchanged.

This pays Mac bar 1 for these fixtures under the pinned simulated sender and
controlled receiver clock. The instrument embeds latency/pacing data, but no
latency statistics from these runs earn bar 3 credit: the required CPU inventory
was unreadable. Engine-dependent output and actual hardware remain outside this
instrument's declared coverage. No Windows-installed fixture was replayed on
Windows by E1; E1 made no laptop acts.

## Handoff / remaining show-ready bars

- E2 consumes the documented live routes for received highlights, raw axis
  positions, exact attributable MIDI row flashes and FOLLOW default OFF.
- E3/EG must run qualified timing with readable empty CPU-load checks before
  and after every arm. E1's guarded microbenchmark is ready, but its no-client
  cost and stalled-minus-closed numbers are UNVERIFIED-BY-EXECUTION here. The
  50 ms / 1000 datagrams difference bound is a loose blocking detector (50 us
  per datagram), chosen well below one 30 Hz UI wait per packet. It does not
  replace the locked no-added-delay show-ready bar or authorize that much delay.
- EG runs the complete Windows suite, full candidate A/B and actual browser
  live interactions. Ben's hardware check and rollback readiness stay with
  EG/master/Ben. The Deck stayed offline; no real MIDI port was opened by E1.
- Product code was committed and pushed before the byte replay. The evidence
  commit keeps those product bytes; no deployment or merge was performed.
  Branch is chain/steamdeck-20260914. Final local/remote identity and clean-tree
  proof are recorded in the terminal envelope after the final push.

All text evidence is ASCII. Existing suite logs with non-ASCII output are
escaped for storage; raw artifacts remain in /tmp/sdlive-e1. The failed initial
geometry launch's cleanup receipt is retained as
[initial receipt](evidence/geometry-initial-failure-receipt.json).
