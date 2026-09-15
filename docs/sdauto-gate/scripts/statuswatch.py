import json, os, signal, socket, subprocess, sys, time
sys.path.insert(0, '/tmp/sdauto-gate/s3')
import f5f2
from pathlib import Path
out = Path('/tmp/sdauto-gate/s3/statuswatch'); out.mkdir(parents=True, exist_ok=True)
res = {}
for name in ('BASE', 'HEAD'):
    t = f5f2.tree(f5f2.REVS[name], Path('/tmp/sdauto-gate/s3/run'))
    p, log, base, meta = f5f2.spawn(t, out, f'{name}-watch')
    rows = []
    t0 = time.time()
    for at in (1, 3, 6, 10, 15, 20):
        while time.time() - t0 < at: time.sleep(0.1)
        rows.append({'at_s': at, **f5f2.windows_of(p.pid)})
    meta['watch'] = rows
    meta.update(f5f2.finish(p, log))
    res[name] = meta
    print(name, [(r['at_s'], r['pid_windows'], r['status_layer_25']) for r in rows], 'final', meta['final_returncode'], 'gone', meta['pid_gone'], flush=True)
(out / 'statuswatch.json').write_text(json.dumps(res, indent=2))
