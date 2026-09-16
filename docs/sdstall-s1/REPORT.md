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

### MASTER 13, 17:02 - the FOURTH cause class, declared BEFORE any data

Received in session at 17:02 MDT, while session 1's first arms were running and before any arm of the counted data existed. Copied here because PRODUCT and ENVIRONMENT are now downstream of it.

1. FOURTH CAUSE CLASS, INSTRUMENT-ARTEFACT: `timing_ab.py bridge_join` (:85-103) keys a MIDI record to a packet by `(row['step'], row['logical_ns'])`, and `row['step']` is the step the bridge was HANDLING when it wrote; but the bridge also writes MIDI from its OWN timers (fades receiver.py ~374, relative_cc repeats ~467, staged macros ~478, engine ticks, long-press holds), so a timer-driven write inside a quiet window carries the LAST received datagram's step and M_bridge = t3 - t1_pre of a packet already seconds old. A stall sample is INSTRUMENT-ARTEFACT if its record was timer-driven AND no datagram arrived between its cause packet and t3. Classify EVERY stall > 1 s this way FIRST, from the raw, reporting per stall: the record's action, timer-driven or not, the gap between the cause packet's arrival and t3, and the count of datagrams in between.
3. The PRODUCT and ENVIRONMENT classes apply ONLY to stall samples that SURVIVE (1): a record whose cause packet arrived while datagrams kept flowing.
6. Do NO heavy analysis DURING an arm: run the artefact classification and any scan of a large raw file between arms or after a session, so the load rule is not tripped by this link's own work, and say so in the report.

HOW THIS LINK HONOURED (6): every scan of a raw result file, every census and every artefact classification in this report was run AFTER a session's last arm finished, never while an arm was running. The only reads taken during an arm were of the session log and the 49-line machine-sampler file. The session driver's own per-arm check is a provisional load1 test over already-written samples; the AUTHORITATIVE `arm_validity.py` pass runs once per revision after the session's last arm.

HOW THIS LINK TESTS (1), and the independent instrument it adds: the classifier `docs/sdstall-s1/scripts/stall_classify.py` reports, for every stall sample over 1,000 ms, the record's action and MIDI bytes, its step / cause_step / cause_packet, the gap t3 - t1_pre(cause), `datagrams_sent_between` (packets whose own t1_pre lies in that interval), `datagrams_processed_between` (records at or before t3 carrying a NEWER cause packet - if this is zero the bridge processed nothing new in the window) and `concurrent_fresh_records` (records within +-250 ms of t3 whose own M_bridge is under 100 ms - if any, the receive path was demonstrably not stopped). It adds one check that comes from OUTSIDE the instrument's own bookkeeping: `recvq_backlog_s_at_t3`, the arm's own UDP receive-queue backlog at the same wall moment. A real receive stall piles unconsumed datagrams in the kernel buffer; a stale-attribution artefact does not. A sample is INSTRUMENT-ARTEFACT if fresh records or newer-cause records exist, or if the independent Recv-Q backlog stayed under 200 ms at t3; it SURVIVES only if nothing newer was processed, nothing fresh was adjacent, and the kernel buffer was filling.

### A load defect this link caused, found and fixed BEFORE the counted data

The first session-1 attempt (17:00:55-17:03:23) produced 2 arms and BOTH were INVALID under the EXTENDED LOAD VALIDITY cap: `s1-a01-base` max load1 **13.46**, load1 above 5.0 in 12 of its 14 in-arm samples, and a non-lane hog `fseventsd` at **104.1%** for 10.0 s. The cause was this link's own design, not the machine: the first driver extracted a fresh `git archive` candidate tree (1,356 files at BASE, 1,612 at HEAD) for EVERY arm, and Spotlight indexed each one - the machine sampler shows `git` 42%, then `fseventsd` 92-104%, `mds` 37-40% and `mds_stores` 89-100% across 17:01:00-17:01:20 while load1 climbed 2.21 -> 7.0.

Fixed two ways, both before any counted arm:

- `.metadata_never_index` in `/tmp/sdstall/` and in each work directory: the unprivileged, reversible way to keep Spotlight off the tree. No `mdutil`, no sudo, no machine-wide setting changed.
- ONE candidate tree per revision per session, reused by all of that revision's arms through `closed_only.py --work`. This is what the pinned instrument itself does (`timing_ab.run()` builds one tree at lines 787-800 and serves all 15 arms of a run from it). Both trees are now built BEFORE the quiet gate, so any residual indexing is over before the first arm is timed.

