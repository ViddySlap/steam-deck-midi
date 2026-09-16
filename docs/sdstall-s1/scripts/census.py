"""sdstall S1: the AUTHORITATIVE stall census, recomputed from the RAW files.

  census.py --session NAME --dir /tmp/sdstall/NAME [--session NAME2 --dir ...] --out FILE.json

Every number here comes from an arm's own raw result file (its `bridge_samples`,
M_bridge = t3 - t1_pre per message), never from the watch and never from a
summary line. The watch only decided WHERE to sample; it decides nothing here.

Per arm it reports:
  stalls_over_1s      M_bridge samples > 1,000 ms   (the DECLARED stall)
  samples_over_100ms  M_bridge samples > 100 ms     (the gate census threshold)
  max/p50/p95/p99 M_bridge, timed message count
  VALID or INVALID with the reason, from arm_validity.py's own JSON lines
  fine-sampled or UNSAMPLED, and the lms statuses the watch saw
"""
import argparse, glob, gzip, json, os, statistics, sys
from pathlib import Path


def load(p):
    b = Path(p).read_bytes()
    return json.loads(gzip.decompress(b) if b[:2] == b'\x1f\x8b' else b)


def pct(v, q):
    if not v:
        return None
    s = sorted(v)
    if len(s) == 1:
        return s[0]
    i = (len(s) - 1) * q
    lo, hi = int(i), min(int(i) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)


ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--session', action='append', required=True)
ap.add_argument('--dir', action='append', required=True)
ap.add_argument('--out', required=True)
a = ap.parse_args()

out = {'schema': 'sdstall-census/1', 'sessions': {},
       'stall_definition_ms': 1000, 'gate_census_threshold_ms': 100}
