E3 ENTRY HEAD bd1bdda42d9f9926ec23ab5d5218e029435f50a4

# sdlive E3 - bar 3 timing instrument

Instrument built and tested. Bar 3 qualification is OWED TO THE GATE.
No laptop acts, hardware acts, real MIDI ports, deployment or merge.
All Mac timing arms in this report are UNVERIFIED-LOAD and accelerated
DIAGNOSTICS. They cannot authorize an upgrade, even when the numeric rule passes.

The serial load check returned exit 3 with exact stderr:

```
sysmon request failed with error: sysmond service not found
pgrep: Cannot get process list
```

Command: `pgrep -f "while True: pass"`. The instrument ran it serially before
and after every arm, retaining exit code, stdout, stderr and os.getloadavg().
No denied result was treated as empty. This executor cannot qualify the Mac
load check; the gate's full-rate measurement is authoritative.

## Delivered and scope

- `scripts/showready/timing_ab.py`: serial CLOSED, OPEN, CLOSED-B triplets on
  one archived HEAD, sectioned EDM Show from verified fixtures, UI always on.
  CLOSED uses no HTTP client. OPEN uses an SSE reader with snapshot recovery,
  plus a 250 ms snapshot presence monitor. Both Python and browser clients must
  provide nonzero real data events, client counts and explicit dropped counts.
- `capture_runner.py`: optional `--timing-config` enables the UI and a sender
  thread in the same bridge process. The existing bar 1 invocation and all
  real-MIDI denial/port/config checks remain. Default still requires --no-ui.
- `timing_browser.cjs`: foreground native Chromium/Edge client hook, real
  Controller visible and Follow on, actual EventSource observations, cooperative
  stop, client process wait and independently checked browser PID absence.
- `tests/test_showready_timing.py`: percentile, tolerance, wide-floor, byte,
  empty-sample, dead-client, load retry/denial, causal attribution, clock and
  process-cleanup controls. SHA256SUMS repinned; README defines usage and limits.

`scope.json` records `git diff bd1bdda -- windows protocol deck config mac` and
existing instrument/rail/UI test paths: empty. No mapping handlers, semantics,
MIDI product paths, public functions, existing assertions or UI affordances
changed. All scratch/config saves were under /tmp/sdlive-e3. No vault write.
Predecessor E1/E2 launch records were fetched into Mac scratch and their reports,
the W3 latency report and pinned kit were read before implementation.

## Clock and attribution

Sender and Recorder call `time.perf_counter_ns()` in ONE process per arm.
Both timestamps and that PID are embedded in every result; no inter-process
offset is needed. The legacy Recorder field `monotonic_ns` is retained and
mirrored as `perf_counter_ns`. Clock implementation/resolution is in each arm.
The new sender-clock test supplies disagreeing perf_counter/monotonic readings
and asserts the actual two emitted packet timestamps and same-process PID.

Accepted input publication and E1's current Action ID associate each message
with its initiating input. Note/CC release belongs to UP. Fade, repeat and
staged sends keep their DOWN origin through release. Raw records retain both
causal step and current replay step. Startup bytes are compared but have no
fabricated input latency. Missing attribution, negative latency and zero
samples fail. Intentional timer delays remain INCLUDED in the distribution.
`--clock script` controls receiver scheduling as in W3; latency timestamps and
pacing are real perf_counter time. This is not ordinary scheduler certification.

### Bridge clock finding for Ben (source read, no MIDI-path change)

`windows/receiver.py:132` defaults `_clock` to time.monotonic, saved at :148.
Datagram timestamp :232, fades :374, relative repeats :467 and staged work :478
use it. `windows/engines/base.py:27` has the same default; live engine ticks
come from time.monotonic at receiver.py:1037, :1059 and :1067. MIDI feedback
also uses monotonic (`windows/midi.py:239`). The axis dispatcher at
receiver.py:891-977 has no direct time-based MIDI throttle: it emits for each
mapped non-deadzone packet and passes `_clock()` to engines at :897. The button
loop guard/dedupe uses datagram time (:493-546). Deck axis pacing is a separate
sender concern; no Deck hardware was measured.

