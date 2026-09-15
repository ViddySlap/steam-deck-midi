BASE OF LAP b0c5019dd6b43f6f91b6dff78381d9576d77ac7e

# sdview V1: owned control map and editing routes

Branch: chain/steamdeck-20260914. Build link, Mac only. No laptop acts.
This implements V1 only. V2 owns original SVG and the front door; V3 owns
scoped drill-in forms. Live highlights remain the next lap, sdlive.

## Owned map

`windows/static/controller/controller_map.json` is the relation's only source.
It has schema_version 1 and view_box [0, 0, 1200, 600]. V2 can adjust anchors in
that file when drawing the original dark SVG. The lower rear-button inset and
gyro tile are placement proposals for V2, not completed artwork.

Count command: `TMPDIR=/tmp/sdview-v1 .venv/bin/python -m unittest tests.test_controller_map -v`
asserts 23 unique controls/labels, 75 catalog actions exactly once, allowed groups,
nonempty controls, finite numeric anchors, ASCII, notes and name-based groups.

| Control | Groups and Action IDs |
| --- | --- |
| A (`btn_a`) | tap: BTN_A; layer_2: BTN_A_LAYER_2 |
| B (`btn_b`) | tap: BTN_B; layer_2: BTN_B_LAYER_2 |
| X (`btn_x`) | tap: BTN_X; layer_2: BTN_X_LAYER_2 |
| Y (`btn_y`) | tap: BTN_Y; layer_2: BTN_Y_LAYER_2 |
| D-pad Up (`dpad_up`) | tap: DPAD_UP; long_press: DPAD_UP_LONG_PRESS |
| D-pad Down (`dpad_down`) | tap: DPAD_DOWN; long_press: DPAD_DOWN_LONG_PRESS |
| D-pad Left (`dpad_left`) | tap: DPAD_LEFT; long_press: DPAD_LEFT_LONG_PRESS |
| D-pad Right (`dpad_right`) | tap: DPAD_RIGHT; long_press: DPAD_RIGHT_LONG_PRESS |
| Left stick (`left_stick`) | tap: LEFT_STICK_CLICK_L3, L_STICK_UP, L_STICK_DOWN, L_STICK_LEFT, L_STICK_RIGHT; analog: L_STICK_X_AXIS, L_STICK_Y_AXIS |
| Right stick (`right_stick`) | tap: RIGHT_STICK_CLICK_R3, R_STICK_UP, R_STICK_DOWN, R_STICK_LEFT, R_STICK_RIGHT; analog: R_STICK_X_AXIS, R_STICK_Y_AXIS |
| L1 (`l1`) | tap: L1; layer_2: L1_LAYER_2 |
| R1 (`r1`) | tap: R1; layer_2: R1_LAYER_2 |
| L2 (`l2`) | tap: L2_SOFT, L2_FULL; layer_2: L2_SOFT_LAYER_2, L2_FULL_LAYER_2; analog: L_TRIGGER_PRESSURE |
| R2 (`r2`) | tap: R2_SOFT, R2_FULL; layer_2: R2_SOFT_LAYER_2, R2_FULL_LAYER_2; analog: R_TRIGGER_PRESSURE |
| L4 (`l4`) | tap: L4 |
| L5 (`l5`) | tap: L5 |
| R4 (`r4`) | tap: R4 |
| R5 (`r5`) | tap: R5 |
| START (`start`) | tap: START |
| SELECT (`select`) | tap: SELECT |
| Left trackpad (`left_pad`) | tap: L_PAD_UP, L_PAD_DOWN, L_PAD_LEFT, L_PAD_RIGHT; long_press: L_PAD_UP_LONG_PRESS, L_PAD_DOWN_LONG_PRESS, L_PAD_LEFT_LONG_PRESS, L_PAD_RIGHT_LONG_PRESS; analog: L_PAD_X_POS, L_PAD_Y_POS |
| Right trackpad (`right_pad`) | tap: R_PAD_UP, R_PAD_DOWN, R_PAD_LEFT, R_PAD_RIGHT; long_press: R_PAD_UP_LONG_PRESS, R_PAD_DOWN_LONG_PRESS, R_PAD_LEFT_LONG_PRESS, R_PAD_RIGHT_LONG_PRESS; analog: R_PAD_X_POS, R_PAD_Y_POS |
| Gyro (`gyro`) | tap: GYRO_FORWARD, GYRO_BACKWARD; analog: GYRO_PITCH, GYRO_YAW, GYRO_ROLL |

