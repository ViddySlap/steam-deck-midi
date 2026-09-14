# sdcore2 gate (RG) report

Gate for repair lap `sdcore2` (run `sdcore2-q001`), executor claude-rc on the Mac,
unsandboxed, real IAC ports, 2026-09-14 13:52-14:05 MDT. Branch
`chain/steamdeck-20260914`, gated HEAD `e0344e6f390ea6cf5b3af3ed9f59d54f29b9f263`
(R2). Launch records for R1 and R2 were fetched from the engine: both `done`,
envelope status `complete` (R1 commit c246c94; R2's envelope carries no `commit`
field, its commit is HEAD e0344e6). docs/sdcore2-r1/REPORT.md,
docs/sdcore2-r2/REPORT.md and docs/sdcore-gate/REPORT.md were read first.

No product code was changed by this gate. The only commit is this directory. No
test-only defect was found, so none was fixed. Scratch was under /tmp/sdcore2-gate/.

## Verdict summary

| Step | Result |
| --- | --- |
| 1. Suite at HEAD | GREEN: `Ran 821 tests in 7.025s` / `OK (skipped=1)`, exit 0 |
| 1. Mutations (a)-(d) plus one variant | 5 of 5 RED, all restored GREEN with sha256 equal (`ALL_BITE`) |
| 2. F1 controls | FIXED. Pre-repair control f809be1 still exits 2; HEAD fresh pull boots (no UI and UI arms); sectioned arm selects macbook and creates the file; existing windows file is byte-identical |
| 3. F3 on the real bridge | ROUTE WORKS, EXIT CODE FAILS THE BAR. 202, held note gets its note-off, panic on 16 channels, 45123/7723 released, second bridge binds. But the process dies by SIGTRAP (exit -5), not exit 0. New finding F5 |
| 4. API bar | PASS: the three detectors pass by name; Tray Quit now maps to POST /api/shutdown; no remaining gap |
| 5. Windows back-fill | AGREE with R1's file:line reading; UNVERIFIED-BY-EXECUTION (no pwsh) |
| 6. Push, porcelain, exclusions, local config | PASS: remote equals HEAD, porcelain empty, no excluded file committed, 36 config files byte-identical before/after the gate, user presets and bridge.local.json untouched by this lap |

## Findings

**F5 (product, INTRODUCED THIS LAP as a reachable path; severity medium): on
macOS, a bridge started with the Mac launcher's argv exits by SIGTRAP (exit code
-5) after an HTTP shutdown, instead of exit 0.** Both runs (pid 23090, pid 23106)
exited -5 at 0.085 s and 0.014 s after the POST. macOS wrote a crash report for
each (`~/Library/Logs/DiagnosticReports/Python-2026-09-14-135749.ips` and
`-135751.ips`, excerpt in evidence/crash-reports-excerpt.txt): `EXC_BREAKPOINT
SIGTRAP`, application-specific info `Must only be used from the main thread`,
faulting thread is NOT the main thread, stack
`-[NSStatusItem _uninstall]` -> `-[NSWindow _close]` -> ... -> `NSWMWindowCoordinator`.

- Where: without `--tray`, `windows/win_recv.py:426` creates `ReceiverTray` and
  `windows/tray.py:185` runs the pystray icon on a non-main thread named "tray".
  The final `tray.stop()` at `windows/win_recv.py:478` stops it, and AppKit
  uninstalls the status item off the main thread and traps.
- Everything else in teardown ran before the trap: `tray.stop()` is the last line
  of the `finally`, after the preset watcher, MIDI out, OSC relay and UI server
  are closed. The IAC capture shows the note-off and panic, and the ports were
  free for the second bridge.
- Single-variable control: the same script, argv and real IAC ports with only
  `PYSTRAY_BACKEND=dummy` added (the dummy backend fails to construct, so
  `tray` is None) gave exit code 0 on both runs (0.16 s, 0.038 s), the same
  note-off and panic bytes, and no new crash report (evidence/f3-real-dummytray.log).
- Why "introduced this lap": the `tray.stop()` line already exists at
  f809be1:457, but at f809be1 `serve_forever` was `while True` and never checked
  a stop event (receiver.py:1009 at f809be1), and SIGINT is ignored on macOS
  (F2). So that `finally` was practically unreachable on a Mac. R2 made it
  reachable through POST /api/shutdown and through the Mac tray's Quit callback.
- Inference, NOT measured: the native macOS menu-bar Quit (`ReceiverTray._quit`,
  tray.py:169, which also calls `icon.stop()`) is likely to hit the same rule.
  The gate did not click the native menu bar.
