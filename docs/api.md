# Bridge HTTP API

The bridge serves HTTP on `http://127.0.0.1:7723` by default. JSON write requests
use `Content-Type: application/json`. This inventory is taken from
`windows/ui_server.py`, plus Flask's static-file route. Flask also supplies HEAD for GET and automatic OPTIONS.
Later links must extend this inventory with every new UI or control action.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Serve the mapping editor HTML. |
| GET | `/static/<path:filename>` | Serve the editor's static assets (Flask-generated route). |
| GET | `/api/live/events` | Stream received highlights, stick/pad dots, trigger/gyro values and attributable MIDI row flashes as bounded, lossy SSE; optional since sequence. |
| GET | `/api/live/snapshot` | Initialize/resynchronize controller pressed actions and axes; read recent MIDI, sequence, drops and live client count. |
| GET | `/api/state-version` | Return an integer revision for applied reloads and successful per-action disk writes. |
| POST | `/api/reload` | Request an immediate reload of the active preset and changed local settings. |
| POST | `/api/shutdown` | Loopback only: request graceful bridge Quit; return 202 {"stopping": true}, including repeated calls while stopping. |
| GET | `/api/settings` | Return live preset_section, listen, midi_port, feedback_port, pulse_port, ui_port, and map_path. |
| PUT | `/api/settings` | Persist preset_section in bridge.local.json and request a live reload. |
| GET | `/api/mappings` | Read selected section mappings, settings, and section/preset metadata; optional ?section=name defaults to this machine. |
| GET | `/api/controller-map` | Read the owned physical control map JSON. |
| GET | `/api/controller-map/<control_id>` | Read grouped Action IDs, current mappings and ownership; optional section. |
| PUT | `/api/mappings/<action_id>` | Validate and atomically store one mapping; optional section and force=1 for conflicts. |
| DELETE | `/api/mappings/<action_id>` | Clear one section mapping idempotently; optional section and force=1 for conflicts. |
| POST | `/api/macros/<macro_id>/apply` | Apply a compatible library macro to {action_id, section}; optional force=1. |
| GET | `/api/actions` | List action IDs from actions.yaml. |
| POST | `/api/conflicts` | Check supplied mappings for unintentional MIDI CC conflicts. |
| POST | `/api/save` | Validate and save {section, document} into one active-preset section, preserving sibling bytes, then reload. Legacy flat bodies still work. |
| POST | `/api/reset` | Restore the selected section from the base map; {section} defaults to this machine. Preserve siblings and reload. |
| GET | `/api/presets` | List preset names and the shared active selection. |
| GET | `/api/presets/<name>/sections` | List the sections of a named preset without activating it. |
| POST | `/api/presets/sections/add` | Add a section to the active preset; optional copy_from clones one section. |
| POST | `/api/presets/sections/rename` | Rename one active-preset section; persist local identity too if it is this machine's section. |
| POST | `/api/presets/sections/delete` | Delete one active-preset section; refuse this machine's section and the last section. |
| POST | `/api/presets/load` | Change the shared active preset marker and request reload. |
| POST | `/api/presets/save-as` | Copy the complete active preset under a new name, capture this machine's live engine states only in its section, and activate it. |
| POST | `/api/presets/rename` | Rename a preset and update the active marker if needed; default is protected. |
| POST | `/api/presets/delete` | Delete a preset, falling back to default if active; default is protected. |
| GET | `/api/macros` | List reusable macro-library entries. |
| POST | `/api/macros` | Validate and create a macro-library entry. |
| PUT | `/api/macros/<macro_id>` | Validate and replace a macro-library entry by ID. |
| DELETE | `/api/macros/<macro_id>` | Delete a macro-library entry by ID. |
| GET | `/api/engines` | List loaded engine status. |
| POST | `/api/engines/<type_name>/active` | Toggle a loaded engine live; persist on preset save. |
| POST | `/api/engines/osc-sync/resync` | Resynchronize OSC targets and return their count. |
| POST | `/api/engines/gyro-feedback/resync` | Invert gyro-feedback polarity and refresh its outputs. |
| POST | `/api/engines/refresh` | Invoke every loaded engine's refresh hook and return results. |

