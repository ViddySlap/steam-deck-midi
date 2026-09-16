BASE OF LAP 778eaa78441c0e7d5539f540cfed8aa944142f8b
P3 START ae19c4f6d4070dbe1b3bdf353540aea30751e119

# sdpolish P3 - the Windows bridge clock

GUARD COMPARE: `GUARD GREEN: compare; protected state observed; pythonProcesses=0`
(exit 0). The snapshot was the FIRST laptop act of this link and the compare the
LAST; both returned exit 0 and `GUARD GREEN`, so the protected state -
`C:\Program Files\STEAMDECK MIDI Receiver 2\`, loopMIDI, the orphan checkout -
is unchanged, and no python process under the clone or LAPTOP WORK survives.

## (a) THE CLOCK INVENTORY, AT P3 START, BEFORE ANY CHANGE

Produced by, at `ae19c4f`:

    grep -rn "time\.monotonic\|time\.perf_counter\|time\.time\|monotonic_ns" \
      windows/ --include='*.py' | grep -v __pycache__
    grep -rn "from time import\|import time" windows/ --include='*.py' | grep -v __pycache__

Two facts that bound the whole item:

- There is NO use of `time.perf_counter`, `time.monotonic_ns` or `time.time()`
  anywhere under `windows/` at P3 START. Every clock read in the bridge is
  `time.monotonic`, so there is nothing to un-mix and no wall-clock read to
  preserve except the one logging `datetime.now()` noted below.
- Every module reaches the clock as `import time` + `time.monotonic`. There is
  no `from time import monotonic` anywhere, so an AST/source check that looks
  for the attribute access `time.monotonic` covers the tree with no second form
  to chase.

### A1. Clock reads: file:line, and what each one times

DEFAULTS FOR AN INJECTION POINT (the `clock=` parameter each one names is the
existing test seam and keeps working; the default is what the bridge actually
runs on):

| file:line | site | what it times |
|---|---|---|
| windows/receiver.py:137 | `ActionReceiver(clock=...)` default | every receiver timestamp: fades, relative_cc repeats, staged macros, timeouts, the rate-limit loop guard |
| windows/engines/base.py:58 | `BaseEngine(clock=...)` default | the base class every engine inherits; engine-local scheduling |
| windows/live_events.py:59 | `LiveEvents(capacity, clock=...)` default | event timestamps on the SSE ring |
| windows/engines/autopilot.py:145 | `Autopilot(clock=...)` default | autopilot crossfade scheduling |
| windows/engines/autopilot_ptz.py:86 | default | PTZ autopilot scheduling |
| windows/engines/autopilot_state.py:127 | default | autopilot state generation stamps |
| windows/engines/audio_opacity.py:80 | default | audio-driven opacity ramp |
| windows/engines/bumper_blast.py:83 | default | bumper blast decay |
| windows/engines/chaser_stack_dispatcher.py:85 | default | chaser step scheduling |
| windows/engines/flash_blast.py:160 | default | flash decay |
| windows/engines/global_color.py:187 | default | global colour ramp |
| windows/engines/gyro_feedback.py:182 | default | gyro feedback rate |
| windows/engines/l_stick_layer.py:80 | default | left-stick layer hold |
| windows/engines/nestdrop_engine.py:105 | default | NestDrop dispatch scheduling |
| windows/engines/osc_sync.py:98 | default | OSC sync cadence |
| windows/engines/ptz_visca.py:92 | default | VISCA send pacing |
| windows/engines/stageflow_bridge.py:81 | default | Stageflow dispatch |
| windows/engines/steam_input_layer_tracker.py:63 | default | Steam Input layer debounce |

BARE READS (no injection point; these are the ones that bypass the seam):

| file:line | site | what it times |
|---|---|---|
| windows/receiver.py:1043 | main loop, after a datagram drain | the value passed to `engine_registry.tick()` |
| windows/receiver.py:1076 | `socket.timeout` branch | same, on the idle path - THE HOT PATH: this is the tick that runs when no datagram arrives, i.e. almost always |
| windows/receiver.py:1084 | post-datagram branch | same |
| windows/receiver.py:1128 | `_handle_feedback_message` | `now` for `classify_midi_feedback` - THE CROSS-CLOCK SITE (A2) |
| windows/midi.py:239 | `MidiIn._clock` | stamps `received_at` on every inbound CC and MIDI clock message |
| windows/preset_watch.py:59 | `PresetWatch.run` | preset-file change debounce (file poll, not MIDI timing) |
| windows/engines/autopilot_state.py:166,169 | `flush()` deadline | a writer-thread join deadline (`_cond.wait`), not MIDI timing |

NOT A CLOCK READ, left alone: `time.sleep` at windows/win_recv.py:210 and
windows/live_events.py:127,132 (P0's back-off) - a duration, not a reading.
`windows/tray.py:29` imports `time` but never reads a clock.
`windows/osc_relay.py` and `windows/ui_server.py` do not import `time` at all,
so the item's "every clock use" list for them is empty.

WALL CLOCK, GENUINELY NEEDED, STAYS: `windows/receiver.py:1138`
`datetime.now().isoformat(timespec="milliseconds")` - a human-readable stamp in
a DEBUG log line for the MIDI feedback receipt. It is never subtracted from
anything and never compared; it is there so a person reading the log can line an
event up against a wall clock. It stays as `datetime.now()`.

### A2. Where two readings are subtracted or compared, and which clock feeds each side

| comparison | file:line | left side | right side |
|---|---|---|---|
| fade progress | receiver.py:380, 461, 875 (`_fade_value_at`) | `self._clock()` (receiver injection) | fade `started_at`, stamped by `self._clock()` | 
| relative_cc repeat due | receiver.py:477 `timestamp >= active.next_send_time` | `self._clock()` | `next_send_time`, seeded at receiver.py:680 from `timestamp + repeat_interval_seconds`, same clock | 
| staged note macro due | receiver.py:484 | `self._clock()` | staged deadline, same clock |
| rate-limit loop guard | receiver.py:380, 473, 484, 499 vs 545 | `self._clock()` | `self._loop_guard_until`, set at receiver.py:545 from `timestamp + cooldown`, same clock |
| action timeouts | receiver.py:283 `check_timeouts` | `self._clock()` | per-action stamps from `self._clock()` |
| engine tick delta | engines, via `self._clock()` | engine injection | the `now` the registry passed from receiver.py:1043/1076/1084, a BARE `time.monotonic()` |
| MIDI clock / feedback arrival | engines, via `on_midi_clock(..., message.received_at)` (receiver.py:1119) | engine `self._clock()` | `received_at`, stamped by `MidiIn._clock` at midi.py:239, a SEPARATE bare `time.monotonic` |
| **MIDI feedback classify** | **receiver.py:1128 -> 460-461** | **bare `time.monotonic()` passed in as `now`** | **the active fade's `started_at`, stamped by `self._clock()`** |

THE DEFECT THE REVIEWER FOUND (MASTER 13, 11:33), confirmed at P3 START at
windows/receiver.py:1128 (the line numbers given as 1111-1142 from origin; the
function now begins at 1122 and the read is at 1128): `_handle_feedback_message`
computes `now = time.monotonic()` and hands it to
`receiver.classify_midi_feedback(..., now=now)`, which at receiver.py:460-461
subtracts it against a fade `started_at` that was stamped by the receiver's
INJECTED `self._clock()`. Today the two are the same function object, so the
subtraction is accidentally correct and no test catches it. It is latent in two
ways: under a test fake clock the two sides already disagree, and the moment
this item moves the injected clock to `perf_counter` while a bare read stays on
`monotonic`, the two sides become DIFFERENT EPOCHS and the subtraction becomes
meaningless - `_fade_value_at` would see a difference of thousands of seconds
and snap every fade to its end value. The same shape holds for the three
`engine_registry.tick()` reads and for `MidiIn._clock`: all four are compared
against engine-injected readings. So the one-clock change is not cosmetic here;
doing it by halves would break MIDI output, which is exactly what bar 1 exists
to catch.

### A3. What (b) therefore has to do

Every row in A1 - both tables - moves to one function, `windows/clock.py: now()`,
returning `time.perf_counter()`. Every `clock=` default becomes that function, so
the injection seams keep working unchanged. The four bare reads that feed a
comparison against an injected clock (receiver.py:1043, 1076, 1084, 1128 and
midi.py:239) become calls to it. `preset_watch.py:59` and
`autopilot_state.py:166,169` are not MIDI timing, but they move too: leaving
them behind would mean an allow-list with three entries in the (c) source check
instead of one, and a rule with exceptions is the thing that lets the next bare
read in. After the change the ONLY place under `windows/` that names
`time.monotonic` is `windows/clock.py`.

---

# (b) THE ONE-CLOCK CHANGE

`windows/clock.py` is new and holds one function, `now()`, returning
`time.perf_counter()`. It is the only file under `windows/` that names a stdlib
clock. Landed in 8f1a98a.

| file:line (at HEAD) | before | after |
|---|---|---|
| windows/clock.py:46 | (new file) | `return time.perf_counter()` |
| windows/receiver.py:138 | `clock: Callable[[], float] = time.monotonic,` | `= clock_now,` |
| windows/receiver.py:1044, 1077, 1085 | `engine_registry.tick(time.monotonic())` | `engine_registry.tick(clock_now())` |
| windows/receiver.py:1129 | `now = time.monotonic()` (the reviewer's site) | `now = clock_now()` |
| windows/midi.py:240 | `self._clock = time.monotonic` | `self._clock = clock_now` |
| windows/live_events.py:60 | `clock=time.monotonic` | `clock=clock_now` |
| windows/preset_watch.py:60 | `now = time.monotonic()` | `now = clock_now()` |
| windows/engines/base.py:59 | `clock: Callable[[], float] = time.monotonic,` | `= clock_now,` |
| windows/engines/autopilot_state.py:167,170 | `time.monotonic()` deadline/remaining | `clock_now()` |
| 15 further engine modules | `clock: Callable[[], float] = time.monotonic,` | `= clock_now,` |

Full list of the 16 engine classes in `EXPECTED_ENGINE_CLOCK_DEFAULTS`
(tests/test_bridge_clock.py), asserted as an exact roster.

WHAT DID NOT CHANGE. No mapping handler logic, no route, no mapping semantics
in windows/config.py, no change to what MIDI is sent. Every `clock=` injection
point still exists and still means the same thing; only its default moved. No
public function was removed or renamed.

`time.time()` STAYS NOWHERE, because it was nowhere: the inventory found no
`time.time()`, `time.monotonic_ns` or `time.perf_counter` under `windows/` at
P3 START. The one genuine wall-clock read is
`windows/receiver.py:1139 datetime.now().isoformat(timespec="milliseconds")`,
a human-readable stamp in the MIDI-feedback DEBUG log. It is never subtracted
or compared, so it stays `datetime.now()`. A `perf_counter` reading has an
undefined epoch and could not have served there.

`time.sleep` is untouched (windows/win_recv.py:210, windows/live_events.py:127
and :132, which is P0's back-off): a duration is not a reading.

WHY preset_watch AND autopilot_state MOVED TOO. Neither is MIDI timing - one is
a file-poll debounce, the other a writer-thread join deadline. They moved so
the (c) source check has ONE exemption instead of three. A rule with exceptions
is what lets the next bare read in.

# (c) THE TESTS, AND THE REVERT PROOFS

`tests/test_bridge_clock.py`, 12 tests, three groups.

1. `BridgeClockSourceScanTests` - an AST scan asserting no module under
   `windows/` reads a stdlib clock directly, `windows/clock.py` excepted.
   `scan_tree()` is importable so a BASE archive can be scanned with HEAD's
   scanner, the same shape as tests/test_config_divisor_tripwire.py.
   THE DETECTOR IS SHOWN TO FIRE AND NOT TO FIRE: on a planted fixture it
   returns exactly `['bare.py:5:time.monotonic']`, and returns nothing for a
   file using `clock_now` or for `time.sleep`. Zero observations on both sides
   would be a vacuous pass, so the planted case is asserted by exact value.

2. `BridgeClockWiringTests` - every `clock=` default IS the `windows.clock.now`
   OBJECT (`assertIs`), for the receiver, LiveEvents and all 16 engine classes,
   plus `MidiIn._clock`. The engine walk asserts the EXACT 16-name roster
   rather than a floor, so a class dropping out of the walk is as loud as a
   class with the wrong default.

3. `BridgeClockResolutionTests` - the behaviour. A `_Wall` is read through two
   clocks: `fine` (exact) and `coarse` (floored to 15.625 ms). Nothing passes
   `now=`; the receiver reads its own injected clock, which is the only path a
   clock change can reach.

REVERT PROOFS ON THE MAC. Each arm was applied to the tree, measured, and
reverted; the tree was confirmed back to HEAD and the full suite re-run green
after each.

| revert arm | what went RED |
|---|---|
| bare read reintroduced at receiver.py:1128, as a VALID mixed-clock program (`import time` restored) | `test_no_module_under_windows_reads_a_stdlib_clock_directly` FAILED: `Lists differ: ['receiver.py:1129:time.monotonic'] != []` |
| one engine default (`gyro_feedback`) back to `time.monotonic` | TWO tests: the scan test (`['engines/gyro_feedback.py:183:time.monotonic']`) AND `test_every_engine_class_defaults_to_the_bridge_clock` (`<built-in function monotonic> is not <function now>`) |
| `windows/clock.py: now()` back to `time.monotonic()` | NOTHING on the Mac. See below. |

TWO TESTS FAIL WHEN REVERTED, as required, and they are independent detectors:
the scan reads source, the wiring reads the live function objects.

THE THIRD ARM IS RECORDED AS A NON-PROOF, NOT COUNTED AS ONE. Reverting
`windows.clock.now` to `time.monotonic` leaves all 12 tests GREEN on the Mac,
because macOS `time.monotonic` and `time.perf_counter` have the SAME
resolution: `time.get_clock_info` reports 4.1667e-08 for both
(`.venv/bin/python -B scripts/showready/clock_intervals.py --label mac-HEAD`).
`test_the_real_bridge_clock_resolves_finer_than_a_millisecond` is therefore a
WINDOWS-ONLY detector. It is proved RED on the laptop in (e); saying it fires
on the Mac would have been a caption that does not match the measurement.

WHAT THIS TEST FILE WAS WORTH, measured rather than asserted: under the FIRST
revert arm (the mixed-clock program), the pre-existing 59-test receiver suite
stays GREEN.

    .venv/bin/python -m unittest discover -s tests -p "test_receiver.py"
    Ran 59 tests in 0.007s
    OK

The mixed-clock defect the reviewer found was invisible to the existing suite
by construction. That is the reason the scan test exists.

ONE EXISTING TEST CHANGED - `tests/test_preset_watch.py`, NO assertion touched.
It patched `'windows.preset_watch.time.monotonic'`. That target reaches through
the module attribute into the SHARED stdlib `time` module and monkeypatches it
process-wide - including the test's own `FakeEvent.set`, which is the only
reason `self.event.when` came out as 0.26 rather than a real clock reading.
That was a side effect of the patch target, not a seam. The patch now names
`windows.preset_watch.clock_now`, and `FakeEvent.set` stamps from that same
seam explicitly, with a comment saying why. `assertEqual(self.event.count, 1)`,
`assertEqual(self.event.when, 0.26)`, `assertTrue(self.event.signal.is_set())`
and the file-content assertion are all unchanged and all pass.

# (e) THE WINDOWS MEASUREMENT

## The bundle route, its first real use

CODE REACHED THE LAPTOP ONLY BY THE BUNDLE ROUTE. No GitHub fetch or pull was
run from the laptop.

    git bundle create /tmp/sdpolish-p3/sdpolish-p3.bundle \
      f943c7b626730925ac153bd9cde297fcb077d258..09c42e509162b27f187952d794e4a1206660d90f \
      chain/steamdeck-20260914
    shasum -a 256 -> 4e146381ca2f3224d275a2afd6afed10e404966e85c6a0a60bd159b2ef85a17d
    scripts/showready/win_rail.sh put p3 /tmp/sdpolish-p3/sdpolish-p3.bundle   (exit 0)

Clone HEAD before: `f943c7b626730925ac153bd9cde297fcb077d258`, branch
chain/steamdeck-20260914, `git --no-optional-locks status --porcelain` 0 lines,
Python 3.12.10.

    scripts/showready/win_rail.sh run p3 scripts/showready/pull_bundle.ps1 \
      -Bundle 'C:\Users\Ben\AppData\Local\Temp\sdwin\p3\sdpolish-p3.bundle' \
      -Expected 09c42e509162b27f187952d794e4a1206660d90f

EVERY OUTPUT LINE, and the exit code:

    BUNDLE_SHA256 4e146381ca2f3224d275a2afd6afed10e404966e85c6a0a60bd159b2ef85a17d
    VERIFY The bundle contains this ref:
    VERIFY 09c42e509162b27f187952d794e4a1206660d90f refs/heads/chain/steamdeck-20260914
    VERIFY The bundle requires this ref:
    VERIFY f943c7b626730925ac153bd9cde297fcb077d258
    VERIFY The bundle uses this hash algorithm: sha1
    VERIFY C:/Users/Ben/AppData/Local/Temp/sdwin/p3/sdpolish-p3.bundle is okay
    FETCH From C:\Users\Ben\AppData\Local\Temp\sdwin\p3\sdpolish-p3.bundle
    FETCH  * branch            chain/steamdeck-20260914 -> FETCH_HEAD
    FETCH_HEAD 09c42e509162b27f187952d794e4a1206660d90f
    MERGE  create mode 100644 tests/test_showready_scratch_pattern.py
    MERGE  create mode 100644 windows/clock.py
    PINNED_HEAD 09c42e509162b27f187952d794e4a1206660d90f
    PORCELAIN_LINES 0
    EXIT 0

The BUNDLE_SHA256 the laptop computed equals the sha256 the Mac computed, and
FETCH_HEAD equalled -Expected, so no path existed for a different tree to land.
P1's parameterised `-Bundle` was exercised: the bundle is NOT named
`sdpick.bundle`, which the K1 original hardcoded.

## The two arms, and what was held constant

Both arms are `git archive` trees extracted under LAPTOP WORK
(`C:\Users\Ben\AppData\Local\Temp\sdwin\p3\{base,head}`), never in the clone,
driven by the SAME interpreter and the SAME instrument file:

    TREE base 778eaa78441c0e7d5539f540cfed8aa944142f8b files=1888
    TREE head 09c42e509162b27f187952d794e4a1206660d90f files=1926
    INSTRUMENT_SHA256_HEAD 45c80952e9d05c91d4b23d73eab8cb72df1475999d9f32056966da8f27ca4111
    INSTRUMENT_SHA256_BASE 45c80952e9d05c91d4b23d73eab8cb72df1475999d9f32056966da8f27ca4111
    CLOCK_MODULE base exists=False
    RECEIVER_DEFAULT base clock: Callable[[], float] = time.monotonic,
    CLOCK_MODULE head exists=True
    RECEIVER_DEFAULT head clock: Callable[[], float] = clock_now,

BASE has no `windows/clock.py` at all, which is why the instrument names no
clock: it reads whatever the tree defaults to, and it RECORDS which
(`receiver_default_clock` in every output). The instrument is byte-identical on
both arms and identical to the pinned copy in SHA256SUMS.

CLOCK MODE: the bridge's REAL clock path. Nothing passed `now=`, nothing passed
`clock=`. This is NOT the timing instrument's `--clock script` mode, which
drives the receiver from the script's own timeline and bypasses the receiver's
clock (scripts/showready/README.md, "Clock and origin of each MIDI message").

## get_clock_info, on the interpreter the bridge runs

| machine | interpreter | `monotonic` resolution | `perf_counter` resolution |
|---|---|---|---|
| laptop (viddyslaptop) | 3.12.10 | **0.015625** | **1e-07** |
| Mac | 3.12.13 | 4.1666666666666667e-08 | 4.1666666666666667e-08 |

The laptop reproduces sdwin W4 exactly: `monotonic` is a 15.625 ms clock,
`perf_counter` is 100 ns. On the Mac the two are the SAME, which is why this
defect cannot be seen there and why the verdict below is a Windows measurement.

## Arm 1: a 40 ms relative_cc repeat (3.0 s, 1 ms poll)

    <tree>\scripts\showready\clock_intervals.py --out <arm>-intervals.json \
      --seconds 3.0 --poll-ms 1.0 --repeat-ms 40 --label <arm>        (exit 0 both arms)

| arm | clock | n | p50 | p95 | max | min |
|---|---|---|---|---|---|---|
| BASE | time.monotonic | 75 | **45.7533 ms** | 48.1921 ms | 52.6642 ms | 25.6916 ms |
| HEAD | windows.clock.now | 75 | **39.9192 ms** | 41.1086 ms | 41.5957 ms | 38.7416 ms |

The medians are the headline, but the discriminator is WHERE the intervals sit:

| arm | mean abs error vs the 40 ms target | mean abs residual from a whole 15.625 ms tick | interval / 15.625, rounded |
|---|---|---|---|
| BASE | **7.822 ms** | **0.941 ms** | {2 ticks: 33, 3 ticks: 41} |
| HEAD | **0.554 ms** | 6.829 ms | {2: 7, 3: 67} |

At BASE every one of the 74 intervals lands within about 1 ms of a whole
15.625 ms tick (31.25 ms or 46.875 ms) and NONE lands on 40 ms: the schedule is
quantized to the clock. At HEAD the intervals sit on the 40 ms target to within
0.55 ms and are NOT on tick boundaries.

## Arm 2: a macro fade

FIRST CONFIGURATION, REPORTED AS UNINFORMATIVE RATHER THAN QUIETLY DROPPED.
A 2.0 s fade over the 0-127 CC range is one value per 2000/128 = **15.625 ms**,
numerically identical to the Windows monotonic tick. Value granularity and
clock granularity coincide, so both arms produced p50 ~15.7-15.9 ms
(BASE 15.7334, HEAD 15.8980) and the arm cannot discriminate. That is a
property of the chosen fade length, not a result about the clock. It is
recorded here so the figure is not mistaken later for a NOT FIXED.

SECOND CONFIGURATION, which separates the two: a 0.5 s fade is one value per
500/128 = 3.9 ms, well under the 15.625 ms tick, so the clock becomes the
binding constraint.

    ... --seconds 3.0 --poll-ms 1.0 --fade-seconds 0.5 --update-hz 120   (exit 0 both arms)

| arm | clock | messages | p50 | p95 | max | value steps |
|---|---|---|---|---|---|---|
| BASE | time.monotonic | **31** | **15.9849 ms** | 32.2471 ms | 38.0457 ms | mean 4.23, max 7 (25 of 30 steps are 4) |
| HEAD | windows.clock.now | **115** | **3.8032 ms** | 6.3301 ms | 32.0236 ms | mean 1.11, max 8 (110 of 114 steps are 1) |

Both arms ramp 0 -> 127. At BASE the fade emits 31 times and JUMPS four CC
values at a time, because the clock only moves once per 15.625 ms. At HEAD it
emits 115 times and walks one value at a time at the true 3.9 ms rate. That is
the quantization a person would see on the light.

## The control that decides whether the instrument measured anything

THE POLL LOOP IS NOT THE BOTTLENECK. A 1 ms poll was requested; the achieved
cadence, computed from the recorded poll count over the 3.0 s arm, was
535-603 polls/s (about 1.7 ms per poll) on every arm - Windows `time.sleep`
does not deliver exactly 1 ms. 1.7 ms is still far under both the 15.625 ms
tick and the 40 ms target, so it cannot manufacture either result, and it is
within 12% across the four arms so it cannot explain a 45.75 vs 39.92
difference. Had this come back near 64 polls/s, every number above would have
been the loop's cadence rather than the bridge's clock, and the arms would have
been void.

## VERDICT (e): FIXED

The rule declared by MASTER 13 at 11:05, corrected 11:33 before any data: the
~15.6 ms steps VISIBLE at BASE and ABSENT at HEAD is FIXED; VISIBLE at both is
NOT FIXED; NOT VISIBLE at BASE means the measurement did not exercise the clock
and the result is INVALID.

BASE DOES show the ~15.6 ms steps, on both arms and by two independent measures
(intervals sitting within 0.94 ms of whole ticks; a fade jumping 4 CC values at
a time). So the measurement exercised the clock and the result is NOT INVALID.
HEAD does not show them on either arm. **FIXED.**

# (e2) THE WINDOWS ENGINE A/B - and a FINDING, owner P0

## FINDING: engine_ab.py still dies on a laptop with LOCALAPPDATA unset

THE DECLARED CHECK IN (e2) IS RED. Run in the clone at HEAD with
`Remove-Item Env:\LOCALAPPDATA` first (verified absent before launching), all
four arms failed identically:

    {
     "result": "C:\\Users\\Ben\\AppData\\Local\\Temp\\sdwin\\p3\\engine-ab-ptz.json",
     "passed": false,
     "control": null,
     "control_expected": null,
     "error": "KeyError: 'LOCALAPPDATA'",
     "problems": null,
     "comparisons": {},
     "coverage": []
    }
    EXIT_edm 1   EXIT_ptz 1   EXIT_sens-autopilot 2   EXIT_sens-lstick 2

ROOT CAUSE, located rather than guessed. P0's F5 fix is real but covers only
`engine_ab.py`'s OWN parser default, which now uses `environ.get`
(scripts/showready/engine_ab.py:119, and tests/test_engine_ab_scratch_default.py
proves that one site). `engine_ab.py:659` then does

    from ab_run import archive, validate_scratch, verify_preset, write_result

and `ab_run.validate_scratch` still subscripts the variable directly:

    scripts/showready/ab_run.py:33
        allowed = Path(os.environ['LOCALAPPDATA']) / 'Temp/sdwin' if os.name == 'nt' else Path('/tmp')

`scripts/showready/ab_run.py:28` (`default_scratch`) has the same shape. So the
KeyError moved from the parser to the function the parser's value is handed to,
on the same machine for the same reason. This is the reported-instance-fixed,
class-unswept shape: the sdauto AG report was a SAMPLE of the defect, and the
sweep needed to cover every member including `ab_run.py`.

OWNER P0. This link did not touch `ab_run.py` or `engine_ab.py`: P3 changes
only which clock bridge timing reads, and editing another item's instrument to
make its own arm pass is exactly the move that makes a green meaningless.

NOT VISIBLE FROM THE MAC: `os.name == 'nt'` guards both lines, so the Mac takes
the `/tmp` branch and the whole Mac suite stays green. Only a Windows run under
the rail reaches it. The existing test asserts on `scratch_dir_for`, a pure
function, and never imports `ab_run`, so it cannot see this.

## The measurement itself, on a labelled workaround arm

So that the engine byte comparison was not left unmeasured, the four arms were
re-run identically except with `$env:LOCALAPPDATA = 'C:\Users\Ben\AppData\Local'`.
THIS ARM DOES NOT SATISFY (e2)'s environment condition and is not offered as
if it did; it isolates the finding above to the environment lookup and shows
the comparison underneath is sound.

| arm | preset | passed | control | control_expected | exit |
|---|---|---|---|---|---|
| edm | windows-installed/presets/EDM Show.json | **true** | null | null | **0** |
| ptz | windows-installed/presets/PTZ.json | **true** | null | null | **0** |
| sens-autopilot | EDM Show.json `--control sensitivity-autopilot` | false | sensitivity-autopilot | true | **1** |
| sens-lstick | EDM Show.json `--control sensitivity-l_stick_layer` | false | sensitivity-l_stick_layer | true | **1** |

Command shape (identical across arms but for `--preset` and `--control`):

    <clone>\.venv\Scripts\python.exe -B <clone>\scripts\showready\engine_ab.py \
      --candidate HEAD --preset <fixture> \
      --fixtures C:\Users\Ben\AppData\Local\Temp\sdwin\p3\fixtures \
      --scratch  C:\Users\Ben\AppData\Local\Temp\sdwin\p3\engine-ab-scratch \
      --repo     C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc \
      --out      C:\Users\Ben\AppData\Local\Temp\sdwin\p3\engine-ab-<arm>.json

EDM Show and PTZ are IDENTICAL at HEAD, and BOTH per-engine sensitivity
controls went RED, so the instrument has teeth on this machine and the identity
is not a vacuous pass. `--fixtures` points at LAPTOP WORK; `deck_script.verify_fixtures`
re-verified all 16 fixture observations (mac 5, windows-installed 11) against
their MANIFEST.sha256 before use. Nothing was written into the clone.

# (f) THE WINDOWS SUITE, IN THE CLONE AT HEAD

    cd C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc
    HEAD 09c42e509162b27f187952d794e4a1206660d90f
    PORCELAIN 0
    $env:PYSTRAY_BACKEND = 'dummy'
    .venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"

    Ran 1099 tests in 68.925s
    OK (skipped=6)
    SUITE_EXIT 0

The Mac reports the same 1099 tests; the skip counts differ (6 on Windows vs 2
on the Mac) because the suite skips platform-specific arms on each host.

# (g) NOTHING LANE-STARTED LEFT

READ-ONLY `Win32_Process` listing taken before /complete:

    --- BROWSERS (read-only, SessionId + CreationDate) ---
    BROWSERS none
    --- PYTHON under the clone or LAPTOP WORK (must be none) ---
    PYTHON_TOTAL 0 LANE_LEFTOVER 0
    --- PROCESS-CLASS ORDER over every process ---
    CLASS i_PROTECTED = 99
    CLASS ii_RECORDED_LANE = 0
    CLASS iii_LANE_PATH_UNRECORDED = 0
    CLASS iv_NOT_LANE = 179
    --- PROTECTED tray still running ---
    PROTECTED 16020 loopMIDI
    PROTECTED 5268 STEAMDECK-MIDI-RECEIVER-2-Tray
    PROTECTED 23640 STEAMDECK-MIDI-RECEIVER-2-Tray

NO BROWSER EXISTS ON THE LAPTOP AT ALL - chrome.exe, msedge.exe and firefox.exe
all return nothing - so there is no browser in Ben's session 1 created after
this link started, and no `NEEDS-MASTER: browser in Ben's session` line is
owed. This link started no bridge and no UI process: the interval instrument
replaces MidiOut with a recorder and binds no socket, so the BROWSER CLASS
RULE's `--no-browser`/`BROWSER` clauses had nothing to apply to. No process
this link started survives, and THIS LINK STOPPED NOTHING: every process it
started was awaited to exit, so class (ii) is empty by construction rather than
by killing.