W4's existing laptop probe (docs/sdwin-w4/REPORT.md:272-277, commit b3b2861)
measured Python 3.12 GetTickCount64 at 15.625 ms for monotonic versus QPC at
100 ns for perf_counter. Inference from that probe and the source: coarse
monotonic ticks CAN quantize fade progress, due-time decisions, repeat batching
and engine timing on that runtime. High-resolution capture does not repair
that bridge clock. Current laptop runtime behavior is UNVERIFIED-BY-EXECUTION
here and is a finding for Ben/gate, not an authorized change in E3.

## R and duration

Generator command:
`.venv/bin/python -B scripts/showready/deck_script.py --out /tmp/sdlive-e3/deck-script.json`.
It produced 732 steps, 47039 packets and
469.716666743 seconds of schedule. Its digest is
`9256621abf62eb21e6c345ef286b6b7fcc087a2db87b8f682ce7fcf7703a993e`.

R=5, the required minimum, minimizes runtime. The full-rate lower
bound is 3 * R * script duration = 7045.750001145
seconds (117.43 minutes), excluding setup.
The locked full script/R requirements cannot fit a roughly ten-minute real-rate
run. E3 used --speed 15 diagnostics with the full packet stream and script clock.
Accelerated mode additionally drains each preceding loop before sending again,
preventing compressed timer probes from overflowing UDP in the sleep mutant.
This drain is disabled at speed 1. Neither speed 15 nor unreadable load earns
bar 3 credit. Full-rate Mac and laptop runs are UNVERIFIED-BY-EXECUTION, owed
to the gate, including fresh full-rate sensitivity for each client type.

## Locked verdict rule

Compute p50, p95, p99 and max of latency per arm (pooled over repeats) and per
repeat. The NOISE FLOOR is |CLOSED - CLOSED-B| per statistic. Bar 3 PASSES when,
for p50, p95 and p99, |OPEN - CLOSED| <= NOISE FLOOR + 1.0 ms AND the byte sequence
of every arm is identical to CLOSED (the bar 1 property, re-checked), AND the
stream's dropped count is reported (drops are allowed; delay is not). Report max
separately, not as a pass criterion, with the top 5 outliers and their steps.

`BAR3_TOLERANCE_MS = 1.0` is the sole tolerance constant. Percentiles linearly
interpolate `(N-1)*p/100`. Pooled rule determines the numeric outcome; per-repeat
outcomes remain visible. A floor that admits a synthetic +2 ms shift is invalid.
A qualified clean pass additionally needs a matching actual sensitivity receipt
whose OPEN timing inequality failed, with complete valid arms and identical
bytes. Same host/runtime, candidate, preset, script, client, clock and kit hashes
are required. If the 2 ms control passes, the instrument explicitly says it
cannot see that delay with this noise floor and bar 3 does not count.

## Executed controls and suites

| Control | Actual observation | Exit |
| --- | --- | --- |
| Planted publisher sleep 0.002 s while a client exists | All arms complete; identical MIDI; OPEN timing inequality RED | 1 |
| NULL, raw CLOSED vs CLOSED-B | Nonempty byte equality; latency difference within its measured floor | 0 (verify_results.py) |
| Dead OPEN (client creation omitted) | Ordinary presence guard observed clients=0 and rejected it; bridge gone | 1 |
| Rule assertion pristine / inequality removed / restored | Named +2 ms rejection assertion GREEN / RED / GREEN; scratch source restored | 0 / 1 / 0 |
| Real browser hook, speed 50, one full-script OPEN | Actual Controller/Follow/live checks, real data events, browser/client/bridge gone | 0 |
| Whole Mac suite | Ran 893 tests in 15.860s; OK (skipped=2) | 0 |
| Four standalone Node checks | All four unchanged check programs returned success | 0 |
| Unchanged real Chromium geometry detector | SUMMARY 1048/1048 PASS; bridge PID gone | 0 |

The initial accelerated sensitivity attempt overflowed UDP and exited 1; this
was invalid arm evidence, NOT sensitivity proof. It led to diagnostic-only
packet draining. See evidence/initial-overflow.json for its error and teardown.
A completed intermediate R=5 control was then rerun after final pinning; only
final-* artifacts below are used for the reported table.

