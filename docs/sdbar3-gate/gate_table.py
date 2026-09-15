"""sdbar3 gate: M_bridge / M_post / M_total tables from a timing_ab --rule m_bridge result.

  gate_table.py RESULT.json.gz [--load-log /tmp/sdbar3-gate/load-samples.log] [--day 2026-09-15]

Independent of the instrument's summary: recomputes every per-arm and pooled
p50/p95/p99/max from the raw bridge_samples (m_bridge_ms, m_post_ms) and samples
(latency_ms = M_total), the worst-case segment from cause_step, the declared rule
(|OPEN-CLOSED| <= |CLOSED-CLOSED-B| + 1.0 ms at p50, p95 AND p99, every arm
every-message >= 1000), and compares each number with the instrument's own output.
Re-derives M_bridge = t3 - t1_pre from t1_pre_ns[cause_packet] for every message.
With --load-log (foreign_load.py lines prefixed HH:MM:SS.ns) reports the last sample
before each arm's start file and the max foreign_lines / load1 during the arm.
"""
import datetime, gzip, json, math, re, sys
from pathlib import Path

STATS = ('p50', 'p95', 'p99')
ARMS = ('CLOSED', 'OPEN', 'CLOSED-B')
METRICS = ('m_bridge_ms', 'm_post_ms', 'm_total_ms')


def pct(v, p):
    v = sorted(v)
    at = (len(v) - 1) * p / 100
    lo, hi = math.floor(at), math.ceil(at)
    return v[lo] + (v[hi] - v[lo]) * (at - lo)


def st(v):
    return {'p50': pct(v, 50), 'p95': pct(v, 95), 'p99': pct(v, 99), 'max': max(v), 'n': len(v)}


def rule(P, valid):
    floor = {k: abs(P['CLOSED'][k] - P['CLOSED-B'][k]) for k in STATS}
    delta = {k: abs(P['OPEN'][k] - P['CLOSED'][k]) for k in STATS}
    within = {k: delta[k] <= floor[k] + 1.0 for k in STATS}
    return {'noise_floor_ms': floor, 'open_delta_ms': delta, 'within': within,
            'floor_can_resolve_2ms': any(2.0 > floor[k] + 1.0 for k in STATS),
            'valid_arms': valid, 'within_all': all(within.values())}


def load_samples(path, day):
    out = []
    for line in open(path):
        m = re.match(r'(\d\d:\d\d:\d\d\.\d+) (\{.*\})', line)
        if m:
            t = datetime.datetime.strptime(day + ' ' + m.group(1)[:15], '%Y-%m-%d %H:%M:%S.%f').timestamp()
            out.append({'at': t, **json.loads(m.group(2))})
    return out


