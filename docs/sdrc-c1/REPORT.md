CANDIDATE 2e4292a75f08674fdf5c78358485b27c2d3bd913

GUARD COMPARE (last laptop act, 2026-09-16T09:16:43Z): `GUARD GREEN: compare; protected state observed; pythonProcesses=0`, rail exit 0 (evidence/L08-guard-compare.txt). Snapshot (first laptop act, 09:09:38Z): `GUARD GREEN: snapshot; protected state observed; pythonProcesses=0`, exit 0 (evidence/L00-guard-snapshot.txt).

# sdrc C1 - the 0.5.0 candidate, built on the laptop, staged, frozen-smoked

Executor: claude-rc claude-opus-5 on the Mac, unsandboxed. Mac scratch /tmp/sdrc-c1/. Laptop work dir `C:\Users\Ben\AppData\Local\Temp\sdwin\sdrc-c1\`. Every laptop act went through `scripts/showready/win_rail.sh`; ssh answered every call. Rail transcripts are under docs/sdrc-c1/evidence/ (L00..L08 in order). The installer was NEVER run. Nothing was installed. No tag, release, merge or main push.

## Result in plain words

| Step | Result |
| --- | --- |
| 1 Clone at CANDIDATE | GREEN: bundle route, pinned pull_bundle.ps1 exit 0, clone HEAD 2e4292a = Mac HEAD = origin, porcelain 0, VERSION 0.5.0 |
| 1b Interpreter match | GREEN: v0.4.9 exes bundle `python312.dll`; the build used `py -3.12` = 3.12.10, the script's own hardcoded choice, no edit |
| 2 Build | GREEN on attempt a2 (exit 0, 152.5 s). Attempt a1 EXIT 1 on a script precondition defect (build_exe_v2.ps1:81, finding F1); NEEDS-MASTER written, option (a) taken |
| 3 Stage | GREEN: installer + both exes copied (never moved, never run) to `C:\Users\Ben\Documents\steamdeck-midi-showready\candidate-2e4292a\`, copy sha256 == dist sha256 for all three; SHA256SUMS.txt and BUILD-INFO.txt fetched here |
| 4 Frozen smoke, UI ON | GREEN: every route and check below; exit 0 after POST /api/shutdown; pid tree gone; no listener left; browsers before = after = none |
| 5 Leftovers | GREEN: all 10 recorded pids gone; python.exe total 0; classes PROTECTED 99, RECORDED 0, LANE_PATH_UNRECORDED 0, NOT_LANE 173 |

## 1. Clone at CANDIDATE (bundle route, never GitHub from the laptop)

Mac: `git rev-parse HEAD` = `git ls-remote --heads origin chain/steamdeck-20260914` = 2e4292a75f08674fdf5c78358485b27c2d3bd913. Clone before: HEAD a4b2c01a0db154a610111edb83bf581f88c4220e, porcelain 0 (L01).

```
git bundle create /tmp/sdrc-c1/bundle/steamdeck.bundle a4b2c01a0db154a610111edb83bf581f88c4220e..2e4292a75f08674fdf5c78358485b27c2d3bd913 chain/steamdeck-20260914
sha256 418716d6f9a8172337329425b89fe3dcd00de9842a0e10d890bc69cb739e257c
scripts/showready/win_rail.sh put sdrc-c1 /tmp/sdrc-c1/bundle/steamdeck.bundle
scripts/showready/win_rail.sh run sdrc-c1 scripts/showready/pull_bundle.ps1 -Bundle 'C:\Users\Ben\AppData\Local\Temp\sdwin\sdrc-c1\steamdeck.bundle' -Expected 2e4292a75f08674fdf5c78358485b27c2d3bd913
```

pull_bundle.ps1 is the pinned P1 version (sha256 7b2c34d7adbcdcc7153bf02c33b4b8a897b4ede809ddf2a81830f2224b9bce2a, equal to scripts/showready/SHA256SUMS; `shasum -a 256 -c scripts/showready/SHA256SUMS` all OK). The d9be9540... sha in the lap brief is K1's pre-parameter original, which reads a hardcoded name; the pinned one takes `-Bundle`. Every output line (L03-pull-bundle.txt):

```
BUNDLE_SHA256 418716d6f9a8172337329425b89fe3dcd00de9842a0e10d890bc69cb739e257c
VERIFY The bundle contains this ref:
VERIFY 2e4292a75f08674fdf5c78358485b27c2d3bd913 refs/heads/chain/steamdeck-20260914
VERIFY The bundle requires this ref:
VERIFY a4b2c01a0db154a610111edb83bf581f88c4220e
VERIFY The bundle uses this hash algorithm: sha1
VERIFY C:/Users/Ben/AppData/Local/Temp/sdwin/sdrc-c1/steamdeck.bundle is okay
FETCH From C:\Users\Ben\AppData\Local\Temp\sdwin\sdrc-c1\steamdeck.bundle
FETCH  * branch            chain/steamdeck-20260914 -> FETCH_HEAD
FETCH_HEAD 2e4292a75f08674fdf5c78358485b27c2d3bd913
MERGE  1 file changed, 683 insertions(+)
MERGE  create mode 100644 docs/sdpolish-gate/REPORT.md
PINNED_HEAD 2e4292a75f08674fdf5c78358485b27c2d3bd913
PORCELAIN_LINES 0
RAIL_EXIT 0
```

VERSION in the clone: `0.5.0` (L01). The laptop recomputed the Mac's bundle sha256.

## 1b. Interpreter match (for the evidence report)

(a) v0.4.9's bundled interpreter, read-only. `Get-ChildItem 'C:\Program Files\STEAMDECK MIDI Receiver 2' -Recurse -Filter python3*.dll` -> `PYTHON_DLL_COUNT 0`: the install is onefile (the install dir holds only receiver.ico, the two exes, unins000.dat/.exe). So each installed exe was opened with `[IO.File]::Open(path, Open, FileAccess.Read, FileShare.ReadWrite)`, copied to memory, decoded as Latin-1 and searched with the regex `python3[0-9]{1,2}\.dll`:

| Installed exe | FileVersion | Names found |
| --- | --- | --- |
| STEAMDECK-MIDI-RECEIVER-2.exe | 0.4.9 | `python312.dll` x2 (no other python3NN.dll) |
| STEAMDECK-MIDI-RECEIVER-2-Tray.exe | 0.4.9 | `python312.dll` x2 |

The same method is confirmed against the candidate by PyInstaller's own archive viewer on the staged console exe: `10844752, 2548450, 6945272, 1, 'b', 'python312.dll'` (evidence/archive_viewer.out.txt).

(b) Every interpreter on the laptop (`py -0p`): `-V:3.14[-64] *` (the launcher default) at `...\pythoncore-3.14-64\python.exe`, and `-V:3.12[-64]` at `...\pythoncore-3.12-64\python.exe`. `time.get_clock_info` run from LAPTOP WORK (`py -3.X -B clockinfo.py`, launcher pids recorded, exit 0, gone), L02:

| Interpreter | monotonic | monotonic resolution | perf_counter | perf_counter resolution | time |
| --- | --- | --- | --- | --- | --- |
| 3.12.10 (64 bit) | GetTickCount64() | **0.015625 s** | QueryPerformanceCounter() | 1e-07 s | GetSystemTimeAsFileTime(), 0.015625 s |
| 3.14.3 (64 bit) | QueryPerformanceCounter() | **1e-07 s** | QueryPerformanceCounter() | 1e-07 s | GetSystemTimePreciseAsFileTime(), 1e-07 s |

So the master's recollection is MEASURED TRUE for 3.14 on this laptop: monotonic moved to QueryPerformanceCounter (3.13 itself is not installed and was not measured). Note for the evidence report: at CANDIDATE the bridge clock is `windows.clock.now = time.perf_counter` (sdpolish P3), which is QPC 1e-07 s on BOTH minors, so the bridge's own clock no longer depends on the minor.

(c) `scripts/windows/build_exe_v2.ps1` hardcodes `py -3.12` (both the version check and `py -3.12 -m venv .venv-build`) and has no interpreter parameter. It would therefore use 3.12, the SAME minor as v0.4.9, and 3.12 is installed: no edit and no override were needed. The build log confirms it: `123 INFO: Python: 3.12.10` and `Using Python shared library: C:\Users\Ben\AppData\Local\Python\pythoncore-3.12-64\python312.dll`.

(d) v0.4.9 = Python 3.12 (python312.dll; patch level not readable from the name). Candidate = Python 3.12.10. Clock resolutions as in the table.

## 2. Build

| Step | Command | Exit | Elapsed |
| --- | --- | --- | --- |
| a1 | `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<CLONE>\scripts\windows\build_installer_v2.ps1" -RepoRoot "<CLONE>"` (Start-Process, root pid 360664, cwd CLONE) | **1** | 15.5 s |
| mkdir | `New-Item -ItemType Directory <CLONE>\build` (empty; `git check-ignore -v build/windows-file-version.txt` -> `.gitignore:25:build/`; porcelain 0 before and after) | 0 | - |
| a2 | same command, root pid 353404, 09:12:20.72Z -> 09:14:53.25Z | **0** | 152.5 s |
| a2 inner: build_exe_v2.ps1 | run by build_installer_v2.ps1:15 | 0 (inferred: build_installer_v2.ps1:17 throws on nonzero and it did not; its stdout ends `Build complete.`) | inside a2 |
| a2 inner: ISCC | `ISCC.exe /DAppVersion=0.5.0 installer\windows\steamdeck-midi-receiver-2.iss` | 0 (`Successful compile (11.141 sec)`) | 11.1 s |