The NULL timing inequality uses the CLOSED/CLOSED-B floor by definition. Its
independent useful assertions are nonzero captures and exact bytes; it does not
prove a quiet host. Diagnostic sensitivity also does not establish full-rate
2 ms resolution. No result here is aggregate show-ready green.

Exact matrix commands and exit codes are in evidence/final-commands.json:

```sh
/Users/viddyslap/Documents/project-workspaces/steam-deck-midi/.venv/bin/python -B /Users/viddyslap/Documents/project-workspaces/steam-deck-midi/scripts/showready/timing_ab.py --candidate HEAD --script /tmp/sdlive-e3/deck-script.json --speed 15 --allow-unverified-load --scratch /tmp/sdlive-e3/final-sensitivity --out /tmp/sdlive-e3/final-sensitivity.json.gz --control sensitivity
# exit 1; measured wall 610.306 seconds
/Users/viddyslap/Documents/project-workspaces/steam-deck-midi/.venv/bin/python -B /Users/viddyslap/Documents/project-workspaces/steam-deck-midi/scripts/showready/timing_ab.py --candidate HEAD --script /tmp/sdlive-e3/deck-script.json --speed 15 --allow-unverified-load --scratch /tmp/sdlive-e3/final-clean --out /tmp/sdlive-e3/final-clean.json.gz --sensitivity-result /tmp/sdlive-e3/final-sensitivity.json.gz
# exit 78; measured wall 502.271 seconds
/Users/viddyslap/Documents/project-workspaces/steam-deck-midi/.venv/bin/python -B /Users/viddyslap/Documents/project-workspaces/steam-deck-midi/scripts/showready/timing_ab.py --candidate HEAD --script /tmp/sdlive-e3/deck-script.json --speed 15 --allow-unverified-load --scratch /tmp/sdlive-e3/final-dead --out /tmp/sdlive-e3/final-dead.json.gz --control dead-client
# exit 1; measured wall 1.193 seconds
```

Other executed commands (from the run root):

```sh
TMPDIR=/tmp/sdlive-e3 PYSTRAY_BACKEND=dummy BROWSER=/usr/bin/true .venv/bin/python -B -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python -B -m unittest tests.test_showready_timing -v
.venv/bin/python -B docs/sdlive-e3/check_mutation.py
.venv/bin/python -B docs/sdlive-e3/check_browser_hook.py --script /tmp/sdlive-e3/deck-script.json --chromium /Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell
TMPDIR=/tmp/sdlive-e3 .venv/bin/python -B docs/sdlive-e2/check_geometry.py --chromium /Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell --scratch /tmp/sdlive-e3/geometry --single-process
TMPDIR=/tmp/sdlive-e3 node tests/ui_controller_check.cjs
TMPDIR=/tmp/sdlive-e3 node tests/ui_controller_macro_check.cjs
TMPDIR=/tmp/sdlive-e3 node tests/ui_reload_check.cjs
TMPDIR=/tmp/sdlive-e3 node tests/ui_sections_check.cjs
.venv/bin/python -B docs/sdlive-e3/verify_results.py /tmp/sdlive-e3/final-sensitivity.json.gz /tmp/sdlive-e3/final-clean.json.gz
```

The raw verifier re-subtracts every non-startup MIDI timestamp from the
recorded causal send, checks the exact sample population, all packet counts and
digests, every arm's raw byte sequence, nonempty streams/drop counts, both load
checks and PID absence. It recomputes the entire summary and requires equality.
It verifies data integrity, not host load qualification.

## Final clean Mac diagnostic

Producer: its exact timing_ab.py command above. All rows UNVERIFIED-LOAD, speed 15.

