GUARD GREEN: laptop guard compare LAST act 13:48:12-14 `win_rail.sh run sdauto-a3 scripts/showready/win_guard.ps1 -Mode compare -Baseline sdwin\sdauto-a3\before.json -Out sdwin\sdauto-a3\after.json` exit 0, `GUARD GREEN: compare; protected state observed; pythonProcesses=0` (snapshot FIRST act 13:34:31-34, exit 0).

# sdauto A3 - F5 root fix, F2 measured and fixed on the Mac, --no-browser

Link A3 of run sdauto-q001, lane steamdeck, claude-rc claude-opus-5 on the Mac (unsandboxed). Branch
`chain/steamdeck-20260914`. Entry HEAD = origin = `5f35bbe` (A2). BASE OF LAP `70cebd0` (docs/sdauto-a1/REPORT.md line 1).
Product commit `38de0a4c3dae84411fe2ba06a1ae4d117b13dfec`; this report and its evidence are the following docs-only commit
(README.md, docs/sdauto-a3/ only; no windows/ or tests/ byte changes after 38de0a4).

## Verdict in one screen

| Question | Answer | Evidence |
| --- | --- | --- |
| F5: Mac exit code after POST /api/shutdown | BASE `70cebd0`: wait status 133 (128+5, SIGTRAP) and a new crash report. HEAD `38de0a4`: **exit 0**, no crash report | section 3, Mac arms |
| F2 on the Mac | SAME CAUSE as F5, FIXED by the same change. 94.2-94.3% of one core and SIGINT ignored at BASE and at the parent `5f35bbe`; 0.3% and SIGINT exit 0 at HEAD | section 3 |
| F2 cause (file:line) | `windows/tray.py:185` runs `pystray.Icon.run` on a daemon thread named "tray"; on darwin that reaches `pystray/_darwin.py:108` `self._app.run()` off the main thread. `sample` puts 2226 of 2347 samples of that thread in `-[NSApplication run]`, 2171 of them inside `-[NSApplication reportException:]` (os_log symbolicating a call stack). Single-variable control: the same BASE tree with `PYSTRAY_BACKEND=dummy` (the tray thread dies with NotImplementedError) is 0.3% and exits 0 on SIGINT | evidence/mac/base-sample-callgraph-excerpt.txt, arms-base-dummy-sigint.txt |
| F2 on Windows (`--no-ui`, no tray) | NO SPIN at either revision (0.00-0.52% of one core). Ctrl-C exits 0 with graceful teardown at BOTH revisions when the console has Ctrl-C processing enabled | section 4 |
| Installed v0.4.9 tray (the show build), read-only | **not spinning**: 0.6250 CPU-s over 60.004 s = 1.042% of one core = 0.033% of 32 logical cores | section 4c |
| Suites | Mac 989 tests OK (skipped=2) + 4 node checks; Windows clone at 38de0a4: `Ran 989 tests`, `OK (skipped=6)`, exit 0 | section 6 |

## 1. The platform rule (windows/win_recv.py)

`_should_start_receiver_tray(platform, tray_mode) -> bool`, called once in `main()` as
`_should_start_receiver_tray(sys.platform, args.tray)`, only inside the UI-on block (unchanged: `--no-ui` never starts a tray).

| platform | non-tray (no `--tray`) | `--tray` |
| --- | --- | --- |
| win32 | True (today, unchanged) | False (the sidecar is never used; `run_tray_mode` owns the tray, unchanged) |
| darwin | **False** (new) + one INFO line `system tray not started on darwin; stop with POST /api/shutdown` | False |
| linux (and any other) | True, which is today: pystray's X/AppIndicator backend is tried and a construction failure is already caught as `system tray unavailable` WARNING | False |

The Windows sidecar Quit still calls `receiver.request_shutdown` (`ReceiverTray(..., quit_callback=receiver.request_shutdown)`
unchanged; asserted by `test_win32_non_tray_constructs_runs_and_stops_receiver_tray` and the existing
`test_main_wires_both_tray_modes_to_the_http_shutdown_function`). `--tray` mode is not touched on any platform.

