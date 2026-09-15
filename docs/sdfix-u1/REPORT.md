BASE OF LAP d67a13439028cfc983b34636e82d3de7282eab2a

# sdfix U1 - controller layout repair

Branch: chain/steamdeck-20260914. Mac build link only; no laptop acts.
All work belongs to U1. The original shape coordinates and physical arrangement
are unchanged; steam_deck.svg is byte-identical to BASE OF LAP. No mapping,
receiver, engine, API, MIDI, config data or mac/ changes.

## Layout and ownership

controller_map.json remains the source of control anchors, label banks/order,
and routing hints. Existing anchor coordinates and groups are unchanged.
The right bank now follows the outside order Y, B, A, X, Right stick, Right
trackpad. Five leader_via entries route inner controls around their neighbours.
controller_view.js layout() projects this data into one pane-sized SVG. It
uniformly scales the entire artwork, distributes label banks with minimum
spacing, and intersects each final ray with its own shape's getBBox boundary.
Arrowheads are explicit triangles with their tips on that boundary and their
bases outside the shape. No glyph is used as an endpoint.

controller_view.css keeps labels on one line, gives the controller the available
pane height, and bounds scrolling to the card. The card sits beside the picture
at wide sizes and in a bounded drawer below it at narrow sizes. All labels and
shapes stay visible even with the card open; long card contents scroll inside
the card. The header's existing wrapping remains with sdauto (F4).

## Real Chromium geometry

Command G (exit 0):

```sh
scripts/showready/ui_geometry.sh --chromium '/Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell' --scratch /tmp/sdfix-u1/nearest --single-process --mutations
```

The standalone tests/ui_controller_geometry.cjs boots nothing. G copies tracked
working files plus verified fixtures to scratch, checks TCP/UDP ports free,
boots a dry-run bridge with engines/pulse/OSC relay off, then terminates/waits
and proves its PID absent. G used TCP 17841 / UDP 47841, bridge PID 3876;
os.kill(pid, 0) raised ProcessLookupError. Effective settings and every child
command/exit are in evidence/geometry-receipt.json. Scratch:
/tmp/sdfix-u1/nearest/geometry-_wb64bna. No run-root preset was served or written.

Default Chromium launch was tried first, one browser at a time. It failed:
`FATAL:base/apple/mach_port_rendezvous_mac.cc:155 Check failed: kr == KERN_SUCCESS.
bootstrap_check_in org.chromium.Chromium.MachPortRendezvousServer.58718:
Permission denied (1100)`, SIGTRAP. Repeating with --single-process launched
and read a real DOM successfully. All reported geometry uses that mode.

G's pristine check: 1048/1048 PASS, exit 0. Computed from DOM rectangles,
SVG points transformed with getScreenCTM(), segment intersections, explicit
arrowhead triangles, all artwork text boxes, and elementFromPoint at every
label centre. No screenshot-only geometry claims. The check also verifies no
page/pane scroll and card containment at every measured state (stronger than
the two required closed-card sizes). Full measurements: evidence/pristine-geometry.json.

| Viewport / card | Labels | Label overlaps | Segment crossings | Own edge <=3 px | Glyph hits | Occluded labels | Pane/scroll |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1024x768.closed | 23 | 0 | 0 | 23/23 | 0 | 0 | PASS |
| 1024x768.open-btn_a | 23 | 0 | 0 | 23/23 | 0 | 0 | PASS |
| 1024x768.open-nearest-gyro | 23 | 0 | 0 | 23/23 | 0 | 0 | PASS |
| 1366x768.closed | 23 | 0 | 0 | 23/23 | 0 | 0 | PASS |
| 1366x768.open-btn_a | 23 | 0 | 0 | 23/23 | 0 | 0 | PASS |
| 1366x768.open-nearest-right_pad | 23 | 0 | 0 | 23/23 | 0 | 0 | PASS |
| 1440x900.closed | 23 | 0 | 0 | 23/23 | 0 | 0 | PASS |
| 1440x900.open-btn_a | 23 | 0 | 0 | 23/23 | 0 | 0 | PASS |
| 1440x900.open-nearest-right_pad | 23 | 0 | 0 | 23/23 | 0 | 0 | PASS |
| 1920x1080.closed | 23 | 0 | 0 | 23/23 | 0 | 0 | PASS |
| 1920x1080.open-btn_a | 23 | 0 | 0 | 23/23 | 0 | 0 | PASS |
| 1920x1080.open-nearest-right_pad | 23 | 0 | 0 | 23/23 | 0 | 0 | PASS |

