BASE OF LAP 6eff30e6211543e8be1d6159e41467086730ddb7 (from docs/sdbar3-b1/REPORT.md line 1). Candidate measured: HEAD cdf0d403f9133d92306237516c408e848845c79c.

# sdbar3 gate: the fresh qualifying M_bridge measurement (Mac + Chromium)

Executor: claude-rc claude-opus-5 on the Mac, unsandboxed. Branch chain/steamdeck-20260914. Scratch /tmp/sdbar3-gate/.
This link commits evidence only (docs/sdbar3-gate/). No instrument edit.

**M_bridge VERDICT: PASS.** Mac + real Chromium, R=5 interleaved, qualified, sensitivity-proven on M_bridge: |OPEN - CLOSED| p50/p95/p99 = 0.017 / 0.004 / 0.009 ms against floor + 1.0 = 1.018 / 1.064 / 1.073 ms; bytes identical; 15/15 arms VALID with 9,638 every-message timed MIDI each; foreign_lines 0 and pgrep empty before and after every arm; `bar3_counts` true, exit 0.

The sdlive locked-rule RED (M_total p99 2.818 ms > 1.021 ms, candidate 5f98123) STANDS and is not re-scored (MASTER 04:00). This run's M_total is reported beside as required (section 4); it is a new measurement of a different candidate, not a re-score.

No deviation found in step 1 (section 1). Pre-registration written before any gate M_bridge data: /tmp/sdbar3-gate/PREREG.txt (11:14:16), quoted in section 1.

## 0. Suite, node checks, pins (at HEAD cdf0d40)

| Command | Result |
| --- | --- |
| `TMPDIR=/tmp/sdbar3-gate/suite PYSTRAY_BACKEND=dummy BROWSER=/usr/bin/true .venv/bin/python -B -m unittest discover -s tests -p 'test_*.py'` | exit 0, `Ran 910 tests in 14.969s`, `OK (skipped=2)` |
| `node tests/ui_controller_check.cjs` | exit 0, `UI controller behavior: PASS (23 arrows, ...)` |
| `node tests/ui_controller_macro_check.cjs` | exit 0, `Controller macro parity: 48 disk writes match page Save; 72 incompatible writes refused without byte changes` |
| `node tests/ui_reload_check.cjs` | exit 0, `UI reload behavior: PASS` |
| `node tests/ui_sections_check.cjs` | exit 0, `UI section behavior: PASS` |
| `node tests/ui_controller_geometry.cjs` (no args) | exit 2, usage. NOT RUN as a measurement: needs a live URL; its wrapper refuses non-/tmp/sdfix scratch. PRE-EXISTING, owned by sdpolish P1 (lane log MASTER 11:07). No geometry or UI file changed in this lap. |
| `shasum -a 256 -c scripts/showready/SHA256SUMS` | exit 0, 15 OK |
| `shasum -a 256 scripts/showready/timing_ab.py` | **b9b7994a9f599d3eb8960379c7b2e09f4d4164daf743b4d852bcfa2f7d2c7c78** (the instrument run; both results record the same value in `instrument_sha256`) |
| `shasum -a 256 scripts/showready/timing_browser.cjs scripts/showready/capture_runner.py` | 23f89a13... / c254085b... (both OK in SHA256SUMS) |

## 1. Code read (file:line at HEAD cdf0d40)

