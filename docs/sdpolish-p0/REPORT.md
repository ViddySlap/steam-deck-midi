BASE OF LAP 778eaa78441c0e7d5539f540cfed8aa944142f8b

# sdpolish P0 - the CPU and crash guards

GUARD COMPARE: `GUARD GREEN: compare; protected state observed; pythonProcesses=0`
(snapshot before the first laptop act, compare after the last; both exit 0).

## WHY IT LINGERED

The sdcore3 T1 fix of 09-14 was refused admission for scope overlap and archived
rather than queued, so the defect it addressed stayed in the tree. Independently,
every automated run in this lane sets `PYSTRAY_BACKEND=dummy`, which removes the
real tray and therefore removes the defect from view: the class was invisible to
the suite by construction. sdauto A3 fixed the cause (docs/sdauto-a3/REPORT.md:
Mac 94.3% of one core down to 0.3%), but its tests mock `windows.tray` wholesale
- so they cannot see which thread an Icon runs on - and its CPU number came from
a one-off script rather than a rerunnable check. This link makes both classes
rerunnable: a test that patches only `pystray.Icon` and lets the real
`windows.tray` run, and a pinned instrument that runs the real tray path on the
Mac with `PYSTRAY_BACKEND` removed.

## THE BASE REPRODUCTION

Three distinct shapes. They are separate cases because they are different
failures with different fixes, and "the bridge stops receiving" and "the bridge
raises ZeroDivisionError" must not be collapsed into one another.

Command: `PYTHONPATH=<run root> .venv/bin/python -B /tmp/sdpolish-p0/repro_base.py`
(builds each engine at BASE, calls `shortest_tick_interval()`, then does what
`serve_forever` does with the result).

```
update_hz=         0  build OK  shortest_tick_interval() RAISED ZeroDivisionError: float division by zero
update_hz=        -5  build OK  shortest_tick_interval() = -0.2
                       sock.settimeout(min(0.25,-0.2)) RAISED ValueError: Timeout value out of range
update_hz=    100000  build OK  shortest_tick_interval() = 1e-05
                       sock.settimeout(min(0.25,1e-05)) OK -> 1e-05
update_hz=       nan  build OK  shortest_tick_interval() = nan
update_hz=       inf  build OK  shortest_tick_interval() = 0.0
                       sock.settimeout(min(0.25,0.0)) OK -> 0.0
```

### CASE 1 - ZERO: the receive loop raises

`1.0 / 0` raises `ZeroDivisionError` inside `tick_interval_seconds()`, called from
`EngineRegistry.shortest_tick_interval()` (windows/engines/registry.py:203-208 at
BASE), which sits OUTSIDE the per-engine `try/except` in `tick()`. `serve_forever`
catches only `KeyboardInterrupt`. The loop exits.

### CASE 2 - NEGATIVE: the socket refuses the timeout

`1.0 / -5 = -0.2`, and `sock.settimeout(-0.2)` raises `ValueError: Timeout value
out of range`. The loop exits by a different route.

### CASE 3 - INFINITE: a NON-BLOCKING socket, and an exception the handler cannot catch

This shape is its own case and was found by execution, not by reading.
`1.0 / inf` is `0.0`, and `sock.settimeout(0.0)` does not mean "no timeout": it
puts the socket into NON-BLOCKING mode. `recvfrom` then raises `BlockingIOError`,
which is NOT `socket.timeout`, so it escapes the `except socket.timeout` handler
below it and kills the receive loop. Neither of the two named shapes would have
found this one. A huge-but-finite rate (100000) is the separate spin shape: a
10 microsecond timeout.

### THE SAME DEFECT THROUGH THE REAL HTTP PATH, AT BASE

Command: `PYTHONPATH=/tmp/sdpolish-p0/base-tree .venv/bin/python -B
/tmp/sdpolish-p0/real_bridge_put_base.py /tmp/sdpolish-p0/realbridge-base2`
(a real non-tray bridge subprocess on loopback non-default ports, dry-run MIDI).

```
BASE PUT update_hz 0 : [200, {'ok': True, 'path': '.../engines/autopilot.json', ... 'update_hz': 0}]
BASE PUT 100000      : ['ConnectionResetError', '[Errno 54] Connection reset by peer']
BASE alive after PUT : False
BASE version_after   : URLError: <urlopen error [Errno 61] Connection refused>
BASE exit_code       : 1
```

with the bridge's own log:

```
  File ".../windows/receiver.py", line 1055, in serve_forever
    engine_tick = engine_registry.shortest_tick_interval()
  File ".../windows/engines/registry.py", line 207, in shortest_tick_interval
    if engine.active and engine.tick_interval_seconds() is not None
  File ".../windows/engines/autopilot.py", line 311, in tick_interval_seconds
    return 1.0 / self._update_hz
ZeroDivisionError: float division by zero
```

The PUT was ACCEPTED (200) and the stanza WRITTEN, because A2's isolation probe
constructs the engine but never calls `tick_interval_seconds()`. ONE HTTP request
stopped the bridge. PRE-EXISTING at v0.4.9 through a hand-edited config.

## (a) BOUNDS

- `windows/engines/base.py:11-16` `MIN_TICK_HZ = 1.0`, `MAX_TICK_HZ = 120.0` - the
  same bounds `windows/static/index.html:1905,1913` already enforces in the UI.
- `windows/engines/base.py:19-45` `clamp_tick_hz(value, *, default)`. Never raises;
  a non-finite or non-numeric value falls back to `default`. Clamping happens AT
  THE POINT OF ASSIGNMENT, so every division downstream is safe by construction.

Five engines, each with its file:line and its clamp:

| engine | rate field | division at BASE | assignment now clamped at |
|---|---|---|---|
| autopilot | `update_hz` | `autopilot.py:311` | `autopilot.py:160` |
| audio_opacity | `update_hz` | `audio_opacity.py:227` AND `:239` | `audio_opacity.py:124` |
| autopilot_ptz | `update_hz` | `autopilot_ptz.py:148` | `autopilot_ptz.py:109` |
| chaser_stack_dispatcher | `tick_hz` | `chaser_stack_dispatcher.py:190` | `chaser_stack_dispatcher.py:101` |
| ptz_visca | `stream_hz` | `ptz_visca.py:613` | `ptz_visca.py:126` |

THE FIFTH ENGINE, AND WHY A GUARD IS NOT A BOUND. The master named four; the
sweep in (e) found a fifth. `ptz_visca` guarded only the ZERO-AND-NEGATIVE END:
at BASE, `ptz_visca.py:613` reads `base = 1.0 / self._stream_hz if
self._stream_hz > 0 else 0.125`, so 0 and any negative value were already safe
there. It had NO UPPER BOUND, so `stream_hz` 100000 still produced a 10
microsecond interval - the same spin defect through a different door. A guard
that covers one end of a range is not a bound. The clamp at `ptz_visca.py:126`
supplies the missing end (and the now-redundant ternary is left alone: smallest
correct change).

- `windows/engines/registry.py:203-243` `shortest_tick_interval()` now skips an
  engine that raises, or returns a non-finite or non-positive interval, and logs
  it, instead of letting it out into a caller with no handler.
- `windows/receiver.py:34-38` `MIN_SOCKET_TIMEOUT_SECONDS = 0.001`, applied at
  `windows/receiver.py:1051-1064`. A floor, not a fix: the clamps are the fix.
- `windows/engine_config_api.py:79-107,143-147` PUT returns 400 naming the field
  for `update_hz`, `tick_hz` or `stream_hz` outside [1,120], NaN, infinite or
  not a number. Refused BEFORE the isolation probe and before any write.
  `stream_hz` is included because (e) found it; that is a superset of the item's
  wording, and the addition is deliberate. `docs/api.md:50,77` carry the rule.

TESTS: `tests/test_engine_tick_bounds.py`, 20 tests. `{0, -5, 100000, nan, inf}`
per engine against `tick_interval_seconds()`, `shortest_tick_interval()`,
`tick()`, and a REAL `socket.settimeout` - including a test that the floored
timeout leaves the socket BLOCKING, so `recvfrom` raises `socket.timeout` (caught)
and not `BlockingIOError` (not caught), which is Case 3 asserted directly.

### THE REAL-BRIDGE HTTP CHECK AT HEAD

Same script, HEAD tree. Real subprocess, loopback non-default ports, dry-run MIDI:

```
PUT 0            : 400 | invalid autopilot config: update_hz must be a number from 1 to 120 (got 0)
PUT 100000       : 400
PUT -5           : 400
config unchanged : True
alive after PUT  : True | GET /api/version: 200
datagrams sent   : 6
MIDI recorded    : [{"action":"BTN_A","bytes":[144,36,127],...},{"bytes":[128,36,0],...}, ...]
exit/gone        : 0 True
```