G additionally clicks all 23 labels at each viewport and compares the title
and all drill-in Action IDs to the owned map: 92/92 pass. Nearest-card controls
are selected by computed rectangle distance, with longest-label text width breaking ties (then ID). PNGs from
this run are in screenshots/; all required output PNGs were opened and read.
Prior gate front-door, geometry and drill-in PNGs were also opened before repair.

## Detector mutations

G runs each mutation in a fresh browser DOM served by the scratch bridge.
It requires nonzero AND each named assertion, then a fresh restored page
must pass the full four-viewport matrix. No source or fixture mutation leaks.

| Mutation | RED | Required named failure | Restored |
| --- | --- | --- | --- |
| m1 swap A/B leaders and their arrowheads | exit 1, 77/79 | own-edge.btn_a and own-edge.btn_b; each endpoint inside the other's shape | exit 0, 1048/1048 |
| m2 overlap A/B labels | exit 1, 77/79 | label-overlaps names btn_a and btn_b | exit 0, 1048/1048 |
| m3 put A under status bar | exit 1, 76/79 | labels-topmost names btn_a (plus pane containment and scroll) | exit 0, 1048/1048 |

Raw mutated geometry/logs and restored summaries are in evidence/. The wrapper,
checker and README are pinned by scripts/showready/SHA256SUMS. The added
unittest verifies their presence and bytes; no browser is started by unittest.

## Conflict marks

Cancel now closes the modal while retaining row markers and messages. Card
navigation preserves them. A failed Save retains them; a successful Save
clears them. Resolving the reported channel/CC collision clears the affected
warning group. Rows use a light red message and left border on a contrasting
background. The modal's existing action list and Save guard are unchanged.
The only index.html changes move the presentation-clear hook from modal close
to successful Save. No save payload or editor operation changes.

ui_controller_check.cjs changes only C. Its obsolete assertion that Cancel
clears markers was changed to assert the newly required persistence; all other
existing assertions remain, with added failed-save, navigation, message and
resolution assertions. Failed Save requests are retained and marked in the
fake HTTP receipt; the existing force-save count measures successful writes.

`TMPDIR=/tmp/sdfix-u1 .venv/bin/python -B docs/sdfix-u1/check_conflict_mutations.py`
requires the cancel-clear, missing-success-clear and missing-resolution-clear
reversions to fail at named assertions, then restored GREEN. See
conflict-mutations.json and /tmp/sdfix-u1/conflict-mutations/.

## Mac suite and node checks

- `TMPDIR=/tmp/sdfix-u1 PYSTRAY_BACKEND=dummy BROWSER=/usr/bin/true .venv/bin/python -m unittest discover -s tests -p 'test_*.py'`: 866 tests, OK (skipped=2), exit 0. Log: evidence/mac-suite.log.
- `TMPDIR=/tmp/sdfix-u1 node tests/ui_controller_check.cjs`: PASS, exit 0.
- `TMPDIR=/tmp/sdfix-u1 node tests/ui_controller_macro_check.cjs`: 48 disk-write matches, 72 incompatible writes refused, exit 0.
- `TMPDIR=/tmp/sdfix-u1 node tests/ui_reload_check.cjs`: PASS, exit 0.
- `TMPDIR=/tmp/sdfix-u1 node tests/ui_sections_check.cjs`: PASS, exit 0.
- `shasum -a 256 -c scripts/showready/SHA256SUMS`: all 10 pinned files OK, exit 0.
- `git diff --check`: exit 0.

