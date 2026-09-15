E2 ENTRY HEAD 95d3da0a740911e0677a549b75bee648a198b2cc

# sdlive E2 - live Controller view

Implemented on chain/steamdeck-20260914. Mac only; no laptop acts, no Deck,
no real MIDI ports, no deployment, and no show-ready/latency claim. The E1 launch
record was fetched into /tmp/sdlive-e2/predecessor.json and its committed report
and the sdview V2/V3/gate reports were read before implementation.

## Delivered behavior and lifecycle

- `windows/static/controller/controller_live.js` owns the live consumer.
  ControllerView supplies the actual map, labels, current card, card opening
  callback and a read-only unsaved-edit predicate. List/editor functions remain
  intact. All control/Action-ID relationships come from the existing map groups.
- Visible Controller in Mappings fetches GET /api/live/snapshot (no-store),
  applies pressed/axis state, then opens GET /api/live/events?since=<snapshot seq>.
  Snapshot history never replays MIDI flashes or follows an old press.
- Selecting List, switching application tabs, hiding the browser tab, or
  pagehide closes the EventSource, aborts a pending snapshot, and cancels the
  retry, expiry and animation-frame callbacks. Epoch/source guards ignore late
  callbacks, including a late snapshot response after hiding the view.
- Stream errors close native EventSource auto-reconnect and show offline.
  Snapshot plus stream retry with 250 ms exponential backoff capped at 8 s;
  a successful open resets it. A dropped event immediately fetches a fresh
  snapshot and reconnects from that cursor. The live indicator means an open
  SSE connection; it does not assert a connected Deck or MIDI device.
- Received input down lights the physical shape and label, including unmapped
  controls. Any remaining held Action ID keeps its shared control lit. Tags
  show tap, hold and L2 in explicit group order, independent of JSON key order.
- MIDI events flash only their attributable Action ID row on the open card,
  including tap, hold, layer 2 and analog rows. A same-frame Follow target also
  receives its matching flash. Null or another card's attribution flashes
  nothing. Flashes last 150 ms and retrigger from the latest matching event.
- Follow is off by default and remembered with try/catch localStorage under
  steamdeck.controllerFollow. A down opens its control without stealing focus.
  Unapplied row/Advanced drafts and applied mappings awaiting Save on the open
  card pause Follow and show `follow paused: unsaved edit`. Blocked presses
  are discarded; after saving, the next new press can follow.

The existing E1 routes cover every live affordance. No backend route, publisher
semantics, mapping semantics, receiver, engine or MIDI code changed. docs/api.md
updates the existing live-route rows and names exactly List/Controller and
Follow under `View-only exemptions`; both are browser preferences.

## Render policy and ranges

Events update bounded sets/maps of known actions and one pending Follow target.
They do not render or enqueue per-event rendering work. One requestAnimationFrame
paints the latest values, at most once per frame. Live paints never reconstruct
editor rows. One expiry timer requests a later frame for the nearest flash/pad
expiration; idle displays do not run an animation loop. Closed views have no
live client or pending render work.

`controller_map.json` now owns `axis_ranges`, served unchanged by the existing
GET /api/controller-map route. Each analog Action ID has integer min/max/rest.
The following values are verified by `node tests/ui_controller_check.cjs` and
`.venv/bin/python -B -m unittest tests.test_controller_map`; source derivation is
HidrawAxisReader._STATIC_AXIS_MAP, _parse_report and gyro integration in
`deck/xinput_send.py`, read only:

| Axes | min | max | rest |
| --- | ---: | ---: | ---: |
| L_STICK_X_AXIS | -32886 | 32649 | 0 |
| L_STICK_Y_AXIS | -33202 | 32333 | 0 |
| R_STICK_X_AXIS | -33048 | 32487 | 0 |
| R_STICK_Y_AXIS | -32432 | 33103 | 0 |
| L/R_TRIGGER_PRESSURE | 0 | 65535 | 0 |
| L/R_PAD_X/Y_POS | -32768 | 32767 | 0 |
| GYRO_PITCH/YAW/ROLL | -32767 | 32767 | 0 |

The sender already subtracts the measured stick rest offsets. Received zero is
centered; each sign normalizes by its own bound and clamps. Positive Y draws up.
The stick/pad dot travels 30 SVG units from its map anchor. The trigger bar is
64 SVG units times pressure/max. Gyro indicators independently move across
center. These drawing dimensions are distinct from the centralized wire ranges.
L3/R3 captions moved above their centered dots to keep them readable.

Trackpad dots appear only after a position event and begin an 80 ms opacity fade
after 300 ms without one. Either axis refreshes the age. Snapshot has no axis
age, so snapshot-only positions stay hidden. Sticks, triggers and gyro retain
last received values. Physical rest can only be represented by samples the
sender supplies: its deadzone suppression can omit samples near rest. Hardware
rest/release fidelity is UNVERIFIED-BY-EXECUTION and remains for the gate/Ben;
E2 does not fabricate samples or change the sender.