| Check | Where | Finding |
| --- | --- | --- |
| t1_pre immediately BEFORE sendto | `scripts/showready/timing_ab.py:366-367` | `t1_pre = time.perf_counter_ns()` then `written = sender.sendto(payload, (host, port))`; nothing between them. |
| t1_post immediately after sendto returns | `timing_ab.py:368` | `t1_post = time.perf_counter_ns()` on the next line; the length check (:370) is after it. |
| both stamps for EVERY packet | `timing_ab.py:345-369` | inside `for index, row in enumerate(self.script['packets'])`, unconditional (not under `if event:`); stored at :369. Measured: every arm of both runs has 20,513 / 20,513 packets with t1_pre and with t1_post (gate_table `packets_sent_with_t1_pre/_post`). |
| every timed MIDI message joined | `timing_ab.py:321-326` (enrich), `:85-103` (bridge_join), `:386` | every `record == 'midi'` with step != -1 is appended to `timed` with `cause_packet` = packet index of (step, logical_ns); `bridge_join` raises on a missing stamp, unknown packet, or t3 < t1_pre (never skips). |
| join key is the datagram the bridge was handling | `scripts/showready/capture_runner.py:191` (context set in recvfrom, BEFORE the bridge handles the payload), `:52-53` (t3 `perf_counter_ns` in Recorder.send, same PID), `windows/receiver.py:1054-1069` (single-threaded recvfrom / handle_datagram / advance_fades / check_timeouts), `capture_runner.py:155` (script clock = 1000 + logical_ns, so a timeout wakeup does not advance time) | Consistent with B1's JOIN ASSUMPTION: an output released by a later heartbeat is timed from that heartbeat's t1_pre, so the scheduled hold/fade duration (rig pacing) sits outside M_bridge and inside M_total. Per arm: 9,142 messages caused by a first packet, 496 by a later packet. |
| M_bridge = t3 - t1_pre BINDS | `timing_ab.py:101-102` (`m_bridge_ms`), `:674-679` (verdict on `pooled['m_bridge_ms']`, `require_floor_resolution=False`), `:819` (`result['passed'] = m_bridge_rule_passed` under `--rule m_bridge`) | binds. Independently re-derived in docs/sdbar3-gate/gate_table.py from `t1_pre_ns[cause_packet]` and `t3_ns`: 0 mismatches over 144,570 messages (clean) and 86,742 (sensitivity). |
| t3 - t1_post DIAGNOSTIC only | `timing_ab.py:102` (`m_post_ms`), `:685` (`diagnostic_m_post_rule`) | never feeds `passed`, `bar3_counts` or the exit code. |
| floor, +1.0 ms, p50 AND p95 AND p99 | `timing_ab.py:25` (`BAR3_TOLERANCE_MS = 1.0`), `:27` (STATISTICS p50/p95/p99), `:55-57`, `:65` | floor = abs(CLOSED - CLOSED-B), delta = abs(OPEN - CLOSED), within = delta <= floor + 1.0 for each, `all(within)` required (:65). Absolute delta is at least as strict as the declared signed OPEN minus CLOSED. |
| R | `timing_ab.py:134-144` | qualification needs repeats >= 5 clean, >= 3 sensitivity, speed 1, an external client, all arms load-verified. |
| power floor on the every-message set | `timing_ab.py:74-77`, `:140-142`, `:628-629`, `:677` | every-message >= 1000 required per arm for qualification, arm pass and `valid_arms`. |
| INVALID voiding | `timing_ab.py:65` (`valid_arms` in `passed`), `:813-814` (any unaccepted or failed arm raises: no summary, no verdict), `:880-882` (m_bridge sensitivity not RED, or no verdict -> exit 3) | an invalid arm cannot produce a pass. |
| foreign_lines per MASTER definition | `timing_ab.py:185-204` (`foreign_lines`), `:207-228` (`foreign_load_check`), `:803` (used under `--rule m_bridge`) | same definition as docs/sdlive-gate/scripts/foreign_load.py (engine tests path or run-all.sh, zsh/bash/sh/node, codex exec excluded). |
| sensitivity receipt must be an M_bridge RED | `timing_ab.py:146-158` | `--sensitivity-result` accepted only if `rule == 'm_bridge'`, `m_bridge_sensitivity_timing_red`, qualified, same host, candidate, preset, client, clock, instrument digests and script. |