`GET /api/settings` reports resolved live MIDI port names; unavailable/disabled
input ports are `null`. `map_path` is the absolute, resolved active preset path,
so it follows scene changes. `listen` is a host:port string and `ui_port` is an
integer. The PUT response has the same fields as GET after the change. Only
`preset_section` is writable in S1; see [section semantics](preset-sections.md).

`POST /api/shutdown` uses the same stop request as both Windows tray Quit modes.
It releases held MIDI controls before stopping engines, closes MIDI ports and
UDP, and closes HTTP after in-flight replies finish. The process then exits 0.
Non-loopback remote addresses receive 403, regardless of the bind address or
forwarded headers. A standalone UI server with no bridge shutdown callback
returns 503. No request body is required.

## Section editing

`GET /api/mappings?section=windows` returns the selected effective document's
`mappings`, `macro_settings`, `analog_settings`, and `engines` (when present), plus:

- `section`: the returned selection; defaults to the current live bridge setting.
- `bridge_section`: the machine-local selection, independent of editor selection.
- `sections`: all named sections, in file order; empty for a legacy flat preset.
- `preset`: the active preset filename, including `.json`.
- `legacy`: true for the universal v0.4.9 format.
- `document`: the stored section document, before merging shared mappings.
- `shared_mappings`: the shared mapping defaults, for editors preserving inheritance.

`POST /api/save` accepts `{"section":"windows","document":{"mappings":{},
"engines":{"osc_sync":false}}}`. The document replaces only that section's
mappings, optional macro/analog settings, and engine overrides. Validation uses
the preset loader before atomic replacement; siblings and shared data retain
literal bytes, including whitespace. Missing sections return 422. Invalid JSON
bodies or missing mappings return 400; invalid mapping values return 422; failed
writes return 500. Failures do not request reload. The older flat save body
still defaults to this machine and captures its live engine states, as before.
An explicit document never captures another section's live states.

`GET /api/presets/<name>/sections` accepts a display name or `.json` filename
(URL-encode spaces), returning section metadata without changing `.active`.
An invalid filename returns 400, a missing file 404, and an invalid preset 422.

The three section writes accept, respectively:

- Add: `{"name":"grandma","copy_from":"windows"}`; omit `copy_from` for empty
  mappings. Copies retain the source's entire section document.
- Rename: `{"old":"windows","new":"grandma"}`. Renaming this machine's own
  section also persists its new local identity. If local persistence fails,
  the preset is restored and no reload is requested. Other machines' local
  identities are not changed; their agents must use PUT /api/settings as needed.
  Only the active preset is renamed; names in other presets remain as stored.
- Delete: `{"name":"grandma"}`. This machine's own section and the last remaining
  section are protected, including when local identity is absent from the file.

Names follow S1's case-sensitive ASCII charset. Malformed bodies/names return
400, missing sections/copy sources 404, duplicate names or protected deletions
409, invalid preset content 422, and filesystem failures 500. Successful writes
return `ok` with section metadata and set the bridge's reload event.

Legacy presets remain flat when read or saved and apply to any machine name.
Adding a section migrates the old complete document under this machine's name.
If no local name is set, the first add names the existing document and persists
that name locally; it preserves the legacy mappings. Subsequent adds create
empty sections or copies. Legacy rename/delete require adding a named section
first (422).

The editor keeps mapping and remote engine changes as drafts until `/api/save`.
A loaded engine's checkbox in this machine's section also uses the existing live
`/api/engines/<type_name>/active` endpoint. Remote section checkboxes never toggle
this bridge's engines; absent remote overrides display Default. Runtime resync
controls operate on this bridge and are disabled while editing another section.

## Controller view