def main():
    path = sys.argv[1]
    raw = open(path, 'rb').read()
    d = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)
    day = sys.argv[sys.argv.index('--day') + 1] if '--day' in sys.argv else datetime.date.today().isoformat()
    samples = load_samples(sys.argv[sys.argv.index('--load-log') + 1], day) if '--load-log' in sys.argv else []
    steps = {s['id']: s for s in d['script']['steps']}
    seg = d['script'].get('worst_case_segment')
    pooled = {m: {a: [] for a in ARMS} for m in METRICS}
    worst = {m: {a: [] for a in ARMS} for m in METRICS}
    rows, mismatches, rederive_bad = [], [], 0
    inst_rows = {(r['repeat'], r['arm']): r for r in (d.get('m_bridge') or {}).get('rows', [])}
    for run in d['runs']:
        arm = run.get('arm') or {}
        joined = arm.get('bridge_samples', [])
        pre = arm.get('t1_pre_ns') or []
        for s in joined:
            if s['t1_pre_ns'] != pre[s['cause_packet']] or abs((s['t3_ns'] - pre[s['cause_packet']]) / 1e6 - s['m_bridge_ms']) > 1e-9:
                rederive_bad += 1
        vals = {'m_bridge_ms': [s['m_bridge_ms'] for s in joined], 'm_post_ms': [s['m_post_ms'] for s in joined],
                'm_total_ms': [s['latency_ms'] for s in arm.get('samples', [])]}
        wv = {'m_bridge_ms': [s['m_bridge_ms'] for s in joined if s['cause_step'] is not None and steps[s['cause_step']].get('segment') == seg],
              'm_post_ms': [s['m_post_ms'] for s in joined if s['cause_step'] is not None and steps[s['cause_step']].get('segment') == seg],
              'm_total_ms': [s['latency_ms'] for s in arm.get('samples', []) if steps[s['cause_step']].get('segment') == seg]}
        last = run['attempts'][-1]
        row = {'repeat': run['repeat'], 'arm': run['name'], 'attempts': len(run['attempts']), 'load_status': run['load_status'],
               'accepted': run['accepted'], 'passed': arm.get('passed'), 'error': arm.get('error'),
               'first_packet_join': len(arm.get('samples', [])), 'every_message': len(joined),
               'cause_first_packet': sum(bool(s['first_packet']) for s in joined), 'cause_later_packet': sum(not s['first_packet'] for s in joined),
               'midi_records': sum(r['record'] == 'midi' for r in arm.get('records', [])),
               'packets_sent_with_t1_pre': sum(x is not None for x in pre), 'packets_sent_with_t1_post': sum(x is not None for x in (arm.get('t1_post_ns') or [])),
               'publisher_dropped': (arm.get('snapshot_after') or {}).get('dropped'), 'stream_dropped': (arm.get('stream') or {}).get('dropped'),
               'stream_data_events': (arm.get('stream') or {}).get('data_events'),
               'client_counts_minmax': [min(arm['client_counts']), max(arm['client_counts'])] if arm.get('client_counts') else None,
               'browser_pids_gone': (arm.get('browser_cleanup') or {}).get('gone'), 'bridge_pid_gone': (arm.get('cleanup') or {}).get('pid_gone'),
               'pgrep_before': [a['before'].get('status') for a in run['attempts']], 'pgrep_after': [a['after'].get('status') for a in run['attempts']],
               'foreign_before': [(a['before'].get('foreign') or {}).get('foreign_lines') for a in run['attempts']],
               'foreign_after': [(a['after'].get('foreign') or {}).get('foreign_lines') for a in run['attempts']],
               'foreign_matched': [((a['before'].get('foreign') or {}).get('matched'), (a['after'].get('foreign') or {}).get('matched')) for a in run['attempts']],
               'load1_before': (last['before'].get('foreign') or {}).get('load1'), 'load1_after': (last['after'].get('foreign') or {}).get('load1')}
        if joined:
            row['stats'] = {m: st(v) for m, v in vals.items()}
            row['worst_stats'] = {m: st(v) for m, v in wv.items() if v}
            for m in METRICS:
                pooled[m][run['name']].extend(vals[m])
                worst[m][run['name']].extend(wv[m])
            ir = inst_rows.get((run['repeat'], run['name']))
            if ir:
                for m in METRICS:
                    for k in ('p50', 'p95', 'p99', 'max'):
                        if abs(ir['statistics_ms'][m][k] - row['stats'][m][k]) > 1e-9:
                            mismatches.append((run['repeat'], run['name'], m, k))
        if samples:
            start = Path(d.get('work', '')) / f"r{run['repeat']}-{run['name']}-try{len(run['attempts'])}" / 'start'
            result_file = start.parent / 'timing.json'
            if start.exists():
                t0 = start.stat().st_mtime
                t1 = result_file.stat().st_mtime if result_file.exists() else t0 + 80
                before = [s for s in samples if s['at'] <= t0]
                during = [s for s in samples if t0 <= s['at'] <= t1]
                row['sampler'] = {'foreign_lines_at_start': before[-1]['foreign_lines'] if before else None,
                                  'load1_at_start': before[-1]['load1'] if before else None,
                                  'sample_age_s': round(t0 - before[-1]['at'], 2) if before else None,
                                  'n_during': len(during),
                                  'foreign_lines_max_during': max((s['foreign_lines'] for s in during), default=None),
                                  'pgrep_nonempty_during': sum(s['pgrep_status'] != 'empty' for s in during),
                                  'load1_max_during': max((s['load1'] for s in during), default=None)}
        rows.append(row)
    out = {'result': path, 'result_sha256': __import__('hashlib').sha256(raw).hexdigest(), 'rule_flag': d.get('rule'),
           'control': d.get('control'), 'repeats': d.get('repeats'), 'candidate': d.get('candidate'),
           'instrument_timing_ab_sha256': (d.get('instrument_sha256') or {}).get('scripts/showready/timing_ab.py'),
           'client': d.get('client'), 'error': d.get('error'), 'passed': d.get('passed'),
           'measurement_qualified': d.get('measurement_qualified'), 'locked_rule_passed': d.get('locked_rule_passed'),
           'm_bridge_rule_passed': d.get('m_bridge_rule_passed'), 'sensitivity_timing_red': d.get('sensitivity_timing_red'),
           'm_bridge_sensitivity_timing_red': d.get('m_bridge_sensitivity_timing_red'), 'sensitivity_valid': d.get('sensitivity_valid'),
           'bar3_counts': d.get('bar3_counts'), 'byte_identical': (d.get('summary') or {}).get('byte_identical'),
           'wall_seconds': d.get('wall_seconds'), 'rederived_m_bridge_mismatches': rederive_bad,
           'per_arm_stat_mismatches_vs_instrument': mismatches, 'rows': rows}
    if all(pooled['m_bridge_ms'][a] for a in ARMS):
        valid = all(r['every_message'] >= 1000 for r in rows)
        P = {m: {a: st(v) for a, v in pooled[m].items()} for m in METRICS}
        W = {m: {a: st(v) for a, v in worst[m].items() if v} for m in METRICS}
        R = {m: rule(P[m], valid) for m in METRICS}
        RW = {m: rule(W[m], valid) for m in METRICS if len(W[m]) == 3}
        inst = d.get('m_bridge') or {}
        out.update(pooled=P, rules=R, worst_case_segment=seg, worst_pooled=W, worst_rules=RW,
                   pooled_matches_instrument_m_bridge=all(abs(P[m][a][k] - inst['pooled_ms'][m][a][k]) < 1e-9
                                                          for m in METRICS for a in ARMS for k in ('p50', 'p95', 'p99', 'max')) if inst else None,
                   locked_summary_pooled_matches=all(abs(P['m_total_ms'][a][k] - d['summary']['pooled_ms'][a][k]) < 1e-9
                                                     for a in ARMS for k in ('p50', 'p95', 'p99', 'max')) if d.get('summary') else None,
                   instrument_m_bridge_rule=inst.get('rule'), instrument_locked_rule=(d.get('summary') or {}).get('rule'),
                   instrument_m_post_rule=inst.get('diagnostic_m_post_rule'),
                   per_repeat_m_bridge=[{k: r[k] for k in ('repeat', 'within', 'passed')} for r in inst.get('per_repeat', [])])
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