Consequence for the Mac: the menu-bar icon (Open web UI / Quit) is gone. Stop is Ctrl-C, `POST /api/shutdown`, or SIGTERM.
The macOS "native menu-bar Quit" path that sdcore2-gate F5 inferred would also trap no longer exists.

## 2. The flag

`--no-browser` (store_true, default off). Suppresses `_open_browser_delayed` in non-tray mode, and in the `--tray`
already-running path (the single-instance mutex is held by another process) it logs
`single-instance: another tray-mode process is running at <url>; --no-browser set, exiting` and returns 0, which is
today's return code there. Without the flag every path behaves as before. No launcher passes it
(`git ls-files | grep -E '\.(ps1|command|bat|cmd|sh)$' | xargs grep -l -- --no-browser` exit 1, no match), so every existing launcher is unchanged.
Documented in `docs/windows-receiver.md` (Mapping UI section, next to `--no-ui`) and `README.md` (macOS stop line).

Live check on the Mac at HEAD (`docs/sdauto-a3/scripts/browser_live.sh`, BROWSER = a recorder script that appends its argv
to a file and exits 0, 5 s run, SIGINT):

| argv | exit | recorder invocations |
| --- | --- | --- |
| no flag | 0 | 1 (`http://127.0.0.1:58811`) |
| `--no-browser` | 0 | 0 (no record file) |

## 3. F2 and F5 on the Mac

Instrument: `docs/sdauto-a3/scripts/mac_arm.sh <tree> <label> <sigint|shutdown>` (sha256 d5fd628c...). Each tree is
`git archive <rev>` into /tmp/sdauto-a3/<arm>/tree with `.showready/fixtures/mac/presets/*.json` copied over
`config/presets/`. It runs, from the tree, under `perl -e '$SIG{INT}="DEFAULT"; exec @ARGV'` (so a background job does
not inherit SIG_IGN; sdcore-gate wrapper check):

```
BROWSER=/usr/bin/true <run root>/.venv/bin/python -B -u -m windows.win_recv --listen 127.0.0.1:<free udp> \
  --map config/windows_midi_map.json --midi-port "IAC Driver DECK_IN" --feedback-port "IAC Driver DECK_OUT" \
  --pulse-port "IAC Driver PULSE_OUT" --timeout 2.0 --ui-port <free tcp> --dry-run --no-engines --no-pulse --no-osc-relay
```

That is the Mac launcher argv (`scripts/mac/run_receiver.command`) with loopback non-default ports, plus `--dry-run` and
the load rules' `--no-engines --no-pulse --no-osc-relay`. DEVIATION, stated: the load rules say `PYSTRAY_BACKEND=dummy` for
any UI-on bridge; the main arms leave it UNSET because the real darwin tray is the variable under test, and one control arm
sets it. The real tray put a status item in the menu bar for about 35 s per BASE/parent arm, as sdcore2-gate's did.
CPU = `ps -o time=` delta over a 30-s window divided by the wall time of that window (and the mean of 30 `ps -o %cpu=`
samples, one per second). Stop = SIGINT (or POST /api/shutdown), poll `kill -0` every 0.25 s for 5 s, `wait` for the
status; SIGTERM only if still alive. Load: every arm had `pgrep -f "while True: pass"` empty and `foreign_lines=0`
before and after (`docs/sdauto-a3/scripts/load_check.sh`; shown to fire: a planted `zsh /tmp/sdauto-a3/run-all.sh`
gave `foreign_lines=1`, then 0 after it ended).