The 2 aborted arms are kept at `/tmp/sdstall/s1-aborted-spotlight/` and are NOT counted in any table: they measured this link's own defect, not the product or the machine.

This is worth carrying: sdauto AG's own run 1 had **8 of 15 arms INVALID with load1 up to 17.22**, and its qualifying run still reached load1 4.79, on the same `/tmp` scratch pattern. Whether Spotlight indexing of the candidate tree contributed to that is UNVERIFIED-BY-EXECUTION here - this link did not re-run sdauto's configuration - but the mechanism is now measured on this machine.

### MASTER 13, 17:39 - session 1 accepted, and a conditional THIRD session

Received in session at 17:40 MDT, after session 1's counted arms and before session 2.

- Session 1 is ACCEPTED as reported: it establishes zero M_bridge samples over 1,000 ms on a quiet Mac at BASE and HEAD alike, and the about 2.6 s natural quiet in every arm confirms the detector rebuild was right.
- It establishes NOTHING about the inference-active case: lms IDLE in every arm makes the split DEGENERATE, and **a degenerate split is not evidence of absence**. This report states that wherever the split appears.
- ADDITION: if qwen-bench or any local-LLM-* workload becomes ACTIVE again while sdstall still holds the lane, run a THIRD session labelled DIAGNOSTIC-UNDER-LOAD, AFTER the two Mac sessions and the Windows interleave, never delaying them: same ABAB interleave, BASE and HEAD, >= 4 arms per revision, fine sampling ARMED FROM THE FIRST ARM rather than at the 200 ms trigger, arms EXPECTED to be INVALID under the load cap and never counted toward any R >= 8 floor. Its single question: does an M_bridge sample over 1,000 ms REAPPEAR under load, and if so does it pass the 17:02 artefact test, and what does Recv-Q say at t3.
  - reappears on BOTH revisions and artefact-classified = INSTRUMENT-ARTEFACT TRIGGERED BY LOAD (the sdauto RED explained with no product fault);
  - reappears on HEAD alone, artefact or not = a PRODUCT finding the master rules on;
  - does not reappear at all = the sdauto RED stays UNEXPLAINED.
- The per-arm quiet gate is APPROVED and goes into sdpolish's rules as well: a gate before each arm beats voiding an arm after it.

THIS LINK NEVER STARTS THAT WORKLOAD. The hard rule stands: it never loads, unloads, stops or reconfigures an LM Studio model or server, and `~/.lmstudio/bin/lms ps` is the only lms verb it runs. `docs/sdstall-s1/scripts/mac_session_load.sh` checks the precondition itself (a PROCESSINGPROMPT row in `lms ps`, or a local-LLM process above 20% of a core) and exits 9 without running an arm if nothing is active.

### The THIRD session did NOT run: its named workload was stopped

MASTER 13's 17:39 DIAGNOSTIC-UNDER-LOAD session is conditional on a qwen-bench or other local-LLM-* workload being ACTIVE. Ben stopped his qwen-bench testing at about 18:00 MDT on 2026-09-15 and ran no further benches while sdstall held the lane (relayed through the master).

This link measured the precondition itself rather than accepting the relay. `docs/sdstall-s1/evidence/under-load-precondition.txt`, taken at **2026-09-15 17:47:56 MDT**:

| Check | Command | Value |
| --- | --- | --- |
| load1 | `sysctl -n vm.loadavg` | 2.93 (1 min), 3.03, 3.34 |
| local model state | `~/.lmstudio/bin/lms ps` | qwen3-coder-30b-a3b-instruct-mlx **IDLE**, text-embedding-bge-m3 **IDLE**; no PROCESSINGPROMPT row |
| local-LLM workloads above 20% of one core | `ps -A -o pcpu=,command=` filtered for qwen-bench / local-LLM- , `awk '$1 > 20.0'` | **0** |
| the named processes | `ps` filtered for drive-iteration / run-watcher / run2.sh | **absent**; the only local-LLM-* match is the harness engine `server.mjs --port 8899` at 2.0% |

