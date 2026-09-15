# sdview V2: Controller picture and read-only drill-in

V2 BASE: 85b3032fa4244baa04456dd69d6ed289dd91fe2b, from `git rev-parse HEAD`
at entry. V1 records BASE OF LAP b0c5019dd6b43f6f91b6dff78381d9576d77ac7e.
Branch: chain/steamdeck-20260914. Build link, Mac only; no laptop acts.
GET http://127.0.0.1:8899/launches/sdview-q001.V1 returned state done and
commit 85b3032fa4244baa04456dd69d6ed289dd91fe2b. Saved read receipt:
/tmp/sdview-v2/predecessor.json.

## Delivered behavior and file layout

- `windows/static/controller/steam_deck.svg`: original geometric SVG, drawn
  directly for this item. No external artwork, logo, tracing or embedded image.
  Body and screen, front controls, top-edge triggers/bumpers, rear grip insets
  and gyro tile use the existing page CSS variables.
- `windows/static/controller/controller_map.json`: still the only owned
  control-to-Action-ID relation. Existing controls, groups, order and anchors
  are unchanged. Added label_anchor coordinates and scene_view_box so callouts
  also have an owned position, without a parallel table in JavaScript.
- `windows/static/controller/controller_view.js`: static SVG fetch/import,
  map-driven arrows and native button labels, browser preference, selection,
  read-only card and refresh. The SVG is imported into the page so its CSS
  variables inherit and the next lap can address its data-control shapes.
- `windows/static/controller/controller_view.css`: controller layout and theme,
  label focus/selection, unmapped dimming and card rows. The card moves below
  the picture on narrow windows; the picture can scroll horizontally there.
- `windows/static/index.html`: Controller/List switch, picture/card containers,
  external assets and small boot/load/commit/tab hooks. The original sidebar
  and editor DOM and edit/save functions remain in place. Macro Library retains
  the sidebar for its original target-selection behavior. The shared badge and
  description helpers use ASCII punctuation in both views, per the lap rule.
- `tests/ui_controller_check.cjs`: executes both shipped scripts in document
  order with a fake DOM and controlled HTTP. No product rendering functions
  are replaced. This does not claim real browser layout or native key dispatch.
- `tests/test_ui_node.py`: runs all ui_*_check.cjs files using node, including
  V1's macro parity check. Only missing node causes NODE-ABSENT skip; failures
  and timeouts fail. The child parity check uses the suite's Python interpreter.
- `tests/test_ui_server.py`: extends the existing API literal detector to every
  static file, including nested assets. A permanent test runs that actual
  detector with a clean scratch tree, a planted unknown JS route and restoration.
- `docs/api.md`: describes the navigation, draft behavior and existing HTTP
  equivalents. No routes added or removed; V1's routes cover saved inspection.

External JS/CSS keep controller code bounded and leave the large inline editor
intact. The two pre-existing node checks still load only the inline script:
optional integration hooks let those checks run unchanged. The new node check
loads the real external script as well, proving the integration independently.
The external API literal is covered by the extended static-file detector.

Controller is the default; the browser remembers an explicit List choice.
Labels show mapped/total Action IDs from the selected section's in-memory state.
A label, arrow or shape opens the card; native buttons supply Enter/Space
activation. Close/Escape closes the card and returns focus to its label.
Rows appear in TAP, LONG PRESS, LAYER 2, ANALOG order, only for present groups,
with map-ordered Action IDs. Every row calls the original mappingBadge,
mappingBadgeClass and mappingDesc helpers. Open in list mounts the existing
editor for that action. Commit and accepted loadAll results refresh the card
and counts; dirty hot reloads retain the draft and the existing notice.

## SVG shape inventory

`/opt/homebrew/bin/node tests/ui_controller_check.cjs` observed 23 visible arrows,
23 labels, and these 23 distinct artwork data-control shapes, exactly equal to
the owned map's control IDs:

- Face circles: btn_a, btn_b, btn_x, btn_y.
- D-pad direction paths: dpad_up, dpad_down, dpad_left, dpad_right.
- Stick circles, including clicks: left_stick, right_stick.
- Top-edge bumpers/triggers: l1, r1, l2, r2.
- Rear grip buttons: l4, l5, r4, r5.
- Menu circles: start, select.
- Trackpad rectangles: left_pad, right_pad.
- Gyro tile: gyro.

Each control has one visible leader with an arrowhead. A wider transparent
stroke provides its pointer target; it is not a second visible arrow. Scene
and label endpoints come from the map; no Action IDs are embedded in the SVG.
Selection styling is editor selection only. No live-input highlights, stick
dots, trigger bars, MIDI flash or follow mode are implemented.

## Executed checks