- R2's native-tray abort is a DIFFERENT failure: its crash report
  (`Python-2026-09-14-134448.ips`, pid 69060) is SIGABRT on the MAIN thread in
  `+[NSApplication sharedApplication]` -> `HIServices _RegisterApplication`
  (`abort() called`) at icon construction. That fits the codex exec context being
  unable to register with the window server. On this claude-rc host the same
  construction succeeds and the bridge boots.
- Impact: the stop does its job (MIDI released, ports freed), but anything that
  checks the exit status sees a crash, and every stop writes a crash report.
  `run_receiver.command` pipes through `tee`, so the launcher masks the status.
  The gate did not check whether a "quit unexpectedly" dialog appears on screen.
- Candidate fixes, not applied (product change, and the gate does not choose):
  skip ReceiverTray on darwin in non-tray mode (run_receiver.command:40
  already keeps `--tray` off macOS, for a different reason), or stop the icon
  on the main thread.

**Observation O1 (not a defect): the two first-run paths leave different disk
state on a flat default.** The direct Python entry point writes no
bridge.local.json when default.json is flat (arm A2b). The launcher snippet
writes `macbook` unconditionally when the file is absent (arm A5), and the
resulting argv boots (arm A5b). Both are what R1 documented. The launcher's
file only matters once a sectioned preset becomes active, and then it selects
macbook, which is the intended Mac default.

**Observation O2: R2's loopback test asserts the REMOTE ADDRESS.**
`tests/test_ui_server.py:173` `test_shutdown_refuses_non_loopback_even_with_forwarded_header`
sets `environ_base={"REMOTE_ADDR": remote}` for 192.168.1.7, 203.0.113.1, ::,
empty and invalid, adds `X-Forwarded-For: 127.0.0.1`, and leaves the test
client's default Host `localhost`. It asserts 403, a "loopback" error, an unset
stop event, and an uncalled callback. A Host-header or forwarded-header check
would pass those requests and fail the test. Mutant (c) confirms it bites.
`:191` also checks refusal while stopping, and `:197` checks that `::1` is
accepted.

F2 (SIGINT/CPU) and F4 (header wrap) remain Ben's backlog items and were not
re-tested.

## 1. Suite and mutations

```
cd /Users/viddyslap/Documents/project-workspaces/steam-deck-midi
.venv/bin/python -m unittest discover -s tests -p "test_*.py"
  exit 0; Ran 821 tests in 7.025s; OK (skipped=1)      evidence/suite-head.log
git status --porcelain   -> empty after the suite
```

Mutations ran in `git -C <run root> archive HEAD | tar -x -C /tmp/sdcore2-gate/tree`,
using the run root's .venv python. An import probe from the copy resolved
`windows.win_recv` to `/private/tmp/sdcore2-gate/tree/windows/win_recv.py`.
Script: scripts/mutate.py. Each mutant runs the WHOLE suite with `-B`,
`PYTHONDONTWRITEBYTECODE=1` and `__pycache__` purged, which avoids lap 1's mtime
bytecode artefact. Anchors must occur exactly once. Pristine: exit 0, 821 OK.
`.venv/bin/python -B scripts/mutate.py` exit 0, `ALL_BITE` (evidence/mutate.log).

| Id | Mutant | Mutant suite | Failing tests (world asserted) | Restored |
| --- | --- | --- | --- | --- |
| a | Tracked default.json replaced by f809be1's sectioned bytes | exit 1, failures=1 errors=2 | test_upgrade_boot `test_git_pull_default_without_marker_or_local_file_boots_everywhere` on darwin, win32, linux | exit 0, 821 OK, sha equal |
| b | Darwin first-run default overwrites an existing file (loader guard reduced to `if platform == "darwin":` and `save_if_missing` always `_save(overwrite=True)`) | exit 1, failures=13 | including `test_existing_local_selection_and_sentinel_bytes_survive`, `test_existing_null_or_unavailable_selection_is_not_defaulted`, `test_initialization_does_not_replace_file_created_since_load`, launcher snippet byte preservation | exit 0, 821 OK, sha equal |
| b2 | Variant: only `save_if_missing` overwrites (loader guard intact) | exit 1, failures=5 | race, byte-preservation, and snippet tests | exit 0, 821 OK, sha equal |
| c | POST /api/shutdown skips the loopback check (`if not loopback:` -> `if False:`) | exit 1, failures=7 | `test_shutdown_refuses_non_loopback_even_with_forwarded_header` (5 subtests), `test_non_loopback_is_still_refused_while_stopping` | exit 0, 821 OK, sha equal |
| d | Route returns 202 before the lock and before calling the stop function | exit 1, failures=8 | `test_shutdown_sets_stop_event_and_returns_202`, `test_shutdown_is_idempotent`, `test_unwired_ui_refuses_shutdown`, `test_http_stop_waits_for_shutdown_reply_and_releases_port`, both tray-mode wiring subtests | exit 0, 821 OK, sha equal |