## Executed checks

All commands below ran from /Users/viddyslap/Documents/project-workspaces/steam-deck-midi.
Scratch is exclusively /tmp/sdlive-e2. Check logs below are committed copies;
original raw logs and scratch trees remain there. Text logs are ASCII-escaped.

| Command | Result | Evidence |
| --- | --- | --- |
| `TMPDIR=/tmp/sdlive-e2 PYSTRAY_BACKEND=dummy BROWSER=/usr/bin/true .venv/bin/python -B -m unittest discover -s tests -p 'test_*.py'` | 883 tests in 13.782 s, OK (skipped=2), exit 0. No new skip. Duration is suite bookkeeping, not MIDI timing. | [suite](evidence/mac-suite-complete.log) |
| `TMPDIR=/tmp/sdlive-e2 node tests/ui_controller_check.cjs` | Existing editing/behavior assertions plus live checks pass, exit 0. | [controller](evidence/ui_controller_check.log) |
| `TMPDIR=/tmp/sdlive-e2 node tests/ui_controller_macro_check.cjs` | 48 disk writes match page Save; 72 incompatible writes refused without byte changes, exit 0. | [macro](evidence/ui_controller_macro_check.log) |
| `TMPDIR=/tmp/sdlive-e2 node tests/ui_reload_check.cjs` | Unchanged check passes, exit 0. | [reload](evidence/ui_reload_check.log) |
| `TMPDIR=/tmp/sdlive-e2 node tests/ui_sections_check.cjs` | Unchanged check passes, exit 0. | [sections](evidence/ui_sections_check.log) |
| `TMPDIR=/tmp/sdlive-e2 .venv/bin/python -B docs/sdlive-e2/check_mutations.py /tmp/sdlive-e2/mutations-complete` | Pristine GREEN; seven named faults RED (exit 1), each byte-restored GREEN (exit 0). | [results](evidence/mutation-results.json) |
| `.venv/bin/python -B docs/sdlive-e2/collect_evidence.py` | Protected source unchanged; all 130 prior JS assertion lines and 21 prior map-test assertion lines retained; seven started bridge PIDs independently absent. | [scope](evidence/scope.json) |
| `TMPDIR=/tmp/sdlive-e2 .venv/bin/python -B -m unittest tests.test_controller_map` | Four map tests pass, exit 0. | terminal check |
| `shasum -a 256 -c scripts/showready/SHA256SUMS` | All ten pinned files match, exit 0. | terminal check |
| `git diff --check` | Exit 0. | terminal check |

The controller VM now supplies a driven EventSource, abortable/deferred snapshot,
virtual clock, timeouts and requestAnimationFrame. The live fixture reproduces
Flask's sorted JSON group keys. Assertions observe the actual rendered DOM and
requests: shape/label down/up, two simultaneous IDs, hold/L2 tags, computed axis
positions and clamps, trigger widths, pad expiry/refresh, each gyro axis, matching
rows only, retrigger/expiry, no row replacement, Follow default/persistence/denied
storage, blocked drafts through Apply/Save, Advanced protection, loss resync,
old/new sequences, backoff/reset, cancellation, hidden-page races and client
creation. A burst of 500 axis events produces exactly one frame callback and one
shape paint, uses the last value, and leaves zero pending frames. These counts
come from `node tests/ui_controller_check.cjs`, not production counters.

### Mutation controls

`check_mutations.py` changes scratch static copies only. Every needle matches
exactly once, every RED must contain AssertionError and the named assertion,
and each restored source must equal its pristine bytes before rerunning.

| Removed behavior | Assertion that actually failed |
| --- | --- |
| Explicit group display order | group tags use tap/hold/layer order |
| Shape highlight | input down lights the physical shape |
| Stick X normalization | axis moves stick dot to computed X |
| MIDI row flash | MIDI flashes matching row only |
| Follow unsaved-edit guard | follow cannot switch cards over an unsaved inline edit |
| Pending-frame guard | 500 axis events schedule one animation frame |
| EventSource.close | dropped stream closes before resync |

### Real Chromium and real loopback receiver

Exact final browser command (exit 0):

```sh
.venv/bin/python -B docs/sdlive-e2/check_browser.py --chromium /Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell --scratch /tmp/sdlive-e2/browser-complete --ui-port 17842 --listen-port 47842 --single-process
```

