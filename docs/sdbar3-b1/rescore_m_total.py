"""sdbar3 B1: M_total regression check of the UNCHANGED locked metric. Not a re-scoring of bar 3.

Feeds every row of EXISTING sdlive capture files through the NEW CaptureTiming.enrich
(t3 = recorder perf_counter_ns, t0 = the stored cause-step send stamp), then pools with the
NEW summarize() and compares p50/p95/p99/max/count to the values stored in the sdlive result.
  rescore_m_total.py RESULT.json.gz TIMING_DIR [--plant-1ns]
--plant-1ns is the negative control: t0 one nanosecond earlier must make it exit 1.
Exit 0 only if every per-message latency and every statistic is exactly equal.
"""
import gzip, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'scripts/showready'))
import timing_ab as timing
if '--plant-1ns' in sys.argv:
    original = timing.m_total_ms
    timing.m_total_ms = lambda t3, t0: original(t3, t0 - 1)

stored = json.load(gzip.open(sys.argv[1]))
work = Path(sys.argv[2])
script = stored['script']
runs, mismatched_messages, compared_messages = [], 0, 0
for item in stored['runs']:
    label = f"r{item['repeat']}-{item['name']}-try{len(item['attempts'])}"
    arm = item['arm']
    capture = timing.CaptureTiming({'mappings': {}}, script, {})
    capture.sent = {int(k): v for k, v in json.loads((work / label / 'timing.json').read_text())['sends'].items()}
    current = [None]
    capture.action = lambda: current[0]
    for line in (work / label / 'capture.jsonl').read_text(encoding='ascii').splitlines():
        old = json.loads(line)
        if old['record'] != 'midi':
            continue
        row = {k: old[k] for k in ('record', 'monotonic_ns', 'step', 'logical_ns', 'bytes')}
        current[0] = old['action']
        capture.origins = {old['action']: old['cause_step']}
        capture.enrich(row)
        compared_messages += 1
        mismatched_messages += row.get('latency_ms') != old['latency_ms']
    runs.append({**item, 'arm': {**arm, 'samples': capture.samples}})
new = timing.summarize(runs, script)
table, equal = [], mismatched_messages == 0 and not any(r['arm']['samples'] == [] for r in runs)
for old_row, new_row in zip(stored['summary']['rows'], new['rows']):
    same = old_row['statistics_ms'] == new_row['statistics_ms']
    equal &= same
    table.append({'repeat': new_row['repeat'], 'arm': new_row['arm'], 'equal': same,
                  **{k: new_row['statistics_ms'][k] for k in ('p50', 'p95', 'p99', 'count')}})
pooled_equal = stored['summary']['pooled_ms'] == new['pooled_ms'] and stored['summary']['rule'] == new['rule']
equal &= pooled_equal
print(json.dumps({'result': sys.argv[1], 'timing_dir': str(work), 'messages_compared': compared_messages,
                  'message_latency_mismatches': mismatched_messages, 'rows': table,
                  'pooled_stored': stored['summary']['pooled_ms'], 'pooled_new': new['pooled_ms'],
                  'pooled_and_rule_equal': pooled_equal, 'ALL_EQUAL': equal}, indent=1))
sys.exit(0 if equal else 1)