M_total unchanged: `git diff 5f98123 HEAD -- scripts/showready/timing_ab.py` (5f98123 digest verified 93e4d2b1184474008651242cb065b1e912dcbac7f0481204d0a08c47546a7876, equal to the sdlive gate's). capture_runner.py and windows/ have no commits since 5f98123 (`git log 5f98123..HEAD -- scripts/showready/capture_runner.py windows/` empty). Every hunk:

| Hunk | What | Effect on M_total |
| --- | --- | --- |
| `@@ -26,6 +26,10 @@` | RULES, M_BRIDGE_INVALID, FOREIGN_TESTS constants | none |
| `@@ -46,16 +50,19 @@` | `verdict(..., require_floor_resolution=True)`; `passed` uses `resolved` | locked callers use the default True: identical |
| `@@ -64,6 +71,38 @@` | new `every_message_floor`, `m_total_ms(t3, t0) = (t3 - t0) / 1e6`, `bridge_join` | `m_total_ms` is the same expression as before |
| `@@ -98,13 +137,20 @@` | `measurement_qualified` adds the every-message floor under m_bridge; `sensitivity_matches(..., rule)` | locked path identical |
| `@@ -136,6 +182,52 @@` | new `foreign_lines`, `foreign_load_check` | none |
| `@@ -180,6 +272,13 @@` | CaptureTiming init: packet_index, first_packets, t1 arrays, `timed` | none to the computation |
| `@@ -217,8 +316,14 @@` | `latency_ms = m_total_ms(row['perf_counter_ns'], sent)` (was the inline expression); appends to `timed` after the sample | same value |
| `@@ -258,7 +363,11 @@` | sender: `sent_at` still taken first and stored for the first packet (`self.sent`), then t1_pre / sendto / t1_post | t0 is the same stamp. The measured SYSTEM gained one `perf_counter_ns` call between t0 and sendto and one after it, on every arm alike (B1 measured t1_post - t1_pre min about 2.4 us). |
| `@@ -274,10 +383,13 @@` | `bridge_join` after replay; extra result fields | post-replay, none |
| `@@ -511,10 +623,80 @@` | run_arm every-message floor gate under m_bridge; `open_flags`, `summarize_bridge`, `beside` | none |
| `@@ -547,8 +729,7 @@` | `summarize` uses `open_flags` (same two expressions moved) | identical |
| `@@ -572,7 +753,7 @@` | result gains `rule` | none |
| `@@ -619,25 +800,32 @@` | load check choice by rule; `m_bridge` summary; `passed` by rule; `m_bridge_sensitivity_timing_red`; `sensitivity_matches(..., args.rule)` | locked summary unchanged |
| `@@ -645,7 +833,7 @@`, `@@ -669,6 +857,8 @@`, `@@ -686,8 +876,17 @@` | `--rule` flag, BESIDE line, exit 3 | none |

Cross-check of the unchanged M_total: B1's rescore of sdlive mac-clean through the new code, 144,660 messages, 0 mismatches, 1 ns plant RED (docs/sdbar3-b1/REPORT.md section 3), not re-run here. In both gate runs the independent recompute of the locked pooled statistics from raw `latency_ms` equals the instrument's `summary.pooled_ms` (`locked_summary_pooled_matches true`).

Points B1 left for the master, recorded here (no MASTER line answered them before the run; none is a deviation from the declared rule, which is the authority):
1. The locked verdict's `floor_can_resolve_2ms` clause is not required under m_bridge (`timing_ab.py:674-675`). The declared rule has no such clause; resolution is proven by the sensitivity run. Reported anyway: True for M_bridge in both runs (floors under 0.08 ms).
2. foreign_lines enforced inside the instrument only under `--rule m_bridge`. Both gate runs used `--rule m_bridge`, and the external sampler covered them too.
3. JOIN ASSUMPTION (heartbeat-released outputs timed from the heartbeat). Confirmed by reading (row above). It is the declared metric's meaning, t3 minus the send of the datagram that produced the output.

Not passed by the pinned instrument, stated rather than assumed: `--dry-run` and `--no-browser` (receiver.py has neither flag; `grep -n "no-browser\|dry-run" windows/receiver.py` empty). MIDI goes to the capture Recorder (`capture_runner.py:40-53`, port name SDWIN_RECORDER_NO_REAL_PORT; a real port open is fatal). PYSTRAY_BACKEND=dummy, BROWSER=/usr/bin/true, --no-engines --no-pulse --no-osc-relay, free non-default ports, fixture copy of .showready/fixtures/mac/presets/EDM Show.json into the archived tree (`timing_ab.py:770-785`).

Pre-registration (/tmp/sdbar3-gate/PREREG.txt, `date` 2026-09-15 11:14:16 MDT, before the sensitivity run started at 11:14:28): verdict = `m_bridge.rule` of the pooled R=5 run; floor-resolution clause reported not required; abs deltas; sensitivity must be `m_bridge_sensitivity_timing_red` True; a failed arm stops the instrument and the run is repeated whole; the PNG is taken in a SEPARATE non-qualifying run; external sampler every 2.5 s.

## 2. Sensitivity (2 ms publisher delay, R=3, Mac + Chromium, `--rule m_bridge`): RED on M_bridge

Command (11:14:28 - 11:26:16, wall 701.9 s):
`.venv/bin/python -B scripts/showready/timing_ab.py --rule m_bridge --candidate HEAD --script scripts/showready/timing_script.json --repeats 3 --control sensitivity --scratch /tmp/sdbar3-gate/mac-mbridge-sensitivity --out /tmp/sdbar3-gate/mac-mbridge-sensitivity.json.gz --client-cmd '["node","/Users/viddyslap/Documents/project-workspaces/steam-deck-midi/scripts/showready/timing_browser.cjs","{url}","{stop}","{receipt}","/Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell","--single-process"]'`
-> **exit 1** (expected; exit 3 would be INVALID). `m_bridge_sensitivity_timing_red true`, `sensitivity_timing_red true`, `measurement_qualified true`, bytes identical, 9/9 arms VALID, error null, limitation null. Result sha256 861c2730af593c245448ca6fd5a9a8ce35151abb1d6672fd883849de3d1c9b2e.
Table: `.venv/bin/python -B docs/sdbar3-gate/gate_table.py /tmp/sdbar3-gate/mac-mbridge-sensitivity.json.gz --load-log /tmp/sdbar3-gate/load-samples.log --day 2026-09-15` -> exit 0; recompute equals instrument (per-arm 0 mismatches, pooled equal), re-derived M_bridge 0 mismatches. Copy: docs/sdbar3-gate/evidence/sensitivity-table.json.

| Sensitivity pooled (ms), n=28,914 per arm | p50 | p95 | p99 | max |
| --- | --- | --- | --- | --- |
| M_bridge CLOSED | 1.150 | 1.677 | 1.889 | 23.691 |
| M_bridge OPEN | 5074.404 | 10218.787 | 10635.235 | 10772.743 |
| M_bridge CLOSED-B | 1.146 | 1.652 | 1.841 | 17.778 |
| M_bridge floor abs(CLOSED - CLOSED-B) | 0.004 | 0.025 | 0.048 | - |
| M_bridge abs(OPEN - CLOSED) | 5073.254 | 10217.111 | 10633.347 | - |
| M_bridge within floor + 1.0 | False | False | False | - |
| M_total floor / delta | 0.004 / 5073.202 | 1.421 / 10099.080 | 1.089 / 8978.991 | - |
| M_post floor / delta (diagnostic) | 0.003 / 5073.240 | 0.018 / 10217.114 | 0.046 / 10633.354 | - |

Per-repeat M_bridge within (p50/p95/p99): r1 NNN, r2 NNN, r3 NNN. Load: every arm 1 attempt, `verified`, pgrep empty before and after, foreign_lines 0 before and after (no matched lines), load1 at arm start 2.66-3.31; external sampler 255 samples during the arms, foreign_lines max 0, pgrep non-empty 0. OPEN arms: client count 1 throughout, stream dropped 0, browser and bridge PIDs gone.
NOTE on what this proves: the planted 2 ms is per published event, so under OPEN the bridge falls seconds behind the 60 Hz stream (same shape as the sdlive locked-rule sensitivity, p50 5,133 ms there). It proves the M_bridge rule is not blind to a publisher delay on this path; it does not measure how small a steady shift M_bridge resolves. The clean run's M_bridge floor (under 0.08 ms at every statistic) is the resolution figure.

## 3 and 4. Qualifying run: R=5 interleaved, Mac + Chromium (Controller view, Follow ON), candidate HEAD

Command (11:26:54 - 11:46:27, wall 1163.3 s):
`.venv/bin/python -B scripts/showready/timing_ab.py --rule m_bridge --candidate HEAD --script scripts/showready/timing_script.json --repeats 5 --scratch /tmp/sdbar3-gate/mac-mbridge-clean --out /tmp/sdbar3-gate/mac-mbridge-clean.json.gz --sensitivity-result /tmp/sdbar3-gate/mac-mbridge-sensitivity.json.gz --client-cmd '<same argv as section 2>'`
-> **exit 0**. `rule_passed true`, `m_bridge_rule_passed true`, `locked_rule_passed true`, `bar3_counts true`, `measurement_qualified true`, `sensitivity_valid true`, bytes identical across 15 arms, error null. Result sha256 b17966cac7483c919eafb476e8ff728c7e04b93695d064778ce6245b98936d40. Instrument timing_ab.py b9b7994a... (recorded in the result).
Table: `.venv/bin/python -B docs/sdbar3-gate/gate_table.py /tmp/sdbar3-gate/mac-mbridge-clean.json.gz --load-log /tmp/sdbar3-gate/load-samples.log --day 2026-09-15` -> exit 0; per-arm statistics 0 mismatches against the instrument, pooled M_bridge/M_post/M_total equal, locked summary equal, re-derived M_bridge 0 mismatches. Copy: docs/sdbar3-gate/evidence/clean-table.json. Raw results stay in /tmp/sdbar3-gate/ (46 MB, not committed).

### Pooled, side by side (ms), n = 48,190 per arm

| Arm | M_bridge p50 | p95 | p99 | max | M_total p50 | p95 | p99 | max | M_post (diag) p50 | p95 | p99 | max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CLOSED | 1.117 | 1.660 | 1.912 | 12.873 | 1.166 | 121.025 | 1657.129 | 2038.185 | 1.099 | 1.640 | 1.890 | 12.863 |
| OPEN | 1.134 | 1.664 | 1.921 | 15.819 | 1.186 | 121.086 | 1654.634 | 2044.812 | 1.105 | 1.640 | 1.887 | 15.591 |
| CLOSED-B | 1.099 | 1.596 | 1.839 | 22.625 | 1.154 | 121.279 | 1655.156 | 2041.913 | 1.072 | 1.572 | 1.818 | 22.384 |
| noise floor abs(CLOSED - CLOSED-B) | 0.018 | 0.064 | 0.073 | - | 0.012 | 0.254 | 1.973 | - | 0.027 | 0.068 | 0.072 | - |
| abs(OPEN - CLOSED) | 0.017 | 0.004 | 0.009 | - | 0.020 | 0.061 | 2.495 | - | 0.006 | 0.000 | 0.003 | - |
| floor + 1.0 | 1.018 | 1.064 | 1.073 | - | 1.012 | 1.254 | 2.973 | - | 1.027 | 1.068 | 1.072 | - |
| within | True | True | True | - | True | True | True | - | True | True | True | - |
| rule outcome | **PASS (binding)** | | | | within (reported beside) | | | | within (diagnostic) | | | |

Per-repeat M_bridge (instrument `m_bridge.per_repeat`): r1-r5 all within at p50, p95 and p99, all passed.
`floor_can_resolve_2ms`: True for all three metrics.

M_total beside: in THIS run the locked expression is within at p99 because this run's M_total p99 floor is 1.973 ms (sdlive's was 0.021 ms) and the OPEN delta 2.495 ms. This is reported, not scored: the sdlive locked-rule RED on 5f98123 stands. Read together, M_total p99 moved by about 2 ms between CLOSED and CLOSED-B in this run, while M_bridge p99 moved 0.073 ms.