The MIDI record is the non-vacuous half: the bridge still turns a following
datagram into real note-on/note-off bytes after the refused PUT. (The first
attempt at this check recorded ZERO MIDI - my datagrams lacked the `seq` field
`protocol/messages.py:126` requires, so they were rejected as invalid packets.
A zero observation is RED, not a pass; the check was fixed, not accepted.)

## (b) THE TRAY MAIN-THREAD INVARIANT

`tests/test_tray_main_thread_invariant.py`, 6 tests. Only `pystray.Icon` is
patched, with a stub that records the thread its `run()` executes on and blocks
on an Event exactly as a real tray loop does; the real `windows.tray` and the
real `win_recv.main` wiring run. `setup_log_tee` and
`acquire_single_instance_lock` are mocked - the single-instance mutex name is the
INSTALLED tray's and must never be taken. Every tray thread is joined explicitly;
no sleep is used as synchronisation.

| platform | --tray | locked behaviour |
|---|---|---|
| darwin | no | no Icon is EVER constructed (A3's fix) |
| win32 | no | Icon IS constructed and runs OFF the main thread, on the "tray" thread; the bridge keeps the main thread |
| linux | no | same as win32 |
| win32 | yes | Icon runs ON the main thread; the bridge is on the "bridge" thread |
| linux | yes | same |
| darwin | yes | refused, exit 2 - see (c) |

RECONCILING (b) WITH (c): the item asks (b) to lock "darwin --tray runs on the
main thread" and (c) to refuse `--tray` on darwin. Both cannot hold. (c) is the
stronger guarantee and the one the master asked for, so the darwin `--tray` arm
of (b) asserts the refusal instead, and a new arm locks the main-thread
invariant on win32 and linux, where the tray actually exists. Nothing is lost:
the invariant is still locked on every platform that has a tray.

## (c) --tray ON DARWIN

The grep, as run: `grep -rn -- "--tray" mac/ scripts/mac/` returns exactly one
line, and it is a COMMENT FORBIDDING the thing, not a launch:

```
scripts/mac/run_receiver.command:40:#    Do NOT use --tray on macOS (windows/tray.py imports ctypes.wintypes). tee mirrors output to the log.
```

No darwin `--tray` launch exists, so the refusal is implemented rather than a
NEEDS-MASTER line. `windows/win_recv.py:216-231`: `--tray` on darwin prints a
plain-ASCII message and returns 2, BEFORE `setup_log_tee` and BEFORE
`acquire_single_instance_lock`, so a darwin `--tray` launch touches neither.

## (d) THE LiveEvents RETRY

`windows/live_events.py:113-137`. At BASE both retry paths spun with at most
`time.sleep(0)`, which yields the GIL but does not deschedule; the Controller
view holds a live EventSource, so the reader is not hypothetical. After
`SPIN_BEFORE_BACKOFF = 64` attempts the reader sleeps `BACKOFF_SECONDS = 0.001`.

`tests/test_live_events_backoff.py`, 5 tests, measured with a threshold declared
before the data: over a 1.0 s wall window with a reader blocked on a writer
stalled mid-publication, the process must burn under 25% of one core.
`test_the_unbounded_shape_really_does_pin_a_core` measures the BASE shape in the
same process, window and instrument and REQUIRES it to exceed that bar, so a
green above cannot be a blind instrument.

## (e) THE AST TRIPWIRE

`tests/test_config_divisor_tripwire.py`. Flags a division whose divisor is a
`self` attribute assigned from a config lookup and NOT clamped where it is
assigned. Declared before the data.

BASE run, from a `git archive` extract of BASE OF LAP scanned with HEAD's
scanner (`PYTHONPATH=/tmp/sdpolish-p0/base-tree .venv/bin/python -B
tests/test_config_divisor_tripwire.py /tmp/sdpolish-p0/base-tree`): **6 sites in
5 engines**

```
windows/engines/audio_opacity.py:227           in tick_interval_seconds() divides by self._update_hz
windows/engines/audio_opacity.py:239           in tick()                  divides by self._update_hz
windows/engines/autopilot.py:311               in tick_interval_seconds() divides by self._update_hz
windows/engines/autopilot_ptz.py:148           in tick_interval_seconds() divides by self._update_hz
windows/engines/chaser_stack_dispatcher.py:190 in tick_interval_seconds() divides by self._tick_hz
windows/engines/ptz_visca.py:613               in tick_interval_seconds() divides by self._stream_hz
```

HEAD: **0**. Per MASTER 13 19:41 this is a PASS: the four named sites are a
floor, and the scan found the four plus audio_opacity's second division and
ptz_visca. The detector is shown to fire on a planted unclamped divisor and to
stay silent on a clamped assignment, on a function that clamps locally, and on a
divisor that is not config-derived.

## (f) THE IDLE SMOKE INSTRUMENT

`scripts/showready/idle_smoke.py`, pinned in `scripts/showready/SHA256SUMS`,
documented in `scripts/showready/README.md`, with a release-checklist line in
`docs/windows-release-checklist.md`. Declared before data: CPU <= 5% of one core,
exit within 5 s, no new crash report. Never `--tray`; the installed tray's ports
(45123, 7723) are refused by assertion. On the Mac it runs WITHOUT
`PYSTRAY_BACKEND=dummy` so the real tray path executes, and asserts the darwin
no-sidecar line; `BROWSER` stays a no-op and `--no-browser` is passed wherever
the entry point supports it. Not in `unittest discover`; its decision and its
load classifiers are unit-tested in `tests/test_idle_smoke_decision.py` (25 tests).

### THE CPU READER IS PROVEN BEFORE ANY NUMBER IS BELIEVED

`--cpu-self-test` spins a child for a fixed window and sleeps another, and
requires busy >= 50% of one core and idle <= 5%. Every run executes it first and
returns INVALID if it fails. This exists because the Windows reader was WRONG
and silently so - see FINDINGS.

| machine | busy | idle | passed |
|---|---|---|---|
| Mac | 99.93 - 99.96% | 0.0% | yes |
| Windows | 91.55% | 0.0% | yes |

### THE ARM TABLE

All Mac arms: `.metadata_never_index` present in the scratch root before the
first file was written; candidate trees built once per revision per session.

MAC (HEAD = f943c7b626730925ac153bd9cde297fcb077d258 unless noted)

| arm | stop | verdict | CPU % of one core | exit s | no-sidecar line | crash reports | load1 | free mem | foreign_lines | loopback scan |
|---|---|---|---|---|---|---|---|---|---|---|
| mac-head | SIGINT | PASS | 0.230 | 0.041 | yes | 0 | 3.29 | 19% | 0 | n/a |
| mac-head | POST /api/shutdown | PASS | 0.230 | 0.205 | yes | 0 | 3.24 | 19% | 0 | n/a |
| mac-5f35bbe (pre-A3) | SIGINT | **FAIL** | **94.254** | 15.004 | no | 0 | 2.71 | 19% | 0 | n/a |
| mac-5f35bbe (pre-A3) | shutdown | **FAIL** | **94.269** | 0.194 | no | 0 | 2.28 | 19% | 0 | n/a |
| mac-head engines ON | shutdown | PASS | 0.951 | 0.090 | - | 0 | quiet | 19% | 0 | 0 (4 rewritten) |
| mac-head engines ON, update_hz 0 | shutdown | PASS | 0.919 | 0.095 | - | 0 | quiet | 19% | 0 | 0 |
| mac-BASE engines ON, update_hz 0 | shutdown | **FAIL** | - | - | - | 0 | quiet | 19% | 0 | 0 |

The 5f35bbe arm reproduces A3's number independently: **94.25-94.27% against
A3's measured 94.3%**. It also exposes a second defect at that revision that A3
did not record: the SIGINT arm took **15.004 s** to exit, because the spinning
tray does not yield to the signal handler.

WINDOWS (clone at HEAD, session 0)

| arm | stop | verdict | CPU % of one core | exit s | crash reports | loopback scan |
|---|---|---|---|---|---|---|
| win-head --no-ui (3 runs) | CTRL_BREAK | PASS | 0.207 / 0.155 / 0.311 | 0.016 | 0 | n/a |
| win-v0.4.9 --no-ui (3 runs) | CTRL_BREAK | PASS | 0.0 / 0.0 / 0.104 | 0.015 - 0.016 | 0 | n/a |
| win-head UI sidecar | CTRL_BREAK | PASS | 0.415 | 0.000 | 0 | n/a |
| win-head UI sidecar | POST /api/shutdown | PASS | 0.311 | 0.125 | 0 | n/a |
| win-head engines ON | shutdown | PASS | 1.245 | 0.188 | 0 | 0 (4 rewritten) |
| win-head engines ON, update_hz 0 | shutdown | PASS | 1.555 | 0.203 | 0 | 0 |
| win-BASE engines ON, update_hz 0 | shutdown | **FAIL** | - | - | 0 | 0 |

WINDOWS IDLE CPU, HEAD vs v0.4.9 - A FINDING, NOT A HOLD. Mean of three pairs:
HEAD 0.224%, v0.4.9 0.035%, difference **0.19 points**, which does NOT exceed the
0.2-point bar on the mean; two of the three individual pairs sit at 0.207. The
direction agrees with sdauto AJ (HEAD 0.36-0.41% vs v0.4.9 0.05-0.10%) but the
magnitude here is smaller. At this level the measurement is near its floor -
v0.4.9 read exactly 0.0 twice, which is a real sub-quantum reading and not a
broken reader, since the self-test reads 91.55% on a spinning process on the same
machine minutes earlier. UNATTRIBUTED: I did not chase a per-thread attribution
for a difference that does not cross the bar. py-spy was not installed.

THE UI SIDECAR ARM ON WINDOWS. The bridge logged neither a tray start nor the
`system tray unavailable:` warning that `windows/win_recv.py:482` emits on
failure, so the sidecar was constructed and run without raising in session 0. Its
icon is not visible in a service session and I did NOT verify visibility - only
that the sidecar path executed and cost 0.415% / 0.311% of one core.

### THE ENGINES-ON ARM AND ITS LOOPBACK SCAN

The qualifying engine, by the master's rule (active at boot in the scratch
factory configs AND its `tick_interval_seconds()` derives from `update_hz`), is
**autopilot**, from the bridge's own log line:

```
INFO engines loaded: Audio Engine(audio_opacity), Autopilot(autopilot), Autopilot PTZ(autopilot_ptz),
Bumper Blast(bumper_blast), Chaser Stack Dispatcher(chaser_stack_dispatcher), Flash Blast(flash_blast),
Global Color(global_color), Gyro Feedback(gyro_feedback), Left Stick Layer(l_stick_layer),
NestDrop(nestdrop), OSC Sync(osc_sync), PTZ VISCA(ptz_visca), StageFlow Bridge(stageflow_bridge),
SteamInput Layer Tracker(steam_input_layer_tracker)
```

`config/engines.factory/ptz_visca.json` points at Ben's Resolume network:
`camera_nic_ip 192.168.0.100` and cameras `192.168.0.203/204/205`. Every
engines-on arm boots from a scratch COPY with **4 addresses rewritten** to
loopback, and the pre-boot scan found **0** non-loopback targets on every arm; a
hit refuses the boot. All laptop engines-on arms ran dry-run MIDI on non-default
ports and opened no loopMIDI port.

### THE SENSITIVITY CONTROL: THE DECLARED ONE DID NOT FIRE

MASTER 13 14:37 declared the control as `update_hz 100000`, FAIL at BASE and PASS
at HEAD. **It does not fire on the Mac**, and I did not move the declared
threshold to make it:

| arm | CPU % of one core | verdict |
|---|---|---|
| BASE, engines ON, update_hz 100000 | 4.883 / 4.105 | PASS (needed FAIL) |
| HEAD, engines ON, update_hz 100000 | 1.378 / 1.346 | PASS |
| BASE, engines ON, update_hz 1e9 (diagnostic) | 4.585 | PASS |

A billion Hz reaches only 4.585%, so the huge-rate spin is CPU-BOUNDED below the
declared 5% bar on this machine at ANY rate: it is not a CPU-detectable event
here, and no threshold within the declared bar would have caught it. Per MASTER
13 14:39, the engines-on arm therefore does NOT guard the engine-tick class via
that control, and I do not claim it does.

**A control that DOES fire, on both machines**: `update_hz 0`, same arm, same
instrument, same thresholds - BASE dies with `ZeroDivisionError` at
`registry.py:207` -> `autopilot.py:311`, HEAD passes clamped to 1 Hz.

| machine | BASE | HEAD |
|---|---|---|
| Mac | **FAIL** (bridge gone, exit 1) | PASS 0.919% |
| Windows | **FAIL** (bridge gone, exit 1) | PASS 1.555% |

It exercises the same class - an unbounded config rate reaching
`shortest_tick_interval()` - through the case that kills rather than the case
that spins. OWED TO THE GATE: whether that substitution satisfies 14:39 is the
master's call, not mine. `scripts/showready/README.md` records both results so a
later gate cannot pick the silent control by accident.

