BASE OF LAP 778eaa78441c0e7d5539f540cfed8aa944142f8b
P2 START 5f440be1c4ed3b03ebedd387931ce97a3f4caf11

# sdpolish P2 - the controller view layout

NO PRODUCT CODE CHANGED OUTSIDE windows/static/. `git diff --stat` against P2 START touches
only `windows/static/controller/` (4 files), `tests/ui_controller_check.cjs`,
`scripts/showready/ui_geometry.py` and its `SHA256SUMS`, plus this docs folder.
`git diff -- windows/midi.py windows/receiver.py windows/config.py windows/engines/ protocol/`
is EMPTY. No route, no mapping semantics, no MIDI byte path.

## 1. The reference, and the arrangement verdict: IT DIFFERED

REFERENCE URL (Valve's own product render, served from Valve's CDN for the official
Steam Deck tech-specs page https://www.steamdeck.com/en/tech/deck):

    https://cdn.fastly.steamstatic.com/steamdeck/images/tech-specs/tech-specs_1_english.png?v=2

sha256 `56f3107c84bc1e91bfcbba71cad63540f12cf7a6d70105f7d4697acb50d592c0`, 2208x1224,
saved as `docs/sdpolish-p2/reference/steamdeck-tech-specs-front.png`. The top-edge and rear
renders from the same page are saved beside it and used for L1/L2/R1/R2 and L4/L5/R4/R5:

    tech-specs_2_english.png  8b9052bed0e5ccd6bca6fbba289a988360a3e958e145809062b68a025a43dbe5  (top edge)
    tech-specs_3_english.png  e87caecf3628aa0761d2930f0598fc1f2aa3ebc1d897cee3f135315c12cf5615  (rear)

Provenance, fetch command and a SHA256SUMS file: `docs/sdpolish-p2/reference/SOURCE.md`.
NOTHING IS EMBEDDED OR TRACED. `steam_deck.svg` is still an original geometric drawing of
rects, circles and paths; no path in it was derived from Valve's artwork.

### Where each control sits on the real device, read off Valve's renders

FRONT (tech-specs_1). Reading the left half outward-to-inward: the D-PAD is the
outermost control and the HIGHEST of the left cluster; the LEFT THUMBSTICK sits inboard of
it and slightly LOWER; the VIEW button is a small pill ABOVE, horizontally BETWEEN the two;
the LEFT TRACKPAD is a large rounded square BELOW BOTH, roughly under the gap between them;
the STEAM button is a pill below the trackpad. The right half mirrors it: RIGHT THUMBSTICK
inboard, ABXY outboard of the stick and slightly ABOVE its centre in a diamond (Y top, X
left, B right, A bottom), MENU above between stick and ABXY, RIGHT TRACKPAD below, QUICK
ACCESS below that.

TOP EDGE (tech-specs_2). L1 and L2 are at the extreme left end of the top edge and R1/R2
at the extreme right. In the top view the trigger is the FARTHER-BACK of the pair and the
bumper the nearer-front, so drawn on a front-facing picture the trigger reads as sitting
ABOVE the bumper.

REAR (tech-specs_3, a mirrored view). Each grip carries two stacked rounded rects. The
left of that image is the device's RIGHT grip, and its labels read R4 on the UPPER rect,
R5 on the LOWER. By the device's symmetry L4 is the upper and L5 the lower on the left grip.

GYRO. The gyro appears on NONE of the three renders: it is an internal IMU with no external
feature to point at, so Valve's imagery does not represent it at all. Our picture therefore
cannot copy it from the reference; it draws a labelled `GYRO` tile below the body outline as
an explicit non-physical placeholder, which the map's own note already records ("The anchor
marks a gyro tile, not a physical button."). That is unchanged by this link.

STEAM and QUICK ACCESS appear on Valve's front render but have NO Action ID in
`controller_map.json` and are not mappable, so the picture does not draw them. Unchanged.

### Control-by-control comparison

Positions are expressed as a fraction of the LEFT (or mirrored RIGHT) CONTROL COLUMN, not
of the whole body: our body is far squatter than the real one (our control column is 295 x
315 units, aspect 0.94; Valve's is 345 x 674 px, aspect 0.51) because the drawn screen takes
a larger share of the body. Absolute fractions therefore cannot match and matching them was
never the goal; the ORDER and the relative placement are what the item asks for.

fx = distance from the outboard body edge / column width. fy = distance from the top edge /
column height. Valve figures measured off tech-specs_1 at full resolution (body x 252..1965,
y 259..933; left column x 252..597).

| control | Valve fx, fy | BEFORE fx, fy | AFTER fx, fy | verdict |
|---|---|---|---|---|
| D-pad | 0.235, 0.182 | 0.390, 0.571 | 0.339, 0.270 | WAS WRONG, FIXED |
| View (SELECT) | 0.507, 0.068 | 0.644, 0.016 | 0.464, 0.051 | adjusted |
| Left stick | 0.728, 0.214 | 0.661, 0.238 | 0.746, 0.286 | was close, kept |
| Left trackpad | 0.670, 0.507 | 0.763, 0.698 | 0.729, 0.762 | order right before and after |
| Right stick | 0.754, 0.214 | 0.729, 0.238 | 0.746, 0.286 | was close, kept |
| Menu (START) | 0.536, 0.071 | 0.644, 0.016 | 0.464, 0.051 | adjusted |
| ABXY centre | 0.261, 0.176 | 0.390, 0.254 | 0.383, 0.273 | direction fixed, residual below |
| Right trackpad | 0.684, 0.505 | 0.763, 0.698 | 0.729, 0.762 | order right before and after |
| L1 / L2, R1 / R2 | outermost of the top edge, trigger above bumper | inboard of the outer corner | outermost | MATCHES after the shift |
| L4 / L5, R4 / R5 | L4 upper, L5 lower, rear | L4 upper, L5 lower, rear | unchanged | MATCHED ALREADY |
| Gyro | not depicted | tile below the body | unchanged | not comparable, see above |

THE ONE REAL ARRANGEMENT ERROR was the D-PAD. On the real device it is the highest control
of the left cluster and sits ABOVE and OUTBOARD of the thumbstick, with the trackpad below
both. Our drawing had it 105 units BELOW the stick and level with the trackpad, so the
picture read left-to-right as "stick, then D-pad beside the trackpad", which is not the
device. It is now at (185,185) against the stick's (305,190): outboard, and its top arm
(y 130) is above the stick's centre, with the trackpad at y 295..385 below both.

TWO SMALLER CORRECTIONS came with it, both read off the same render. (1) L1/L2 and R1/R2
were inboard of the body's top corners; they are now the outermost things on the top edge
(l2 x 130..220 was 165..255; l1 x 160..240 was 200..280, mirrored on the right). (2) ABXY
sat 5 units BELOW the right stick's centre; Valve has the cluster slightly ABOVE, and it now
sits at centre y 186 against the stick's 190.

RESIDUAL, STATED PLAINLY: ABXY is still more inboard than the real device (0.383 against
0.261 of the column). Our right control column is 295 units wide and the ABXY diamond is
116 of them; pushing the cluster outboard far enough to reach 0.26 would put btn_b's right
edge within ~7 units of the drawn body edge. I left the ARRANGEMENT FACT (ABXY outboard of
the stick, slightly above its centre, Y/X/B/A in the correct diamond) correct and did not
chase the fraction. Same reasoning for the trackpads' fy: the real ones sit at mid-body,
ours at 0.76 of a much shorter column, because the drawn screen occupies the middle band.

NOTHING ELSE MOVED IN MEANING. Every `data-control` id (23 of them), every control's
`label`, `kind`, `groups`, `notes`, the control ORDER, `view_box`, `scene_view_box` and
`axis_ranges` are byte-identical to BASE - asserted directly, see "Checks" below. No card,
drill-in, group or Action ID changed.

## 2. Where the layout change lives

Everything is data plus the ONE layout function sdfix U1 built. No new layout code path.

- `windows/static/controller/steam_deck.svg` - the drawn shapes moved. Each `data-control`
  element kept its id and its element type; only coordinates changed. The A/B/X/Y and L3/R3
  captions and the two `REAR` captions moved with the shapes they caption.
- `windows/static/controller/controller_map.json` - `anchor`, `label_anchor` and
  `leader_via` only. Full before/after table:

| id | anchor BEFORE | anchor AFTER | label_anchor BEFORE | label_anchor AFTER | leader_via AFTER |
|---|---|---|---|---|---|
| btn_a | (1000,220) | (1002,226) | (1330,270) | (1330,330) | - |
| btn_b | (1040,180) | (1042,186) | (1330,200) | (1330,250) | - |
| btn_x | (960,180) | (962,186) | (1330,340) | (1330,410) | [[1090,262],[962,262]] |
| btn_y | (1000,140) | (1002,146) | (1330,130) | (1330,170) | - |
| dpad_up | (200,240) | (185,150) | (-130,205) | (-130,170) | - |
| dpad_down | (200,320) | (185,220) | (-130,345) | (-130,330) | - |
| dpad_left | (160,280) | (145,185) | (-130,275) | (-130,250) | - |
| dpad_right | (240,280) | (225,185) | (-130,415) | (-130,410) | [[110,262],[234,262]] |
| left_stick | (280,175) | (305,190) | (-130,130) | (-130,450) | [[150,285],[305,285]] |
| right_stick | (900,175) | (895,190) | (1330,410) | (1330,450) | [[1050,285],[895,285]] |
| l1 | (240,90) | (200,90) | (180,-90) | (180,-90) | [[280,90]] |
| r1 | (960,90) | (1000,90) | (1020,-90) | (1020,-90) | [[920,90]] |
| l2 | (210,50) | (175,50) | (-80,-90) | (-80,-90) | - |
| r2 | (990,50) | (1025,50) | (1280,-90) | (1280,-90) | - |
| select | (275,105) | (222,116) | (440,-90) | (-130,90) | [[150,110]] |
| start | (925,105) | (978,116) | (760,-90) | (1330,90) | [[1050,110]] |
| left_pad | (310,320) | (300,340) | (-130,485) | (-130,490) | - |
| right_pad | (890,320) | (900,340) | (1330,480) | (1330,490) | - |
| l4 l5 r4 r5 gyro | unchanged | unchanged | unchanged | unchanged | - |

- `windows/static/controller/controller_view.css` - two changes, both at the
  `max-width: 1250px` breakpoint. See section 5 (criterion d).
- `windows/static/controller/controller_view.js` - ONE line, inside `layout()`:
  `labelWidth` gained a 132 floor. See section 4.

BANK MOVES. SELECT and START left the TOP bank for the LEFT and RIGHT banks, and the two
STICKS did not join the top bank. The top bank is now exactly the four shoulder controls
(l2, l1, r1, r2) and each side bank holds seven. That is what makes b reachable: with the
D-pad outboard, nothing can reach the stick from the left edge without crossing the D-pad,
so both sticks are now reached through a corridor BELOW the D-pad (left) and below ABXY
(right), at scene y 285. dpad_right and btn_x use the same idea one corridor higher, at
y 262. The corridors are 23 scene units apart by construction, which is what criterion c's
margin rests on.

## 3. Criterion b: no leader through another control

GREEN at all four viewports, card closed and with each of the 23 cards open, with the live
overlays driven and drawn. `b.no-leader-through-other-control` detail is `[]` in all 96
states. The two faults P1 measured are gone:

- `l1 -> l2.shape`, `l1 -> l2.track`, `l1 -> l2.bar` and the r1/r2 mirror, RED in all 96
  states at P1's HEAD. L1's leader now leaves the top bank, turns at scene (280,90) - which
  is 60 units clear of l2's right edge at 220 - and enters l1's right edge horizontally, so
  it never enters l2's box and therefore never enters l2's 64x8 live track or its bar
  wherever trigger pressure puts the fill. Mirrored for r1 at (920,90).
- `b2.no-live-overlay-over-card-or-label` is `[]` everywhere, as it was.

ONE FINDING WORTH RECORDING, because it cost an iteration and will cost the next person one.
`lineHitsRect`'s near-collinear epsilon reports a HIT when a leader's straight leg is
EXACTLY aligned with a shape's edge. My first dpad_right route turned upward at scene x=225,
and l4/l5 are rects whose left edge is x=225; the leg spans y 201..258 and l4 spans y
433..457, nowhere near it, yet `1024x768.closed.b` reported `dpad_right -> l4.shape` and
`-> l5.shape`. `cross(a,b,c)` is then ~1.3e-4 - above the 1e-5 collinear threshold but small
enough that the product test `cross(a,b,c)*cross(a,b,d) <= eps` passes on both pairs. I did
NOT touch the criterion: I moved the leg to x=234. Any future leader leg should avoid
sharing an exact x or y with another shape's edge.

## 4. Criterion c: >= 6.0 px between two different leaders

DECLARED BEFORE THE DATA by P1 and unchanged: minimum distance between any two DIFFERENT
leaders' segments, bends and arrowheads >= 6.0 px. Measured minimum per viewport and card
state, from the final pinned run's `pristine/geometry.json`:

| viewport | card closed | worst of the 23 open states | binding pair |
|---|---|---|---|
| 1024x768 | 11.090 px | 6.609 px | btn_y.head / start.segment (open) |
| 1366x768 | 15.283 px | 10.879 px | btn_a.segment / btn_x.segment |
| 1440x900 | 14.839 px | 11.650 px | btn_a.segment / btn_x.segment |
| 1920x1080 | 18.638 px | 15.954 px | btn_a.segment / btn_x.segment |

P1's failing pair at BASE was `dpad_right.segment / left_pad.segment`: 3.408 px at 1024x768,
3.801 at 1366x768, 4.155 at 1440x900, GREEN at 1920x1080. That pair is no longer the binding
one anywhere.

THE MARGIN IS HONEST BUT THIN AT ONE PLACE: 6.609 px at 1024x768 with a card open, 0.609 px
of headroom, between btn_y's arrowhead and START's leader. Both live in the corridor between
r1's bottom (scene y 104) and btn_y's top (scene y 127) - 23 scene units, about 8.4 px at
that viewport's scale. My first routing measured 6.082 px there; raising the SELECT/START
corridor from scene y 112 to 110 moved it to 6.609 and I stopped, because y=108 broke
criterion b (the leader sagged into l1/r1's box in all 23 open states at 1024x768 - measured,
not predicted). Anyone widening that further has to move r1/l1 up, which I judged not worth
the churn on the last feature lap. NAMED SO THE GATE KNOWS WHERE THE THIN EDGE IS.

## 5. Criterion d: the 1024x768 card

At BASE the card was a BOTTOM DRAWER 170 px tall (`grid-template-rows: minmax(300px,1fr)
170px`), and d was RED for all 23 controls: the title and tabs fit, the first action row
overflowed the card bottom by 100.0 px and the second by 224.5 or 265.0 px.

A TALLER DRAWER CANNOT WORK, and I checked rather than assumed. From the BASE measurement
the second row's bottom sits 435 px below the card's top, so the card needs ~451 px; the
whole layout area at 1024x768 is ~547 px, which would leave the picture ~86 px. At that
height the label banks alone need more vertical space than the picture has, so
`inside-visible-pane` fails. The drawer is the wrong shape at this width.

THE FIX IS THAT 1024x768 KEEPS THE CARD AS A COLUMN, 300 px wide instead of the default 330:

```css
@media (max-width: 1250px) {
  .controller-layout:not(:has(#controllerCard[hidden])) { grid-template-columns: minmax(0, 1fr) 300px; gap: 10px; }
  ...
  #controllerCard { padding: 12px; }
  .controller-card-hint { margin-top: 6px; }
  .controller-tabs { margin-top: 10px; }
  .controller-group { margin-top: 12px; }
  .controller-row { padding: 8px 0; }
}
```

The card is then full pane height (554 px), which holds the title, the tabs and both action
rows of every one of the 23 controls with `scrollTop` 0. `d.drawer-rows-visible` is GREEN
for all 23, `clipped: []`, `scrollTop: 0`. Screenshot `after-1024x768-open-btn_a.png` shows
the A card with TAP/BTN_A and LAYER 2/BTN_A_LAYER_2 both fully drawn.

THE KNOCK-ON, AND THE ONE JS LINE. A 300 px card leaves the picture 690 px wide, and
`layout()`'s `labelWidth = Math.min(146, width / 6 - 10)` then gave 105 px, which clips
"Right trackpad" (125 px of content), "Left trackpad" (117) and "D-pad Down" (106) - measured
with a probe, not guessed. That turned `labels-unwrapped` and `no-page-or-pane-scroll` RED
in all 23 open states. The line is now:

```js
const labelWidth = Math.max(132, Math.min(146, width / 6 - 10));
```

A floor, not a new formula. It binds ONLY where `width / 6 - 10 < 132`, i.e. picture width
below 852 px, which among the four measured viewports is exactly the 1024x768 card-open case;
1024x768 card-closed and all three wider viewports still resolve to 146 and are bit-identical
in behaviour to BASE.

## 6. Criterion e: P1's pinned check at HEAD

Command, exactly as `scripts/showready/README.md` gives it and as P1's report instructs,
WITHOUT `--pristine-may-fail`:

```
scripts/showready/ui_geometry.sh \
  --chromium '/Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell' \
  --scratch /tmp/sdpolish-p2/final2 --single-process --mutations \
  --ui-port 17882 --listen-port 47882
```

PRISTINE 8175/8175 PASS, failures=0. That is 4 viewports x (closed + 23 open) = 96 states,
every sdfix criterion by name plus b, b2, c and d, with the stream live and the overlays
driven (`stream-live-with-overlays-drawn` PASS in every state, so no obstacle criterion
passed vacuously). Bridge PID gone=True. Receipt
`/private/tmp/sdpolish-p2/final2/geometry-juxw6ubo/receipt.json`.

THE INSTRUMENT'S CRITERIA WERE NOT TOUCHED. `git diff -- tests/ui_controller_geometry.cjs`
is EMPTY: not one line of the file that decides PASS or FAIL changed. I did not run with
`--pristine-may-fail` and did not need it.

EACH CRITERION I CLAIM TO HAVE FIXED WAS RED AT P1's HEAD, from P1's own report and
reproduced by me at BASE in `/tmp/sdpolish-p2/before/` (PRISTINE 7984/8175, failures=191,
the same 191 P1 recorded): b RED in 24 of 24 states at every viewport; c RED in 24 of 24 at
1024x768, 1366x768 and 1440x900 (GREEN at 1920x1080, as P1 said, and not a defect); d RED
for all 23 at 1024x768.

### The mutation sweep, and TWO PINNED MUTATIONS I HAD TO RE-SIZE

All six mutations RED at their named assertion and restored to the pristine line.
m1, m2, m3 (DOM-planted) are untouched and behaved exactly as P1 recorded.
m4 is untouched and still fires: `dpad_up` routed via (210,58) still puts
`{"leader":"dpad_up","part":"segment","hits":"l2.track"}` into b's detail, and b now goes
PASS -> FAIL, which is a STRONGER proof than the marker P1 had to use on an already-red line.

I CHANGED TWO LINES OF `scripts/showready/ui_geometry.py`, both in the MUTATION PAYLOADS -
the faults that get planted - and NEITHER in what any criterion asserts. I am flagging this
loudly because "change the instrument so the check passes" is exactly the hazard here, and
these changes do the opposite: they RESTORE proof that my own layout change had destroyed.

- m5 was `dpad_right.leader_via = [[240,393]]`, tuned by P1 as a DELIBERATE NEAR MISS: 4.63 px
  against the 6.0 floor with `leader-intersections` still GREEN, so criterion c was the only
  thing that could catch it. Against the new layout that waypoint became an ACTUAL CROSSING:
  measured distance 0, and `leader-intersections` went red too
  (`[["dpad_right","left_stick"],["dpad_right","left_pad"]]`). That is precisely the version
  P1 rejected as proving nothing about c. m5 is now `[[110,282],[234,282]]` - dpad_right's
  corridor dropped from y 262 to 282, three scene units short of left_stick's corridor at 285.
  MEASURED: `1920x1080.closed.c.leader-clearance-6px` FAIL at distance 3.878 px, and it is the
  ONLY failure in the run - `leader-intersections` is GREEN. c is uniquely demonstrated again.
- m6 pushed the card header down `260px` for controls owning an analog group, sized to the
  170 px drawer. Against a full-height 300 px column, 260 px clipped the rows but no longer
  forced the card to scroll, so P1's inverted marker `!"scrollTop":0` failed and the run
  aborted with `m6: inverted marker '"scrollTop":0' is still in the mutated ... line`. The
  push is now `900px`, sized to the new card. MEASURED: `scrollTop` 649 in the mutated line,
  so P1's inverted marker is satisfied unchanged, AND the clipping clause fires as well, AND
  the `unchanged` selectivity assertion (`1024x768.open-btn_a.d.drawer-rows-visible`
  byte-identical to pristine) still holds.

`scripts/showready/SHA256SUMS` re-pinned accordingly: 18 entries, `shasum -a 256 -c` all OK.
The only pinned file whose digest changed is `ui_geometry.py`.

## 7. Criterion f: no regression

- MIDI/product code: `git diff -- windows/midi.py windows/receiver.py windows/config.py
  windows/engines/ protocol/` is EMPTY.
- Map invariants, asserted not assumed: ids, labels, kinds, groups, notes, control ORDER,
  `view_box`, `scene_view_box`, `axis_ranges` and `schema_version` all identical to BASE;
  the `data-control` set in the SVG is the same 23 ids.
- sdauto A4's header: A4's own pinned `docs/sdauto-a4/scripts/header_measure.cjs` at HEAD -
  `1440x900 header_height=48 center_spread_px=1 one_row=true section_select_width=160
  scroll_width=1440 version="v0.5.0 (source)"`, `page_errors=0`. That is A4's recorded 48 px,
  unchanged. (1024x768 reports `header_height=85 one_row=false`, which is A4's own recorded
  pre-existing state - the h1 title wraps inside its `flex: 1` box - not a regression here.)
  I ran the `.cjs` directly against a scratch bridge rather than A4's `header_measure.py`
  wrapper, because that wrapper asserts its output directory is under `/tmp/sdauto-a4`, and
  this lap's rules put my scratch under `/tmp/sdpolish-p2/`. Same instrument, same numbers.
- The live-view checks and every node check: all five exit 0, see Checks.
- Bar 1 A/B for EDM Show on the Mac at HEAD: see Checks.

### The two node-check assertions I had to change, and why

`tests/ui_controller_check.cjs` hard-coded the OLD drawn coordinates in its live-overlay
block, so moving the sticks and pads turned it RED (`305 !== 280`). NAMED, as the rule
requires:

- `'wire zero is centered; sender already subtracts rest offset'` and its siblings asserted
  literal `280`, `175`, `310`, `870`, `145`, `190`, `340`, `350` and `280+.../32649*30`.
  Those literals ARE the map's `left_stick`, `right_stick` and `left_pad` anchors and the
  +/-30 overlay radius. They now read the anchors from `relation`, the map the test already
  loads: `LS.x`, `LS.y`, `LS.x+30`, `RS.x-30`, `RS.y-30`, `LP.x+30`, `LP.y+30`,
  `LS.x+16324/32649*30`, `LS.y+16601/33202*30`, `LS.x+499/32649*30`. THE CLAIM IS UNCHANGED
  and is still the one the message states - that the overlay lands at the control's own
  anchor when the wire says zero, and at the computed offset when it does not. The arithmetic
  is untouched; only "which anchor" stopped being a literal. This is the change that stops
  the same breakage happening to the next person who moves a control.
- `'stick caption stays above the centered live dot'` asserted the literal `y === 153`. The
  L3/R3 captions moved with the sticks to y 168. It now asserts what the message says -
  `caption.getAttribute('y') < dot(its own stick).getAttribute('cy')` - for each caption
  against its own stick. Strictly, this is the property the assertion was named for; the
  literal was a proxy for it.

No other assertion in any node check or in the 1087-test Python suite changed.

## 8. The PNGs

BEFORE at BASE OF LAP `778eaa7` (the geometry instrument run with `--revision
778eaa78441c0e7d5539f540cfed8aa944142f8b`, which reproduced P1's 7984/8175); AFTER at HEAD.
Written to `docs/sdpolish-p2/screenshots/` and copied to
`/Users/viddyslap/Documents/ViddyVault/screenshots/sdpolish-p2/`. 16 files. I opened every
one of them.

| file | what it shows |
|---|---|
| before-1024x768-closed.png | Top bank crowded with six labels; D-pad drawn BELOW the left stick and level with the left trackpad; L1's leader runs straight down through the L2 pill and R1's through R2. |
| before-1024x768-open-btn_a.png | The A card as a short bottom drawer: title, hint and tabs fit, then `BTN_A` is sliced off at the drawer's bottom edge with its value and buttons not drawn at all. This is criterion d's RED. |
| before-1366x768-closed.png | Same picture wider; the L1-through-L2 and R1-through-R2 crossings are still plainly visible at the shoulders. |
| before-1366x768-open-btn_a.png | Card as a right-hand column (1366 is above the 1250 breakpoint) with the same faulty picture beside it. |
| before-1440x900-closed.png | The clearest view of the arrangement fault: reading the left side, stick on top, D-pad beneath it, trackpad beside the D-pad. |
| before-1440x900-open-btn_a.png | Same, card column open, picture squeezed left, leaders unchanged. |
| before-1920x1080-closed.png | Same faults with the most room; this is the viewport where criterion c was already GREEN. |
| before-1920x1080-open-btn_a.png | Same, card open. |
| after-1024x768-closed.png | Four labels on the top bank (L2, L1, R1, R2); SELECT and START now on the side banks; D-pad upper-outer, stick inboard and a little lower, trackpad below both. |
| after-1024x768-open-btn_a.png | The A card as a full-height 300 px column showing the title, both tabs, TAP/`BTN_A` with `ch1 | note 36 vel 127` and its Edit / Open in list / macro controls, and LAYER 2/`BTN_A_LAYER_2` in full. Nothing clipped, nothing scrolled. |
| after-1366x768-closed.png | The new arrangement at the show laptop's own width; L1 and R1 leaders now enter their pills from the inboard side, clear of L2 and R2. |
| after-1366x768-open-btn_a.png | Same with the card column; the picture keeps all 23 labels and leaders. |
| after-1440x900-closed.png | The reference view of the finished picture: SELECT above between D-pad and stick, D-pad's four arms outboard, L3 caption above the stick's live dot, trackpad below, REAR insets inboard-labelled. |
| after-1440x900-open-btn_a.png | Same with the A card open; the live stick dot and trigger bars stay off every label and off the card. |
| after-1920x1080-closed.png | The finished picture with the most room; leader clearance is widest here (18.6 px). |
| after-1920x1080-open-btn_a.png | Same, card open. |

## 9. Checks

| command | result |
|---|---|
| `.venv/bin/python -m unittest discover -s tests -p "test_*.py"` | Ran 1087 tests, OK (skipped=2) |
| `node tests/ui_controller_check.cjs` | exit 0 |
| `node tests/ui_controller_macro_check.cjs` | exit 0 |
| `node tests/ui_reload_check.cjs` | exit 0 |
| `node tests/ui_sections_check.cjs` | exit 0 |
| `node tests/ui_version_check.cjs` | exit 0 |
| `scripts/showready/ui_geometry.sh ... --scratch /tmp/sdpolish-p2/final2 --single-process --mutations` | exit 0; PRISTINE 8175/8175 PASS failures=0; m1-m6 each RED at their named assertion and restored to the pristine line; bridge PID gone=True |
| `scripts/showready/ui_geometry.sh ... --scratch /tmp/sdpolish-p2/before --revision 778eaa7... --pristine-may-fail` | exit 0; PRISTINE 7984/8175, failures=191, all b/c/d - P1's BASE numbers reproduced |
| `node docs/sdauto-a4/scripts/header_measure.cjs <bridge> <chromium> ... p2-after` | 1440x900 header_height=48 center_spread_px=1 one_row=true; page_errors=0 |
| `shasum -a 256 -c scripts/showready/SHA256SUMS` | 18 of 18 OK |
| `git diff -- tests/ui_controller_geometry.cjs` | EMPTY - the criteria file is untouched |
| `git diff -- windows/midi.py windows/receiver.py windows/config.py windows/engines/ protocol/` | EMPTY |
| `scripts/showready/ab_run.py --candidate <this commit> --preset '.showready/fixtures/mac/presets/EDM Show.json' --section windows --script .../deck-script.json` | recorded in section 10 below, measured AFTER this commit exists, because `--candidate` archives a REVISION and not the working tree |

No laptop act: P2 does not touch the laptop, so no guard snapshot, no browser listing, no
bundle. No timing or CPU arm, so the per-arm quiet gate, the vault-sync sample and the
extended load validity do not apply to anything in this link; nothing here is a measurement
of elapsed time or CPU. Mac scratch under `/tmp/sdpolish-p2/` with `.metadata_never_index`
created before the first file was written. `git status --porcelain` is empty after the commit.

## 10. Bar 1 A/B, and a trap worth passing on

`ab_run.py --candidate <rev>` builds the candidate arm with `git archive <rev>`
(`scripts/showready/ab_run.py:236`). IT DOES NOT USE THE WORKING TREE. My first run, started
at 22:00 with `--candidate HEAD` while my changes were still uncommitted, therefore compared
v0.4.9 against P1's commit `5f440be` - my predecessor's code, not mine. It passed (732 steps,
56 of 56 mappings exercised, 1531 messages on each arm, `different_mappings: []`,
`unexercised_mappings: []` in both B1 and B2), which is a true fact about `5f440be` and NOT
evidence about this link. NAMED because it is an easy way to ship a green bar 1 that measured
the wrong tree: unlike `ui_geometry.py`, whose `--revision` defaults to tracked working bytes,
`ab_run.py` has no working-tree mode.

BAR1_RESULT_PLACEHOLDER

## FOR P3 AND THE GATE

- The picture is GREEN on the pinned check without `--pristine-may-fail`. If you see that
  flag in a command, the picture has regressed, not the instrument.
- `scripts/showready/ui_geometry.py` changed in two mutation PAYLOADS (m5's waypoint, m6's
  margin) and `SHA256SUMS` was re-pinned. `tests/ui_controller_geometry.cjs` did NOT change.
  Re-verify with `shasum -a 256 -c scripts/showready/SHA256SUMS`.
- The thinnest measured margin in the whole picture is criterion c at 1024x768 with a card
  open: 6.609 px against a 6.0 floor, btn_y's arrowhead against START's leader, in the
  23-unit corridor between r1's bottom and btn_y's top. Do not move r1, btn_y, START or the
  ABXY cluster without re-running the 1024x768 open states.
- A leader leg that shares an exact x or y with another shape's rect edge reads as a HIT
  through `lineHitsRect`'s near-collinear epsilon even when the two are hundreds of units
  apart. Offset any new leg by a few units.
- P3 changes only which clock bridge timing reads. Nothing in this link touches that, and
  nothing in this link is in the MIDI path, so bar 1 and bar 3 are unaffected by it.
