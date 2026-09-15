"""sdlive gate: bar 3 table from a timing_ab result (recomputes pooled statistics from raw samples).

  timing_table.py RESULT.json.gz [--load-samples SAMPLES.jsonl]
Recomputes pooled p50/p95/p99/max from every arm's raw latency_ms samples (and the
worst-case segment from cause_step), compares with the instrument's summary, applies the
locked rule (|OPEN-CLOSED| <= |CLOSED-CLOSED-B| + 1.0 ms for p50/p95/p99), and lists each
arm's load checks. With --load-samples (foreign_load.py JSON lines stamped with 'at'),
reports the last sample before each arm's replay start ('start' file mtime) and the
maximum foreign_lines during the arm.
"""
import gzip, json, math, os, sys
from pathlib import Path

def pct(v, p):
    v = sorted(v); at = (len(v) - 1) * p / 100; lo, hi = math.floor(at), math.ceil(at)
    return v[lo] + (v[hi] - v[lo]) * (at - lo)

def st(v):
    return {'p50': pct(v, 50), 'p95': pct(v, 95), 'p99': pct(v, 99), 'max': max(v), 'n': len(v)}

path = sys.argv[1]
raw = open(path, 'rb').read()
d = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)
samples = []
if '--load-samples' in sys.argv:
    samples = [json.loads(l) for l in open(sys.argv[sys.argv.index('--load-samples') + 1]) if l.strip()]
steps = {s['id']: s for s in d['script']['steps']}
seg = d['script'].get('worst_case_segment')
pooled, worst, rows = {}, {}, []
for run in d['runs']:
    arm = run.get('arm') or {}
    vals = [s['latency_ms'] for s in arm.get('samples', [])]
    wv = [s['latency_ms'] for s in arm.get('samples', []) if steps[s['cause_step']].get('segment') == seg]
    pooled.setdefault(run['name'], []).extend(vals)
    worst.setdefault(run['name'], []).extend(wv)
    row = {'repeat': run['repeat'], 'arm': run['name'], 'load_status': run['load_status'], 'accepted': run['accepted'],
           'passed': arm.get('passed'), 'timed_midi': len(vals), 'worst_n': len(wv),
           'load_before': [a['before'].get('status') for a in run['attempts']], 'load_after': [a['after'].get('status') for a in run['attempts']],
           'loadavg_before': [a['before'].get('load_average') for a in run['attempts']],
           'publisher_dropped': (arm.get('snapshot_after') or {}).get('dropped'), 'stream_dropped': (arm.get('stream') or {}).get('dropped'),
           'client_counts_minmax': [min(arm['client_counts']), max(arm['client_counts'])] if arm.get('client_counts') else None,
           'data_events': (arm.get('stream') or {}).get('data_events'), 'error': arm.get('error')}
    if vals:
        row['stats'] = st(vals)
    work = Path(d.get('work', ''))
    start = work / f"r{run['repeat']}-{run['name']}-try{len(run['attempts'])}" / 'start'
    result_file = start.parent / 'timing.json'
    if samples and start.exists():
        t0 = start.stat().st_mtime; t1 = result_file.stat().st_mtime if result_file.exists() else t0 + 80
        before = [s for s in samples if s['at'] <= t0]
        during = [s for s in samples if t0 <= s['at'] <= t1]
        row['foreign_lines_at_start'] = before[-1]['foreign_lines'] if before else None
        row['load1_at_start'] = before[-1]['load1'] if before else None
        row['sample_age_s'] = round(t0 - before[-1]['at'], 2) if before else None
        row['foreign_lines_max_during'] = max((s['foreign_lines'] for s in during), default=None)
    rows.append(row)
out = {'result': path, 'control': d.get('control'), 'repeats': d.get('repeats'), 'client': d.get('client'), 'host': d.get('host', {}).get('platform'),
       'error': d.get('error'), 'passed': d.get('passed'), 'measurement_qualified': d.get('measurement_qualified'),
       'sensitivity_timing_red': d.get('sensitivity_timing_red'), 'sensitivity_valid': d.get('sensitivity_valid'), 'bar3_counts': d.get('bar3_counts'),
       'wall_seconds': d.get('wall_seconds'), 'rows': rows}
if all(pooled.get(k) for k in ('CLOSED', 'OPEN', 'CLOSED-B')):
    P = {k: st(v) for k, v in pooled.items()}
    W = {k: st(v) for k, v in worst.items() if v}
    floor = {k: abs(P['CLOSED'][k] - P['CLOSED-B'][k]) for k in ('p50', 'p95', 'p99')}
    delta = {k: abs(P['OPEN'][k] - P['CLOSED'][k]) for k in ('p50', 'p95', 'p99')}
    out.update(pooled=P, worst_case_pooled=W, noise_floor=floor, open_delta=delta,
               within={k: delta[k] <= floor[k] + 1.0 for k in floor},
               recomputed_matches_instrument=all(abs(P[a][k] - d['summary']['pooled_ms'][a][k]) < 1e-9 for a in P for k in ('p50', 'p95', 'p99', 'max')) if d.get('summary') else None,
               instrument_rule=(d.get('summary') or {}).get('rule'), per_repeat=[{k: r[k] for k in ('repeat', 'within', 'passed')} for r in (d.get('summary') or {}).get('per_repeat', [])],
               top_outliers=[{k: o.get(k) for k in ('latency_ms', 'repeat', 'arm', 'cause_step', 'action', 'bytes')} for o in (d.get('summary') or {}).get('top_five_outliers', [])])
print(json.dumps(out, indent=1))
