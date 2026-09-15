BASE 70cebd0b6baed2ece86a2d218843e02b6298789d
HEAD e2919763fe9174fe0fe44e2782f4279895cf0434

# sdstall S1 - MEASURE THE RECEIVER STALLS

Lane `steamdeck`, week of 2026-09-14. A MEASUREMENT lap: NO product code.
Question: is the ~3.5 s receive stall sdauto's gate measured in the PRODUCT (the 70cebd0..e291976 diff) or in the MAC'S ENVIRONMENT?

Link start: 2026-09-15 16:44:36 MDT (launch record `created`). `git rev-parse HEAD` at S1 start, run 16:44:44 MDT: e2919763fe9174fe0fe44e2782f4279895cf0434. `git status --porcelain` at S1 start: 0 lines.

## sdauto LANDED line (quoted from the LANE LOG, line 1009)

> NEEDS-MASTER: sdauto LANDED at e2919763fe9174fe0fe44e2782f4279895cf0434 - FEATURE-COMPLETE 0.5.0 candidate; bar 1 byte-identical vs v0.4.9 EDM Show/PTZ/default on Mac and laptop, dead-seam RED (PTZ Mac re-run by AJ); bar 2 Windows `Ran 997 tests` OK (skipped=6) exit 0 at a8fec2a; bar 3 M_bridge |OPEN-CLOSED| p95 1868.469 ms vs floor+1.0 2.904 ms on qualifying clean3 (RED, HELD owner sdstall); F2 Mac BASE 94.3% SIGINT ignored -> HEAD 0.3% SIGINT exit 0, Windows HEAD 0.36-0.41% vs v0.4.9 0.05-0.10% of one core, installed tray 1.198%; known finding update_hz bounds owner sdpolish P0; ready for sdrc

Found by `grep -n "NEEDS-MASTER: sdauto LANDED" "/Users/viddyslap/Documents/ViddyVault/Ai playground/batons/lane-steamdeck-20260914-m12.md"` -> exit 0, line 1009.

## DECLARED BEFORE DATA

Copied verbatim from the item (MASTER 13, 16:23 and 16:41), then the four MASTER 13 16:44 changes, then this link's own declarations. Committed before any measurement so its timestamp precedes the data.

### From the item (MASTER 13, 16:23; corrected 16:41)

- A STALL is a receiver gap: any moment where the receiver's newest MIDI record is more than 1 s older than the sender's newest send, equivalently an M_bridge sample > 1,000 ms. Also report the gate's census threshold (> 100 ms) beside it.
- PRODUCT-CAUSED, CORRECTED (MASTER 13, 16:41 (1), because the earlier count rule fires by chance about 9 percent of the time when BASE and HEAD are identical: at the census rate of about 0.20 stalls per CLOSED-type arm, P(0 in 6 BASE) = 0.8^6 = 0.26 and P(>= 2 in 6 HEAD) = 0.35):
  - COUNT EVIDENCE: the pattern is 0 BASE arms with a stall > 1 s and >= 2 HEAD arms with one, over R >= 8 VALID CLOSED arms per revision per session, and it must hold in TWO sessions started at least 30 minutes apart so they sample different windows of the day. One session showing the pattern alone is never PRODUCT-CAUSED: it is UNRESOLVED-PENDING-REPLICATION, and S1 runs the second session itself.
  - STACK EVIDENCE, on its own and in ONE session: a stall-time `sample` stack that shows the receive thread blocked in code the lap changed (a lock, a file write, a logging handler) is PRODUCT-CAUSED, on either machine. That is direct evidence, not a count.
  - Counts on either machine follow the two-session rule for that machine.
- ENVIRONMENT-CAUSED if stalls hit BASE and HEAD alike with receive-thread samples in the normal wait (recvfrom/select), OR every stall coincides with lms PROCESSINGPROMPT or a decompression burst while none occurs without it. The coincidence half of this clause is read ONLY from the FINE-GRAINED samples defined below (0.5 s polling around a gap); a stall with no fine-grained sample around it is reported as UNSAMPLED, never as "no coincidence" (MASTER 13, 16:41 (2)).
- Anything else is UNRESOLVED: NEEDS-MASTER.
- ADJACENT-PAIR TABLE (MASTER 13, 16:41 (1)), reported beside the totals: for each BASE/HEAD pair in the interleave, whether each arm stalled. A product cause should show HEAD stalling with its BASE neighbour clean, pair after pair.
- UNRESOLVED-PENDING-REPLICATION is a fourth outcome: the count pattern held in one session and the second session did not reproduce it (or could not run). Say which.
- TWO READINGS (MASTER 13, 16:30 (c)): this lap is ATTRIBUTION, not a bar verdict. The clauses above are evaluated TWICE: on VALID arms only, and on ALL arms with complete raw files (VALID plus INVALID-by-load). Both readings are reported. Where they AGREE, that is the classification; where they DISAGREE, the result is UNRESOLVED with both shown. R >= 8 per revision per session counts VALID arms only.
- NOT REPRODUCED (MASTER 13, 16:30, declared before any data): if NO arm on a machine (>= 8 VALID per revision in each of the two sessions) shows a stall > 1 s AND the lms record shows no PROCESSINGPROMPT during those arms, that machine's result is `NOT REPRODUCED ON A QUIET MAC` (or `LAPTOP`). It is a finding, not a pass: the product stall was not observed without inference. It is NOT ENVIRONMENT-CAUSED unless the stalls also reappear with inference in the same session.
- "Code the lap changed" means a file:function in `git diff 70cebd0 <HEAD> -- windows/`; list those files in the report before the data.

