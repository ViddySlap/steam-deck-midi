# Bridge HTTP API

The bridge serves HTTP on `http://127.0.0.1:7723` by default. JSON write requests
use `Content-Type: application/json`. This inventory is taken from
`windows/ui_server.py`: 28 explicit method/path registrations after S3, plus
Flask's static-file route. Flask also supplies HEAD for GET and automatic OPTIONS.
Later links must extend this inventory with every new UI or control action.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Serve the mapping editor HTML. |
| GET | `/static/<path:filename>` | Serve the editor's static assets (Flask-generated route). |
| GET | `/api/state-version` | Return the integer count of successfully applied reloads in this bridge process. |
| POST | `/api/reload` | Request an immediate reload of the active preset and changed local settings. |
| GET | `/api/settings` | Return live preset_section, listen, midi_port, feedback_port, pulse_port, ui_port, and map_path. |
| PUT | `/api/settings` | Persist preset_section in bridge.local.json and request a live reload. |
| GET | `/api/mappings` | Read selected section mappings, settings, and section/preset metadata; optional ?section=name defaults to this machine. |
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

## Reload and disk synchronization

`GET /api/state-version` returns a JSON integer (initially `0`), with
`Cache-Control: no-store`. It increases after every successful `reload_mappings`
application, including reloads requested by `/api/save`, `/api/reload`, or the
disk watcher. A rejected preset or settings file leaves the version and last
good mappings unchanged. The counter belongs to one process and resets on
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