All temporary config writes used /tmp/sdview-v2 through TMPDIR. No bridge was
started for the view checks. Full-suite receiver/MIDI tests use their existing
isolated fixtures. No Ben preset, show-ready instrument, receiver MIDI code,
parser rule or mac/ file was changed. Existing test assertions were preserved;
tests/ui_reload_check.cjs and tests/ui_sections_check.cjs were not edited.

| Command | Executed result |
| --- | --- |
| TMPDIR=/tmp/sdview-v2 .venv/bin/python -m unittest discover -s tests -p 'test_*.py' | Ran 865 tests in 11.097s; OK (skipped=2); exit 0. /tmp/sdview-v2/mac-suite.log |
| TMPDIR=/tmp/sdview-v2 /opt/homebrew/bin/node tests/ui_controller_check.cjs | Exit 0: arrows/anchors/shapes; default and switch; storage restore/denial; card groups/order; all mapping types and clear; List handoff; commits; section counts; clean/dirty reload; close/Escape; dynamic IDs; asset-failure fallback |
| TMPDIR=/tmp/sdview-v2 /opt/homebrew/bin/node tests/ui_reload_check.cjs | Exit 0: timer, clean editor/engines, dirty notice, explicit reload, in-flight edits, retry |
| TMPDIR=/tmp/sdview-v2 /opt/homebrew/bin/node tests/ui_sections_check.cjs | Exit 0: selection, dirty guard, engine refresh, remote save, shared inheritance, CRUD calls |
| TMPDIR=/tmp/sdview-v2 /opt/homebrew/bin/node tests/ui_controller_macro_check.cjs | Exit 0: 48 disk writes match actual page Save; 72 incompatible writes refused without byte changes |
| TMPDIR=/tmp/sdview-v2 .venv/bin/python docs/sdview-v2/check_mutations.py /tmp/sdview-v2/mutations | Exit 0: pristine GREEN, seven planted faults RED, seven restored GREEN. Committed mutation-results.json records exact commands, exits and log paths |
| git diff --check | Exit 0 |

The suite's existing skips are the anticipated global-color channel-CC remap
and PowerShell guard execution without pwsh. No new skip occurred. Node logs
are /tmp/sdview-v2/ui_<name>_check.cjs.log.

## Revert and detector proof

The committed check_mutations.py copies windows/tests plus the catalog and API
document into scratch. It mutates only those copies, executes the shipped
checks, requires a named assertion failure/nonzero exit, and restores source
before requiring exit 0. Python uses -B to exclude stale bytecode effects.

| Planted fault | Observed failed assertion |
| --- | --- |
| Remove commit's ControllerView.refresh hook | Open row retains previous mapping description when commit changes its spec |
| Remove loadAll's refresh hook | Initial selected-section count stays 0/5 instead of 2/5 |
| Default to List with absent browser preference | Controller is the default front door |
| Omit L2's visible arrow | Exactly 23 visible arrows |
| Remove label click handler | Click does not open the drill-in card |
| Remove L2's artwork data-control identity | Artwork cannot mount and visible-arrow count is not 23 |
| Add /api/sdview-planted-missing-route to a nested scratch static JS file | HTML API path has no registered route |

The first proof run stopped because its expected load-refresh failure text
named the later section-switch assertion. The detector had already failed on
the earlier initial count (0/5 versus 2/5). Named that assertion, corrected the
proof's expected failure, and reran the entire matrix successfully. No product
behavior or assertion was weakened. Final evidence is under
/tmp/sdview-v2/mutations/proof-dj9mpy2b/ and in mutation-results.json.

## Handoff to V3 and the gate

V3 can mount forms inside .controller-row, keyed by data-action. Group containers
have data-group; artwork shapes have data-control. ControllerView owns init,
refresh and tabChanged. The shared page state remains authoritative for drafts.
Current refresh replaces card rows: V3 must account for unapplied form input
before rebuilding rows and scope all form IDs. Reuse existing renderFields and
readFields logic, including the existing axis forms. Preserve the current dirty
and conflict-save guards. Keep the owned map as the only relation.

OWED TO THE GATE: a real browser at 1440x900 must verify the picture/card layout,
legible labels with no overlaps, visible arrow/shape click targets, native Tab
and Enter activation, focus visibility, Escape closing/focus return, List
handoff and responsive card placement. Node VM tests exercise handlers and DOM
state only. These browser observations are UNVERIFIED-BY-EXECUTION in V2.

OWED TO THE GATE/JUDGE: the full Windows suite and the pinned Windows MIDI A/B
show-ready bar, exactly as scripts/showready/README.md defines them. Windows,
real hardware and MIDI A/B replay are UNVERIFIED-BY-EXECUTION in V2. This build
link did not touch the laptop or change either pinned instrument.
