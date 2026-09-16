BASE OF LAP 778eaa78441c0e7d5539f540cfed8aa944142f8b
P1 START 05b0ec2cf2624a9140bd7c48015ba38a77b976d5

# sdpolish P1 - the geometry instrument and the pinned laptop bundle script

NO PRODUCT CODE CHANGED. This link touches scripts/showready/, tests/ and docs/ only.
`git diff --stat 05b0ec2..HEAD -- windows/` is empty. The instrument exists and FAILS on
today's picture BEFORE P2 moves anything, which is the whole point of the ordering.

## 1. Scratch is a pattern, not a lap name

- `scripts/showready/deck_script.py:74-89` - `SCRATCH_PATTERN` / `scratch_ok(path)`.
  Accepts `/tmp/sd<lap>-<link>/...` and the `/private/tmp/...` form macOS resolves it to;
  refuses everything else, and refuses any path containing a `..` segment outright.
- `scripts/showready/ui_geometry.py:27,29` - the guard call replaces the two
  `startswith('/tmp/sdfix-')` literals.
- `tests/test_showready_scratch_pattern.py` - BOTH DIRECTIONS: 7 accepted shapes, 14
  refused (the run root, the vault, `/Users/viddyslap/private`, `/var/folders`, a bare
  `/tmp`, a lap with no link, an unanchored `xsdpolish-p1`, a relative path, the empty
  string), a new-lap case that needs no edit, and a test that the instrument actually
  CALLS the guard. The `..` case was written first and went RED against my first
  implementation, which accepted `/tmp/sdpolish-p1/../../Users`; the guard was fixed,
  not the test.

## 2. The check is live-view aware; it never waits on networkidle

`tests/ui_controller_geometry.cjs`, rewritten around the sdlive gate's `geom_live.cjs`
method. Changes with file:line at HEAD:

- `:244` `page.goto(url,{waitUntil:'domcontentloaded'})`. The old `networkidle` at the
  old `:118` could never settle: the Controller view holds an open EventSource.
- `:246-247` waits for 23 `.controller-label` elements AND `#controllerLiveStatus`
  reading `live`, on a 15 s timeout.
- `:10,:206-216` a real `dgram` UDP socket at the bridge's own `/api/settings` listen
  address, with a 100 ms heartbeat, refusing host != 127.0.0.1 and port 45123.
- `:224-233` `drive()` pushes both sticks off centre, both trigger bars non-zero and both
  gyro axes off rest, then waits for the r2 bar width > 40 and two rAF. Overlays are
  therefore DRAWN OBSTACLES at every measurement, not zero-width rects at rest.
- `:79-81` `<tag>.stream-live-with-overlays-drawn` asserts that state per measurement, so
  a run that silently lost the stream cannot pass the obstacle criteria vacuously.
- `:268-276` EVERY ONE of the 23 cards is opened at EVERY viewport and gets a full
  `assertGeometry`, not only btn_a and the nearest label.
- `:191` live-overlay `text` (the gyro axis captions) is excluded from `glyphs` and
  judged by b2 instead; it is an overlay, not scene art.

EXISTING ASSERTIONS. Every sdfix criterion is preserved by name and still passes at all
four viewports with the live overlays drawn: `23-labels/leaders/shapes/arrowheads`,
`label-overlaps`, `leader-intersections`, `own-edge.<id>`, `glyph-clear.<id>`,
`leader-visible.<id>`, `inside-visible-pane`, `labels-topmost`, `labels-unwrapped`,
`no-page-or-pane-scroll`, `card-inside-pane`, `drill.<id>`.
ONE ASSERTION NAME IS GONE: `<vp>.open-nearest-<id>`. It opened the single label nearest
the card. Its coverage is a strict subset of the new all-23 loop, which opens that label
too and asserts more on it. Named here and in the commit body because the rule says an
assertion may not just disappear.

## 3. The new criteria

- `b.no-leader-through-other-control` (`:112-124`) - no leader segment, bend or arrowhead
  intersects or touches (distance 0) the geometry box of any OTHER control's
  `data-control` shape, live trigger track or live bar. Overlays are joined to their owner
  by the `.controller-live-overlay` group index, which is the map order
  (`controller_live.js:33` appends one group per control); the 23-count assertions pin
  that join.
