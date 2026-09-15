"""sdfix gate (beyond the acceptance rule): does any leader or arrowhead cross ANOTHER control's shape box,
or pass within 2 px (one stroke width) of another control's arrowhead? Page px from geom_gate.cjs JSON.
Shape boxes shrink by 1 px (inset) so a line merely grazing a neighbour's edge does not count.
Usage: leader_over_shapes.py geometry.json
"""
import json, math, sys
def orient(a, b, c): return (b['x'] - a['x']) * (c['y'] - a['y']) - (b['y'] - a['y']) * (c['x'] - a['x'])
def cross(p1, p2, p3, p4):
    d1, d2, d3, d4 = orient(p3, p4, p1), orient(p3, p4, p2), orient(p1, p2, p3), orient(p1, p2, p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))
def inside(p, r): return r['left'] < p['x'] < r['right'] and r['top'] < p['y'] < r['bottom']
def seg_rect(a, b, r):
    if inside(a, r) or inside(b, r): return True
    c = [{'x': r['left'], 'y': r['top']}, {'x': r['right'], 'y': r['top']}, {'x': r['right'], 'y': r['bottom']}, {'x': r['left'], 'y': r['bottom']}]
    return any(cross(a, b, c[i], c[(i + 1) % 4]) for i in range(4))
def pd(p, a, b):
    dx, dy = b['x'] - a['x'], b['y'] - a['y']; L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((p['x'] - a['x']) * dx + (p['y'] - a['y']) * dy) / L))
    return math.hypot(p['x'] - a['x'] - t * dx, p['y'] - a['y'] - t * dy)
total = 0
for r in json.load(open(sys.argv[1])):
    raw = r['raw']
    shapes = {s['id']: {'left': s['rect']['left'] + 1, 'top': s['rect']['top'] + 1, 'right': s['rect']['right'] - 1, 'bottom': s['rect']['bottom'] - 1} for s in raw['shapes']}
    heads = {h['id']: h['points'] for h in raw['heads']}
    over, graze = set(), set()
    for a in raw['arrows']:
        segs = list(zip(a['points'], a['points'][1:])) + ([(heads[a['id']][1], heads[a['id']][2])] if a['id'] in heads and len(heads[a['id']]) == 3 else [])
        for sid, box in shapes.items():
            if sid != a['id'] and any(seg_rect(p, q, box) for p, q in segs):
                over.add((a['id'], sid))
        for hid, tri in heads.items():
            if hid != a['id'] and any(pd(v, p, q) < 2 for v in tri for p, q in zip(a['points'], a['points'][1:])):
                graze.add((a['id'], hid))
    total += len(over) + len(graze)
    print(f"{r['viewport']} {r['state']} leader-over-other-shape={sorted(over)} line-within-2px-of-other-head={sorted(graze)}")
print('TOTAL', total)