The existing skips cover the anticipated global-color channel-CC remap and
PowerShell execution without pwsh. Test-induced error log lines exercise
negative controls; the suite has no failures/errors. No new skip was added.

## Additional executed controls

The initial geometry run selected A again for the nearest-card test at wide
sizes because every right-bank label ties in rectangle distance. The final
G run above breaks ties by longest label text, then ID: Right trackpad at the
three wide viewports and Gyro at 1024x768. It exercises a distinct second card.
Every mutation and restored full matrix was repeated with this final checker.

Before-repair control command (exit 1): G with --scratch /tmp/sdfix-u1,
without --mutations, plus --revision d67a13439028cfc983b34636e82d3de7282eab2a.
The same detector produced 363/1048 PASS. It found the named original label
pairs at 1024, crossings, glyph intersections and covered labels at 1440.
The old marker-based artwork also fails the new explicit-head inventory;
that schema difference is recorded separately from the observed layout
failures in evidence/base-regression.json. Bridge PID 91879 was proved gone.
This control used the checker before the nearest-card tie-break refinement.

The wrapper's default launch (same Chromium path, without --single-process,
--scratch /tmp/sdfix-u1) repeated the Permission denied (1100) / SIGTRAP error,
exit 1, browser PID 91703. Bridge PID 91670 was proved gone. Exact output and
receipt: evidence/default-launch.log and default-launch-receipt.json.

`TMPDIR=/tmp/sdfix-u1 .venv/bin/python -B docs/sdfix-u1/run_browser_conflicts.py /tmp/sdfix-u1/geometry-4ajwqjf_/tree`
exited 0, seven real-browser assertions PASS. After Cancel the message is
uncovered at its centre with contrast 9.5903:1, and the preset bytes are
unchanged. SELECT remains marked on navigation; successful forced Save clears
the marks and changes only START.cc from 78 to 79 on the scratch disk copy.
Exact underlying browser command, arguments and PID proof are in
evidence/conflict-browser-receipt.json; bridge PID 99041 gone. The PNG
screenshots/conflict-after-cancel.png was opened and read.

The first conflict-browser run had a RIG ERROR: it compared JSON key order
instead of parsed values. The recursive parsed diff was exactly START.cc
78 -> 79. Changed the check to isDeepStrictEqual, restored the scratch fixture
bytes, and reran the entire proof. Initial log is retained as
conflict-browser-RIGERROR.log (its bridge PID 97261 also gone).

`tests/.gitattributes` pins the geometry check to LF for Windows checkouts.
`git check-attr eol -- tests/ui_controller_geometry.cjs` returns lf.
`.venv/bin/python -B docs/sdfix-u1/check_checkout_eol.py` creates disposable
Git clones with core.autocrlf=true: pinned bytes GREEN; removing the rule gives
154 CRLFs and a different digest (RED); restoring gives pinned bytes GREEN.
Exact commands and hashes: evidence/eol-proof.json. No laptop was touched.

The final Mac suite ran 866 tests in 13.297s, OK (skipped=2), exit 0, with the
suite command above. evidence/mac-suite-source.json hashes the untouched
scratch log; the committed log renders the pre-existing test warning's
non-ASCII dash as an ASCII Unicode escape to meet the report's ASCII rule.

## Bar 1 and handoff

MIDI A/B replay will run at this implementation commit. The verified result
will be appended in a docs-only evidence commit before U1 completes.
The Windows full suite and Windows bar 1 remain OWED TO THE GATE under the
unchanged showready instruments/guard. Windows behavior is
UNVERIFIED-BY-EXECUTION in U1. This is no deployment or show-ready verdict.

For sdlive: shape data-control identities, SVG source coordinates and map
anchors are unchanged. Rendered scene coordinates now fit the pane; use the
artwork's transform when projecting live dots/bars. Leaders are polylines;
arrowheads are explicit data-control-head polygons. layout() owns positioning.
