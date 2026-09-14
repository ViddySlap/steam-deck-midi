# Preset sections

A preset without `sections` keeps the v0.4.9 format and applies to every bridge,
including a bridge with no section setting. No installed legacy config needs to
be recreated.

A sectioned preset contains a non-empty `sections` object. Its keys are names
made of ASCII letters, digits, spaces, underscores, and hyphens, using the same
charset as preset filenames. Names are case-sensitive. Each value has the old
document shape: required `mappings`, optional `macro_settings`, `analog_settings`,
and `engines`. The existing validation and default settings still apply;
malformed `engines` values are ignored, and only non-empty string-to-boolean
engine entries are retained.

`load_midi_map(path, section=None)` selects the named section. A missing selection
or an absent name raises `ConfigError` listing the available sections. On a
failed hot reload, the receiver continues using its last good mappings.

The optional `shared` object holds `mappings` only; macro, analog, and engine
settings belong to each section.

Shared mappings apply to every section, and a section's mapping replaces the
entire shared mapping for the same action.

For example, both bridges receive BTN_B as note 40, while BTN_A is note 36 on
Windows and CC 72 on the MacBook:

```json
{
  "shared": {
    "mappings": {
      "BTN_A": {"type": "note", "channel": 0, "note": 60},
      "BTN_B": {"type": "note", "channel": 0, "note": 40}
    }
  },
  "sections": {
    "windows": {
      "mappings": {
        "BTN_A": {"type": "note", "channel": 0, "note": 36}
      },
      "macro_settings": {"update_hz": 30},
      "engines": {"osc_sync": true}
    },
    "macbook": {
      "mappings": {
        "BTN_A": {"type": "cc", "channel": 1, "cc": 72}
      },
      "macro_settings": {"update_hz": 30},
      "analog_settings": {"deadzone": 1000},
      "engines": {"osc_sync": false}
    }
  }
}
```

The Deck sends the same action IDs to each host; hosts select their own mappings.
`config/presets/.active` selects the scene for every machine and remains separate
from the machine-local identity.

## Machine-local selection

The bridge reads `bridge.local.json` beside its `--map` base file at startup
(normally `config/bridge.local.json`). The file is gitignored. Use
`config/bridge.example.json` as a template:

```json
{"preset_section": "macbook"}
```

`--preset-section NAME` overrides the file for that process without changing the
file. If both are absent, selection is `null`, except for the macOS first-run
rule below.
UTF-8 with or without a Windows BOM is accepted.

```sh
.venv/bin/python -m windows.win_recv --map config/windows_midi_map.json --preset-section macbook
```

`GET /api/settings` returns the running selection and ports. `PUT /api/settings`
accepts only `{"preset_section": "name"}`, validates the current preset for that
name, atomically writes the local file, changes the running selection, and sets
the receiver's reload event. It does not restart the bridge or change the shared
active marker. A successful HTTP write supersedes the startup argv selection for
the current process. `null` clears selection only while the active preset is
legacy. Invalid bodies return 400, unavailable sections return 422, and a failed
write returns 500 without changing the running selection. See [API](api.md).

The Mac launcher initializes an absent local file to `macbook`, reads it, and
passes the section as one argv value.
All three Windows launchers back-fill `preset_section` in an existing settings
file from the launcher example (initially `windows`) and pass `--preset-section`.
An existing `bridge.local.json` takes priority over that launcher bootstrap value so an HTTP change survives the
next launch. A manually supplied argv flag still wins over the bridge file.

## Upgrading and first run

The tracked `config/presets/default.json` retains the flat v0.4.9 format and
original bytes. A fresh clone or git-pulled install with no `.active` marker and
no `bridge.local.json` boots with that preset on every platform. Existing user
presets and local settings do not need to be recreated.

The Mac launcher atomically creates `config/bridge.local.json` with
`{"preset_section": "macbook"}` only when the file is absent. Direct Python
bridge startup (including a Mac host that passes no section flag) also creates
that file on macOS when the active preset has a valid `macbook` section and no
local file or explicit selection exists. It logs the created filename. It does
not create a file for a flat preset. Other platforms, or a sectioned preset
without `macbook`, keep the error listing available sections. Existing files,
including an explicit null or unavailable selection, are never overwritten by
first-run initialization.

### Windows launcher execution (2026-09-14)

Executed on Windows PowerShell 5.1 in the isolated laptop clone, with each
unchanged launcher pointed at temporary settings and an argv-only executable:

| Launcher | Existing file, no section key | Existing `grandma` | No settings file |
| --- | --- | --- | --- |
| `scripts/windows/start_receiver.ps1` | Writes and passes `windows`; exit 0 | Bytes unchanged; passes `grandma`; exit 0 | Exit 1; file stays absent; no executable call |
| `scripts/windows/start_installed_receiver.ps1` | Writes and passes `windows`; exit 0 | Bytes unchanged; passes `grandma`; exit 0 | Exit 1; file stays absent; no executable call |
| `scripts/windows/start_installed_receiver_v2.ps1` | Writes and passes `windows`; exit 0 | Bytes unchanged; passes `grandma`; exit 0 | Exit 1; file stays absent; no executable call |

The absent-file failure occurs at line 35 in each launcher: strict mode rejects
`.PSObject.Properties.Name` on the empty object created at line 30. This is a
recorded first-run defect; W2's missing-key back-fill arm succeeds and needed no
product fix. No receiver or real MIDI port was opened. See
[W2 executed evidence](sdwin-w2/REPORT.md) for settings hashes, captured argv,
process checks, and the Windows and Mac suite results. R1's historical
UNVERIFIED-BY-EXECUTION debt for the existing-file back-fill is now discharged.

## Initial migration

S1 initially wrapped default.json, PTZ.json, and EDM Show.json in identical
`windows` and `macbook` sections. R1 restored the tracked default to flat format
for upgrades; the two untracked user presets remain sectioned. Ben can customize the
MacBook mappings later. The two user presets have byte-for-byte backups named
`PTZ.json.v049.bak` and `EDM Show.json.v049.bak` beside them; both presets and
backups remain untracked. Only default.json is committed. This machine's local
selection is `macbook`.