- `b2.no-live-overlay-over-card-or-label` (`:126-132`) - with a card open, no stick dot,
  trigger bar, track or gyro dot intersects the open card or any of the 23 label boxes.
- `c.leader-clearance-6px` (`:134-142`) - minimum distance between any two DIFFERENT
  leaders' segments, bends and arrowheads >= 6.0 px, via a real segment-to-segment
  distance (`:56-64`). The measured minimum AND the pair are reported per viewport and
  card state, pass or fail.
- `d.drawer-rows-visible` (`:144-149`, measured at `:178-186`) - at 1024x768 only, for
  each of the 23 cards in turn, the card title, its tabs and the first two action rows
  (all rows if fewer) fully inside the card's visible area with the card's own
  `scrollTop` at 0.

## 4. TODAY'S PICTURE FAILS, and only on the three new criteria

Command: `scripts/showready/ui_geometry.sh --chromium <chrome-headless-shell 1208>
--scratch /tmp/sdpolish-p1/final2 --single-process --pristine-may-fail --mutations
--ui-port 17873 --listen-port 47873`, at HEAD 05b0ec2 plus this link's instrument changes.
PRISTINE: 7984/8175 PASS, 191 failures. Every one of the 191 is b, c or d:

| viewport | b RED states | c RED states | d RED states |
|---|---|---|---|
| 1024x768 | 24 of 24 | 24 of 24 | 23 of 23 |
| 1366x768 | 24 of 24 | 24 of 24 | n/a (d is 1024x768 only) |
| 1440x900 | 24 of 24 | 24 of 24 | n/a |
| 1920x1080 | 24 of 24 | 0 of 24 (GREEN) | n/a |

b - THE SAME TWO LEADERS AT EVERY VIEWPORT AND EVERY CARD STATE, six obstacle hits each:
`l1 -> l2.shape`, `l1 -> l2.track`, `l1 -> l2.bar`, `r1 -> r2.shape`, `r1 -> r2.track`,
`r1 -> r2.bar`. This is exactly the fault docs/sdfix-gate/REPORT.md ~20 records, and the
`.track`/`.bar` hits are the sdlive live trigger bars sitting in the same place.
Numbers at 1440x900 closed: l1's leader runs (373.2,187.5) -> (396.2,304.3) straight down
through l2's shape box x 331.7..412.0, y 265.0..297.1, and through l2's live track box
x 343.3..400.4, y 284.6..291.8.

c - RED at three of four viewports, ALWAYS the same pair, `dpad_right.segment` against
`left_pad.segment`: minimum 3.408 px at 1024x768, 3.801 px at 1366x768, 4.155 px at
1440x900, against the 6.0 px floor. GREEN at 1920x1080, where the same pair measures
6.348 px (worst state) / 7.867 px (closed). SAID PLAINLY AS THE ITEM ASKS: c is ALREADY
GREEN at 1920x1080 and that is not a defect.

d - RED for ALL 23 controls at 1024x768. The card's visible area is 170.0 px tall
(`controller_view.css:48`, `grid-template-rows: minmax(300px, 1fr) 170px`), scrollTop 0.
The title and the tabs FIT; the rows do not. First action row overflows the card bottom by
100.0 px for every one of the 23. Second row overflows by 265.0 px on the ten controls whose
second row is a LAYER_2 or LONG_PRESS entry (btn_a/b/x/y, dpad_up/down/left/right, l1, r1)
and by 224.5 px on the seven group-separated ones (gyro, l2, r2, left_pad, right_pad,
left_stick, right_stick). Six controls have only one row (l4, l5, r4, r5, select, start),
each clipped by 100.0 px alone. 10 + 7 + 6 = 23.

## 5. Mutations - each RED, then restored to the PRISTINE LINE