## 2. F1 controls (git-exported trees, no local files)

Command in every arm, run from the exported tree with the run root's python.
This is the run_receiver.command argv plus lap 1's dry-run flags:

```
<run root>/.venv/bin/python -B -u -m windows.win_recv --listen 0.0.0.0:45123 \
  --map config/windows_midi_map.json --midi-port "IAC Driver DECK_IN" \
  --feedback-port "IAC Driver DECK_OUT" --pulse-port "IAC Driver PULSE_OUT" \
  --timeout 2.0 --ui-port 7723 --dry-run --no-ui --no-engines --no-pulse --no-osc-relay
```

("UI" arms drop only `--no-ui`.) Scripts: scripts/boot_arms.py (exit 0, evidence/boot-arms.log)
and scripts/control_f809.py (exit 0, evidence/control-f809be1.log). Before each
arm the script binds UDP 0.0.0.0:45123 and TCP 127.0.0.1:7723 to prove both are
free. Socket ownership comes from `lsof -a -p <child pid> -i`. Every booting
child was stopped with SIGTERM (reaped -15), and both ports were proven free
again before the next arm. Per-arm bridge logs are in evidence/arms/.

| Arm | Tree and local state | Exit | Listen lines and sockets (child) | bridge.local.json after |
| --- | --- | --- | --- | --- |
| C0 control | f809be1, no local, no .active | **2** (did not boot) | `win_recv.py: error: preset section None is not available; available sections: macbook, windows` | absent |
| A1 | 5d778eb (v0.4.9), no local, no .active | -15 (SIGTERM) | `listening on udp://0.0.0.0:45123`; UDP *:45123 | absent |
| A2 fresh-pull sim | HEAD, no local, no .active, --no-ui | -15 | `listening on udp://0.0.0.0:45123`; UDP *:45123 | absent |
| A2b same, with UI | HEAD, no local, no .active | -15 | `mapping UI available at http://127.0.0.1:7723`, `listening on udp://0.0.0.0:45123`; TCP 127.0.0.1:7723 LISTEN, UDP *:45123. GET /api/settings 200 `preset_section: null`, map_path .../presets/default.json | absent (no first-run write, flat default) |
| A3 | HEAD + run root's sectioned PTZ.json, .active=PTZ.json, no local | -15 | `created bridge settings config/bridge.local.json with preset_section=macbook`, `listening on udp://0.0.0.0:45123` | created: `{"preset_section": "macbook"}` (indent 2), sha 7476c269... |
| A3b same, with UI | as A3 | -15 | same plus UI line; GET /api/settings `preset_section: "macbook"`, map_path .../PTZ.json | created, macbook |
| A4 | HEAD + PTZ.json active + existing `{"preset_section": "windows"}` | -15 | `listening on udp://0.0.0.0:45123`, no creation line | byte-identical (sha d9e354ef... before and after) |
| A4b same, with UI | as A4 | -15 | GET /api/settings `preset_section: "windows"` | byte-identical |
| A5 launcher snippet | HEAD, no local; the `python -c` from run_receiver.command extracted verbatim and run in the tree with the venv activated | 0 | prints `PRESET_SECTION=macbook` | created: `{"preset_section": "macbook"}` |
| A5b | A5's tree with the launcher's resulting argv `--preset-section macbook` + dry-run flags | -15 | `listening on udp://0.0.0.0:45123`; UDP *:45123 | unchanged |

F1 is fixed on the Mac path. The Windows half is below (step 5).

## 3. F3 on the real bridge

Script: scripts/f3_shutdown.py, run from the run root, exit 0 (evidence/f3-real.log;
bridge logs f3-real-bridge1.log, f3-real-bridge2.log). The section came from
running the launcher's own snippet against the run root. The file exists, so it
printed `macbook` and wrote nothing. Full engines, UI on 7723, real IAC ports, no
`--dry-run`, `BROWSER=/usr/bin/true` (suppresses only the browser tab). A
python-rtmidi monitor was open on `IAC Driver DECK_IN` throughout.

