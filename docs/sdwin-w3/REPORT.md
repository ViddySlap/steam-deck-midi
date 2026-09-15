GUARD GREEN: final compare exit 0 against the original W3 snapshot; protected state unchanged; no Python under CLONE or LAPTOP WORK.

# sdwin W3 - A/B MIDI instrument

No candidate MIDI byte difference was observed in the completed, rate-checked matrix. All eight presets pass, including B1 and B2 for the sectioned Mac EDM Show and PTZ fixtures. These are controlled-clock synthetic Deck replays; live scheduler timing and hardware are separate gates.

Entry HEAD: `a205d16df61a9d171194fc33f94c3b0331ce7b3d`. Tested candidate and Windows clone: `e8a64f4efe526ba3210731083355c95472915e2e`. Branch: `chain/steamdeck-20260914`. No merge or deployment.

## Per-preset results

Command producer: the exact argv/exit for each row is in [evidence/matrix.json](evidence/matrix.json); the reusable one-line commands are in [the README](../../scripts/showready/README.md). Each result contains raw captures, per-step bytes/latencies, packet hashes, mappings, arm identities and cleanup proof.

| Preset | Arm | Steps | Mappings exercised/total | MIDI messages A/B | Identical | NOT COVERED | Exit |
| --- | --- | ---: | ---: | ---: | --- | --- | ---: |
| [mac-default](results/mac-default.json.gz) | B1 | 732 | 56/56 | 1531/1531 | yes | none | 0 |
| [mac-edm-show](results/mac-edm-show.json.gz) | B1 | 732 | 56/56 | 1531/1531 | yes | none | 0 |
| [mac-edm-show](results/mac-edm-show.json.gz) | B2 | 732 | 56/56 | 1531/1531 | yes | none | 0 |
| [mac-ptz](results/mac-ptz.json.gz) | B1 | 732 | 52/52 | 1395/1395 | yes | none | 0 |
| [mac-ptz](results/mac-ptz.json.gz) | B2 | 732 | 52/52 | 1395/1395 | yes | none | 0 |
| [windows-installed-default](results/windows-installed-default.json.gz) | B1 | 732 | 56/56 | 1531/1531 | yes | none | 0 |
| [windows-installed-edm-show](results/windows-installed-edm-show.json.gz) | B1 | 732 | 56/56 | 1531/1531 | yes | none | 0 |
| [windows-installed-ptz](results/windows-installed-ptz.json.gz) | B1 | 732 | 52/52 | 1395/1395 | yes | none | 0 |
| [windows-installed-test-1](results/windows-installed-test-1.json.gz) | B1 | 732 | 63/63 | 1615/1615 | yes | none | 0 |
| [windows-installed-v1-default](results/windows-installed-v1-default.json.gz) | B1 | 732 | 61/61 | 1711/1711 | yes | none | 0 |

B1 uses the same flat fixture bytes as A. B2 uses the sectioned fixture and --preset-section windows. The two additional installed preset JSON files (test 1 and v1 Default) are included. Active markers, historical backups, settings and macro libraries are verified fixture dependencies, not extra selected presets.

## Executed controls

The exact commands and exits are retained in [controls.json](evidence/controls.json) and [matrix.json](evidence/matrix.json). All controls use the same instrument. Accelerated controls explicitly use --speed 50; full-rate A/A uses --speed 1.

