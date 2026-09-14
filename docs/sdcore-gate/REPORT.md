# sdcore gate (SG) report

Gate for lap `sdcore` (run `sdcore-q001`), executor claude-rc on the Mac, unsandboxed,
2026-09-14 12:55-13:12 MDT. Branch `chain/steamdeck-20260914`, gated HEAD
`32368bf628c3f948f162bfd0ff7de2514fd34f09` (S5). All five link launches (S1..S5)
were fetched from the engine: every one is `done` with envelope status `complete`,
and every docs/sdcore-s*/REPORT.md was read before gating.

No product code was changed by this gate. The only commit is this directory
(report, screenshots, evidence captures, gate scripts). The run root's `config/`
tree was hashed before the bridge boot and after all steps: all 36 files are
byte-identical (the show preset, `.active` marker and `bridge.local.json` were
edited during the live tests and restored from byte copies).

## Verdict summary

| Step | Result |
| --- | --- |
| 1. Suite at HEAD | GREEN: `Ran 795 tests in 6.531s` / `OK (skipped=1)`, exit 0. No errors. |
| 1. Mutation spot-checks | 6 of 6 mutants RED, all restored GREEN (one per link, plus a second for S3). |
| 2. Real bridge boot, disk reload, section switch | PASS, including real MIDI on the IAC bus. |
| 2. Clean SIGINT shutdown | FAILS, but PRE-EXISTING (identical at v0.4.9). Finding F2. |
| 3. UI in a real browser | PASS in headless Chromium (playwright-core 1.58.2), 9 screenshots. |
| 4. API bar | One gap: the bridge has no shutdown/quit endpoint (Finding F3). All three API-bar detectors bite. |
| 5. Fan-out on the wire, Deck control API | PASS: identical bytes and seq to both listeners; all 21 Deck routes exercised; token refusal proven. |
| 6. Commits, push, exclusions | PASS: every link commit on origin, porcelain empty, only `config/presets/default.json` tracked. |
| Extra: git-pull upgrade | FAILS on the Mac path, INTRODUCED THIS LAP (S1). Finding F1. |

## Findings

