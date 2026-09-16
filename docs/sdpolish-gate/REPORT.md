BASE OF LAP 778eaa78441c0e7d5539f540cfed8aa944142f8b

# sdpolish GATE

GUARD COMPARE (first line, laptop): see "9. LAPTOP SAFETY" - snapshot GREEN before
the first laptop act, compare GREEN after the last.

BYTE DIFFERENCE AT HEAD: **NONE**. Bar 1 is byte-identical for EDM Show, PTZ and
default on both machines, and `engine_ab.py` is identical on both. Details in "8.
BARS 1 AND 2".

HEAD JUDGED: `a4b2c01a0db154a610111edb83bf581f88c4220e` (this gate's own evidence
commit, whose parent is P3's `e1facbde`; no product code differs between them).

## VERDICT IN ONE PARAGRAPH

Everything this gate was told to prove, it proved. The four show-ready bars this
lap was forbidden to move did not move: MIDI is byte-identical to v0.4.9 for every
mapping in EDM Show and PTZ on both machines, both full suites are green at 1099
tests, and the controller-view work changed no product code outside
`windows/static/`. The three things the lap set out to add are real and are
measured here by instruments that were shown to fire and to stay quiet: the CPU
and crash guards, the geometry criteria, and the one bridge clock. The Windows
clock defect is FIXED by the declared rule - visible at BASE, absent at HEAD. The
layout now matches Valve's own render of the device, which the previous picture
did not. Nothing in this lap is owed to a later link except the three unguarded
`LOCALAPPDATA` subscripts named in 7d, which are a Windows-only instrument
nuisance and touch no shipped code.

---

## 1. SUITES, NODE CHECKS AND THE PIN

| check | command | result |
|---|---|---|
| Mac suite | `cd <run root> && .venv/bin/python -m unittest discover -s tests -p "test_*.py"` | **Ran 1099 tests, OK (skipped=2)**, exit 0 |
| node checks | `node tests/{ui_reload_check,ui_sections_check,ui_controller_check,ui_controller_macro_check,ui_version_check}.cjs` | all five **exit 0** |
| pin | `shasum -a 256 -c scripts/showready/SHA256SUMS` | **19 of 19 OK**, exit 0 |
| Windows suite | `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"` in the clone at HEAD | **Ran 1099 tests, OK (skipped=6)**, rail exit 0, suite pid proved gone |

## 2. GEOMETRY - TWO DETECTORS, AND THEY AGREE EXACTLY

**P1's pinned check at HEAD**, run exactly as the README says and WITHOUT
`--pristine-may-fail`:

```
scripts/showready/ui_geometry.sh --chromium <chrome-headless-shell 1208> \
  --scratch /tmp/sdpolish-gate/geom-head --single-process --mutations \
  --ui-port 17891 --listen-port 47891
```
`PRISTINE 8175/8175 PASS failures=0`, receipt `exit 0`, bridge pid gone.

**The gate's own detector**, `docs/sdpolish-gate/scripts/gate_geometry.cjs`. It
shares no code with `tests/ui_controller_geometry.cjs`: its own DOM extraction,
its own segment/box mathematics (exact segment-segment and segment-box distance,
not a collinearity epsilon), its own criteria and its own output format. It was
written from the app's own sources - `controller_map.json`, `controller_view.js`,
`controller_live.js` and `protocol/messages.py` - and it drives real UDP axis
packets from node so the stick dots are off centre, both trigger bars are
non-zero and the gyro dots are drawn. It never waits on `networkidle`: it waits
for 23 `.controller-label` elements, `#controllerLiveStatus` reading `live`, and
at least two painted trigger bars, and it asserts that live state per measurement
so an obstacle criterion cannot pass vacuously.

| arm | pinned check | the gate's detector |
|---|---|---|
| HEAD | 8175/8175 PASS, failures 0 | **1071/1071 PASS, failures 0**, exit 0 |
| pre-P2 picture | 7984/8175, **191 failures** | 880/1071, **191 failures**, exit 1 |

THE AGREEMENT IS EXACT, NOT APPROXIMATE. On the pre-P2 picture the two detectors
produce failing assertion tag sets that are **set-equal**: 191 = 191, `only
pinned: []`, `only mine: []`. The split is identical criterion by criterion:

| criterion | pinned | gate |
|---|---|---|
| `b.no-leader-through-other-control` | 96 | 96 |
| `c.leader-clearance-6px` | 72 | 72 |
| `d.drawer-rows-visible` | 23 | 23 |

Criterion c's measured minima agree numerically too: across the 96 card-state
measurements at HEAD, **no tag differs by more than 0.05 px**, and both detectors
independently find the same global minimum:

- pinned: **6.6092 px** at `1024x768.open-btn_a`, pair `btn_y.head` / `start.segment`
- gate:   **6.6095 px** at `1024x768.open-btn_a`, pair `btn_y.arrowhead` / `start.segment`

That is P2's claimed thinnest margin (6.609 px, btn_y's arrowhead against START's
leader) confirmed by an instrument P2 never saw. There is no disagreement to
report.

**b, c and d each FAILED before P2**, which is what the gate asked to confirm: 96
b failures, 72 c failures and 23 d failures on the pre-P2 picture, reproducing
P1's and P2's recorded 191/7984 exactly.

FINDING - THE PINNED TOOL'S `--revision` MODE IS BROKEN AT THIS HEAD. The control
could not be run the way P2 ran it. `ui_geometry.py --revision <pre-P3 sha>` copies
the CURRENT tracked file list and pulls each path at that revision, so it dies on
the first file that did not exist then:

