"""Collect E2 evidence and assert scope, original assertions and exact PID cleanup."""
import collections
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = Path('/tmp/sdlive-e2')
OUT = ROOT / 'docs/sdlive-e2/evidence'
OUT.mkdir(parents=True, exist_ok=True)
BASE = '95d3da0a740911e0677a549b75bee648a198b2cc'

def copy_text(source, target):
    text = source.read_text()
    text = re.sub(r'\x1b\[[0-9;]*m', '', text)
    target.write_text(text, encoding='ascii', errors='backslashreplace')

for name in ['mac-suite-complete', 'geometry', 'geometry-complete', 'browser', 'browser-complete',
             'controller-initial', 'group-order-red', 'mutations-complete',
             'ui_controller_check', 'ui_controller_macro_check', 'ui_reload_check', 'ui_sections_check']:
    copy_text(SCRATCH / (name + '.log'), OUT / (name + '.log'))
shutil.copyfile(SCRATCH / 'node-results.json', OUT / 'node-results.json')
for kind in ['geometry', 'geometry-complete', 'browser', 'browser-complete']:
    works = list((SCRATCH / kind).glob('geometry-*'))
    assert len(works) == 1, (kind, works)
    work = works[0]
    shutil.copyfile(work/'receipt.json', OUT/(kind+'-receipt.json'))
    copy_text(work/'pristine.log', OUT/(kind+'-detector.log'))
    if kind.endswith('-complete'):
        result = 'geometry.json' if kind.startswith('geometry') else 'browser-results.json'
        shutil.copyfile(work/'pristine'/result, OUT/result)
        if kind.startswith('browser'):
            for source in (work/'pristine').glob('*.png'):
                shutil.copyfile(source, OUT/source.name)
mutations = list((SCRATCH / 'mutations-complete').glob('proof-*'))
assert len(mutations) == 1
shutil.copyfile(mutations[0]/'results.json', OUT/'mutation-results.json')
for source in mutations[0].glob('*.log'):
    copy_text(source, OUT/('mutation-'+source.name))

# Protect source and pins, not just test return codes.
protected = ['windows/receiver.py', 'windows/live_events.py', 'windows/win_recv.py',
             'windows/midi.py', 'windows/config.py', 'scripts/showready',
             'tests/ui_controller_geometry.cjs', 'config', 'deck', 'protocol', 'mac',
             'tests/ui_reload_check.cjs', 'tests/ui_sections_check.cjs']
assert not subprocess.check_output(['git','-C',str(ROOT),'diff',BASE,'--',*protected])
assertions = {}
for name in ['tests/ui_controller_check.cjs', 'tests/test_controller_map.py']:
    old = subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':'+name]).decode()
    before = collections.Counter(line.strip() for line in old.splitlines() if 'assert.' in line or 'self.assert' in line)
    after = collections.Counter(line.strip() for line in (ROOT/name).read_text().splitlines())
    assert not before-after, (name, before-after)
    assertions[name] = sum(before.values())
owned = ['windows/static/controller/controller_live.js', 'windows/static/controller/controller_view.js',
         'windows/static/controller/controller_map.json', 'windows/static/controller/controller_view.css',
         'windows/static/controller/steam_deck.svg', 'windows/static/index.html',
         'tests/ui_controller_check.cjs', 'tests/test_controller_map.py', 'docs/api.md']
actual = subprocess.check_output(['git','-C',str(ROOT),'diff',BASE,'--name-only']).decode().splitlines()
assert all(name in owned or name.startswith('docs/sdlive-e2/') for name in actual), actual
processes = []
for receipt in sorted(SCRATCH.glob('*/geometry-*/receipt.json')):
    record = json.loads(receipt.read_text())
    pid = record['bridge_pid']
    assert record['bridge_pid_gone']
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        pass
    else:
        raise AssertionError(('bridge PID still exists', pid))
    processes.append({'pid':pid, 'absent':True, 'receipt':str(receipt), 'method':'os.kill(pid, 0) -> ProcessLookupError'})
assert processes
scope = {'entry_head':BASE, 'protected_unchanged':protected,
         'preserved_assertion_lines':assertions, 'bridge_cleanup':processes,
         'sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in owned}}
(OUT/'scope.json').write_text(json.dumps(scope,indent=2)+'\n')
print(json.dumps({'protected_unchanged':True,'preserved_assertion_lines':assertions,
                  'bridge_pids_absent':[p['pid'] for p in processes]},indent=2))
