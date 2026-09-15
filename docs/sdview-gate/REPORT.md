GUARD GREEN at the gate's LAST laptop act (`win_guard.ps1 -Mode compare -Baseline sdwin\vg\before.json` exit 0, "protected state observed; pythonProcesses=0"). NO BYTE DIFFERENCE: every A/B arm pair for EDM Show, PTZ and default is identical on the Mac and on the Windows laptop at HEAD b38ffb2, recomputed from raw captures.

# sdview GATE (VG) - independent measurement of V1..V3

Gate: claude-rc on the Mac, unsandboxed. Branch `chain/steamdeck-20260914`.
BASE OF LAP `b0c5019dd6b43f6f91b6dff78381d9576d77ac7e` (first line of docs/sdview-v1/REPORT.md).
Gate HEAD at entry `b38ffb23c3d9bfb78f8fc2337abe61cb00336907` (V3's final evidence commit; `git status --porcelain` empty, ls-remote equal).
Scratch: `/tmp/sdview-gate/` on the Mac, `C:\Users\Ben\AppData\Local\Temp\sdwin\vg\` on the laptop.
Envelopes read: `curl -s http://127.0.0.1:8899/launches/sdview-q001.V1|V2|V3` (all state done, status complete).
Scripts committed under [scripts/](scripts/): `ui_gate.cjs` (Chromium), `api_bar.py` (curl), `mutate.py`. Evidence under [evidence/](evidence/).

Verdict in one line: the editor half WORKS END TO END in a real browser (every drill-in edit lands on disk as exactly the intended change, the API does the same, bars 1 and 2 hold on both OSes), with TWO LAYOUT DEFECTS: labels overlap at 1024x768 (a FAIL on 2a) and three bottom labels are hidden under the status bar on the 1440x900 front door until you scroll.

## For Ben

1. **Friday is not at risk from this lap.** The MIDI send path, config parser, engines and receiver are untouched since the start of the lap (`git diff b0c5019 HEAD -- windows/midi.py windows/receiver.py windows/config.py mac/` = 0 lines; the only `windows/` changes are ui_server.py and static/). Every mapping in EDM Show, PTZ and default sends the same bytes as v0.4.9 on the Mac and on the laptop, and the full suite is green on both (865 tests). The engine caveat from lap sdwin still applies unchanged: the instrument runs with engines off.
2. **The controller view does what you asked.** In a real Chromium I clicked all 23 controls, edited every mapping type, cleared, applied a library macro, used the Advanced JSON tab, hit a conflict, cancelled (file untouched) and saved anyway. After every Save I read the preset file: each time exactly the one intended value changed and nothing else. The same edits sent with curl to the new API produced the same file, step for step (27/27).
3. **Layout defect A (fails 2a at 1024x768):** at 1024x768 "D-pad Right" overlaps "Left trackpad" and "Right stick" overlaps "Right trackpad" (5.2 px vertically; the trackpad labels wrap to two lines). At 1440x900 the same Right stick / Right trackpad overlap appears once a drill-in card is open. See `after-controller-front-door-1024.png` and `after-geometry-1440x900-card-open-btn_a.png`.
4. **Layout defect B:** on the 1440x900 front door with no card open, L5, Gyro and R5 sit under the status bar at the bottom. They are reachable by scrolling the pane 91 px, and they fit once a card is open. The literal 2a check (label box inside the viewport) passes; I report it anyway because you cannot see 3 of 23 labels at first glance (`after-controller-front-door.png`).
5. **Small things:** conflict marks on rows only exist while the conflict modal is open and are blurred behind it, so they are hard to read (the modal text does name both actions). The drill-in macro picker shows "Encoder" plus a non-ASCII minus sign (U+2212) from config/macro_library.json (pre-existing data, first surfaced in this view).

## Step 0 - real bridges

Each bridge ran from a `git archive` tree in scratch with byte copies of `.showready/fixtures/mac/presets/{EDM Show,PTZ,default}.json` (EDM Show sha256 58e47bfd... equal to the fixture), `.active` = `EDM Show.json`, no bridge.local.json, env `PYSTRAY_BACKEND=dummy BROWSER=/usr/bin/true`. No bridge touched the run root's config.

| Bridge | Tree | argv (python = run root .venv) | pid | Listen lines |
| --- | --- | --- | ---: | --- |
| head | `git archive b38ffb2` -> /tmp/sdview-gate/bridges/head | `-u -m windows.win_recv --listen 127.0.0.1:47791 --map config/windows_midi_map.json --preset-section windows --dry-run --no-engines --no-pulse --no-osc-relay --ui-port 17791 --timeout 2.0` | 83711 | `mapping UI available at http://127.0.0.1:17791`, `listening on udp://127.0.0.1:47791`; lsof TCP 127.0.0.1:17791 LISTEN, UDP 127.0.0.1:47791 |
| api (second config copy) | `git archive b38ffb2` -> bridges/api | same, ports 17792 / 47792 | 83712 | `mapping UI available at http://127.0.0.1:17792`, `listening on udp://127.0.0.1:47792` |
| base (BEFORE PNG) | `git archive b0c5019` -> bridges/base | same, ports 17793 / 47793 | 17255 | `mapping UI available at http://127.0.0.1:17793`, `listening on udp://127.0.0.1:47793` |
| mutant e | mutate.py copy `e-default-list-browser` | same, ports 17794 / 47794 | recorded in evidence/mutations.json | SIGTERM, `os.kill(pid,0)` ProcessLookupError |

Ports checked free by bind before boot (python bind on 17791-17793 TCP and 47791-47793 UDP: all free). `GET /api/settings` on head: `listen 127.0.0.1:47791, preset_section windows, ui_port 17791, map_path .../bridges/head/config/presets/EDM Show.json`.
Boot noise, classified: the dummy pystray backend raises `NotImplementedError` in the tray thread (expected for `dummy`; the bridge keeps serving), and `build fingerprint: version=0.4.9 commit=2ae8f4ef55bf` comes from the tracked windows/build_fingerprint.py (pre-existing, not this lap).
Stop: `POST /api/shutdown` on 17791/17792/17793 each returned 202; `ps -p 83711,83712,17255` exit 1 (none listed); `lsof -nP -iTCP:17791 -iTCP:17792 -iTCP:17793 -iUDP:47791 -iUDP:47792 -iUDP:47793` exit 1; `pgrep -fl windows.win_recv` exit 1.

## Step 1 - suite and node checks at HEAD

| Command | Exit | Result |
| --- | ---: | --- |
| `TMPDIR=/tmp/sdview-gate/mactmp PYSTRAY_BACKEND=dummy BROWSER=/usr/bin/true .venv/bin/python -m unittest discover -s tests -p "test_*.py"` | 0 | `Ran 865 tests in 9.695s` / `OK (skipped=2)` ([log](evidence/mac-suite.log)) |
| `/opt/homebrew/bin/node tests/ui_controller_check.cjs` | 0 | `UI controller behavior: PASS (23 arrows, map anchors/shapes, front door, ...)` |
| `/opt/homebrew/bin/node tests/ui_controller_macro_check.cjs` | 0 | `48 disk writes match page Save; 72 incompatible writes refused without byte changes` |
| `/opt/homebrew/bin/node tests/ui_reload_check.cjs` | 0 | `UI reload behavior: PASS (...)` |
| `/opt/homebrew/bin/node tests/ui_sections_check.cjs` | 0 | `UI section behavior: PASS (...)` |
| `.venv/bin/python -m unittest -v tests.test_ui_server.BridgeSettingsApiTests.test_api_inventory_matches_registered_method_paths` | 0 | Ran 1, OK |
| `.venv/bin/python -m unittest -v tests.test_ui_server.HtmlApiBarTests` | 0 | Ran 2, OK (`test_external_static_api_detector_fires_and_restores`, `test_html_parses_and_all_api_paths_are_registered`) |

## Step 2 - real browser

`/opt/homebrew/bin/node docs/sdview-gate/scripts/ui_gate.cjs full 17791 /tmp/sdview-gate/bridges/head /tmp/sdview-gate/ui-head` -> exit 1, `SUMMARY 73/74 PASS` (the one FAIL is defect A). playwright-core 1.58.2 from life-os-showday/web-ui-server, its bundled headless Chromium, clipboard permission granted for the bridge origin. Per-assertion JSON: [ui-results.json](evidence/ui-results.json); log: [ui-gate.log](evidence/ui-gate.log).

Rig error, disclosed: the FIRST full run ([ui-gate-run1-RIGERROR.log](evidence/ui-gate-run1-RIGERROR.log), 68/71) queued a dialog answer for a Reload click on a hidden button; the click was swallowed, so every later confirm dialog got the previous step's answer (d10 switched sections instead of staying; e2 started with a notice already showing). Fixed by removing that step's queued answer, failing on any dialog with no queued answer (`no-unexpected-dialogs`) and asserting the queue is empty at the end. The fixture copy was restored (sha256 58e47bfd...) and the whole run repeated; only the second run is used below.

### 2a/2b assertion table

| Assertion | 1440x900 | 1024x768 | Evidence |
| --- | --- | --- | --- |
| Mappings opens on Controller (controllerView visible, List hidden, Controller aria-pressed, tab editor, section windows) | PASS | PASS | cleared localStorage first |
| 23 visible arrows, 23 unique, none zero-size | PASS | PASS | `.controller-arrow` |
| 23 labels, ids equal `GET /api/controller-map` ids | PASS | PASS | |
| every label bounding box inside the viewport | PASS | PASS | [geometry](evidence/ui-occlusion-geometry.json) |
| no two label boxes intersect (253 pairs) | PASS | **FAIL**: dpad_right x left_pad, right_stick x right_pad | defect A |
| no horizontal page scroll | PASS (1440) | PASS (1024) | |
| List switch shows today's editor (sidebar, 75 chips, editor) | PASS | PASS | |
| reload remembers List, then reload remembers Controller | PASS | PASS | localStorage `steamdeck.mappingView` |
| 2b every control: clicked its label; groups, group order and Action IDs equal `GET /api/controller-map/<id>?section=windows` | PASS 23/23 | PASS 23/23 | [1440](evidence/ui-drill-1440x900.json), [1024](evidence/ui-drill-1024x768.json) |
| 2b every row badge equals the API mapping type (or unmapped) | PASS | PASS | |
| 2b Escape closes the card, all 23 | PASS 23/23 | PASS 23/23 | |
| keyboard: focus label B, Enter opens card (focus to title), Escape closes and returns focus to label B, outline solid | PASS | - | V2 owed this |

Occlusion probe (not in the gate's list, added after reading the front-door PNG): `node ui_gate.cjs geometry 17791 ...` samples `elementFromPoint` at each label's centre and four inset corners, pane scrolled to top. Detector fires and does not fire in the same run:

| Viewport | Card | Intersections | Labels not topmost at their own points |
| --- | --- | --- | --- |
| 1440x900 | closed | none | l5, r5, gyro (covered by `statusbar`; `tab-editor` scrollHeight 818 > clientHeight 727) - defect B |
| 1440x900 | open (A) | right_stick x right_pad | right_stick (by the Right trackpad label) - defect A |
| 1024x768 | closed | dpad_right x left_pad, right_stick x right_pad | dpad_right, right_stick - defect A |
| 1024x768 | open (A) | same two | same two |

2g KNOWN F4: the header wraps to three rows at both 1440x900 and 1024x768 (header height 106 px at both, `ui-gate.log` "F4 note"), and the logo text wraps at 1024. Known backlog item F4 (lap sdauto); not failed.

### 2c disk-diff rows (edit through the UI, Save, read the preset file)

Every row: `before` and `after` are the sha256 of `bridges/head/config/presets/EDM Show.json`; the diff is a recursive JSON diff of the WHOLE file and must equal the expected list exactly (nothing else changed). Full records: [ui-steps.json](evidence/ui-steps.json).

| Step | UI operation (drill-in) | Whole-file JSON diff | sha before -> after | Result |
| --- | --- | --- | --- | --- |
| c1 | A > BTN_A Edit, Note field 36 -> 50, Apply fields, Save | `sections.windows.mappings.BTN_A.note` 36 -> 50 | 58e47bfde76e -> b5ca30b284e0 | PASS |
| c2 | Right stick > R_STICK_X_AXIS (axis_split_cc) Deadzone 3500 -> 4000 | `...R_STICK_X_AXIS.deadzone` 3500 -> 4000 | b5ca30b284e0 -> f6068cfbb54b | PASS |
| c3 | Y > BTN_Y_LAYER_2 Clear mapping | `...BTN_Y_LAYER_2` {note 43} -> absent | f6068cfbb54b -> 186d2cd2e4bd | PASS |
| c4 | D-pad Down > DPAD_DOWN_LONG_PRESS Apply macro "Click Toggle" (encoder/staged options disabled) | `...DPAD_DOWN_LONG_PRESS.gesture` long_press -> click | 186d2cd2e4bd -> f7b69086aa49 | PASS |
| c5 | L5 > Advanced tab `{"L5":{note 80, velocity 100}}` Apply JSON | `...L5.note` 75 -> 80, `...L5.velocity` 127 -> 100 | f7b69086aa49 -> a0c1f0110d8e | PASS |
| c6 | START > CC 78 -> 79 (collides with SELECT ch3 CC79), Save: modal "Ch3 CC79: START, SELECT", START row has `controller-conflict` + "MIDI CC conflict"; **Cancel** | none; sha unchanged 3 s later; marks cleared | a0c1f0110d8e -> a0c1f0110d8e | PASS |
| c6 | Save again, **Save anyway** | `...START.cc` 78 -> 79 | a0c1f0110d8e -> b6c16e202ebb | PASS |

### 2d parity walk (V3's table, each performed in the browser)

| V3 List operation | Performed in the drill-in | Disk / DOM result | Result |
| --- | --- | --- | --- |
| Set type | d1: Gyro > GYRO_FORWARD type select Note (DEFAULTS), Apply, Save | adds `GYRO_FORWARD {note, ch0, note 36, vel 127}`, only change (4dc9232dda6b -> cec039214cbd) | PASS |
| Edit note fields | c1 | above | PASS |
| Edit cc fields | d2: L4 On value 127 -> 100 | `L4.on_value` only (-> 8e0c01a39ff7) | PASS |
| Edit macro_cc fields | d3: D-pad Right > DPAD_RIGHT fade override 1.5 | adds `DPAD_RIGHT.fade_duration_seconds 1.5` only (-> e98249e7a026) | PASS |
| Edit relative_cc fields | d4: Right trackpad > R_PAD_DOWN repeat interval 40 -> 60 | `R_PAD_DOWN.repeat_interval_ms` only (-> b845e102fd3a) | PASS |
| Edit staged_note_macro fields | d5: Left trackpad > L_PAD_LEFT_LONG_PRESS macro delay 120 | adds `macro_delay_ms 120` only (-> a200e1131e48) | PASS |
| Edit axis_to_cc fields | d6: L2 > L_TRIGGER_PRESSURE deadzone 5000 -> 6000, curve quadratic | those two fields only (-> 62755fa695ca) | PASS |
| Edit axis_split_cc fields | c2 | above | PASS |
| Clear | c3 (row Clear); d8 Advanced `{"SELECT": null}` | d8 removes SELECT only (b6c16e202ebb -> 4dc9232dda6b) | PASS |
| Apply library macro | c4 | above; incompatible options disabled | PASS |
| Raw JSON Apply | c5; plus foreign ID `{"L4":...,"BTN_A":null}` on L4 | refused inline "BTN_A does not belong to this control.", Save stays disabled, nothing committed | PASS |
| Copy JSON | d9: A > Advanced > Copy | clipboard text equals the textarea (BTN_A note 50) | PASS |
| Save and conflict guard | c6 | above | PASS |
| Section switch confirm | d10: typed BTN_B 57 unapplied, select macbook, dismiss | stays windows, typed 57 kept; accept -> macbook shows BTN_B note 38; back to windows | PASS |
| Draft preservation on reload | e, e2 below | | PASS |
| Factory reset | d12: Factory Reset > confirm | windows mappings equal windows_midi_map.json mappings, macbook byte-for-value unchanged, all 26 diff paths under `sections.windows.` (b77411f79a46 -> bbe0cff0931e) | PASS |
| Return to List | d11: A > BTN_A "Open in list" | List editor shows BTN_A badge with note 50 (`after-list-view.png`); Controller button returns | PASS |

List operations NOT in V3's table, checked by reading renderEditor and the tabs: the sidebar filter and chip navigation (navigation, not a mapping operation); Macro Library tab create/edit/delete of library entries (library management, reachable from the Controller view because the tabs are global, and it has its routes); Global Settings and Engines tabs (not mapping operations, unchanged). **No mapping operation the List offers is missing from the drill-in.** One note: the Macro Library tab's "apply to selected" still targets the List selection, not the open drill-in control; the drill-in's own per-row picker is the Controller path.

### 2e drafts and 2e2 agent edit under a draft

| Step | Action | Observed | Result |
| --- | --- | --- | --- |
| e | B > BTN_B Note typed 55, not applied; outside process rewrote the file with `sections.macbook.mappings.BTN_A.note` 36 -> 37 (diff exactly that, 62755fa695ca -> 9ab0d2365cc0) | notice "preset changed on disk - reload to see it" visible; typed field still 55; still 55 after 2.5 s more of polling (`after-draft-notice.png`) | PASS |
| e | Reload, accept discard | notice hidden | PASS |
| e2 | 3 s settle, notice hidden; X > BTN_X Note typed 60, not applied; `curl -sS -X PUT -H 'content-type: application/json' --data '{"type":"note","channel":0,"note":44,"velocity":127}' 'http://127.0.0.1:17791/api/mappings/BTN_X?section=windows'` | HTTP 200; notice appears; typed field still 60; row description still shows the old note 40 | PASS |
| e2 | file after | whole-file diff exactly `sections.windows.mappings.BTN_X.note` 40 -> 44; sha256 b77411f79a4688580cbcf45c8fc853f363d7330b89466ec5a0bc1966b39fe1a4 | PASS |
| e2 | Reload, accept | BTN_X row shows note 44 | PASS |

### 2f API bar (curl on the second config copy)

`python3 docs/sdview-gate/scripts/api_bar.py 17792 /tmp/sdview-gate/bridges/api /tmp/sdview-gate/ui-head/steps.json /tmp/sdview-gate/api-bar.json` -> exit 0, `ALL PASS 27/27`. Each write's resulting file (parsed) is compared with the BROWSER run's file after the same step. Full commands and codes: [api-bar.json](evidence/api-bar.json).

| Row | Route | HTTP (want) | File |
| --- | --- | --- | --- |
| bad spec channel 99 | PUT /api/mappings/BTN_A?section=windows | 400 (400) | bytes identical |
| bad spec channel 99 with force=1 | PUT ...&force=1 | 400 (400) | bytes identical |
| unknown type / malformed JSON body | PUT | 400 / 400 | bytes identical |
| unknown action / unknown section / incompatible macro | PUT NOPE / DELETE section=nosuch / POST /api/macros/encoder-plus/apply | 404 / 422 / 409 | bytes identical |
| controller map | GET /api/controller-map; 23x GET /api/controller-map/<id>?section=windows; GET .../nosuch | 200 equals owned file; 23/23 groups equal the map; 404 | unchanged |
| c1 c2 c5 d1-d6 e2 | PUT /api/mappings/<action_id>?section=windows with the explicit spec | 200 each | equals browser snapshot at each step |
| c3, d8 | DELETE /api/mappings/<action_id>?section=windows | 200 | equals browser snapshot |
| c4 | POST /api/macros/click-toggle/apply `{"action_id":"DPAD_DOWN_LONG_PRESS","section":"windows"}` | 200 | equals browser snapshot |
| c6 conflict without force | PUT START cc 79 | 409 (409), body has `conflicts` | bytes identical |
| c6 with force | PUT ...&force=1 | 200 | equals browser snapshot |
| e | outside python write (same as browser step) | - | equals browser snapshot |
| d12 | POST /api/reset `{"section":"windows"}` | 200 | equals browser snapshot |

Comparator control (it can say no): the API copy's final file compared with every browser snapshot is equal ONLY for d12 (16 other steps False): [api-bar-comparator-control.txt](evidence/api-bar-comparator-control.txt).
Every drill-in operation performed has its HTTP route in docs/api.md (the api-inventory test is the equality check of that table with Flask's url_map, exit 0 above; mutation d shows it bites).

## Step 3 - PNGs

Written to `/Users/viddyslap/Documents/ViddyVault/screenshots/sdview-gate/` and [screenshots/](screenshots/) (22 files, identical copies). I opened every one.

| File | Size | What it shows |
| --- | --- | --- |
| before-mappings.png | 1440x900 | BASE OF LAP b0c5019: Mappings tab is the sidebar list (BTN_A... chips) and "Select an action from the sidebar" empty state; no controller view. |
| after-controller-front-door.png | 1440x900 | HEAD front door: Controller/List switch, original drawn Deck outline, 23 labelled arrows with mapped/total counts; L5/Gyro/R5 labels cut off at the bottom by the status bar (defect B). |
| after-drill-a.png | 1440x900 | A card open on the right: TAP BTN_A note 36, LAYER 2 BTN_A_LAYER_2 note 37, A arrow and button highlighted blue. |
| after-drill-l2.png | 1440x900 | L2 card: TAP L2_SOFT/L2_FULL, LAYER 2 rows visible; card continues below the fold (pane scrolls). |
| after-drill-left-stick.png | 1440x900 | Left stick card: LEFT_STICK_CLICK_L3 note 72 and the unmapped digital directions; ANALOG group below the fold. |
| after-drill-left-trackpad.png | 1440x900 | Left trackpad card: four TAP pad directions with notes 88/89/82/83; long press and analog below the fold. |
| after-drill-gyro.png | 1440x900 | Gyro card: TAP GYRO_FORWARD/BACKWARD unmapped, ANALOG GYRO_PITCH/YAW unmapped; gyro tile highlighted. |
| after-drill-a-card.png | 350x471 (card element, 1440x1800 viewport) | Whole A card, both groups. |
| after-drill-l2-card.png | 350x885 | Whole L2 card: TAP, LAYER 2, ANALOG L_TRIGGER_PRESSURE AXIS ch1 CC 1. |
| after-drill-left-stick-card.png | 350x1093 | Whole Left stick card: TAP click + 4 directions, ANALOG L_STICK_X/Y_AXIS. |
| after-drill-left-trackpad-card.png | 350x1507 | Whole Left trackpad card: TAP 4, LONG PRESS 4 (two STAGED), ANALOG L_PAD_X/Y_POS. |
| after-drill-gyro-card.png | 350x844 | Whole Gyro card: TAP 2, ANALOG PITCH/YAW/ROLL, all unmapped. |
| after-row-open-in-edit.png | 1440x900 | BTN_A row expanded: Mapping type Note, Channel 0, Note 50 typed, Velocity 127, Apply fields, Clear mapping. |
| after-advanced-tab.png | 1440x900 | L5 card on the Advanced tab: "Mappings JSON for L5" textarea with note 80 / velocity 100, Apply JSON and Copy. |
| after-conflict-modal-marked-rows.png | 1440x900 | "Mapping conflict detected" modal, `Ch3 CC79: START, SELECT`, Cancel / Save anyway; START row's red conflict mark visible but blurred behind the backdrop. |
| after-list-view.png | 1440x900 | List selected after one click on "Open in list": today's editor for BTN_A (note 50), sidebar chips, Raw JSON. |
| after-draft-notice.png | 1440x900 | "preset changed on disk - reload to see it / Reload" notice while BTN_B's typed 55 stays in its open row. |
| after-controller-front-door-1024.png | 1024x768 | 1024 front door (taken after the factory-reset step, so counts differ): D-pad Right/Left trackpad and Right stick/Right trackpad labels touching and overlapping (defect A); header wraps (F4). |
| after-geometry-1440x900-card-closed.png | 1440x900 | Occlusion probe frame: same as the front door, bottom labels under the status bar. |
| after-geometry-1440x900-card-open-btn_a.png | 1440x900 | A card open; all labels visible; Right trackpad wraps to two lines and overlaps Right stick. |
| after-geometry-1024x768-card-closed.png | 1024x768 | Defect A overlaps with the card closed. |
| after-geometry-1024x768-card-open-btn_a.png | 1024x768 | Card below the picture, pane at top; same two overlaps. |

PNG rig error, disclosed: the first card-element PNGs at 1440x900 were half blank because the editor pane clips the element; re-taken at a 1440x1800 viewport (named `-card`). The 1440x900 page PNGs show only the top of long cards because the pane scrolls; that is the real view, not a clipped image.

## Step 4 - mutations (each RED, restore, GREEN)

`python3 docs/sdview-gate/scripts/mutate.py <run root> /tmp/sdview-gate/mut /tmp/sdview-gate/mutations.json` -> exit 0. Each mutation is in its own `git archive HEAD` copy; restore writes the pristine bytes back and asserts they equal `git show HEAD:<file>` before the GREEN run. Logs: `/tmp/sdview-gate/mut/<id>-red.log`, `-green.log`; summary [mutations.json](evidence/mutations.json).

| Id | Mutation | Command | RED exit and named failure | Restored = HEAD blob | GREEN exit |
| --- | --- | --- | --- | --- | ---: |
| a | remove `BTN_A_LAYER_2` from btn_a layer_2 in controller_map.json | `python -B -m unittest -v tests.test_controller_map` | 1: `FAIL: test_every_catalog_action_appears_exactly_once` (also `test_control_schema_and_anchors (control='btn_a')`) | yes | 0 |
| b | edit_mapping: `guard_conflicts(); active.write_text(content)` instead of `_write_preset` (PUT/DELETE/macro skip load_midi_map validation) | `python -B -m unittest -v tests.test_controller_routes` | 1: `FAIL: test_bad_specs_return_parser_error_and_preserve_bytes_even_when_forced`, `test_bad_ids_sections_and_json_leave_bytes_unchanged` (`200 != 400`) | yes | 0 |
| c | drill-in Clear mapping no longer calls `commit(action, null)` | `node tests/ui_controller_check.cjs` | 1: `AssertionError [ERR_ASSERTION]: Clear commits null` | yes | 0 |
| d | delete the `DELETE /api/mappings/<action_id>` row from docs/api.md | `python -B -m unittest -v tests.test_ui_server.BridgeSettingsApiTests.test_api_inventory_matches_registered_method_paths` | 1: `AssertionError: Items in the second set but not the first` | yes | 0 |
| e (node) | default sub-view List when no preference stored | `node tests/ui_controller_check.cjs` | 1: `AssertionError [ERR_ASSERTION]: Controller is the default front door` | yes | 0 |
| e (browser) | same mutation served by a real bridge from the mutant copy (ports 17794/47794) | `node ui_gate.cjs frontdoor 17794 <mutant>` | 1: `FAIL a.1440x900.opens-on-controller {"controllerVisible":false,"listHidden":false,"pressed":"false"}` | yes (restored in place, same bridge) | 0; bridge SIGTERM, pid gone |

## Step 5 - bar 1 and bar 2

### Bar 1 - A/B MIDI instrument at HEAD (README commands, `--speed 1`, `--clock script`)

Mac: [mac-matrix.sh](evidence/ps/mac-matrix.sh) (`deck_script.py` exit 0, then 3 concurrent `ab_run.py --candidate b38ffb23... --preset <fixture> [--section windows] --script /tmp/sdview-gate/ab/deck-script.json --scratch ... --out ...`, all exit 0).
Laptop: [winmatrix.ps1](evidence/ps/winmatrix.ps1) (sdwin gate's driver with the vg paths and the three Windows-installed fixtures; `GEN exit=0` script document f6611e7e..., 732 steps, 47039 packets; three concurrent runs, `EXIT code=0` each).
Tables recomputed from the raw capture records by the sdwin gate's `docs/sdwin-gate/evidence/table.py` (`raw` = A and candidate `(step, bytes)` lists equal and non-empty): [bar1-mac-table.jsonl](evidence/bar1-mac-table.jsonl), [bar1-windows-table.jsonl](evidence/bar1-windows-table.jsonl).

| Preset (fixture) | OS | Arm pair | Steps | Exercised/total | Msgs A/B | Identical (summary / raw) | Candidate digest | 60 Hz min ns | pids gone |
| --- | --- | --- | ---: | ---: | ---: | --- | --- | ---: | --- |
| mac EDM Show (sectioned) | Mac | A v0.4.9 / B1 flat | 732 | 56/56 | 1531/1531 | yes / yes | 8d72c54f636e | 16681292 | yes |
| mac EDM Show (sectioned) | Mac | A / B2 --preset-section windows | 732 | 56/56 | 1531/1531 | yes / yes | 8d72c54f636e | 16680750 | yes |
| mac PTZ (sectioned) | Mac | A / B1 flat | 732 | 52/52 | 1395/1395 | yes / yes | d4bdd41f4449 | 16681667 | yes |
| mac PTZ (sectioned) | Mac | A / B2 --preset-section windows | 732 | 52/52 | 1395/1395 | yes / yes | d4bdd41f4449 | 16681500 | yes |
| mac default | Mac | A / B1 | 732 | 56/56 | 1531/1531 | yes / yes | 8d72c54f636e | 16675125 | yes |
| windows-installed EDM Show | Windows | A / B1 | 732 | 56/56 | 1531/1531 | yes / yes | 8d72c54f636e | 16771800 | yes |
| windows-installed PTZ | Windows | A / B1 | 732 | 52/52 | 1395/1395 | yes / yes | d4bdd41f4449 | 16776200 | yes |
| windows-installed default | Windows | A / B1 | 732 | 56/56 | 1531/1531 | yes / yes | 8d72c54f636e | 16776900 | yes |

Every run: `passed: true`, error null, candidate commit b38ffb2, A commit e66ff44, sent packet stream c06cfa67469f, no_overspeed true, replay wall 470.3-470.5 s; Mac clock mach_absolute_time(), Windows QueryPerformanceCounter(). The candidate digests equal the sdwin gate's (8d72c54f636e for 56-mapping presets, d4bdd41f4449 for PTZ), so the bytes are unchanged across the whole week so far. NOT COVERED (carried unchanged from docs/sdwin-gate/REPORT.md 4b): engine-dependent MIDI, since the instrument runs `--no-engines`; this lap changed no engine, receiver or win_recv code (`git diff --stat b0c5019 HEAD -- windows/engines windows/win_recv.py windows/midi.py windows/receiver.py windows/config.py deck protocol installer config mac scripts` empty). The Mac fixtures were not replayed on the laptop in this gate (the brief asked for the Windows fixtures there).

### Bar 2 - full suites at HEAD b38ffb2

| Host | Command | Ran | Result | Exit |
| --- | --- | --- | --- | ---: |
| Mac | step 1 command | Ran 865 tests in 9.695s | OK (skipped=2) | 0 |
| Windows clone | [suite.ps1](evidence/ps/suite.ps1): `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"` with PYSTRAY_BACKEND=dummy, no-op BROWSER | Ran 865 tests in 28.385s | OK (skipped=5) | 0 |

Windows launcher pid 285128 and child 282872 gone=True; PYTHON_PROCESSES_AFTER 0 ([laptop-4-suite.txt](evidence/laptop-4-suite.txt)).

### Laptop sequence and hard rules

Driver [laptop.sh](evidence/ps/laptop.sh); step log [laptop-STEPS.txt](evidence/laptop-STEPS.txt) (its echo lines render `\U`/`\v`/`\b` in the Windows paths as escapes; the arguments passed were the literal `C:\Users\Ben\AppData\Local\Temp\sdwin\vg\...` paths, as the guard's own output confirms).

| # | Laptop act (all via scripts/showready/win_rail.sh, tag vg) | Exit | Result |
| --- | --- | ---: | --- |
| 0 | `win_guard.ps1 -Mode snapshot -Out sdwin\vg\before.json` (FIRST act) | 0 | `GUARD GREEN: snapshot; protected state observed; pythonProcesses=0` |
| 1 | inventory.ps1 | 0 | matching sdwin/clone processes 1 (its own cmd.exe), python machine-wide 0 |
| 2 | pins.ps1: `git -C CLONE pull --ff-only`, pins, fixture manifests | 0 | clone b0c5019 -> b38ffb2, porcelain 0, v0.4.9 peeled e66ff44; pins 7/7 OK; fixtures mac 5/5, windows-installed 11/11, total_bad=0 |
| 3 | winmatrix.ps1 | 0 | 3 runs exit 0; ports at t=62 s and t=313 s: UDP 0.0.0.0:45123 and TCP 127.0.0.1:7723 owned by pid 23640 STEAMDECK-MIDI-RECEIVER-2-Tray; arm receivers on 127.0.0.1:55055-55057 and 57825-57827; 0.0.0.0:55058-55060 are the driver sender sockets (sendto auto-bind, as sdwin found); SEEN_PIDS 18, all gone=True, PYTHON_LEFT 0 |
| 4 | suite.ps1 | 0 | bar 2 above |
| 5 | inventory.ps1 | 0 | matching 1 (own cmd.exe), python machine-wide 0 |
| 6-7 | `win_rail.sh get` of the three result .json.gz and before.json | 0 each | downloaded to /tmp/sdview-gate/laptop |
| 9 | `win_guard.ps1 -Mode compare -Baseline sdwin\vg\before.json -Out sdwin\vg\after.json` (LAST act) | 0 | `GUARD GREEN: compare; protected state observed; pythonProcesses=0` |

No process opened a real MIDI port (capture_runner denies MIDI constructors); no process used 45123 or 7723; the orphan checkout was not touched (guard orphan HEAD/status equal); nothing installed; ssh answered throughout.

## Step 6 - pick-up

| Check | Command | Result |
| --- | --- | --- |
| Every link pushed | `git -c url...insteadOf -c core.sshCommand=... ls-remote --heads origin chain/steamdeck-20260914` at gate start | b38ffb23c3d9... equals `git rev-parse HEAD` |
| Porcelain | `git status --porcelain` at gate start | empty (before the gate's docs/sdview-gate/) |
| Nothing excluded committed since BASE OF LAP | `git -c core.quotePath=false log --name-only --format= b0c5019..HEAD \| sort -u` (24 paths) then `grep -E '^\.showready/\|^config/presets/\|bridge\.local\.json\|windows_receiver_settings\.local\.json\|^config/engines/.*\.json\|^config/state/'` | grep exit 1 (no match); control `echo config/presets/EDM Show.json \| grep -E '^config/presets/'` exit 0 |
| MIDI / mapping semantics / mac untouched | `git diff b0c5019 HEAD -- windows/midi.py windows/receiver.py windows/config.py mac/ \| wc -l` | 0; no hunk to classify |
| Pinned instruments unchanged | `git diff --stat b0c5019 HEAD -- scripts/showready`; `shasum -a 256 -c scripts/showready/SHA256SUMS` | empty; 7/7 OK |
| Ben's Mac files | `shasum -a 256 "config/presets/EDM Show.json" config/presets/PTZ.json config/bridge.local.json` | 58e47bfd..., 11b37cd6..., 7476c269... all as required |
| .showready ignored | `git check-ignore -v .showready/fixtures/mac/MANIFEST.sha256` | `.gitignore:65:.showready/` |
| Mac bridges gone | see step 0 | ps exit 1, lsof exit 1, pgrep exit 1 |
| Mac A/B processes gone | `pgrep -fl "ab_run.py\|capture_runner.py"` | exit 1 |

## Findings (reported, not fixed; product code is not the gate's to change)

| # | Kind | Finding | Where it shows |
| --- | --- | --- | --- |
| 1 | PRODUCT, layout, FAILS 2a at 1024x768 | Label boxes intersect: dpad_right x left_pad and right_stick x right_pad (5.2 px vertical overlap, label height is fixed px while the picture scales, and the trackpad labels wrap). Also right_stick x right_pad at 1440x900 whenever a card is open. | 2a table, occlusion table, PNGs |
| 2 | PRODUCT, layout | 1440x900 front door, card closed: L5, Gyro, R5 are hidden under the status bar at scroll top (pane scrollHeight 818 vs clientHeight 727). Boxes are inside the viewport, so the literal 2a assertion passes. | occlusion table, after-controller-front-door.png |
| 3 | PRODUCT, usability, minor | Conflict row marks exist only while the modal is open and are blurred behind its backdrop; Cancel clears them. Only the open control's rows can be marked (SELECT is on another control). | after-conflict-modal-marked-rows.png |
| 4 | ASCII, minor, pre-existing | Drill-in macro picker shows "Encoder" plus U+2212 MINUS SIGN from config/macro_library.json (unchanged since base). Also pre-existing in index.html at base and HEAD: warning sign in the conflict modal, check mark in the Saved toast, "Saving" and "Filter actions" with U+2026 ellipsis, gamepad emoji; U+2212 in the ui_server conflict labels "(+)/(-)" for split axes. The new controller files contain no non-ASCII (`LC_ALL=C grep -n -P '[^\x00-\x7F]' windows/static/controller/*` exit 1). | c4 option list, PNGs |
| 5 | Gate's own detector, disclosed | My first 2a geometry check measured the viewport, not occlusion, and passed while three labels were hidden; I found it from the PNG and added the occlusion probe. | this report |

Real-browser behaviour the build links owed is now measured, except: clipboard was exercised with granted permissions in headless Chromium (not a user gesture in a headed browser), and native select dropdown rendering was driven through Playwright `selectOption`.