**F1 (product, INTRODUCED THIS LAP by S1, severity high for Mac upgrades): a
v0.4.9 install that `git pull`s this branch with `default.json` active and no
`config/bridge.local.json` no longer boots.** S1 converted the TRACKED
`config/presets/default.json` to `{"sections": {"windows", "macbook"}}`. A
sectioned preset with no selected section raises, so the bridge exits 2:
`win_recv.py: error: preset section None is not available; available sections:
macbook, windows`. `.active` absent also resolves to default.json. The Mac launcher
`scripts/mac/run_receiver.command:45` only passes `--preset-section` when
bridge.local.json already exists, and nothing creates that file on upgrade.
Controls, same command (`--dry-run --no-ui --no-engines --no-pulse --no-osc-relay`),
same tree shape: v0.4.9 source boots and listens; HEAD with a one-line
`{"preset_section":"macbook"}` boots and listens; HEAD without it exits 2.
Evidence: evidence/upgrade-boot.log, upgrade-boot-v049.log, upgrade-boot-withlocal.log.
This breaks locked-design rule 5 ("Installed machines upgrade by git pull, not by
re-creating config"). The Windows launchers read `preset_section` from
windows_receiver_settings.local.json (example back-fills "windows"); whether an
existing v0.4.9 local file with no such key gets it is UNVERIFIED here (no pwsh).
Candidate fixes for a later link, not applied (product change): leave default.json
flat (a legacy preset already applies everywhere), or give machines with no
configured section a default (for example, the Mac launcher writing
bridge.local.json on first run the way the Windows example back-fills "windows").
This gate did not choose.

**F2 (product, PRE-EXISTING at v0.4.9): the bridge ignores SIGINT on macOS and one
thread spins about 94% CPU from boot.** With the exact gate boot command, two
SIGINTs (5 s and 3 s waits) left the process alive; SIGTERM stopped it and both
45123 and 7723 were released. `ps` at 10 s after boot: `%CPU 94.2`, CPU time 9.6 s
of 11 s elapsed. A `sample` of the live process puts the hot thread in the Python
main-thread eval loop (lock acquire with timeout, traceback creation), consistent
with a very short socket timeout in `windows/receiver.py:1009-1044`
(`serve_forever`, timeout = min(poll, fade poll, engine tick)). Root cause NOT
verified. Launch-artefact control: a nohup background job inherits SIGINT as
SIG_IGN; the gate launched through `perl -e '$SIG{INT}="DEFAULT"; exec ...'` and
proved Python then installs `default_int_handler` (evidence/wrapper-check.txt),
so the signal was deliverable. Version control: scripts/arm.sh run against a
v0.4.9 export (5d778eb, its own pre-migration presets) and against HEAD gave the
same result on both arms: 94% CPU, SIGINT ignored, SIGTERM exits, ports released
(evidence/arm-v049.txt, arm-head.txt, shutdown-head.txt). Not this lap's defect;
it matters because docs and the gate brief both assume Ctrl+C stops the bridge.

**F3 (API bar gap, lane-wide rule 4): the bridge has no quit/shutdown endpoint.**
The Windows tray menu `Quit` (windows/tray.py:177 and :382) stops the bridge, but
no HTTP route does. The Deck side has `POST /api/shutdown`. With F2, an SSH agent
on the Mac can only stop a bridge with SIGTERM. Every other bridge UI affordance
maps to a documented route (table below).

**F4 (UI, cosmetic): header layout.** At 1440x900 the section `<select>` (class
`btn`) stretches to full width and the header wraps into three rows, with the
"Section" label on the row above its select (screenshots 01, 04, 08). Functional.

**Observation (not a defect of this lap):** the build fingerprint still reports
`version=0.4.9 commit=2ae8f4ef55bf built_utc=2026-08-06` on this branch.

No test-only defect was found, so none was fixed.

## 1. Suite and mutation spot-checks

```
cd /Users/viddyslap/Documents/project-workspaces/steam-deck-midi
.venv/bin/python -m unittest discover -s tests -p "test_*.py"
  exit 0; Ran 795 tests in 6.531s; OK (skipped=1)
git status --porcelain   -> empty after the suite
```

Mutations ran only in a copy: `rsync -a --exclude .venv --exclude .git ./
/tmp/sdcore-gate/tree/`. An import probe proved modules load from the copy, and the
whole suite was green there first (`Ran 795 ... OK (skipped=1)`). Script:
scripts/mutate.py. For each mutant it checks that the anchor occurs exactly once,
runs the test on the pristine copy (must be GREEN), applies the mutant (must be
RED), restores the original bytes (must be GREEN, sha256 equal).

| Link | Behaviour reverted (file) | Test | Mutant |
| --- | --- | --- | --- |
| S1 | Section mapping overrides shared: swapped to shared-overrides-section (windows/config.py `select_preset_section`) | test_windows_config.PresetSectionTests.test_shared_mappings_apply_everywhere_with_whole_action_override | RED (AttributeError: shared note mapping replaced the section's cc mapping) |
| S2 | Refuse deleting this machine's section: guard removed (windows/ui_server.py) | test_ui_server.SectionApiTests.test_crud_refusals_leave_file_and_reload_untouched | RED, failures=3 (`200 != 409`) |
| S3 | Watcher also watches `.active` and bridge.local.json: dropped (windows/preset_watch.py `_scan`) | test_preset_watch.PresetWatcherTests.test_touch_add_delete_marker_and_local_settings | RED (`False is not true`) |
| S3 (extra) | `state_version += 1` removed (windows/receiver.py `reload_mappings`) | test_preset_watch.ReloadIntegrationTests.test_save_and_disk_reload_versions_and_real_midi | RED (`0 != 1`) |
| S4 | Fan-out loop truncated to the first target (deck/transport.py `_send_payload`) | test_deck_transport.DeckTransportTests.test_action_identical_bytes_and_seq_in_target_order | RED (list differs, second target missing) |
| S5 | Off-loopback token check disabled (deck/control_api.py) | test_deck_control_api.DeckControlAPITests.test_off_loopback_requires_token_on_every_route | RED, failures=9 errors=13 |

`.venv/bin/python -B mutate.py` exit 0, `ALL_BITE` (evidence/mutate.log).

Sweep artefact, recorded so nobody repeats it: the first run reported S1 as
"restored still RED". The S1 mutant has the same byte size as the original and
was written within the same second, so Python's mtime+size bytecode cache served
the mutant after the restore. Re-run with `__pycache__` purged and `python -B`:
all six clean. A mutation harness on this repo must disable bytecode caching.

## 2. Real bridge

Pre-flight: nothing bound on UDP 45123 or TCP 7723, no win_recv running, mido
lists `IAC Driver DECK_IN`, `DECK_OUT`, `PULSE_OUT`. Active marker `EDM Show.json`
(sections windows + macbook, 56 mappings each, identical), bridge.local.json
`{"preset_section": "macbook"}`. Byte copies of those three files were taken first.

Boot (from the run root; `BROWSER=/usr/bin/true` only suppresses the
`webbrowser.open` tab; the SIGINT wrapper is explained in F2):

```
BROWSER=/usr/bin/true nohup perl -e '$SIG{INT}="DEFAULT"; exec @ARGV' \
  .venv/bin/python -u -m windows.win_recv --listen 0.0.0.0:45123 --map config/windows_midi_map.json \
  --midi-port "IAC Driver DECK_IN" --feedback-port "IAC Driver DECK_OUT" --pulse-port "IAC Driver PULSE_OUT" \
  --timeout 2.0 --ui-port 7723 --preset-section macbook
```

- Boots: `engine config: path=config/engines count=14 active=13`, then
  `engines loaded:` with 14 names, `listening on udp://0.0.0.0:45123`,
  `mapping UI available at http://127.0.0.1:7723`. lsof: UDP *:45123 and TCP
  127.0.0.1:7723 LISTEN. Benign warnings as expected: PTZ VISCA bind to
  192.168.0.100, autopilot REST 127.0.0.1:8080 refused.
- `GET /api/settings` HTTP 200: `"preset_section":"macbook"`,
  `map_path` .../config/presets/EDM Show.json (evidence/settings-boot.json).
- `GET /api/state-version` HTTP 200 `0`, `Cache-Control: no-store`.
- `GET /api/mappings`: `section macbook`, `bridge_section macbook`,
  `sections ["windows","macbook"]`, `legacy false`.

Disk reload (a separate python3 process rewrote the preset with macbook BTN_A
note 36 -> 48; evidence/disk-reload.txt). Elapsed from write:

```
INFO preset watch changed: config/presets/EDM Show.json   0.424 s
INFO hot-reloaded mappings: 56 actions                     0.600 s
/api/state-version 0 -> 1                                  0.601 s
/api/mappings macbook BTN_A note 48                        read at 0.627 s
PASS (all three within 2 s)
```

Beyond the brief, the live receiver was checked on the wire: scripts/wire_note.py
sends BTN_A down/up as UDP to 45123 and reads the IAC loopback input. It received
`('note_on', 0, 48, 127), ('note_off', 0, 48, 0)` (evidence/wire-macbook.txt).

Section switch without restart (evidence/section-switch.txt):
`PUT /api/settings {"preset_section":"windows"}` HTTP 200; state-version 1 -> 3
(the documented duplicate: the API signal plus the watcher seeing
bridge.local.json); `GET /api/mappings` `section windows`, BTN_A note 36; the wire
now gives `('note_on', 0, 36, 127)`; bridge pid 47350 before and after. Section
set back to macbook with PUT (bridge.local.json bytes equal to the copy).

Shutdown: see F2. SIGINT x2 did not stop pid 47350; SIGTERM did; lsof then shows
nothing on 45123 or 7723.

## 3. UI in a real browser

Headless Chromium through playwright-core 1.58.2 (borrowed read-only from an
existing node_modules), viewport 1440x900, against the live bridge.
Script: scripts/ui_gate.cjs; log: evidence/ui-gate.log. JS `prompt`/`confirm`
dialogs were answered through the browser's dialog events. They are real page
dialogs, not OS windows.

| Screenshot | Shows |
| --- | --- |
| 01-header-section-selector-macbook.png | Header with the Section selector, `macbook (this machine)` selected; status bar `Machine: macbook, Preset: EDM Show.json`. |
| 02-section-add-rename-delete-controls.png | Add/Rename/Delete section controls; Delete disabled on this machine's own section. |
| 03-editor-macbook-btn-a-note-48.png | Editor on macbook, BTN_A note 48 (the disk-reloaded value). |
| 04-editor-switched-to-windows-btn-a-note-36.png | After switching the selector to windows: BTN_A note 36; bridge identity stays macbook (GET /api/settings confirmed). |
| 05-section-added-gatecheck.png | Add section via prompt `gatecheck` + copy confirm; API lists windows, macbook, gatecheck. |
| 06-section-renamed-gatecheck-renamed.png | Rename via prompt. |
| 07-section-deleted-back-to-macbook.png | Delete via confirm; API back to windows, macbook. |
| 08-changed-on-disk-notice-unsaved-edit-kept.png | BTN_A edited to 61 and applied (UNSAVED), then a second process changed macbook BTN_B to 50 on disk: notice `preset changed on disk - reload to see it` visible, field still 61, UNSAVED badge still shown; disk BTN_A still 48 (edit not saved). |
| 09-after-reload-disk-value-btn-b-50.png | Reload clicked: first confirm cancelled (edit 61 and notice kept), second accepted; BTN_B shows the disk value 50, UNSAVED cleared. |

Copies are in /Users/viddyslap/Documents/ViddyVault/screenshots/sdcore-gate/ and
in screenshots/ here. Each PNG was opened and checked against its caption.
Afterwards the show preset was restored from its byte copy while the bridge still
ran. The watcher reloaded it (version 11 -> 12, macbook BTN_A 36, BTN_B 38), and
`cmp` confirmed all three files identical to the copies. No page errors were
logged.

## 4. The API bar

Detectors, run manually and made to bite in the scratch copy (restored copies
byte-equal to the run root):

| Detector | Pristine | With fake `/api/nope` |
| --- | --- | --- |
| test_ui_server.HtmlApiBarTests (S2 grep test; `apiFetch('/api/nope')` added to index.html) | OK, `HTML API bar: 21 paths registered` | FAILED: `HTML API path has no registered route: /api/nope` |
| test_ui_server.BridgeSettingsApiTests.test_api_inventory_matches_registered_method_paths (undocumented Flask route added) | OK | FAILED: `('GET', '/api/nope')` |
| test_deck_control_api.DeckControlAPITests.test_every_deck_route_is_documented (undocumented entry in ROUTES) | OK | FAILED: `('GET', '/api/nope')` |

Evidence: evidence/apibar-grep-test.txt, apibar-inventory-test.txt.

Bridge UI affordances (windows/static/index.html, every click/change/input/keydown
handler; line numbers at 32368bf) and the Windows tray:

| Affordance | Route in docs/api.md |
| --- | --- |
| Page load and 2 s poll (880-886, 942) | GET /api/state-version, /api/actions, /api/mappings, /api/presets, /api/macros, /api/engines |
| Reload on the disk notice `btnReloadPreset` (953) | POST /api/reload |
| Section selector `sectionSelect` (1008) | GET /api/mappings?section=name |
| Add section `btnSectionAdd` (1020) | POST /api/presets/sections/add |
| Rename section `btnSectionRename` (1029) | POST /api/presets/sections/rename |
| Delete section `btnSectionDelete` (1035) | POST /api/presets/sections/delete |
| Mapping type, Apply fields, Apply JSON, Clear mapping (1177-1197) | Local draft; persisted by POST /api/save (section document) |
| Save and Apply `btnSave`, Ctrl/Cmd+S (1908, 2084) | POST /api/conflicts then POST /api/save |
| Conflict modal Save anyway (1965) | POST /api/save |
| Global Settings Save `btnSaveSettings` (1948) | POST /api/save (macro_settings, analog_settings) |
| Factory Reset confirm (1977) | POST /api/reset |
| Preset list item click (1422) | POST /api/presets/load |
| Preset rename (1429, 1518) | POST /api/presets/rename |
| Preset delete (1436, 1552) | POST /api/presets/delete |
| Save as new preset, button or Enter (1456, 1488, 1504) | POST /api/presets/save-as |
| New macro / edit macro save (1683, 1790) | POST /api/macros, PUT /api/macros/<id> |
| Delete macro confirm (1827) | DELETE /api/macros/<id> |
| Apply macro to selected button (1645) | Local draft; POST /api/save |
| Engine toggle checkbox (2024) | POST /api/engines/<type>/active (this machine), persisted by POST /api/save; remote sections via POST /api/save |
| Resync OSC Wiggles (2047) | POST /api/engines/osc-sync/resync |
| Action chip select, search filter, tab switch, preset dropdown open, Copy JSON, all Cancel buttons | View-only; the data is in the GETs above |
| Tray `Open Web UI`, `View Terminal` (tray.py:175, :379-380) | View-only |
| **Tray `Quit` (tray.py:177, :382)** | **NONE: gap F3** |

Routes with no UI (GET /api/settings, PUT /api/settings, GET
/api/presets/<name>/sections, POST /api/engines/gyro-feedback/resync, POST
/api/engines/refresh) exceed the bar and are fine. There is no UI to change this
machine's own section identity; only PUT /api/settings or the launchers do that.

Deck TTY menus (deck/launch_send.py menu at 155-218, deck/learn_wizard.py):

| Menu item | Route in docs/api.md (Deck sender section) |
| --- | --- |
| Number N: send to one preset (clears any active set) | POST /api/targets/active {"names":[N]} then POST /api/sender/start |
| Create new preset (host, name prompts) | POST /api/targets/add |
| m. Select multiple targets (toggle, s save, q cancel) | POST /api/targets/active |
| s. Start active targets | POST /api/sender/start |
| r. Rename a preset | POST /api/targets/rename |
| d. Delete a preset (y/n) | POST /api/targets/delete |
| t. Stop sender | POST /api/sender/stop |
| x. Restart sender | POST /api/sender/restart |
| q. Quit | POST /api/shutdown |
| Menu header: bindings path, device id, target list | GET /api/status, GET /api/targets, GET /api/settings |
| Learn: 1. Full re-learn | POST /api/learn/start {} |
| Learn: 2. Re-learn one action (numbered action list) | GET /api/actions, POST /api/learn/start {"action":...} |
| Learn: press control and watch candidate | GET /api/learn |
| Learn: Enter confirm | POST /api/learn/confirm |
| Learn: Esc skip | POST /api/learn/skip |
| Learn: Ctrl+X cancel, q quit | POST /api/learn/cancel |

No Deck gap found.

## 5. Fan-out on the wire and the Deck control API

`python3 -B /tmp/sdcore-gate/fanout_wire.py` (system Python 3.14.7, imports the run
root's deck.transport, nothing faked): exit 0, `FANOUT_PASS`
(evidence/fanout-wire.txt). Two real listeners bound 127.0.0.1:45123 and :45124.
One sender socket sent `send_action` seq 1, `send_axis` seq 2 and `send_heartbeat`
seq 3 to `parse_targets("127.0.0.1:45123,127.0.0.1:45124")`. Both listeners got
all three packets with identical bytes (sha256 d3ed9ca6..., d1156404...,
7e3e67ac...), the same seq, and the same source port 64160.

Deck control API standalone: `python3 -B -m deck.control_api --settings
/tmp/sdcore-gate/deck/settings.json`, from a copy of the example settings with
bindings pointed at a /tmp copy so no tracked file could be written. Script:
scripts/deck_api_routes.sh, exit 0 (evidence/deck-api-routes.txt). All 21
documented method/path pairs were called with curl:

- 200 with the expected JSON: GET status, targets, bindings, settings, actions,
  learn; POST targets/add, targets (replace), targets/rename, targets/active,
  targets/delete, bindings/reload, sender/start, sender/stop, sender/restart,
  shutdown; PUT settings. Writes checked on disk: active_targets `['windows',
  'macbook']` in that order, profile_name `gate-profile`.
- Refusals with 400 and a JSON error: add with host `not a host!`, active with an
  unknown name, learn/start (`failed to locate shared library: Xi`, expected on
  macOS), and learn confirm/skip/cancel with `no learn session`.
- sender/start and sender/restart return `running: true`, then status shows
  `running: false`, and api.log shows `failed to start XI2 listener` (the
  documented asynchronous start; there is no XI2 on a Mac).
- `POST /api/shutdown` exited the process and released 7724. A first aborted run
  (a bug in my script) was stopped with SIGINT, and the Deck API did exit on it.

Token refusal (scripts/deck_token.sh with a throwaway token in the /tmp settings
only, exit 0, evidence/deck-token.txt):

- `--api-bind 0.0.0.0` with no token refuses startup: exit 2, `api_token is
  required when binding off-loopback`, 7725 never bound.
- Token persisted over loopback: `GET /api/settings` shows only
  `api_token_configured: true`, never the value.
- `--api-bind 0.0.0.0 --api-port 7725`, requested via the LAN address
  192.168.1.63: status with no token 401, wrong token 401; `POST
  /api/targets/add` with no token 401 `X-Deck-Token required`; `POST
  /api/shutdown` with no token 401 and the process stayed up; loopback with no
  token on the 0.0.0.0 bind also 401. The settings sha256 was unchanged by the
  refused writes. With the right token, status returned its JSON and shutdown
  returned 200 and exited. 7724 and 7725 were released.

## 6. Commits, push, exclusions

```
git -c url.git@github.com:.insteadOf=https://github.com/ -c core.sshCommand=... fetch origin chain/steamdeck-20260914   exit 0
git rev-parse HEAD                                   32368bf628c3f948f162bfd0ff7de2514fd34f09
git ls-remote --heads origin chain/steamdeck-20260914  32368bf628c3f948f162bfd0ff7de2514fd34f09
git log origin/chain/steamdeck-20260914 --oneline -1   32368bf feat(deck): add shared sender control API and SSH CLI
git status --porcelain                               empty (before this gate's own files)
```

| Link | Engine-recorded commit | On origin |
| --- | --- | --- |
| S1 | d20f195 (feat) + 0f86e92 (docs, recorded) | yes |
| S2 | b91d248 | yes |
| S3 | 8dcb482 | yes |
| S4 | e360646 | yes |
| S5 | 32368bf | yes |

`git log --stat 5d778eb..HEAD` grepped for `presets/`, `.local.json`,
`osc_sync.json`, `audio_opacity.json`: the only hit is `config/presets/default.json`,
which is allowed (see F1 for its content change). `git ls-files` of those
patterns at HEAD: only `config/presets/default.json`.

## Owed-to-gate items

Discharged here: real HTTP/UDP binds; a real browser, dialogs and screenshots
(S1, S2, S3); disk hot reload on the real bridge with the watcher's log line
(S3); real MIDI output on this Mac's IAC bus for both sections (S1, S3 physical
MIDI on the Mac host); wire fan-out to two listeners (S4); every Deck HTTP route
and token refusal on a real LAN interface (S5).

NOT discharged, with the reason:

- Windows launcher execution and the Windows bridge host (S1): no Windows machine
  or pwsh from this executor. This also leaves F1's Windows half unverified.
- Native Steam Deck XI2/HID capture, TTY menu on the Deck, and HTTP learn with a
  physical control (S4, S5): no Deck is attached. On macOS, learn/start and the
  sender worker fail at the Xi library as designed.
- Travel-router mDNS/DHCP recovery and Deck-to-bridge reachability across the
  router (S4, S5): the token test ran on the home LAN address of this Mac only.
- Multiple physical bridges answering one Deck with MIDI feedback (S4, S5): needs
  the Deck plus the Windows bridge. Only loopback fan-out was proven.

## Reproduce

Scripts are in scripts/ (they write to /tmp/sdcore-gate/ and assume that layout):
mutate.py (step 1), wire_note.py (IAC wire check), ui_gate.cjs (step 3; needs a
playwright-core path), arm.sh (F2 control arms), fanout_wire.py and
deck_api_routes.sh / deck_token.sh (step 5). Raw captures are in evidence/.