### Placement decisions (also stored on each affected control)

- `left_stick`: The stick click and four digital directions share this physical stick. Digital directions are tap actions; continuous X/Y values are analog. L3/R3 are not separate arrows.
- `right_stick`: The stick click and four digital directions share this physical stick. Digital directions are tap actions; continuous X/Y values are analog. L3/R3 are not separate arrows.
- `l2`: SOFT and FULL are two digital stages of one trigger, both under tap. Their LAYER_2 variants stay on this trigger; continuous trigger pressure is analog.
- `r2`: SOFT and FULL are two digital stages of one trigger, both under tap. Their LAYER_2 variants stay on this trigger; continuous trigger pressure is analog.
- `l4`: Rear grip button; anchor is in the rear-button inset below the front face.
- `l5`: Rear grip button; anchor is in the rear-button inset below the front face.
- `r4`: Rear grip button; anchor is in the rear-button inset below the front face.
- `r5`: Rear grip button; anchor is in the rear-button inset below the front face.
- `left_pad`: All four digital directions and their LONG_PRESS actions belong to this trackpad. X/Y_POS are continuous pad position, not stick axes. No separate pad click Action ID exists.
- `right_pad`: All four digital directions and their LONG_PRESS actions belong to this trackpad. X/Y_POS are continuous pad position, not stick axes. No separate pad click Action ID exists.
- `gyro`: FORWARD and BACKWARD name digital gyro actions, so they use tap. PITCH, YAW and ROLL carry continuous values under analog. The anchor marks a gyro tile, not a physical button.

Face LAYER_2 actions stay with the corresponding face button. L1/R1 LAYER_2
stay with their bumper. D-pad LONG_PRESS actions stay with their direction.
These names are unambiguous. Neither long press nor layer state is synthesized.

## Routes and status codes

| Method and route | Success | Refusals |
| --- | --- | --- |
| GET /api/controller-map | 200, JSON read directly from owned file | File is a packaged asset |
| GET /api/controller-map/<control_id>?section=name | 200, control fields and grouped rows {action_id, mapping, source}, section metadata | 404 unknown control; 422 invalid selection/preset; 500 filesystem error |
| PUT /api/mappings/<action_id>?section=name | 200, stored mapping and effective mapping | 404 unknown action; 422 section selection; 400 bad spec/parser error; 409 conflicts; 500 write failure |
| DELETE /api/mappings/<action_id>?section=name | 200, mapping null, effective shared fallback or null; repeat succeeds | Same errors as PUT; force=1 accepts conflicts exposed by clear |
| POST /api/macros/<macro_id>/apply | 200, body {action_id, section}, page-compatible merge | 400 malformed body/library/parser error; 404 unknown macro/action; 409 incompatible type or conflicts; 422 section selection; 500 write failure |

`force=1` on every write accepts conflicts, never parser failure. The conflict
list is from `_detect_conflicts` on the resulting effective section, including
shared values. Validation happens before conflict checking and atomic replace.
All writes use `_write_preset`, validate every section through `load_midi_map`,
preserve shared/sibling bytes, and retain section macro/analog/engine settings.
No receiver/MIDI/parser semantics or pinned show-ready instruments changed.

Omitted section uses this machine; explicit section selects that section, just
like existing mappings/save. Flat presets remain flat and accept any safe
selection, including null. A row source is section/shared/flat/null. Read and
write responses retain raw specs (including absent default fields) because
`loadAll` uses raw mappings, not `_mapping_to_dict`'s expanded defaults.

## Page versus server behavior

- `windows/static/index.html:874` loadAll reads effective mappings, document and
  shared_mappings; the new control GET uses the same selection and raw specs.
- `windows/static/index.html:1925` doSave preserves shared defaults unless a
  mapping is already section-owned or the edited spec differs. Per-action
  writes retain that ownership behavior. Clear removes the override and reveals
  any shared mapping; shared cannot be suppressed by the preset format. Neither
  UI nor API silently deletes the shared source. Matching JSON comparison also
  preserves parser rejection of a float supplied for an integer field.