| Repeat | Arm | MIDI / samples | p50 ms | p95 ms | p99 ms | max ms | Stream / publisher drops |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | CLOSED | 1531 / 1525 | 47.772 | 125.798 | 134.497 | 137.841 | no stream / 1239 |
| 1 | OPEN | 1531 / 1525 | 49.093 | 127.575 | 134.691 | 137.765 | 0 / 1239 |
| 1 | CLOSED-B | 1531 / 1525 | 48.486 | 127.809 | 134.870 | 139.528 | no stream / 1239 |
| 2 | CLOSED | 1531 / 1525 | 48.217 | 127.035 | 135.517 | 138.297 | no stream / 1239 |
| 2 | OPEN | 1531 / 1525 | 48.581 | 127.057 | 135.066 | 137.159 | 0 / 1239 |
| 2 | CLOSED-B | 1531 / 1525 | 47.636 | 126.654 | 134.490 | 139.170 | no stream / 1239 |
| 3 | CLOSED | 1531 / 1525 | 47.913 | 127.592 | 135.950 | 140.523 | no stream / 1239 |
| 3 | OPEN | 1531 / 1525 | 48.254 | 126.995 | 134.738 | 137.671 | 0 / 1239 |
| 3 | CLOSED-B | 1531 / 1525 | 48.003 | 127.861 | 135.711 | 140.675 | no stream / 1239 |
| 4 | CLOSED | 1531 / 1525 | 48.476 | 126.650 | 135.608 | 137.834 | no stream / 1239 |
| 4 | OPEN | 1531 / 1525 | 48.327 | 127.037 | 135.244 | 140.089 | 0 / 1239 |
| 4 | CLOSED-B | 1531 / 1525 | 48.563 | 127.671 | 135.691 | 138.436 | no stream / 1239 |
| 5 | CLOSED | 1531 / 1525 | 49.409 | 126.625 | 134.879 | 138.891 | no stream / 1239 |
| 5 | OPEN | 1531 / 1525 | 48.459 | 126.452 | 134.013 | 139.488 | 0 / 1239 |
| 5 | CLOSED-B | 1531 / 1525 | 48.906 | 129.239 | 135.999 | 140.662 | no stream / 1239 |

Pooled statistics and contrasts (max is informational only):

| Statistic | CLOSED | OPEN | CLOSED-B | Noise floor | Open delta | Rule |
| --- | --- | --- | --- | --- | --- | --- |
| p50 ms | 48.248 | 48.464 | 48.522 | 0.274 | 0.216 | PASS |
| p95 ms | 126.846 | 127.006 | 127.838 | 0.993 | 0.160 | PASS |
| p99 ms | 135.377 | 134.789 | 135.471 | 0.094 | 0.587 | PASS |
| max ms | 140.523 | 140.089 | 140.675 | 0.152 | 0.434 | informational |

Pooled numeric rule: **PASS**. Byte-identical: True. Synthetic +2 ms visible against floor: True. Bar 3 counts: **False**.

Per-repeat rules: R1=PASS, R2=PASS, R3=PASS, R4=PASS, R5=PASS.

Top five individual latencies, including intentional timer delay:

| Repeat / arm | ms | Cause step | Action / phase | MIDI bytes |
| --- | --- | --- | --- | --- |
| 3 / CLOSED-B | 140.675 | 50 | DPAD_UP_LONG_PRESS / hold | [176, 22, 0] |
| 5 / CLOSED-B | 140.662 | 56 | DPAD_LEFT_LONG_PRESS / tap | [176, 23, 127] |
| 3 / CLOSED | 140.523 | 62 | DPAD_RIGHT_LONG_PRESS / hold | [176, 21, 0] |
| 5 / CLOSED-B | 140.515 | 56 | DPAD_LEFT_LONG_PRESS / tap | [176, 23, 126] |
| 3 / CLOSED-B | 140.341 | 50 | DPAD_UP_LONG_PRESS / hold | [176, 22, 1] |

Both pgrep checks per arm, from raw receipts. All have empty stdout and the exact exit-3 stderr quoted above. Load averages are (1, 5, 15 minute), produced by os.getloadavg():