```
.venv/bin/python -B -u -m windows.win_recv --preset-section macbook --listen 0.0.0.0:45123 \
  --map config/windows_midi_map.json --midi-port "IAC Driver DECK_IN" \
  --feedback-port "IAC Driver DECK_OUT" --pulse-port "IAC Driver PULSE_OUT" --timeout 2.0 --ui-port 7723
```

| Observation | Bridge 1 (pid 23090) | Bridge 2, booted immediately after (pid 23106) | Control: same + PYSTRAY_BACKEND=dummy |
| --- | --- | --- | --- |
| Boot | 1.21 s; engines loaded (14); lsof UDP *:45123, TCP 127.0.0.1:7723 LISTEN, UDP 127.0.0.1:7010 (relay) | 1.22 s; same sockets; `selected MIDI output port: name=IAC Driver DECK_IN index=0` | 1.23 s / 1.22 s |
| Held note | BTN_A down only (no up), seq 900001: IAC got `[144, 36, 127]` | (not sent) | same |
| POST /api/shutdown (first) | 202 `{"stopping":true}` in 0.003 s | 202 in 0.001 s | 202 / 202 |
| Second POST 10 ms later | 202 `{"stopping":true}` (caught while stopping) | connection reset (process already gone) | 202 / reset |
| IAC after POST | `[128, 36, 0]` note-off, then CC 123 value 0 on channels 1-16 (panic) | CC 123 value 0 on 16 channels | identical bytes |
| Log | `released note mapping for BTN_A`; no `input timeout reached` line (the note-off came 0.3 s after note-on, under the 2.0 s timeout) | n/a | same |
| Exit code (`Popen.wait`) | **-5 (SIGTRAP)** at 0.085 s | **-5 (SIGTRAP)** at 0.014 s | **0** at 0.16 s / **0** at 0.038 s |
| Crash report | Python-...-135749.ips (pid 23090) | Python-...-135751.ips (pid 23106) | none written |
| Released | 45123 and 7723 bind free; bridge 2 binds both and opens the IAC ports | free after | free after |

Notes:

- Engine shutdown has no success log line in the code
  (`windows/engines/registry.py:214-219` logs only failures), so it cannot be
  shown from the log. The order (release_all before engine shutdown) is proven
  by R2's test and R2's "Release moved after engines" mutant, not by this run.
- IAC is a CoreMIDI bus, not an exclusive device. "Released" means the second
  bridge opened the same port names and its note-off/panic reached the monitor.
- Exit code 0 was the brief's bar, and it FAILS on the launcher argv: finding F5.
- The launcher script itself was not run. Its `tee` masks the exit status and
  its trailing `read -r` waits for Enter, so it could not have reported one.

## 4. The API bar

```
.venv/bin/python -B -m unittest -v tests.test_ui_server.HtmlApiBarTests \
  tests.test_ui_server.BridgeSettingsApiTests.test_api_inventory_matches_registered_method_paths \
  tests.test_deck_control_api.DeckControlAPITests.test_every_deck_route_is_documented
  exit 0; Ran 3 tests; OK; "HTML API bar: 21 paths registered; HTML parsed; ids unique"
```

(evidence/apibar-tests.log. The first attempt used bare module names, got an
ImportError from my own invocation, and was rerun with the `tests.` package
prefix.) Lap 1's gate made all three detectors bite. `git diff f809be1 HEAD --stat --
windows/static deck` is empty, so this lap added no UI affordance and no Deck
route. docs/api.md:15 documents `POST /api/shutdown`. R2 ran the inventory test
after registering the route and before documenting it, and it failed on
`('POST', '/api/shutdown')` (R2 evidence/inventory-before-doc.log).

Lap 1's table (docs/sdcore-gate/REPORT.md section 4) stands unchanged for every
bridge UI row and every Deck TTY row. The row that changes:

| Affordance | Route in docs/api.md | Gate evidence |
| --- | --- | --- |
| Tray `Quit`: Windows `--tray` (tray.py TrayApp) and the sidecar tray, including the Mac menu-bar tray created in non-tray mode (win_recv.py:426) | POST /api/shutdown | HTTP (win_recv.py:407), the sidecar tray (:426) and `--tray` (:455) all wire `receiver.request_shutdown`. The route works on the real bridge (step 3), but see F5 for the exit code. Native tray clicks were not executed |

No remaining API-bar gap.

## 5. Windows back-fill

I read the three launchers and agree with R1's file:line reading.
`config/windows_receiver_settings.example.json:6` has `"preset_section": "windows"`.

| Launcher | Example loaded | Missing keys added | Local file saved | Section read | bridge.local.json override | `--preset-section` passed |
| --- | --- | --- | --- | --- | --- | --- |
| scripts/windows/start_receiver.ps1 | 25 | 34-40 | 42-44 | 67 | 68-74 | 75-77 |
| scripts/windows/start_installed_receiver.ps1 | 25 | 34-40 | 42-44 | 64 | 65-71 | 72-74 |
| scripts/windows/start_installed_receiver_v2.ps1 | 25 | 34-40 | 42-44 | 64 | 65-71 | 72-74 |

A v0.4.9 `windows_receiver_settings.local.json` with no `preset_section` gets
`windows` added and saved, and that value is passed as argv. A later
bridge.local.json key wins. With the tracked default flat again, a Windows box
also boots with no section at all (arm A2 shape, win32 covered by R1's
`test_git_pull_default_without_marker_or_local_file_boots_everywhere`).
UNVERIFIED-BY-EXECUTION: there is no pwsh on this Mac. It stays in For Ben.

## 6. Push, porcelain, exclusions, local config

```
git rev-parse HEAD                                    e0344e6f390ea6cf5b3af3ed9f59d54f29b9f263
git -c url...insteadOf -c core.sshCommand=... ls-remote --heads origin chain/steamdeck-20260914
                                                      e0344e6f390ea6cf5b3af3ed9f59d54f29b9f263  exit 0
