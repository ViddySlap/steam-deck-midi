# TODO — Steam Deck MIDI

Authoritative handoff document. Start here when resuming work.

---

## Current target: v0.2.0

All code is implemented and unit tests pass (128 Windows-side tests green). The remaining
steps before cutting the release are below, roughly in order.

---

### Step 1 — End-to-end hardware test (REQUIRED before installer build)

Start the receiver:

```powershell
.venv\Scripts\python -m windows.win_recv --map config\windows_midi_map.json --dry-run --verbose
```

Checklist:
- [ ] Browser opens automatically to `http://127.0.0.1:7723`
- [ ] System tray icon appears
- [ ] Select a button → change its type → click "Save & Apply"
- [ ] Receiver console logs a hot-reload line (config reloaded)
- [ ] Press that button on the Steam Deck → MIDI output in `--dry-run` log matches the new mapping

### Step 2 — Preset system E2E

In the browser UI:
- [ ] Click preset dropdown → confirm "default" is active
- [ ] "Save As" → create a preset named "Test"
- [ ] Switch back to "default", then switch to "Test" → confirm mappings reload
- [ ] Rename "Test" to "Test2" → confirm dropdown updates
- [ ] Delete "Test2" → confirm it falls back to "default"
- [ ] "Factory Reset" → confirm current preset reverts to factory content

### Step 3 — Macro library E2E

- [ ] Open "Macro Library" tab
- [ ] Shipped defaults (5 cards) are visible
- [ ] "+ New macro" opens creation dialog; save a new macro_cc entry
- [ ] Edit an existing macro via the pen icon
- [ ] Delete a macro via the trash icon
- [ ] Select a button in the sidebar, switch to Macro Library tab → compatible macros show "Apply"
- [ ] Click Apply on a compatible macro → mapping form fills in immediately

### Step 4 — Update installer scripts for v0.2.0

The installer needs to bundle new assets that did not exist in v0.1.x.

Files to update:
- `steamdeck-midi-receiver.spec` — add `config/presets/default.json` and
  `config/macro_library.json` as data files so they land under `config/` at install time
- `scripts/windows/build_installer.iss` (or equivalent Inno Setup script) — add the two
  new config files to the `[Files]` section with `Flags: onlyifdoesntexist` so upgrades
  do not clobber user presets or macros
- `config/windows_receiver_settings.example.json` — add `ui_port` and `no_ui` fields

The `config/presets/.active` file should NOT be shipped in the installer; it is created at
first run by `ensure_presets_initialized()`.

### Step 5 — Bump VERSION to 0.2.0

Edit `VERSION` at the repo root: change to `0.2.0`.

### Step 6 — Build and smoke-test installer

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\build_exe.ps1 -RepoRoot (Get-Location).Path
powershell -ExecutionPolicy Bypass -File .\scripts\windows\build_installer.ps1 -RepoRoot (Get-Location).Path
```

Verify:
- [ ] `installer-output\STEAMDECK-MIDI-RECEIVER-Setup-0.2.0.exe` exists
- [ ] Install it (or upgrade over an existing install)
- [ ] Shortcut launches receiver → browser opens → UI loads with default preset
- [ ] Existing user presets and macro library are preserved across upgrade

### Step 7 — Playwright UI tests

Run the E2E browser test suite against the live server:

```powershell
.venv\Scripts\python tests\playwright_ui_test.py
```

All 44 checks should pass (including updated macro library tab tests).

### Step 8 — Git commit, tag, GitHub Release

```powershell
git add -A
git commit -m "feat: v0.2.0 — preset system, macro library, mapping UI overhaul"
git tag v0.2.0
git push && git push --tags
```

Then follow `docs/github-release.md` to publish the GitHub Release with the installer EXE attached.

---

## What was completed — v0.2.0 implementation

| Area | What changed |
|---|---|
| `config/presets/` | New directory: `default.json`, `v1 Default.json`, `.active` |
| `config/macro_library.json` | 5 shipped default macros (click toggle, animated fade, encoder +/−, staged modifier) |
| `windows/config.py` | Per-mapping timing overrides (`fade_duration_seconds` on `macro_cc`; `macro_delay_ms`/`modifier_hold_ms` on `staged_note_macro`); preset helpers (`ensure_presets_initialized`, `get_active_preset_path`, `set_active_preset`) |
| `windows/receiver.py` | Uses per-mapping timing overrides when non-null, falls back to global `macro_settings` |
| `windows/ui_server.py` | Full rewrite: new constructor, preset CRUD API, macro library CRUD API, factory reset writes to active preset |
| `windows/win_recv.py` | Uses preset system at startup and in hot-reload callback; passes `presets_dir` and `macro_library_path` to `MappingUIServer` |
| `windows/static/index.html` | Full rewrite: preset dropdown, Macro Library tab, Save As / Rename / Delete preset modals, Create / Edit / Delete macro modals, Factory Reset modal |
| `tests/test_ui_server.py` | Rewritten: 41 tests across 5 classes covering new API endpoints |
| `tests/playwright_ui_test.py` | Constructor and macro tab checks updated for new API |

---

## Architecture notes for future agents

- **Factory file** (`config/windows_midi_map.json`) is read-only from the app's perspective — it is the source of truth for Factory Reset. Never modify it at runtime.
- **Active preset** is tracked in `config/presets/.active` (just a filename string, e.g. `default.json`).
- **Default preset** is user-editable. It starts as a copy of the factory file but the user can freely modify it.
- **Macro library** is global across all presets — stored in `config/macro_library.json`, not inside any preset file.
- **Macros store only behavior** (gesture, timing, step values) — NOT MIDI targeting (channel, CC, note). Applying a macro merges behavior fields into the existing mapping spec.
- **MappingUIServer constructor**: `MappingUIServer(base_map_path, presets_dir, macro_library_path, actions_yaml_path, reload_event, port=7723)`
- **Start command**: `.venv\Scripts\python -m windows.win_recv --map config\windows_midi_map.json --dry-run --verbose`
- **UI URL**: `http://127.0.0.1:7723`