Mappings opens in Controller view by default; the Controller/List choice is
stored per browser. Labels show mapped/total Action IDs in the selected section.
Selecting a label, its arrow or the drawn shape opens grouped editable rows;
Open in list selects that Action ID in the existing editor. Escape closes the
card. These navigation actions do not write configuration. Agents use the two
controller GET routes in the table above and GET `/api/mappings` for the same
saved information; the browser card also reflects its current unsaved draft.
The map's `label_anchor` places each callout, `anchor` places the control, and
`scene_view_box` frames both. The original artwork, CSS and view script are
served by the existing static-file route. No new routes are introduced here.

Each row's Edit button expands the shared List forms with unique field IDs.
Type changes use the same defaults; Apply fields and Clear update the page draft.
Apply macro... lists GET `/api/macros` with the same compatibility and target-field
merge as the List library. Mappings and Advanced are tabs inside the card.
Advanced edits one object keyed by this control's Action IDs. Apply parses and
checks every key/value before committing any: foreign IDs, arrays, non-object
mappings and unsupported types are refused. Missing IDs and null clear the draft.
Copy copies the current text, including unapplied edits. Server parser validation
still runs on Save. Shared fallback/ownership rules below remain unchanged.

| Controller operation | HTTP equivalent (registered route table above) |
| --- | --- |
| Inspect rows, switch control, Mappings/Advanced, Copy saved JSON | GET `/api/controller-map/<control_id>` with section; project grouped rows to an object keyed by action_id |
| Set type and edit fields (all seven types), Apply fields/JSON | PUT `/api/mappings/<action_id>` for one mapping; POST `/api/save` for the full section document |
| Clear or omit an Action ID | DELETE `/api/mappings/<action_id>`; omit it from the document sent to POST `/api/save` |
| Apply library macro | GET `/api/macros`, POST `/api/macros/<macro_id>/apply` |
| Save, conflict check, cancel/force | POST `/api/conflicts`, then existing POST `/api/save` only after confirmation; cancel writes nothing |
| Select section, discard drafts/reload | GET `/api/mappings?section=name`; POST `/api/reload` requests receiver reload |
| Factory reset | POST `/api/reset` with section |

Browser Apply operations remain drafts until the existing Save button is used;
per-action API writes persist immediately. Draft typing, tabs and clipboard are
local operations, not separate server state. HTTP clients retain their draft
locally and use the listed read/write endpoints. Save uses the existing conflict
modal; its open-control conflicting rows are marked until cancel or force.
Unapplied row/Advanced edits protect against polling reloads, section switches
and explicit reload without discard confirmation. Other row commits and saves
retain them. Accepted loads/reset discard the old section's cached editors.

`windows/static/controller/controller_map.json` is the only owned physical
control-to-Action-ID relation. `schema_version: 1` defines an ordered `controls`
list with stable IDs, labels, kinds, anchors and grouped Action IDs. `view_box`
is `[x, y, width, height]` for the original SVG. Anchor coordinates belong only
to this file; V2 may adjust them while drawing the artwork. Control `notes`
explain placement choices. GET `/api/controller-map` reads this file directly.

GET `/api/controller-map/<control_id>?section=windows` keeps the control fields
and replaces each group list with ordered `{action_id, mapping, source}` rows.
`mapping` is the raw effective spec, preserving parser defaults as omissions,
or null if unmapped. `source` is `section`, `shared`, `flat`, or null. Section
metadata matches `/api/mappings`. Unknown controls return 404; invalid or absent
sections return 422. Omitted section uses the bridge selection. Flat presets
still apply universally, including with a safe named section.

PUT `/api/mappings/<action_id>?section=windows` takes one mapping spec as its
entire JSON body. DELETE on the same path removes the section's override; doing
so twice returns 200 both times when there are no conflicts. An inherited shared
mapping remains shared, and clearing an override reveals the shared default,
just like the list editor's Clear then Save. Neither operation changes shared
or sibling-section bytes, section settings, or machine-local identity. PUT of
an unchanged inherited spec retains its shared ownership.

POST `/api/macros/<macro_id>/apply` takes `{"action_id":"BTN_A","section":"windows"}`.
The section may be omitted or null with the same meaning as `/api/save`.
Unmapped actions accept any library macro type; a mapped action must match its
type (409 otherwise). Existing MIDI target fields survive. An unmapped action
uses the page's defaults. Macro CC applies gesture and optional fade; relative
CC applies step and interval; staged notes apply channels, refresh actions and
optional delays. Absent optional overrides are removed, exactly as in the page.