| Arm (evidence/mac/) | Rev | Tray | load1 before | CPU-s / wall s | % one core | ps %cpu mean | Stop | Exit within 5 s | Status | New crash report |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| arms-base-sigint.txt | 70cebd0 BASE | real darwin | 2.53 | 28.64 / 30.36 | 94.3 | 94.2 | SIGINT | **no** | SIGTERM -> 143 | none |
| arms-base-dummy-sigint.txt (control) | 70cebd0 BASE | PYSTRAY_BACKEND=dummy | 2.31 | 0.09 / 30.55 | 0.3 | 0.1 | SIGINT | yes (<= 0.5 s) | 0 | none |
| arms-parent-sigint.txt | 5f35bbe (A2, parent of 38de0a4) | real darwin | 2.64 | 28.63 / 30.39 | 94.2 | 94.1 | SIGINT | **no** | SIGTERM -> 143 | none |
| arms-head-sigint.txt | 38de0a4 HEAD | none (darwin rule) | 2.31 | 0.10 / 30.57 | 0.3 | 0.1 | SIGINT | yes (<= 0.5 s) | **0** | none |
| arms-base-shutdown.txt | 70cebd0 BASE | real darwin | 2.61 | 28.60 / 30.34 | 94.3 | 94.1 | POST /api/shutdown -> 202 | yes (<= 0.5 s) | **133** (SIGTRAP) | Python-2026-09-15-133208.ips |
| arms-head-shutdown.txt | 38de0a4 HEAD | none | 2.36 | 0.09 / 30.55 | 0.3 | 0.1 | POST /api/shutdown -> 202 | yes (<= 0.5 s) | **0** | none |

Every arm: pid gone afterwards, `lsof -nP -iUDP:<udp> -iTCP:<ui>` exit 1 (ports released). The crash report's pid is
43496 = the base-shutdown bridge; `EXC_BREAKPOINT SIGTRAP`, `"Must only be used from the main thread"`
(evidence/mac/crash-report-base-shutdown-excerpt.txt), matching sdcore2-gate F5. Thread count from `ps -M`: 6 with the real
tray, 4 with the dummy control, 3 at HEAD.

F2 cause, measured: the spin lives on the tray thread in AppKit (`sample <pid> 3`, 13:27, BASE tree, same argv without the
feedback/pulse ports; evidence/mac/base-sample-callgraph-excerpt.txt): Thread_64150225 = Python `thread_run` ->
PyObjC -> `-[NSApplication run]` 2226/2347 -> `-[NSApplication reportException:]` 2171 -> `_os_log_impl` ->
`-[_NSCallStackArray descriptionWithLocale:indent:]` -> `backtrace_symbols` -> dyld symbol lookup. The main thread is idle
in `poll` inside `sock_recvfrom` (2346/2347), so sdcore-gate's earlier "short socket timeout" guess is refuted.
What exception AppKit is reporting in that loop is UNVERIFIED (not captured). Why SIGINT is lost is INFERENCE, not
measured: `pystray/_darwin.py:105` replaces the SIGINT handler with `PyObjCTools.MachSignals.signal(signal.SIGINT, sigint)`,
whose callback needs a working AppKit run loop; the measured fact is that removing the tray (dummy control, HEAD) restores
SIGINT -> exit 0. The fix is the F5 change itself (0 extra lines).

## 4. Windows (laptop, through the rail)

Guard snapshot FIRST (13:34:31, exit 0), compare LAST (13:48:12, exit 0). ssh answered every call (no RAIL_EXIT 255).
Laptop acts in order, logs in evidence/win/ (CR stripped): L0 guard snapshot; L1 read-only state (clone at `d882f97`, porcelain 0,
32 logical cores, zero browsers, tray pids 5268 and 23640 in session 1); L2 bundle; L3 Windows suite; L4-L9 F2 arms;
L10 tray CPU; L11 browser listing; L12 guard compare.