| Repeat / arm | Before exit | Before load averages | After exit | After load averages |
| --- | --- | --- | --- | --- |
| 1 / CLOSED (try 1) | 3 | [3.7587890625, 4.5751953125, 4.728515625] | 3 | [3.73193359375, 4.48779296875, 4.6904296875] |
| 1 / OPEN (try 1) | 3 | [3.73193359375, 4.48779296875, 4.6904296875] | 3 | [3.5400390625, 4.353515625, 4.63232421875] |
| 1 / CLOSED-B (try 1) | 3 | [3.5400390625, 4.353515625, 4.63232421875] | 3 | [3.40625, 4.251953125, 4.58544921875] |
| 2 / CLOSED (try 1) | 3 | [3.40625, 4.251953125, 4.58544921875] | 3 | [3.3916015625, 4.1455078125, 4.53173828125] |
| 2 / OPEN (try 1) | 3 | [3.3916015625, 4.1455078125, 4.53173828125] | 3 | [3.11376953125, 3.99951171875, 4.46240234375] |
| 2 / CLOSED-B (try 1) | 3 | [3.11376953125, 3.99951171875, 4.46240234375] | 3 | [2.81298828125, 3.8388671875, 4.38720703125] |
| 3 / CLOSED (try 1) | 3 | [2.81298828125, 3.8388671875, 4.38720703125] | 3 | [3.041015625, 3.77734375, 4.3408203125] |
| 3 / OPEN (try 1) | 3 | [3.041015625, 3.77734375, 4.3408203125] | 3 | [2.9658203125, 3.67431640625, 4.27978515625] |
| 3 / CLOSED-B (try 1) | 3 | [2.9658203125, 3.67431640625, 4.27978515625] | 3 | [2.94189453125, 3.60693359375, 4.2333984375] |
| 4 / CLOSED (try 1) | 3 | [2.94189453125, 3.60693359375, 4.2333984375] | 3 | [3.42724609375, 3.650390625, 4.22314453125] |
| 4 / OPEN (try 1) | 3 | [3.42724609375, 3.650390625, 4.22314453125] | 3 | [3.42236328125, 3.6240234375, 4.189453125] |
| 4 / CLOSED-B (try 1) | 3 | [3.42236328125, 3.6240234375, 4.189453125] | 3 | [3.4921875, 3.61279296875, 4.16455078125] |
| 5 / CLOSED (try 1) | 3 | [3.4921875, 3.61279296875, 4.16455078125] | 3 | [3.6474609375, 3.625, 4.14599609375] |
| 5 / OPEN (try 1) | 3 | [3.6474609375, 3.625, 4.14599609375] | 3 | [3.56640625, 3.60205078125, 4.11572265625] |
| 5 / CLOSED-B (try 1) | 3 | [3.56640625, 3.60205078125, 4.11572265625] | 3 | [3.56298828125, 3.60400390625, 4.09814453125] |

## Final planted-delay Mac diagnostic

Producer: its exact timing_ab.py command above. All rows UNVERIFIED-LOAD, speed 15.

| Repeat | Arm | MIDI / samples | p50 ms | p95 ms | p99 ms | max ms | Stream / publisher drops |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | CLOSED | 1531 / 1525 | 49.649 | 129.751 | 139.378 | 160.901 | no stream / 1239 |
| 1 | OPEN | 1531 / 1525 | 462.085 | 1591.705 | 1787.415 | 2059.165 | 0 / 1239 |
| 1 | CLOSED-B | 1531 / 1525 | 49.447 | 128.318 | 136.176 | 142.483 | no stream / 1239 |
| 2 | CLOSED | 1531 / 1525 | 55.251 | 134.219 | 174.856 | 190.588 | no stream / 1239 |
| 2 | OPEN | 1531 / 1525 | 478.829 | 1541.961 | 1674.049 | 1741.698 | 0 / 1239 |
| 2 | CLOSED-B | 1531 / 1525 | 48.223 | 127.783 | 135.325 | 138.844 | no stream / 1239 |
| 3 | CLOSED | 1531 / 1525 | 50.274 | 130.055 | 151.695 | 153.420 | no stream / 1239 |
| 3 | OPEN | 1531 / 1525 | 459.847 | 1521.825 | 1616.673 | 1689.783 | 0 / 1239 |
| 3 | CLOSED-B | 1531 / 1525 | 48.822 | 128.578 | 135.748 | 140.445 | no stream / 1239 |
| 4 | CLOSED | 1531 / 1525 | 48.252 | 127.893 | 135.273 | 138.476 | no stream / 1239 |
| 4 | OPEN | 1531 / 1525 | 447.243 | 1506.543 | 1725.417 | 1910.778 | 0 / 1239 |
| 4 | CLOSED-B | 1531 / 1525 | 48.539 | 127.412 | 134.735 | 138.628 | no stream / 1239 |
| 5 | CLOSED | 1531 / 1525 | 50.018 | 128.361 | 136.566 | 145.538 | no stream / 1239 |
| 5 | OPEN | 1531 / 1525 | 489.730 | 1619.239 | 1878.631 | 2077.753 | 0 / 1239 |
| 5 | CLOSED-B | 1531 / 1525 | 48.765 | 127.710 | 135.465 | 138.706 | no stream / 1239 |