```
fatal: path 'windows/clock.py' exists on disk, but not in '5f440be...'
subprocess.CalledProcessError: ... 'git','show','5f440be...:windows/clock.py' ... exit 128
```

This is a tool limitation, not a product defect, and it will bite every future lap
whose control predates a newly added file. The control was therefore reproduced by
serving the pre-P2 static files from a scratch tree and pointing BOTH detectors at
it. That substitution is sound and is proved sound: `git diff --stat 778eaa7
5f440be -- windows/static/` is **empty**, so the picture measured is byte-identical
to BASE OF LAP's picture.

## 3. MUTATIONS

All six planted faults went RED and all six restored to the pristine line. Every
one is the STRONG case - a boolean PASS -> FAIL flip, not a marker - so no
mutation rests on detail text:

| mutation | assertion it flipped | pristine -> mutated |
|---|---|---|
| m1 | `1440x900.closed.own-edge.btn_a` | distance 0.00004 -> **39.243** |
| m2 | `1440x900.closed.label-overlaps` | `[]` -> `[["btn_a","btn_b"]]` |
| m3 | `1440x900.closed.labels-topmost` | `[]` -> `[{"id":"btn_a","by":"SPAN"}]` |
| m4 | `1440x900.closed.b.no-leader-through-other-control` | `[]` -> dpad_up through `l2.shape`, `l2.track`, `l2.bar`, `l1.shape` |
| m5 | `1920x1080.closed.c.leader-clearance-6px` | 18.638 px -> **3.878 px** (`dpad_right.segment`/`left_stick.segment`) |
| m6 | `1024x768.open-r2.d.drawer-rows-visible` | clipped `[]`, scrollTop 0 -> `row1:R2_FULL` overflowing 89 px, scrollTop 649 |

m6 is planted on `r2`, which is neither `btn_a` nor `dpad_up`, as required. Each
restored run returned its line byte for byte and the run exited 0.

## 4. ARRANGEMENT VERDICT - P2 IS RIGHT, AND THE OLD PICTURE WAS WRONG

I fetched Valve's image myself rather than trusting the committed copy:

```
curl -sS -o valve-front.png "https://cdn.fastly.steamstatic.com/steamdeck/images/tech-specs/tech-specs_1_english.png?v=2"
```
sha256 **56f3107c84bc1e91bfcbba71cad63540f12cf7a6d70105f7d4697acb50d592c0**, which
**matches** P2's reference copy `docs/sdpolish-p2/reference/steamdeck-tech-specs-front.png`
byte for byte. Side by side in `docs/sdpolish-gate/arrangement-side-by-side.png`
(Valve's render above, HEAD's 1440x900 card-closed view below). Valve's artwork is
a reference for Ben and is NOT shipped; `steam_deck.svg` remains an original
geometric drawing and embeds none of it.

Control by control, against Valve's own front render:

| control | Valve's device | HEAD | verdict |
|---|---|---|---|
| D-pad | top-left, OUTBOARD, level with the stick | top-left, outboard, level with L3 | MATCHES |
| Left stick (L3) | INBOARD of the d-pad, same row | inboard, same row | MATCHES |
| Left trackpad | below, inboard of the d-pad | below the stick | MATCHES |
| View / SELECT | small capsule above, between d-pad and stick | capsule above-left | MATCHES |
| Right stick (R3) | INBOARD, left of ABXY, same row | inboard, left of ABXY | MATCHES |
| ABXY | OUTBOARD right, diamond Y top / X left / B right / A bottom | same diamond, same orientation | MATCHES |
| Right trackpad | below the right stick | below | MATCHES |
| Menu / START | capsule above the right cluster | capsule above-right | MATCHES |
| L1/L2, R1/R2 | top edge (not in the front render) | drawn above each shoulder | consistent |
| L4/L5, R4/R5 | rear (rear render) | dashed REAR groups below | consistent |

P2's "changed" verdict is **RIGHT**. The pre-P2 picture put the left stick ABOVE
the D-pad and the right stick above ABXY; Valve's render places the d-pad and the
stick SIDE BY SIDE, d-pad outboard. HEAD matches the device and the old picture did
not. I record plainly that my own first reading of the two screenshots guessed the
opposite, and the fetched image is what settled it - which is why the gate requires
fetching it.

## 5. THE ONE BRIDGE CLOCK

`windows/clock.py` defines `now() = time.perf_counter()` and is the only module
under `windows/` permitted to read a stdlib clock.

```
grep -rn "time\.monotonic|time\.perf_counter|time\.time()" windows/ (excluding clock.py)
-> NO MATCHES (exit 1)
```
Every `clock=` default across the bridge is `clock_now`: `receiver.py`, `midi.py`,
`live_events.py` and all 14 engine classes. So every bridge timing comparison
reads one function.

P3's revert proofs, re-run BY NAME in a scratch `git archive` copy:

| revert | test | reverted | restored |
|---|---|---|---|
| a bare `time.monotonic()` planted in `windows/receiver.py` | `BridgeClockSourceScanTests.test_no_module_under_windows_reads_a_stdlib_clock_directly` | **RED** (exit 1) | GREEN (exit 0), file byte-identical |
| `gyro_feedback` clock default back to `time.monotonic` | same scan test | **RED** | GREEN |
| the same revert | `BridgeClockWiringTests.test_every_engine_class_defaults_to_the_bridge_clock` | **RED** | GREEN |

