"""sdlive gate 3a: independent subset check of the pinned timing script.

Re-derives the set of (kind, action, state-or-value) tuples from the decoded
wire packets of the pinned full deck script, then requires every decoded
timing-script packet AND step event to be a member. Heartbeats compare by kind.
Also counts the worst-case segment's events per tick. Exit 0 subset, 1 not.
  subset_gate.py TIMING DECK [--plant-foreign OUT.json]
"""
import collections, json, sys
from pathlib import Path

def tuple_of(ev):
    kind = ev.get('kind')
    extra = sorted(k for k in ev if k not in ('kind', 'action', 'state', 'value', 'seq'))
    return (kind, ev.get('action'), ev.get('state'), ev.get('value'), tuple(extra))

timing = json.loads(Path(sys.argv[1]).read_text())
deck = json.loads(Path(sys.argv[2]).read_text())
if '--plant-foreign' in sys.argv:
    # Replace the first L_STICK_X_AXIS packet and its step with a value absent from the deck script.
    deck_values = {json.loads(bytes.fromhex(p['hex'])).get('value') for p in deck['packets']}
    foreign = 12347
    assert foreign not in deck_values
    for p in timing['packets']:
        ev = json.loads(bytes.fromhex(p['hex']))
        if ev.get('action') == 'L_STICK_X_AXIS':
            ev['value'] = foreign
            p['hex'] = json.dumps(ev, sort_keys=True, separators=(',', ':')).encode().hex()
            for s in timing['steps']:
                if s['id'] == p['step']:
                    s['event']['value'] = foreign
            break
allowed = {tuple_of(json.loads(bytes.fromhex(p['hex']))) for p in deck['packets']}
bad = []
kinds = collections.Counter()
for p in timing['packets']:
    t = tuple_of(json.loads(bytes.fromhex(p['hex'])))
    kinds[t[0]] += 1
    if t not in allowed:
        bad.append(('packet', p['step'], t))
for s in timing['steps']:
    t = tuple_of(s['event'])
    if t not in allowed:
        bad.append(('step', s['id'], t))
seg = timing.get('worst_case_segment')
ticks = collections.defaultdict(list)
seg_start = min(s['at_ns'] for s in timing['steps'] if s.get('segment') == seg)
for s in timing['steps']:
    if s.get('segment') == seg:
        ticks[round((s['at_ns'] - seg_start) / 16666667)].append(s['event']['action'])  # 1 ns ordering offsets collapse per tick
per_tick = collections.Counter(len(v) for v in ticks.values())
axes_per_tick = collections.Counter(tuple(sorted(v)) for v in ticks.values())
out = {'timing_packets': len(timing['packets']), 'timing_steps': len(timing['steps']), 'deck_packets': len(deck['packets']),
       'distinct_deck_tuples': len(allowed), 'kinds': dict(kinds), 'foreign': bad[:5], 'foreign_count': len(bad),
       'worst_segment': seg, 'worst_ticks': len(ticks), 'events_per_tick_histogram': dict(per_tick),
       'axis_sets_per_tick': {', '.join(k): v for k, v in axes_per_tick.items()}}
print(json.dumps(out, indent=1))
sys.exit(0 if not bad and timing['packets'] and timing['steps'] else 1)