Code route (the verified bundle route): `git bundle create /tmp/sdauto-a3/win/sdpick.bundle d882f97..38de0a4 chain/steamdeck-20260914`
(sha256 1fb17fa0409e201f2d0f318a8d4b3f8481decfc11c27771cd3eba3df8aeee178), `win_rail.sh put`, then the committed
`docs/sdpick-k1/scripts/pull_bundle.ps1` (sha256 d9be95406ee30937352c51a5713eaf6be827ae48b850870a00e7a1d42567833e, copied unchanged)
with `-Expected 38de0a4c3dae84411fe2ba06a1ae4d117b13dfec`: `BUNDLE_SHA256 1fb17fa0...` (same on the laptop), bundle
`is okay`, `FETCH_HEAD 38de0a4c...`, `PINNED_HEAD 38de0a4c...`, `PORCELAIN_LINES 0`, exit 0 (L2). No GitHub fetch.

### 4a. Instrument

`docs/sdauto-a3/scripts/f2.ps1 -Which head|v049 -Udp <port> -Ui <port> -Run <id> [-EnableCtrlC]`, run through `win_rail.sh run sdauto-a3`.
`head`: the bridge runs from the CLONE at 38de0a4 with `--map` pointing at a copy of the clone's `config/` in
`sdwin\sdauto-a3\f2-head-<run>\config` (the clone stays clean). `v049`: `git --no-optional-locks -C <clone> archive v0.4.9^{commit}`
(`e66ff44b36eadb6d43db01680c65279df82cd63c`) extracted into `sdwin\sdauto-a3\f2-v049-<run>\tree`, run from there with its own config.
Both use the clone venv python and the argv
`-B -u -m windows.win_recv --listen 127.0.0.1:<udp> --map <copy> --midi-port DECK_IN --timeout 2.0 --ui-port <ui> --dry-run --no-ui --no-engines --no-pulse --no-osc-relay`
(+ `--no-browser` at head only; v0.4.9 has no such flag, and with `--no-ui` it is a no-op). `PYSTRAY_BACKEND` is deliberately
NOT set; `--no-ui` constructs no tray at either revision (win_recv.py builds both the UI and the tray only inside `if not args.no_ui`).
BROWSER = `<clone venv python, forward slashes> -c pass %s` (the 51b1d5b exit-0 form). Ports checked free first
(Get-NetUDPEndpoint / Get-NetTCPConnection).

`scripts/win_f2.py` (the driver, started with the BASE interpreter `pythoncore-3.12-64\python.exe`, not the venv launcher) starts
the bridge in its OWN hidden console (CREATE_NEW_CONSOLE), records the pid tree (`owned-tree-*.txt`: driver, venv launcher,
conhost, real interpreter), waits for `listening on udp`, sleeps 2 s, then reads GetProcessTimes (kernel+user) on each tree pid
every second for 30 s. Stop: `scripts/win_ctrl.py`, a disposable sender, detaches, `AttachConsole(<bridge launcher pid>)`, REFUSES
if any process on that console is outside the recorded tree, sets its own Ctrl-C ignore, and calls
`GenerateConsoleCtrlEvent(CTRL_C_EVENT, 0)`; if the tree is not gone in 5 s, a second sender sends `CTRL_BREAK_EVENT`; if still
alive, TerminateProcess on the recorded tree only (never reached). `-EnableCtrlC` makes the driver call
`SetConsoleCtrlHandler(NULL, FALSE)` before spawning, clearing an inherited "ignore Ctrl-C" attribute so the bridge starts with
normal Ctrl-C processing, as it would in a console a person opened.

### 4b. Results

