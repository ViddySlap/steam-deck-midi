"""sdbar3 B1: print the diagnostic run's M_bridge / M_post / M_total tables and t1 coverage. Diagnostic only.
  diagnostic_table.py RESULT.json.gz
"""
import gzip, json, sys
d = json.load(gzip.open(sys.argv[1]))
print('rule', d['rule'], 'repeats', d['repeats'], 'client', d['client'], 'qualified', d.get('measurement_qualified'),
      'locked_rule_passed', d.get('locked_rule_passed'), 'm_bridge_rule_passed', d.get('m_bridge_rule_passed'), 'error', d.get('error'))
for run in d['runs']:
    arm = run['arm']
    pre, post, packets = arm['t1_pre_ns'], arm['t1_post_ns'], d['script']['packets']
    joined = arm['bridge_samples']
    stamps = all(type(s['t1_pre_ns']) is int and type(s['t1_post_ns']) is int for s in joined)
    load = [(a['before']['status'], a['before'].get('foreign', {}).get('foreign_lines'), a['before'].get('foreign', {}).get('load1'),
             a['after']['status'], a['after'].get('foreign', {}).get('foreign_lines')) for a in run['attempts']]
    print(f"{run['name']}: load {run['load_status']} attempts(before status, foreign_lines, load1, after status, foreign_lines)={load}")
    print(f"  packets {len(packets)} t1_pre recorded {sum(type(v) is int for v in pre)} t1_post recorded {sum(type(v) is int for v in post)}; "
          f"every timed message has both stamps: {stamps}; min(t1_post - t1_pre) {min(b - a for a, b in zip(pre, post))} ns max {max(b - a for a, b in zip(pre, post))} ns")
rows = d['m_bridge']['rows']
print('| Arm | first_packet_join | every_message | cause first packet | cause later packet | status |')
for r in rows:
    c = r['counts']
    print(f"| {r['arm']} | {c['first_packet_join']} | {c['every_message']} | {c['every_message_cause_first_packet']} | {c['every_message_cause_later_packet']} | {r['every_message_timing_status']} |")
print('| Metric | Arm | p50 | p95 | p99 | max | n |')
for metric in ('m_bridge_ms', 'm_post_ms', 'm_total_ms'):
    for name, s in d['m_bridge']['pooled_ms'][metric].items():
        print(f"| {metric} | {name} | {s['p50']:.3f} | {s['p95']:.3f} | {s['p99']:.3f} | {s['max']:.3f} | {s['count']} |")
for metric in ('m_bridge_ms', 'm_post_ms', 'm_total_ms'):
    for name, s in d['m_bridge']['worst_case']['pooled_ms'][metric].items():
        print(f"| worst-case {metric} | {name} | {s['p50']:.3f} | {s['p95']:.3f} | {s['p99']:.3f} | {s['max']:.3f} | {s['count']} |")
for key, rule in (('locked (M_total)', d['summary']['rule']), ('m_bridge', d['m_bridge']['rule'])):
    print(key, 'floor', {k: round(v, 3) for k, v in rule['noise_floor_ms'].items()},
          'delta', {k: round(v, 3) for k, v in rule['open_delta_ms'].items()}, 'within', rule['within'], 'passed', rule['passed'])