All three writes validate every section through `load_midi_map` before the
same `_write_preset` atomic replacement used by `/api/save`. A bad mapping or
malformed JSON returns 400 with the parser's error and unchanged preset bytes.
Unknown action or macro IDs return 404; invalid section selection returns 422;
filesystem errors return 500. Conflicts in the resulting effective section
return 409 with `conflicts` and no write. `?force=1` accepts those conflicts,
including on DELETE or macro apply. It never bypasses parser validation.
Successful writes return `{ok, action_id, section, mapping, effective_mapping,
saved_to}`: `mapping` is the stored section spec (null after clear or for an
unchanged inherited spec), while `effective_mapping` includes shared fallback.
They request reload and immediately advance the polled state version.

## Reload and disk synchronization

`GET /api/state-version` returns a JSON integer (initially `0`), with
`Cache-Control: no-store`. It includes successful per-action disk writes and increases after every successful `reload_mappings`
application, including reloads requested by `/api/save`, `/api/reload`, or the
disk watcher. A rejected preset or settings file leaves the version and last
good mappings unchanged. A per-action disk write advances the UI version before
receiver application; that increment alone is not proof of a live reload. The counter belongs to one process and resets on
restart; clients should compare for inequality, not just increases.

`POST /api/reload` takes no body and returns `200 {"ok":true}` after setting the
reload event. This acknowledges the request; it does not promise application.
The receiver picks it up within its normal 250 ms poll, and clients can poll the
version to observe success. Multiple requests may coalesce. An API write can
also be observed by the watcher, producing an additional applied reload/version.

Disk polling defaults to 0.5 seconds (`--preset-poll-interval SECONDS`) with a
150 ms quiet period before requesting reload. It watches preset JSON files,
`.active`, and `bridge.local.json`. A changed local file updates live identity
only after its selected preset validates; an unchanged local file preserves
startup argv precedence. Missing/legacy local settings remain supported.

The UI checks the version every 2 seconds. Clean editors refresh their selected
section, current action, and Engines tab. Dirty editors show a persistent,
non-modal notice and Reload button; Reload uses `/api/reload` and the existing
unsaved-change confirmation. Background reads also check for edits made while
HTTP requests were in flight before replacing any draft.

## Live events

### View-only exemptions

Exactly these two persistent controller preferences are exempt from a bridge
action endpoint. Neither writes a preset or changes MIDI behavior:

| Preference | Browser behavior |
| --- | --- |
| List/Controller choice | `steamdeck.mappingView` in localStorage; default Controller. List closes the live client. |
| Follow toggle | `steamdeck.controllerFollow` in localStorage; default off. When on, received input down opens its physical control's card without stealing keyboard focus. |

Storage reads/writes use try/catch; denied storage keeps both choices usable for
the current page. Follow pauses while the open card has unapplied row/Advanced
text or applied mapping changes awaiting Save. It displays
`follow paused: unsaved edit`. After Apply and Save, the next press can follow;
blocked presses are never replayed later. Navigation and edit operations retain
the HTTP equivalents in the Controller view table above.

### Controller consumer

While the Controller sub-view and Mappings tab are visible, the browser fetches
the snapshot with no-store, applies its pressed/axis state, then opens one
EventSource at `since=snapshot.seq`. Hiding the view, switching application or
browser tabs, or leaving the page closes it, aborts an in-flight snapshot, and
cancels render/retry/expiry work. A late callback cannot open a hidden client.
Errors show `offline`, clear stale display state, close native auto-reconnect,
and retry snapshot plus stream after 250 ms, doubling to 8 s; opening resets
the backoff. A `dropped` event closes and resynchronizes immediately. `live`
means the SSE connection is open, not that a Deck or MIDI device is connected.