- `windows/static/index.html:1597` macroCompatible requires unmapped or same
  type. The page's apply function itself can replace an incompatible type if
  called directly, but the UI disables that action. The route enforces the UI
  compatibility rule with 409.
- `windows/static/index.html:1651` applyMacroToSelected copies current target
  fields or DEFAULTS, then replaces gesture/step/channels/refresh list and
  removes absent optional timing fields. Server mirrors this, including omitted
  staged channels (JS undefined disappears on JSON serialization). The new Node
  check executes those actual page functions and doSave against API disk writes.
- New per-action bad specs return the requested 400, while existing /api/save
  keeps its 422 behavior. Existing save relies on the separate UI conflict
  request; new routes guard their own writes and expose force=1.
- New per-action writes add a server-owned revision to the existing applied
  reload counter, immediately notifying clean/dirty pages through the unchanged
  poll. This revision is disk-write evidence, not proof the receiver has applied
  a reload. Receiver reload observations still increment the same polled integer.

No product JavaScript was moved. The existing API literal/HTML detector and
existing test assertions are unchanged. A future static JS extraction must
extend the detector to scan all static files and prove that extension bites.

## Executed verification

All test writes use temporary config trees under /tmp/sdview-v1 via TMPDIR.
The full Mac suite's isolated socket/mocked MIDI tests do not open a real port.

| Command | Executed result |
| --- | --- |
| TMPDIR=/tmp/sdview-v1 .venv/bin/python -m unittest discover -s tests -p 'test_*.py' | Ran 863 tests in 11.985s; OK (skipped=2); exit 0 |
| /opt/homebrew/bin/node tests/ui_reload_check.cjs | PASS: timer, clean editor/engines, dirty notice, explicit reload, in-flight edits, retry |
| /opt/homebrew/bin/node tests/ui_sections_check.cjs | PASS: selection, dirty guard, engine refresh, remote save, shared inheritance, CRUD calls |
| TMPDIR=/tmp/sdview-v1 /opt/homebrew/bin/node tests/ui_controller_macro_check.cjs | 48 disk writes match actual page Save; 72 incompatible writes refuse with unchanged bytes; exit 0 |
| TMPDIR=/tmp/sdview-v1 .venv/bin/python docs/sdview-v1/check_mutations.py /tmp/sdview-v1/mutations | Pristine GREEN, 12 planted faults RED (assertion failures, exit 1), 12 restored GREEN (exit 0) |
| git diff --check | Exit 0 |

New route tests assert persisted specs for all seven types, raw bad-spec parser
messages and identical bytes, shared/sibling byte retention, remote sections,
flat presets, clear twice, fallback ownership, conflicts and force on PUT/DELETE/
macro apply, reload events and revision, all-section validation, failed replace
cleanup, source map GET and every drill-in row against real file contents.

The suite skips two existing tests: anticipated global-color channel-CC remap
(`tests/test_global_color.py:371`) and PowerShell guard execution without pwsh
(`tests/test_showready_rail.py:108`). Neither skip is new. Mac log:
`/tmp/sdview-v1/mac-suite.log`. Mutation evidence:
`/tmp/sdview-v1/mutations/proof-ivgja8mi/results.json`.

### Planted faults and restoration

The committed `docs/sdview-v1/check_mutations.py` copies windows/tests plus the
catalog and API document into scratch. It runs actual unittest selectors in
those copies with -B, so same-second bytecode cannot mask a source mutation.
The first attempt exposed that Python bytecode cache issue in the proof script;
-B fixed the instrument, and the full matrix then passed. No product tree was
mutated by fault proofs.

