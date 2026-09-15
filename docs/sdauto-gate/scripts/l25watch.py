import json, subprocess, sys, time
sys.path.insert(0, '/tmp/sdauto-gate/s3')
import f5f2
from pathlib import Path
out = Path('/tmp/sdauto-gate/s3/l25watch'); out.mkdir(parents=True, exist_ok=True)
L = lambda: subprocess.run(['/tmp/sdauto-gate/s3/layer25'], capture_output=True, text=True).stdout.strip()
res = {'idle_before': L()}
for name in ('BASE', 'HEAD'):
    t = f5f2.tree(f5f2.REVS[name], Path('/tmp/sdauto-gate/s3/run'))
    p, log, base, meta = f5f2.spawn(t, out, f'{name}-l25')
    time.sleep(8)
    meta['layer25_running'] = L()
    meta.update(f5f2.finish(p, log))
    time.sleep(2)
    meta['layer25_after'] = L()
    res[name] = {k: meta[k] for k in ('pid', 'layer25_running', 'layer25_after', 'final_returncode', 'pid_gone')}
    print(json.dumps(res[name]), flush=True)
print('idle_before', res['idle_before'])
(out / 'l25watch.json').write_text(json.dumps(res, indent=2))