## (f2) THE ENGINE A/B INSTRUMENT

**F5** - `scripts/showready/engine_ab.py` read `os.environ["LOCALAPPDATA"]` while
the argument parser was being BUILT, so it exited 1 with `KeyError` on the laptop
before reading a single argument; not even an explicit `--scratch` could avoid
it. `scratch_dir_for(environ, os_name)` resolves after parsing and falls back
through TEMP/TMP, and returns a string so the Windows branches are testable from
macOS. `tests/test_engine_ab_scratch_default.py` includes an AST check that no
`os.environ[...]` subscript exists anywhere in the instrument - the SHAPE, not
the one instance. I did not run engine_ab on the laptop: that is P3's first real
use, and PG re-runs it.

**F6** - `engine_ab.py` hardcoded audio_opacity's `outputs.protocol` to `"midi"`,
so the OSC branch of `audio_opacity._send_master` was NEVER compared. Verified on
the laptop: `C:\Program Files\STEAMDECK MIDI Receiver 2\config\engines\audio_opacity.json`
has NO `protocol` key, so the code default `osc` is what actually ships.
`--audio-opacity-protocol` selects the surface and DEFAULTS TO OSC;
`required_surfaces()` replaces what was briefly a mutated module constant.

| run | audio_opacity observations | identical across arms |
|---|---|---|
| `--audio-opacity-protocol osc` | midi 0, **osc 58** | yes, both B arms |
| `--audio-opacity-protocol midi` | **midi 58**, osc 0 | yes, both B arms |
| `--control sensitivity-audio_opacity-osc` | - | **NO - different_sources ['audio_opacity'], exit 1, control_expected True** |

## (g) NO REGRESSION

| check | result |
|---|---|
| Mac suite `python -m unittest discover -s tests -p "test_*.py"` | **OK, 1077 tests** (run twice, order-independent) |
| Mac node checks: ui_reload, ui_sections, ui_controller, ui_controller_macro, ui_version | **all GREEN** |
| Windows suite in the clone at HEAD | **OK, 1077 tests** |
| bar 1 A/B, EDM Show, Mac | identical; 56/56 mappings exercised, 1531 messages both arms, 0 different, 0 unexercised |
| bar 1 A/B, PTZ, Mac | identical; 52/52 mappings exercised, 1395 messages both arms, 0 different, 0 unexercised |
| engine_ab, Mac, osc and midi | identical on both B arms, every engine covered |

`tests/ui_controller_geometry.cjs` was NOT run: it is the real-Chromium geometry
check whose `networkidle` wait never settles against the live Controller view,
which is exactly what P1 is rebuilding this lap.

## (h) THE LAPTOP

Bundle route, both directions verified, `pull_bundle.ps1` sha256
`d9be95406ee30937352c51a5713eaf6be827ae48b850870a00e7a1d42567833e` (the pinned
value). Six bundles; the last: `BUNDLE6_SHA256
e463837f1979b9425e54d682e0ff44690e8b2a791306a0a07f810e662b580086`, and every run
ended `FETCH_HEAD` == `-Expected`, `PINNED_HEAD` == the Mac HEAD,
`PORCELAIN_LINES 0`, **exit 0**. No GitHub fetch from the laptop at any point.

BROWSER LISTING (read-only `Win32_Process`, name/SessionId/CreationDate):
**no chrome.exe, msedge.exe or firefox.exe existed at all**, in any session. No
browser was created in Ben's session 1 during this link.

PROCESS INVENTORY, classified by the PROCESS-CLASS ORDER, protected tested first:

```
PROTECTED(installed) pid=16020 session=1 loopMIDI.exe
PROTECTED(installed) pid=5268  session=1 STEAMDECK-MIDI-RECEIVER-2-Tray.exe  created 08/16/2026 00:29:37
PROTECTED(installed) pid=23640 session=1 STEAMDECK-MIDI-RECEIVER-2-Tray.exe  created 08/16/2026 00:29:37
```

No class (iii) unrecorded lane-path process, and no protected process in the lane
record. Every process this link started is gone: `NONE - every process this link
started is gone`. The installed tray predates this link by a month and was never
touched.

