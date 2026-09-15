GUARD GREEN at the gate's LAST laptop act (`win_guard.ps1 -Mode compare -Baseline sdwin\ug3\before.json` exit 0, "GUARD GREEN: compare; protected state observed; pythonProcesses=0", 23:10:36). All three guarded laptop passes (ug, ug2, ug3) had a GREEN snapshot first and a GREEN compare last.

# sdfix GATE (UG) - independent real-browser measurement of U1

Gate: claude-rc on the Mac, unsandboxed. Branch `chain/steamdeck-20260914`.
BASE OF LAP `d67a13439028cfc983b34636e82d3de7282eab2a` (first line of docs/sdfix-u1/REPORT.md).
Gate HEAD at entry `19cd48e0dd6e8d36126812c5e687504928e4fcbd` (U1's final commit; porcelain empty; `git ls-remote --heads origin chain/steamdeck-20260914` = 19cd48e). Every measurement below is of 19cd48e. This gate's own commit adds only docs/sdfix-gate/.
U1 envelope: `curl -s http://127.0.0.1:8899/launches/sdfix-q001.U1` -> state done, status complete.
Scratch: `/tmp/sdfix-gate/` on the Mac; `C:\Users\Ben\AppData\Local\Temp\sdwin\ug`, `ug2`, `ug3` on the laptop.
Gate scripts (share no code with U1's check): [scripts/](scripts/) `bridge.py`, `geom_gate.cjs`, `mutate.py`, `controls_gate.cjs`, `arrangement.py`, `leader_clearance.py`, `leader_over_shapes.py`, `bar1_table.py`. Laptop drivers: [evidence/ps/](evidence/ps/).

Verdict in one line: the ACCEPTANCE GEOMETRY holds at every size and card state on two independent detectors, every control still works and saves exactly, the conflict marks now persist (C), bar 1 is byte-identical on both OSes; BUT bar 2 went RED once on Windows from a PRE-EXISTING flaky deck API test (not this lap's code), and two readability defects remain that the acceptance rule does not measure (L1/R1 leaders cut through the L2/R2 shapes everywhere; at 1024x768 with the card open the L1 line runs over the L2 arrowhead).

## For Ben

1. **The picture is fixed for what was reported.** No label overlaps, no crossing lines, every arrow stops at its own control's edge, no arrowhead covers L3/R3/A/B/X/Y/GYRO, and L5/Gyro/R5 are visible without scrolling. Measured, not eyeballed, at 1024x768, 1366x768, 1440x900 and 1920x1080 with the card closed and open. Screenshots: `screenshots/sdfix-gate/after-*.png` (and `before-1440x900-card-closed.png` for comparison).
2. **The controls still work.** All 23 labels open their own card with the right actions, an edit plus Save writes exactly one value to the preset, and a MIDI CC conflict now stays marked on the rows after you close the warning, until a Save succeeds.
3. **Friday MIDI is unchanged.** EDM Show, PTZ and default send the same bytes as v0.4.9 on the Mac and on the laptop.
4. **One thing to know about the laptop test suite.** Its first run had 1 error in a Deck control API test (a connection reset on Windows). That test and its code have not changed since before this week's show-ready work; a second full run was green, and repeated alone it failed 80 times in 300. It does not touch the receiver or MIDI. The master decides what bar 2 means here.
5. **Two small picture issues are still there** (not in the fix list): the L1 and R1 arrows pass through the L2 and R2 shapes on their way in, and on a 1024x768 screen with a card open the L1 line touches the L2 arrowhead (the same on the right side). The 1024x768 card is also a short drawer (about 170 px) that needs scrolling. The shape arrangement question stays with the master.

## Step 1 - Mac suite, node checks, pins at HEAD 19cd48e

| Command | Exit | Result |
| --- | ---: | --- |
| `TMPDIR=/tmp/sdfix-gate/mactmp PYSTRAY_BACKEND=dummy BROWSER=/usr/bin/true .venv/bin/python -m unittest discover -s tests -p "test_*.py"` | 0 | `Ran 866 tests in 9.631s` / `OK (skipped=2)` ([log](evidence/mac-suite.log)) |
| `TMPDIR=/tmp/sdfix-gate/mactmp node tests/ui_controller_check.cjs` | 0 | `UI controller behavior: PASS (23 arrows, ...)` |
| `TMPDIR=/tmp/sdfix-gate/mactmp node tests/ui_controller_macro_check.cjs` | 0 | `48 disk writes match page Save; 72 incompatible writes refused without byte changes` |
| `TMPDIR=/tmp/sdfix-gate/mactmp node tests/ui_reload_check.cjs` | 0 | `UI reload behavior: PASS` |
| `TMPDIR=/tmp/sdfix-gate/mactmp node tests/ui_sections_check.cjs` | 0 | `UI section behavior: PASS` |
| `shasum -a 256 -c scripts/showready/SHA256SUMS` | 0 | 10/10 OK ([log](evidence/shasums.log)) |

tests/ui_controller_geometry.cjs is the fifth .cjs under tests/; it needs a URL and a browser and is run in step 2 (it is deliberately outside unittest, per the README).

## Step 2 - geometry in real Chromium

Chromium: `/Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell`, playwright-core 1.58.2 from life-os-showday/web-ui-server. Default launch WORKS for this unsandboxed gate (U1's sandbox needed --single-process); both modes were run.

### 2a - U1's wrapper, exactly as the README says

| Command | Exit | Result |
| --- | ---: | --- |
| `scripts/showready/ui_geometry.sh --chromium '<path>' --scratch /tmp/sdfix-gate/geometry --single-process --mutations` | 0 | pristine `SUMMARY 1048/1048 PASS`; m1 `77/79` RED; m2 `77/79` RED; m3 `76/79` RED; each restored `1048/1048`; `PASS bridge PID 7747 gone=True` ([log](evidence/geom-readme.log), [receipt](evidence/u1-wrapper-receipt.json)) |
| same without `--single-process --mutations`, `--scratch /tmp/sdfix-gate/geom-default` (default launch) | 0 | `SUMMARY 1048/1048 PASS`; `bridge PID 6988 gone=True` ([log](evidence/geom-default-launch.log)) |

Wrapper settings from the receipt: `git ls-files` tracked working bytes + verified Mac fixture copies, `.active` EDM Show, PYSTRAY_BACKEND=dummy, BROWSER=/usr/bin/true, `--dry-run --no-engines --no-pulse --no-osc-relay`, TCP 17841 / UDP 47841 bound free first.

U1 check table (per-state counts tallied from evidence/geom-readme.log PASS/FAIL lines; 23 own-edge + 23 glyph-clear + 23 leader-visible per state; drill 23 per viewport):

| Viewport | Card | Label overlaps | Segment intersections | Endpoints on own edge | Glyph overlaps | Hidden / scrolled | Labels |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: |
| 1024x768 | closed | 0 | 0 | 23/23 | 0 | none / no | 23 |
| 1024x768 | open btn_a | 0 | 0 | 23/23 | 0 | none / no | 23 |
| 1024x768 | open nearest (gyro) | 0 | 0 | 23/23 | 0 | none / no | 23 |
| 1366x768 | closed | 0 | 0 | 23/23 | 0 | none / no | 23 |
| 1366x768 | open btn_a | 0 | 0 | 23/23 | 0 | none / no | 23 |
| 1366x768 | open nearest (right_pad) | 0 | 0 | 23/23 | 0 | none / no | 23 |
| 1440x900 | closed | 0 | 0 | 23/23 | 0 | none / no | 23 |
| 1440x900 | open btn_a | 0 | 0 | 23/23 | 0 | none / no | 23 |
| 1440x900 | open nearest (right_pad) | 0 | 0 | 23/23 | 0 | none / no | 23 |
| 1920x1080 | closed | 0 | 0 | 23/23 | 0 | none / no | 23 |
| 1920x1080 | open btn_a | 0 | 0 | 23/23 | 0 | none / no | 23 |
| 1920x1080 | open nearest (right_pad) | 0 | 0 | 23/23 | 0 | none / no | 23 |

Plus `drill.<id>` 23/23 at each of the 4 viewports (92/92).

### 2b - the gate's independent detector

`node docs/sdfix-gate/scripts/geom_gate.cjs http://127.0.0.1:18851 /tmp/sdfix-gate/geom-head 1440x900,1024x768,1366x768,1920x1080 --extra-open right_pad@1440x900,gyro@1024x768,right_pad@1366x768,right_pad@1920x1080 --png` -> exit 0, `GATE-GEOMETRY states=16 bad=0` ([log](evidence/geom-gate-head.log), [raw](evidence/gate-geometry-head.json)).
Bridge: `bridge.py start --tree /tmp/sdfix-gate/br-head --rev 19cd48e --ui-port 18851 --listen-port 48851` (git archive of windows/protocol/config, byte copies of the three Mac fixtures, no bridge.local.json, same safety flags), pid 75061, stopped by SIGTERM, `gone=True`.

How it measures, differently from U1: SVG leader points (polyline `points`, or `<line>` x1..y2 at BASE) are mapped to page px by hand from the scene svg's getBoundingClientRect and viewBox (preserveAspectRatio meet), not getScreenCTM. **The 3 px endpoint rule is measured against the SHAPE's own getBoundingClientRect** (the element with `data-control="<id>"` inside `svg.controller-art`), never the label box; "inside another control" means strictly inside another shape's box by more than 0.5 px. Glyph overlap tests every leader segment and every arrowhead triangle against the getBoundingClientRect of every `<text>` in the artwork. Hidden = label outside the pane (#tab-editor) or viewport, elementFromPoint at its centre not the label, or its box touching the status bar; shapes must lie inside pane and viewport. Scroll = document or pane scrollHeight > clientHeight, or any non-zero scroll offset. Nearest-to-card = smallest rectangle gap; ties are listed and the first non-A id opened, so the gate also opened U1's picks explicitly.

Side by side (U1 check | gate), the brief's required states:

| Viewport / card | Overlaps U1 / gate | Intersections U1 / gate | Own-edge U1 / gate (gate max px) | Glyph U1 / gate | Hidden+scroll U1 / gate | Agree |
| --- | --- | --- | --- | --- | --- | --- |
| 1440x900 closed | 0 / 0 | 0 / 0 | 23 / 23 (0.000) | 0 / 0 | none / none | yes |
| 1440x900 open btn_a | 0 / 0 | 0 / 0 | 23 / 23 (0.000) | 0 / 0 | none / none | yes |
| 1440x900 open right_pad | 0 / 0 | 0 / 0 | 23 / 23 (0.000) | 0 / 0 | none / none | yes |
| 1440x900 open btn_b (gate nearest) | n/a / 0 | n/a / 0 | n/a / 23 | n/a / 0 | n/a / none | - |
| 1024x768 closed | 0 / 0 | 0 / 0 | 23 / 23 (0.000) | 0 / 0 | none / none | yes |
| 1024x768 open btn_a | 0 / 0 | 0 / 0 | 23 / 23 (0.000) | 0 / 0 | none / none | yes |
| 1024x768 open gyro | 0 / 0 | 0 / 0 | 23 / 23 (0.000) | 0 / 0 | none / none | yes |
| 1024x768 open l4 (gate nearest) | n/a / 0 | n/a / 0 | n/a / 23 | n/a / 0 | n/a / none | - |

The gate also ran 1366x768 and 1920x1080 (closed, btn_a, btn_b, right_pad): all zero, 23/23, no scroll. **No disagreement.** Nearest-card choice differs (U1 breaks rectangle-gap ties by longest label; the gate by DOM order: at 1440 the tie is btn_a, btn_b, btn_x, btn_y, right_stick, right_pad at 19.00 px; at 1024 it is l4, l5, r4, r5, gyro at 12.50 px), so both picks were measured.

**The gate's detector fires** (control on BASE OF LAP d67a134, bridge pid 76268 gone=True, [log](evidence/geom-gate-base.log)): 1440x900 closed: 2 crossings (btn_b/btn_x, dpad_down/dpad_right), 0/23 endpoints (lines end at shape centres, max 35.0 px), 9 glyph hits (A, B, X, Y, L3, R3, GYRO), L5/R5/Gyro hidden under the status bar with pane overflow 91 px. 1440x900 open: right_stick/right_pad overlap. 1024x768 closed: dpad_right/left_pad and right_stick/right_pad overlap, pane overflow 32 px. These match defects A, B, E and F as reported. The m1-m3 rows below show it firing on HEAD mutants too.

## Step 3 - mutations against U1's check, planted in scratch STATIC FILES

Driver [evidence/ps/mutations.sh](evidence/ps/mutations.sh). Each mutant: `bridge.py start --tree /tmp/sdfix-gate/mut/tree-mN --rev 19cd48e --mutation mN` (git archive tree, then [mutate.py](scripts/mutate.py) edits the served controller_view.js/.css), U1's standalone check `node tests/ui_controller_geometry.cjs http://127.0.0.1:<port> <chromium> --out ...` (default launch, full 4-viewport matrix, NOT its --mutation DOM mode), the gate detector at 1440x900, stop (gone proved), restore the four controller files from `git archive 19cd48e` and prove each byte-equal to the HEAD blob, restart, re-run both.

| Mutation (static files) | U1 check RED | Named in U1 output | Gate detector | Restored bytes = HEAD | U1 check restored | Gate restored |
| --- | --- | --- | --- | --- | --- | --- |
| m1 swap btn_a/btn_b leader targets (anchor + shape box; only those two lose their via-bends) | exit 1, `SUMMARY 1012/1048` | `FAIL 1440x900.closed.own-edge.btn_a` (37.9 px, insideOther btn_b) and `...own-edge.btn_b` (17.7 px, insideOther btn_a); `leader-intersections [["btn_a","btn_b"]]`; same at every viewport | exit 1: crossings [btn_a,btn_b], endpoints 21/23 (btn_a 37.94 px, btn_b 17.70 px) | 1 | exit 0, 1048/1048 | exit 0 |
| m2 btn_b label moved 10 px below btn_a's centre | exit 1 | `FAIL 1024x768.closed.label-overlaps [["btn_a","btn_b"],["btn_b","btn_x"]]`, `labels-topmost btn_a by controller-label` | exit 1: overlaps [btn_a,btn_b], btn_a centre hit by another label | 1 | exit 0, 1048/1048 | exit 0 |
| m3 btn_a label fixed at the bottom, painted beneath the status bar | exit 1 | `FAIL 1024x768.closed.inside-visible-pane ["btn_a"]`, `labels-topmost btn_a by statusbar` | exit 1: btn_a outside pane, centre hit statusbar, overlaps status bar | 1 | exit 0, 1048/1048 | exit 0 |

Logs: [evidence/mutations/](evidence/mutations/). A first m1 variant dropped every control's via-bends (not only A/B); it was also RED (`985/1048`, plus dpad_right/right_stick endpoints inside dpad_down/btn_x) and restored GREEN, but was replaced by the surgical variant above; kept as `m1-broad-u1.log`.

FINDING (test rig, low): with a static-file m2 or m3, U1's check prints the named FAIL lines at 1024x768 closed and then dies in `page.click` (30 s timeout: the moved label cannot be clicked), so it exits 1 through its catch handler with no SUMMARY line. The RED is real (named FAILs precede it), but a crash and an assertion failure share exit 1. Not fixed (not a clear sub-20-line cause-and-fix).

Definitional note: U1 counts an endpoint lying exactly on another shape's box edge as insideOther; the gate requires strictly inside by 0.5 px. Both fail own-edge for m1; no pristine state is affected.

## Step 4 - every control still works (1440x900)

`node docs/sdfix-gate/scripts/controls_gate.cjs 18851 /tmp/sdfix-gate/br-head /tmp/sdfix-gate/controls-head` -> exit 0, `CONTROLS 33/33 PASS` ([log](evidence/controls-head.log), [results](evidence/controls/controls-results.json), [drill](evidence/controls/drill-1440x900.json)).

| Row | Result |
| --- | --- |
| 23 labels, ids equal `GET /api/controller-map` | PASS |
| Each label click opens its own card: title = label, only that label aria-expanded, rows grouped tap/long_press/layer_2/analog equal `GET /api/controller-map/<id>?section=windows` action_id lists in order | 23/23 PASS (e.g. btn_a BTN_A, BTN_A_LAYER_2; left_pad 10 ids; gyro 5 ids) |
| Edit through the drill-in: BTN_A Edit, note 36 -> 50, Apply fields, Save & Apply; parsed JSON diff of the scratch `EDM Show.json` | exactly `[sections.windows.mappings.BTN_A.note 36 -> 50]` |
| Conflict: START cc 78 -> 79, Save opens modal | modal `Ch3 CC79: START, SELECT`, START row marked |
| Cancel: modal closed (overlay display none), START row still `.controller-conflict`, message "MIDI CC conflict" uncovered at its centre (elementFromPoint) and in viewport | PASS |
| Cancel writes nothing | preset sha unchanged (b5ca30b2...) |
| Navigate to SELECT: marked and uncovered; back to START: still marked | PASS / PASS |
| Save anyway: parsed JSON diff | exactly `[sections.windows.mappings.START.cc 78 -> 79]` |
| After successful Save: 0 marked rows and 0 messages on START and SELECT | PASS (non-vacuous: both were measured marked just before) |

Control (the check fires): same script against BASE OF LAP (bridge pid 94517 gone=True, [log](evidence/controls-base-control.log)) -> exit 1, `30/33`: exactly `start-marked-and-visible-after-modal-closed`, `select-marked-on-navigation`, `start-still-marked-after-navigation` FAIL (`marked:false`), which is defect C as reported. PNGs: [conflict-after-cancel-1440x900.png](screenshots/conflict-after-cancel-1440x900.png), [conflict-after-save-1440x900.png](screenshots/conflict-after-save-1440x900.png).

## Step 5 - PNGs for Ben

Written by geom_gate.cjs to `/Users/viddyslap/Documents/ViddyVault/screenshots/sdfix-gate/` and [screenshots/](screenshots/). Opened each; crops zoomed where lines run close.

| PNG | Labels + glyphs readable | Any line crosses | Anything cut off |
| --- | --- | --- | --- |
| before-1440x900-card-closed.png (BASE d67a134) | No: arrowheads sit on L3, R3, Y, X, B, A, GYRO | Yes: B/X, D-pad Down/Right, several right-side lines tangle | Yes: L5, Gyro, R5 half under the status bar |
| after-1024x768-card-closed.png | Yes (glyphs small but clear) | No | No (header wraps: F4, sdauto's) |
| after-1024x768-card-open.png | Yes, glyphs very small (eyeballed, not measured) | No crossing, but the L1 line runs over the L2 arrowhead (and R1 over R2) | No; the card is a 170 px drawer showing title, tabs and the TAP heading, rows scroll inside it |
| after-1366x768-card-closed.png | Yes | No | No |
| after-1366x768-card-open.png | Yes | No; X's elbow (705.4, 442.8) sits 5.5 px above the Right stick bend (705.4, 448.3) at the same x (raw points, evidence/gate-geometry-head.json), reads as a near-junction when zoomed | No |
| after-1440x900-card-closed.png | Yes | No (L1 line passes through the L2 shape, R1 through R2) | No |
| after-1440x900-card-open.png | Yes | No | No |
| after-1920x1080-card-closed.png | Yes | No (L1 through L2, R1 through R2 visible) | No |
| after-1920x1080-card-open.png | Yes | No | No |

**Arrangement unchanged from BASE OF LAP**: `python3 docs/sdfix-gate/scripts/arrangement.py <base 1440x900 closed> <head 1440x900 closed>` -> exit 0 `ARRANGEMENT UNCHANGED` ([json](evidence/arrangement.json)): 23 = 23 same ids; art root box 830.7x421.6 -> 911.0x462.4, scale x 1.096686 = y 1.096686 (uniform); after dividing by that one scale every shape box edge relative to the SVG art root is within 0.00015 px of BASE; getBBox() in SVG user units equal for all 23. Control: the same comparison with btn_a's box moved 5 px -> exit 1 `ARRANGEMENT CHANGED`. `git diff d67a134 HEAD -- windows/static/controller/steam_deck.svg` is empty.

### Beyond the acceptance rule (measured, reported, not fixed)

[leader_over_shapes.py](scripts/leader_over_shapes.py) on the gate's raw geometry ([head](evidence/leader-over-shapes-head.txt), [base control](evidence/leader-over-shapes-base.txt)); [leader_clearance.py](scripts/leader_clearance.py) ([txt](evidence/leader-clearance.txt)):

- FINDING (layout, medium): at all 16 measured states the L1 leader (or its head) crosses the L2 shape box and R1 crosses R2 (1 px inset). BASE had 7 such pairs; HEAD has these 2.
- FINDING (layout, medium, 1024x768 card open only, all three open states): the L1 line passes 1.17 px from a vertex of L2's arrowhead and 1.50 px from the L2 leader (R1/R2 mirrored). Leaders are 2 px strokes, so they paint touching; visible when after-1024x768-card-open.png is zoomed at x 270-420, y 225-305. The acceptance rule passes this because the segments do not mathematically intersect and L2 has no text glyph.
- Closest approach otherwise: dpad_right/left_pad 3.8-3.9 px at 1024 closed and 1366 open; btn_x/right_stick 4.2 px (1024 open) to 11.7 px (1920 closed).
- Card drawer at 1024x768 is 170 px (CSS `grid-template-rows: minmax(300px, 1fr) 170px`); usability note, not a geometry fault.

## Step 6 - bars 1 and 2

### Bar 1 - A/B MIDI at candidate 19cd48e

Mac: [mac-matrix.sh](evidence/ps/mac-matrix.sh): `deck_script.py --out /tmp/sdfix-gate/ab/deck-script.json` exit 0, then 3 concurrent `ab_run.py --candidate 19cd48e0dd6e8d36126812c5e687504928e4fcbd --preset <fixture> [--section windows] --script /tmp/sdfix-gate/ab/deck-script.json --scratch ... --out ...`; EXITS: script 0, default 0, ptz 0, edm 0.
Laptop: [winmatrix.ps1](evidence/ps/winmatrix.ps1) in the clone at 19cd48e (`GEN exit=0` script f6611e7e..., 732 steps, 47039 packets); three concurrent runs, `EXIT code=0` each; ports at t=62 s and t=313 s: UDP 0.0.0.0:45123 and TCP 127.0.0.1:7723 owned only by pid 23640 STEAMDECK-MIDI-RECEIVER-2-Tray, arms on 127.0.0.1:49519-49521 / 57840-57842, driver sender sockets 0.0.0.0:49522-49524; `SEEN_PIDS 18 ALIVE_AFTER 0`, `PYTHON_LEFT 0`.

Table recomputed from the RAW midi records by [bar1_table.py](scripts/bar1_table.py) (`python3 docs/sdfix-gate/scripts/bar1_table.py <host> <result.json.gz>...`, exit 0; digest = sha256 of JSON `[[step, bytes], ...]` including startup step -1; [mac](evidence/bar1-mac-table.jsonl), [windows](evidence/bar1-windows-table.jsonl)). Control: one data byte in one B1 record changed in a copy -> `raw_equal False`, digest 721305eb04ef -> 762a1f6fb71c.

| Preset (fixture) | OS | Arm pair | Steps | Exercised/total | Msgs A/B | Raw bytes equal | Digest A = B | Sent = received | No overspeed | PIDs gone | Wall s |
| --- | --- | --- | ---: | ---: | ---: | --- | --- | --- | --- | --- | ---: |
| mac EDM Show (windows section) | Mac | A / B1 | 732 | 56/56 | 1531/1531 | yes | 721305eb04ef | c06cfa67469f | yes | yes | 470.4 |
| mac EDM Show (windows section) | Mac | A / B2 | 732 | 56/56 | 1531/1531 | yes | 721305eb04ef | c06cfa67469f | yes | yes | 470.4 |
| mac PTZ (windows section) | Mac | A / B1 | 732 | 52/52 | 1395/1395 | yes | 299dcecef3bc | c06cfa67469f | yes | yes | 470.4 |
| mac PTZ (windows section) | Mac | A / B2 | 732 | 52/52 | 1395/1395 | yes | 299dcecef3bc | c06cfa67469f | yes | yes | 470.4 |
| mac default | Mac | A / B1 | 732 | 56/56 | 1531/1531 | yes | 721305eb04ef | c06cfa67469f | yes | yes | 470.4 |
| windows-installed EDM Show | Windows | A / B1 | 732 | 56/56 | 1531/1531 | yes | 721305eb04ef | c06cfa67469f | yes | yes | 470.3 |
| windows-installed PTZ | Windows | A / B1 | 732 | 52/52 | 1395/1395 | yes | 299dcecef3bc | c06cfa67469f | yes | yes | 470.2 |
| windows-installed default | Windows | A / B1 | 732 | 56/56 | 1531/1531 | yes | 721305eb04ef | c06cfa67469f | yes | yes | 470.2 |

Every run `passed: true`, A commit e66ff44 (v0.4.9 peeled), candidate 19cd48e; clocks mach_absolute_time() / QueryPerformanceCounter(). The gate's digest is its own formula, so it is not comparable to the sdview gate's `candhash` column. NOT COVERED (unchanged from docs/sdwin-gate): engine-dependent MIDI (instrument runs `--no-engines`), physical hardware.

### Bar 2 - full suites at 19cd48e

| Host | Run | Command | Ran | Result | Exit |
| --- | --- | --- | --- | --- | ---: |
| Mac | 1 | step 1 command | Ran 866 tests in 9.631s | OK (skipped=2) | 0 |
| Windows clone | 1 (tag ug) | [suite.ps1](evidence/ps/suite.ps1): `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"`, PYSTRAY_BACKEND=dummy, no-op BROWSER | Ran 866 tests in 24.450s | **FAILED (errors=1, skipped=5)** | 1 |
| Windows clone | 2 (tag ug2) | same | Ran 866 tests in 23.983s | OK (skipped=5) | 0 |

**FINDING - bar 2 RED on run 1, classified PRE-EXISTING (flaky), not introduced this lap.** The error ([run 1 log](evidence/laptop/windows-suite-run1.stderr.log)): `ERROR: test_malformed_json_and_unsupported_method_are_json (test_deck_control_api.DeckControlAPITests...) (method='POST', body='{')`, `conn.getresponse()` -> `ConnectionAbortedError: [WinError 10053] An established connection was aborted by the software in your host machine`. Evidence for the class:
- `git diff --stat d67a134 HEAD -- deck/ tests/test_deck_control_api.py` = 0 lines; both last changed in 62b0dc4, which is an ancestor of BASE OF LAP and of the sdview gate HEAD b38ffb2 (whose single Windows suite run was OK).
- Base rate, measured in a third guarded pass (tag ug3, [flake.ps1](evidence/ps/flake.ps1) + [flake_rate.py](evidence/ps/flake_rate.py), one process, the single test 300 times): `RUNS 300 RUNS_WITH_ERROR 80`; kinds: 95 x WinError 10053, 3 x WinError 10054 (subtests counted separately). The rate inside a full-suite run is NOT measured (1 of 2 runs here); the isolated loop is not the same population.
- Suspected mechanism (UNVERIFIED-BY-EXECUTION): the deck control API answers a malformed body and closes while the client is still sending/reading, and Windows reports the abort as 10053/10054. Code under windows/ (receiver, MIDI, ui_server) is not involved.
Not fixed: a product/test race with an unproven cause is a report, not a gate edit. The master decides whether bar 2 counts as green.

Windows PIDs: run 1 launcher 247312 / child 281052 gone=True; run 2 286220 / 283804 gone=True; flake loop 246032 / 283632 gone=True; `PYTHON_PROCESSES_AFTER 0` each.

### Laptop sequence and hard rules

All acts via `scripts/showready/win_rail.sh`; .ps1 files written on the Mac and run with `-NoProfile -ExecutionPolicy Bypass -File`. No inline -Command, no --tray, no real MIDI port, no install, orphan checkout untouched (the guard hashes its HEAD/status). Step logs: [evidence/laptop/](evidence/laptop/) (text normalized to ASCII/LF for this report; the first pass's STEPS lines show `\U`/`\b` path escapes from zsh echo, the arguments passed were the literal paths, as the guard output confirms).

| Pass | # | Act | Exit | Result |
| --- | --- | --- | ---: | --- |
| ug | 0 | `win_guard.ps1 -Mode snapshot -Out sdwin\ug\before.json` (FIRST act) | 0 | GUARD GREEN: snapshot; pythonProcesses=0 |
| ug | 1 | inventory.ps1 | 0 | matching 1 (its own cmd.exe), python machine-wide 0 |
| ug | 2 | pins.ps1: `git -C CLONE pull --ff-only` | 0 | clone b38ffb2 -> 19cd48e, porcelain 0, v0.4.9 peeled e66ff44; pins_bad=0 (includes tests/ui_controller_geometry.cjs, LF pin holds on Windows); fixtures mac 5, windows-installed 11, total_bad=0 |
| ug | 3 | winmatrix.ps1 | 0 | bar 1 above |
| ug | 4 | suite.ps1 | 1 | bar 2 run 1 above |
| ug | 5 | inventory.ps1 | 0 | matching 1, python 0 |
| ug | 6-7 | `get` 3 result .json.gz, before.json | 0 each | to /tmp/sdfix-gate/laptop |
| ug | 9 | `win_guard.ps1 -Mode compare -Baseline sdwin\ug\before.json` | 0 | GUARD GREEN: compare; pythonProcesses=0 |
| ug2 | 0 | guard snapshot `sdwin\ug2\before.json` | 0 | GREEN |
| ug2 | 1-2 | `get` sdwin\ug\suite.stderr.log and .stdout.log | 0 | fetched run 1 logs |
| ug2 | 3 | suite.ps1 -Label suite2 | 0 | bar 2 run 2 above |
| ug2 | 4-5 | `get` suite2 log; inventory | 0 | python 0 |
| ug2 | 9 | guard compare | 0 | GREEN |
| ug3 | 0 | guard snapshot `sdwin\ug3\before.json` | 0 | GREEN |
| ug3 | 1 | `put` flake_rate.py into sdwin\ug3 | 0 | |
| ug3 | 2 | flake.ps1 -N 300 | 0 | 80/300 |
| ug3 | 5 | inventory.ps1 | 0 | matching 1, python 0 |
| ug3 | 9 | guard compare (LAST laptop act) | 0 | GUARD GREEN: compare; protected state observed; pythonProcesses=0 |

## Step 7 - pick-up

| Row | Command | Result |
| --- | --- | --- |
| U1 pushed | `git ls-remote --heads origin chain/steamdeck-20260914` at entry | 19cd48e = local HEAD |
| Porcelain at entry | `git status --porcelain` | empty |
| Scope | `git -c core.quotePath=false diff --name-only d67a134 19cd48e \| grep -v -E '^(windows/static/\|tests/\|scripts/showready/\|docs/)'` | exit 1 (no line): 57 files, all under windows/static/ (4), tests/ (4), scripts/showready/ (4), docs/sdfix-u1/ (45) |
| Protected code | `git diff d67a134 19cd48e -- windows/midi.py windows/receiver.py windows/config.py windows/ui_server.py mac/ config/ \| wc -l` | 0 |
| macro_library | `git diff --quiet d67a134 19cd48e -- config/macro_library.json` | exit 0 (unchanged) |
| Artwork | `git diff d67a134 19cd48e -- windows/static/controller/steam_deck.svg` | empty |
| Ben's Mac files | `shasum -a 256 "config/presets/EDM Show.json" config/presets/PTZ.json config/bridge.local.json` | 58e47bfd..., 11b37cd6..., 7476c269... (all as required) |
| Mac processes | [mac-pids-gone.txt](evidence/mac-pids-gone.txt): os.kill(pid, 0) on 13 bridge pids + 8 A/B arm pids | `PIDS 21 ALIVE 0`; `pgrep -fl "ab_run.py\|capture_runner.py\|win_recv\|chrome-headless-shell"` exit 1; no listener on 17841, 18851-18853, 18861-18863 (lsof exit 1) |
| Laptop processes | last guard compare | pythonProcesses=0 |

Scope notes read from the diff: index.html changes 2 lines of JavaScript, moving `ControllerView.markConflicts([])` from the conflict modal's close to a successful `doSave` (the fix for C; not CSS, but presentation state only, no payload change). tests/ui_controller_check.cjs inverts ONE pre-existing assertion (`'cancel clears row markers'` -> `'cancel retains row markers'`) because defect C requires the opposite behaviour; U1 disclosed it, and all other assertions stay, with additions.

Post-commit rows (this gate's commit, docs/sdfix-gate/ only): porcelain empty and ls-remote equal to HEAD are checked after the push and recorded in the envelope.

## Commands not run / limits

- The Mac fixtures were not replayed on the laptop (the brief asks for the Windows fixtures there).
- The gate did not re-run U1's conflict-mutation script or EOL proof; it measured C in a real browser itself (step 4) with a BASE control.
- Suite-context flake rate for the Windows deck API test: UNMEASURED (needs many full-suite runs).
