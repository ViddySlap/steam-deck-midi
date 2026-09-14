# Bridge HTTP API

The bridge serves HTTP on `http://127.0.0.1:7723` by default. JSON write requests
use `Content-Type: application/json`. This inventory is taken from
`windows/ui_server.py`: 22 explicit method/path registrations after S1, plus
Flask's static-file route. Flask also supplies HEAD for GET and automatic OPTIONS.
Later links must extend this inventory with every new UI or control action.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Serve the mapping editor HTML. |
| GET | `/static/<path:filename>` | Serve the editor's static assets (Flask-generated route). |
| GET | `/api/settings` | Return live preset_section, listen, midi_port, feedback_port, pulse_port, ui_port, and map_path. |
| PUT | `/api/settings` | Persist preset_section in bridge.local.json and request a live reload. |
| GET | `/api/mappings` | Read the active preset JSON. |
| GET | `/api/actions` | List action IDs from actions.yaml. |
| POST | `/api/conflicts` | Check supplied mappings for unintentional MIDI CC conflicts. |
| POST | `/api/save` | Validate and save supplied mappings and settings to the active preset, then reload. |
| POST | `/api/reset` | Replace the active preset with the base map's factory defaults and reload. |
| GET | `/api/presets` | List preset names and the shared active selection. |
| POST | `/api/presets/load` | Change the shared active preset marker and request reload. |
| POST | `/api/presets/save-as` | Copy the active preset under a new name, capture live engine states, and activate it. |
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
