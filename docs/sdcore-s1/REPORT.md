# sdcore S1 report

S1 implements the sectioned preset loader and live machine-local section setting.
Branch: `chain/steamdeck-20260914`. Baseline: `5d778eb` (v0.4.9 checkout).
S1 checks pass relative to the explicitly accepted macOS baseline; the whole
suite still has the two known libXi import errors assigned to S4.

## Schema and startup

See [preset-sections.md](../preset-sections.md) for the worked two-section example.
A legacy document has no `sections` key and loads unchanged for any bridge,
including a bridge with no section setting. A sectioned document has a non-empty
object of case-sensitive names using the existing filename charset. Every
section has its own mappings, macro settings, optional analog settings, and
optional lenient engine state map. Missing selection or a missing section raises
`ConfigError` listing available sections.

Shared mappings apply to every section, and a section's mapping replaces the
entire shared mapping for the same action.

`shared` holds a `mappings` object; macro/analog/engine settings remain section
local. `select_preset_section()` in windows/config.py returns the effective raw
mapping document for S2 to reuse; `load_midi_map(path, section=None)` validates
that result using the existing parsers. The dead `load_effective_midi_map()` was
removed as explicitly requested. Every Python caller was enumerated with rg.
Existing one-argument calls still validate legacy documents, including the UI's
current flat save candidate.

The bridge now loads `bridge.local.json` beside its base `--map` file at startup.
Explicit `--preset-section` wins over that file without rewriting it.
`BridgeSettings` is the same mutable object used by startup, the HTTP server, and
the reload closure. This makes PUT changes affect the existing receiver loop.
A bad preset switch still leaves the last good MIDI mapping in use; an actual
receiver-loop test observes the MIDI note-on/off calls after a bad scene switch.
No receiver loop behavior or public function was removed except the explicitly
identified dead loader. No runtime dependency was added.

## HTTP and launchers

Added GET and PUT `/api/settings`. GET reports the selected section, listen
address, resolved output/input MIDI port names, UI port, and absolute active map
path. Unavailable input ports are null. PUT accepts only `preset_section`,
validates the current preset, atomically replaces the local file, updates the
running selection, and signals reload. Invalid input, missing sections, and disk
write errors leave the prior selection intact. A successful PUT can supersede
startup argv for this process. Null selection is accepted with legacy presets.

[api.md](../api.md) lists all 20 existing explicit routes and both new routes,
plus Flask's generated static route. A test compares the documented method/path
set to the app's actual URL map. S2 must keep it passing when adding routes.

The Mac launcher reads bridge.local.json and passes the section as one argv
argument, including names containing spaces. All three Windows launchers pass
the new back-filled `preset_section` key. They prefer an existing
bridge.local.json over the launcher bootstrap value, so an HTTP change survives
relaunch instead of being reset to windows. A direct argv flag still wins.

## Migration performed in this run root

| Preset | Mappings in each section | Backup |
| --- | --- | --- |
| config/presets/PTZ.json | 52 | config/presets/PTZ.json.v049.bak |
| config/presets/EDM Show.json | 56 | config/presets/EDM Show.json.v049.bak |
| config/presets/default.json | 56 | Original is in baseline git; scratch copy only |

Each original full document was wrapped as
`{"sections": {"windows": OLD, "macbook": OLD}}`. Both sections were compared to
the parsed original, and both user-file backups were compared byte-for-byte.
Hashes are committed in [evidence.json](evidence.json). Only default.json is
tracked. The other presets, backups, and config/bridge.local.json are ignored.
This machine's bridge.local.json is `{"preset_section": "macbook"}`.
The shared `.active` marker remains `EDM Show.json`, exactly as found.

## Verification

All commands run from the run root unless stated. Scratch and logs are under
`/tmp/sdcore-s1/`; suite runs set TMPDIR there for temporary fixtures.

