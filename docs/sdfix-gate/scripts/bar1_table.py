"""sdfix gate: recompute bar 1 A/B identity from the RAW midi records of ab_run results.
Usage: bar1_table.py HOST result.json[.gz] ...  -> one JSON line per candidate arm.
digest = sha256 of json.dumps([[step, bytes], ...]) over midi records (startup step -1 included).
"""
import gzip, hashlib, json, os, sys

host = sys.argv[1]
for path in sys.argv[2:]:
    d = json.load(gzip.open(path)) if path.endswith('.gz') else json.load(open(path))
    seq = {name: [[r['step'], r['bytes']] for r in arm['records'] if r.get('record') == 'midi'] for name, arm in d['arms'].items()}
    dig = {name: hashlib.sha256(json.dumps(s).encode()).hexdigest()[:12] for name, s in seq.items()}
    for name in [n for n in d['arms'] if n != 'A']:
        c = d['comparisons'][name]
        maps = c['mappings']
        print(json.dumps({'host': host, 'name': os.path.basename(path).split('.json')[0], 'arm': name,
            'steps': len(d['script']['steps']) if isinstance(d.get('script'), dict) and 'steps' in d['script'] else None,
            'exercised': sum(1 for m in maps if m['exercised']), 'total': len(maps),
            'mA': len(seq['A']), 'mB': len(seq[name]), 'summary_identical': c['identical'], 'raw_equal': seq['A'] == seq[name],
            'different': c['different_mappings'], 'unexercised': [m['mapping'] for m in maps if not m['exercised']],
            'passed': d['passed'], 'candidate': d['arms'][name]['commit'][:7], 'A': d['arms']['A']['commit'][:7],
            'digest_A': dig['A'], 'digest_B': dig[name], 'sent': d['sent_packet_stream_sha256'][:12],
            'received_equal_sent': all(a['received']['packet_stream_sha256'] == d['sent_packet_stream_sha256'] for a in d['arms'].values()),
            'no_overspeed': all(v['no_overspeed'] for arm in d['pacing'].values() for v in arm.values()),
            'pids_gone': all(a['cleanup']['pid_gone'] for a in d['arms'].values()),
            'wall': round(d['replay_wall_seconds'], 1), 'clock': d.get('timestamp_clock', {}).get('implementation') if isinstance(d.get('timestamp_clock'), dict) else d.get('timestamp_clock')}))