The precondition is NOT met, so `mac_session_load.sh` was not run and would have exited 9 without an arm if it had been. THE THIRD SESSION DID NOT RUN, and this link never created the trigger: it never loaded, unloaded, stopped or reconfigured an LM Studio model or server.

CONSEQUENCE, stated plainly because it bounds what this lap concluded: every Mac arm in this report was measured with the local model IDLE. The inference-active case is UNTESTED here. A degenerate inference split is not evidence of absence (MASTER 13, 17:39), and the sdauto RED was measured in a window where MASTER 13 observed the same model in PROCESSINGPROMPT at 16:22-16:24.

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

## The measurement

Three interleaved CLOSED-arm BASE/HEAD runs. Every arm alternates BASE, HEAD, BASE, HEAD; every number below is recomputed from the arm's own raw result file.

| Session | Host | Wall start - end | Arms run | BASE VALID | HEAD VALID | R >= 8 both |
| --- | --- | --- | --- | --- | --- | --- |
| s1 | Mac | 17:06:51 - 17:42:47 | 24 | 8 | 8 | YES |
| win | laptop `viddyslaptop` | 17:38:36 - 18:02:50 | 16 | 8 | 8 | YES |
| s2 | Mac | 18:03:08 - 18:27:56 | 19 | 8 | 8 | YES |

Gap between the START of Mac session 1 and the START of Mac session 2: **56.3 minutes** (the rule requires >= 30). The Windows interleave ran in that gap, as MASTER 13 ordered at 16:44 (3). Mac `load1` was recorded throughout it: `{ 3.58 3.00 3.47 }` before the Windows arms, `{ 2.00 1.87 2.28 }` after.

Windows is ONE session of R >= 8 per revision, diagnostic, per MASTER 13 16:44 (1).

### Headline numbers, both readings

| Session / reading | Rev | Arms | Arms with a stall > 1,000 ms | Arms with a sample > 100 ms | max M_bridge (ms) | worst arm p95 (ms) | max load1 | lms STATUS seen |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| s1 VALID only | BASE | 8 | **0** | 0 | 32.8 | 1.712 | 4.85 | IDLE |
| s1 VALID only | HEAD | 8 | **0** | 0 | 16.1 | 1.721 | 4.27 | IDLE |
| s1 ALL complete raw | BASE | 10 | **0** | 0 | 45.7 | 1.742 | 14.91 | IDLE |
| s1 ALL complete raw | HEAD | 14 | **0** | 1 | 227.5 | 1.854 | 10.87 | IDLE |
| s2 VALID only | BASE | 8 | **0** | 0 | 20.1 | 1.644 | 3.70 | IDLE |
| s2 VALID only | HEAD | 8 | **0** | 0 | 24.9 | 1.697 | 3.87 | IDLE |
| s2 ALL complete raw | BASE | 10 | **0** | 0 | 25.1 | 1.644 | 5.68 | IDLE |
| s2 ALL complete raw | HEAD | 9 | **0** | 0 | 34.6 | 1.697 | 3.87 | IDLE |
| win VALID | BASE | 8 | **0** | 8 | 344.3 | 96.380 | n/a | n/a |
| win VALID | HEAD | 8 | **0** | 8 | 377.5 | 126.379 | n/a | n/a |

Windows has no Mac load sampler and the pinned instrument records load as `not applicable` there (`timing_ab.load_check`, `os.name == 'nt'`), so the load1 cap and the hog clause are NOT CHECKABLE for those arms; VALID there means what the instrument itself accepted (load guard accepted the attempt AND the arm passed). The ALL and VALID readings are therefore identical for Windows.

**ZERO M_bridge samples over 1,000 ms in all 59 arms, on both revisions, on both machines, in both readings.** The two readings AGREE everywhere.

### The stall-sample classification is empty, and that is the honest result

MASTER 13 17:02 (1) required every stall over 1,000 ms to be classified as INSTRUMENT-ARTEFACT or not before PRODUCT or ENVIRONMENT could apply. The classifier ran over all 59 arms:

    Stall samples over 1,000 ms across every arm classified: 0
    Surviving MASTER 17:02 (1): 0
    AGREE-REAL (17:02 survived AND the queue was filling): 0
    DISAGREE: 0