Classification used the PROCESS-CLASS ORDER with (i) PROTECTED tested FIRST,
before any recorded-pid test (sdpick KJ's finding). Class (iii) is empty, so no
`NEEDS-MASTER: sdpolish unrecorded lane-path process` line is owed.

NO MIDI PORT WAS OPENED by anything this link ran, on either machine. The tray
kept UDP 45123 and TCP 7723; this link bound no port at all.

# (d) BAR 1 AT HEAD - a clock change must not change bytes

## Mac, candidate HEAD vs tag v0.4.9 (e66ff44)

One shared packet stream for every comparison:

    .venv/bin/python -B scripts/showready/deck_script.py --out /tmp/sdpolish-p3/ab/deck-script.json
    script_sha256 9256621abf62eb21e6c345ef286b6b7fcc087a2db87b8f682ce7fcf7703a993e
    file_sha256   b642eee8ea7afeb5e965b3bb5e62c03cc130c8efaa611dcdb96d112d6942edba
    steps 732   packets 47039   seconds 469.716666743

    .venv/bin/python -B scripts/showready/ab_run.py --candidate HEAD \
      --preset '.showready/fixtures/mac/presets/<NAME>.json' [--section windows] \
      --script /tmp/sdpolish-p3/ab/deck-script.json \
      --scratch /tmp/sdpolish-p3/ab/scratch --out /tmp/sdpolish-p3/ab/<OUT>.json

| preset | section | arm | messages A | messages B | mappings exercised | different mappings | unexercised | passed | exit |
|---|---|---|---|---|---|---|---|---|---|
| EDM Show | windows | B1 (flat) | 1531 | **1531** | 56 / 56 | 0 | 0 | **true** | 0 |
| EDM Show | windows | B2 (sectioned) | 1531 | **1531** | 56 / 56 | 0 | 0 | **true** | 0 |
| PTZ | windows | B1 (flat) | 1395 | **1395** | 52 / 52 | 0 | 0 | **true** | 0 |
| PTZ | windows | B2 (sectioned) | 1395 | **1395** | 52 / 52 | 0 | 0 | **true** | 0 |
| default | - | B1 | 1531 | **1531** | 56 / 56 | 0 | 0 | **true** | 0 |

Byte-identical to v0.4.9 for every mapping in EDM Show, PTZ and default, with
every mapping exercised and none unexercised. Both candidate arms equal A on
the sectioned fixtures, as the instrument requires.

## Windows, at HEAD

`engine_ab.py` for the Windows-installed EDM Show and PTZ: both IDENTICAL,
exit 0, with both per-engine sensitivity controls RED. Full table and the
LOCALAPPDATA finding in (e2) above.

## The Mac arm of (e): BASE vs HEAD, no regression

Same instrument, same interpreter, two `git archive` trees under
`/tmp/sdpolish-p3/mac-{base,head}`, run through
`/tmp/sdpolish-p3/mac_timing.py` which enforces the LOAD RULES per arm.

| arm | receiver default clock | relative_cc n | p50 | p95 | max | fade n | fade p50 | fade p95 |
|---|---|---|---|---|---|---|---|---|
| BASE 778eaa7 | time.monotonic | 375 | 40.0343 ms | 40.9230 ms | 41.4446 ms | 128 | 4.2015 ms | 4.6387 ms |
| HEAD 09c42e5 | windows.clock.now | 375 | 40.0443 ms | 40.9980 ms | 41.2815 ms | 128 | 4.2556 ms | 4.7040 ms |

NO REGRESSION: the p50 of the 40 ms repeat differs by 0.010 ms between BASE and
HEAD, the p95 by 0.075 ms, and the fade emits exactly 128 messages on both. The
two arms are indistinguishable, which is the expected result and the reason:
`time.get_clock_info` on the Mac reports resolution **4.1666666666666667e-08
for BOTH `monotonic` and `perf_counter`**, so there is no coarse clock here to
improve on. The Mac arm can only show a regression; it cannot show the fix.

### Load record for both Mac arms (LOAD RULES, per arm)

| | BASE | HEAD |
|---|---|---|
| quiet gate (load1 < 4.0 immediately before) | **PASSED at 2.61**, waited 0.0 s | **PASSED at 2.69**, waited 0.0 s |
| load1 before / after | 2.61 / 2.69 | 2.69 / 2.92 |
| max load1 in any in-arm sample (INVALID if > 5.0) | **2.8** | **3.0** |
| whole-machine samples (every 2 s; brief requires <= 5 s) | 14 | 14 |
| `pgrep -f "while True: pass"` before / after | EMPTY / EMPTY | EMPTY / EMPTY |
| `foreign_lines` before / after | **0 / 0** | **0 / 0** |
| vault sync `obsidian-headless ... --continuous` (re-resolved by pgrep) before / after | 0.0% / 0.0% | 0.1% / 0.0% |
| lane engine server.mjs (RECORDED, never counted; raise over 25%) | 1.7% | 0.0% |
| non-lane process over 50% of one core for > 10 s | **none** | **none** |
| breaches | **[]** | **[]** |
| VERDICT | **VALID** | **VALID** |

The only processes sampled above 20% of one core were pid 398 (WindowServer /
SkyLight) and pid 18429 (a WebKit XPC service) in the BASE arm, plus the lane
engine: WindowServer and kernel_task are RECORDED, NOT COUNTED by the extended
validity, and none held above 50% for over 10 s. `.metadata_never_index` was
created in `/tmp/sdpolish-p3/` and in the A/B scratch BEFORE the first file was
written, and each candidate tree was built ONCE per revision, not per arm.

NO OTHER LANE WORK WAS IN FLIGHT, INCLUDING THIS LINK'S OWN (MASTER 13, 20:34
ruling (a)): the bar 1 A/B replays and every laptop act were finished and
confirmed exited before the first quiet gate was sampled. This is why the Mac
timing arm ran last.