| Planted fault | Named assertion that fails |
| --- | --- |
| Extra SCRATCH_NEW_ACTION in scratch actions.yaml | every_catalog_action_appears_exactly_once |
| Duplicate BTN_A in scratch map | every_catalog_action_appears_exactly_once |
| LAYER_2 moved to long_press | groups_follow_action_names |
| Remove controller-map route table row | api_inventory_matches_registered_method_paths |
| Skip loader validation | bad_specs_return_parser_error_and_preserve_bytes_even_when_forced |
| Skip conflict guard | conflict_409_and_force_200_include_shared_mappings |
| Ignore force=1 | conflict_409_and_force_200_include_shared_mappings |
| Skip atomic disk replacement | put_all_mapping_types_flat_and_sectioned |
| Skip revision increment | version_keeps_receiver_reload_observations |
| Skip deletion | delete_twice_and_shared_fallback_flat_and_sectioned |
| Macro overwrites current target with defaults | macro_cc_and_staged_merge_preserve_targets_remove_optional_overrides |
| Macro accepts incompatible type | macro_incompatible_unknown_action_invalid_section_and_parser_error |

## Bar 1 MIDI replay

The pinned sdwin README command is run against the implementation HEAD, with
only script/output/scratch paths relocated to the required /tmp/sdview-v1 root.
The script command is:

```
.venv/bin/python -B scripts/showready/deck_script.py --out /tmp/sdview-v1/deck-script.json
```

It produced script_sha256
9256621abf62eb21e6c345ef286b6b7fcc087a2db87b8f682ce7fcf7703a993e,
732 steps, 47039 packets, scripted duration 469.716666743 seconds.
Replay command (exit 0):

```
TMPDIR=/tmp/sdview-v1 .venv/bin/python -B scripts/showready/ab_run.py --candidate HEAD --preset '.showready/fixtures/mac/presets/EDM Show.json' --section windows --script /tmp/sdview-v1/deck-script.json --scratch /tmp/sdview-v1/ab --out /tmp/sdview-v1/mac-edm.json
```

Verbatim instrument verdict line:

```json
{"result": "/tmp/sdview-v1/mac-edm.json.gz", "passed": true, "error": null, "comparisons": {"B1": {"totals": {"steps": 732, "mappings": 56, "mappings_exercised": 56, "messages_A": 1531, "messages_B": 1531}, "different_mappings": [], "unexercised_mappings": []}, "B2": {"totals": {"steps": 732, "mappings": 56, "mappings_exercised": 56, "messages_A": 1531, "messages_B": 1531}, "different_mappings": [], "unexercised_mappings": []}}}
```

Both candidate arms archive implementation commit
`ad94d3a53b003f43609f54401f0e7b6ed6379a05`; A archives v0.4.9.
The final evidence-only commit changes this report and adds midi-verdict.json,
with no implementation changes. Machine-readable coverage, hashes, pacing,
non-default ports, process IDs and cleanup proof are in
`docs/sdview-v1/midi-verdict.json`. Full timestamped captures and script:
`/tmp/sdview-v1/mac-edm.json.gz` (SHA256
98bd9120035e4d2aa9e99711460383895df6ed782e7237786e4b9a80f9712f87).

The driver's cleanup reports pid_gone=true for A, B1 and B2 after wait and
kill(pid,0). `/tmp/sdview-v1/finish_evidence.py` independently repeated kill(pid,0)
after completion and observed ProcessLookupError for every recorded PID.
This is the pinned synthetic-input, controlled-clock byte-regression instrument
with real loopback UDP and stub MIDI. It is not Windows or real-hardware show
readiness. The full show-ready bar remains owed to the gate/judge.


## Handoff to V2/V3 and the gate

- Consume controller_map.json or GET /api/controller-map; never duplicate the
  relation or anchor coordinates. Existing forms remain in index.html; scope
  their global field IDs when reusing them across rows.
- Controller GET groups contain row objects, while map GET groups contain IDs.
  Use source plus mapping to expose shared ownership and clear fallback.
- Writes persist immediately. Draft-based forms must still preserve the existing
  dirty/hot-reload behavior and call the write routes on the chosen save action.
  A 409 has conflicts and can be retried with force=1; incompatible macros remain
  refused even with force. Section choice is independent of bridge identity.
- OWED TO THE GATE: real browser rendering/interaction and full Windows suite.
  Node VM checks are not browser proof. Windows suite and Windows MIDI behavior
  are UNVERIFIED-BY-EXECUTION in V1; build links do not touch the laptop.
- No SVG/editor/live visuals were built in V1. The next lap owns all live behavior.
