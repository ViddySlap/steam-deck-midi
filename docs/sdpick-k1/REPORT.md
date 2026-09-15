GUARD GREEN x6: first act 10:04:22 `win_guard.ps1 -Mode compare -Baseline sdwin\sdlive-gate\before.json` exit 0 and LAST act 10:37:04 same compare exit 0, both `GUARD GREEN: compare; protected state observed; pythonProcesses=0`; every guard JSON K1 downloaded has sha256 50aa227c, byte-identical to EG's 02:04 baseline.

# sdpick K1 - laptop debt from sdlive EG, paid

Link K1 of run sdpick-q001, lane steamdeck, claude-rc on the Mac. Branch `chain/steamdeck-20260914`, entry HEAD = origin =
`d882f97b6e9f11226ba26ea9ceb87d4ae7adebec` (EG's final commit; product bytes identical to 51b1d5b per EG line 8).
No product code, tests or pinned scripts changed. Laptop scripts, logs and evidence are under this directory:
`scripts/` (every .ps1/.sh/.py K1 ran), `logs/` (one file per rail step, CR stripped), `laptop-evidence/` (raw bytes as
downloaded; Windows CRLF kept so each file matches the sha256 in `logs/I1-downloads.txt`).

## Guard results (all through `scripts/showready/win_rail.sh run sdpick-k1 scripts/showready/win_guard.ps1 ...`)

| Log | When | Mode / baseline -> out | Exit | Line |
| --- | --- | --- | --- | --- |
| S1a-guard-compare-vs-EG | 10:04:18-22 (FIRST laptop act after the reachability probe) | compare `sdwin\sdlive-gate\before.json` -> `sdwin\sdpick-k1\guard-1a-compare-vs-eg.json` | 0 | GUARD GREEN: compare |
| S1e-guard-compare-vs-EG | 10:21:40-42 (after step 1 d) | same baseline -> `guard-1e-compare-vs-eg.json` | 0 | GUARD GREEN: compare |
| S2-0-guard-snapshot | 10:22:26-28 (before step 2) | snapshot -> `sdwin\sdpick-k1\before.json` | 0 | GUARD GREEN: snapshot |
| G2-guard-compare-after-fg | 10:26:31-34 (after f and g) | compare K1 `before.json` -> `guard-after-fg.json` | 0 | GUARD GREEN: compare |
| J5-guard-compare-final-vs-k1 | 10:37:00-02 | compare K1 `before.json` -> `after-final-vs-k1.json` | 0 | GUARD GREEN: compare |
| J6-guard-compare-LAST-vs-EG | 10:37:02-04 (LAST laptop act) | compare EG `before.json` -> `after-final-vs-eg.json` | 0 | GUARD GREEN: compare |

EG's baseline path was not written in its report; K1 used the README's pattern `sdwin\sdlive-gate\before.json`, and the
10:35 read-only listing (`logs/I0-list-eg-laptop.txt`) shows that file written at 02:04:11, which is EG's L0 snapshot time.
sha256 of EG's `before.json`, K1's `before.json`, `guard-1a-...json`, `guard-1e-...json` and `guard-after-fg.json`:
all `50aa227cd7d864835f45232930cbb00f8b8c6f36b6d8d162c027d2cf56ad0ad5` (`logs/I1-downloads.txt`). The two final JSONs
were not downloaded (downloading after the last compare would break the last-act rule). The guard covers UDP 45123 and
TCP 7723 owners, tray and loopMIDI pids and start times, 44 installed files, installed user-config hashes, the orphan
checkout HEAD and status (read with `git --no-optional-locks`), and python/pythonw under the clone or sdwin.

## Step 0 - reachability (`logs/S0-reachability.txt`)

`ssh -i ~/.ssh/claude-mac-win-key -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=20 ben@viddyslaptop.local hostname`
- 10:03:45 -> `ViddySlaptop`, exit 0, under 1 s.
- 10:08:14 (second probe while step 1b looked stuck) -> `ViddySlaptop`, exit 0.
No retry loop was needed; no NEEDS-MASTER line for ssh. Every later rail call in `logs/` connected (no RAIL_EXIT 255 except the one K1 caused by ending its own ssh client at 10:20:23).

## Step 1 - safety first

### (a) guard compare against EG: GREEN (table above, S1a).

### An incident of K1's own, before (b): K1's first inventory script hung, and K1 stopped it

- 10:04:55 first attempt: `inventory.ps1` exit 1 at once (`ManagementDateTimeConverter.ToDateTime` on a CIM DateTime). Nothing started beyond that PowerShell, which exited.
- 10:05:06 second attempt (log `S1b-inventory-before.txt`) never returned. Read-only diagnosis:
  `quick.ps1` (Get-Process only, 10:08:30) showed the script's PowerShell pid 315296 (session 0, started 10:05:07) and no python, pythonw or browser;
  `diag.ps1` (10:20:08) showed `winmgmt` RUNNING and a filtered `Get-CimInstance Win32_Process` answering in 617 ms, while pid 315296 had used 770 CPU seconds. So WMI was healthy and the spin was in K1's own script: `ConvertTo-Json -Depth 8` over `Get-Content` lines, which carry PSPath/PSDrive/PSProvider note properties (cause inferred from the fix below, not traced).
- 10:20:23 K1 ended its Mac ssh client (rail exit 255). 10:20:27 `pidcheck.ps1 -Ids 315296`: still ALIVE (sshd did not end it).
- 10:20:47 `stop_own.ps1 -TargetPid 315296 -Created 2026-09-15T10:05:07 -CmdNeedle sdwin/sdpick-k1/inventory.ps1`: identity read by CIM
  `pid=315296 ppid=319108 name=powershell.exe si=0 created=2026-09-15T10:05:07 cmd=powershell -NoProfile -ExecutionPolicy Bypass -File "C:/Users/Ben/AppData/Local/Temp/sdwin/sdpick-k1/inventory.ps1" "-Label" "before"`, no children, `STOPPED 315296`, `PID 315296 gone=True`, exit 0.
  This is a process K1 itself started (its launch is in K1's log), not a lane process from the classification below.
- Fix (K1 scratch script only): records cast to `[string]`, depth 4. 10:21:01-03 the fixed inventory completed in 2 s. Parent 319108 is absent from that inventory's full process list.

### (b) and (c) session-aware browser listing and process inventory, BEFORE (10:21:03, `logs/S1c-classified-before.txt`, raw `laptop-evidence/inventory-before.json`)

Command: `win_rail.sh run sdpick-k1 scripts/inventory.ps1 -Label before2` (Win32_Process: pid, ppid, name, SessionId,
CreationDate, ExecutablePath, CommandLine for chrome.exe, msedge.exe, firefox.exe, python.exe, pythonw.exe, powershell.exe,
pwsh.exe, node.exe; plus pid/ppid/name/session/created of all 270 processes and the text of every `owned-tree-*.txt` and
`python-pids.txt` under sdwin), classified on the Mac by `scripts/classify.py`.

Browsers (chrome.exe, msedge.exe, firefox.exe): **0 in session 1, 0 in session 0, 0 total.** No NEEDS-MASTER browser line.

| pid | name | session | ppid | created | class | executable | command line |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 57056 | node.exe | 1 | 44052 | 2026-09-02T23:38:13 | NOT LANE (session 1, Program Files) | C:\Program Files\Adobe\Adobe Creative Cloud Experience\libs\node.exe | Adobe Creative Cloud Experience js\main.js |
| 320124 | powershell.exe | 0 | 320260 | 2026-09-15T10:21:02 | this inventory itself | C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe | -File "C:/Users/Ben/AppData/Local/Temp/sdwin/sdpick-k1/inventory.ps1" "-Label" "before2" |

No python.exe, pythonw.exe, pwsh.exe or msedge.exe existed. COUNT RECORDED LANE PID 0; COUNT LANE-STARTED BY PATH, UNRECORDED 0.

Classification rule as implemented (`scripts/classify.py`, MASTER 04:13):
- NOT LANE first: session other than 0, or executable / command line starting with the orphan root `C:\Users\Ben\Documents\project-workspaces\steam-deck-midi\` or `C:\Program Files\`.
- RECORDED LANE PID: the pid or an ancestor (ancestor walk stops at a parent created after its child, i.e. a reused pid) is in EG's records: 5 laptop files (`owned-tree-clean/ctl10/pins/sensitivity.txt`, `python-pids.txt`) plus the 18 pids in `docs/sdlive-gate/evidence/laptop/L22-ab.txt`, 218 distinct pids in all (`recorded_pids 218` in the classifier output). A record with a start time must match the live CreationDate to the second; a pid-only record counts only if the live process was created 2026-09-15T00:00-04:10.
- LANE-STARTED BY PATH, UNRECORDED: executable, or command line with at most one leading double quote removed, starts case-insensitively with `...\steam-deck-midi-rc\` or `C:\Users\Ben\AppData\Local\Temp\sdwin\` (full prefix with separator, never substring).
- Control (`logs/S1c0-classifier-control.txt`, synthetic `scripts/classify-control-inventory.json`): 9 of 9 rows as intended, including orphan-prefix python -> NOT LANE, clone python -> PATH, `-File ...sdwin...` in a system powershell -> NOT LANE (not a prefix), quoted sdwin exe -> PATH, session-1 clone python -> NOT LANE, recorded pid with matching start -> RECORDED, recorded pid number with a different start -> NOT LANE, child of a recorded pid -> RECORDED, Program Files exe -> NOT LANE.

### (d) stop RECORDED LANE pids: nothing to stop

0 recorded lane pids alive, 0 unrecorded lane-path processes, so no NEEDS-MASTER line and no stop. The one EG process last
seen alive, msedge.exe 298364 (`owned-tree-ctl10.txt`: `299124 298364 msedge.exe parent=296196 start=09/15/2026 03:50:46 gone=False`,
EG L21 `Owned descendant PIDs alive: 1` at 03:55), is absent from the 270-process list at 10:21:03 and from the 272-process
list at 10:36:33; so are its recorded parent 296196 and root 299124. When and how it ended is UNVERIFIED (Windows does not
log process exit by default). EG's `cv_debug.log` in `sdwin\sdlive-gate` (Edge's headless log; cwd was that directory) has
its last entry at `0915/095047` UTC = 03:50:47 local, one second after 298364 started, and nothing later.

### (e) guard compare again: GREEN (S1e).

## Step 2 - the owed measurements (guard: snapshot S2-0 before, compares G2 and J5/J6 after)

### Clone to branch HEAD (`logs/S2-2-pull-bundle.txt`)

Bundle directly, not a GitHub fetch: EG's fetch reset and timed out, and a hung remote git would sit out of the rail's reach.
`git bundle create /tmp/sdpick-k1/sdpick.bundle 51b1d5b..d882f97 chain/steamdeck-20260914` (sha256 f157e51b...), `win_rail.sh put`, then
`scripts/pull_bundle.ps1 -Expected d882f97b...` (EG's script, bundle name changed): bundle verify okay, FETCH_HEAD d882f97b...,
`merge --ff-only`, `PINNED_HEAD d882f97b6e9f11226ba26ea9ceb87d4ae7adebec`, `PORCELAIN_LINES 0`, exit 0.

### (f) BAR 2 re-proof, clone at d882f97

| Run | Command (via `win_rail.sh run sdpick-k1`) | Result | Exit | PIDs |
| --- | --- | --- | --- | --- |
| 300x HEAD | `scripts/flake_gate.ps1 -Which head` -> `python -B docs\sdlive-e0\scripts\repeat.py <clone> 300 test_malformed_json_and_unsupported_method_are_json green flake-head.json` | `RUNS 300 RUNS_WITH_ERROR 0`, kinds {} | 0 (green observed) | 306128, 315592 gone=True |
| 300x BASE 14aa218 (control) | `-Which base`: `git archive 14aa2182...` extracted to `sdwin\sdpick-k1\e0-base`, same repeat.py, `red` | `RUNS 300 RUNS_WITH_ERROR 69`; 73 x WinError 10053, 1 x WinError 10054; per subtest BOGUS 22, POST `{` 20, POST `null` 21, PATCH 11 | 0 (red observed) | 288644, 320212 gone=True |
| Windows suite 1 | `scripts/suite.ps1 -Label k1-suite1` -> `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"` | `Ran 902 tests in 51.465s`, `OK (skipped=5)`, PYTHON_PROCESSES_AFTER 0 | 0 | 314856, 318168 gone=True |
| Windows suite 2 (consecutive) | `-Label k1-suite2` | `Ran 902 tests in 55.789s`, `OK (skipped=5)`, PYTHON_PROCESSES_AFTER 0 | 0 | 314528, 291772 gone=True |

Environment for all four: PYSTRAY_BACKEND=dummy, BROWSER=`<clone venv python, forward slashes> -c pass %s` (51b1d5b form), TEMP/TMP = `sdwin\sdpick-k1`.
Only change to EG's `flake_gate.ps1`: work dir, and `$args` renamed `$argline` (PowerShell automatic variable). `suite.ps1` is EG's, unchanged.
E0's earlier counts for comparison: BASE 55/300 and 66/300, HEAD 0/300, suites 868 OK; the suite now has 902 tests (the Mac count at d882f97 per EG).
Raw: `laptop-evidence/k1/flake-head.json`, `flake-base.json`, `k1-suite1.stderr.log`, `k1-suite2.stderr.log`.

### (g) browser-fix revert control (`logs/G1-browserfix-red.txt`)

`scripts/browserfix_red.ps1` (EG's, work dir changed): `git archive HEAD scripts/showready tests` into two scratch trees,
the `reverted` one with timing_ab.py's `NOOP_BROWSER` replaced by `'C:/Windows/System32/cmd.exe /c rem %s'` (needle matched once).
- ARM reverted: EXIT 1, `The syntax of the command is incorrect.`, `AssertionError: False is not True`, `FAILED (failures=1)`; pid 314812 gone=True.
- ARM head: EXIT 0, `test_bridge_noop_browser_command_really_succeeds ... ok`, `OK`; pid 303900 gone=True.
The test calls `webbrowser.GenericBrowser(...).open` directly (`tests/test_showready_timing.py:205`), so no default-browser fallback can run.

### (h) Windows bar 1 independent re-check at d882f97 (`logs/H1-ab-windows-installed.txt`, 10:26:43-10:34:49)

`scripts/ab.ps1` (EG's, work dir changed, plus a tracked `deck_script.py --fixtures sdwin\fixtures --out sdwin\sdpick-k1\deck-script.json`:
exit 0, script_sha256 f6611e7e (EG's laptop script value), 732 steps, 47,039 packets, pid 320396 gone=True). Three concurrent
`ab_run.py --candidate d882f97b... --preset sdwin\fixtures\windows-installed\presets\<preset> --script ... --fixtures ... --scratch ... --out ...`.

| Preset | ab_run exit | Instrument | `bar1_verify.py d882f97b... <result>` (Mac, raw rows) |
| --- | --- | --- | --- |
| EDM Show.json | 0 | passed true, 56/56 mappings exercised, MIDI A 1531 / B1 1531 | commits ok, 47,039 packets both arms, pid_gone both, MIDI 1531 (mapped 1525) identical to A, independent_passed true |
| PTZ.json | 0 | passed true, 52/52, 1395 / 1395 | 1395 (mapped 1389) identical, independent_passed true |
| default.json | 0 | passed true, 56/56, 1531 / 1531 | 1531 (mapped 1525) identical, independent_passed true |

`bar1_verify.py` exit 0 (`logs/H2-bar1-verify-k1.jsonl`). All 3 launcher pids and 15 descendant python pids gone=True.
Ports and browser: `ab_run.py:140-145` binds port 0 and refuses 45123/7723; arms run `--no-ui` (`ab_run.py:268`), and
`windows/win_recv.py:402` skips the whole UI block, including `_open_browser_delayed` at :425, under `--no-ui`.
`windows/win_recv.py` has no `--no-browser` flag. The driver ran with the exit-0 BROWSER above. Note for a later chain,
not a defect today: `ab_run.py:274` hands its arms `BROWSER='true'`, which is not a command on Windows; it is inert only
because of `--no-ui`.

### (i) downloads (`logs/I1-downloads.txt`, 10:35:24-45, all exit 0) into `laptop-evidence/`

From `sdwin\sdlive-gate` (EG, marked not downloaded or truncated): `edge-ctl10.json.gz` (17,883,726 bytes, sha256 b7bb500e; EG's
truncated Mac copy was 3d42a1c6), `ab-win-edm/ptz/default.json.gz` + stdout logs, the four `owned-tree-*.txt`, `python-pids.txt`,
`before.json`, `cv_debug.log`, `client-command.json`. Other EG results (edge/python sensitivity and clean) were already
downloaded: laptop sha256 equal to `docs/sdlive-gate/evidence/raw-results-sha256.txt` (listing `logs/I0-list-eg-laptop.txt`).
From `sdwin\sdpick-k1`: K1's flake JSON and logs, suite stderr, browserfix logs, three A/B results, guard JSONs.

EG's three Windows bar 1 results, independently: `bar1_verify.py 51b1d5b1... <3 results>` exit 0 (`logs/I2-bar1-verify-eg.jsonl`):
same counts as K1's row for row, independent_passed true for all three.

EG's every-10th Windows control, per statistic (`timing_table.py edge-ctl10.json.gz`, recomputed from raw samples,
`recomputed_matches_instrument true`, `logs/I3-edge-ctl10-table.json`): candidate cc4c769, Edge, R=3, all 9 arms VALID, 9,638 timed MIDI each, byte_identical true.

| Pooled (ms, n=28,914) | p50 | p95 | p99 | max |
| --- | --- | --- | --- | --- |
| CLOSED | 7.981 | 353.122 | 1637.499 | 2023.368 |
| OPEN | 11.008 | 313.767 | 1643.640 | 2033.559 |
| CLOSED-B | 7.278 | 231.610 | 1656.255 | 2041.077 |
| NOISE FLOOR abs(CLOSED - CLOSED-B) | 0.703 | 121.511 | 18.756 | - |
| abs(OPEN - CLOSED) | 3.026 | 39.355 | 6.141 | - |
| within floor + 1.0 ms | **False** | True | True | - |

Per repeat (p50/p95/p99 within): r1 N N Y, r2 Y Y N, r3 Y Y Y. `rule_passed false` came from p50 only. EG's declared
expectation (p95 and p99 FAIL) was NOT met; the control detected the planted delay at p50 and was hidden by the Windows
noise floor at p95/p99. This is diagnostic; Windows bar 3 stays DIAGNOSTIC, as EG and MASTER 04:00 already said.

### (j) FINAL (`logs/J1`-`J6`)

- 10:36:33 inventory `-Label final` (`logs/J2-classified-final.txt`): browsers 0 (session 1: 0, session 0: 0); rows: Adobe node 57056 (session 1, NOT LANE) and the inventory's own powershell 310288. RECORDED LANE 0, UNRECORDED lane-path 0, python/pythonw 0.
- `logs/J3-k1-pids-absent-final.txt`: all 36 pids K1 recorded (its own hung inventory, probes, flake, suites, browserfix, deck script, 18 A/B pids, and EG's survivor 298364) absent: CHECKED 36 PRESENT 0.
- `logs/J4-processes-created-since-k1-start.txt`: 9 processes created since 10:03 in the 272-process list: the inventory's own sshd x2, cmd, conhost, powershell; svchost 299216 and WmiPrvSE 317640 (system services); ADPClientService 313408 and its conhost in session 1 (Adobe). None started by K1 besides the inventory itself.
- Then J5 and J6 guard compares GREEN; J6 was the last laptop act.

## Mac side

Scratch `/tmp/sdpick-k1/` only. Step chains ran in a private tmux server `-L sdpick` (sessions chainf and chainh ended on their
own; `tmux -L sdpick ls` -> `no server running`). No Mac process left from this link besides this session.

## For Ben (plain words)

- Nothing was left running on your show laptop from last night's work, and nothing was found in your desktop session: no browser windows at all, no leftover test programs. The one test browser that was still alive at 03:55 is gone.
- Your installed v0.4.9 tray, its files and settings, loopMIDI, the ports it owns and the old checkout are exactly as they were at 02:04 last night (six checks, all identical).
- The Windows fix for the flaky test holds: 0 errors in 300 runs with the fix, 69 in 300 without it. The full test suite passed twice in a row on the laptop (902 tests).
- Your Windows presets (EDM Show, PTZ, default) still produce byte-for-byte the same MIDI as v0.4.9 at the current build, checked again from the raw data.
- One slip of mine: my first process listing script hung on the laptop for about 15 minutes (it spun on formatting its output). It used CPU in the background session but touched nothing of yours; I stopped it by its exact process id and fixed the script.
- The laptop's ssh answered normally all morning; the 03:55 stall did not recur during this link.

## For the next link (KJ)

- Clone `C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc` is at d882f97, porcelain 0. K1's commit is docs only; a later laptop link can bundle d882f97..<new HEAD>.
- LAPTOP WORK `sdwin\sdpick-k1\` holds K1's results, the BASE archive `e0-base`, A/B scratch trees and the bundle. No process runs there.
- Bar 2 at d882f97 is re-proven on Windows (f); bar 1 Windows is independently re-checked for K1's run and EG's run (h, i).
- Still OWED elsewhere, not in K1's item: bar 3 (sdbar3, M_bridge), the geometry instrument defects (EG FOR BEN 4), Ben's bars 4 and 5.
- Log caption gotcha: zsh `echo` mangles `\U`/`\b` in Windows paths in log captions; K1's `step.sh` uses `print -r` (the first S1a caption was re-typed by hand, noted inside it).