All 12 `tests/test_bridge_clock.py` tests green on the restored copy.

## 5a. THE P0 GUARDS

### idle_smoke, Mac (run WITHOUT `PYSTRAY_BACKEND=dummy`, so the real tray path runs)

| arm | CPU % of one core | exit | crashes | verdict |
|---|---|---|---|---|
| HEAD, sigint | 0.295 | 0.040 s | 0 | **PASS** |
| HEAD, shutdown | 0.295 | 0.086 s | 0 | **PASS** |
| `5f35bbe`, sigint | **94.333** | **15.010 s** | 0 | **FAIL** (required) |

The darwin no-sidecar line is present at HEAD and absent at `5f35bbe`
(`tree_has_a3_fix` false there). The detector fires and does not fire.

THE VAULT SYNC COST THREE ARMS BEFORE THE BASE ARM LANDED. `obsidian-headless
... sync --continuous` (pid 17038) bursts to 82-90% of one core for about 20 s out
of every 60 s. A BASE arm runs about 45 s (30 s idle plus the 15 s hung SIGINT
exit), which does not fit the ~40 s quiet gap, so three attempts were voided by
the instrument's own sampler and preflight - the rule working, not a softening:

| attempt | start | CPU % | exit s | why voided |
|---|---|---|---|---|
| 1 | 23:53:50 | 94.234 | 15.001 | preflight_after `vault sync busy: pcpu 89.4` |
| 2 | 23:59:17 | 94.257 | 15.001 | in-arm sample pid 17038 at 88.8% for 10.1 s |
| 3 | 00:00:56 | 94.265 | 15.004 | in-arm sample pid 17038 at 88.8% for 10.1 s |
| 4 | 00:04:13 | 94.392 | 15.006 | pid 17038 at 90.3% for 15.2 s |
| **5** | **00:05:13** | **94.333** | **15.010** | **VALID - zero breaches, clean preflight** |

The five measurements agree to within 0.16 of a percentage point, so the finding
was never in doubt; only its validity was, and attempt 5 settled it. No
NEEDS-MASTER vault-sync line is owed. Quiet gate before the valid arm: load1 3.82,
vault 1.8%. `.metadata_never_index` was created in every scratch before the first
file was written.

### The real-bridge HTTP check at HEAD

Non-tray bridge, engines ON from a loopback-rewritten scratch copy, dry-run MIDI,
UDP 62778 / TCP 50927 (neither is 45123 or 7723), loopback scan count **0**:

| PUT `update_hz` | status | body |
|---|---|---|
| 0 | **400** | `invalid autopilot config: update_hz must be a number from 1 to 120 (got 0)`, `"field":"update_hz"` |
| -5 | **400** | same shape, `(got -5)` |
| 100000 | **400** | same shape, `(got 100000)` |
| inf | **400** | same shape, `(got inf)` |

`config_unchanged_after_refusals: true` - nothing was written. Then `GET
/api/version` returned **200**, and a following datagram was still recorded as
MIDI: `note_on channel=0 note=36 velocity=127` / `note_off ... velocity=0` (4 MIDI
lines). Process proved gone. The bridge refuses the rate and stays alive.

The loopback scan is not decorative: my first rewrite missed `ptz_visca`'s
`camera_nic_ip` and its `cameras` map, and the check **REFUSED THE BOOT** naming
`192.168.0.100/.203/.204/.205` rather than sending anything at Ben's network.

### The AST tripwire

| tree | count | sites |
|---|---|---|
| BASE OF LAP | **6** | `audio_opacity.py:227`, `audio_opacity.py:239`, `autopilot.py:311`, `autopilot_ptz.py:148`, `chaser_stack_dispatcher.py:190`, `ptz_visca.py:613` |
| HEAD | **0** | - |

Six is MORE than the four the master named (autopilot, audio_opacity,
autopilot_ptz, chaser_stack_dispatcher), so this is a **PASS** under MASTER 13
19:41: the four are a floor, and the sweep also found audio_opacity's second
division and `ptz_visca` - the fifth engine. Each is named with its file:line and
its clamp site in P0's report table.

P0'S REPORT SAYS BOTH REQUIRED THINGS PLAINLY, and I confirm both from the source:

- `ptz_visca` GUARDED ONLY THE ZERO-AND-NEGATIVE END. At BASE, `ptz_visca.py:613`
  reads `base = 1.0 / self._stream_hz if self._stream_hz > 0 else 0.125`, so 0 and
  negatives were already safe there - but there was NO UPPER BOUND, so `stream_hz`
  100000 still produced a 10 microsecond interval. **A guard on one end is not a
  bound.** The clamp at `ptz_visca.py:126` supplies the missing end.
- THE INFINITE SHAPE HAS ITS OWN CASE (P0 report "CASE 3"). An infinite rate makes
  `shortest_tick_interval()` return 0.0, `settimeout(0.0)` puts the socket into
  NON-BLOCKING mode, and `recvfrom` then raises **`BlockingIOError`, which escapes
  the `except socket.timeout` handler** - a different failure from the
  ZeroDivisionError and the ValueError, with a different fix. A test asserts the
  floored timeout leaves the socket BLOCKING, which is that case asserted directly.

### The guard revert sweep - 11 of 11

Each guard reverted alone in a fresh `git archive HEAD` scratch copy, its named
test run, then the copy restored and the test re-run:

| # | guard reverted | test | reverted | restored |
|---|---|---|---|---|
| g01 | autopilot clamp -> raw `float()` | `test_engine_tick_bounds` | RED | GREEN |
| g02 | audio_opacity clamp | `test_engine_tick_bounds` | RED | GREEN |
| g03 | autopilot_ptz clamp | `test_engine_tick_bounds` | RED | GREEN |
| g04 | chaser_stack_dispatcher clamp | `test_engine_tick_bounds` | RED | GREEN |
| g05 | ptz_visca clamp | `test_engine_tick_bounds` | RED | GREEN |
| g06 | `MAX_TICK_HZ` 120 -> 1e9 | `test_engine_tick_bounds` | RED (5 failures) | GREEN |
| g07 | `MIN_SOCKET_TIMEOUT_SECONDS` 0.001 -> 0.0 | `test_engine_tick_bounds` | RED (4 failures) | GREEN |
| g08 | `RATE_FIELDS` emptied (the PUT 400) | `test_engine_config_api` | RED (2 failures) | GREEN |
| g09 | `BACKOFF_SECONDS` 0.001 -> 0.0 | `test_live_events_backoff` | RED (2 failures) | GREEN |
| g10 | darwin gets a sidecar again | `test_tray_main_thread_invariant` | RED | GREEN |
| g11 | darwin `--tray` refusal removed | `test_win_recv_tray_platform` | RED | GREEN |

CORRECTION WORTH RECORDING: my first sweep paired g08 with `test_agent_routes`,
which stayed GREEN under the revert and looked like an unpinned guard. The guard is
pinned - by `tests/test_engine_config_api.py`. **My pairing was wrong, not the
guard**; a revert that goes green is a question about the pairing before it is a
finding about the code.

### Engines ON, and the two sensitivity controls

Every engines-ON arm booted from a loopback-rewritten scratch copy with
**loopback scan count 0**. Autopilot is ACTIVE in my own boot, so the control is
valid by construction and not silently skipped by `shortest_tick_interval()`:

```
INFO engines loaded: Audio Engine(audio_opacity), Autopilot(autopilot), Autopilot PTZ(autopilot_ptz),
Bumper Blast(bumper_blast), Chaser Stack Dispatcher(chaser_stack_dispatcher), Flash Blast(flash_blast),
Global Color(global_color), Gyro Feedback(gyro_feedback), Left Stick Layer(l_stick_layer),
NestDrop(nestdrop), OSC Sync(osc_sync), PTZ VISCA(ptz_visca), StageFlow Bridge(stageflow_bridge),
SteamInput Layer Tracker(steam_input_layer_tracker)
```

| machine | arm | BASE OF LAP | HEAD | scan |
|---|---|---|---|---|
| Mac | engines ON, plain | - | **PASS 1.080%** | 0 |
| Mac | `--engines-update-hz 0` | **FAIL** - bridge died, `ZeroDivisionError: float division by zero` | **PASS 1.112%** | 0 |
| Mac | `--engines-update-hz 100000` | **FAIL 5.304%** | **PASS 1.244%** | 0 |
| laptop | engines ON, plain | - | **PASS 1.606% / 1.652%** | 0 |
| laptop | `--engines-update-hz 0` | **FAIL** - `ZeroDivisionError`, bridge died | **PASS 1.496%** | 0 |
| laptop | `--engines-update-hz 100000` | **FAIL 10.777%** | **PASS 1.762%** | 0 |

BASE fails and HEAD passes on both controls on both machines, so the engines-on arm
is VALID for the engine-tick class on both, and neither machine's arm has to fall
back to the `update_hz 0` substitution P0 flagged as owed.