| Control | Exit | Observed assertion |
| --- | ---: | --- |
| [determinism-1](results/determinism-1.json.gz) | 0 | A/A identical; 1531 messages per arm; cross-run bytes also identical |
| [determinism-2](results/determinism-2.json.gz) | 0 | A/A identical; 1531 messages per arm; cross-run bytes also identical |
| [aa-real-1](results/aa-real-1.json.gz) | 0 | A/A identical; 1531 messages per arm; cross-run bytes also identical |
| [aa-real-2](results/aa-real-2.json.gz) | 0 | A/A identical; 1531 messages per arm; cross-run bytes also identical |
| [Sensitivity](results/sensitivity.json.gz) | 1 | Only BTN_A differs: note-on `90 24 7f` versus `90 25 7f`; copied B note 36 -> 37 |
| [Coverage](results/coverage.json.gz) | 1 | BTN_A is NOT EXERCISED; 55/56 mappings, 728 steps |
| [Dead seam](results/dead-seam.json.gz) | 1 | Zero MIDI messages on both sides is RED |
| [Unit mutation](evidence/unit-mutation.json) | 0 / 1 / 0 | Ten focused tests: pristine, note-on status fault, restored |
| [Rate detector](evidence/pacing-red.json) | RED / GREEN | Actual old capture fails the rate check; every final capture passes measured interval checks |

Ordinary-clock A/A diagnostic: [aa-wall-noise](results/aa-wall-noise.json.gz), exit 1, 1079/1070 messages. Differing mappings: DPAD_DOWN_LONG_PRESS, DPAD_LEFT_LONG_PRESS, DPAD_RIGHT_LONG_PRESS, DPAD_UP_LONG_PRESS. Both code arms are v0.4.9. This diagnostic measures time-driven sampling noise, not a candidate regression. The controlled-clock A/A runs above are the determinism controls.

## Measured wall pacing

Each row below is recomputed from send_monotonic_ns in the result, not inferred from its configured frequency. Values are milliseconds for A; all candidate arms also pass the minimum-interval check. Scheduling delays are retained, and the latency columns are informational for the later timing gate. The six first comparisons ran together; five remaining jobs followed.

| Preset | Wall seconds | 60 Hz min / median / max ms | 10 Hz min / median / max ms |
| --- | ---: | --- | --- |
| mac-default | 475.806 | 16.683 / 16.692 / 27.370 | 100.017 / 100.026 / 100.987 |
| mac-edm-show | 476.141 | 16.685 / 16.697 / 18.083 | 100.022 / 100.033 / 125.717 |
| mac-ptz | 475.892 | 16.686 / 16.696 / 51.241 | 100.023 / 100.033 / 105.205 |
| windows-installed-default | 475.754 | 16.682 / 16.692 / 21.960 | 100.017 / 100.026 / 101.164 |
| windows-installed-edm-show | 475.977 | 16.683 / 16.692 / 26.340 | 100.016 / 100.025 / 117.548 |
| windows-installed-ptz | 476.027 | 16.683 / 16.692 / 26.942 | 100.018 / 100.026 / 101.267 |
| windows-installed-test-1 | 476.097 | 16.678 / 16.693 / 19.715 | 100.013 / 100.030 / 103.545 |
| windows-installed-v1-default | 475.328 | 16.678 / 16.693 / 17.208 | 100.013 / 100.031 / 103.019 |

Every arm records 229 measured adjacent intervals per sweep rate. Script SHA256: `9256621abf62eb21e6c345ef286b6b7fcc087a2db87b8f682ce7fcf7703a993e`. Packet stream SHA256: `c06cfa67469f551b9c28f600349a117bbfee7d3e692e3a54a02f8b18b63a6bc9`. The full script is embedded in every result.

| Identity | Value |
| --- | --- |
| A commit | `e66ff44b36eadb6d43db01680c65279df82cd63c` |
| A Git tree | `e2fc57e4da26a62085719a89cf7579362c1f0174` |
| B1 commit | `e8a64f4efe526ba3210731083355c95472915e2e` |
| B1 Git tree | `f7659e7c9f92eec70536afc3c910ae6627b044cb` |
| ab_run.py SHA256 | `49cadcdba1009b0c4ec417bd922c4ff064bc90b2e8805f4517e9eca1a5224af3` |
| capture_runner.py SHA256 | `3a64c52c4cc0f97068ffc8f69d18b174a66ed9d642e78356bf3f1845830a9aca` |
| deck_script.py SHA256 | `c0661d3331140f0571e593b87f72bfb6b1ac2b632b96cb97208f941fbd2a8f72` |