ONE INTERVENTION: two of my own python processes (pids 310368, 345444, session 0,
under the CLONE) were stopped by pid after the first `--no-ui` arm hung - see
FINDINGS 3. They were classified PROTECTED-first and matched class (ii) RECORDED
LANE PID, and both were proved gone.

## FINDINGS - defects in my own instruments, each caught by running it

Recorded because each one produced, or would have produced, a wrong number in
this report.

1. **The Windows CPU reader measured the wrong process and always read 0.0%.**
   A positive control caught it: a child spinning a whole core measured 0.0% of
   one core, identical to a sleeping child. The venv's `Scripts\python.exe` is a
   LAUNCHER that re-execs the real interpreter, so the pid started is not the pid
   that burns CPU; and `OpenProcess`'s return was left as ctypes' default
   `c_int`, truncating a pointer-sized HANDLE. Every Windows CPU number before
   this fix was meaningless and no Windows arm could ever have FAILED on CPU.
   Fixed by summing over the process tree via a Toolhelp32 snapshot and giving
   the three calls real argtypes/restypes, and permanently guarded by
   `--cpu-self-test`, which every run now executes before any arm.

2. **The declared engines-on sensitivity control does not fire** (above). Reported
   rather than repaired by moving a declared threshold.

3. **The quiet gate hung forever on Windows.** It treated an unavailable load
   average as "not yet quiet"; Windows has none, so the first `--no-ui` arm sat
   in the gate for 25 minutes and never started. An unavailable signal is not a
   failing signal - it now passes and RECORDS itself as unavailable, so no report
   can read it as a measured quiet.

4. **The Windows stop arm signalled its own runner.** `CTRL_BREAK_EVENT` to a
   child in the same process group reached the PowerShell host and the ssh rail:
   the run ended at `IDLE_EXIT=-1073741510` (STATUS_CONTROL_C_EXIT) with the
   console in the PS debugger. The child is created with
   `CREATE_NEW_PROCESS_GROUP` now, and each arm records its own `stop_mechanism`
   because that arm is abrupt on Windows and graceful on the Mac.

5. **A Windows bind failure was scored as a product FAIL.** The HEAD arm of the
   `update_hz 0` control came back FAIL where it must PASS; the bridge's log said
   WSAEACCES 10013, a reserved port range catching an ephemeral port. The bridge
   never bound, so the arm said nothing about the receive loop. A startup death
   carrying a known bind signature is INVALID with the signature named, and a
   refused port is redrawn up to three times.

6. **The F6 OSC control was inert.** It perturbed the default in
   `osc.get("logo_path", ...)`, and the factory config SUPPLIES `logo_path`, so
   the default was never read: the anchor existed exactly once and the control
   changed nothing. PRESENCE IS NOT EFFECT. It now perturbs the clamp inside
   `_send_master`, and two tests were added - a control must edit an emitting
   call, and no control anywhere may perturb a default its factory config
   supplies.

7. **My foreign-load detector classed a `claude` session and the harness engine
   as foreign load**, by matching the patterns against the WHOLE command line and
   by the `local-LLM-*` glob matching `local-LLM-engine/`. Both corrections were
   put to the master before any arm was counted and were ratified at 19:42, which
   also ruled that the clause bites on consumption rather than presence. A third
   correction is recorded here for ratification: the harness ALSO runs
   short-lived node processes out of `local-LLM-engine/` (the advancer, every
   30 s), each briefly above the 5% threshold, and one of them voided a BASE arm
   before it could even be named. The whole engine tree is treated as LANE
   INFRASTRUCTURE - recorded beside every arm with its sampled CPU, never counted.

8. **The suite's own coverage depends on git state.** `test_resolume_home_defaults`
   scans `git ls-files`, which lists TRACKED files only, so a real Windows user
   home literal in a new test file passed on the Mac while the file was untracked
   and failed on Windows after it was committed. Two other Windows-only defects
   surfaced in the same run (a platform-dependent assertion, and both new test
   modules writing `__pycache__` into the pinned kit, which made the suite poison
   a later pin check - an order-dependent red). All three are fixed and the suite
   is verified green twice in a row.

## NEEDS-MASTER

Written to the LANE LOG at 19:44 and superseded by MASTER 13 19:42, which
unblocked the arms; recorded here for the trail. The open item from it is
FINDINGS 7's third correction (the harness advancer), which I applied and am
reporting rather than asking first, because the alternative was arms voided at
random every 30 seconds.
