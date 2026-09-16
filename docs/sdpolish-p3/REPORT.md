BASE OF LAP 778eaa78441c0e7d5539f540cfed8aa944142f8b
P3 START ae19c4f6d4070dbe1b3bdf353540aea30751e119

# sdpolish P3 - the Windows bridge clock

GUARD COMPARE: pending (this commit is item (a), the inventory, which item (a)
requires be committed BEFORE any change; no laptop act has happened yet).

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