### Worst-case six-axis segment (simultaneous-sticks-triggers-60hz), pooled, n = 45,080 per arm

| Arm | M_bridge p50 | p95 | p99 | max | M_total p50 | p95 | p99 | max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CLOSED | 1.145 | 1.671 | 1.918 | 12.873 | 1.145 | 1.671 | 1.918 | 12.873 |
| OPEN | 1.166 | 1.673 | 1.931 | 15.819 | 1.166 | 1.673 | 1.931 | 15.819 |
| CLOSED-B | 1.133 | 1.603 | 1.849 | 22.625 | 1.133 | 1.603 | 1.849 | 22.625 |
| floor | 0.012 | 0.068 | 0.070 | - | 0.012 | 0.068 | 0.070 | - |
| abs(OPEN - CLOSED) | 0.021 | 0.002 | 0.013 | - | 0.021 | 0.002 | 0.013 | - |
| within floor + 1.0 | True | True | True | - | True | True | True | - |

M_bridge and M_total agree at this precision in the segment (same n) because those outputs are written while the bridge handles the step's first packet, whose t0 and t1_pre are stamps a few hundred ns apart. M_post worst-case (diagnostic): floor 0.017 / 0.068 / 0.070, delta 0.009 / 0.001 / 0.002, within.

### Per arm (clean run)

