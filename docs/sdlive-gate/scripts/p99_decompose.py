"""sdlive gate: where does an OPEN-vs-CLOSED percentile shift live? Diagnostic only.

For every timed MIDI message: latency = sender part + receiver part, where
  sender part   = sent[last event step at or before the emitting step] - sent[cause_step]
  receiver part = emit time - sent[that step]
and sender pacing drift per event step = (sent[step] - sent[first step]) - (at_ns[step] - at_ns[first step]).
Reports pooled p50/p95/p99 of latency and of each part per arm, restricted to all messages and
to messages at or above each arm's own p95 latency. Uses the pinned result JSON only.
  p99_decompose.py RESULT.json.gz
"""
import gzip, json, math, sys
def pct(v, p):
    v = sorted(v); at = (len(v) - 1) * p / 100; lo, hi = math.floor(at), math.ceil(at)
    return v[lo] + (v[hi] - v[lo]) * (at - lo)
d = json.load(gzip.open(sys.argv[1]))
steps = {s['id']: s for s in d['script']['steps']}
order = sorted(steps)
agg = {}
for run in d['runs']:
    arm = run['arm']
    sent = {int(k): v for k, v in arm['sends'].items()}
    ev = sorted(sent)
    first = ev[0]
    drift = {s: (sent[s] - sent[first]) - (steps[s]['at_ns'] - steps[first]['at_ns']) for s in ev}
    import bisect
    a = agg.setdefault(run['name'], {'lat': [], 'snd': [], 'rcv': [], 'hi_snd': [], 'hi_rcv': [], 'drift_end_ms': [], 'hi_lat': []})
    lat = [m['latency_ms'] for m in arm['samples']]
    p95 = pct(lat, 95)
    for m in arm['samples']:
        i = bisect.bisect_right(ev, m['step']) - 1
        base = ev[i]
        snd = (sent[base] - sent[m['cause_step']]) / 1e6
        rcv = (m['perf_counter_ns'] - sent[base]) / 1e6
        a['lat'].append(m['latency_ms']); a['snd'].append(snd); a['rcv'].append(rcv)
        if m['latency_ms'] >= p95:
            a['hi_lat'].append(m['latency_ms']); a['hi_snd'].append(snd); a['hi_rcv'].append(rcv)
    a['drift_end_ms'].append(drift[ev[-1]] / 1e6)
out = {}
for name, a in agg.items():
    out[name] = {k: {p: round(pct(a[k], p), 3) for p in (50, 95, 99)} for k in ('lat', 'snd', 'rcv')}
    out[name]['top5pct_mean_ms'] = {k: round(sum(a[k]) / len(a[k]), 3) for k in ('hi_lat', 'hi_snd', 'hi_rcv')}
    out[name]['sender_drift_at_last_event_ms_per_repeat'] = [round(x, 3) for x in a['drift_end_ms']]
print(json.dumps(out, indent=1))