a1 stderr (evidence/build-a1.err.txt): `Set-Content : Could not find a part of the path '...\steam-deck-midi-rc\build\windows-file-version.txt'. At ...\build_exe_v2.ps1:81` then `Failed to build receiver EXE before installer packaging.` At a1 the `.venv-build` venv had been created and nothing tracked had changed (porcelain 0).

Versions (L05, tracked pids, all exit 0 and gone):

| Item | Value |
| --- | --- |
| Python | 3.12.10 (tags/v3.12.10:0cc8128, Apr 8 2025) [MSC v.1943 64 bit (AMD64)] |
| PyInstaller | 6.22.3 (pip), contrib hooks 2026.7 |
| pystray / Flask / Werkzeug / Jinja2 / mido / python-rtmidi / Pillow | 0.19.5 / 3.1.3 / 3.1.8 / 3.1.6 / 1.3.3 / 1.5.8 / 12.3.0 |
| pip in .venv-build | 26.2.1 (build_exe_v2.ps1 upgrades it) |
| ISCC found | `C:\Users\Ben\AppData\Local\Programs\Inno Setup 6\ISCC.exe` (not on PATH, not under Program Files (x86): L01 `ISCC_ON_PATH False`, `ISCC_X86 False`, `ISCC_PERUSER True`) |
| ISCC version | `Compiler engine version: Inno Setup 6.7.1` (the compiler banner; the exe's file VersionInfo reads 0.0.0.0) |

pip installed into `<CLONE>\.venv-build` only. No admin prompt, no system-wide install. ISCC printed one warning, recorded not acted on: `The [Setup] section directive "PrivilegesRequired" is set to "admin" but per-user areas (HKCU) are used by the script` (the HKCU Run key).

Last 40 lines, build_exe_v2.ps1 (stdout lines 43-82 of evidence/build-a2.out.txt; its PyInstaller stderr is evidence/build-a2.err.txt, 131 lines, ending `71722 INFO: Build complete! The results are available in: ...\steam-deck-midi-rc\dist`):

```
Collecting pefile>=2022.5.30 (from pyinstaller->-r ...\requirements-build.txt (line 2))
...
Installing collected packages: altgraph, six, setuptools, pywin32-ctypes, python-rtmidi, Pillow, pefile, packaging, markupsafe, itsdangerous, click, blinker, werkzeug, pystray, pyinstaller-hooks-contrib, mido, jinja2, pyinstaller, Flask

Successfully installed Flask-3.1.3 Pillow-12.3.0 altgraph-0.17.5 blinker-1.9.0 click-8.5.0 itsdangerous-2.2.0 jinja2-3.1.6 markupsafe-3.0.3 mido-1.3.3 packaging-26.3 pefile-2024.8.26 pyinstaller-6.22.3 pyinstaller-hooks-contrib-2026.7 pystray-0.19.5 python-rtmidi-1.5.8 pywin32-ctypes-0.2.3 setuptools-84.0.0 six-1.17.0 werkzeug-3.1.8
Building executable...

Build complete.
Dist directory: C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc\dist
Executable:     C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc\dist\STEAMDECK-MIDI-RECEIVER-2.exe

Example run:
.\dist\STEAMDECK-MIDI-RECEIVER-2.exe --map .\config\windows_midi_map.json --midi-port "DECK_IN" --verbose
```

(The full 40 lines, including the pip download lines elided above, are lines 43-82 of evidence/build-a2.out.txt.)

Last 40 lines, build_installer_v2.ps1 (its own output after the ISCC compile; lines 161-200 of evidence/build-a2.out.txt), abridged only where 14 identical `Compressing: ...config\engines.factory\<name>.json` lines repeat:

```
Parsing [Files] section, line 63
Creating setup files
   Verification successful
   Updating icons (Setup.exe)
   Compressing: ...\dist\STEAMDECK-MIDI-RECEIVER-2.exe
   Compressing: ...\dist\STEAMDECK-MIDI-RECEIVER-2-Tray.exe
   Compressing: ...\assets\windows\receiver.ico
   Compressing: ...\config\windows_midi_map.json
   Compressing: ...\config\windows_receiver_settings.example.json
   Compressing: ...\scripts\windows\start_installed_receiver_v2.ps1
   Compressing: ...\config\presets\default.json
   Compressing: ...\config\macro_library.json
   Compressing: ...\config\engines\README.md
   Compressing: ...\config\engines.factory\audio_opacity.json ... steam_input_layer_tracker.json (14 files)
   Compressing: ...\config\actions.yaml
   Compressing Setup program executable
   Updating version info (Setup.exe)
   Updating manifest (Setup.exe)

Warning: The [Setup] section directive "PrivilegesRequired" is set to "admin" but per-user areas (HKCU) are used by the script. ...

Successful compile (11.141 sec). Resulting Setup program filename is:
C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc\installer-output\STEAMDECK-MIDI-RECEIVER-2-Setup-0.5.0.exe

Installer build complete.
Output directory: C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc\installer-output
Installer EXE:    C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc\installer-output\STEAMDECK-MIDI-RECEIVER-2-Setup-0.5.0.exe
```

After a2: root pid gone, no process under the CLONE, no ISCC.exe, no child of the root (L04-build-a2.txt `LEFTOVER_COUNT 0`).

### The fingerprint

Build-written `windows/build_fingerprint.py` (L05), before restore:

```
"""Build fingerprint metadata for runtime diagnostics."""

APP_VERSION = "0.5.0"
GIT_COMMIT = "2e4292a75f08674fdf5c78358485b27c2d3bd913"
GIT_COMMIT_SHORT = "2e4292a75f08"
BUILD_TIME_UTC = "2026-09-16T09:12:21Z"
```

version 0.5.0, git commit = CANDIDATE, build time 2026-09-16T09:12:21Z. `git -C <CLONE> status --porcelain` before restore: ` M windows/build_fingerprint.py`. `git -C <CLONE> checkout -- windows/build_fingerprint.py` exit 0; porcelain after: **0 lines**; the tracked file reads `"source"` again for the three build fields. `git status --porcelain --ignored` after: `.showready/`, `.venv-build/`, `.venv/`, `build/`, `dist/`, `installer-output/` and five `__pycache__/` dirs. Nothing else. The built artefacts were kept.

## 3. Staging

`C:\Users\Ben\Documents\steamdeck-midi-showready\` did not exist and was created, then `candidate-2e4292a\` (the script refuses an existing one). Copy-Item from dist\ and installer-output\ (sources still present after), then Get-FileHash on the copy compared to the source hash:

| File | Bytes | sha256 | copy == source |
| --- | --- | --- | --- |
| STEAMDECK-MIDI-RECEIVER-2-Setup-0.5.0.exe | 43981989 | 9232d8c4a2673dd1c3ec1bc35c9f87b9bc00c528114d71dec88892065c1565a1 | True |
| STEAMDECK-MIDI-RECEIVER-2.exe | 21003745 | 2fcb2868d847615b5dd8b78732b654c857d48872f7125ab014a51253797f9b1c | True |
| STEAMDECK-MIDI-RECEIVER-2-Tray.exe | 20998625 | 1550c0ce838f43d42b8fd7e707dff4ce61d2e1d6e7ccc339c2e8d43b631f9c96 | True |
| SHA256SUMS.txt | 308 | 5257148507d793f57b84d42faa1f00196b1a03a742905998561c4644f769079d | fetched: docs/sdrc-c1/SHA256SUMS.txt, same sha256 on the Mac |
| BUILD-INFO.txt | 1573 | d9b9daefabe3c8be4c1c82833d1ac18055f88cc82f378d6aa59c788f91115ebc | fetched: docs/sdrc-c1/BUILD-INFO.txt, same sha256 on the Mac |

BUILD-INFO.txt was written in two appends by this link (the second added the ISCC engine version and the build run line; L05b). The final listing above was re-read in L07 just before the guard compare, unchanged. The installer was not copied to the Mac. No process ever ran from dist\ or installer-output\, and the only process that ran from STAGING was the console exe of step 4 (`PROCESSES_RUNNING_FROM_STAGING 0` afterwards).

## 4. Frozen smoke (the BUILT console exe, from STAGING)

### pystray dummy finding (determined BEFORE the UI-on run)

pystray's dummy backend IS in the bundle, by two independent reads:
- PyInstaller's build TOCs: `build\steamdeck-midi-receiver-2\PYZ-00.toc` and `Analysis-00.toc` both list `pystray._dummy` (with _appindicator, _base, _darwin, _gtk, _info, _util, _win32, _xorg). The build log shows why: `Processing standard module hook 'hook-pystray.py' from ...\_pyinstaller_hooks_contrib\stdhooks`, which collects every backend. The spec itself names only `pystray` and `pystray._win32`.
- The archive viewer on the STAGED exe: `.venv-build\Scripts\python.exe -m PyInstaller.utils.cliutils.archive_viewer --list --recursive <STAGING>\STEAMDECK-MIDI-RECEIVER-2.exe` (exit 0, 966 lines) lists `0, 3534103, 231, 'pystray._dummy'`.

And the frozen exe HONOURS `PYSTRAY_BACKEND=dummy` at runtime. The run's stderr shows `Exception in thread tray: ... File "pystray\_base.py", line 212, in run ... File "pystray\_base.py", line 379, in _run  NotImplementedError`. `pystray/_dummy.py` is `from ._base import Icon`, the abstract base whose `_run` raises NotImplementedError, whereas the win32 backend implements `_run`. So the dummy Icon was the one loaded, and the sidecar tray thread ended at once without creating an icon. The bridge kept serving (the thread's exception is contained). The process ran in session 0, so it could not have reached Ben's desktop either way.

### Setup

- Scratch tree `sdwin\sdrc-c1\smoke2\config\` built from `sdwin\fixtures\windows-installed`: all 11 MANIFEST entries hash-verified at the source and again after copy. Active preset `EDM Show.json`. (A first attempt, L06-smoke.txt, stopped in my own script BEFORE any process started: an empty browser list returned $null under StrictMode. It left only the empty-of-processes `smoke\` config copy. Fixed with `@(...)`, rerun into `smoke2\`.)
- Ports checked free first (no UDP endpoint and no TCP connection on either): UDP **46211**, UI **47311**. Never 45123 or 7723.
- Env: `PYSTRAY_BACKEND=dummy`; `BROWSER=C:/Users/Ben/Documents/project-workspaces/steam-deck-midi-rc/.venv/Scripts/python.exe -c pass %s` (the 51b1d5b form, a real interpreter that exits 0); `TMP=TEMP=` LAPTOP WORK.
- argv: `<STAGING>\STEAMDECK-MIDI-RECEIVER-2.exe --listen 127.0.0.1:46211 --map "<smoke2>\config\windows_midi_map.json" --ui-port 47311 --dry-run --no-engines --no-pulse --no-osc-relay --no-browser`. No `--tray`, no `--feedback-port`. `/api/midi/ports` was NOT called.
- Pid tree: root 362072 (onefile bootloader, session 0) -> child 357944 (session 0), which owned `UDP 127.0.0.1:46211` and `TCP 127.0.0.1:47311`. UI answered 1.05 s after start. stderr: `INFO selected MIDI output port: name=DECK_IN index=n/a` (the dry-run stub; no port opened).

### Route table

| Route | Status | Value |
| --- | --- | --- |
| GET /api/version | 200 | `{"build_time_utc":"2026-09-16T09:12:21Z","frozen":true,"git_commit":"2e4292a75f08674fdf5c78358485b27c2d3bd913","version":"0.5.0"}` -> version 0.5.0 True, git_commit = CANDIDATE True, frozen true True |
| GET /api/controller-map | 200 | controls = **23** (True), body sha256 4df22c82... |
| GET / | 200 | 94112 bytes, sha256 fbf5a734c879385fbac18e46d6b35736b203085617e8897a449e265c395f538c = clone windows\static\index.html |
| GET /static/controller/controller_live.js | 200 | 11206 bytes, 5af0ac68...14765 = source |
| GET /static/controller/controller_map.json | 200 | 13191 bytes, 13eded61...4669e = source |
| GET /static/controller/controller_view.css | 200 | 7260 bytes, ec184416...be790 = source |
| GET /static/controller/controller_view.js | 200 | 25021 bytes, 69bb183f...86d46 = source |
| GET /static/controller/steam_deck.svg | 200 | 3622 bytes, 4e3d6817...63e78 = source |
| GET /api/live/snapshot, before input | 200 | pressed [], axes {}, seq 6 (the six startup layer-state CCs: B0 4E 00, B1 4E 00, B0 4F 00, B1 4F 00, B0 4A 7F, B1 4A 00), clients 0, dropped 0 |
| UDP x3 `{"kind":"action","action":"BTN_A|BTN_B|BTN_X","state":"down","seq":1..3}` then GET snapshot | 200 | pressed **["BTN_A","BTN_B","BTN_X"]** (True); midi rows 90 24 7F (BTN_A), 90 26 7F (BTN_B), 90 28 7F (BTN_X), plus BTN_A's layer CCs B0 4E 7F, B1 4E 00 |
| UDP x9 `{"kind":"axis","action":"R_STICK_X_AXIS","value":-32767..32767 step 8192,"seq":4..12}` then GET snapshot | 200 | axes **{"R_STICK_X_AXIS":32767}** (True); nine midi rows BF 74 7F, 5B, 38, 14, 00 then BF 72 14, 38, 5B, 7F |
| UDP x3 up, seq 13..15, then GET snapshot | 200 | pressed [] (True), seq 38, midi rows 20, dropped 0, clients 0 |
| POST /api/shutdown | 202 | `{"stopping":true}` |

All 15 datagrams from one loopback socket. Exe stdout (dry-run MIDI log, evidence/smoke.out.txt) matches the rows, then `MIDI note_off` x3 and `MIDI panic`.

### Stop and proof

| Check | Result |
| --- | --- |
| exit code after POST /api/shutdown (WaitForExit 20 s) | **0** |
| Get-Process 362072 / 357944 | gone / gone |
| listeners on 46211 / 47311 after | **0** (L07). My in-script "port free" test counted ANY TCP row and read ui=False: L07 shows only `TimeWait pid=0` client-side entries from my own HTTP calls, no listener, no owning process |
| `_MEI*` extraction dirs in LAPTOP WORK | 0 before, 0 after (the bootloader cleaned up) |
| browsers (msedge, chrome, firefox, iexplore) before / after the exe | 0 / 0, **equal** |

stderr also shows 9x `ERROR engine_registry.on_axis_event failed ... receiver.py, line 901 ... AttributeError: 'NoneType' object has no attribute 'on_axis_event'`, one per axis datagram. The axis still mapped to MIDI. See F2: it is PRE-EXISTING and only reachable with `--no-engines`.

## 5. Process and port rows (L07, read-only, 09:16:28Z, then the guard compare)

| Row | Value |
| --- | --- |
| recorded pids (owned-pids.txt: builds a1/a2 roots, 5 version/listing pythons, archive viewer, smoke root + child) | 353404, 354408, 357944, 358440, 360592, 360664, 362072, 362392, 363488, 363940: **all alive=False**. (Clock-probe launcher pids 360456 and 361828 were proved gone in L02.) |
| python.exe / pythonw.exe on the laptop | **PYTHON_TOTAL 0** |
| processes running from STAGING | 0 |
| PROCESS-CLASS ORDER, protected tested first | (i) PROTECTED **99**, none recorded; (ii) RECORDED alive **0**; (iii) LANE_PATH_UNRECORDED **0**; (iv) NOT_LANE 173. Nothing was stopped: the only stop this link issued was POST /api/shutdown to its own exe |
| browsers, read-only Win32_Process (chrome.exe, msedge.exe, firefox.exe) with SessionId + CreationDate | **BROWSER_COUNT 0 in any session**, so none in session 1 created after link start 09:09:38Z, and no NEEDS-MASTER browser line. (Session-1 `msedgewebview2.exe` processes exist, created 2026-08-16 and 2026-09-16T03:44Z, both before this link; not a browser class in the rule, recorded in L01 only) |
| protected, untouched | tray 5268 and 23640 (session 1, created 2026-08-16T06:29:37Z), loopMIDI 16020 (created 06:29:31Z); UDP 45123 pid 23640; TCP 7723 pid 23640. Same as L01 |
| clone | HEAD 2e4292a, porcelain 0 |
| guard compare | GREEN, exit 0 |

## Findings

- **F1 (product build script, fresh-clone build fails).** `scripts/windows/build_exe_v2.ps1:81` `Set-Content -Path $versionInfoPath` writes `build\windows-file-version.txt` before anything creates `build\`, so on a clone with no `build\` the documented release command (docs/windows-release-checklist.md "Build") exits 1. v0.4.9's orphan checkout already had `build\` from earlier PyInstaller runs, which hid it. Taken here: option (a), create the empty ignored `build\` and rerun the UNCHANGED script. NEEDS-MASTER line written at the bottom of the LANE LOG at 03:12. The fix (e.g. `New-Item -ItemType Directory -Force (Split-Path $versionInfoPath)` before :81) is a product-script change for a later link, NOT made here. It does not change what the build produces.
- **F2 (pre-existing, --no-engines only).** `windows/receiver.py:900-901` calls `self._engine_registry.on_axis_event` inside try/except. With `--no-engines` the registry is None, so every axis datagram logs an ERROR traceback. The MIDI mapping is unaffected: the axis rows were emitted. PRE-EXISTING: `git show 'v0.4.9^{commit}':windows/receiver.py` has the identical block at 869-874; `git log -L` puts its origin at 2b55e2e (v0.4.4). The installed tray runs engines ON, so the show path does not reach it. Log noise, not a regression.
- **F3 (instrument, mine).** My in-script port-free test counts TimeWait rows. The listener proof in L07 is the one to read.

## For the next links

- C2 (rollback pack): `C:\Users\Ben\Documents\steamdeck-midi-showready\` now exists (created by C1) with only `candidate-2e4292a\` in it. ROLLBACK does not exist yet.
- CG and bar 4: the staged candidate is `C:\Users\Ben\Documents\steamdeck-midi-showready\candidate-2e4292a\STEAMDECK-MIDI-RECEIVER-2-Setup-0.5.0.exe`, sha256 9232d8c4a2673dd1c3ec1bc35c9f87b9bc00c528114d71dec88892065c1565a1, 43981989 bytes. Ben runs it; no link does.
- The clone now holds ignored `.venv-build\`, `build\`, `dist\`, `installer-output\`. The clone porcelain is 0. A new link that needs the clone clean of ignored outputs should know they are there.
- The Windows no-op BROWSER in scripts/showready/README.md "Isolated clone and suite" is still the broken `cmd.exe /c rem %s` form. This link used the 51b1d5b form. Carry-forward, not fixed (docs-only link).
- The sdwin gate's d136787-vs-e66ff44 comparison (bar 1 against the tag, clean or QUALIFIED) is not C1's to carry. The evidence-report link must quote it verbatim.
- UNVERIFIED-BY-EXECUTION here: the Tray exe was staged but not started (the item smokes the console exe only), and the installer was not run (by rule). No Mac suite was run: this link changed no code.
- The laptop-side .ps1 bodies this link ran are not committed (docs only). Their full outputs are evidence/L00..L08.