git status --porcelain                                empty (0 lines) before this gate's files
git -c core.quotePath=false log --stat f809be1..HEAD | grep presets/ .local.json osc_sync.json audio_opacity.json
                                                      only config/presets/default.json (R1, tracked, allowed)
git ls-files config | grep ...                        config/presets/default.json, config/engines.factory/{audio_opacity,osc_sync}.json
                                                      (factory files, pre-existing, not touched this lap)
```

| Link | Commit | On origin |
| --- | --- | --- |
| R1 | c246c94 | yes (ancestor of remote head e0344e6) |
| R2 | e0344e6 | yes (remote head) |

Config tree: `find config -type f | sort | shasum -a 256` before the gate's first
action and after its last bridge run gave 36 files both times, and `diff` exit 0
(evidence/config-before.sha, config-after.sha). The gate's bridges ran from the
run root with the real engines and wrote nothing to config/.

Across the whole lap, not only this gate: `config/bridge.local.json` sha
7476c269..., `EDM Show.json` 58e47bfd... and `PTZ.json` 11b37cd6... match R2's
before/after preservation record. The two presets also equal lap 1 S1's
`converted_sha256` in docs/sdcore-s1/evidence.json. Their mtimes (bridge.local.json
12:58:57, EDM Show.json 13:00:49, PTZ.json 04:22:47) all predate R1's launch at
13:25:20. `.active` is `EDM Show.json` (sha cc768739...). The only config file
this lap changed is the tracked default.json (13:29:31, R1).

## For Ben

1. **F5 (new, needs a product decision for a later link):** on the Mac,
   `curl -X POST http://127.0.0.1:7723/api/shutdown` stops the bridge cleanly
   (note-offs, panic, ports freed). The process then dies by SIGTRAP (exit -5),
   and every stop writes a crash report, because the menu-bar tray icon is
   stopped off the main thread (win_recv.py:478, tray.py:185). The native
   menu-bar Quit probably does the same (not clicked). Candidate fixes: no
   ReceiverTray on darwin in non-tray mode, or main-thread icon stop.
2. **Windows launchers (F1 Windows half):** the back-fill reads correct by
   file:line, but no PowerShell ran. Run `scripts/windows/start_receiver.ps1` on
   the Windows box with an old local settings file that has no `preset_section`,
   and confirm it gains `"windows"` and the bridge boots.
3. **Native tray clicks:** Windows `--tray` Quit and sidecar Quit, and the Mac
   menu-bar Quit, were not clicked by any link or the gate.
4. Carried from lap 1 and unchanged: F2 (SIGINT ignored, ~94% CPU on macOS,
   pre-existing) and F4 (header wrap) are backlog choices. Build fingerprint
   still reads 0.4.9. Deck hardware, the travel router and multi-bridge feedback
   were not tested.

## Reproduce

Scripts in scripts/ write under /tmp/sdcore2-gate/:
mutate.py (step 1; needs the tree export and
`git show f809be1:config/presets/default.json > /tmp/sdcore2-gate/default-sectioned-f809be1.json`),
boot_arms.py and control_f809.py (step 2), f3_shutdown.py (step 3; add
`--dummy-tray` for the control arm). Raw captures are in evidence/, with
non-ASCII output backslash-escaped.