Counts: every arm has first_packet_join 9,638, every_message 9,638 (cause first packet 9,142, cause later packet 496), MIDI records 9,644 (6 startup records with step -1 are compared for bytes but not timed; `invalid` empty, measured on r1 CLOSED), packets 20,513 with t1_pre and t1_post. The >= 1000 floor applies to every_message: VALID on all 15. First-packet and every-message counts are equal because the locked metric already timed every MIDI record; what changed is which send each is timed from (B1 section 1).

| Rep | Arm | Load (pgrep before/after) | foreign_lines before/after (instrument) | sampler foreign max during | load1 before / after | M_bridge p50 / p95 / p99 / max | M_total p50 / p95 / p99 / max | M_post p99 | Stream dropped | Clients | Stream data events |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | CLOSED | verified empty/empty | 0/0 | 0 | 3.96 / 3.56 | 1.137 / 1.653 / 1.847 / 12.792 | 1.192 / 119.784 / 1655.059 / 2035.136 | 1.836 | - | - | - |
| 1 | OPEN | verified empty/empty | 0/0 | 0 | 3.56 / 3.25 | 1.199 / 1.778 / 2.543 / 12.221 | 1.255 / 119.068 / 1653.162 / 2032.066 | 2.438 | 0 | 1-1 | 16039 |
| 1 | CLOSED-B | verified empty/empty | 0/0 | 0 | 3.25 / 3.68 | 1.192 / 1.785 / 2.110 / 19.324 | 1.246 / 119.746 / 1658.199 / 2038.251 | 2.080 | - | - | - |
| 2 | CLOSED | verified empty/empty | 0/0 | 0 | 3.68 / 3.37 | 1.225 / 1.821 / 2.346 / 11.603 | 1.280 / 119.516 / 1657.099 / 2032.818 | 2.330 | - | - | - |
| 2 | OPEN | verified empty/empty | 0/0 | 0 | 3.34 / 3.12 | 1.175 / 1.713 / 1.946 / 11.094 | 1.235 / 118.644 / 1649.975 / 2044.812 | 1.923 | 0 | 1-1 | 16032 |
| 2 | CLOSED-B | verified empty/empty | 0/0 | 0 | 3.12 / 3.19 | 1.119 / 1.603 / 1.765 / 16.777 | 1.175 / 120.905 / 1657.712 / 2038.065 | 1.749 | - | - | - |
| 3 | CLOSED | verified empty/empty | 0/0 | 0 | 3.19 / 3.30 | 1.178 / 1.692 / 1.915 / 12.873 | 1.234 / 120.244 / 1657.967 / 2038.185 | 1.900 | - | - | - |
| 3 | OPEN | verified empty/empty | 0/0 | 0 | 3.19 / 3.07 | 1.146 / 1.633 / 1.828 / 8.806 | 1.201 / 120.399 / 1656.527 / 2039.457 | 1.811 | 0 | 1-1 | 16028 |
| 3 | CLOSED-B | verified empty/empty | 0/0 | 0 | 2.91 / 2.29 | 1.048 / 1.506 / 1.672 / 22.625 | 1.114 / 119.310 / 1654.932 / 2029.601 | 1.645 | - | - | - |
| 4 | CLOSED | verified empty/empty | 0/0 | 0 | 2.19 / 1.83 | 1.037 / 1.484 / 1.631 / 8.468 | 1.101 / 119.817 / 1657.325 / 2037.194 | 1.593 | - | - | - |
| 4 | OPEN | verified empty/empty | 0/0 | 0 | 1.93 / 2.46 | 1.075 / 1.559 / 1.742 / 8.664 | 1.130 / 120.567 / 1656.812 / 2037.931 | 1.700 | 0 | 1-1 | 16115 |
| 4 | CLOSED-B | verified empty/empty | 0/0 | 0 | 2.42 / 2.17 | 1.059 / 1.523 / 1.673 / 15.553 | 1.132 / 118.218 / 1650.184 / 2030.848 | 1.648 | - | - | - |
| 5 | CLOSED | verified empty/empty | 0/0 | 0 | 2.16 / 2.33 | 1.025 / 1.467 / 1.623 / 10.701 | 1.090 / 117.801 / 1656.947 / 2036.600 | 1.591 | - | - | - |
| 5 | OPEN | verified empty/empty | 0/0 | 0 | 2.42 / 1.77 | 1.081 / 1.569 / 1.768 / 15.819 | 1.138 / 119.573 / 1652.722 / 2031.668 | 1.751 | 0 | 1-1 | 16102 |
| 5 | CLOSED-B | verified empty/empty | 0/0 | 0 | 1.71 / 1.58 | 1.055 / 1.529 / 1.683 / 8.731 | 1.123 / 118.727 / 1648.621 / 2041.913 | 1.640 | - | - | - |