There were no stalls to classify. The artefact test, the Recv-Q check beside it and the agreement column all have empty tables. The stall-stack table is empty for the same reason: the watch's stack trigger is a 1 s Recv-Q backlog and the largest backlog any Mac arm reached was **0.059 s**, so `sample` was never run on a bridge process during the counted sessions.

### Environment during the Mac arms

| Item | Value |
| --- | --- |
| lms STATUS in every Mac arm of both sessions | **IDLE** only. PROCESSINGPROMPT count: **0**, at the 5 s baseline and in fine-grained polling alike |
| fine-grained samples fired | 0, because no arm's Recv-Q backlog reached the 200 ms trigger |
| max Recv-Q backlog per arm | 0.030 - 0.059 s (raw bytes 512 - 1,000), against a 200 ms trigger at 3,391 bytes |
| max record-stream silence per arm | about 2.6 s in EVERY arm - the natural script quiet, not a stall |
| memory pressure level | 2 throughout (`sysctl -n kern.memorystatus_vm_pressure_level`) |
| `.metadata_never_index` | present in BOTH the scratch and the work directory for all four Mac scratches (2 revisions x 2 sessions); n/a on the Windows host |

The UNSAMPLED marking has no members: a stall with no fine-grained sample around it is marked UNSAMPLED, and there were no stalls.

### Stall rates split by inference state (MASTER 13, 16:44 (4)) - DEGENERATE

| Reading | Revision / state | Arms | Arms with a stall > 1 s |
| --- | --- | --- | --- |
| VALID only | base / inference-active | 0 | 0 |
| VALID only | base / inference-quiet | 16 | 0 |
| VALID only | head / inference-active | 0 | 0 |
| VALID only | head / inference-quiet | 16 | 0 |

Every arm is inference-quiet. The split has an empty arm on one side and therefore discriminates nothing. **A degenerate split is not evidence of absence** (MASTER 13, 17:39). This is the sharpest discriminator the lap declared and it could not be applied, because the workload that would have populated the other side was stopped.

### Adjacent-pair tables, INVALID-arm tables, per-arm environment

The full generated tables - arm table with the `.metadata_never_index` column, adjacent-pair table per session, totals in both readings, inference split, INVALID-arm table with reasons, and the per-arm environment summary - are in `docs/sdstall-s1/evidence/tables.md` (327 lines), rendered by `docs/sdstall-s1/scripts/report_tables.py` from `evidence/census.json`.

Every adjacent BASE/HEAD pair in every session reads `base_stalled no | head_stalled no`. A product cause should show HEAD stalling with its BASE neighbour clean, pair after pair; no pair shows that, because no arm stalled.

### A Windows finding that is NOT a stall

The laptop's M_bridge distribution is materially worse than the Mac's, on BOTH revisions:

| Arm | n | samples > 100 ms | max M_bridge (ms) | p50 (ms) |
| --- | --- | --- | --- | --- |
| win-a01-base | 9,638 | 335 (3.48%) | 224.4 | 5.38 |
| win-a02-head | 9,638 | 666 (6.91%) | 254.1 | 5.48 |
| win-a15-base | 9,638 | 391 (4.06%) | 286.5 | 5.23 |
| win-a16-head | 9,638 | 482 (5.00%) | 255.8 | 5.59 |

Mac p50 is about 1.1 ms and p95 about 1.7 ms; the laptop's p50 is about 5.4 ms and its p95 96-126 ms, with 3.5-6.9 percent of messages over 100 ms in bursts spread through the stream. NO sample reaches 1,000 ms. This is present at BASE 70cebd0 as well as HEAD, so it is NOT introduced by the sdauto diff. It is NOT a comparison against the v0.4.9 tag (e66ff44): BASE here is 70cebd0, sdauto's base of lap, not v0.4.9. A v0.4.9-vs-HEAD Windows latency comparison was not part of this item and has not been run.

## CLASSIFICATION

Evaluated against the declared rules, in BOTH readings, per machine and overall.