Pooled statistics and contrasts (max is informational only):

| Statistic | CLOSED | OPEN | CLOSED-B | Noise floor | Open delta | Rule |
| --- | --- | --- | --- | --- | --- | --- |
| p50 ms | 50.265 | 467.047 | 48.645 | 1.619 | 416.783 | FAIL |
| p95 ms | 130.026 | 1556.795 | 127.847 | 2.179 | 1426.769 | FAIL |
| p99 ms | 144.882 | 1735.622 | 135.609 | 9.273 | 1590.740 | FAIL |
| max ms | 190.588 | 2077.753 | 142.483 | 48.105 | 1887.165 | informational |

Pooled numeric rule: **FAIL**. Byte-identical: True. Synthetic +2 ms visible against floor: False. Bar 3 counts: **False**.

The measured noise floor can hide a uniform +2 ms shift. This run does not count for bar 3, even if the accelerated publisher fault amplifies into a larger timing RED.

Per-repeat rules: R1=FAIL, R2=FAIL, R3=FAIL, R4=FAIL, R5=FAIL.

Top five individual latencies, including intentional timer delay:

| Repeat / arm | ms | Cause step | Action / phase | MIDI bytes |
| --- | --- | --- | --- | --- |
| 5 / OPEN | 2077.753 | 48 | DPAD_UP_LONG_PRESS / tap | [176, 22, 127] |
| 5 / OPEN | 2069.855 | 48 | DPAD_UP_LONG_PRESS / tap | [176, 22, 126] |
| 1 / OPEN | 2059.165 | 48 | DPAD_UP_LONG_PRESS / tap | [176, 22, 127] |
| 5 / OPEN | 2051.763 | 48 | DPAD_UP_LONG_PRESS / tap | [176, 22, 125] |
| 5 / OPEN | 2043.884 | 48 | DPAD_UP_LONG_PRESS / tap | [176, 22, 124] |

Both pgrep checks per arm, from raw receipts. All have empty stdout and the exact exit-3 stderr quoted above. Load averages are (1, 5, 15 minute), produced by os.getloadavg():

| Repeat / arm | Before exit | Before load averages | After exit | After load averages |
| --- | --- | --- | --- | --- |
| 1 / CLOSED (try 1) | 3 | [5.572265625, 5.78515625, 4.70361328125] | 3 | [6.01708984375, 5.84326171875, 4.75927734375] |
| 1 / OPEN (try 1) | 3 | [6.01708984375, 5.84326171875, 4.75927734375] | 3 | [5.54833984375, 5.74462890625, 4.78857421875] |
| 1 / CLOSED-B (try 1) | 3 | [5.54833984375, 5.74462890625, 4.78857421875] | 3 | [5.51904296875, 5.734375, 4.8232421875] |
| 2 / CLOSED (try 1) | 3 | [5.51904296875, 5.734375, 4.8232421875] | 3 | [6.54931640625, 5.96484375, 4.9375] |
| 2 / OPEN (try 1) | 3 | [6.54931640625, 5.96484375, 4.9375] | 3 | [7.0791015625, 6.19921875, 5.0869140625] |
| 2 / CLOSED-B (try 1) | 3 | [7.0791015625, 6.19921875, 5.0869140625] | 3 | [6.15625, 6.0400390625, 5.0712890625] |
| 3 / CLOSED (try 1) | 3 | [6.15625, 6.0400390625, 5.0712890625] | 3 | [5.3955078125, 5.86083984375, 5.0390625] |
| 3 / OPEN (try 1) | 3 | [5.44384765625, 5.86279296875, 5.04443359375] | 3 | [5.49365234375, 5.80517578125, 5.06884765625] |
| 3 / CLOSED-B (try 1) | 3 | [5.49365234375, 5.80517578125, 5.06884765625] | 3 | [5.759765625, 5.8271484375, 5.10498046875] |
| 4 / CLOSED (try 1) | 3 | [5.759765625, 5.8271484375, 5.10498046875] | 3 | [5.41552734375, 5.78466796875, 5.12060546875] |
| 4 / OPEN (try 1) | 3 | [5.41552734375, 5.78466796875, 5.12060546875] | 3 | [4.3349609375, 5.40869140625, 5.02001953125] |
| 4 / CLOSED-B (try 1) | 3 | [4.3349609375, 5.40869140625, 5.02001953125] | 3 | [3.9111328125, 5.1953125, 4.9541015625] |
| 5 / CLOSED (try 1) | 3 | [3.91796875, 5.17529296875, 4.9482421875] | 3 | [3.52392578125, 4.96435546875, 4.87890625] |
| 5 / OPEN (try 1) | 3 | [3.52392578125, 4.96435546875, 4.87890625] | 3 | [3.40869140625, 4.65625, 4.76513671875] |
| 5 / CLOSED-B (try 1) | 3 | [3.37548828125, 4.62841796875, 4.75439453125] | 3 | [3.56396484375, 4.55126953125, 4.72119140625] |