m1-m3 are planted in the live DOM; m4-m6 are planted in the SERVED STATIC FILES of the
scratch tree and the original bytes are written back and re-compared (`ui_geometry.py`
file-mutation loop). HOW A MUTATION IS PROVEN (`ui_geometry.py` `proven()`): a boolean
flip PASS-pristine -> FAIL-mutated is the strong case. THREE OF THE SIX TARGET ASSERTIONS
ARE ALREADY RED ON TODAY'S PICTURE, so a flip is unavailable and would prove nothing;
those mutations must instead put a planted MARKER into that assertion's own detail that
the pristine detail does not carry (or, with a leading `!`, remove one it does), and the
restored run must return the line to the pristine line byte for byte.

| id | file mutated | assertion | pristine | mutated | proof |
|---|---|---|---|---|---|
| m1 | DOM | `1440x900.closed.own-edge.btn_a` | PASS distance 0.0000279 | FAIL distance 39.737, insideOther ["btn_b"] | flip |
| m2 | DOM | `1440x900.closed.label-overlaps` | PASS [] | FAIL [["btn_a","btn_b"]] | flip |
| m3 | DOM | `1440x900.closed.labels-topmost` | PASS [] | FAIL [{"id":"btn_a","by":"SPAN"}] | flip |
| m4 | controller_map.json | `1440x900.closed.b.no-leader-through-other-control` | FAIL (l1/r1 only) | FAIL, now carrying `{"leader":"dpad_up","part":"segment","hits":"l2.track"}` | marker |
| m5 | controller_map.json | `1920x1080.closed.c.leader-clearance-6px` | PASS 7.867 px | FAIL 4.631 px, pair dpad_right/left_pad | flip |
| m6 | controller_view.css | `1024x768.open-r2.d.drawer-rows-visible` | FAIL, `"scrollTop":0` | FAIL, `"scrollTop":206`, row0 overflow 100 -> 154 px | inverted marker |

- m4 routes `dpad_up`'s leader through the L2 trigger track via `leader_via [[210,58]]`
  (L2 anchor 210,50; its live track is the 64x8 rect at x-32, y+4).
- m5 drops `dpad_right`'s waypoint three scene pixels, `[[240,390]] -> [[240,393]]`. A
  DELIBERATE NEAR MISS: 4.631 px against the 6.0 px floor with `leader-intersections`
  still GREEN in the same run, so criterion c is the ONLY thing that can catch it. My
  first m5 measured distance 0.0, i.e. an actual crossing that the pre-existing
  `leader-intersections` criterion already caught; that version proved nothing about c
  and was replaced.
- m6 appends `#controllerCard:has(.controller-group[data-group="analog"])
  .controller-card-header { margin-top: 260px; }`. THE NAMED CONTROL IS `r2`, which is
  neither btn_a nor dpad_up. It is selective by construction: `r2` owns an analog group,
  btn_a and dpad_up do not, and the run ASSERTS that
  `1024x768.open-btn_a.d.drawer-rows-visible` is byte-identical to its pristine line.
  WHAT IT CAUGHT IS THE SCROLL CLAUSE, not the clipping: opening a card focuses the title
  (`controller_view.js:214`), so the card scrolls the pushed-down header back into view
  and `scrollTop` goes 0 -> 206. Criterion d's `scrollTop === 0` clause is doing real work
  and I am reporting what fired rather than what I expected to fire.

All six: `PASS mutation RED and restored to the pristine line mN`; receipt exit 0; bridge
PID gone=True. Receipt: /private/tmp/sdpolish-p1/final2/geometry-66pp8fct/receipt.json.

`--pristine-may-fail` is NEW and records a RED pristine run instead of aborting, because
the instrument is required to fail today. IT WEAKENS NOTHING: `proven()` and the
restored-line comparison run identically with or without it. THE GATE AND P2 RUN WITHOUT
IT once the picture is green.

## 6. The pinned bundle script