| Clause | MAC | LAPTOP |
| --- | --- | --- |
| PRODUCT-CAUSED, count evidence: 0 BASE arms with a stall > 1 s and >= 2 HEAD arms with one, over R >= 8 VALID CLOSED arms per revision per session, in TWO sessions >= 30 min apart | NOT MET. HEAD arms with a stall: 0 in s1, 0 in s2. R >= 8 was met in both sessions and both revisions; the gap was 56.3 min. The pattern requires >= 2 HEAD arms with a stall and there were none | NOT MET. HEAD arms with a stall: 0. Windows is one session by MASTER 13 16:44 (1) |
| PRODUCT-CAUSED, stack evidence: a stall-time `sample` stack showing the receive thread in code the lap changed | NOT MET. No stack was taken, because no arm's Recv-Q backlog reached the 1 s stack trigger (max 0.059 s) | NOT MET. No stall, and Windows stacks were not in scope |
| ENVIRONMENT-CAUSED, first half: stalls hit BASE and HEAD alike with receive-thread samples in the normal wait | NOT MET. No stalls hit either revision | NOT MET |
| ENVIRONMENT-CAUSED, second half: every stall coincides with lms PROCESSINGPROMPT or a decompression burst while none occurs without it. Read ONLY from the fine-grained samples | NOT APPLICABLE. No stalls, and no fine-grained samples fired. Nothing is reported as "no coincidence" | NOT APPLICABLE |
| INSTRUMENT-ARTEFACT (MASTER 13, 17:02 (1)), which decides first | NOT APPLICABLE. 0 stall samples to classify | NOT APPLICABLE |
| NOT REPRODUCED: no arm shows a stall > 1 s, with >= 8 VALID per revision in each of the two sessions, AND the lms record shows no PROCESSINGPROMPT during those arms | **MET on both halves.** 0 stalls in 8+8 VALID arms in s1 and 8+8 in s2; lms IDLE with 0 PROCESSINGPROMPT in every arm | **MET** for its one declared session: 0 stalls in 8+8 arms. lms is not applicable on the laptop |

**MAC: `NOT REPRODUCED ON A QUIET MAC`. LAPTOP: `NOT REPRODUCED ON A QUIET LAPTOP`. OVERALL: `NOT REPRODUCED ON A QUIET MAC`.**

The two readings AGREE on every machine and every clause, so that is the classification, with no UNRESOLVED branch taken.

As the declared rule says in its own words, this is **a finding, not a pass**: the product stall was not observed without inference. It is explicitly NOT ENVIRONMENT-CAUSED, because that clause needs the stalls to reappear with inference in the same session and no session with inference could be run.

### What this does and does not settle

SETTLED, on 32 VALID Mac arms and 16 Windows arms:

- The ~3.5 s receive stall is NOT a property of the sdauto diff that appears whenever HEAD runs. HEAD ran 16 VALID Mac arms across two sessions an hour apart plus 8 Windows arms. Its worst M_bridge sample in a VALID Mac arm was **24.9 ms**; across ALL 23 HEAD Mac arms including the load-invalid ones it was **227.5 ms** (s1-a04-head, an arm INVALID at load1 10.87); on the laptop **377.5 ms**. The declared stall threshold is 1,000 ms.
- BASE 70cebd0 and HEAD e291976 are indistinguishable on this metric on a quiet machine. Over the 16 VALID Mac arms per revision, per-arm p95 spans **1.494-1.712 ms at BASE** and **1.564-1.721 ms at HEAD**; max M_bridge **32.8 ms at BASE** (s1-a12-base) and **24.9 ms at HEAD** (s2-a04-head).
- The stall is not reproducible at will. sdauto's gate saw 4 stalling arms in 20 in one window and none in 21 arms in another; this lap saw 0 in 59.

NOT SETTLED, and this is the part that matters for Friday:

- The inference-active case is UNTESTED. Every arm here ran with the local model IDLE. MASTER 13 measured that same model in PROCESSINGPROMPT at 16:22-16:24, inside the window where sdauto's stalls appeared, and the DIAGNOSTIC-UNDER-LOAD session that would have tested it had no trigger once Ben stopped his benches.
- So the sdauto bar 3 RED is **UNEXPLAINED, not cleared**. By MASTER 13's own 17:39 wording, "does not reappear at all = the sdauto RED stays UNEXPLAINED, which the master would rather know than guess."
- A cause that needs a loaded machine to appear is not excluded by 59 arms on a quiet one.

## For Ben, in plain words

The scary thing from yesterday's gate was that the bridge stopped receiving MIDI for about three and a half seconds, with the controller view CLOSED. If that were in the 0.5.0 code, it would be a dropout on stage on Friday.