| Check | Observed result |
| --- | --- |
| Baseline `.venv/bin/python -m unittest discover -s tests -p "test_*.py"` | Ran 648 tests in 1.550s; FAILED (errors=2, skipped=1) |
| Final `.venv/bin/python -m unittest discover -s tests -p "test_*.py"` | Ran 672 tests in 1.886s; FAILED (errors=2, skipped=1) |
| `.venv/bin/python -m unittest tests.test_windows_config tests.test_ui_server tests.test_engine_states tests.test_win_recv_settings tests.test_section_launchers` | 94 tests, OK, in pristine and restored control copies |
| New config/settings tests before implementation | Red: loader and server did not accept section arguments |
| `.venv/bin/python /tmp/sdcore-s1/reversions.py` | All 15 deliberate regressions caught; pristine and restored copies green |
| `bash -n scripts/mac/run_receiver.command` | Exit 0 |
| Mac launcher subprocess with a captured Python argv | Section with spaces is one argument; absent local file omits flag |
| Windows launcher source contract | All three pass the flag; real PowerShell execution not performed |
| Existing test-body AST comparison | All 52 prior bodies in the two edited test modules unchanged |
| Route inventory comparison | 23 method/path pairs match the registered Flask app exactly |
| `git diff --check` | Exit 0 |

The two full-suite errors are unchanged: `test_deck_sender` and
`test_learn_wizard` fail import because deck/xinput_send.py loads libXi on macOS.
They are S4's work. The existing skip remains. There are 24 new tests and no new
full-suite failures or errors.

Reversion controls cover omitted shared mappings, reversed precedence, invalid
names, implicit first-section fallback, rejected legacy documents, strict
engines, ignored local selection, ignored argv, reload losing section selection,
PUT failing to persist or request reload, loss of last-good mappings, incorrect
live ports, and omitted Mac/Windows launcher flags. They modify only a scratch
copy. Tests inspect mappings, MIDI calls, files, HTTP JSON, and captured argv;
the Windows-only launcher check is explicitly a source contract.

## Source boot and gate handoff

The source bridge booted with converted PTZ.json selected through a temporary
active marker, section macbook, dry-run MIDI, engines/pulse/OSC relay disabled,
and browser/tray side effects suppressed. UDP 45123 and HTTP 7723 were available.
A real HTTP GET returned:

```json
{
  "preset_section": "macbook",
  "listen": "0.0.0.0:45123",
  "midi_port": "DECK_IN",
  "feedback_port": null,
  "pulse_port": null,
  "ui_port": 7723,
  "map_path": "/Users/viddyslap/Documents/project-workspaces/steam-deck-midi/config/presets/PTZ.json"
}
```

The child was stopped with SIGINT and reaped; the original marker bytes were
restored. This was a source smoke test, not an installed-app deployment or a
physical MIDI test. There is no sandbox bind debt. Real Windows launcher
execution (pwsh is absent here), browser checks, and physical host/MIDI acceptance
are OWED TO THE GATE. Flask test-client settings and fake-socket receiver-loop
checks passed locally.

## Required next-link work (S2)

S2 owns the section editor and CRUD per its manifest. Until that link lands, the
existing UI still expects a flat document: windows/ui_server.py:175 reads the
whole document and :267 returns it; :283 saves a flat candidate over the active
file; :322 factory reset replaces the whole document; :348 save-as writes engine
states at the top level. Do not edit migrated presets through those legacy
routes before S2 makes them section-aware and preserves sibling sections.

S2 should use `server.bridge_settings.preset_section` as the machine identity,
not a separate captured startup value. The shared active marker and local
identity must remain separate. The two migrated user presets are deliberately
uncommitted but already present in this same run root. Keep their backups.

S3 still owns disk watching and browser refresh. The current reload callback
continues to return exactly `(mappings, macro_settings)`, as before; section
analog settings are parsed but the bridge's pre-existing reload tuple does not
carry them. No change to that contract was included in S1.

## Push command for later links

The executor cannot obtain HTTPS credentials for origin, but its existing SSH
key authenticates as ViddySlap. Use this command-local transport override to push
the same GitHub repository without modifying the remote or credential settings:

```sh
git -c 'url.git@github.com:.insteadOf=https://github.com/' -c 'core.sshCommand=ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10' push -u origin chain/steamdeck-20260914
```

The push succeeds remotely. The sandbox denies Git's attempt to write upstream
tracking into `.git/config`, even though Git prints a tracking-success line.
Explicit remote/branch arguments above work without that local tracking entry.
Verify the published SHA using the same overrides with
`ls-remote --heads origin chain/steamdeck-20260914`; do not infer tracking from
Git's success text. If local upstream tracking is desired, its config write is
OWED TO THE GATE outside this executor. No permission was widened.
