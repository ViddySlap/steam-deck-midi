# sdcore S2 report

S2 adds the section editor and section CRUD API on
`chain/steamdeck-20260914`, following S1 commit
`0f86e921ea5e3ddf21418b19c95e5898f23e4b49`. S1's launch was fetched and was done.
No design change, runtime dependency, preset migration, or deployed bridge
restart is part of S2. Existing ignored runtime files were not edited.

## Routes

Added:

| Method | Route | Result |
| --- | --- | --- |
| GET | `/api/presets/<name>/sections` | List sections without changing the active marker. |
| POST | `/api/presets/sections/add` | Add empty mappings or copy a complete existing section. |
| POST | `/api/presets/sections/rename` | Rename a section; persist local identity when renaming this machine's section. |
| POST | `/api/presets/sections/delete` | Delete a section; refuse this machine's section and the last remaining section. |

Extended:

- `GET /api/mappings?section=name` defaults to the bridge's current local
  selection. It returns effective mappings/settings, section and bridge names,
  the active preset, all section names, the unmerged document, and shared defaults.
- `POST /api/save` accepts `{section, document}`. It replaces one section's
  document after loader validation. Sibling and shared bytes are unchanged,
  including whitespace, JSON escapes, and CRLF line endings. Atomic replacement
  prevents partial JSON files; failures leave the old file and reload flag intact.
- `POST /api/reset` accepts `{section}` and restores factory defaults in that
  section only. The default is this machine's section.
- `POST /api/presets/save-as` copies all sections and captures live engine states
  only into this machine's section. Preset rename now also signals reload.

All successful section writes signal reload. [api.md](../api.md) documents the
complete request bodies, responses, legacy semantics, and refusal status codes.
Its inventory matches all 27 method/path pairs, including Flask's static route.

## UI

The existing header now has a section selector, with this machine preselected
and labelled `this machine`, plus Add, Rename, and Delete section controls.
The status line keeps the bridge's identity and active preset visible while the
editor selects another section. Header controls wrap on smaller windows using
the existing styles. New text is ASCII.

Section and preset switches use the same unsaved-change confirmation. Section
CRUD, preset deletion, and Save As also guard drafts. The selected section's
mappings, macro/analog settings, and engine states are submitted to `/api/save`.
Unchanged shared mappings remain inherited instead of becoming local overrides.

`loadAll` fetches engine metadata and renders the selected section's states on
every load. `renderEngines` uses that snapshot plus unsaved engine changes, so
switching tabs retains the draft. Remote section toggles are saved through
`/api/save` and never toggle this bridge's live engines. This machine's loaded
engines retain the existing live toggle endpoint. Remote engine types absent
from this bridge are still shown from the document; absent remote overrides
show Default. OSC resync is a local runtime operation and is disabled while
editing another section.

Legacy documents still read/save as universal flat documents. Adding named
sections preserves the old complete document under this machine's name. If no
local name exists, the first add names that document and persists the name.
Renaming this machine's section persists its new identity; a local write failure
restores the original preset. Section renames affect only the active preset;
other presets and other machines' local identities keep their existing names.

## Verification

Commands run from the run root. Python fixture scratch uses
`TMPDIR=/tmp/sdcore-s2`. [evidence.json](evidence.json) contains source hashes and
all mutation outcomes; [reversions.py](reversions.py) reproduces the controls.

| Check | Observed result |
| --- | --- |
| Baseline `.venv/bin/python -m unittest discover -s tests -p "test_*.py"` | 672 tests; FAILED (errors=2, skipped=1). |
| Final `.venv/bin/python -m unittest discover -s tests -p "test_*.py"` | 691 tests in 1.864s; FAILED (errors=2, skipped=1). |
| `.venv/bin/python -m unittest tests.test_ui_server tests.test_engine_states` | 88 tests, OK, including pristine and restored scratch controls. |
| Initial new section API tests against S1 | 13 tests; red with 18 subtest failures and 3 errors. |
| `.venv/bin/python -m unittest tests.test_ui_server.HtmlApiBarTests` | OK; output below. |
| `node tests/ui_sections_check.cjs` | PASS: section selection, cancelled dirty switch, engines refresh, remote save isolation, shared inheritance, and CRUD calls. |
| `.venv/bin/python docs/sdcore-s2/reversions.py` | All 25 deliberate regressions caught; pristine and restored Python/UI checks green. |
| Existing UI-server test-body AST comparison against S1 | All 51 bodies unchanged; 19 unittest cases added. |
| `git diff --check` | Exit 0. |

The API-bar detector is permanently in `tests/test_ui_server.py`. It parses the
served HTML, checks balanced tags and unique IDs, extracts quoted `/api/` paths
including JS templates, and checks each against Flask's real URL map. Output:

```text
HTML API bar: 19 paths registered; HTML parsed; ids unique
```

The deliberate missing-route and malformed-HTML controls both fail that test.
The other controls remove section selection/metadata, flatten saves, reserialize
siblings, omit validation/atomic writes/reload signals, leak local engines into
remote sections, break copying and deletion guards, omit identity writes and
rollback, write Save As engines at the top level, activate a preset while merely
listing sections, or regress the actual editor script's section/engine flows.

The whole suite has no new failures or errors. Its only two errors remain
`test_deck_sender` and `test_learn_wizard`, which cannot import Linux libXi on
macOS. S4 owns them. The existing skip remains. This is baseline-relative
acceptance, not an aggregate green suite.

## Gate and next-link handoff

Real-browser layout, native confirmation dialogs, screenshots, and physical
host/MIDI acceptance are OWED TO THE GATE. Screenshots are not expected from S2.
Flask test-client and Node DOM/HTTP-double checks are local evidence only. No
port bind or browser run was claimed, and no running bridge was restarted.

S3 should read these integration points before adding file watching:

- `windows/static/index.html:864`: `loadAll(section = selectedSection)` reloads
  the selected section; explicit `null` selects the bridge's current identity.
  It returns success/failure. It replaces drafts and clears dirty on success,
  so an unsolicited watcher refresh must defer while dirty, as S3's item requires.
- `windows/static/index.html:1925`: `renderEngines` renders the selected snapshot
  and draft. Refresh data via `loadAll`, not by re-fetching local engine flags
  and replacing remote state in this renderer.
- `windows/ui_server.py:215`: `_write_preset` validates every section in a
  temporary `.preset-*.tmp` beside the destination, then atomically replaces the
  JSON file. Watch completed JSON/active-marker changes, not temporary files.
- Machine identity remains `server.bridge_settings.preset_section`; editor
  selection is only request/UI state. Shared inheritance uses `document` and
  `shared_mappings` in the GET response.

The S1 analog-settings reload-tuple limitation remains S1's documented follow-up;
S2 does not change the receiver loop. Existing preset path/name hardening outside
the new section routes is also outside this item (load/rename/delete at
`windows/ui_server.py:500`, `:545`, and `:567`).

The lane log is outside this executor's writable roots. This committed report
is the durable next-link baton; the engine progress/completion report supplies
the lane's live notification.

## Delivery

Use S1's command-local SSH transport override to push this branch, then compare
`git rev-parse HEAD` with `ls-remote --heads origin chain/steamdeck-20260914`.
The terminal envelope records the resulting commit and remote verification.
The known sandbox refusal to write upstream tracking in `.git/config` does not
prevent publishing the branch; use explicit remote/branch arguments. No remote
configuration or credentials were changed.