MEMORY, recorded because the brief asks for it: free memory was 12.2-12.4%
across both arms, under the 25% line. The rule bars starting a THIRD concurrent
process tree under 25%; these arms ran as the only lane process tree on the
machine, one arm at a time, so no such tree was started. No process died
without a report.

OBSERVER EFFECT (MASTER 13, 20:26): the quiet gate was sampled BEFORE each arm,
the in-arm sampler is what watched the arm, nothing tight-polled during a live
arm, and the orchestrator session's own checks happened BETWEEN arms. The
orchestrator session is recorded as lane infrastructure and never counted.

A DETECTOR CORRECTION MADE BEFORE ANY ARM RAN, recorded because it would have
voided every arm for a reason that is not real. The first draft of the
foreign-load detector matched the local-LLM-* path extension against the whole
command line. That flagged (i) the lane's OWN engine
`local-LLM-engine/engine/server.mjs`, which MASTER 13 (19:42 (2)) rules is lane
infrastructure, and (ii) any `claude` session carrying a local-LLM path in its
`--add-dir` arguments - the exact false positive MASTER 13 (19:42 (3)) names.
The detector now matches on the EXECUTABLE plus the FIRST SCRIPT ARGUMENT only,
excludes the lane engine by path, and applies the local-LLM test only to script
interpreters. Verified against the live machine before the arms: `foreign_lines`
empty, with two idle `local-LLM-deepseek` proxies correctly RECORDED-not-counted
(0.0% each, neither a bench driver) per clause (1), and the lane engine and
orchestrator recorded separately.