| Run (evidence) | Rev | Ctrl-C processing | Tree CPU-s / wall s | % one core | % of 32 cores | CTRL_C_EVENT | CTRL_BREAK_EVENT | Final exit (launcher / interpreter) | Teardown in bridge log |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| head-r3 (L6, laptop-evidence/f2-head-r3) | 38de0a4 | inherited from the rail | 0.1406 / 30.195 | 0.47 | 0.015 | sent (generate=1), **not gone in 5 s** | gone in 0.11 s | 0xC000013A / 0xC000013A | none (killed) |
| head-r4 (L7, f2-head-r4) | 38de0a4 | enabled | 0.0625 / 30.219 | 0.21 | 0.006 | **gone in 0.359 s** | not needed | 0 / 0 | `INFO shutdown requested`, `MIDI panic` |
| v049-r1 (L8, f2-v049-r1) | v0.4.9 e66ff44 | enabled | 0.0312 / 30.086 | 0.10 | 0.003 | **gone in 0.266 s** | not needed | 0 / 0 | `INFO shutdown requested`, `MIDI panic` |
| v049-r2 (L9, f2-v049-r2) | v0.4.9 e66ff44 | inherited from the rail | 0.0000 / 30.271 | 0.00 | 0.000 | sent, **not gone in 5 s** | gone in 0.14 s | 0xC000013A / 0xC000013A | none (killed) |
| head-r1 (L4, superseded driver) | 38de0a4 | n/a | 0.0781 / 30.119 | 0.26 | 0.008 | results lost, see below | | | none |
| head-r2 (L5, superseded driver) | 38de0a4 | n/a | 0.1562 / 30.296 | 0.52 | 0.016 | results lost, see below | | | none |

All CPU is on the real interpreter; the venv launcher and conhost read 0.0 CPU-s in every run. GetProcessTimes resolution on this
laptop is 15.625 ms, so every Windows figure is a few ticks. Every run: all recorded pids `gone=True` (Get-Process by pid),
`PYTHON_PROCESSES_AFTER 0`, UDP port rebind `ok`.

Windows F2 verdict: **no F2 on Windows** in non-tray `--no-ui` mode at either revision: at most 0.52% of one core, against 94% on the
Mac. Ctrl-C is honoured with graceful teardown (MIDI panic logged, exit 0, under 0.4 s) at both revisions when the console has
Ctrl-C processing enabled. Under this rail's inherited ignore attribute (head-r3, v049-r2) neither revision sees Ctrl-C. That is
the rail, identical at both revisions, and removed by the single-variable `-EnableCtrlC` arm. CTRL_BREAK stops both revisions
at once, but ABRUPTLY: exit 0xC000013A, no `shutdown requested`, no `MIDI panic`, so a note held at that moment would get no
note-off. A3 changes nothing on Windows: the darwin rule returns True on win32 and `--no-ui` never reaches it.
NOT measured: Windows non-tray WITH the UI (the sidecar ReceiverTray on a non-main thread). The item prescribed `--no-ui`,
so whether the Windows sidecar spins is UNVERIFIED-BY-EXECUTION.

Superseded driver runs, stated rather than dropped. r1 (`scripts/superseded/win_f2_r1.py`: FreeConsole+AllocConsole, then
CTRL_C to the shared console) and r2 (`win_f2_r2.py`: attach from the driver itself) each ended with the DRIVER's launcher exit
0xC000013A before the stop results were saved, and the bridge log shows no teardown. The driver ran under the venv launcher,
which holds its child in a kill-on-close job, so when the driver died the job took the bridge down with it. r3 onwards starts the
driver with the base interpreter and sends every event from a disposable sender process. Their CPU figures (0.26%, 0.52%) are
consistent with r3/r4. No process outlived any run (L4/L5 `gone=True` for every pid, guard GREEN).

### 4c. The running installed v0.4.9 tray (read-only)