- load1 is `sysctl -n vm.loadavg` as read by the instrument's `foreign_load_check` immediately before and after each arm. Every arm: 1 attempt, no INVALID arm, nothing re-run or dropped. No matched foreign line in any before/after check.
- External sampler (`docs/sdlive-gate/scripts/foreign_load.py` every ~2.5 s, /tmp/sdbar3-gate/load-samples.log): 415 samples inside the 15 arms, foreign_lines max 0, pgrep non-empty 0; 887 of 887 samples over the whole session foreign_lines 0.
- Dropped live-stream events: 0 on every OPEN arm (browser-side count). The publisher's own counter `snapshot_after.dropped` is 23,990 on every arm, including CLOSED arms that have no client (the same value on every arm in sdlive), so it is not a browser-side loss.
- Every OPEN arm: client count 1 at every sample, live receipt valid, browser PIDs gone (kill(pid,0)), client and bridge PIDs gone.

**M_bridge VERDICT: PASS** (Mac + Chromium, R=5, sensitivity RED on M_bridge, instrument b9b7994a, candidate cdf0d40).

## 5. PNG

/Users/viddyslap/Documents/ViddyVault/screenshots/sdbar3-gate/open-arm-controller-view-live.png (sha256 848abb8d...): the Controller view mid-replay with "Follow: on" and "live", the Gyro card opened by follow, left and right stick dots and L2/R2 bars drawn from the live stream. Opened and inspected.
How: a SEPARATE, non-qualifying run (`timing_ab.py --rule m_bridge --candidate HEAD --repeats 1 --scratch /tmp/sdbar3-gate/png-run --out /tmp/sdbar3-gate/png-run.json.gz --client-cmd <same argv>` -> exit 78 HARNESS-SKIP, result sha256 4578d174...). During its r1 OPEN arm, `/tmp/sdbar3-gate/png/shot.cjs` opened a second headless Chromium on that arm's UI port (from capture.jsonl.ready.json), set Controller view and Follow, waited for "live", held 8 s and screenshotted: page state live / follow true / view visible, snapshot clients 2, stream dropped 0, its browser PID 96932 gone after close. It ran in a separate run because a second client inside a qualifying arm would change what is measured. A first attempt failed before opening a page (`browser.process is not a function`, exit 1); `ps` afterwards showed only the instrument's own browser (parent timing_browser.cjs).