## Browser hook and cleanup evidence

The check_browser_hook.py command above observed 1795
real stream data events and 101 actual page samples;
every sample kept Controller visible, Follow on and live. Stream drops:
0. This was a one-arm accelerated lifecycle control,
not the gate's browser latency matrix. No E3 UI proof is only node:vm.
Client PID 75374 exited 0;
browser PIDs [75395] were independently absent; bridge
PID 75373 was terminated, waited and absent. Every final matrix
bridge has the corresponding exact PID/exit/kill-zero proof in its receipt.
The Python stream reader also joins and proves its thread gone.

## Gate handoff and exact commands

Full-rate load-verified Mac timing, Windows suite and timing, real-browser
matrices on both hosts, Ben's hardware check and rollback readiness remain
OWED TO THE GATE/Ben. A push is not deployment. This link only builds the
instrument and reports its bounded diagnostic evidence. Gate must inspect
sensitivity_timing_red and bar3_counts, never infer PASS from an exit-1 control.

The following is copied from the pinned README so the gate can execute it
without this conversation. It uses no accelerated or unverified-load flags.
Windows commands are UNVERIFIED-BY-EXECUTION in E3. Allow at least 117 minutes
per five-triplet full-rate run, plus overhead; each client type needs its own
sensitivity run followed by clean. Run one timing arm at a time.

### Gate commands: Mac

From this checkout, generate once, then run sensitivity followed by clean:

```bash
mkdir -p /tmp/sdlive-gate
.venv/bin/python -B scripts/showready/deck_script.py --out /tmp/sdlive-gate/deck-script.json
.venv/bin/python -B scripts/showready/timing_ab.py --candidate HEAD --script /tmp/sdlive-gate/deck-script.json --scratch /tmp/sdlive-gate/sensitivity --out /tmp/sdlive-gate/sensitivity.json.gz --control sensitivity
.venv/bin/python -B scripts/showready/timing_ab.py --candidate HEAD --script /tmp/sdlive-gate/deck-script.json --scratch /tmp/sdlive-gate/clean --out /tmp/sdlive-gate/clean.json.gz --sensitivity-result /tmp/sdlive-gate/sensitivity.json.gz
.venv/bin/python -B scripts/showready/timing_ab.py --candidate HEAD --script /tmp/sdlive-gate/deck-script.json --scratch /tmp/sdlive-gate/dead --out /tmp/sdlive-gate/dead.json.gz --control dead-client
```

### Real browser hook (Mac and Windows)

`--client-cmd` is a JSON argv array, run directly without a shell.
`--client-cmd-file` reads that array from a JSON file, avoiding PowerShell
native-argument quote stripping. `{url}`,
`{stop}` and `{receipt}` placeholders are required. The command stays foreground,
owns its browser, never daemonizes, and writes an atomic JSON receipt with
`ready:true` after Controller is visible, live, and Follow is ON. It polls the
stop-file path and gracefully closes every owned child before exiting 0. The
final receipt reports `browser_pids`, `data_events`, `dropped`, and `error:null`.
The driver requests stop, waits, checks its process handle and checks each
reported browser PID (kill(pid,0) on Mac; a file-backed Get-Process script on
Windows). A missing receipt/PID, early exit or failed teardown invalidates the
arm. Gate must additionally retain the Windows guard's final Python inventory.