`scripts/tray_cpu.ps1 -Seconds 60` (L10): `Get-Process -Name STEAMDECK-MIDI-RECEIVER-2*` filtered to paths under
`C:\Program Files\STEAMDECK MIDI Receiver 2\`, TotalProcessorTime before and after a 60 s Stopwatch. No signal, no attach, no debugger.

| pid | role | session | started | CPU-s delta | % one core | % of 32 cores |
| --- | --- | --- | --- | --- | --- | --- |
| 5268 | PyInstaller bootloader (parent) | 1 | 2026-08-16T00:29:37 | 0.0938 | 0.156 | 0.0049 |
| 23640 | tray app (child of 5268) | 1 | 2026-08-16T00:29:37 | 0.5313 | 0.885 | 0.0277 |
| total | | | | 0.6250 over 60.004 s | **1.042** | **0.0326** |

The show build does NOT spin a core. Its lifetime totals agree: 24664.7 CPU-s for pid 23640 since 2026-08-16 is also about 1% of
one core. That figure is arithmetic on the BEFORE line, not a separate measurement.

### 4d. Browsers (BROWSER CLASS RULE b)

`scripts/browsers.ps1` (L11, 13:48:04, READ-ONLY Win32_Process): `BROWSER_PROCESSES 0` (no chrome.exe, msedge.exe or firefox.exe in
any session); L1 at 13:34:45 also listed none. No NEEDS-MASTER line. No process was stopped outside the recorded trees, and no
protected or unrecorded lane-path process was seen.

## 5. Tests (each fails when its behaviour is reverted)

`tests/test_win_recv_tray_platform.py` (9 tests): platform rule (darwin False, win32 True, linux True); tray mode never starts the
sidecar on any platform; `main()` on injected `sys.platform = "darwin"` with `windows.tray` mocked never constructs `ReceiverTray`,
never runs or stops it; on `win32` constructs it once with `quit_callback=receiver.request_shutdown` before the serve loop and
stops it once at teardown; `--tray` on darwin still calls `run_tray_mode` with `stop_bridge=receiver.request_shutdown`;
`--no-browser` never calls `webbrowser.open`; without it `webbrowser.open("http://127.0.0.1:7723")` is called once and
`time.sleep(1.2)` precedes it (sleep patched, thread joined); the already-running path with and without the flag.

Changed existing test, named: `tests/test_bridge_shutdown.py::test_main_wires_both_tray_modes_to_the_http_shutdown_function`
keeps every assertion and now pins `win_recv.sys.platform` to `win32` for `main()`. Its non-tray assertion
`tray_callback == [receiver.request_shutdown]` describes the sidecar tray, which by design no longer starts on darwin.

Revert proof: `.venv/bin/python -B docs/sdauto-a3/mutant_sweep.py` exit 0, `SWEEP GREEN` (docs/sdauto-a3/mutant_sweep.json):

| Mutant | One-site change | Result |
| --- | --- | --- |
| M0 | clean copy (3 modules) | GREEN, Ran 23 OK |
| M1 | rule returns True (darwin starts the sidecar) | RED: test_platform_rule, test_darwin_non_tray_... |
| M2 | rule returns False (win32 regresses) | RED: test_platform_rule, test_win32_non_tray_..., the existing shutdown wiring test |
| M3 | tray-mode clause removed | RED: test_tray_mode_never_starts_the_sidecar |
| M4 | main() back to `if not args.tray:` | RED: test_darwin_non_tray_never_constructs_or_stops_receiver_tray |
| M5 | --no-browser ignored in non-tray mode | RED: test_no_browser_never_opens_a_browser (+ a leaked-thread failure in the next test) |
| M6 | --no-browser ignored in the already-running path | RED: test_already_running_with_no_browser_exits_without_opening |
| M7 | non-tray startup never opens the browser | RED: test_without_no_browser_opens_once_after_the_delay |
| M8 | win32 sidecar not stopped at teardown | RED: test_win32_non_tray_constructs_runs_and_stops_receiver_tray |
| M9 | the existing shutdown test without its win32 pin | RED on darwin: proves the pin is needed |

## 6. Suites and bars

| Command | Result |
| --- | --- |
| MAC SUITE `.venv/bin/python -m unittest discover -s tests -p "test_*.py"` (with PYSTRAY_BACKEND=dummy BROWSER=/usr/bin/true, at 38de0a4 working tree before commit) | exit 0, `Ran 989 tests in 18.523s`, `OK (skipped=2)` |
| MAC SUITE exactly as the lane writes it (no env), on the report commit tree | exit 0, `Ran 989 tests in 18.849s`, `OK (skipped=2)`; the four node checks exit 0 again; mutant sweep re-run exit 0 SWEEP GREEN |
| `node tests/ui_controller_check.cjs` / `ui_controller_macro_check.cjs` / `ui_reload_check.cjs` / `ui_sections_check.cjs` | exit 0 each: PASS / 48 disk writes match, 72 refused / PASS / PASS |
| WINDOWS SUITE (L3) `win_rail.sh run sdauto-a3 suite.ps1 -Label a3-suite1` (docs/sdpick-k1/scripts/suite.ps1 copied unchanged) in the clone at `HEAD 38de0a4c...` | `Ran 989 tests in 60.275s`, `OK (skipped=6)`, EXIT 0; launcher 324996 and child 321248 gone=True; PYTHON_PROCESSES_AFTER 0 |
| Bar 1 on the Mac at 38de0a4 | see section 7 |

Bar 3 (timing with the controller view open) was NOT re-run by A3: OWED TO THE GATE. The change is outside the MIDI send path,
but on darwin a UI-on bridge now constructs no tray thread, where before it constructed a dummy-backend tray whose thread died
at once. Engine A/B was not re-run: no engine file changed.

## 7. Bar 1 (Mac)

Script: `.venv/bin/python -B scripts/showready/deck_script.py --out /tmp/sdauto-a3/w3/deck-script.json` (exit 0; script_sha256
9256621abf62..., 732 steps, 47,039 packets, 469.7 s; the same script sha as A1 and A2).

| Command (`.venv/bin/python -B scripts/showready/ab_run.py --candidate 38de0a4c3dae84411fe2ba06a1ae4d117b13dfec --section windows --script /tmp/sdauto-a3/w3/deck-script.json ...`) | Exit | Result |
| --- | --- | --- |
| `--preset '.showready/fixtures/mac/presets/EDM Show.json' --scratch /tmp/sdauto-a3/w3/scratch-edm --out /tmp/sdauto-a3/w3/mac-edm.json` | 0 | passed; B1 and B2 each 732 steps, 56 of 56 mappings exercised, 1,531 messages on A and B, different_mappings [], unexercised [] (the same totals as A2) |
| `--preset '.showready/fixtures/mac/presets/PTZ.json' --scratch /tmp/sdauto-a3/w3/scratch-ptz --out /tmp/sdauto-a3/w3/mac-ptz.json` | 0 | passed; B1 and B2 each 732 steps, 52 of 52 mappings exercised, 1,395 messages on A and B, different_mappings [], unexercised [] (the same totals as A2) |

Results and stdout are in docs/sdauto-a3/bar1/. Afterwards `pgrep -fl "capture_runner|ab_run|win_recv"` exit 1 (none running).
Bar 1 runs `--no-ui`, so it could not reach the tray rule; this re-run confirms the bytes rather than assuming them.
Windows bar 1: OWED TO THE GATE.

## Notes for the next link

- On macOS the non-tray bridge has no menu-bar icon now. Stop it with Ctrl-C, `POST /api/shutdown` (exit 0) or SIGTERM. Pass
  `--no-browser` to any UI-on bridge you start; BROWSER no-op is still required for older revisions.
- A Windows bridge started through the rail inherits "ignore Ctrl-C". To test Ctrl-C, clear it in the spawning process
  (`SetConsoleCtrlHandler(NULL, FALSE)`) or use `scripts/win_f2.py -EnableCtrlC`'s pattern. Never send a console event from a
  process that shares the rail's console, and never run a driver under the venv launcher if its children must outlive it
  (kill-on-close job).
- CTRL_BREAK stops a Windows bridge abruptly (0xC000013A, no MIDI panic) at v0.4.9 and at HEAD: a fact for Ben, not changed here.
- Laptop work dir `sdwin\sdauto-a3` holds `before.json`, `after.json`, the four f2-* arm folders (tree copy, bridge logs,
  owned-tree records) and the bundle. Nothing is running.