FINDING - THE 100000 CONTROL IS MARGINAL ON THE MAC AND SHOULD NOT BE TRUSTED
ALONE. P0 measured BASE at **4.883%** and reported it DOES NOT FIRE; I measured
BASE at **5.304%** and it DID fire. Both are correct measurements; they sit either
side of the same 5% bar, and the difference is ambient machine load (my arm ran at
load1 1.88, quieter than P0's). A control whose verdict flips with the load of the
machine is not a dependable detector of the engine-tick class. `update_hz 0` is,
on both machines and in both links' runs: the BASE bridge does not merely get slow,
it dies with a named exception. The README already records `0` as the working
control; that guidance is right and should stay.

INSTRUMENT NOTE: the laptop BASE `hz0` arm reported `cpu=-11.384`, a negative CPU
percentage. It is an artefact of taking a CPU-time delta against a process that
exited mid-measurement. It did not mislead - the arm returned FAIL and named the
`ZeroDivisionError` - but a negative percentage should be reported as "died", not
as a number.

### idle_smoke on the laptop, at HEAD

| arm | CPU % of one core | exit | gone | verdict |
|---|---|---|---|---|
| `--no-ui`, sigint | 0.311 | 0.016 s | yes | PASS |
| UI sidecar, sigint | 0.830 | 0.015 s | yes | PASS |
| UI sidecar, shutdown | 0.362 | 0.343 s | yes | PASS |
| engines ON, sigint | 1.606 | 0.016 s | yes | PASS |
| engines ON, shutdown | 1.652 | 0.187 s | yes | PASS |

The tray sidecar IS available in the rail session on Windows, so no
tray-unavailable evidence is needed. `--cpu-self-test` passed on the laptop before
any arm (busy process read, idle process read 0.0), which is the check P0 added
after finding the Windows reader silently read 0.0% for everything.

## 6. THE PINNED BUNDLE SCRIPT

Guard first. Clone state BEFORE: HEAD `09c42e509162b27f187952d794e4a1206660d90f`,
`PORCELAIN_LINES 0`, branch `chain/steamdeck-20260914`.

```
git bundle create <scratch>/steamdeck.bundle 09c42e5..a4b2c01 chain/steamdeck-20260914
sha256 1b2c77c7602c8c95d4d37aa251a35687b41ef9be53f9795b2fcb91137b841415
```
The laptop recomputed the same sha256. No GitHub fetch was made from the laptop.

| run | `-Expected` | exit | clone HEAD after | porcelain after |
|---|---|---|---|---|
| refusal | `e1facbde...` (a REAL but different commit) | **6** | `09c42e5...` UNCHANGED | **0** UNCHANGED |
| update | `a4b2c01...` (correct) | **0** | `a4b2c01...` | **0** |

Exit 6 is `FETCH_HEAD != -Expected`, exactly the documented code. The refusal
fetched (`FETCH_HEAD a4b2c01`) and then refused to fast-forward, leaving the clone
untouched - which is the behaviour that matters.

## 7. THE WINDOWS BRIDGE CLOCK, MEASURED INDEPENDENTLY

Clone, `--no-ui`-class non-tray bridge, non-default loopback ports. THE MODE: the
bridge's own REAL default clock on both arms. `--clock script` was never used, and
nothing passed `clock=` or `now=`. The instrument is the pinned
`scripts/showready/clock_intervals.py`; because it postdates BASE it was copied
into the BASE tree, and both arms therefore ran the **same instrument sha256
45C80952E9D05C91D4B23D73EAB8CB72DF1475999D9F32056966DA8F27CA4111**. The tree under
test is genuinely BASE: `BASE_HAS_CLOCK_PY False`, `HEAD_HAS_CLOCK_PY True`.

`time.get_clock_info` on the interpreter the bridge runs (Python 3.12.10, win32):

| clock | implementation | resolution |
|---|---|---|
| `monotonic` | `GetTickCount64()` | **0.015625 s** |
| `perf_counter` | `QueryPerformanceCounter()` | **1e-07 s** |

40 ms `relative_cc` repeat, intervals at the MIDI output seam:

| arm | receiver default clock | msgs | p50 ms | p95 ms | max ms | min ms |
|---|---|---|---|---|---|---|
| BASE OF LAP | `time.monotonic` | 75 | **46.3315** | 47.9030 | 47.9755 | 29.8706 |
| HEAD | `windows.clock.now` | 75 | **40.0703** | 41.2220 | 41.4260 | 38.4881 |

A 40 ms repeat scheduled on a 15.625 ms tick cannot land on 40 ms; it lands on
46.875 ms, and BASE's p50 of 46.33 ms is that. HEAD's 40.07 ms is the target.

Macro fade (`--fade-seconds 0.5 --update-hz 120`):

| arm | fade messages | p50 ms | p95 ms | max ms |
|---|---|---|---|---|
| BASE OF LAP | **33** | 15.5136 | 17.4602 | 21.757 |
| HEAD | **115** | 3.7690 | 6.9336 | 29.0776 |

BASE emits a third as many messages, pinned to the 15.625 ms tick; HEAD advances
smoothly. **VERDICT: FIXED** by the declared rule - the effect is VISIBLE at BASE
and ABSENT at HEAD, on both shapes. (P3 measured 45.7533 -> 39.92; I measure
46.3315 -> 40.0703. Same shape, same conclusion, independently.)

THE MAC SHOWS NO REGRESSION, under the LOAD RULES:

| arm | clock | p50 ms | p95 ms | max ms | msgs |
|---|---|---|---|---|---|
| BASE OF LAP | `time.monotonic` | 39.9487 | 40.9512 | 41.0956 | 75 |
| HEAD | `windows.clock.now` | 40.0606 | 41.0367 | 41.3166 | 75 |

0.112 ms apart. Both arms VALID: quiet gate load1 3.52 and 3.59 before, 3.59 and
3.38 after, every reading under the 5.0 cap; vault sync 0.0-0.2% throughout. On
macOS BOTH clocks are `mach_absolute_time()` at 4.1667e-08 s, which is exactly why
the Mac cannot show the defect and the laptop can.

## 7b. ENGINE A/B AND WINDOWS IDLE CPU

`engine_ab.py` re-run by this gate at HEAD on both machines:

| machine | preset | exit | passed |
|---|---|---|---|
| Mac | EDM Show (`--section windows`) | 0 | true |
| Mac | PTZ (`--section windows`) | 0 | true |
| laptop | EDM Show (windows-installed) | 0 | true |
| laptop | PTZ (windows-installed) | 0 | true |

Per-engine sensitivity controls, all RED with `control_expected: true`:

| control | Mac | laptop |
|---|---|---|
| `sensitivity-autopilot` | exit 1 RED | exit 1 RED |
| `sensitivity-l_stick_layer` | exit 1 RED | exit 1 RED |
| `sensitivity-audio_opacity-osc` | exit 1 RED | exit 1 RED |

AUDIO_OPACITY'S OSC CALLS ARE COMPARED, not just its MIDI: the coverage table
records `audio_opacity` as `{"midi": 0, "osc": 58}` identically on all three arms
(A, B_nostate, B_state) for EDM Show - the engine emits no MIDI at all, so if OSC
were not compared its row would be zero observations, which the instrument treats
as RED. Perturbing that OSC goes RED, on both machines. The autopilot control's
perturbation is visible in the coverage table itself: arm A
`column_notes_dropped=1, reemitted=5, midi=5, osc=1474` against the B arms'
`dropped=0, reemitted=4, midi=4, osc=1592`.

`engine_ab.py` runs with `LOCALAPPDATA` unset **on the Mac** (exit 0; the subscript
sites are behind `os.name == 'nt'`). On the laptop it does not - see 7d.

WINDOWS IDLE CPU, v0.4.9 tag tree vs HEAD (same instrument copied into the v0.4.9
tree; `V049_HAS_CLOCK_PY False`):

| arm | v0.4.9 | HEAD | delta |
|---|---|---|---|
| `--no-ui` | 0.000% | 0.206% | +0.206 pts - **UNATTRIBUTED** |
| UI sidecar | **77.900%** (FAIL) | **0.411%** (PASS) | **-77.5 pts** |

The `--no-ui` delta is 0.006 of a point over the 0.2 threshold, so by the rule it
is reported as UNATTRIBUTED rather than explained: I did not take thread
attribution for it. It is a 30 s sample of a near-idle process, a v0.4.9 reading of
exactly 0.0% is at the reader's floor, and both numbers are more than an order of
magnitude under the 5% bar. The UI arm is the one that matters and it runs the
other way by two orders of magnitude: the tray-thread defect this lap fixed costs
**77.9% of one core** on Windows at v0.4.9 and **0.411%** at HEAD.

## 7c. THE NO-PUSH FORM, MEASURED AT BOTH ENDS

| reading | GATE START (2026-09-15 23:34:48) | GATE END | changed? |
|---|---|---|---|
| `git ls-remote origin main` | `5d778eb90a2baa85b98ffa9ff11571a9aca0ce39` | see below | - |
| `git ls-remote --tags origin` | 42 lines, highest `v0.4.9` (peeled `e66ff44`) | see below | - |
| `git tag --list 'v0.5*'` | EMPTY | see below | - |

Filled in at the end of this report under "GATE-END READINGS".

## 7d. THE LOCALAPPDATA SWEEP

`grep -rn LOCALAPPDATA scripts/ tests/` at MY OWN HEAD (`a4b2c01`, run 00:48:06):
**COUNT = 20 lines**. The unguarded `os.environ['LOCALAPPDATA']` SUBSCRIPTS are
**THREE**, the same three the orchestrator found at 23:22, none fixed and none new:

| site | shape | still unguarded? |
|---|---|---|
| `scripts/showready/ab_run.py:28` (`default_scratch`) | inside `if os.name == 'nt':` | **YES** |
| `scripts/showready/ab_run.py:33` (`validate_scratch`) | conditional expression, `nt` branch | **YES** |
| `tests/test_showready_instrument.py:74` | conditional expression, `nt` branch | **YES** |
| `scripts/showready/engine_ab.py:119` | `environ.get` + `TEMP`/`TMP` fallback | no - P0 fixed it |

No fourth or fifth Python subscript exists at my HEAD, so the number three is a
census at this commit and not just a repeat of the earlier one. The other 16 lines
are prose, a `win_guard.ps1` comment, a README line, two PowerShell
`$env:LOCALAPPDATA` uses in `scripts/windows/build_installer*.ps1` (PowerShell
returns `$null` rather than raising, so they are a different hazard class), and the
assertions in `tests/test_engine_ab_scratch_default.py`.

RUN ON THE LAPTOP AT HEAD WITH `LOCALAPPDATA` UNSET: **exit 1,
`KeyError: 'LOCALAPPDATA'`**. This is the KNOWN state and it does NOT fail this
gate. P0 fixed `engine_ab.py`'s own parser default; `engine_ab.py` imports
`validate_scratch` from `ab_run`, so the KeyError now comes from `ab_run.py:33`,
exactly where P3 said it would. WITH THE VARIABLE SET, the Windows engine A/B runs
identical for EDM and PTZ with both sensitivity controls RED, as P3 measured.

## 8. BARS 1 AND 2 AT HEAD

BAR 1 - byte-identical MIDI. One shared 47,039-packet script
(`script_sha256 f6611e7e191ff59376cc81a9bf299d13f9cce9479bb3a0ec06159a366a99cd5f`,
732 steps, 469.7 s of scripted time).

| machine | preset | arm | identical | mappings | messages A / B | different | unexercised |
|---|---|---|---|---|---|---|---|
| Mac | EDM Show | B1 | **true** | 56/56 | 1531 / 1531 | 0 | 0 |
| Mac | EDM Show | B2 (sectioned) | **true** | 56/56 | 1531 / 1531 | 0 | 0 |
| Mac | PTZ | B1 | **true** | 52/52 | 1395 / 1395 | 0 | 0 |
| Mac | PTZ | B2 (sectioned) | **true** | 52/52 | 1395 / 1395 | 0 | 0 |
| Mac | default | B1 | **true** | 56/56 | 1531 / 1531 | 0 | 0 |
| laptop | EDM Show (installed) | B1 | **true** | 56/56 | 1531 / 1531 | 0 | 0 |
| laptop | PTZ (installed) | B1 | **true** | 52/52 | 1395 / 1395 | 0 | 0 |
| laptop | default (installed) | B1 | **true** | 56/56 | 1531 / 1531 | 0 | 0 |

THE DEAD-SEAM CONTROL IS RED AT HEAD: exit 1, `passed: false`, 0 messages on both
arms, 56 mappings unexercised. Bytes "matched" and the instrument still refused to
credit the run, which is the whole point of that control.

BAR 2 - both suites green at HEAD: Mac **1099 OK (skipped=2)**, Windows **1099 OK
(skipped=6)**. See section 1.

## 9. LAPTOP SAFETY

| check | result |
|---|---|
| guard, FIRST laptop act | `GUARD GREEN: snapshot; protected state observed; pythonProcesses=0`, exit 0 |
| guard, LAST laptop act | `GUARD GREEN: compare; protected state observed; pythonProcesses=0`, **exit 0** |
| browsers (read-only Win32_Process, SessionId + CreationDate) | **NO chrome.exe / msedge.exe / firefox.exe IN ANY SESSION** - so no browser was created in Ben's session 1, and none was stopped |
| python under clone or work root | `PYTHON_TOTAL 0 LANE_LEFTOVER 0` - nothing lane-started left running |
| PROCESS-CLASS ORDER (protected tested FIRST) | (i) PROTECTED **98**, (ii) RECORDED 0, (iii) LANE_PATH_UNRECORDED **0**, (iv) NOT_LANE 172 |
| protected state still there | tray pids 5268 and 23640 (session 1, created 08/16/2026 00:29:37) and loopMIDI pid 16020 (created 08/16/2026 00:29:31) - all predate this gate and were never touched |

No process was stopped on the laptop by this gate: no class (ii) process existed
and no class (iii) process existed, so nothing was a candidate. The installed
tray, loopMIDI, UDP 45123 and TCP 7723 were never touched; every bridge this gate
started used ports it checked free first.

ONE DELIBERATE ADDITION TO THE CLONE, RECORDED. `engine_ab.py` died in 0.019 s on
the laptop with `FileNotFoundError: ...\.showready\fixtures\mac\MANIFEST.sha256`
because the clone had **no `.showready` directory at all** - the fixture tree the
instrument verifies before reading any preset was simply absent. I transferred it
over the rail as a zip (sha256 `92f7ee51cb2b2bc755c58a93ed0974767920411a6d57678265cebc65605a1f12`,
recomputed identical on the laptop) and expanded it into the clone's `.showready/`.
That path is gitignored: the clone's `git status --porcelain` is **0 lines**
before and after. The presets in it are copies and were never modified. It is left
in place, because removing it would only recreate the failure for the next link.

## 10. THE PNGs

Written to `docs/sdpolish-gate/screenshots/` and copied to
`/Users/viddyslap/Documents/ViddyVault/screenshots/sdpolish-gate/`. All were taken
with the live stream up and the overlays drawn (stick dots pushed off centre, both
trigger bars filled, gyro pitch/yaw/roll dots), never on a dead stream.

| file | what it shows |
|---|---|
| `after-1024x768-card-closed.png` | HEAD, narrowest viewport, card closed: 23 labels in four banks, no leader crossing another control, live bars blue in L2/R2 |
| `after-1366x768-card-closed.png` | HEAD, card closed: same arrangement, wider gutters, X's elbow clear of the Right stick bend |
| `after-1440x900-card-closed.png` | HEAD, card closed, the reference view used in the side-by-side: d-pad outboard-left beside L3, ABXY outboard-right beside R3 |
| `after-1920x1080-card-closed.png` | HEAD, card closed, widest viewport: the same picture with the most clearance (criterion c minimum is largest here) |
| `after-1024x768-card-open-btn_a.png` | **criterion d's case**: at 1024x768 with A open, the card is a 300 px SIDE COLUMN showing title "A", the Mappings/Advanced tabs, and BOTH the TAP (BTN_A) and LAYER 2 (BTN_A_LAYER_2) rows, with nothing clipped and scrollTop 0 |
| `after-1366x768-card-open-btn_a.png` | HEAD, card open: side column, full rows visible, picture shrinks rather than the card scrolling |
| `after-1440x900-card-open-btn_a.png` | HEAD, card open at the reference size |
| `after-1920x1080-card-open-btn_a.png` | HEAD, card open, most generous case |
| `before-1440x900-card-closed.png` | **BASE OF LAP**: left stick ABOVE the d-pad and right stick above ABXY - the arrangement Valve's render contradicts - with L1's leader running down through the L2 shape and R1's through R2 |
| `arrangement-side-by-side.png` | Valve's official render above, HEAD's 1440x900 card-closed below, for Ben to compare directly |

(`before-1024x768`, `before-1366x768` and `before-1920x1080` card-closed were also
captured and are included for completeness.)

OBSERVATION, NOT A REGRESSION: every screenshot's status bar reads `Load failed:
HTTP 500`. `GET /api/actions` returns 500 in MY scratch layout because PyYAML is
absent from the Mac venv AND the JSON fallback looks for `actions.yaml` beside the
`--map` file, which in this layout is the presets directory. It is **identical at
BASE and at HEAD**, it is a property of how the gate's own scratch bridge was
pointed, and it touches no criterion. Recorded so nobody reads it as a P2 defect.

SECOND PRE-EXISTING OBSERVATION: with `--no-engines`, every axis datagram logs
`ERROR engine_registry.on_axis_event failed / AttributeError: 'NoneType' object has
no attribute 'on_axis_event'`. The call site is byte-identical at v0.4.9
(`receiver.py:870`), BASE (`:896`) and HEAD (`:901`), it is caught by a
`try/except`, and it is what Ben already runs. **Pre-existing, not introduced this
lap, and it moves no bar** - but it is one caught exception per axis event and is
worth a future lap's attention.

## 11. PICK-UP

| check | result |
|---|---|
| every link pushed | P0, P1, P2, P3 all push-verified; this gate pushed and verified too |
| `git status --porcelain` | EMPTY |
| `git diff --stat 778eaa7 HEAD` | 93 files, +6395 / -257 |
| areas touched | `docs/` 42, `windows/engines` 17, `tests/` 15, `scripts/` 8, `windows/static/` 4, and single files `win_recv.py`, `receiver.py`, `preset_watch.py`, `midi.py`, `live_events.py`, `engine_config_api.py`, `clock.py` - all within the permitted set |
| `windows/config.py` | **UNTOUCHED** - no mapping-semantics change |
| routes | no `@app.route` or `add_url_rule` line added or removed BASE..HEAD |
| `windows/preset_watch.py` | clock seam only: `import time` -> `from windows.clock import now as clock_now`, `time.monotonic()` -> `clock_now()` |
| Ben's Mac files | `EDM Show.json` **58e47bfd**, `PTZ.json` **11b37cd6**, `bridge.local.json` **7476c269** - all unchanged |
| processes | Mac: `pgrep windows.win_recv` 0, `chrome-headless-shell` 0. Laptop: see section 9 |

## 12. FOR BEN, IN PLAIN WORDS

The candidate is ready for you to test, and nothing in this lap moved the things
you said must not move.

Your MIDI is unchanged. Every mapping in EDM Show and in PTZ produces exactly the
same bytes as v0.4.9 - 1,531 messages for EDM Show and 1,395 for PTZ, identical on
both arms, on your Mac and on the show laptop, with nothing left untested. The
full test suite passes on both machines, 1,099 tests each.

Three things got better. First, the CPU problem you asked about cannot come back
quietly: a bad rate in a config file used to either crash the bridge or spin a core
at 94%, and now it is clamped where it is set, refused at the API with a message
naming the field, and caught by a test that fails if anyone removes the guard. On
the show laptop the old build burned 78% of a core just sitting there with its
window open; the new one uses 0.4%. Second, the controller picture now matches the
real Steam Deck - I fetched Valve's own product render and checked it control by
control, and the old picture had the sticks in the wrong place. Nothing overlaps,
nothing is hidden, and at the smallest screen size you can open a control and see
its title, its tabs and both its action rows without scrolling. Third, the timing
jitter on Windows is fixed: a 40 ms repeat used to land at 46 ms because the old
clock only ticked every 15.6 ms, and now it lands at 40 ms. Fades are smooth
instead of stepping - 115 updates where there used to be 33.

Two things you should know. The machine's Obsidian vault sync bursts to about 90%
of a core every minute, which voided four CPU measurements before one landed
cleanly; the measurements all agreed anyway, so the result is solid, but that sync
is why this took longer than it should. And there is a small instrument annoyance -
three places in the test scripts assume a Windows environment variable exists -
which affects only a developer tool, never the bridge you run at the show.

Nothing was pushed to `main`, nothing was merged, no tag and no release was
created. The only branch touched is `chain/steamdeck-20260914`, and I checked the
remote at the start and the end of this gate to prove it.

---

## GATE-END READINGS

Item 7c, the no-push form, MEASURED at both ends rather than promised:

| reading | GATE START 23:34:48 | GATE END 01:53:53 | verdict |
|---|---|---|---|
| `git ls-remote origin main` | `5d778eb90a2baa85b98ffa9ff11571a9aca0ce39` | `5d778eb90a2baa85b98ffa9ff11571a9aca0ce39` | **UNCHANGED** (`diff` empty) |
| `git ls-remote --tags origin` | 42 lines, highest `v0.4.9` (peeled `e66ff44b36eadb6d43db01680c65279df82cd63c`) | 42 lines, byte-identical | **UNCHANGED** (`diff` empty) |
| `git tag --list 'v0.5*'` | EMPTY | **EMPTY** | as required |

No `main` push, no deploy-branch push, no merge, no tag and no release happened
during this gate, by measurement of both endpoints and not by assertion. The only
ref this gate wrote is `chain/steamdeck-20260914`.

PROCESSES AT GATE END - Mac: `windows.win_recv` 0, `chrome-headless-shell` 0,
`ab_run.py` 0, `idle_smoke.py` 0. Laptop: see section 9.

## WHAT THIS GATE COST, AND WHY

Recorded because a run's own friction is a measurement about the run.

- THE VAULT SYNC voided **four** Mac CPU arms (one HEAD arm and three BASE arms)
  between 23:48 and 00:06 with bursts of 82-90% of one core. The fifth BASE attempt
  landed valid. The remedy that worked was a burst-aware launcher that waits for a
  burst to END before starting an arm, buying the longest quiet window; it is worth
  keeping for any later lap that measures CPU on this Mac.
- THE QUESTION I RAISED about how to resolve the BASE arm did **not** stop the
  link: I launched the retry loop at 00:00:56 before asking, and it completed at
  00:06 while the question was still open, so the work and the question overlapped
  rather than queueing. The answer confirmed the option I had already taken.
- TWO SETUP DEFECTS cost laptop time and are worth naming so the next link avoids
  them: piping `git archive` through a PowerShell pipeline **corrupts the byte
  stream** (`tar.exe: Damaged tar archive`, hundreds of retries), so a tree must be
  materialised with `git archive --format=zip -o <file>` and `Expand-Archive`; and
  the laptop clone had no `.showready` fixtures, which makes every `engine_ab.py`
  arm die in 19 milliseconds with an error that names a manifest rather than the
  real cause.
