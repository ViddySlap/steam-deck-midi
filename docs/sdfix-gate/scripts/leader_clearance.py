"""sdfix gate: closest approach (page px) between leaders of DIFFERENT controls, per state.
Leaders are stroked 2 px wide (controller_view.css .controller-arrow), so centre lines closer than 2 px
paint as touching even when they do not intersect. Usage: leader_clearance.py geometry-after.json
"""
import json, math, sys
def pd(p, a, b):
    dx, dy = b['x'] - a['x'], b['y'] - a['y']; L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((p['x'] - a['x']) * dx + (p['y'] - a['y']) * dy) / L))
    return math.hypot(p['x'] - a['x'] - t * dx, p['y'] - a['y'] - t * dy)
def sd(a, b, c, d): return min(pd(a, c, d), pd(b, c, d), pd(c, a, b), pd(d, a, b))
for r in json.load(open(sys.argv[1])):
    segs = [(ar['id'], ar['points'][k], ar['points'][k + 1]) for ar in r['raw']['arrows'] for k in range(len(ar['points']) - 1)]
    best = []
    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            if segs[i][0] != segs[j][0]:
                best.append((sd(segs[i][1], segs[i][2], segs[j][1], segs[j][2]), segs[i][0], segs[j][0]))
    best.sort()
    under = sorted({(round(d, 2), a, b) for d, a, b in best if d < 4})
    print(f"{r['viewport']} {r['state']} min={best[0][0]:.2f}px {best[0][1]}/{best[0][2]} pairs_under_4px={under}")
