"""sdstall S1: render the census + artefact JSON into the report's markdown tables.

  report_tables.py --census FILE.json [--classify GLOB] --out FILE.md

Reads ONLY the JSON the other scripts wrote from raw files. Prints values, not
interpretations: every cell is a number or a name that came out of a raw file.
"""
import argparse, glob, json, time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('--census', required=True)
ap.add_argument('--classify', default=None)
ap.add_argument('--out', required=True)
a = ap.parse_args()
c = json.loads(Path(a.census).read_text())
cls = {}
if a.classify:
    for f in sorted(glob.glob(a.classify)):
        j = json.loads(Path(f).read_text())
        cls[j['label']] = j

L = []
def w(s=''): L.append(s)

def hms(t):
    return time.strftime('%H:%M:%S', time.localtime(t)) if t else '-'

def fmt(x, n=1):
    return '-' if x is None else ('%.*f' % (n, x))

# session table
w('### Session table')
w()
w('| Session | Arms | Wall start | Wall end | Minutes |')
w('| --- | --- | --- | --- | --- |')
starts = {}
for name, s in c['sessions'].items():
    starts[name] = s['wall_start']
    mins = (s['wall_end'] - s['wall_start']) / 60 if s['wall_start'] and s['wall_end'] else None
    w('| %s | %d | %s | %s | %s |' % (name, len(s['arms']), hms(s['wall_start']), hms(s['wall_end']), fmt(mins)))
w()
ks = [k for k in starts if starts[k]]
if len(ks) >= 2:
    ks.sort(key=lambda k: starts[k])
    w('Gap between the START of %s and the START of %s: **%.1f minutes**.' % (
        ks[0], ks[1], (starts[ks[1]] - starts[ks[0]]) / 60))
    w()

for name, s in c['sessions'].items():
    w('### Arm table - %s' % name)
    w()
    w('| # | Label | Rev | Start | End | Valid | .metadata_never_index | max load1 | stalls >1s | samples >100ms | max M_bridge ms | p95 ms | Recv-Q max backlog s | fine-sampled | lms STATUS seen | stacks |')
    w('| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |')
    for r in s['arms']:
        wt = r.get('watch') or {}
        valid = 'VALID' if (r.get('valid') and r.get('accepted') and r.get('arm_passed')) else 'INVALID'
        reason = ''
        if valid == 'INVALID':
            if r.get('load1_over_5'):
                reason = ' (load1>5 x%d)' % len(r['load1_over_5'])
            elif r.get('hogs'):
                reason = ' (hog)'
            elif not r.get('accepted'):
                reason = ' (%s)' % r.get('load_status')
            elif not r.get('arm_passed'):
                reason = ' (arm not passed)'
        ni = r.get('never_index')
        if r.get('load_sampler') is False:
            ni = 'n/a (Windows)'
        else:
            ni = 'present' if ni else ('MISSING' if ni is False else '-')
        w('| %s | %s | %s | %s | %s | %s%s | %s | %s | %d | %d | %s | %s | %s | %s | %s | %s |' % (
            r.get('order'), r['label'], r['revision'], hms(r.get('wall_start')), hms(r.get('wall_end')),
            valid, reason, ni, fmt(r.get('max_load1'), 2), r.get('stalls_over_1s', 0),
            r.get('samples_over_100ms', 0), fmt(r.get('max_m_bridge_ms'), 1), fmt(r.get('p95_ms'), 3),
            fmt(wt.get('max_backlog_s'), 3),
            'yes' if r.get('fine_sampled') else ('UNSAMPLED' if wt else 'n/a'),
            ','.join(wt.get('statuses_seen') or []) or '-', r.get('stacks_taken', 0)))
    w()
    sc = s.get('scratch_never_index') or {}
    if sc:
        w('Scratch directories used by this session, and the MASTER 13 17:09 standing-rule flag file:')
        w()
        w('| Scratch | Work dir | Arms | .metadata_never_index in scratch | in work dir |')
        w('| --- | --- | --- | --- | --- |')
        for k, v in sorted(sc.items()):
            is_win = not (s['arms'] and s['arms'][0].get('load_sampler', True))
            col_scr = ('n/a (Windows host; Spotlight is macOS only and this path is not checkable from the Mac)'
                       if is_win else v['never_index_scratch'])
            col_wrk = 'n/a' if is_win else v['never_index_work']
            w('| %s | %s | %d | %s | %s |' % (k, v['work_dir'], v['arms'], col_scr, col_wrk))
        w()
    w('### Adjacent-pair table - %s' % name)
    w()
    w('| BASE + HEAD pair | BASE stalled | BASE valid | HEAD stalled | HEAD valid | BASE max ms | HEAD max ms |')
    w('| --- | --- | --- | --- | --- | --- | --- |')
    for p in s['adjacent_pairs']:
        w('| %s | %s | %s | %s | %s | %s | %s |' % (
            p['pair'], 'YES' if p['base_stalled'] else 'no', p['base_valid'],
            'YES' if p['head_stalled'] else 'no', p['head_valid'],
            fmt(p['base_max_ms'], 1), fmt(p['head_max_ms'], 1)))
    w()
    w('### Totals - %s, BOTH readings' % name)
    w()
    w('| Reading | Rev | Arms | Arms with a stall >1s | Arms with a sample >100ms | Total stall samples | max M_bridge ms | R>=8 |')
    w('| --- | --- | --- | --- | --- | --- | --- | --- |')
    for key, lbl in (('reading_VALID_only', 'VALID only'), ('reading_ALL_complete_raw', 'ALL complete raw')):
        t = s[key]
        for rev in ('base', 'head'):
            w('| %s | %s | %d | %d | %d | %d | %s | %s |' % (
                lbl, rev.upper(), t[rev]['arms'], t[rev]['arms_with_a_stall_over_1s'],
                t[rev]['arms_with_a_sample_over_100ms'], t[rev]['total_stall_samples'],
                fmt(t[rev]['max_m_bridge_ms'], 1), t['r_per_revision_met']))
        w('| %s | count pattern (0 BASE, >=2 HEAD) | **%s** | | | | | |' % (lbl, t['product_count_pattern']))
    w()
    w('### Stall rates split by inference state - %s (MASTER 13, 16:44 (4))' % name)
    w()
    w('| Reading | Revision / state | Arms | Arms with a stall >1s | Labels |')
    w('| --- | --- | --- | --- | --- |')
    for key, lbl in (('inference_split_VALID_only', 'VALID only'), ('inference_split_ALL', 'ALL')):
        for k, v in s[key].items():
            w('| %s | %s | %d | %d | %s |' % (lbl, k, v['arms'], v['arms_with_a_stall_over_1s'],
                                              ', '.join(v['labels']) or '-'))
    w()
    inv = s['invalid_arms']
    w('### INVALID / not-counted arms - %s (raw files KEPT, entered in the ALL reading)' % name)
    w()
    if not inv:
        w('None: every arm in this session was VALID.')
    else:
        w('| Label | Rev | valid | accepted | arm passed | load_status | max load1 | load1>5 samples | hogs | complete raw | stalls >1s | max M_bridge ms |')
        w('| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |')
        for r in inv:
            w('| %s | %s | %s | %s | %s | %s | %s | %d | %s | %s | %s | %s |' % (
                r['label'], r['revision'], r.get('valid'), r.get('accepted'), r.get('arm_passed'),
                r.get('load_status'), fmt(r.get('max_load1'), 2), len(r.get('load1_over_5') or []),
                len(r.get('hogs') or []), r.get('complete_raw'), r.get('stalls_over_1s'),
                fmt(r.get('max_m_bridge_ms'), 1)))
    w()
    w('### Environment summary per arm - %s' % name)
    w()
    w('| Label | max load1 | pressure levels | max wired pages | decompressions total | peak per 1 s record | pageins total | lms polls | fine lms samples | PROCESSINGPROMPT (fine / any) |')
    w('| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |')
    for r in s['arms']:
        e = r.get('env') or {}
        wt = r.get('watch') or {}
        w('| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s / %s |' % (
            r['label'], fmt(e.get('max_load1'), 2),
            ','.join(str(x) for x in (e.get('pressure_levels') or [])) or '-',
            e.get('max_wired_pages', '-'), e.get('decompressions_total', '-'),
            e.get('decompressions_peak_per_record', '-'), e.get('pageins_total', '-'),
            wt.get('lms_polls', '-'), wt.get('fine_samples', '-'),
            wt.get('processingprompt_fine', '-'), wt.get('processingprompt_any', '-')))
    w()