### MASTER 13, 16:44 - four changes, declared BEFORE any data

Received in session at 16:46 MDT, before any arm was run. The launch at 16:44:36 froze the earlier text; the chain record now carries these too (S1 digest 230cf1c236506c13).

1. The TWO-SESSION replication rule binds the MAC only; WINDOWS is ONE session of R >= 8 VALID arms per revision, diagnostic (its question is only whether HEAD stalls on the show machine at all).
2. The judge's re-run is a SANITY CHECK of 2 arms per revision, not a replication, unless S1's two Mac sessions DISAGREE on the count pattern, in which case the judge runs a full >= 8 session as the tie-break.
3. ORDER, so the 30-minute gap is not idle: Mac session 1, then the Windows interleave during the gap (record Mac load1 throughout it), then Mac session 2, then the judge; budget about 1.5 to 2 hours.
4. ADDITION, the sharpest discriminator: report STALL RATES SPLIT BY INFERENCE STATE, per revision and per session, arms with ANY fine-grained PROCESSINGPROMPT sample against arms with none. Stalls only in inference-active arms ON BOTH revisions is ENVIRONMENT-CAUSED by the declared rule; the same split on HEAD arms alone is NOT and stays with the count rule.

### LOAD RULES and EXTENDED LOAD VALIDITY

Carried verbatim from the item (MASTER 16:5x / 01:11, and MASTER 13 15:21 ruling (3) as corrected at 15:27, carried into sdstall by the 16:23 ruling (2a)). Every Mac timing arm in this lap:

- `pgrep -f "while True: pass"` EMPTY immediately before and after; `load1` recorded (`sysctl -n vm.loadavg`) and `foreign_lines` = 0. (The pinned instrument's own `foreign_load_check` performs exactly these checks before and after every arm attempt; this link does not reimplement them.)
- A whole-machine sampler every <= 5 s records load1 and every process above 20% of one core that is not in the arm's own recorded pid tree.
- An arm is INVALID if ANY in-arm sample has load1 > 5.0, or any non-lane process holds > 50% of one core for > 10 s during the arm. WindowServer and kernel_task are recorded, not counted.
- Wait until load1 < 4.0 for 60 s before starting.
- If the Mac cannot hold a quiet 25 minutes within 90 minutes: `NEEDS-MASTER: sdstall Mac timing blocked by machine load <top processes>` at column 0 at the bottom of the LANE LOG, and wait in session.

DIVERGENCE FROM sdauto AG, DECLARED: sdauto's supervisor VOIDED a whole run when any arm was INVALID and started a fresh full run. This lap does NOT void the run on one INVALID arm, because the item requires that an INVALID arm's raw sender, receiver, environment and stack files are KEPT, listed in a separate table, never deleted, and entered into the ALL-arms reading. An INVALID arm is not counted toward R; the runner keeps going until R >= 8 VALID arms per revision are collected.

### This link's own declarations, before data

- FINE-GRAINED SAMPLING: the receiver-gap watch polls the arm's live `capture.jsonl` (opened by `capture_runner.py` with `buffering=1`, i.e. line-buffered, so each MIDI record reaches the file as it is recorded) every 50 ms. Baseline environment record: 1 per second. Baseline `lms ps`: every 5 s. The moment the observed receiver gap exceeds 200 ms, `~/.lmstudio/bin/lms ps` and `vm_stat` are polled every 0.5 s until the gap clears. A 60 s ring of 1 s samples is kept around every stall. A stall with no fine-grained sample around it is marked UNSAMPLED.
- STALL STACKS: when the observed receiver gap exceeds 1 s, `sample <bridge pid> 2 -file <path>` is run against the arm's own bridge process (a process this link started; no other process is ever sampled). Up to 10 samples per revision. `sample` suspends the target while it walks the stacks, so it costs the arm real time: every stack file records the wall time the `sample` command took, and any arm in which a stack was taken is marked `sampled` in the arm table.
- The GAP THE WATCH SEES is a wall-clock gap in the receiver's record stream, which is the operational form of the declared stall. The AUTHORITATIVE stall count per arm is computed afterwards from the arm's own `bridge_samples` (M_bridge = t3 - t1_pre per message), from the raw result file, exactly as sdauto's census did. The watch triggers sampling; the raw file decides.
- INSTRUMENT: the pinned `scripts/showready/timing_ab.py` at HEAD is used for BOTH revisions, pointed at each tree through its own `--candidate` / `--repo` arguments (it resolves the candidate with `ab_run.archive`, which is `git archive <commit>`). The instrument has NO CLOSED-only order (`timing_ab.py:799`: `names = ('OPEN',) if args.control == 'dead-client' else ARMS`, and `ARMS = ('CLOSED', 'OPEN', 'CLOSED-B')` at line 28). This link therefore drives the instrument's own CLOSED-arm code through a wrapper, `docs/sdstall-s1/scripts/closed_only.py`, which imports `timing_ab` unchanged and calls `timing_ab.guarded_arm(...)` around `timing_ab.run_arm(...)` - the same two functions `timing_ab.run()` calls at lines 803-806 - after building the candidate tree, fixtures, preset and script with the same `timing_ab` / `ab_run` / `deck_script` functions `run()` uses. Equivalence is proved by ONE CLOSED arm run both ways (stock `timing_ab.py --repeats 1` vs the wrapper), comparing the record fields and the files present in the arm directory.

### Files the lap changed (`git diff --name-only 70cebd0 e291976 -- windows/`)

15 files, 1219 insertions, 40 deletions:

| File | insertions/deletions |
| --- | --- |
| windows/build_fingerprint.py | 8 +- |
| windows/engine_config_api.py | 179 ++ (new) |
| windows/engines/autopilot.py | 202 +- |
| windows/engines/autopilot_state.py | 230 ++ (new) |
| windows/engines/base.py | 8 ++ |
| windows/engines/osc_sync.py | 18 +- |
| windows/engines/registry.py | 126 +- |
| windows/engines/stageflow_bridge.py | 20 +- |
| windows/log_ring.py | 48 ++ (new) |
| windows/osc_relay.py | 120 ++ |
| windows/receiver.py | 5 ++ |
| windows/receiver_tasks.py | 84 ++ (new) |
| windows/static/index.html | 15 ++ |
| windows/ui_server.py | 128 +- |
| windows/win_recv.py | 68 +- |

The changed code that sits ON the receive path, for the STACK EVIDENCE clause (read from the diff, not from a summary):

- `windows/receiver.py:serve_forever` - the only receive-loop change: `receiver_tasks=None` parameter, and `if receiver_tasks is not None: receiver_tasks.drain()` inside the loop, beside the existing reload check.
- `windows/receiver_tasks.py:ReceiverTaskQueue.drain` - what that call runs: `with self._lock:` on a `threading.Lock`, then an empty-deque return.
- `windows/log_ring.py:RingLogHandler.emit` and `:tail` - a `logging.Handler` attached to the ROOT logger by `windows/win_recv.py:main` via `install_ring_handler()`, so every log record in the process is formatted into a deque. `emit` runs under `logging.Handler.handle`'s per-handler lock; `tail` takes `self.acquire()`. In a `--no-engines` arm the bridge logs about 15,246 `engine_registry.on_axis_event failed` records, so this handler runs on the MIDI path. (sdauto AG measured the formatting cost at +2.8 us per record and called the ring REFUTED as the cause; the handler lock and the deque are still the changed code a stack would have to show.)
- `windows/win_recv.py:main` - `install_ring_handler()`, `ReceiverTaskQueue()`, `OscRelayController`, `--no-browser`, `_should_start_receiver_tray`, and the extra `ui_server` constructor arguments.
- `windows/ui_server.py` - +128 lines of HTTP handlers. CLOSED arms have NO HTTP client, so these run only at startup/teardown unless a stack shows otherwise.

A stall-time stack showing the receive thread inside any `file:function` above is PRODUCT-CAUSED by the declared rule. A stall-time stack showing it in `recvfrom` / `select` / `kevent` (the normal wait, unchanged since BASE) is the ENVIRONMENT clause's first half.

## Instrument equivalence, and the detector, BEFORE any classification data

### 1. The CLOSED-only wrapper runs the instrument's own CLOSED arm

ONE CLOSED arm at HEAD run both ways in the same session, 2026-09-15:

- wrapper: `docs/sdstall-s1/scripts/closed_only.py --candidate e2919763... --repeats via --valid-target 1 --max-arms 1`, 16:52:12-16:53:26, exit 0.
- stock: `scripts/showready/timing_ab.py --rule m_bridge --candidate e2919763... --repeats 1`, 16:53:26-16:57:09 (exit 78: the m_bridge rule cannot qualify at R=1; only its CLOSED arm is used).

`docs/sdstall-s1/scripts/equivalence.py` compared them (evidence/equivalence.json, exit 0): **EQUIVALENT**.

| Compared | Result |
| --- | --- |
| arm result field set | equal, 29 fields, none only in one |
| load-guard row field set | equal, 6 fields |
| load check `before` field set | equal, 7 fields |
| `bridge_samples[0]` field set | equal, 10 fields |
| `samples[0]` field set | equal, 10 fields |
| `coverage` field set | equal, 8 fields |
| files present in the arm directory | equal: bridge.log, capture.jsonl, capture.jsonl.done.json, capture.jsonl.ready.json, client.log, options.json, start, timing.json |
| candidate archive_sha256 | d3929488c54e31746e5a4d797eacfb5e88a50996f3e11c906238c579b2c07a2b in BOTH; commit e2919763..., git_tree 5332ac9d... |
| pinned instrument sha256 map / script sha256 / preset sha256 | equal |
| passed / timing_status / every_message_timing_status | true / VALID / VALID in both |
| timed MIDI messages | 9,638 in both |
| snapshot clients before, after | [0, 0] in both (CLOSED has no client) |
| load_status | `verified` in both |

The function driven is `timing_ab.run_arm`, wrapped in `timing_ab.guarded_arm` with `timing_ab.foreign_load_check` - the same three calls `timing_ab.run()` makes at lines 803-806.

### 2. The receiver-gap detector: what it measures, and why not the obvious thing

The first version of the watch measured wall-clock silence in the arm's live `capture.jsonl`. Measured on the equivalence arm, that detector is WRONG, and this was found before any classification data was collected:

- the arm's authoritative raw M_bridge: n = 9,638, max **14.4 ms**, p50 1.103 / p95 1.585 / p99 1.763 ms, **0 samples over 100 ms, 0 over 1,000 ms**;
- the same arm's observed record-stream silence: **max 2.55 s**, 37 episodes over 200 ms, and three `sample` stacks taken for nothing.

The reason is in the pinned script, measured directly from `scripts/showready/timing_script.json`: the SEND schedule never pauses (20,513 packets over 70.40 s, 291.4 packets/s, **largest gap between consecutive packets 10.0 ms**), but the MIDI RECORD stream legitimately goes quiet for as long as **3,200 ms**. Record silence is the script being quiet, not the receiver stopping. It is recorded as a diagnostic and is never counted as a stall.

What does mean the receiver stopped is the arm's own UDP socket RECEIVE QUEUE. The sender keeps delivering datagrams into the kernel buffer at 16,954.8 bytes/s, so a stopped receive path piles unconsumed bytes there. The watch reads Recv-Q for THIS ARM'S port from `netstat -an -p udp` (about 3 ms per read, sampled every 50 ms) and converts:

    backlog_s = recvq_bytes / 16954.8      (200 ms = 3,391 bytes; 1 s = 16,955 bytes)

That is the receiver's distance behind the sender, in the declared rule's own units. Recv-Q is a kernel byte count that may include per-buffer overhead, so the derived seconds are approximate and the RAW BYTES are recorded beside them.

### 3. The detector is shown to fire and not to fire, on fixtures

`docs/sdstall-s1/scripts/detector_fixture.py` (evidence/detector-fixture.json, exit 0). Two arms at the script's own rate (291.4 packets/s of 58 bytes), calling the SAME `arm_watch.recvq()` the real watch calls. The positive arm's receiver SLEEPS 2.5 s: it plants a stall without adding any CPU load to this Mac.

| Arm | max Recv-Q bytes | max backlog_s | crossed 200 ms | crossed 1 s |
| --- | --- | --- | --- | --- |
| NEGATIVE, receiver drains continuously | 90 | 0.0053 | NO | NO |
| POSITIVE, receiver sleeps 2.5 s | 64,260 | 3.7901 | YES | YES |

`DETECTOR PROVEN BOTH WAYS`. Separation between the healthy ceiling (0.0053 s) and the fine trigger (0.200 s) is a factor of 38.

The watch is only a TRIGGER for sampling. Every stall count in the tables below is recomputed from the arm's own `bridge_samples` in the raw result file (M_bridge = t3 - t1_pre), exactly as sdauto's census did.