No candidate difference required bisecting. Bisect, live controller-view timing, physical Deck end stops, Ben's hardware check and rollback execution are UNVERIFIED-BY-EXECUTION in W3.

## Scope and seam

W3 adds only scripts/showready, its focused tests and this report/evidence.
No product MIDI send code, mapping, UI, API route or parked mac/ file changed.
The installed v0.4.9 stays frozen. No real MIDI input/output was opened.

Both arms run the SAME capture_runner.py, with the archived arm first on
sys.path. Imports of windows.* and protocol.* are checked to resolve inside
that arm. The runner calls that arm's windows.win_recv.main. The recorder is installed
at that arm's MIDI output factory. Raw bytes encode MIDI 1.0 status
(nibble plus zero-based channel), then two data bytes. note_on, note_off and
control_change are checked on user channels 1 and 16; panic matches
MidoMidiOut's sixteen CC123 messages. windows/midi.py is byte-identical between
v0.4.9 and the tested candidate (`git diff v0.4.9 HEAD -- windows/midi.py`).

A separate venv Python check compared midi_bytes with mido.Message(...).bytes()
for 16 channels, three message types and three data pairs: 144 cases GREEN.
It called no port API. The command and all byte observations are retained in
[evidence/mido-byte-oracle.json](evidence/mido-byte-oracle.json).

The runner installs fail-closed mido and rtmidi modules before importing the
bridge. Opening input, output, virtual ports or a backend constructor raises;
a violation in the child terminates it with exit 70, including a background
thread. A fake mido records no open calls in the negative test. The recorder
substitutes OUTPUT only. No feedback or clock-source MIDI input is opened.

All arms use --no-engines --no-pulse --no-osc-relay --no-ui, without --tray.
Both driver and runner bind-test non-default loopback UDP/UI ports; actual
receiver socket bind produces the ready file. No readiness log is trusted.
The argv, selected config hash, arm commit/tree/archive hashes, actual bound
address and PID are retained in each result. Flat file bytes are copied
unchanged into A and B1; B2 receives the sectioned fixture bytes unchanged
and --preset-section windows. Each disposable config has presets/replay.json
and .active containing replay.json. Neither input fixture nor archived code
is rewritten. The sensitivity control alone changes its copied B config.

## Deterministic time and limits

The receiver's existing injectable clock argument is set to 1000 seconds plus
the script timestamp at actual UDP receipt. Every mapping still uses the arm's
original dispatch and MIDI methods. The original serve_forever loop, fades,
relative repeats, staged timers and timeout checks all run. Legal heartbeat
packets provide 10 ms timer probes. The socket wrapper verifies every received
payload and sequence against the common script; startup and every subsequent
MIDI message remain in the comparison. Receipt counts and length-prefixed
packet stream SHA256 must match on both sides. A lost packet is fatal.

This is controlled-clock synthetic Deck input through real loopback UDP and
real bridge-to-MIDI-backend calls. It is not hardware MIDI capture or a live
scheduler certification. Wall send times and recorder monotonic_ns are real;
per-step send-to-first-message latency is informational only. Full-rate runs
use speed=1. Actual wall sends preserve each Deck-event gap after any late wake; mapped inputs cannot form catch-up bursts. Heartbeat probes use offsets
within the current dwell, and axis waits yield until their deadline to avoid
OS short-sleep coalescing. A result fails if any measured axis interval is below
the scripted minimum. The per-arm interval count/minimum/median/maximum is
reported, so scheduling delay is visible rather than renamed 60 Hz. Accelerated controls are labeled speed=50 in their JSON. The
ordinary-clock A/A diagnostic demonstrates why uncontrolled fade sampling
must not be mistaken for a product byte regression.

