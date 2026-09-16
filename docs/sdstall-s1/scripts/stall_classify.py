"""sdstall S1: classify EVERY stall > 1 s. MASTER 13 17:02 (1) FIRST; Recv-Q BESIDE it.

  stall_classify.py --result FILE.json.gz [--armdir DIR] [--recvq FILE] [--preset FILE]
                    --label L --out FILE.json

WHY (MASTER 13, 17:02 (1)). `timing_ab.bridge_join` (timing_ab.py:85-103) keys a
MIDI record to a packet by (row['step'], row['logical_ns']), and capture_runner
sets both from `context` at each datagram RECEIPT. The bridge also writes MIDI
from its own timers (fades receiver.py ~374, relative_cc repeats ~467, staged
macros ~478, engine ticks, long-press holds). A timer-driven write therefore
inherits whatever datagram the bridge last processed, and if that datagram is
seconds old the record reads as a multi-second M_bridge with no stall.

TWO INDEPENDENT VERDICTS ARE REPORTED SIDE BY SIDE. MASTER 13, 17:09: the Recv-Q
check is approved and welcome, BESIDE the 17:02 test, never instead of it.

  verdict_17_02   MASTER's rule, from the instrument's OWN raw only:
                  INSTRUMENT-ARTEFACT iff the record was TIMER-DRIVEN and NO
                  datagram arrived between its cause packet and t3.
                  timer_driven      the action's mapping type is one of the
                                    timer-capable kinds the instrument itself
                                    names (macro_cc, relative_cc,
                                    staged_note_macro - CaptureTiming.install,
                                    timing_ab.py:297-300), OR the record's step
                                    differs from its cause_step.
                  no_datagram_between  datagrams_processed_between == 0, i.e. no
                                    record at or before t3 carries a NEWER cause
                                    packet, so the bridge processed nothing new.

  verdict_recvq   From OUTSIDE the instrument's bookkeeping: the arm's own UDP
                  receive-queue backlog at the same wall moment. It measures the
                  queue the bridge has NOT yet drained, which the join cannot
                  fake. QUEUE-FILLING (>= 0.200 s of backlog at t3) is consistent
                  with a real receive stall; QUEUE-DRAINING (< 0.200 s) says
                  datagrams were being consumed while the record claims a
                  multi-second wait. NO-RECVQ-RECORD if nothing covers t3.

  agreement       AGREE-ARTEFACT / AGREE-REAL / DISAGREE / UNCHECKED-RECVQ.
                  A stall counts as REAL for the PRODUCT and ENVIRONMENT classes
                  only on AGREE-REAL. DISAGREE is reported, never resolved here.

`concurrent_fresh_records` (records within +-250 ms of t3 whose own M_bridge is
under 100 ms) is reported as a third, instrument-internal signal. It is NOT part
of MASTER's rule and decides nothing on its own.
"""
import argparse, bisect, gzip, json, sys
from pathlib import Path

FRESH_WINDOW_NS = 250_000_000
FRESH_MS = 100.0
STALL_MS = 1000.0
RECVQ_FILLING_S = 0.200
TIMER_KINDS = ('macro_cc', 'relative_cc', 'staged_note_macro')


def load(p):
    b = Path(p).read_bytes()
    return json.loads(gzip.decompress(b) if b[:2] == b'\x1f\x8b' else b)


ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--result', required=True)
ap.add_argument('--armdir')
ap.add_argument('--recvq')
ap.add_argument('--preset')
ap.add_argument('--label', required=True)
ap.add_argument('--out', required=True)
a = ap.parse_args()

kinds = {}
if a.preset:
    sys.path.insert(0, '/Users/viddyslap/Documents/project-workspaces/steam-deck-midi/scripts/showready')
    from deck_script import effective, read_json           # the pinned helpers
    kinds = {k: v.get('type') for k, v in effective(read_json(Path(a.preset)), 'windows')['mappings'].items()}

res = load(a.result)
out = {'label': a.label, 'result_file': a.result, 'stall_threshold_ms': STALL_MS,
       'timer_capable_kinds': list(TIMER_KINDS), 'recvq_filling_threshold_s': RECVQ_FILLING_S,
       'mapping_types_loaded': len(kinds), 'arms': []}
