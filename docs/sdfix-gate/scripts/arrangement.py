"""sdfix gate: is the physical arrangement of the 23 data-control shapes unchanged from BASE OF LAP?
Reads geom_gate.cjs JSON (1440x900 closed) for BEFORE and AFTER. For each shape box relative to the
SVG art root (svg.controller-art getBoundingClientRect), fits ONE uniform scale s = art width AFTER/BEFORE
and compares every box edge after dividing by s. Also compares getBBox() in SVG user units (must be equal).
Usage: arrangement.py before.json after.json
"""
import json, sys
def load(p):
    r = [x for x in json.load(open(p)) if x['viewport'] == '1440x900' and x['state'] == 'closed'][0]['raw']
    art = r['artRect']
    rel = {s['id']: [s['rect']['left'] - art['left'], s['rect']['top'] - art['top'], s['rect']['width'], s['rect']['height']] for s in r['shapes']}
    return art, rel, {s['id']: s['bbox'] for s in r['shapes']}
ab, rb, bb = load(sys.argv[1]); aa, ra, ba = load(sys.argv[2])
sx, sy = aa['width'] / ab['width'], aa['height'] / ab['height']
worst = 0; rows = []
for cid in sorted(rb):
    dev = max(abs(ra[cid][i] / sx - rb[cid][i]) for i in range(4))
    worst = max(worst, dev); rows.append((cid, round(dev, 4), bb[cid] == ba[cid]))
print(json.dumps({'count_before': len(rb), 'count_after': len(ra), 'same_ids': sorted(rb) == sorted(ra),
    'art_before': [ab['width'], ab['height']], 'art_after': [aa['width'], aa['height']], 'scale_x': sx, 'scale_y': sy,
    'uniform_scale': abs(sx - sy) < 1e-3, 'max_edge_deviation_px_in_before_units': worst,
    'getBBox_user_units_equal_all': all(r[2] for r in rows), 'rows': rows}, indent=1))
ok = len(rb) == len(ra) == 23 and sorted(rb) == sorted(ra) and abs(sx - sy) < 1e-3 and worst <= 1.0 and all(r[2] for r in rows)
print('ARRANGEMENT', 'UNCHANGED' if ok else 'CHANGED'); sys.exit(0 if ok else 1)