No direct mapping in the tested fixtures requires engines to emit MIDI.
Therefore the mapping NOT COVERED list is empty. Engine subscriptions,
feedback-driven state, controller-view timing, physical end stops, hardware
checks and rollback remain their separate later gates. Unmapped Action IDs
still appear in the step comparison. A mapping with absent input, an unhandled
button or no mapping-directed MIDI is NOT EXERCISED and fails; it is never
silently waived. Startup messages cannot pay mapping coverage.

## Script parameters and sources

Command: `.venv/bin/python -B scripts/showready/deck_script.py --out /tmp/sdwin-w3/deck-script.json`.
The generator verifies both W2 manifests before consuming presets; ab_run
verifies them again for each run. No live config/presets user files are read.
The default preset in the fast unit test is the tracked repository fixture.

- config/actions.yaml: 75 IDs, 62 button-like and 13 axis-like.
- deck/xinput_send.py:26: AXIS_MIN_INTERVAL=1/60 second; :794-804 applies it
  per axis. Replay intervals are 16,666,667 ns and 100,000,000 ns.
- deck/xinput_send.py:340-349 and :489-497: static HID axes, signed stick
  decoding minus calibrated centers and unsigned trigger decoding. Stick
  ranges: LX [-32886,32649], LY [-33202,32333], RX [-33048,32487],
  RY [-32432,33103]. Trigger representable range: [0,65535].
- deck/xinput_send.py:502-515: signed pad position ranges [-32768,32767].
  :524-534: integrated gyro PITCH/YAW/ROLL clamped to [-32767,32767].
  These are source-derived representable values, not measured physical end
  stops. Explicit zero probes supplement HID reader deadzone suppression.
- deck/xinput_send.py:647-662 resolves an incoming key directly to an Action
  ID; :776-788 sends that ID with state down/up. config/actions.yaml lists
  LONG_PRESS and LAYER_2 as independent IDs. The archived bindings JSON is
  an empty setup stub, so the physical Steam Input bindings were not inspected.
  The sender forwards the chosen binding ID without deriving hold/layer IDs; the bridge does not infer a LONG_PRESS ID from a base-ID dwell.
- windows/receiver.py:640-660 and :454-462: relative_cc starts on down,
  repeats while held and cancels on up. This is bridge hold-time behavior,
  so every button ID is replayed at 100 ms and again at 1.6 s dwell.
- windows/receiver.py:604-636: macro_cc long_press starts a fade even for
  a short down; :362-381 advances it. :668-720 implements staged trigger,
  modifier hold and refresh. windows/config.py:22-31 supplies defaults.
  The verified preset settings specify 2-second fades, 80 ms staged trigger
  delay, 2000 ms modifier hold, 30 Hz macro updates and 40 ms relative repeats.
- windows/receiver.py:979-1045 uses a 250 ms maximum idle poll. The isolation
  gap is max(fade duration, staged trigger delay, modifier hold) + 0.25 s
  = 2.25 s, with exact per-preset/mapping sources in script.parameters.
  It follows button releases and completed axis sweeps. Intra-sweep intervals
  preserve the requested maximum and slower rates.

The deterministic script has 732 input steps and 47,039 total UDP packets,
including timer heartbeats; duration 469.716666743 seconds. Axis sweeps use
nine evenly spaced endpoints/intermediate points plus zero, go out and back,
and finish at zero. The script digest excludes its own sha256 field; the
separate file digest includes the final canonical JSON newline. Packet stream
hashing uses network-order four-byte packet length followed by payload bytes,
so packet boundaries cannot disappear in concatenation. Exact digests are
in every result JSON, alongside the script, runner and ab_run hashes.

## Teardown and protected Windows state

The driver waits for every input and the final timer horizon, observes another
300 ms with unchanged capture size, then terminates each bridge. It never
calls /api/shutdown (absent on v0.4.9). Every process is waited for; on Mac,
kill(pid,0) must return ProcessLookupError. Result arms.*.cleanup contains
method, exit code, PID absence and proof method. The raw capture is flushed
per line before termination; terminate bypasses normal release_all, so the
script releases all button trials and drains delayed work before stopping.
This does not claim shutdown/release-all MIDI behavior equivalence.

