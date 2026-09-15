BASE OF LAP 6eff30e6211543e8be1d6159e41467086730ddb7

# sdbar3 B1: t1_pre / t1_post and the declared M_bridge rule in the pinned timing instrument

Executor: claude-rc claude-opus-5 on the Mac, unsandboxed (Ben's fallback (b)). Branch chain/steamdeck-20260914.
Changed: scripts/showready/timing_ab.py, scripts/showready/README.md, scripts/showready/SHA256SUMS,
tests/test_showready_timing.py, tests/showready_m_total_fixture.json, docs/sdbar3-b1/.
Nothing under windows/, deck/, config/ or mac/. The MIDI path and capture_runner.py are unchanged.
New timing_ab.py digest: b9b7994a9f599d3eb8960379c7b2e09f4d4164daf743b4d852bcfa2f7d2c7c78 (was 93e4d2b1...).
README digest: 9af0a8e8da1c7097e853903e32205f9cc0523f71973a42c7a6c359b532f75313. `shasum -a 256 -c scripts/showready/SHA256SUMS` -> 15 OK.

No bar 3 verdict comes from this link. The locked-rule RED from sdlive (p99 2.818 ms > 1.021 ms) stands and was not re-scored.

## 1. Where the timestamps sat (base 6eff30e)

| Stamp | Where | What it is |
| --- | --- | --- |
| send stamp `sent_at` | `scripts/showready/timing_ab.py:258` | `time.perf_counter_ns()` taken before `sendto` (:261), for EVERY packet |
| stored as `self.sent[step]` | `timing_ab.py:259-260` | ONLY for the first packet of each step (`if event:`); later packets' stamps were discarded |
| MIDI time t3 | `scripts/showready/capture_runner.py:52` | `time.perf_counter_ns()` in Recorder.send, stored as `monotonic_ns`, same PID as the sender |
| latency (locked M_total) | `timing_ab.py:220` | `(perf_counter_ns - sent[cause_step]) / 1e6`, cause_step from the E1 action attribution (:211-214, :189-198) |
| packet in hand | `capture_runner.py:191` | `context.update(step=..., logical_ns=at_ns)` at each receipt, before the bridge handles it |

EG's decomposition (`docs/sdlive-gate/scripts/p99_decompose.py`):
- sender part `= sent[base] - sent[cause_step]` (`p99_decompose.py:32`), where `base` is the last EVENT step at or before the MIDI record's current step (`:30-31`).
- receiver part `= perf_counter_ns - sent[base]` (`:33`).
- Both use only first-packet-of-step stamps from `timing_ab.py:258-260`. So the "receiver part" started at the pre-sendto stamp of the last event packet, NOT at the datagram that released the output: when a delayed output is released by a timer heartbeat (a later packet in that step), the receiver part still contained the rig's heartbeat pacing within the step (up to 2.5 s of scheduled offsets; its p99 was ~173 ms). It did not separate the rig from the bridge, as MASTER 04:00 said.

Correction to the orchestrator's FACT, measured by reading and by the stored capture: the stamp is indeed before sendto and stored only for the first packet of each step. But the locked samples already covered EVERY timed MIDI record (`timing_ab.py:207-221`: every `record == 'midi'` with `step != -1` is timed); what was first-packet-only was the SEND STAMP each record was timed against. Consequence visible below: `first_packet_join` and `every_message` counts are equal (9638 each); the difference is which send each message is timed from. Also, t0 as implemented is not a scheduled time: it is the measured pre-sendto stamp of the cause step's first packet. M_total keeps that exactly.

## 2. What was built (file:line at the new HEAD)

- t1_pre `timing_ab.py:366` `t1_pre = time.perf_counter_ns()` immediately before `written = sender.sendto(...)` (:367); t1_post `:368` immediately after it returns; both stored per packet index (:369) for ALL 20,513 packets. `sent_at` (:363) and `self.sent[step]` (:365) are untouched, so t0 and M_total are the same computation.
- The join (`CaptureTiming.enrich`, `timing_ab.py:320-325`): each timed MIDI record gets `cause_packet` = the packet identified by the (step, script instant) the bridge was handling when it wrote the MIDI (`capture_runner.py:191`; (step, at_ns) is unique over all 20,513 packets, measured). The locked t0 join is unchanged (:319 now calls `m_total_ms`, :80, same expression).
- `bridge_join` (`timing_ab.py:85`): after replay, attaches t1_pre/t1_post to every timed message; a missing stamp, an unknown packet or t3 < t1_pre RAISES (arm error), never skips. M_bridge = t3 - t1_pre, M_post = t3 - t1_post (may be slightly negative: the bridge can write MIDI before the sender thread's post stamp).
- `summarize_bridge` (`timing_ab.py:639`): per arm and pooled p50/p95/p99/max for m_bridge, m_post and m_total (m_total from the locked samples); both count sets per arm (`first_packet_join`, `every_message`) plus `every_message_cause_first_packet` / `_later_packet`; per-repeat verdicts; the six-axis worst-case segment separately for all three metrics; a diagnostic verdict on M_post.
- `--rule m_bridge` (default `locked`). Every run prints a `BESIDE` line with both rules' floors, deltas, within and passed (`beside`, `timing_ab.py:690`); the result carries `summary` (locked, unchanged), `m_bridge`, `locked_rule_passed`, `m_bridge_rule_passed`.
- Under `--rule m_bridge`: arm validity also needs every-message >= 1000; qualification needs it on every arm; the load check is `foreign_load_check` (`timing_ab.py:207`): pgrep as before plus `foreign_lines` (the MASTER definition, ported from `docs/sdlive-gate/scripts/foreign_load.py`) and sysctl load1; any foreign line = present load (retried per `--load-retries`, then fail), unreadable ps = unreadable.
- Sensitivity: `--rule m_bridge --control sensitivity` records `m_bridge_sensitivity_timing_red`; if it is not True (not RED, or no verdict at all) the tool prints `M_BRIDGE RULE INVALID: sensitivity control did not go RED` and exits 3 (`timing_ab.py:882`). The clean command accepts only an m_bridge-RED receipt (`sensitivity_matches(control, result, 'm_bridge')`).

Decisions taken inside the declared rule, stated so they can be overruled before any M_bridge qualifying data exists:
1. The locked verdict's extra clause "floor must resolve 2 ms" (`floor_can_resolve_2ms`) is REPORTED but not required under m_bridge (`require_floor_resolution=False`): the declared rule establishes resolution only through its own sensitivity run. Bytes identical, live client proven, drops reported and valid arms ARE required, exactly as the locked verdict requires them.
2. foreign_lines is enforced inside the instrument under `--rule m_bridge` only; `--rule locked` load behaviour is byte-for-byte as before.

JOIN ASSUMPTION the master and Ben should see (not a change of rule, a consequence of it): `--clock script` releases fades, holds and staged notes when the heartbeat whose script time crosses the deadline arrives. M_bridge times such an output from THAT heartbeat's send, so the intentional product delay (hold/fade/staged duration, ~0.1-2 s) is outside M_bridge, while M_total includes it by design (README "Intentional hold/fade/staged delays are INCLUDED"). In the diagnostic, 496 of 9638 messages per arm are released by a later packet; for the other 9142, t0 and t1_pre are the same packet's stamps taken a few hundred ns apart. The assumption that the bridge writes MIDI only while handling the most recently received datagram holds because the serve loop is single-threaded (`windows/receiver.py:1046-1069`: recvfrom, handle_datagram, advance_fades, check_timeouts); a timeout wakeup under the script clock does not advance time.

## 3. M_total equality proof (regression of the unchanged metric, NOT a re-scoring of bar 3)

`.venv/bin/python -B docs/sdbar3-b1/rescore_m_total.py /tmp/sdlive-gate/mac-clean.json.gz /tmp/sdlive-gate/mac-clean/timing-yf1_10x7` -> exit 0.
Input: the sdlive gate's clean Mac Chromium R=5 result, sha256 37ee1c90131bfdfb73868fb2be59960122591bfb466e425365fce103a786d21f (equal to `docs/sdlive-gate/evidence/raw-results-sha256.txt`), and its 15 capture.jsonl files. Every MIDI row goes through the NEW `CaptureTiming.enrich`, pooled by the NEW `summarize`.
- `messages_compared 144660`, `message_latency_mismatches 0`, all 15 per-arm statistics equal, `pooled_and_rule_equal true`, `ALL_EQUAL true`.
- Pooled (ms), new code = stored: CLOSED p50 1.112708 / p95 121.39962905000871 / p99 1658.7378026200001; OPEN 1.1377705 / 122.17688315001125 / 1661.5554757500006; CLOSED-B 1.107021 / 121.1662734000083 / 1658.7168520100004 (n=48190 each). The stored rule object, including p99 delta 2.818 and floor 0.021, is equal.
- Negative control, same command with `--plant-1ns` (t0 one ns earlier): exit 1, `message_latency_mismatches 144570`, `ALL_EQUAL false`.
- Output files: /tmp/sdbar3-b1/rescore-mac-clean.json, /tmp/sdbar3-b1/rescore-mac-clean-plant.json.

## 4. Tests and revert proofs

`tests/test_showready_timing.py` gained 8 tests (module: `.venv/bin/python -B -m unittest tests.test_showready_timing` -> `Ran 19 tests`, OK):
- `test_t1_pre_before_and_t1_post_after_sendto_for_every_timed_message`: the real sender loop with a sendto that sleeps 5 ms and writes MIDI at the end of the stall, for a first packet and a later packet: t1_post - t1_pre >= 5 ms on both, M_bridge >= 5 ms (includes the stall), M_post < 5 ms (excludes it), M_total >= 5 ms (includes it).
- `test_missing_t1_stamp_is_an_error_not_a_skip`: missing t1_pre, missing t1_post, short stamp list, unknown packet -> ValueError; t3 < t1_pre -> ValueError; a real replay stamps every packet.
- `test_m_bridge_rule_passes_within_floor_and_fails_two_ms_p99_shift`: +0.3 ms passes; a +2 ms shift of the top 2% gives within p50 True, p95 True, p99 False, not passed, every repeat red; different bytes void it.
- `test_invalid_arm_voids_m_bridge_verdict`: one arm with 999 every-message samples -> valid_arms False, pooled not passed, only that repeat red; measurement_qualified refuses it.
- `test_m_bridge_sensitivity_not_red_exits_nonzero`: `main()` with not-RED and with no verdict -> exit 3 and the INVALID line; RED -> exit 1 without it; locked rule unaffected.
- `test_m_total_unchanged_against_stored_fixture`: 714 real rows (486 delayed outputs) from sdlive mac-clean r1-OPEN with their stored latency_ms and statistics computed by the BASE instrument (`git show 6eff30e:scripts/showready/timing_ab.py`); new enrich must reproduce every latency and the stats exactly.
- `test_foreign_lines_match_engine_tests_and_void_the_load_check`, `test_m_bridge_sensitivity_receipt_must_be_an_m_bridge_red`.

Revert proofs: `/tmp/sdbar3-b1/revert_proofs.py` (copy below in section 8) mutates timing_ab.py, runs the named test, restores, and checks the digest -> exit 0, `MUTANTS RED 5/5`:
- R1 t1_pre taken AFTER sendto -> t1 test exit 1
- R2 missing stamp silently skipped -> missing-stamp test exit 1
- R3 sensitivity-not-RED exit code removed -> sensitivity test exit 1
- R4 M_total moved by 1 ns -> fixture test exit 1
- R5 invalid arm no longer voids M_bridge -> invalid-arm test exit 1
- restored digest b9b7994a... equal; module clean after restore, exit 0.

## 5. DIAGNOSTIC dry run (Mac, speed 1, Python client, R=1; NON-QUALIFYING)

Load before the command: `pgrep -f "while True: pass"` exit 1 empty; `sysctl -n vm.loadavg` `{ 2.18 2.86 2.85 }`; `docs/sdlive-gate/scripts/foreign_load.py` foreign_lines 0, exit 0. Load status inside the instrument: verified on all three arms (I can run pgrep; not UNVERIFIED-LOAD), foreign_lines 0 before and after every arm, load1 2.25 / 3.23 / 3.05 at arm start.

`.venv/bin/python -B scripts/showready/timing_ab.py --candidate HEAD --script scripts/showready/timing_script.json --repeats 1 --rule m_bridge --scratch /tmp/sdbar3-b1/diagnostic --out /tmp/sdbar3-b1/diagnostic.json.gz`
-> exit 78 `HARNESS-SKIP` (R=1, Python client, no receipt: never credit). Result sha256 2c87034ae9073d50081a26f88bc5d500a95a2dfd14259135128736c1d70ce76d, instrument timing_ab.py b9b7994a... (the committed one).
The run is R=1 with CLOSED, OPEN and CLOSED-B (the tool always runs the triplet). Table from `.venv/bin/python -B docs/sdbar3-b1/diagnostic_table.py /tmp/sdbar3-b1/diagnostic.json.gz` (exit 0):

Stamps: every arm 20513 packets, t1_pre recorded 20513, t1_post recorded 20513, every timed message has both: True. t1_post - t1_pre min 2417 / 2417 / 2416 ns, max 1.516 / 3.384 / 2.376 ms (CLOSED / OPEN / CLOSED-B).

| Arm | first_packet_join | every_message | cause first packet | cause later packet | status |
| --- | --- | --- | --- | --- | --- |
| CLOSED | 9638 | 9638 | 9142 | 496 | VALID |
| OPEN | 9638 | 9638 | 9142 | 496 | VALID |
| CLOSED-B | 9638 | 9638 | 9142 | 496 | VALID |

| Metric (ms) | Arm | p50 | p95 | p99 | max | n |
| --- | --- | --- | --- | --- | --- | --- |
| M_bridge | CLOSED | 1.119 | 1.627 | 1.852 | 14.565 | 9638 |
| M_bridge | OPEN | 1.120 | 1.664 | 1.961 | 13.085 | 9638 |
| M_bridge | CLOSED-B | 1.148 | 1.661 | 1.883 | 37.456 | 9638 |
| M_post | CLOSED | 1.114 | 1.615 | 1.843 | 14.561 | 9638 |
| M_post | OPEN | 1.109 | 1.639 | 1.941 | 13.081 | 9638 |
| M_post | CLOSED-B | 1.139 | 1.639 | 1.855 | 37.452 | 9638 |
| M_total | CLOSED | 1.169 | 115.857 | 1648.956 | 2024.427 | 9638 |
| M_total | OPEN | 1.170 | 115.653 | 1644.813 | 2019.666 | 9638 |
| M_total | CLOSED-B | 1.200 | 114.666 | 1648.158 | 2023.975 | 9638 |
| worst-case M_bridge | CLOSED | 1.151 | 1.636 | 1.861 | 14.565 | 9016 |
| worst-case M_bridge | OPEN | 1.152 | 1.671 | 1.976 | 13.085 | 9016 |
| worst-case M_bridge | CLOSED-B | 1.181 | 1.668 | 1.887 | 37.456 | 9016 |
| worst-case M_total | CLOSED | 1.151 | 1.636 | 1.861 | 14.565 | 9016 |
| worst-case M_total | OPEN | 1.152 | 1.671 | 1.976 | 13.085 | 9016 |
| worst-case M_total | CLOSED-B | 1.182 | 1.668 | 1.887 | 37.456 | 9016 |

BESIDE line printed by the run: locked (M_total) floor p50 0.032 / p95 1.192 / p99 0.798, delta 0.002 / 0.205 / 4.142, within T/T/F, passed false; m_bridge floor 0.029 / 0.034 / 0.031, delta 0.001 / 0.036 / 0.109, within T/T/T, passed true.
These are R=1 Python-client numbers and prove only that the fields exist and are computed. They are not a bar 3 result and must not be read as one; the qualifying Chromium run, with its sensitivity control, is the next link's.

## 6. QUALIFYING commands (README "Declared M_bridge rule (sdbar3 B1)")

Sensitivity first (R=3, expected exit 1 with `m_bridge_sensitivity_timing_red:true`; exit 3 = rule INVALID), then clean (R=5). Measured wall time of the same workload in the sdlive gate: sensitivity 691 s, clean 1135 s; budget 12-14 and 19-21 minutes plus load retries. UNVERIFIED-BY-EXECUTION in this link.

```bash
.venv/bin/python -B scripts/showready/timing_ab.py --rule m_bridge --candidate HEAD --script scripts/showready/timing_script.json --repeats 3 --control sensitivity --scratch /tmp/sdbar3-gate/mac-mbridge-sensitivity --out /tmp/sdbar3-gate/mac-mbridge-sensitivity.json.gz --client-cmd '["node","/Users/viddyslap/Documents/project-workspaces/steam-deck-midi/scripts/showready/timing_browser.cjs","{url}","{stop}","{receipt}","/Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell","--single-process"]'
.venv/bin/python -B scripts/showready/timing_ab.py --rule m_bridge --candidate HEAD --script scripts/showready/timing_script.json --repeats 5 --scratch /tmp/sdbar3-gate/mac-mbridge-clean --out /tmp/sdbar3-gate/mac-mbridge-clean.json.gz --sensitivity-result /tmp/sdbar3-gate/mac-mbridge-sensitivity.json.gz --client-cmd '["node","/Users/viddyslap/Documents/project-workspaces/steam-deck-midi/scripts/showready/timing_browser.cjs","{url}","{stop}","{receipt}","/Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell","--single-process"]'
```

Scratch paths are /tmp/sdbar3-gate/ for the gate; a differently named link should substitute its own /tmp/sdbar3-<link>/.

## 7. Suite, node checks, pins, bar 1

| Command | Result |
| --- | --- |
| `TMPDIR=/tmp/sdbar3-b1/suite PYSTRAY_BACKEND=dummy BROWSER=/usr/bin/true .venv/bin/python -B -m unittest discover -s tests -p 'test_*.py'` | exit 0, `Ran 910 tests in 15.030s`, `OK (skipped=2)` (902 at sdlive + 8 new) |
| `node tests/ui_controller_check.cjs` | exit 0, `UI controller behavior: PASS (...)` |
| `node tests/ui_controller_macro_check.cjs` | exit 0, 48 disk writes match, 72 refused |
| `node tests/ui_reload_check.cjs` | exit 0, PASS |
| `node tests/ui_sections_check.cjs` | exit 0, PASS |
| `node tests/ui_controller_geometry.cjs` | NOT RUN as a measurement. It needs a live bridge URL and Chromium (no-arg run: exit 2, usage). Its wrapper `scripts/showready/ui_geometry.py:27-28` refuses scratch outside /tmp/sdfix-*, which this lap's scratch rule forbids, and the sdlive gate recorded it exit 1 against the live Controller (networkidle, `tests/ui_controller_geometry.cjs:118`). PRE-EXISTING, owed per docs/sdlive-gate/REPORT.md item 4; no UI or geometry file changed here. |
| `shasum -a 256 -c scripts/showready/SHA256SUMS` | exit 0, 15 OK |
| `.venv/bin/python -B scripts/showready/deck_script.py --out /tmp/sdbar3-b1/bar1/deck-script.json` | exit 0, script_sha256 9256621abf62eb21e6c345ef286b6b7fcc087a2db87b8f682ce7fcf7703a993e (= pinned source_deck_sha256), 732 steps, 47039 packets |
| `.venv/bin/python -B scripts/showready/ab_run.py --candidate HEAD --preset '.showready/fixtures/mac/presets/EDM Show.json' --section windows --script /tmp/sdbar3-b1/bar1/deck-script.json --out /tmp/sdbar3-b1/bar1/mac-edm.json` (candidate HEAD = base 6eff30e; capture_runner.py unchanged; run after the instrument edit) | exit 0, `passed: true`, B1 and B2 identical to A, 56/56 mappings exercised, messages 1531 / 1531 (same as sdlive gate), no different or unexercised mappings; result sha256 21dc3d88090a266c03a73d7432fa179847c5aef71e9723abb5675c7e5d390a32. BAR 1 (EDM Show, Mac): GREEN |

## 8. For the next link

- The instrument now records t1_pre/t1_post on every packet in every run, whatever the rule. `--rule locked` output is unchanged apart from the extra fields and the BESIDE line.
- Run the sensitivity command first; exit 3 means the declared rule is INVALID on this host, not a pass.
- Read `m_bridge.rows[*].counts` for both count sets; `summary` is still the locked rule.
- The two decisions in section 2 (floor-resolution clause reported not required; foreign_lines enforced only under m_bridge) and the join assumption (intentional delay durations are outside M_bridge) are for the master to confirm before the qualifying run.
- FOR BEN (either way): if bar 3 stays RED on M_bridge, the practical mitigation is to leave the controller view CLOSED during the show and use it for setup and soundcheck; live highlights are for checking controls, not for the performance.
- Evidence scripts committed: docs/sdbar3-b1/rescore_m_total.py, docs/sdbar3-b1/diagnostic_table.py, docs/sdbar3-b1/revert_proofs.py. Raw outputs stay in /tmp/sdbar3-b1/ (not committed).