I ran the same measurement 59 times today - 32 clean timed runs on the Mac split across two sessions an hour apart, 16 more on your show laptop, alternating the old code and the new code every single run - and **it never happened once**. Not on the new code, not on the old code, not on either machine. In the clean runs the worst single delay on the Mac was 33 thousandths of a second. Even counting the runs I threw out because your Mac got busy, the worst was 227 thousandths. On the laptop the worst was under four tenths of a second. A stall has to be over one full second to count, and nothing came within half of that.

Two honest caveats:

1. **I could not test the case I most wanted to test.** When the gate saw those stalls, your local AI model was busy generating. Today it sat idle for every single run, and you stopped your benchmark testing partway through, so I had no way to put the machine under that load without breaking the rule that I never start or stop your models. So I can tell you the new code does not stall a quiet machine. I cannot yet tell you it will not stall a busy one.
2. **That means the original problem is unexplained rather than fixed.** Nothing I found points at the new code - the old code behaved identically in every run - but "I could not make it happen again" is weaker than "I found what caused it."

Two things worth knowing that came out of the measurement:

- **Your laptop is about five times slower than the Mac on this path**, and a few percent of MIDI messages there take over a tenth of a second. That is true of the OLD code too, so it is not something 0.5.0 introduced - it is just what that machine does. It is well inside what a show needs, and I am flagging it rather than acting on it.
- **My first stall detector was wrong and I caught it before it produced any numbers.** It would have reported a 2.6 second stall in every single run. The replay script genuinely goes quiet for up to 3.2 seconds with no MIDI due, and I was reading that silence as the bridge freezing. I rebuilt it to watch the actual network queue the bridge has not read yet, which cannot be fooled that way, and proved it both ways on a test rig before trusting it.

If you want the strongest possible answer before Friday, the one thing that would help is running the same measurement while your local model is actually generating. That needs your say-so, since I will not start it myself.

## Evidence and how to re-run it

Committed under `docs/sdstall-s1/`:

| Path | What |
| --- | --- |
| `scripts/closed_only.py` | the CLOSED-only wrapper; drives `timing_ab.guarded_arm(timing_ab.run_arm(...))`, the pinned instrument's own calls |
| `scripts/arm_watch.py` | per-arm environment record, Recv-Q receiver-gap watch, stall stacks |
| `scripts/detector_fixture.py` | proves the gap detector fires and does not fire, on fixtures |
| `scripts/equivalence.py` | proves the wrapper's CLOSED arm equals the stock instrument's |
| `scripts/stall_classify.py` | MASTER 17:02 (1) artefact test, with the Recv-Q verdict beside it |
| `scripts/census.py`, `scripts/report_tables.py` | the authoritative census from raw files, and the rendered tables |
| `scripts/mac_session.sh`, `scripts/mac_session_more.sh`, `scripts/mac_session_load.sh` | the Mac session runners (the second adds the per-arm quiet gate; the third is the DIAGNOSTIC-UNDER-LOAD runner that did not run) |
| `scripts/win_session.sh`, `win_setup.ps1`, `win_arms.ps1`, `win_teardown.ps1`, `win_list_results.ps1` | the laptop interleave, over the rail |
| `scripts/machine_sampler.py`, `scripts/arm_validity.py` | VERBATIM copies of sdauto AG's (sha256 `c7052e2770c6b4da...` and `9fa1209d189188b7...`, identical to `docs/sdauto-gate/scripts/`) |
| `evidence/census.json`, `evidence/tables.md` | every per-arm number, and the rendered tables |
| `evidence/classify/` | the per-arm stall classification (all empty of stalls) |
| `evidence/equivalence.json`, `evidence/detector-fixture.json` | the two pre-data proofs |
| `evidence/mac/s1/`, `evidence/mac/s2/` | session logs, `arm_validity.py` output per revision, the whole-machine sampler (gzipped), and every arm's watch summary, environment record, Recv-Q record and gap record (gzipped) |
| `evidence/win/` | the laptop arm log, results list and recorded pids |
| `evidence/win-guard-before.txt`, `evidence/win-guard-after.txt`, `evidence/win-teardown.txt`, `evidence/win-setup.txt`, `evidence/win-session.log` | the guard snapshot and compare, the teardown inventory, the railed payload sha256 on both machines |
| `evidence/under-load-precondition.txt` | this link's own measurement that the DIAGNOSTIC-UNDER-LOAD trigger was absent |
| `evidence/raw-result-sha256.txt` | sha256 of all 59 raw result files |