Windows suite execution used W1's pinned rail and suite script, with a clean
clone fast-forward and exact expected HEAD check added. All remote scripts
and logs are under C:\Users\Ben\AppData\Local\Temp\sdwin\w3. No installer,
pip install, orphan checkout mutation or installed/runtime change occurred.
W1's no-op browser and dummy pystray apply to existing suite UI tests. Suite
PIDs are waited for and checked with Get-Process; a final path inventory and
guard compare reject any clone/work Python. The final compare is the last
laptop act; no artifact download follows it.

## Reproduction and handoff

[scripts/showready/README.md](../../scripts/showready/README.md) contains the
exact one-line command for each Mac and Windows-installed preset, the script
generation command and all control commands. Example for the show preset:

```bash
.venv/bin/python -B scripts/showready/ab_run.py --candidate HEAD --preset '.showready/fixtures/mac/presets/EDM Show.json' --section windows --script /tmp/sdwin-w3/deck-script.json --out /tmp/sdwin-w3/mac-edm.json
```

The default Mac scratch path is explicitly /tmp/sdwin-w3; --scratch can place
a later link's work under its own /tmp/sdwin-<link>. On Windows the default is
LOCALAPPDATA\Temp\sdwin\w3 and --scratch must remain under that sdwin root.
All result files above 1 MB are gzip-compressed. SHA256SUMS pins every file
under scripts/showready; tests/test_showready_rail.py remains unchanged.
The next link must fast-forward the Windows clone from the last tested code
commit to this report commit, after its own guard snapshot. Fixtures stay
host-local and ignored. This lap does not grant the complete show-ready bar.

## Instrument findings and resolved probe errors

- Real-rate claim caught by actual timestamps: the first absolute-deadline
  sender caught up in bursts after host delays. Re-evaluating the retained
  [unpaced capture](evidence/unpaced-edm.json.gz) with the rate detector is RED:
  its A-arm 60 Hz intervals include 26,416 ns and have median 65,750 ns.
  [pacing-red.json](evidence/pacing-red.json) retains the measurements and
  source hash. Those preliminary runs do not earn real-rate credit.
- Requiring a fresh sleep for every 10 ms heartbeat then compounded host
  sleep delays. That superseded batch was ended: the session interrupt
  reached the first cohort, and queued arms failed closed on planted invalid
  packets sent only to their recorded non-default loopback ports. The driver
  exited 130. Independent kill(pid,0) checks proved all 24 receiver PIDs gone;
  five queued-arm results also retain owner wait/cleanup proof. See
  [timer-probe-abort.json](evidence/timer-probe-abort.json). No stopped probe
  earns a completed replay result. The final sender preserves Deck-event
  gaps, schedules timer probes within the dwell and uses yielding axis waits.
- Initial Mac scratch used tempfile.gettempdir(), which resolves to the
  per-user macOS temporary directory. That violated this link's required
  /tmp/sdwin-w3 convention. The default and allowed root were corrected,
  with a red-before/green-after test. Preliminary evidence was superseded;
  every final result records work under /private/tmp/sdwin-w3 (the resolved
  spelling of /tmp/sdwin-w3).
- The new root-refusal test initially assumed a repository could not itself
  be under /tmp. A scratch-copy mutation run exposed that test-only assumption.
  It now checks the filesystem root, outside the permitted work directory on
  either platform. The refusal assertion is preserved. The failed probe is
  retained in unit-mutation-preliminary.json; the final ten-test mutation
  probe is pristine GREEN, changed note-on status RED, restored GREEN.
- The first generator probe encountered a list-valued macro_library.json
  among the verified files. The generator now skips non-object documents;
  only preset mapping documents contribute delay bounds. No receiver started
  in that failed probe.