`scripts/showready/pull_bundle.ps1`, from `docs/sdpick-k1/scripts/pull_bundle.ps1`.
PARAMETERS: `-Bundle <path>` and `-Expected <full sha>`, both
`[Parameter(Mandatory=$true)][string]`. EXIT CODES UNCHANGED: 3 dirty clone, 4
`git bundle verify`, 5 fetch, 6 FETCH_HEAD != -Expected, 7 `merge --ff-only`, 8 HEAD or
porcelain; 0 only on success.
`tests/test_showready_pull_bundle.py` (5 tests) asserts both parameters are mandatory,
that `sdpick.bundle` and `PSScriptRoot` are gone, that all seven exit codes appear each
still preceded by its own condition, that `git bundle verify` and `merge --ff-only`
survive, and - line by line against the K1 original - that ONLY line 1 (param) and line 5
(`$bundle=$Bundle`) differ, with equal line counts.
NOT RUN ON THE LAPTOP. P3 is its first real use. UNVERIFIED-BY-EXECUTION on Windows.

## 7. Re-pin and docs

- `scripts/showready/SHA256SUMS` regenerated: 18 entries, now including
  `pull_bundle.ps1`, and `__pycache__` excluded.
- `tests/test_showready_rail.py` `verify_pins` now skips `__pycache__`. NAMED CHANGE:
  the new scratch-pattern test imports `deck_script` directly, which wrote
  `scripts/showready/__pycache__/deck_script.cpython-312.pyc` and turned both pin tests
  RED. A bytecode cache is a build artefact of whoever imported a module, not an
  instrument file, so including it made the pin set depend on import order. The test also
  sets `sys.dont_write_bytecode` so the directory is normally not created at all. Both
  pin tests are GREEN and still fail on a real unpinned edit (they are in the 1087).
- `scripts/showready/README.md`: the exact geometry command, the scratch pattern, the
  live-aware waiting and driving, the four viewports and the closed + 23-open states, all
  four new criteria with their definitions, the mutation table and the proof rule, and a
  new "Laptop bundle route (pinned)" section with create / sha256 / put / run using
  `-Bundle` and `-Expected` and all seven exit codes. The re-pin command in the README now
  excludes `__pycache__` too.

## 8. Checks

| command | result |
|---|---|
| `.venv/bin/python -m unittest discover -s tests -p "test_*.py"` | Ran 1087 tests, OK (skipped=2) |
| `node tests/ui_controller_check.cjs` | exit 0 |
| `node tests/ui_controller_macro_check.cjs` | exit 0 |
| `node tests/ui_reload_check.cjs` | exit 0 |
| `node tests/ui_sections_check.cjs` | exit 0 |
| `node tests/ui_version_check.cjs` | exit 0 |
| `scripts/showready/ui_geometry.sh ... --pristine-may-fail --mutations` | exit 0; pristine 7984/8175 (191 RED, all b/c/d); m1-m6 each RED then restored to the pristine line; bridge PID gone |

No laptop act. No timing or CPU arm, so no quiet gate applies. Scratch under
/tmp/sdpolish-p1/ with `.metadata_never_index` created before the first file was written.
`git status --porcelain` empty after the commit.

## FOR P2

- Your target is the three RED criteria above with those numbers. Run
  `scripts/showready/ui_geometry.sh --chromium <shell> --scratch /tmp/sdpolish-p2/geometry
  --single-process --mutations` WITHOUT `--pristine-may-fail`: when the picture is right,
  pristine is GREEN and the flag is unnecessary. If you still need it, the picture is not
  right yet.
- b needs the L1 and R1 leaders off the L2 and R2 shapes AND off their live trigger tracks
  and bars. The bars move with trigger pressure, so route clear of the whole 64x8 track,
  not just the drawn fill.
- c is a 6.0 px floor on the WORST state, and the worst pair today is dpad_right against
  left_pad at 1024x768 (3.408 px). Fixing the picture at 1920x1080 alone is not fixing it.
- d is a 170 px drawer at 1024x768 against a first row that starts 100 px below it. The
  title and tabs already fit; the rows are the problem, and note that opening a card
  focuses the title, so a taller card can scroll itself and trip the `scrollTop === 0`
  clause even when nothing is clipped.
- Do NOT change the check to make it pass. The mutation sweep is what stops that: every
  criterion's detector has been shown to fire on a planted fault and to go quiet when the
  fault is removed.