This reuses the pinned scratch/fixture/port/teardown rail without changing its
bytes. The only adaptations are the E2 scratch prefix and browser detector path.
The browser starts with empty storage and uses domcontentloaded plus actual UI
readiness. check_browser.cjs sends valid action/axis JSON through a real loopback
UDP socket to the isolated receiver; the browser consumes real SSE. No route
response or DOM implementation is replaced. Dry-run MIDI and disabled engines,
pulse and OSC relay ensure no real MIDI input or output is opened. The UI bridge
uses PYSTRAY_BACKEND=dummy and BROWSER=/usr/bin/true.

[Browser results](evidence/browser-results.json) observe default Controller,
Follow off, press/release plus shared held IDs, label highlight, attributable
BTN_A row flash and expiry, actual stick/trigger/gyro geometry, visible pad fade,
Follow opening B, preserving B's actual typed note during X input, visible pause
note, fresh state on reopening, remembered Follow after reload, and no browser
JavaScript errors. Snapshot clients transitions are observed at 0 and 1 for
List/Controller, application-tab switches, reload and page close; no empty
observation is credited. [Receipt](evidence/browser-complete-receipt.json) records
bridge PID 8216 reaped and absent. [Default PNG](evidence/default-controller.png)
and [paused Follow PNG](evidence/live-follow-paused.png) were opened and inspected.
The test never saves the typed field; its config is disposable in any case.

Exact final geometry command (exit 0):

```sh
.venv/bin/python -B docs/sdlive-e2/check_geometry.py --chromium /Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell --scratch /tmp/sdlive-e2/geometry-complete --single-process
```

The pinned `tests/ui_controller_geometry.cjs` remains byte-identical. Its direct
initial run failed at page.goto(networkidle), before any geometry observations,
because the default Controller SSE connection intentionally remains open.
[Initial detector](evidence/geometry-detector.log), [cleanup receipt](evidence/geometry-receipt.json).
No geometry credit is claimed for that attempt. The E2 geometry wrapper preloads
only the supported saved List preference on navigation. The unchanged detector
then explicitly opens Controller and its real stream before every measurement.
No geometry assertion, HTTP response or rendered node is modified by the preload.
This pays geometry in the saved-List entry scenario; the separate live-browser
check above pays default Controller entry.

Final result: 1048/1048 assertions pass at all four pinned sizes with closed/open
cards and every control drill-in. [Geometry JSON](evidence/geometry.json),
[log](evidence/geometry-complete-detector.log), [receipt](evidence/geometry-complete-receipt.json).
Bridge PID 11377 was reaped and absent. Source pins, the A/B instrument and its
checksums were not edited or repinned.

### Disclosed initial failures

- Enabling virtual time exposed the fake DOM's missing Element.remove used by
  existing toast expiry. Added the normal removal operation; no old assertion
  changed. [Initial VM output](evidence/controller-initial.log).
- The first real-browser multi-ID check waited for `tap L2`, but the server's
  sorted group keys produced `L2 tap`. Fixed the live group order and proved its
  removal RED. [First browser log](evidence/browser-detector.log),
  [cleanup receipt](evidence/browser-receipt.json). A first attempt to sort every
  legacy fake response tripped its pre-existing raw-JSON insertion-order
  assertion; sorted responses are now scoped to the new live fixture and every
  old assertion remains intact. [Fixture setup RED](evidence/group-order-red.log).
- The first browser-wrapper adaptation rejected a non-unique scratch-prefix
  replacement before starting any process; narrowed the replacement needles.
  This was a wrapper setup error, not a product result.

## OWED TO THE GATE

- Full Windows suite, the pinned Windows A/B MIDI instrument, rollback checks
  and Ben's hardware check remain UNVERIFIED-BY-EXECUTION in E2. No laptop act
  was authorized for this link and none was made.
- E3/EG own bar 3: paced open/closed MIDI timing with readable, empty CPU-load
  checks immediately before/after each arm. E2 ran no latency/timing arms and
  claims no bar 3 credit. Virtual-clock expiry checks and browser correctness
  waits are functional checks, not MIDI delay measurements.
- Real-browser proofs still owed: forced stream loss/backoff and hide-during-
  snapshot races; background browser-tab/page-cache lifecycle; 500-event render
  count in native requestAnimationFrame; all long-press/layer-2/analog MIDI row
  flashes and retrigger timing; applied-unsaved/Advanced Follow protection and
  storage-denial fallback. Those cases pass only in node:vm here. Repeat the
  full live presentation on Windows with the simulated sender and the gate's
  required PNGs. Confirm real physical axis ranges/rest with Ben when available.
- For E3/EG browser scripts, await DOM/UI readiness, not networkidle with an open
  EventSource. Use GET /api/live/snapshot.clients to prove open/closed conditions.
  The committed geometry wrapper keeps the old pinned assertions intact.

The scoped commit and SSH-override push are followed by exact ls-remote/HEAD
comparison and empty porcelain verification. Their final object identity and
results are supplied in the terminal envelope, after this report is committed.