for name, d in zip(a.session, a.dir):
    d = Path(d)
    # arm_validity.py is run ONCE per revision at the end of a session (heavy
    # scans never run during an arm), so its rows arrive in validity-<rev>.txt
    # keyed by `repeat`, not in a per-arm file.
    # The Windows interleave has no Mac load sampler and the pinned instrument
    # records `not applicable` for pgrep/loadavg there (timing_ab.load_check,
    # os.name == 'nt'), so the EXTENDED LOAD VALIDITY cap cannot be evaluated for
    # those arms. For such a session VALID means what the instrument itself
    # accepted: the load guard accepted the attempt AND the arm passed.
    load_sampled = (d / 'samples.jsonl').exists()
    validity = {}
    for rev in ('base', 'head'):
        f = d / ('validity-%s.txt' % rev)
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            if line.startswith('{'):
                j = json.loads(line)
                validity[(rev, j['repeat'])] = j
    arms = []
    for res in sorted(glob.glob(str(d / '*.json.gz'))):
        label = Path(res).name[:-len('.json.gz')]
        try:
            r = load(res)
        except Exception as exc:
            arms.append({'label': label, 'error': 'unreadable result: %r' % exc}); continue
        rev = 'head' if label.endswith('-head') else 'base' if label.endswith('-base') else '?'
        for run in r.get('runs', []):
            arm = run.get('arm') or {}
            bs = arm.get('bridge_samples') or []
            m = [s['m_bridge_ms'] for s in bs if s.get('m_bridge_ms') is not None]
            row = {'label': label, 'session': name, 'revision': rev,
                   'order': int(label.split('-a')[1][:2]) if '-a' in label else None,
                   'candidate': r.get('candidate'),
                   'wall_start': run.get('wall_start'), 'wall_end': run.get('wall_end'),
                   'accepted': run.get('accepted'), 'arm_passed': arm.get('passed'),
                   'load_status': run.get('load_status'),
                   'complete_raw': bool(m), 'timed_messages': len(m),
                   'stalls_over_1s': sum(1 for x in m if x > 1000),
                   'samples_over_100ms': sum(1 for x in m if x > 100),
                   'max_m_bridge_ms': max(m) if m else None,
                   'p50_ms': pct(m, .50), 'p95_ms': pct(m, .95), 'p99_ms': pct(m, .99),
                   'arm_error': arm.get('error'), 'result_file': res}
            # MASTER 13, 17:09 STANDING RULE: report the presence of
            # .metadata_never_index for every scratch a timing arm used.
            wk = r.get('work')
            if wk:
                wkp = Path(wk)
                row['work_dir'] = wk
                row['scratch_dir'] = str(wkp.parent)
                row['never_index_work'] = (wkp / '.metadata_never_index').exists()
                row['never_index_scratch'] = (wkp.parent / '.metadata_never_index').exists()
                row['never_index'] = row['never_index_work'] and row['never_index_scratch']
            else:
                row['never_index'] = None
            # validity, from arm_validity.py's own JSON lines
            row['valid'] = None
            row['validity_file'] = str(d / ('validity-%s.txt' % rev))
            row['load_sampler'] = load_sampled
            if not load_sampled:
                row['valid'] = bool(run.get('accepted') and (arm.get('passed')))
                row['validity_note'] = ('no Mac load sampler for this host; the pinned instrument '
                                        'records load as `not applicable` on Windows, so the load1 '
                                        'cap and the hog clause are NOT CHECKABLE for this arm')
                row['max_load1'] = None
            j = validity.get((rev, run.get('repeat')))
            if j is not None:
                row.update(valid=j['valid'], max_load1=j['max_load1'],
                           load1_over_5=j['load1_over_5'], hogs=j['hogs_over_50pct_10s'],
                           arm_window=[j['start'], j['end']], validity_samples=j['samples'])
            else:
                v = d / (label + '.validity.txt')
                if v.exists():
                    for line in v.read_text().splitlines():
                        if line.startswith('{'):
                            k = json.loads(line)
                            row.update(valid=k['valid'], max_load1=k['max_load1'],
                                       load1_over_5=k['load1_over_5'], hogs=k['hogs_over_50pct_10s'],
                                       arm_window=[k['start'], k['end']], validity_samples=k['samples'])
            # the watch's own record (environment / lms / stacks), Mac only
            w = d / 'watch' / (label + '.watch.json')
            if w.exists():
                wj = json.loads(w.read_text())
                row['watch'] = {k: wj.get(k) for k in
                                ('max_recvq_bytes', 'max_backlog_s', 'episodes_over_200ms',
                                 'episodes_over_1s', 'max_record_silence_s', 'statuses_seen',
                                 'fine_statuses_seen', 'fine_samples', 'lms_polls',
                                 'processingprompt_fine', 'processingprompt_any', 'stacks',
                                 'sample_seconds', 'lms_seconds', 'recvq_unreadable')}
                row['fine_sampled'] = bool(wj.get('fine_samples'))
                row['inference_active'] = 'PROCESSINGPROMPT' in (wj.get('fine_statuses_seen') or [])
                row['inference_active_any_poll'] = bool(wj.get('processingprompt_any'))
                row['stacks_taken'] = wj.get('stacks', 0)
                sd = d / 'watch' / (label + '.stacks')
                row['stack_files'] = sorted(str(p) for p in sd.glob('*.txt')) if sd.exists() else []
                ef = d / 'watch' / (label + '.env.jsonl')
                if ef.exists():
                    env = [json.loads(l) for l in ef.read_text().splitlines() if l.strip()]
                    plain = [e for e in env if e.get('record') != 'lms']
                    dec = [e['vm_stat'].get('Decompressions') for e in plain if e.get('vm_stat')]
                    dec = [x for x in dec if x is not None]
                    deltas = [dec[i + 1] - dec[i] for i in range(len(dec) - 1)]
                    row['env'] = {
                        'records': len(env),
                        'max_load1': max((e['load1'] for e in plain if e.get('load1') is not None), default=None),
                        'pressure_levels': sorted({e['pressure_level'] for e in plain if e.get('pressure_level') is not None}),
                        'max_wired_pages': max((e['wired_pages'] for e in plain if e.get('wired_pages')), default=None),
                        'decompressions_peak_per_record': max(deltas, default=None),
                        'decompressions_total': (dec[-1] - dec[0]) if len(dec) > 1 else None,
                        'pageins_total': None}
                    pi = [e['vm_stat'].get('Pageins') for e in plain if e.get('vm_stat')]
                    pi = [x for x in pi if x is not None]
                    if len(pi) > 1:
                        row['env']['pageins_total'] = pi[-1] - pi[0]
                        row['env']['pageins_peak_per_record'] = max(
                            pi[i + 1] - pi[i] for i in range(len(pi) - 1))
            arms.append(row)
    arms.sort(key=lambda r: (r.get('order') or 0))
    ok = [r for r in arms if r.get('valid') and r.get('accepted') and r.get('arm_passed')]
    allc = [r for r in arms if r.get('complete_raw')]

    def tally(rows):
        t = {}
        for rev in ('base', 'head'):
            sub = [r for r in rows if r['revision'] == rev]
            t[rev] = {'arms': len(sub),
                      'arms_with_a_stall_over_1s': sum(1 for r in sub if r['stalls_over_1s'] > 0),
                      'arms_with_a_sample_over_100ms': sum(1 for r in sub if r['samples_over_100ms'] > 0),
                      'total_stall_samples': sum(r['stalls_over_1s'] for r in sub),
                      'max_m_bridge_ms': max((r['max_m_bridge_ms'] for r in sub if r['max_m_bridge_ms'] is not None), default=None),
                      'labels_with_a_stall': [r['label'] for r in sub if r['stalls_over_1s'] > 0]}
        t['product_count_pattern'] = (t['base']['arms_with_a_stall_over_1s'] == 0
                                      and t['head']['arms_with_a_stall_over_1s'] >= 2)
        t['r_per_revision_met'] = min(t['base']['arms'], t['head']['arms']) >= 8
        return t

    # inference split (MASTER 13 16:44 (4)): arms with ANY fine-grained
    # PROCESSINGPROMPT sample against arms with none, per revision.
    def split(rows):
        s = {}
        for rev in ('base', 'head'):
            for state in ('inference_active', 'inference_quiet'):
                sub = [r for r in rows if r['revision'] == rev and
                       bool(r.get('inference_active')) == (state == 'inference_active')]
                s['%s/%s' % (rev, state)] = {
                    'arms': len(sub),
                    'arms_with_a_stall_over_1s': sum(1 for r in sub if r['stalls_over_1s'] > 0),
                    'labels': [r['label'] for r in sub]}
        return s

    pairs = []
    by_order = sorted(arms, key=lambda r: (r.get('order') or 0))
    for i in range(len(by_order) - 1):
        x, y = by_order[i], by_order[i + 1]
        if x['revision'] == 'base' and y['revision'] == 'head':
            pairs.append({'pair': '%s + %s' % (x['label'], y['label']),
                          'base_stalled': x['stalls_over_1s'] > 0, 'base_valid': x.get('valid'),
                          'head_stalled': y['stalls_over_1s'] > 0, 'head_valid': y.get('valid'),
                          'base_max_ms': x['max_m_bridge_ms'], 'head_max_ms': y['max_m_bridge_ms']})
    scratches = {}
    for r in arms:
        if r.get('scratch_dir'):
            scratches[r['scratch_dir']] = {'never_index_scratch': r.get('never_index_scratch'),
                                           'never_index_work': r.get('never_index_work'),
                                           'work_dir': r.get('work_dir'),
                                           'arms': scratches.get(r['scratch_dir'], {}).get('arms', 0) + 1}
    out['sessions'][name] = {
        'dir': str(d), 'arms': arms,
        'scratch_never_index': scratches,
        'all_scratches_never_indexed': all(v['never_index_scratch'] and v['never_index_work']
                                           for v in scratches.values()) if scratches else None,
        'wall_start': min((r['wall_start'] for r in arms if r.get('wall_start')), default=None),
        'wall_end': max((r['wall_end'] for r in arms if r.get('wall_end')), default=None),
        'reading_VALID_only': tally(ok),
        'reading_ALL_complete_raw': tally(allc),
        'inference_split_VALID_only': split(ok),
        'inference_split_ALL': split(allc),
        'adjacent_pairs': pairs,
        'invalid_arms': [{'label': r['label'], 'revision': r['revision'], 'valid': r.get('valid'),
                          'accepted': r.get('accepted'), 'arm_passed': r.get('arm_passed'),
                          'load_status': r.get('load_status'), 'max_load1': r.get('max_load1'),
                          'load1_over_5': r.get('load1_over_5'), 'hogs': r.get('hogs'),
                          'arm_error': r.get('arm_error'), 'complete_raw': r.get('complete_raw'),
                          'stalls_over_1s': r.get('stalls_over_1s'),
                          'max_m_bridge_ms': r.get('max_m_bridge_ms')}
                         for r in arms if not (r.get('valid') and r.get('accepted') and r.get('arm_passed'))],
    }
Path(a.out).write_text(json.dumps(out, indent=1))
print('WROTE', a.out)
for name, s in out['sessions'].items():
    print('==', name, 'arms', len(s['arms']))
    for key in ('reading_VALID_only', 'reading_ALL_complete_raw'):
        t = s[key]
        print('  ', key, 'base', t['base']['arms'], 'arms', t['base']['arms_with_a_stall_over_1s'], 'stalled |',
              'head', t['head']['arms'], 'arms', t['head']['arms_with_a_stall_over_1s'], 'stalled | pattern',
              t['product_count_pattern'], '| R>=8', t['r_per_revision_met'])
