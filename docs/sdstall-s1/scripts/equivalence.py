"""Prove the CLOSED-only wrapper runs the SAME arm the pinned instrument runs.

  equivalence.py WRAPPER_RESULT.json.gz STOCK_RESULT.json.gz WRAPPER_SCRATCH STOCK_SCRATCH

Compares ONE CLOSED arm produced by docs/sdstall-s1/scripts/closed_only.py with
the CLOSED arm of a stock `timing_ab.py --repeats 1` run: the record FIELD SET of
the arm result, the field set of one bridge_sample, the files present in the arm
directory, and the load-guard shape. Values differ run to run (they are timings);
the FIELDS and the FILES must not. Exit 0 only if both sets match exactly.
"""
import gzip, json, sys
from pathlib import Path

def load(p):
    b = Path(p).read_bytes()
    return json.loads(gzip.decompress(b) if b[:2] == b'\x1f\x8b' else b)

wrap, stock = load(sys.argv[1]), load(sys.argv[2])
w = next(r for r in wrap['runs'] if r['name'] == 'CLOSED')
s = next(r for r in stock['runs'] if r['name'] == 'CLOSED')
out = {}
out['wrapper_drives'] = wrap['drives']
for tag, a, b in (('arm_result_fields', w['arm'], s['arm']),
                  ('guard_row_fields', w['attempts'][0], s['attempts'][0]),
                  ('load_before_fields', w['attempts'][0]['before'], s['attempts'][0]['before']),
                  ('bridge_sample_fields', w['arm']['bridge_samples'][0], s['arm']['bridge_samples'][0]),
                  ('sample_fields', w['arm']['samples'][0], s['arm']['samples'][0]),
                  ('coverage_fields', w['arm']['coverage'], s['arm']['coverage'])):
    wa, sa = sorted(a), sorted(b)
    out[tag] = {'equal': wa == sa, 'count': len(wa),
                'only_in_wrapper': [k for k in wa if k not in sa],
                'only_in_stock': [k for k in sa if k not in wa]}
wd = Path(sys.argv[3]); sd = Path(sys.argv[4])
wdir = next(next(p for p in wd.iterdir() if p.name.startswith('timing-')).glob('r*-CLOSED-try1'))
sdir = next(next(p for p in sd.iterdir() if p.name.startswith('timing-')).glob('r*-CLOSED-try1'))
wf, sf = sorted(p.name for p in wdir.iterdir()), sorted(p.name for p in sdir.iterdir())
out['arm_directory_files'] = {'equal': wf == sf, 'wrapper': wf, 'stock': sf}
out['arm_directories'] = {'wrapper': str(wdir), 'stock': str(sdir)}
out['values_for_the_record'] = {
    k: {'wrapper': w['arm'].get(k), 'stock': s['arm'].get(k)}
    for k in ('passed', 'timing_status', 'every_message_timing_status', 'timed_midi_messages',
              'every_message_timed_midi_messages', 'client_counts')}
out['load_status'] = {'wrapper': w['load_status'], 'stock': s['load_status']}
out['snapshot_clients'] = {'wrapper': [w['arm']['snapshot_before']['clients'], w['arm']['snapshot_after']['clients']],
                           'stock': [s['arm']['snapshot_before']['clients'], s['arm']['snapshot_after']['clients']]}
out['candidate'] = {'wrapper': wrap['candidate'], 'stock': stock['candidate']}
out['instrument_sha256_equal'] = wrap['instrument_sha256'] == stock['instrument_sha256']
out['script_sha256_equal'] = wrap['script_file_sha256'] == stock['script_file_sha256']
out['preset_sha256_equal'] = wrap['preset_sha256'] == stock['preset_sha256']
checks = [out[k]['equal'] for k in out if isinstance(out.get(k), dict) and 'equal' in out[k]]
checks += [out['instrument_sha256_equal'], out['script_sha256_equal'], out['preset_sha256_equal']]
out['result'] = 'EQUIVALENT' if all(checks) else 'NOT EQUIVALENT'
print(json.dumps(out, indent=1))
sys.exit(0 if out['result'] == 'EQUIVALENT' else 1)
