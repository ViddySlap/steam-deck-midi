"""sdlive gate step 7: independent raw check of ab_run results (does not trust 'passed').

For every result: arm A must be v0.4.9 (e66ff44), every other arm the candidate; each
arm received exactly the script's packet count with the script's stream digest and was
proved gone; (step, bytes) MIDI rows of every candidate arm equal arm A's, nonempty;
every mapping with inputs in the script has mapping-directed (step >= 0) MIDI in A.
  bar1_verify.py CANDIDATE RESULT.json[.gz]...   -> one JSON line per result, exit 0 if all pass
"""
import gzip, json, sys
cand = sys.argv[1]
ok = True
for f in sys.argv[2:]:
    raw = open(f, 'rb').read()
    d = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)
    npk = len(d['script']['packets']) if isinstance(d.get('script'), dict) and 'packets' in d['script'] else None
    rows, good = {}, True
    base = None
    for name, arm in d['arms'].items():
        midi = [(r['step'], tuple(r['bytes'])) for r in arm['records'] if r.get('record') == 'midi']
        mapped = [m for m in midi if m[0] >= 0]
        want = 'e66ff44b36eadb6d43db01680c65279df82cd63c' if name == 'A' else cand
        row = {'commit_ok': arm['commit'] == want, 'packets': arm['received']['packets_received'],
               'packets_ok': arm['received']['packets_received'] == (npk or arm['received']['packets_received']) and arm['received']['packet_stream_sha256'] == d['packet_stream_sha256'],
               'pid_gone': arm['cleanup']['pid_gone'], 'midi': len(midi), 'mapped_midi': len(mapped)}
        if name == 'A':
            base = midi
        else:
            row['identical_to_A'] = midi == base and bool(base)
            if not row['identical_to_A']:
                row['first_diff'] = next((i for i, (x, y) in enumerate(zip(midi, base)) if x != y), min(len(midi), len(base)))
        good &= row['commit_ok'] and row['packets_ok'] and row['pid_gone'] and row['midi'] > 0 and row.get('identical_to_A', True)
        rows[name] = row
    unex = sorted({u for c in d['comparisons'].values() for u in c['unexercised_mappings']})
    diff = sorted({u for c in d['comparisons'].values() for u in c['different_mappings']})
    good &= not unex and not diff and d['control'] is None
    ok &= good
    print(json.dumps({'result': f, 'preset': d['preset'], 'section': d['section'], 'script_sha256': d['script_sha256'],
                      'packets_scripted': npk, 'arms': rows, 'instrument_unexercised': unex, 'instrument_different': diff,
                      'instrument_passed': d['passed'], 'independent_passed': good}))
sys.exit(0 if ok else 1)