A MEASUREMENT NOTE ON `ps pcpu`, which changed what this link did. An early
sample read the vault sync at 71.5% of one core, which under the vault-sync
rule would have held the arm and owed a `NEEDS-MASTER` line. `top -l 2` on the
same pid moments later read **0.0%**, as did `ps` on the next call. `ps pcpu` on
macOS is a decayed recent average, not an instantaneous reading, so a single
high sample is not evidence of the sustained state the rule is about. The rule
as written asks whether the process HOLDS above its threshold for a duration,
so the decision was moved to the in-arm sampler, which takes 14 samples per arm
and requires a sustained streak. Both arms recorded the vault sync at 0.0-0.1%
throughout, so no hold and no NEEDS-MASTER line was owed.

# SUMMARY, AND WHAT IS OWED

| item | state |
|---|---|
| (a) clock inventory, committed before the change | DONE, commit d135281 |
| (b) one clock, `windows/clock.py: now()` = `perf_counter` | DONE, commit 8f1a98a |
| (c) tests that fail when reverted | DONE, 12 tests; TWO fail on revert on the Mac, a third is a Windows-only detector and is labelled as such |
| (d) bar 1 byte-identical, Mac and Windows, plus engine_ab | DONE, all arms identical |
| (e) Windows measurement, BASE vs HEAD | DONE, verdict **FIXED** |
| (e2) Windows engine A/B | MEASURED (identical, controls RED) but its LOCALAPPDATA-unset condition is **RED**: a finding, owner P0 |
| (f) Mac and Windows suites green at HEAD | DONE, 1099 tests both |
| (g) laptop left clean, guard compare last | DONE, GUARD GREEN |