## 6. Pick-up

| Check | Result |
| --- | --- |
| every link pushed | B1 cdf0d40 = origin (B1 envelope ls-remote); this link's commit and ls-remote in the envelope |
| `git status --porcelain` after commit | empty (see envelope check) |
| `git diff --stat 6eff30e HEAD` | 12 files at cdf0d40, all under docs/sdbar3-b1/, scripts/showready/ (README.md, SHA256SUMS, timing_ab.py) and tests/; `git diff --name-only 6eff30e HEAD \| grep -Ev '^(scripts/showready/\|tests/\|docs/)'` exit 1 (none); plus this link's docs/sdbar3-gate/ |
| no change under windows/, deck/, config/, mac/ | `git diff --stat 6eff30e HEAD -- windows deck config mac` empty |
| bar 1 A/B EDM Show, Mac | `.venv/bin/python -B scripts/showready/deck_script.py --out /tmp/sdbar3-gate/bar1/deck-script.json` exit 0, script_sha256 9256621abf62... (= pinned DECK_SHA256, scripts/showready/timing_script.py:11), 732 steps, 47,039 packets; `.venv/bin/python -B scripts/showready/ab_run.py --candidate HEAD --preset '.showready/fixtures/mac/presets/EDM Show.json' --section windows --script /tmp/sdbar3-gate/bar1/deck-script.json --out /tmp/sdbar3-gate/bar1/mac-edm.json` (candidate cdf0d40, run 11:52-12:00) exit 0, `passed: true`, B1 and B2 each: 56/56 mappings exercised, messages 1531 / 1531, different_mappings [], unexercised_mappings []; result sha256 4faf42bf8ee906ba3c159d7e5b37d28b904bad423a37575621e5049d935e55a7. **BAR 1 (EDM Show, Mac): GREEN, byte-identical** |
| processes I started are gone | 46 recorded PIDs (every arm's bridge; every OPEN arm's client and browser; the PNG run's; my screenshot browser 96932) checked with `kill -0` at 12:01:02: none alive. Each instrument arm also recorded `pid_gone` true (bridge) and `browser_cleanup.gone` true (OPEN). `ps -A -o pid=,command= | grep -E "capture_runner|chrome-headless-shell|timing_browser|shot.cjs|timing_ab.py|ab_run.py|sampler.sh"` exit 1 (none). The private tmux server (`tmux -L sdbar3gate`) has no sessions left; the load sampler stopped on its stop file. |

## 7. FOR BEN

On the Mac, opening the controller view does not measurably delay the bridge. With the view open and following live input, the time from the moment a packet is sent to the moment the bridge writes its MIDI moved by 0.02 ms or less at the median, the 95th and the 99th percentile. The run-to-run noise is under 0.08 ms and the allowance is 1 ms. The same test with a planted 2 ms delay in the live-view path failed by seconds, so the test can see this kind of delay. The earlier +2.8 ms result (sdlive) was timed from a point that includes the test rig's own sender pacing, so that red is the rig's pacing, not the bridge. It stays on the record as measured. On the show laptop the real sender is the Steam Deck, so the rig's pacing is not part of the show. Windows bar 3 is still DIAGNOSTIC only: no Windows sensitivity control has qualified, and Friday's installed v0.4.9 tray has no controller view at all. This is a Mac result. The Windows show laptop has not been measured this way, so it does not carry over to the laptop yet.

## Evidence

- docs/sdbar3-gate/gate_table.py: independent table and recompute (this report's numbers).
- docs/sdbar3-gate/evidence/sensitivity-table.json, clean-table.json: its outputs.
- docs/sdbar3-gate/evidence/raw-results-sha256.txt: sha256 of the raw results and the PNG.
- docs/sdbar3-gate/evidence/PREREG.txt: the pre-registration (copy of /tmp/sdbar3-gate/PREREG.txt).
- docs/sdbar3-gate/shot.cjs: the PNG helper as run (copy of /tmp/sdbar3-gate/png/shot.cjs).
- /tmp/sdbar3-gate/: raw results, logs (sens.log, clean.log, pngrun.log, load-samples.log), PREREG.txt, suite.log, metric-diff.patch.
