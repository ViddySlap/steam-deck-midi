GUARD COMPARE OWED: laptop ssh new sessions timed out from 03:55 (retry at 04:03 also timed out, `ssh_dispatch_run_fatal ... fe80::fa1d:ffeb:3115:a0d6%en0 port 22: Operation timed out`); the guard snapshot at the first laptop act was GREEN (`GUARD GREEN: snapshot; protected state observed; pythonProcesses=0`), the compare after the last act could not run. NEEDS-MASTER.

# sdlive EG - independent gate: controller view live half, show-ready bars

BASE OF LAP 14aa21824843dbe148dc3ac3d0bf58929ef34c3a (from docs/sdlive-e0/REPORT.md line 2; line 1 there is E0's guard result).
Entry HEAD 19016931cb70cbe4a546c42c09130f2bb7d38a39 (E4). Gate commits: 51b1d5b (test-only instrument fix, see below),
5f98123 (evidence so far, MASTER 03:10), and the final commit carrying this report. Product bytes (windows/ protocol/
config/ deck/) are identical at 1901693, 51b1d5b and 5f98123 (`git diff --stat 1901693 51b1d5b -- windows protocol config deck` empty).

## Verdict in plain words

- BAR 3 IS RED on the locked rule (Mac, real Chromium, R=5, qualified, sensitivity-proven): p99 |OPEN-CLOSED| 2.818 ms > noise floor 0.021 + 1.0 ms; p50 and p95 within; bytes identical; foreign_lines 0 on all 15 arms. Held for the declared M_bridge chain (MASTER 04:00).
- Windows timing is DIAGNOSTIC: the pinned 2 ms control cannot produce a valid arm on Windows; the approved every-10th control reported rule_passed false but its per-statistic result is OWED. The qualifying, sensitivity-proven bar 3 is the Mac's.
- The live half works in a real browser: 1a-1f 34/34 PASS, closed means closed, Follow default OFF and paused over unsaved edits, row flash on the exact row within 11 ms, stress 60 s at 60 Hz with clicks opening cards in 6-79 ms.
- Geometry holds with the stream live and overlays drawn (126/126, two planted faults RED); the pinned geometry instrument cannot measure the live view (two instrument defects, owed).
- Bar 1 holds on the Mac (EDM Show, PTZ, default byte-identical to v0.4.9, independently re-checked) and the laptop instrument reported pass for the Windows-installed EDM Show, PTZ and default (independent re-check OWED).
- Seam proven: the pinned recorder sits directly below E1's forward-first wrapper (9,644 = 9,644, planted drop RED); dead seam RED at HEAD.
- Mutations (a)-(d) all RED and restored GREEN. E0's causal chain matches the code; contract identical; Windows 300x re-proof and the two Windows suites are OWED (ssh).
- One test-only instrument defect found and fixed (51b1d5b, Windows no-op BROWSER opened the default browser), accepted by MASTER 02:58.

## 0. Mac suite, node checks, pins (HEAD 1901693, repeated after 51b1d5b)

| Command | Result |
| --- | --- |
| `shasum -a 256 -c scripts/showready/SHA256SUMS` at 1901693 | exit 0, 15 OK |
| `TMPDIR=/tmp/sdlive-gate/mac PYSTRAY_BACKEND=dummy BROWSER=/usr/bin/true .venv/bin/python -B -m unittest discover -s tests -p 'test_*.py'` at 1901693 | exit 0, `Ran 901 tests in 14.229s`, `OK (skipped=2)` |
| same, after 51b1d5b | exit 0, `Ran 902 tests in 14.356s`, `OK (skipped=2)`; again before the final commit: `Ran 902 tests in 14.228s`, `OK (skipped=2)`, four node checks exit 0, pins 15 OK |
| `node tests/ui_controller_check.cjs` (both times) | exit 0, `UI controller behavior: PASS (...)` |
| `node tests/ui_controller_macro_check.cjs` | exit 0, 48 disk writes match, 72 refused |
| `node tests/ui_reload_check.cjs` | exit 0, PASS |
| `node tests/ui_sections_check.cjs` | exit 0, PASS |
| `node tests/ui_controller_geometry.cjs` (fifth node check) | see 1g: exit 1 against the default live Controller (instrument defect) |
| `shasum -a 256 -c scripts/showready/SHA256SUMS` after 51b1d5b | exit 0, 15 OK |

## Finding A (fixed, test-only, 51b1d5b): the Windows "no-op" BROWSER opened the default browser

Observed on the laptop Edge sensitivity attempt 1 (before the fix): the OPEN arm counted `clients=2` from its first sample,
and the next CLEAN run's CLOSED arm (no client started) ended with snapshot `clients=1`. Cause, measured:
`windows/win_recv.py:425` calls `_open_browser_delayed(ui_server.url)` for every non-tray UI start;
Python `webbrowser.open` tries BROWSER first and falls through to `windows-default` when it returns False.
Probe `laptop/wbprobe.py` (first entry only, never the fallback): `C:/Windows/System32/cmd.exe /c rem %s` -> `False`
with "The syntax of the command is incorrect."; `cmd.exe /c exit 0 %s` False; `cmd.exe /d /c rem.%s` False;
`<venv python> -c pass %s` True. The laptop's default http handler is `ChromeHTML`.
Fix (under 20 lines, obvious cause, no product/MIDI/statistics change): `scripts/showready/timing_ab.py` `NOOP_BROWSER`
(Windows: the running Python with `-c pass %s`), the same value in `tests/test_live_events.py`'s real win_recv subprocess,
new test `TimingTests.test_bridge_noop_browser_command_really_succeeds`, SHA256SUMS repinned (timing_ab.py
df8b45cd -> 93e4d2b1). After the fix the Edge OPEN arm counts exactly 1 client and bridge logs have no cmd.exe error.
Revert control on Windows: OWED TO THE NEXT LAPTOP LINK: `browserfix_red.ps1` (old string -> RED, HEAD -> GREEN) was queued but its ssh session timed out (L23). The Mac GREEN of the new test is in the 902-test suite; the RED only exists on Windows.
MASTER 02:58 accepted it; only timing arms and Mac controls run after 51b1d5b count below. `windows/win_recv.py` has no
`--no-browser` flag (grep: none), so the exit-0 BROWSER is the only available guard; ab_run arms run `--no-ui`.
Whether a window ever reached Ben's desktop during the pre-fix runs is UNVERIFIED (Windows does not log process creation by default).

## 1. Real bridge + simulated sender + real Chromium (Mac)

Bridge: `docs/sdlive-gate/scripts/bridge.py start --tree /tmp/sdlive-gate/br-51b1d5b --rev 51b1d5b --ui-port 18862 --listen-port 48862`
(full `git archive`, byte copies of the verified Mac fixtures, EDM Show active, `--preset-section windows --dry-run --no-engines
--no-pulse --no-osc-relay`, PYSTRAY_BACKEND=dummy, BROWSER=/usr/bin/true), stopped by SIGTERM, `gone=True` by os.kill(pid,0).
Sender: compact sorted-key UDP JSON, the pinned deck-script packet encoding, monotonic seq, heartbeats every 100 ms.
Browser: headless Chromium (chromium_headless_shell-1208, playwright-core 1.58.2), 1440x900, fresh context.
Command: `node docs/sdlive-gate/scripts/live_gate.cjs http://127.0.0.1:18862 <chromium> /tmp/sdlive-gate/live-final` -> exit 0, `SUMMARY 34/34 PASS`.

| Case | Observation (from the DOM, computed style and the bridge's own /api/live/snapshot) | Result |
| --- | --- | --- |
| 1a highlight | BTN_A down: `[data-control=btn_a]` shape and label gain `control-down` in 28 ms; computed fill rgb(34,40,64) -> rgb(74,158,255), label bg rgb(28,33,48) -> rgb(42,90,154); snapshot `pressed:["BTN_A"]`; card stays closed (Follow off). Up: cleared, fill back to idle. | PASS |
| 1a layer 2 | L2_SOFT_LAYER_2 down: L2 shape+label lit, tag text `L2` visible; up clears | PASS |
| 1b stick | L_STICK_X 32767, Y 0: dot cx=310 cy=175 = anchor (280,175) + (30,0) travel, exact right-edge centre (tolerance 5 percent = 3 units) | PASS |
| 1b trigger | R_TRIGGER_PRESSURE 32768: bar width 32.0005 of 64 = 0.500 | PASS |
| 1b trackpad | L_PAD_X/Y at about 60 Hz for 1 s: computed opacity 1 on 8 of 8 samples after the first; after the stream stops the dot reaches opacity 0 in 380 ms (300 ms hold + 80 ms fade) | PASS |
| 1c row flash | D-pad Up card open; DPAD_UP_LONG_PRESS down: snapshot MIDI rows attributed to DPAD_UP_LONG_PRESS (CC 22 ramp); long-press row gains `controller-midi-flash` 11 ms after the UDP send; DOM sampled at +50 ms: `{DPAD_UP:false, DPAD_UP_LONG_PRESS:true}`; tap row never flashed in the following 1 s | PASS |
| 1d default | fresh context: `#controllerFollow` aria-pressed false, text "Follow: off" | PASS |
| 1d follow | toggle ON (7 ms); BTN_Y down opens card titled Y in 16 ms | PASS |
| 1d paused | inline edit of BTN_Y note typed 99 (unsaved); BTN_X down lights X but card stays Y, field keeps 99, note "follow paused: unsaved edit" visible | PASS |
| 1e closed | click List -> snapshot `clients` 0 at the first poll (1 ms); back to Controller -> 1 in 23 ms; status "offline" while List | PASS |
| 1f stress | 13 axes at 60 Hz for 60.24 s (3600 ticks, 47,397 axis packets, 59.76 Hz) with the page live | see below |
| 1f responsiveness | 12 label clicks every 5 s, click-to-card-open 79, 8, 25, 12, 16, 7, 15, 7, 16, 6, 18, 14 ms (all <= 500) | PASS |
| 1f heap | CDP JSHeapUsedSize after forced GC 1,505,100 -> 2,545,368 bytes (+1,040,268); Nodes 2702 -> 6996; listeners 250 -> 511 | recorded |
| 1f drops | bridge snapshot `dropped` 0 -> 58,675 (history overwrite, allowed); page EventSource: 31,534 data events, 0 dropped events; still "live", 0 JS errors | recorded |
| JS errors | none in 1a-1e or 1f | PASS |

Heap/DOM growth is not live-view retention: `docs/sdlive-gate/scripts/card_growth.cjs` (24 card opens, no input, post-GC)
plateaus after the first 8 distinct cards at BASE 14aa218 (2622 -> 6916 nodes, 234 -> 495 listeners) and HEAD (2706 -> 6996, 246 -> 507),
flat for the next 16 opens on both. Cards are built once per control, pre-existing sdview behaviour.

### 1g. Geometry with the live view connected

- Pinned wrapper, README command with gate scratch: `scripts/showready/ui_geometry.sh --chromium <chromium> --scratch /tmp/sdlive-gate/geometry-pinned --single-process --mutations`
  -> exit 2 `scratch must be under /tmp/sdfix-<link>/` (`scripts/showready/ui_geometry.py:27-28`). INSTRUMENT DEFECT 1: the pinned wrapper cannot run in any sdlive scratch.
- Pinned detector direct against the default live Controller: `node tests/ui_controller_geometry.cjs http://127.0.0.1:18864 <chromium> --single-process --out /tmp/sdlive-gate/geometry-detector-live`
  -> exit 1 after 30.5 s, `page.goto: Timeout 30000ms exceeded ... waiting until "networkidle"` (`tests/ui_controller_geometry.cjs:118`). INSTRUMENT DEFECT 2: networkidle never arrives while the Controller holds its EventSource. It measured nothing.
- What E2/E3/E4's 1048/1048 runs measured, from code: `docs/sdlive-e2/geometry_preload.cjs` seeds `steamdeck.mappingView=list` on every context, so networkidle arrives with no stream;
  the detector then clicks `#viewController` (line 119) and measures after two animation frames with the stream just opened, overlays at rest (no dot pushed, bars zero width), never waiting for "live".
- Independent script `docs/sdlive-gate/scripts/geom_live.cjs` (default Controller entry, waits for 23 labels AND `live`, never networkidle; drives L stick up-right, R stick full right/down,
  L2 100 percent, R2 70 percent, gyro pitch/yaw; asserts bridge snapshot `clients==1`): 1440x900 and 1024x768, card closed and open on A, Left stick and R2.
  `node docs/sdlive-gate/scripts/geom_live.cjs http://127.0.0.1:18864 <chromium> /tmp/sdlive-gate/geom-live` -> exit 0, `SUMMARY 126/126 PASS`; restored rerun exit 0 126/126.
  Every state measured 23 labels/shapes/leaders/arrowheads, 13 displayed glyphs (3 live gyro captions), 9 visible live overlays, status live.
  Checks: zero label overlaps, zero leader crossings, every leader endpoint within 3 px of its own shape and inside no other, no glyph under any leader or arrowhead,
  no live overlay (dots, bars, tracks, gyro) over any glyph, label or the open card, labels topmost by hit test, inside the pane, card inside the pane with no label under it, no scroll.
  Detector fires: `--mutation overlay-on-label` (right stick dot moved onto the A label) exit 1 at `live-overlays-cover-no-glyph-label-or-card`; `--mutation label-overlap` exit 1 at `label-overlaps-zero` and `labels-topmost-hit-test`.
  Info, not a stated criterion: in all 8 states the L1 and R1 leaders pass over the L2/R2 trigger tracks and bars (4 contacts per state); visible in after-1 PNG.
- Fix owed to the next lap that touches the check: FOR BEN.

## 2. PNGs (docs/sdlive-gate/screenshots/ and ViddyVault/screenshots/sdlive-gate/), each opened and inspected

| File | What it shows |
| --- | --- |
| before-base-14aa218-same-input-held.png | BASE (sdview tip) with A down, left stick up-right and R2 70 percent held over UDP: static picture, A unlit, no dots, no bars, no Follow/live tools (snapshot of DOM: aDown false, 0 dots, 0 bars) |
| after-1-a-lit-stick-upright-r2-70-live.png | HEAD: A shape blue with label "A tap", left-stick dot up-right inside L3, R2 bar about 70 percent blue, "Follow: off" and "live" |
| after-1b-hold-same-input-as-before.png | HEAD, same held input as BEFORE via the BEFORE script: A lit, left dot up-right, R2 bar; right stick and gyro dots keep the last values from the earlier stress run on that bridge |
| after-2-dpad-up-long-press-row-flash.png | D-pad Up card, LONG PRESS row mid-flash (blue), TAP row not, D-pad Up label "hold" and shape lit |
| after-3-follow-on-card-opened-by-press.png | "Follow: on", Y card opened by the BTN_Y press, Y lit, its TAP row flashing from Y's MIDI |
| after-3b-follow-paused-unsaved-edit.png | Y card with note field 99 being edited, X lit "tap", card did not switch, "follow paused: unsaved edit" shown |
| after-4-offline-indicator.png | same page after the bridge was stopped: "offline" indicator, dots back at centre |
| geometry-live-1440x900-closed.png | independent geometry state, live, sticks pushed, both bars drawn |
| geometry-live-1024x768-open-btn_a.png | 1024x768 with A card open at the bottom, live overlays drawn |

## 3a. Pinned workload checks (Mac)

| Command | Result |
| --- | --- |
| `.venv/bin/python -B scripts/showready/deck_script.py --out /tmp/sdlive-gate/deck-script.json` | exit 0, script 9256621a..., 732 steps, 47,039 packets (matches README logical SHA) |
| `.venv/bin/python -B scripts/showready/timing_subset_check.py scripts/showready/timing_script.json /tmp/sdlive-gate/deck-script.json` | exit 0, 15,370 steps, 20,513 packets, 245 encodings |
| `.venv/bin/python -B docs/sdlive-gate/scripts/subset_gate.py scripts/showready/timing_script.json /tmp/sdlive-gate/deck-script.json` (independent: decoded (kind, action, state, value) tuples) | exit 0, 0 foreign of 20,513 packets + 15,370 steps; 246 deck tuples |
| same with `--plant-foreign` (L_STICK_X value 12347 in packet and step) | exit 1, 2 foreign (packet 124, step 124) |
| worst-case segment count (same script) | `simultaneous-sticks-triggers-60hz`: 2,520 ticks, every tick exactly 6 events {L/R stick X/Y, L/R trigger} |
| laptop: pins test, deck_script, timing_subset_check (clone at 51b1d5b) | exit 0 each; laptop deck script f6611e7e differs from 9256621a only in Windows path separators in `parameters` and CRLF source hashes; packets, steps and packet-stream digest identical (compared on the Mac) |

## 3b/3/5. Bar 3 on the Mac (QUALIFYING: real Chromium; plus Python diagnostic)

Load gate per arm: `docs/sdlive-gate/scripts/foreign_load.py` sampled every about 2.5 s throughout (load1 from `sysctl -n vm.loadavg`, foreign_lines per MASTER 01:11, pgrep); the per-arm value is the last sample before the arm's `start` file and the maximum during the arm.
The instrument's own pgrep checks ran before and after every arm (all `empty`). The first attempt at 03:10 was stopped at 03:15 because e155 (harness) appeared and r2 CLOSED started with foreign_lines=1; its result is retained as INVALID
(`mac-sensitivity-INVALID-foreign-load-try1.json.gz`) and nothing from it counts. Retry started 03:19:50 after 60 s of foreign_lines 0.

All Mac arms below: candidate 5f98123 (product = 51b1d5b), instrument `scripts/showready/timing_ab.py` sha256 93e4d2b1184474008651242cb065b1e912dcbac7f0481204d0a08c47546a7876 (every arm's embedded instrument digest), timing_script.json ffd4e267, script clock, speed 1, EDM Show windows section, macOS Python 3.12.

### Sensitivity (QUALIFYING control): real Chromium, R=3, 2 ms publisher delay

Command: `.venv/bin/python -B scripts/showready/timing_ab.py --candidate 5f98123 --script scripts/showready/timing_script.json --repeats 3 --control sensitivity --scratch /tmp/sdlive-gate/mac-sensitivity --out /tmp/sdlive-gate/mac-sensitivity.json.gz --client-cmd '["node",".../timing_browser.cjs","{url}","{stop}","{receipt}","<chromium>","--single-process"]'` -> exit 1 (expected), wall 691 s.
`measurement_qualified` True, `sensitivity_timing_red` True, bytes identical across all 9 arms, all arms VALID, raw sha256 4128b9de (the receipt hash the clean run validated). Recomputed from raw samples by `timing_table.py`: equal to the instrument's summary.

| Mac sensitivity (ms) | p50 | p95 | p99 | max |
| --- | --- | --- | --- | --- |
| CLOSED pooled (n=28914) | 1.184 | 120.974 | 1659.039 | 2039.370 |
| OPEN pooled (n=28914) | 5133.665 | 10347.232 | 10985.262 | 11155.389 |
| CLOSED-B pooled (n=28914) | 1.238 | 120.700 | 1659.231 | 2042.214 |
| CLOSED worst-case segment (n=27048) | 1.165 | 1.678 | 1.847 | 19.003 |
| OPEN worst-case segment (n=27048) | 5508.410 | 10382.357 | 10997.202 | 11155.389 |
| CLOSED-B worst-case segment (n=27048) | 1.215 | 1.709 | 1.877 | 16.069 |
| NOISE FLOOR abs(CLOSED - CLOSED-B) | 0.054 | 0.274 | 0.191 | - |
| abs(OPEN - CLOSED) | 5132.481 | 10226.258 | 9326.222 | - |
| within floor + 1.0 ms | False | False | False | - |

Per-repeat inequalities (p50/p95/p99, Y within): r1 NNN, r2 NNN, r3 NNN
Top outliers (ms, arm, causal action): 11155.4 OPEN R_TRIGGER_PRESSURE; 11151.8 OPEN R_STICK_Y_AXIS; 11151.1 OPEN L_TRIGGER_PRESSURE; 11150.5 OPEN R_TRIGGER_PRESSURE; 11148.7 OPEN R_TRIGGER_PRESSURE

| Repeat | Arm | Load (instrument pgrep before/after) | foreign_lines at start / max during | load1 at start | Timed MIDI | p50 | p95 | p99 | max | Stream dropped | Clients | Publisher dropped |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | CLOSED | verified ['empty']/['empty'] | 0 / 0 | 2.93 | 9638 | 1.116 | 120.328 | 1659.976 | 2038.725 | None | None | 23990 |
| 1 | OPEN | verified ['empty']/['empty'] | 0 / 0 | 2.69 | 9638 | 4888.030 | 9859.579 | 10273.910 | 10381.708 | 0 | [1, 1] | 23990 |
| 1 | CLOSED-B | verified ['empty']/['empty'] | 0 / 0 | 3.04 | 9638 | 1.204 | 120.091 | 1658.933 | 2036.872 | None | None | 23990 |
| 2 | CLOSED | verified ['empty']/['empty'] | 0 / 0 | 7.49 | 9638 | 1.260 | 119.616 | 1659.223 | 2039.370 | None | None | 23990 |
| 2 | OPEN | verified ['empty']/['empty'] | 0 / 0 | 5.81 | 9638 | 5256.776 | 10607.608 | 11046.299 | 11155.389 | 0 | [1, 1] | 23990 |
| 2 | CLOSED-B | verified ['empty']/['empty'] | 0 / 0 | 4.82 | 9638 | 1.282 | 119.573 | 1660.617 | 2042.214 | None | None | 23990 |
| 3 | CLOSED | verified ['empty']/['empty'] | 0 / 0 | 3.96 | 9638 | 1.199 | 119.141 | 1656.261 | 2035.770 | None | None | 23990 |
| 3 | OPEN | verified ['empty']/['empty'] | 0 / 0 | 4.42 | 9638 | 5265.823 | 10602.097 | 11035.843 | 11148.669 | 0 | [1, 1] | 23990 |
| 3 | CLOSED-B | verified ['empty']/['empty'] | 0 / 0 | 4.09 | 9638 | 1.244 | 120.007 | 1659.109 | 2035.091 | None | None | 23990 |

RESULT: the 2 ms control FAILS the rule at p50, p95 and p99. The instrument can see a 2 ms delay on the Mac (step 5: not blind).

### Clean (QUALIFYING): real Chromium, R=5, Controller view open, Follow ON

Command: same client argv, `--repeats 5 --scratch /tmp/sdlive-gate/mac-clean --out /tmp/sdlive-gate/mac-clean.json.gz --sensitivity-result /tmp/sdlive-gate/mac-sensitivity.json.gz` -> exit 1, wall 1135 s.
`measurement_qualified` True, `sensitivity_valid` True, bytes identical across all 15 arms, all 15 arms VALID (9,638 timed MIDI each; worst segment 9,016 each), every OPEN arm's browser and client PIDs proved gone, `bar3_counts` False because the rule failed.

| Mac clean (ms) | p50 | p95 | p99 | max |
| --- | --- | --- | --- | --- |
| CLOSED pooled (n=48190) | 1.113 | 121.400 | 1658.738 | 2041.797 |
| OPEN pooled (n=48190) | 1.138 | 122.177 | 1661.555 | 2041.318 |
| CLOSED-B pooled (n=48190) | 1.107 | 121.166 | 1658.717 | 2043.130 |
| CLOSED worst-case segment (n=45080) | 1.094 | 1.527 | 1.695 | 15.803 |
| OPEN worst-case segment (n=45080) | 1.117 | 1.564 | 1.765 | 15.406 |
| CLOSED-B worst-case segment (n=45080) | 1.088 | 1.500 | 1.680 | 16.636 |
| NOISE FLOOR abs(CLOSED - CLOSED-B) | 0.006 | 0.233 | 0.021 | - |
| abs(OPEN - CLOSED) | 0.025 | 0.777 | 2.818 | - |
| within floor + 1.0 ms | True | True | False | - |

Per-repeat inequalities (p50/p95/p99, Y within): r1 YYY, r2 YYN, r3 YYN, r4 YYN, r5 YYN
Top outliers (ms, arm, causal action): 2043.1 CLOSED-B DPAD_RIGHT_LONG_PRESS; 2041.8 CLOSED-B DPAD_LEFT_LONG_PRESS; 2041.8 CLOSED L_PAD_RIGHT_LONG_PRESS; 2041.5 CLOSED L_PAD_LEFT_LONG_PRESS; 2041.3 OPEN DPAD_RIGHT_LONG_PRESS

| Repeat | Arm | Load (instrument pgrep before/after) | foreign_lines at start / max during | load1 at start | Timed MIDI | p50 | p95 | p99 | max | Stream dropped | Clients | Publisher dropped |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | CLOSED | verified ['empty']/['empty'] | 0 / 0 | 3.93 | 9638 | 1.166 | 119.221 | 1659.377 | 2038.625 | None | None | 23990 |
| 1 | OPEN | verified ['empty']/['empty'] | 0 / 0 | 3.2 | 9638 | 1.137 | 118.136 | 1658.348 | 2039.363 | 0 | [1, 1] | 23990 |
| 1 | CLOSED-B | verified ['empty']/['empty'] | 0 / 0 | 2.75 | 9638 | 1.111 | 119.469 | 1655.252 | 2037.901 | None | None | 23990 |
| 2 | CLOSED | verified ['empty']/['empty'] | 0 / 0 | 1.95 | 9638 | 1.088 | 119.960 | 1658.404 | 2038.609 | None | None | 23990 |
| 2 | OPEN | verified ['empty']/['empty'] | 0 / 0 | 1.75 | 9638 | 1.140 | 120.160 | 1663.168 | 2041.318 | 0 | [1, 1] | 23990 |
| 2 | CLOSED-B | verified ['empty']/['empty'] | 0 / 0 | 1.8 | 9638 | 1.100 | 120.420 | 1661.156 | 2043.130 | None | None | 23990 |
| 3 | CLOSED | verified ['empty']/['empty'] | 0 / 0 | 2.25 | 9638 | 1.111 | 119.876 | 1656.840 | 2038.723 | None | None | 23990 |
| 3 | OPEN | verified ['empty']/['empty'] | 0 / 0 | 2.58 | 9638 | 1.141 | 120.646 | 1652.120 | 2039.456 | 0 | [1, 1] | 23990 |
| 3 | CLOSED-B | verified ['empty']/['empty'] | 0 / 0 | 2.45 | 9638 | 1.101 | 120.251 | 1658.834 | 2038.420 | None | None | 23990 |
| 4 | CLOSED | verified ['empty']/['empty'] | 0 / 0 | 3.63 | 9638 | 1.100 | 120.366 | 1654.846 | 2041.797 | None | None | 23990 |
| 4 | OPEN | verified ['empty']/['empty'] | 0 / 0 | 2.04 | 9638 | 1.123 | 120.136 | 1661.001 | 2041.083 | 0 | [1, 1] | 23990 |
| 4 | CLOSED-B | verified ['empty']/['empty'] | 0 / 0 | 2.13 | 9638 | 1.130 | 119.227 | 1657.955 | 2038.127 | None | None | 23990 |
| 5 | CLOSED | verified ['empty']/['empty'] | 0 / 0 | 1.79 | 9638 | 1.116 | 120.327 | 1658.060 | 2035.409 | None | None | 23990 |
| 5 | OPEN | verified ['empty']/['empty'] | 0 / 0 | 1.93 | 9638 | 1.149 | 120.497 | 1662.072 | 2040.739 | 0 | [1, 1] | 23990 |
| 5 | CLOSED-B | verified ['empty']/['empty'] | 0 / 0 | 2.62 | 9638 | 1.096 | 119.325 | 1660.436 | 2038.620 | None | None | 23990 |

**BAR 3 ON THE MAC IS RED on the locked rule: p99 |OPEN-CLOSED| = 2.818 ms > floor 0.021 + 1.0 = 1.021 ms.** p50 (0.025 vs 1.006) and p95 (0.777 vs 1.233) are within. MASTER 04:00: reported RED, not re-scored.

Explanation only, not mitigation (`docs/sdlive-gate/scripts/p99_decompose.py /tmp/sdlive-gate/mac-clean.json.gz`, diagnostic): split each message's latency at the send time of the last scripted event before it into a sender part (in-process simulated sender, send of cause to send of that event) and a receiver part (that send to the MIDI record). p99 sender part: CLOSED 1526.056, OPEN 1529.585, CLOSED-B 1526.908 ms; p99 receiver part: CLOSED 173.004, OPEN 172.894, CLOSED-B 172.317 ms. Sender pacing drift at the last event per repeat: CLOSED [466.95, 529.551, 491.204, 496.572, 507.458], OPEN [671.788, 643.329, 559.632, 651.077, 569.246], CLOSED-B [502.422, 517.13, 493.742, 515.441, 544.51] ms. The p99 population is the intentional ~1.5-2 s long-press fades; the six-axis worst-case segment moves +0.023/+0.037/+0.070 ms at p50/p95/p99. Per MASTER 04:00 this split does not separate the rig from the bridge: the "receiver part" starts at sendto, so kernel delivery and bridge wake-up sit inside it, but the extra sender drift with a browser attached shares the bridge process (GIL/CPU) and can also be a real browser effect. The declared M_bridge = t3 - t1 rule belongs to a later chain; this gate did not edit the instrument for it.

### Mac Python client (DIAGNOSTIC, R=1)

`timing_ab.py --candidate 5f98123 --repeats 1 --scratch /tmp/sdlive-gate/mac-diagnostic --out /tmp/sdlive-gate/mac-diagnostic.json.gz` -> exit 78 HARNESS-SKIP (no receipt, Python client), numeric rule passed, all 3 arms verified load, bytes identical.

| Mac Python diagnostic (ms) | p50 | p95 | p99 | max |
| --- | --- | --- | --- | --- |
| CLOSED pooled (n=9638) | 1.115 | 118.987 | 1662.265 | 2040.487 |
| OPEN pooled (n=9638) | 1.118 | 119.654 | 1657.589 | 2039.320 |
| CLOSED-B pooled (n=9638) | 1.146 | 119.579 | 1657.273 | 2035.153 |
| CLOSED worst-case segment (n=9016) | 1.098 | 1.515 | 1.709 | 3.469 |
| OPEN worst-case segment (n=9016) | 1.098 | 1.528 | 1.725 | 4.681 |
| CLOSED-B worst-case segment (n=9016) | 1.124 | 1.544 | 1.719 | 5.283 |
| NOISE FLOOR abs(CLOSED - CLOSED-B) | 0.031 | 0.593 | 4.993 | - |
| abs(OPEN - CLOSED) | 0.003 | 0.667 | 4.677 | - |
| within floor + 1.0 ms | True | True | True | - |

Per-repeat inequalities (p50/p95/p99, Y within): r1 YYY
Top outliers (ms, arm, causal action): 2040.5 CLOSED DPAD_UP_LONG_PRESS; 2039.3 OPEN L_PAD_RIGHT_LONG_PRESS; 2039.3 OPEN L_PAD_LEFT_LONG_PRESS; 2038.1 CLOSED DPAD_DOWN_LONG_PRESS; 2036.9 OPEN DPAD_LEFT_LONG_PRESS


### Dead-client control (Mac, after 51b1d5b)

`timing_ab.py --candidate HEAD --repeats 1 --control dead-client --client-cmd <chromium argv>` -> exit 1, `DEAD CLIENT: snapshot clients=0`, arm INVALID, bridge pid gone (evidence/mac/mac-dead-client.json.gz).


## 4. Bar 3 on the laptop

**Windows bar 3 is DIAGNOSTIC (MASTER 02:58 and 04:00). The qualifying, sensitivity-proven bar 3 is the Mac's.** The laptop HAD a real browser (existing Microsoft Edge 153.0.4234.32 headless via the existing playwright-core 1.58.2 in `life-os-tbex-chain`, Node v24.14.1, no install); Edge timing was measured, but no Windows sensitivity control qualified, so no Windows timing earns bar 3 credit. Ben's bar 4 hardware check cannot see millisecond delay.

Laptop: Windows 11 10.0.26200, i9-13900HX 32 logical, Python 3.12.10 venv, clone at 51b1d5b (bundle), instrument digest 93e4d2b1 (embedded per arm; `.gitattributes` keeps LF), Windows load checks `not applicable` by design. Guard snapshot GREEN before the first laptop act (L0).

| Run (after 51b1d5b unless stated) | Client | R | Arms | Outcome |
| --- | --- | --- | --- | --- |
| sensitivity attempt 1 (before 51b1d5b, does not count) | Edge | 3 | CLOSED valid; OPEN INVALID | OPEN counted 2 clients (default-browser fallback), bridge died: recorder `Dropped, reordered or foreign UDP packet at 4318` |
| clean attempt 1 (before 51b1d5b, does not count) | Edge | 5 | CLOSED passed=false | CLOSED ended with snapshot clients=1 with no client started (Finding A) |
| pinned 2 ms whole-stream sensitivity | Edge | 3 | r1 CLOSED valid, r1 OPEN INVALID | recorder `... UDP packet at 4492`: the planted delay overflows Windows UDP intake; clients exactly 1 |
| pinned 2 ms whole-stream sensitivity | Python | 3 | r1 CLOSED valid, r1 OPEN INVALID | recorder `... UDP packet at 4597`: same limit, not Edge-specific |
| MASTER 02:58 control: 2 ms on every 10th published event, scratch commit cc4c769 (windows/live_events.py only) | Edge | 3 | all 9 VALID | instrument stdout `rule_passed: false, exit_code 1`; declared expectation p95 and p99 FAIL. Per-statistic outcome OWED: result download truncated when ssh failed (gzip unexpected EOF). Reported as-is. |
| clean | Edge | 5 | all 15 VALID, bytes identical, measurement_qualified | rule RED at p95/p99 with OPEN LOWER than CLOSED (noise), exit 1 |
| clean | Python | 5 | all 15 VALID, bytes identical | numeric rule passes, exit 78 (no valid receipt); p95 floor 147 ms |

Edge clean (ms), command `timing.ps1 -Phase clean` (README body; `--fixtures`/`--preset` point at the verified W4 fixture copy under sdwin\fixtures), wall 1653 s:

| Laptop Edge clean (ms) | p50 | p95 | p99 | max |
| --- | --- | --- | --- | --- |
| CLOSED pooled (n=48190) | 6.970 | 232.097 | 1658.349 | 2120.630 |
| OPEN pooled (n=48190) | 5.697 | 201.923 | 1641.658 | 2029.971 |
| CLOSED-B pooled (n=48190) | 6.475 | 206.995 | 1648.281 | 2086.906 |
| CLOSED worst-case segment (n=45080) | 6.771 | 94.110 | 177.410 | 414.557 |
| OPEN worst-case segment (n=45080) | 5.477 | 72.217 | 146.333 | 310.365 |
| CLOSED-B worst-case segment (n=45080) | 6.209 | 89.696 | 160.715 | 335.321 |
| NOISE FLOOR abs(CLOSED - CLOSED-B) | 0.496 | 25.103 | 10.068 | - |
| abs(OPEN - CLOSED) | 1.274 | 30.174 | 16.691 | - |
| within floor + 1.0 ms | True | False | False | - |

Per-repeat inequalities (p50/p95/p99, Y within): r1 YYY, r2 YYY, r3 YNY, r4 YNY, r5 YYY
Top outliers (ms, arm, causal action): 2120.6 CLOSED DPAD_UP_LONG_PRESS; 2118.2 CLOSED DPAD_DOWN_LONG_PRESS; 2114.4 CLOSED DPAD_UP_LONG_PRESS; 2098.3 CLOSED DPAD_DOWN_LONG_PRESS; 2088.8 CLOSED DPAD_UP_LONG_PRESS

| Repeat | Arm | Load (instrument pgrep before/after) | Timed MIDI | p50 | p95 | p99 | max | Stream dropped | Clients | Publisher dropped |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | CLOSED | verified ['not applicable']/['not applicable'] | 9638 | 7.767 | 128.720 | 1656.434 | 2050.015 | None | None | 23990 |
| 1 | OPEN | verified ['not applicable']/['not applicable'] | 9638 | 6.433 | 144.528 | 1640.047 | 2018.489 | 0 | [1, 1] | 23990 |
| 1 | CLOSED-B | verified ['not applicable']/['not applicable'] | 9638 | 6.384 | 169.911 | 1640.898 | 2019.976 | None | None | 23990 |
| 2 | CLOSED | verified ['not applicable']/['not applicable'] | 9638 | 6.797 | 236.144 | 1637.569 | 2021.880 | None | None | 23990 |
| 2 | OPEN | verified ['not applicable']/['not applicable'] | 9638 | 5.496 | 177.845 | 1637.159 | 2029.971 | 0 | [1, 1] | 23990 |
| 2 | CLOSED-B | verified ['not applicable']/['not applicable'] | 9638 | 5.598 | 175.896 | 1647.898 | 2034.182 | None | None | 23990 |
| 3 | CLOSED | verified ['not applicable']/['not applicable'] | 9638 | 6.785 | 302.827 | 1650.158 | 2029.106 | None | None | 23990 |
| 3 | OPEN | verified ['not applicable']/['not applicable'] | 9638 | 5.543 | 144.394 | 1642.083 | 2025.251 | 0 | [1, 1] | 23990 |
| 3 | CLOSED-B | verified ['not applicable']/['not applicable'] | 9638 | 5.743 | 204.031 | 1669.511 | 2086.906 | None | None | 23990 |
| 4 | CLOSED | verified ['not applicable']/['not applicable'] | 9638 | 7.360 | 171.512 | 1694.209 | 2120.630 | None | None | 23990 |
| 4 | OPEN | verified ['not applicable']/['not applicable'] | 9638 | 6.036 | 265.950 | 1643.129 | 2026.224 | 0 | [1, 1] | 23990 |
| 4 | CLOSED-B | verified ['not applicable']/['not applicable'] | 9638 | 7.001 | 221.242 | 1641.470 | 2051.503 | None | None | 23990 |
| 5 | CLOSED | verified ['not applicable']/['not applicable'] | 9638 | 5.845 | 192.583 | 1638.542 | 2081.919 | None | None | 23990 |
| 5 | OPEN | verified ['not applicable']/['not applicable'] | 9638 | 5.200 | 160.892 | 1640.271 | 2015.550 | 0 | [1, 1] | 23990 |
| 5 | CLOSED-B | verified ['not applicable']/['not applicable'] | 9638 | 7.184 | 244.377 | 1643.474 | 2020.187 | None | None | 23990 |

Python clean (ms), `timing.ps1 -Phase clean -PythonClient`, wall 1703 s:

| Laptop Python clean (ms) | p50 | p95 | p99 | max |
| --- | --- | --- | --- | --- |
| CLOSED pooled (n=48190) | 7.200 | 202.163 | 1651.483 | 2041.131 |
| OPEN pooled (n=48190) | 6.991 | 341.968 | 1642.611 | 2048.397 |
| CLOSED-B pooled (n=48190) | 6.446 | 349.638 | 1643.331 | 2056.578 |
| CLOSED worst-case segment (n=45080) | 6.976 | 86.287 | 163.812 | 271.028 |
| OPEN worst-case segment (n=45080) | 6.733 | 104.051 | 240.593 | 607.405 |
| CLOSED-B worst-case segment (n=45080) | 6.165 | 141.050 | 293.493 | 697.973 |
| NOISE FLOOR abs(CLOSED - CLOSED-B) | 0.754 | 147.474 | 8.152 | - |
| abs(OPEN - CLOSED) | 0.209 | 139.804 | 8.872 | - |
| within floor + 1.0 ms | True | True | True | - |

Per-repeat inequalities (p50/p95/p99, Y within): r1 YYY, r2 YYN, r3 YNN, r4 YYY, r5 YYN
Top outliers (ms, arm, causal action): 2056.6 CLOSED-B L_PAD_RIGHT_LONG_PRESS; 2048.4 OPEN DPAD_LEFT_LONG_PRESS; 2047.4 OPEN DPAD_RIGHT_LONG_PRESS; 2041.1 CLOSED DPAD_UP_LONG_PRESS; 2040.1 CLOSED DPAD_DOWN_LONG_PRESS

Windows latency itself is higher than the Mac's in every arm (worst-segment p50 about 5.5-7 ms vs 1.1 ms), independent of OPEN/CLOSED.
Every laptop timing phase recorded its owned descendant tree (python, node, msedge) every 2 s and proved each gone after exit (`owned-tree-*.txt`, `LAUNCHER ... ALIVE 0`); Edge root pids also proved gone by the driver's own Get-Process check per OPEN arm.


## 4b. Seam below the wrapper

`docs/sdlive-gate/scripts/seam_probe.py run 51b1d5b scripts/showready/timing_script.json /tmp/sdlive-gate/seam-clean`: one bridge process (unchanged pinned capture_runner, `--clock script`, EDM Show windows),
runtime observers log every call E1's `LiveMidiOut._tap` forwards (as raw bytes) and whether each `Recorder.send` runs inside that forward. 20,513 packets replayed in order.
Result exit 0: recorded 9,644 MIDI rows, forwarded 9,644, identical ordered bytes, 9,644 of 9,644 recorder sends inside a wrapper forward, bridge pid gone. So the recorder sits directly BELOW the wrapper and sees exactly what it forwards.
Detector fires: `--plant-drop 50` exit 1, recorded 9,643 vs forwarded 9,644, first difference index 49.
Dead-seam control at HEAD: `ab_run.py --candidate 51b1d5b --preset '.showready/fixtures/mac/presets/default.json' --script /tmp/sdlive-gate/deck-script.json --control dead-seam` -> exit 1, 0 MIDI on both arms, 56 unexercised mappings; `bar1_verify.py` on it exit 1.

## 4c. Windows clock

Read: sender timestamps `scripts/showready/timing_ab.py:237-264` (`time.perf_counter_ns()`), recorder `scripts/showready/capture_runner.py:52` (`time.perf_counter_ns()` stored as monotonic_ns), latency `timing_ab.py:220` (recorder minus send, same PID). No `time.monotonic` in the latency path.
Windows sensitivity: the pinned 2 ms whole-stream control cannot produce a valid arm on Windows (UDP intake overflow, bridge terminated by the recorder, with Edge and with Python). The approved every-10th-event control ran with 9 VALID arms and the instrument reported `rule_passed: false`; which statistics failed is OWED (download truncated). A Windows bar 3 pass without a Windows sensitivity FAIL does not count, so Windows bar 3 is DIAGNOSTIC.
E3's finding for Ben (source read, unchanged here): the bridge itself uses `time.monotonic` (`windows/receiver.py` `_clock` default, fades, relative repeats, staged work; `windows/engines/base.py`; `windows/midi.py` feedback). On the laptop's Python 3.12 that is GetTickCount64 at 15.625 ms (W4 probe), so fade steps, repeat batching and engine timing can quantize to about 16 ms in the real show. The timing instrument's `--clock script` bypasses that clock, so bar 3 does not measure it.

## 6. Mutations (scratch copies of 51b1d5b; none touch the repo)

`docs/sdlive-gate/scripts/mutations.py 51b1d5b /tmp/sdlive-gate/mac/mutations.json` -> exit 0 (every RED observed and every restore GREEN). Restored bytes compared by SHA256.

| Mutation | Check | RED | Restored |
| --- | --- | --- | --- |
| (a) forward MIDI after publish + `time.sleep(0.005)` in publish | `-m unittest -v tests.test_live_events` | exit 1, 5 failures incl. `test_all_methods_forward_exact_arguments_before_publish_including_panic`, `test_full_buffer_and_stalled_stream_leave_all_thousand_midi_calls_identical`, `test_stalled_tcp_reader_cannot_hold_server_stop` | exit 0 |
| (a) same fault as scratch commit 87a2172 | `timing_ab.py --repo /tmp/sdlive-gate/mut-a-repo --candidate HEAD --repeats 1` | exit 1: CLOSED arm INVALID, recorder raised `Dropped, reordered or foreign UDP packet at 7794` (receiver fell behind); pgrep empty before/after | clean Mac runs above |
| (b) handle_datagram publishes out-of-order packets | `tests.test_live_events` | exit 1, `test_rejected_packets_heartbeat_and_duplicate_publish_nothing` | exit 0 |
| (c) EventSource stays open when hidden (`disconnect()` removed from sync) | `node tests/ui_controller_check.cjs` | exit 1 `AssertionError: hiding Controller closes EventSource` (ui_controller_check.cjs:691) | exit 0 |
| (c) real browser, mutated bridge | `live_gate.cjs` step 1e | exit 1: `1e: List view -> zero live clients within 2 s` FAIL, clients stayed 1 for 2005 ms | 34/34 pristine run above |
| (d) Follow default ON | `node tests/ui_controller_check.cjs` | exit 1 `AssertionError: follow defaults OFF` (:531) | exit 0 |
| (d) real browser, mutated bridge | `live_gate.cjs` | exit 1: `1d: Follow default OFF on a fresh profile` FAIL (aria true) | 34/34 |

## 6b. The flaky Windows test (E0)

Causal chain checked against code (BASE 14aa218): the test sends POST/PATCH/BOGUS bodies to /api/settings (`tests/test_deck_control_api.py:275-285`);
`_request` returns 405/404 at `deck/control_api.py` BASE lines 370-372 before the body read at 379; BOGUS goes through `send_error` 501->405 (356-359); `_json` writes (347-354);
stdlib `TCPServer.shutdown_request` then SHUT_WR + close with the declared body unread, which races the client's send on Windows (reset 10053/10054).
Fix `deck/control_api.py:347-362` `finish()` drains a valid positive Content-Length up to 1 MiB with a 3 s timeout inside try/finally, and :396 marks the normal read. No retries, sleeps, swallowed resets, platform skips or loosened assertions (the only except is `ValueError` on a malformed Content-Length -> size 0). `git diff 14aa218 HEAD --stat -- deck/`: 18 insertions, control_api.py only.
Contract, re-run by the gate: `PYTHONHASHSEED=0 .venv/bin/python -B docs/sdlive-e0/scripts/contract.py <BASE product + HEAD test file> contract-base.json contract-tests.json` exit 0 (23 tests, 120 responses);
HEAD vs BASE exit 0 `CONTRACT IDENTICAL`; planted 405 message change in a HEAD scratch copy exit 1 `CONTRACT DIFFERENT` at responses 57-58.
Laptop counts: OWED (laptop ssh down from 04:03): 300x `test_malformed_json_and_unsupported_method_are_json` at HEAD and at the archived pre-fix BASE, and two consecutive full Windows suites at HEAD, were queued (`flake_gate.ps1`, `suite.ps1`) and never connected. E0's own counts stand as E0's (55/300 and 66/300 BASE, 0/300 HEAD, two suites 868 OK); not re-measured by the gate.

## 7. Bars 1 and 2 at HEAD

Mac, `ab_run.py --candidate 51b1d5b ... --script /tmp/sdlive-gate/deck-script.json` (script clock, speed 1, four runs concurrent), independently re-checked by `docs/sdlive-gate/scripts/bar1_verify.py` from raw (step, bytes) rows (exit 0):

| Preset (Mac fixtures) | Arms | Packets per arm | MIDI A / B1 / B2 | Mapped MIDI | Bytes vs v0.4.9 | PIDs gone |
| --- | --- | --- | --- | --- | --- | --- |
| EDM Show (sectioned, windows) | A e66ff44 flat, B1 flat, B2 section | 47,039 digest c06cfa67 | 1531 / 1531 / 1531 | 1525 | identical | yes |
| PTZ (sectioned, windows) | A, B1, B2 | 47,039 | 1395 / 1395 / 1395 | 1389 | identical | yes |
| default | A, B1 | 47,039 | 1531 / 1531 | 1525 | identical | yes |

Laptop (Windows-installed fixtures, clone at 51b1d5b): ran to completion before ssh failed (L22, exit 0 each, all 3 launcher PIDs and 15 descendant python PIDs proved gone by Get-Process):

| Preset (windows-installed fixtures) | Instrument stdout | Mappings exercised | MIDI A / B1 |
| --- | --- | --- | --- |
| EDM Show.json | passed true, no different/unexercised | 56 / 56 | 1531 / 1531 |
| PTZ.json | passed true | 52 / 52 | 1395 / 1395 |
| default.json | passed true | 56 / 56 | 1531 / 1531 |

The gate's independent raw re-check (`bar1_verify.py`) of these three Windows results is OWED: the JSON files are on the laptop (`sdwin\sdlive-gate\ab-win-*.json.gz`) and were not downloaded before ssh failed.
Windows suite: OWED (see 6b). No Windows suite was run by the gate at 51b1d5b.

## 8. Pick-up

| Row | Result |
| --- | --- |
| every link pushed | E0-E4 envelopes list their pushes; `ls-remote` = local HEAD after each gate commit (51b1d5b, 5f98123, final) |
| porcelain | empty after each gate commit (`git status --porcelain | wc -l` = 0) |
| excluded paths since BASE | `git diff --name-only 14aa218 HEAD` filtered for local settings, bridge.local, engines, state, non-default presets, .showready: none (grep exit 1) |
| `git diff 14aa218 HEAD -- windows/config.py mac/` | 0 lines |
| windows/midi.py | 0 diff lines since BASE |
| windows/receiver.py hunks (25+/6-) | all hooks: `field` import and `windows.live_events` import; fade dataclass `action` field defaulting to `current_action`; `live_events=None` ctor param stored; axis publish after seq/heartbeat acceptance before `_handle_axis_event`; input publish after `_allow_event` before layer update/dispatch; `with action_context(...)` around unchanged note_off/_send_macro_value/_emit_cc/_emit_note_on calls; four `@attributed` decorators. No mapping logic, arguments or send conditions changed. |
| Ben's Mac files | `config/presets/EDM Show.json` 58e47bfd, `config/presets/PTZ.json` 11b37cd6, `config/bridge.local.json` 7476c269 (unchanged) |
| Mac processes started | every bridge `gone=True` (SIGTERM + os.kill); timing runs prove bridge and browser PIDs; stopped attempt: run.sh, sampler, timing_ab, bridge pids gone; gate tmux server `sdgate` gone; `ps` for chrome-headless-shell, capture_runner, timing_ab, win_recv, seam_probe, sampler, waiter, gate node scripts, ab_run and laptop ssh: 0 lines at 04:06 |
| laptop processes started | every laptop phase that ran proved its own launcher and descendant pids gone by Get-Process before returning (timing phases `ALIVE 0`, A/B 18 pids `gone=True`, probes `PID_GONE True`); the queued flake step's local ssh client never connected (empty log) and was stopped with its tmux session. The final Get-Process inventory and guard compare are OWED (ssh). |
| laptop browsers (MASTER 02:58 1b) | OWED (ssh): the read-only Win32_Process listing of chrome.exe/msedge.exe/firefox.exe with SessionId and CreationDate could not be taken. Earlier read-only listings this link: 02:14 `MSEDGE_PROCESSES_NOW 0`; 02:30 no msedge/node(gate)/python; 02:31 no chrome/firefox/msedge. NEEDS-MASTER. |

## Other findings for the record

- Laptop clone could not fetch from GitHub (curl 56 connection reset x2, then commit-by-commit fetch: 1 of 5 commits, then timeouts). Commits were carried over the rail as git bundles (sha256 906a526c for 9fc224a..1901693, a8744e65 for 1901693..51b1d5b), `git bundle verify`, `fetch`, `merge --ff-only`, HEAD equal to the pushed SHA, porcelain 0.
- Every timing and bar 1 bridge log carries one `engine_registry.on_axis_event failed` traceback per axis event (15,246 per timing arm) because `--no-engines` leaves the registry None (`windows/receiver.py:896`, same code at v0.4.9:870). Present on both hosts and all arms; not a lap change, but it is per-axis logging work the real tray (engines on) does not do.

## FOR BEN

1. Bar 3 is RED on the locked rule, by 2.8 ms at p99 on the Mac. The shift sits in the long fades and long presses, not in the fast stick/trigger responses. It is held for a small follow-up measurement of the bridge's own delay (M_bridge, MASTER 04:00). Until that says otherwise, the practical mitigation for Friday is to keep the controller view CLOSED during the show and use it for setup and soundcheck. Live highlights are for checking controls, not for the performance.
2. Windows timing is diagnostic only. The real-browser (Edge) numbers exist but no Windows sensitivity control qualified, and Windows run-to-run noise is large (p95 floor 25 ms with Edge, 147 ms with Python). Your bar 4 hardware check cannot see millisecond delay.
3. The laptop's "do nothing" browser setting used by every sdwin/sdlive Windows run was not a no-op: each UI bridge the tools started tried to open your default browser (Chrome) at its local address. Fixed in 51b1d5b for the timing tool and one test. Whether a window ever reached your desktop during earlier runs is UNVERIFIED; Windows does not log process creation by default. Earlier sdwin runs share the defect (note, not a lap).
4. Owed to the next lap that touches the geometry check: (a) `scripts/showready/ui_geometry.py:27-28` only accepts `/tmp/sdfix-*` scratch; (b) `tests/ui_controller_geometry.cjs:118` waits for `networkidle`, which never comes while the Controller view is live, so the pinned check cannot measure the live view. Wait for 23 labels and the live indicator instead; add live overlays (dots, bars) as obstacles like `docs/sdlive-gate/scripts/geom_live.cjs` does.
5. Visual: the L1 and R1 leader lines pass over the new L2/R2 trigger bars. It meets every stated geometry rule but is visible in after-1.
6. Clock: the bridge itself times fades, repeats, staged notes and engines with `time.monotonic`, which is about 16 ms coarse on the laptop's Python. The timing tool bypasses that clock, so bar 3 does not measure it (E3 finding).
7. The laptop could not fetch from GitHub tonight (connection resets); code reached the clone as verified git bundles over the ssh rail. Then new ssh sessions to the laptop stopped connecting at about 03:55 (ping still answered, an already-open session kept working). Owed on the laptop: guard compare, browser session listing, the Windows 300x flake re-proof (HEAD and BASE), two Windows suites at 51b1d5b, the BROWSER-fix revert RED, downloads of the every-10th control result and the three Windows bar 1 results for independent re-check.
8. Rollback readiness and your hardware check (bars 4 and 5) were not in this gate's scope and remain yours.