## The one thing this link did not deliver, and why

(e2)'s declared environment check - `engine_ab.py` running with LOCALAPPDATA
UNSET - is RED at HEAD, because `ab_run.validate_scratch` (scripts/showready/ab_run.py:33,
and `default_scratch` at :28) still subscripts `os.environ['LOCALAPPDATA']`
behind an `os.name == 'nt'` guard. P0's F5 fix covered `engine_ab.py`'s own
parser default only. Full diagnosis in (e2).

OWNER P0, NOT FIXED HERE ON PURPOSE. P3's scope is which clock bridge timing
reads; editing another item's instrument so that this link's own arm turns
green is the move that makes a green meaningless. The engine comparison itself
was still measured, on an arm explicitly labelled as not satisfying the
condition.

WHAT THE FIX LOOKS LIKE, for whoever picks it up: both lines want the same
`environ.get(...)` treatment `engine_ab.scratch_dir_for` already has, and the
test that proves it must IMPORT `ab_run` and call `validate_scratch` with
LOCALAPPDATA absent - `tests/test_engine_ab_scratch_default.py` asserts on a
pure function and never imports `ab_run`, which is precisely why it stayed
green through this defect.

## For the gate and the judge

- BAR 1 IS UNMOVED: every A/B arm on both machines is byte-identical to v0.4.9,
  and engine_ab is identical for EDM Show and PTZ with both sensitivity
  controls RED. A clock change did not change one MIDI byte.
- BAR 2 IS UNMOVED: 1099 tests green on the Mac and 1099 green on Windows.
- BAR 3 IS NOT TOUCHED BY THIS LINK. P3 started no bridge with a UI, opened no
  browser and bound no port, so it cannot have moved the controller-view
  latency figure lap sdbar3 measures.
- THE NEW INSTRUMENT is pinned: `scripts/showready/clock_intervals.py`,
  sha256 45c80952e9d05c91d4b23d73eab8cb72df1475999d9f32056966da8f27ca4111,
  in SHA256SUMS (19 entries) and enforced by tests/test_showready_rail.py. The
  SAME file, verified by digest, drove all four measurement arms on both
  machines.
- OWED TO THE GATE: nothing from (a)-(g) except the P0-owned LOCALAPPDATA
  defect above, which this link measured, diagnosed to the line, and left with
  its owner.