for run in res.get('runs', []):
    arm = run.get('arm') or {}
    bs = arm.get('bridge_samples') or []
    t1 = arm.get('t1_pre_ns') or []
    if not bs or not t1:
        out['arms'].append({'repeat': run.get('repeat'), 'note': 'no raw bridge samples'})
        continue
    t1s = sorted(x for x in t1 if x is not None)
    actions = {}
    if a.armdir:
        cap = Path(a.armdir) / 'capture.jsonl'
        if cap.exists():
            for line in cap.read_text(encoding='ascii').splitlines():
                r = json.loads(line)
                if r.get('record') == 'midi' and r.get('perf_counter_ns') is not None:
                    actions[r['perf_counter_ns']] = {'action': r.get('action'), 'bytes': r.get('bytes')}
    anchor = None
    if a.armdir and (Path(a.armdir) / 'start').exists() and t1s:
        anchor = (Path(a.armdir) / 'start').stat().st_mtime - t1s[0] / 1e9
    q = []
    if a.recvq and Path(a.recvq).exists():
        q = sorted((json.loads(l) for l in Path(a.recvq).read_text().splitlines() if l.strip()),
                   key=lambda r: r['t'])
    qt = [r['t'] for r in q]

    stalls = []
    for s in bs:
        m = s.get('m_bridge_ms')
        if m is None or m <= STALL_MS:
            continue
        pre, t3 = s['t1_pre_ns'], s['t3_ns']
        info = actions.get(t3, {})
        action = info.get('action')
        kind = kinds.get(action)
        processed_between = sum(1 for o in bs if o['t3_ns'] <= t3 and o['t1_pre_ns'] > pre)
        row = {
            'm_bridge_ms': m, 'gap_seconds': (t3 - pre) / 1e9,
            'step': s.get('step'), 'cause_step': s.get('cause_step'),
            'cause_packet': s.get('cause_packet'), 'first_packet': s.get('first_packet'),
            'action': action, 'mapping_type': kind, 'midi_bytes': info.get('bytes'),
            'datagrams_sent_between': bisect.bisect_right(t1s, t3) - bisect.bisect_right(t1s, pre),
            'datagrams_processed_between': processed_between,
            'concurrent_fresh_records': sum(
                1 for o in bs if abs(o['t3_ns'] - t3) <= FRESH_WINDOW_NS
                and o.get('m_bridge_ms') is not None and o['m_bridge_ms'] < FRESH_MS),
            't3_ns': t3, 't1_pre_ns': pre}
        # --- MASTER 13 17:02 (1), from the instrument's own raw only ---
        row['timer_driven'] = bool(kind in TIMER_KINDS or
                                   (s.get('cause_step') is not None and s.get('step') != s.get('cause_step')))
        row['no_datagram_between'] = processed_between == 0
        row['verdict_17_02'] = ('INSTRUMENT-ARTEFACT'
                                if (row['timer_driven'] and row['no_datagram_between'])
                                else 'SURVIVES')
        # --- BESIDE it, from outside the bookkeeping: the arm's own Recv-Q ---
        row['recvq_backlog_s_at_t3'] = None
        row['recvq_bytes_at_t3'] = None
        if anchor is not None and qt:
            wall = anchor + t3 / 1e9
            i = bisect.bisect_left(qt, wall)
            near = [q[j] for j in (i - 1, i, i + 1) if 0 <= j < len(q) and abs(q[j]['t'] - wall) <= 1.0]
            if near:
                row['recvq_backlog_s_at_t3'] = max(x['backlog_s'] for x in near)
                row['recvq_bytes_at_t3'] = max(x['recvq_bytes'] for x in near)
                row['recvq_wall_time'] = wall
        if row['recvq_backlog_s_at_t3'] is None:
            row['verdict_recvq'] = 'NO-RECVQ-RECORD'
        elif row['recvq_backlog_s_at_t3'] >= RECVQ_FILLING_S:
            row['verdict_recvq'] = 'QUEUE-FILLING'
        else:
            row['verdict_recvq'] = 'QUEUE-DRAINING'
        artefact_17 = row['verdict_17_02'] == 'INSTRUMENT-ARTEFACT'
        if row['verdict_recvq'] == 'NO-RECVQ-RECORD':
            row['agreement'] = 'UNCHECKED-RECVQ'
        elif artefact_17 and row['verdict_recvq'] == 'QUEUE-DRAINING':
            row['agreement'] = 'AGREE-ARTEFACT'
        elif (not artefact_17) and row['verdict_recvq'] == 'QUEUE-FILLING':
            row['agreement'] = 'AGREE-REAL'
        else:
            row['agreement'] = 'DISAGREE'
        stalls.append(row)
    stalls.sort(key=lambda r: -r['m_bridge_ms'])
    counts = {}
    for key in ('verdict_17_02', 'verdict_recvq', 'agreement'):
        c = {}
        for r in stalls:
            c[r[key]] = c.get(r[key], 0) + 1
        counts[key] = c
    out['arms'].append({
        'repeat': run.get('repeat'), 'label': a.label, 'timed_messages': len(bs),
        'stall_samples_over_1s': len(stalls),
        'samples_over_100ms': sum(1 for s in bs if (s.get('m_bridge_ms') or 0) > 100),
        'max_m_bridge_ms': max((s['m_bridge_ms'] for s in bs if s.get('m_bridge_ms') is not None), default=None),
        'counts': counts,
        'survives_17_02': counts['verdict_17_02'].get('SURVIVES', 0),
        'agree_real': counts['agreement'].get('AGREE-REAL', 0),
        'disagree': counts['agreement'].get('DISAGREE', 0),
        'arm_has_a_real_stall': counts['agreement'].get('AGREE-REAL', 0) > 0,
        'worst_20_stalls': stalls[:20],
        'wall_anchor_epoch': anchor, 'recvq_records': len(q)})
Path(a.out).write_text(json.dumps(out, indent=1))
print(json.dumps({'label': a.label, 'arms': [
    {k: v[k] for k in ('repeat', 'stall_samples_over_1s', 'survives_17_02', 'agree_real',
                       'disagree', 'arm_has_a_real_stall', 'max_m_bridge_ms')}
    for v in out['arms'] if 'counts' in v]}))