Input down/up highlights the shape and label while any Action ID in that
control's groups remains down. Tags identify tap, hold, L2 or analog groups.
Axis values use only `axis_ranges` in the owned map, also available from GET
`/api/controller-map`: min/max/rest in wire units for every analog Action ID.
Signed values normalize on either side of zero; positive Y draws upward.
Stick bounds include the sender's already-subtracted rest offsets (wire rest
is zero); pads use signed 16-bit bounds, triggers unsigned 16-bit bounds, and
gyro uses the sender's integrated/clamped bounds. Values clamp to these ranges.
Stick/pad travel is 30 SVG units; trigger fill is value/max across 64 SVG units.
Gyro pitch/yaw/roll have independent centered indicators.

Pad dots fade after 300 ms without a received position event. Snapshot positions
have no age, so they do not imply a current pad touch. Other axes retain their
last received value, with zero centered; the UI does not invent missing samples.
Snapshot MIDI history is not replayed. Only a streamed MIDI event attributed
to the open card (or its same-frame Follow target) flashes that Action ID row
for 150 ms, extended by another matching event. Null attribution flashes nothing.

Event callbacks only replace bounded latest state, including one pending Follow
target. requestAnimationFrame draws at most once per frame; a burst leaves no
render queue. One expiry timer requests a frame when a pad/flash expires, with
no continuous idle animation. Live paints preserve the existing editor nodes.

### Wire contract

`GET /api/live/snapshot` returns `{pressed: [ActionID], axes: {ActionID: value},
midi: [event], seq: integer, dropped: integer, clients: integer}`. MIDI retains
the last 20 events, independent of stream history. Pressed/axis state survives
history overflow. Values are the original wire integers, without scaling.

`GET /api/live/events?since=123` returns `text/event-stream`. Omit `since` to
start from now; `Last-Event-ID` is accepted when the query is absent. Invalid
or negative cursors return 400; a cursor beyond the current bridge sequence
starts from now (for example after a bridge restart). Each frame has `id:`,
`event:`, and JSON `data:` lines followed by a blank line. Comment keepalives
carry no event. All data events include `kind`, increasing `seq`, and
`timestamp` (monotonic seconds, meaningful only within this bridge process):

- `input`: `action`, `state` (`down` or `up`), after sequence and input guard
  acceptance. Unmapped accepted controls are still visible. Heartbeats,
  malformed packets, out-of-order packets and guard-rejected buttons emit none.
- `axis`: `action`, `value`; the latest value per axis between reader polls.
  Each client reads at most once per 1/30 second. Input and MIDI never coalesce.
- `midi`: `bytes` (status/data integers), `action` (Action ID or null). The
  backend is called first with unchanged arguments. Releases, relative repeats,
  fades and staged notes retain their cause. Startup, panic and otherwise
  unattributable output uses null. Panic observes actual backend CC calls;
  dry-run panic prints a marker and emits no byte events.
- `dropped`: `count` (history events this client missed), `dropped` (cumulative
  overwritten history plus contended-publication count). Its ID is immediately before the next retained
  event, so reconnects can resume normally. Axis coalescing is not a drop.

The shared journal retains at most 1024 events. History overwrites increment
snapshot `dropped` even without clients; an up-to-date client only receives a
`dropped` frame if its own cursor fell behind. Snapshots retain up to 512 input
IDs and 512 axis IDs, evicting the oldest distinct ID on overflow (the current
controller uses fewer). At most 16 streams can connect; excess connections or
connections while stopping receive 503. Slow clients hold at most one bounded
batch. Publishers try a writer lock once and drop on contention; readers never hold
that lock. No publisher waits for a reader, serializes JSON or writes a socket.
Sequence/time and bounded latest-state bookkeeping run even with zero clients.

Call snapshot first, then connect with `since=snapshot.seq` to cover the gap.
After `dropped`, refresh snapshot and reconnect from its sequence to recover
pressed/axis state. `clients` counts registered event streams, not snapshot
requests. Closing a response removes it; disconnected idle sockets are detected
by keepalives. Bridge shutdown ends streams, clears clients and bounds stalled
stream socket writes to 0.5 seconds so HTTP teardown can finish.


## Deck sender