The pinned adapter `timing_browser.cjs` creates a fresh browser profile, opens
the real Controller page, enables Follow, consumes native EventSource events,
and samples actual visibility/live/Follow state. It closes the browser server
and reports the browser PID for the driver's independent absence check.
`PLAYWRIGHT_CORE` may identify an existing playwright-core installation.

Add this identical option to BOTH sensitivity and clean commands on the Mac:

```bash
--client-cmd '["node","/Users/viddyslap/Documents/project-workspaces/steam-deck-midi/scripts/showready/timing_browser.cjs","{url}","{stop}","{receipt}","/Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell","--single-process"]'
```

### Gate commands: laptop (UNVERIFIED-BY-EXECUTION in E3)

Only the gate runs these, with the existing win_rail.sh guard snapshot BEFORE
its first laptop act and guard compare AFTER its last, including downloads.
Use the clone venv, verify clone HEAD after pull, and put this body in a local
.ps1 carried by `scripts/showready/win_rail.sh run sdlive-gate <local.ps1>`.
No inline PowerShell. Do not change/install dependencies if absent: escalate.
The sectioned EDM Show fixture is the verified MAC fixture on both hosts.

```powershell
$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$work = 'C:\Users\Ben\AppData\Local\Temp\sdwin\sdlive-gate'
New-Item -ItemType Directory -Force -Path $work | Out-Null
$python = (Resolve-Path '.\.venv\Scripts\python.exe').Path
$env:PYSTRAY_BACKEND = 'dummy'
$env:BROWSER = 'C:/Windows/System32/cmd.exe /c rem %s'
function Invoke-TrackedPython([string[]]$PythonArgs) {
  $child = Start-Process -FilePath $python -ArgumentList $PythonArgs -PassThru -NoNewWindow
  $child.Id | Add-Content -Encoding ascii -Path "$work\python-pids.txt"
  $child.WaitForExit()
  $code = $child.ExitCode
  if (Get-Process -Id $child.Id -ErrorAction SilentlyContinue) { throw 'Python PID still exists' }
  return $code
}
$code = Invoke-TrackedPython @('-B', 'scripts/showready/deck_script.py', '--out', "$work\deck-script.json")
if ($code -ne 0) { exit $code }
# Set PLAYWRIGHT_CORE to the gate's already installed module. Verify Edge exists.
$edge = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
if (-not (Test-Path $edge)) { throw 'NEEDS-MASTER: existing browser required' }
$client = @('node', "$PWD\scripts\showready\timing_browser.cjs", '{url}', '{stop}', '{receipt}', $edge) | ConvertTo-Json -Compress
$client | Set-Content -Encoding ascii -Path "$work\client-command.json"
$common = @('-B', 'scripts/showready/timing_ab.py', '--candidate', 'HEAD', '--script', "$work\deck-script.json", '--client-cmd-file', "$work\client-command.json")
$code = Invoke-TrackedPython ($common + @('--scratch', "$work\sensitivity", '--out', "$work\sensitivity.json.gz", '--control', 'sensitivity'))
if ($code -ne 1) { throw 'Expected sensitivity exit 1; inspect JSON timing inequality before continuing' }
$cleanExit = Invoke-TrackedPython ($common + @('--scratch', "$work\clean", '--out', "$work\clean.json.gz", '--sensitivity-result', "$work\sensitivity.json.gz"))
$code = Invoke-TrackedPython @('-B', 'scripts/showready/timing_ab.py', '--candidate', 'HEAD', '--script', "$work\deck-script.json", '--scratch', "$work\dead", '--out', "$work\dead.json.gz", '--control', 'dead-client')
if ($code -ne 1) { throw 'Dead client was not rejected' }
exit $cleanExit
```

Wrap this work using the rail's Start-Process/PassThru PID recording convention,
then Get-Process checks, downloads, and final guard compare. Do the Python-reader
matrix separately by omitting `--client-cmd` from BOTH runs. The browser matrix
must use its own sensitivity receipt. No E3 laptop command was executed.