The 59 raw `*.json.gz` result files are about 3 MB each (about 180 MB total) and stay in `/tmp/sdstall/<session>/` and `/tmp/sdstall/win/`; their sha256 are committed. The arm directories with `capture.jsonl`, `bridge.log`, `timing.json` and `start` are under `/tmp/sdstall/base-70cebd0/<session>/timing-<session>/` and `/tmp/sdstall/head-e291976/<session>/timing-<session>/`, INVALID arms included, none deleted.

The two arms of the aborted first session-1 attempt (the Spotlight defect) are at `/tmp/sdstall/s1-aborted-spotlight/`, kept and counted in no table.

## Laptop hard rules, discharged

| Rule | Evidence |
| --- | --- |
| THE GUARD before the first act and after the last | `GUARD GREEN: snapshot; protected state observed; pythonProcesses=0` at 17:36:27, and `GUARD GREEN: compare; protected state observed; pythonProcesses=0` after the last act. **The compare result is GREEN.** |
| the installed v0.4.9 tray, loopMIDI, Resolume never touched | teardown listing: `PROTECTED_RUNNING=3` - loopMIDI pid 16020, STEAMDECK-MIDI-RECEIVER-2-Tray pids 5268 and 23640, all still running and none stopped |
| no process opened a real MIDI port | `capture_runner.py` denies `mido`/`rtmidi` by construction and every arm ran `--dry-run` equivalent (`--no-engines --no-pulse --no-osc-relay`, Recorder with no real port) |
| the tray's UDP 45123 and TCP 7723 untouched | every arm bound a free non-default loopback port chosen by `timing_ab.free_port`; the guard's UDP 45123 / TCP 7723 owners are unchanged between snapshot and compare |
| the orphan checkout never pulled, committed or modified | never touched; the only reads of the CLONE were `git --no-optional-locks` in the state probe |
| every process started is stopped and PROVEN gone | `RECORDED_PIDS=16`, `RECORDED_PIDS_STILL_ALIVE=0`, `PYTHON_PROCESSES=0` |
| BROWSER CLASS RULE (a) | `BROWSER` set to the no-op proved to return 0 on this laptop (commit 51b1d5b, `<venv python> -c pass %s`), both by the outer script and by `timing_ab.run_arm`'s own env. `--no-browser` was NOT passed: BASE 70cebd0's `win_recv.py` has no such argument (`git show 70cebd0:windows/win_recv.py \| grep -c no-browser` = 0; HEAD = 2), and the pinned instrument does not pass it. Declared deviation, with the no-op belt proven instead |
| BROWSER CLASS RULE (b), session-aware browser listing before /complete | `BROWSER_PROCESSES=0` - no chrome.exe, msedge.exe or firefox.exe running at all, in any session. No `NEEDS-MASTER: browser in Ben's session` line is owed |
| PROCESS-CLASS ORDER | `win_teardown.ps1` classifies in the ruled order (PROTECTED, then RECORDED LANE PID, then LANE PATH UNRECORDED, then NOT LANE) and stops nothing. No unrecorded lane-path process was found |
| CODE reaches the laptop only by a verified route | `git archive` zips railed with `win_rail.sh put`, sha256 recorded on BOTH machines and re-verified on the laptop before use: base.zip `438e04911ac54f30...` 59,672,838 bytes, head.zip `c5ecb49436399518...` 62,697,845 bytes, fixtures.zip `a806a8b85141ca26...` 17,198 bytes, all three `SHA256_MATCH`. NO GitHub fetch or pull from the laptop |
| no system-wide installs | none; the clone's own venv interpreter ran every arm and nothing was pip-installed |

The laptop clone is at `a8fec2ad635e141b0634dc9a51c5442dad9fd966`, one commit behind the Mac HEAD, with `PORCELAIN_LINES=0`. That did not matter: the arms ran the RAILED BASE and HEAD trees, and the clone supplied only the pinned `scripts/showready` kit, whose `timing_ab.py`, `capture_runner.py` and `timing_script.json` sha256 were verified IDENTICAL to the Mac's before any arm. The clone has no `.showready` directory at all, which is why the fixture kit was railed too.