- A direct signal attempt from a separate Mac tool process was denied by the
  OS during the first scratch-path investigation. That batch completed on its
  own, and each owner recorded PID absence. This was not declared an executor
  block. Later stopped probes used the owned session/packet failure paths
  described above and independently proved every PID gone.
- A progress POST initially had a mistyped launch token and was refused.
  The corrected progress POST was accepted. No terminal envelope was used
  for that correction.

A pre-existing product diagnostic remains at windows/receiver.py:876-881:
--no-engines leaves the registry None, and every axis input logs the caught
on_axis_event AttributeError before continuing to mapping dispatch. It occurs
in both arms. Mapped axis MIDI is still captured and covered. This lap does
not change that MIDI path or suppress its diagnostic.

## Suite execution and scope

Final Mac command, from the run root:

```bash
TMPDIR=/tmp/sdwin-w3 PYSTRAY_BACKEND=dummy BROWSER=true .venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

`Ran 838 tests in 11.587s`; `OK (skipped=2)`; exit 0.
[evidence/mac-suite-event-paced.log](evidence/mac-suite-event-paced.log)
contains the full output. The tested working code was then committed as
`e8a64f4efe526ba3210731083355c95472915e2e` and pushed with the required SSH
transport overrides; ls-remote equaled the local HEAD.

Final Windows command, in the isolated clone:

```powershell
C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

Executed with `scripts/showready/win_rail.sh run w3 /tmp/sdwin-w3/suite.ps1 -Label windows-w3-event-paced`.
`Ran 838 tests in 17.561s`; `OK (skipped=5)`; exit 0. Exact clone HEAD was
`e8a64f4efe526ba3210731083355c95472915e2e`. Get-Process proved suite PID
262116 gone. The final cleanup also proved earlier W3 suite PIDs 274068,
272392, 273716 and 276348 absent and no Python executable under CLONE or
LAPTOP WORK. Full output is in windows-suite-event-paced.txt; final executed
PowerShell sources are suite.ps1 and cleanup.ps1 beside it.

Skips are unchanged from W1/W2: Mac skips the PowerShell guard test and the
pre-existing cc_base test; Windows skips the two POSIX launcher tests, two
POSIX rail tests and that cc_base test. No pre-W3 assertion was changed.
Earlier intermediate suite logs remain under evidence/ with their actual
counts; they are not substituted for the final lines above.

Final laptop act:

```bash
scripts/showready/win_rail.sh run w3 scripts/showready/win_guard.ps1 -Mode compare -Baseline 'C:\Users\Ben\AppData\Local\Temp\sdwin\w3\before.json' -Out 'C:\Users\Ben\AppData\Local\Temp\sdwin\w3\after-event-paced.json'
```

Exit 0: `GUARD GREEN: compare; protected state observed; pythonProcesses=0`.
This compares against the ORIGINAL W3 before.json snapshot, so it covers all
W3 Windows work, including the extra suite after the pacing correction.
There was no later laptop act, including downloads. The final compare JSON
stays on the laptop; guard-event-final.txt retains the exact stdout.

`git diff a205d16 HEAD -- windows protocol deck config mac tests/test_showready_rail.py`
is empty: product source, the parked Mac kit and existing rail tests are
unchanged. SHA256SUMS covers the new instrument and updated README. No
installer download, dependency install, deployment or API route was added.
The final report commit contains evidence only; the next link pulls it after
its own guard snapshot.

## Final artifact verification

`.venv/bin/python -B /tmp/sdwin-w3/verify-final.py` independently recomputed
packet digests, raw-byte/step equality, actual rate intervals, cross-run A/A
bytes and required cleanup assertions from the captured records. Result:
GREEN; 16 result files, 18 comparisons. The exact verifier source and its
observations are retained in [verification.json](evidence/verification.json).
All final result instrument hashes match the pinned kit.