if cls:
    w('### Stall samples, classified against MASTER 13 17:02 (1) FIRST')
    w()
    w('MASTER 13 17:02 (1) decides first, from the instrument raw alone. The Recv-Q column sits BESIDE it (MASTER 13, 17:09), never instead of it.')
    w()
    w('| Arm | M_bridge ms | action | mapping type | timer-driven | no datagram between | sent between | processed between | fresh +-250 ms | verdict 17:02 | Recv-Q backlog at t3 (s) | verdict Recv-Q | agreement |')
    w('| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |')
    any_row = False
    for label in sorted(cls):
        for armrow in cls[label]['arms']:
            for r in armrow.get('worst_20_stalls', []):
                any_row = True
                w('| %s | %.1f | %s | %s | %s | %s | %d | %d | %d | %s | %s | %s | %s |' % (
                    label, r['m_bridge_ms'], r.get('action') or '-', r.get('mapping_type') or '-',
                    r.get('timer_driven'), r.get('no_datagram_between'),
                    r['datagrams_sent_between'], r['datagrams_processed_between'],
                    r['concurrent_fresh_records'], r['verdict_17_02'],
                    fmt(r.get('recvq_backlog_s_at_t3'), 3), r['verdict_recvq'], r['agreement']))
    if not any_row:
        w('| - | - | - | - | - | - | - | - | - | - | - | - | NO STALL SAMPLE OVER 1,000 ms IN ANY ARM |')
    w()
    surv = sum(x.get('survives_17_02', 0) for j in cls.values() for x in j['arms'] if 'survives_17_02' in x)
    real = sum(x.get('agree_real', 0) for j in cls.values() for x in j['arms'] if 'agree_real' in x)
    dis = sum(x.get('disagree', 0) for j in cls.values() for x in j['arms'] if 'disagree' in x)
    tot = sum(x.get('stall_samples_over_1s', 0) for j in cls.values() for x in j['arms'] if 'stall_samples_over_1s' in x)
    w('Stall samples over 1,000 ms across every arm classified: **%d**. Surviving MASTER 17:02 (1): **%d**. '
      'AGREE-REAL (17:02 survived AND the queue was filling): **%d**. DISAGREE: **%d**.' % (tot, surv, real, dis))
    w()

Path(a.out).write_text('\n'.join(L) + '\n')
print('WROTE', a.out, len(L), 'lines')