The independent Deck service uses stdlib HTTP on `http://127.0.0.1:7724`.
These routes are served by both `deck.launch_send` and `deck.control_api`, not
by the bridge above. See [deck-api.md](deck-api.md) for request bodies, token
setup, CLI commands, persistence, telemetry meaning, and learn workflow.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/shutdown` | Stop capture, close the API, and quit its launcher after replying. |
| GET | `/api/status` | Read sender liveness, destinations, sequence, heartbeat age, profile, bindings path, and device. |
| GET | `/api/targets` | Read saved receiver presets and active target names. |
| POST | `/api/targets` | Atomically replace receiver presets, retaining surviving active names. |
| POST | `/api/targets/active` | Select and persist ordered target names; apply to the running sender. |
| POST | `/api/targets/add` | Add a named host and optional port. |
| POST | `/api/targets/delete` | Delete a target and remove it from the active set. |
| POST | `/api/targets/rename` | Rename a target and follow its active selection. |
| POST | `/api/sender/start` | Start the sender worker; poll status for hardware startup outcome. |
| POST | `/api/sender/stop` | Set the sender stop Event and wait for capture/socket cleanup. |
| POST | `/api/sender/restart` | Stop the old worker before starting another with current settings. |
| GET | `/api/bindings` | Return the currently loaded bindings JSON snapshot. |
| POST | `/api/bindings/reload` | Validate and load bindings from disk, restarting a running sender. |
| GET | `/api/settings` | Read machine-local settings, redacting the shared token. |
| PUT | `/api/settings` | Atomically persist settings; token rotation is live, bind/port wait for relaunch. |
| GET | `/api/actions` | List the learn wizard's available action IDs. |
| GET | `/api/learn` | Inspect the current action, captured candidate, draft bindings and save state. |
| POST | `/api/learn/start` | Start full learning or single-action re-learning. |
| POST | `/api/learn/confirm` | Confirm the captured token; atomically save when learning finishes. |
| POST | `/api/learn/skip` | Skip a full-learn action or cancel single-action re-learning. |
| POST | `/api/learn/cancel` | Cancel learning and discard the unsaved draft. |

## Mac host (127.0.0.1:7724)

The Swift host serves these routes on the Mac, separately from the Deck
sender's API. All responses are JSON. See [mac-host.md](mac-host.md) for
settings defaults, lifecycle states, guard ownership and executable wiring.

| Method | Path | Body | Response |
| --- | --- | --- | --- |
| GET | `/host/status` | None | State fields, owned PIDs, health, active UI URL. |
| POST | `/host/bridge/start` | None or `{}` | Status after requesting start; poll until healthy. |
| POST | `/host/bridge/stop` | None or `{}` | Status after owned child exit. |
| POST | `/host/bridge/restart` | None or `{}` | Status after old child exits and new start is requested. |
| GET | `/host/log?lines=N` | None | `{"lines":[...],"path":".../bridge.log"}`; default 200, allowed 0-2000. |
| GET | `/host/login-item` | None | `{"status":"..."}` using one of the four login-item states. |
| PUT | `/host/login-item` | `{"enabled":true}` or `false` | Updated login-item status. |
| GET | `/host/settings` | None | Settings object including defaults and unknown keys. |
| PUT | `/host/settings` | Partial settings object | Persisted settings including defaults and unknown keys. |
| POST | `/host/window/open` | None or `{}` | `{"ok":true}` after calling the window handler. |
| POST | `/host/quit` | None or `{}` | 202 `{"quitting":true}`; after reply, stop bridge and quit host. |

Only a bind to `127.0.0.1` is allowed. The server supports HTTP/1.1 with
Content-Length bodies capped at 64 KB. Bad JSON/values return 400, unknown
paths 404, and wrong methods 405; errors have `{"error":"..."}`. Start and
restart report lifecycle status, not a promise of immediate bridge health.
Settings changes affecting the child apply on its next start/restart; changing
the control port requires a host relaunch. Quit replies before stopping the
bridge and terminating the host. The seven status-menu entries are generated
from a model whose routes are checked against the same route table.
