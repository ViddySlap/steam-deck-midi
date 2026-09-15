"""Boot a scratch-only UI bridge, run Chromium geometry, reap the exact PID."""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path('/Users/viddyslap/Documents/project-workspaces/steam-deck-midi')
sys.path.insert(0, str(ROOT / "scripts/showready"))
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--chromium', required=True)
p.add_argument('--scratch', required=True)
p.add_argument('--single-process', action='store_true')
p.add_argument('--revision', help='Optional Git revision for a before-repair control; default is tracked working bytes')
p.add_argument('--mutations', action='store_true')
p.add_argument('--ui-port', type=int, default=17841)
p.add_argument('--listen-port', type=int, default=47841)
a = p.parse_args()
scratch = Path(a.scratch).resolve()
if not str(scratch).startswith('/private/tmp/sdlive-') and not str(scratch).startswith('/tmp/sdlive-'):
    p.error('scratch must be under /tmp/sdlive-<link>/')
if a.ui_port in (7723, 45123) or a.listen_port in (7723,45123) or a.ui_port == a.listen_port:
    p.error('distinct, non-default ports required')
scratch.mkdir(parents=True, exist_ok=True)
work = Path(tempfile.mkdtemp(prefix='geometry-',dir=scratch))
tree = work / 'tree'
tree.mkdir()
# Copy tracked working bytes only. Local presets/config cannot enter the bridge.
files = subprocess.check_output(['git','-C',str(ROOT),'ls-files','-z','windows','protocol','config']).decode().split('\0')
for name in filter(None, files):
    source=ROOT/name
    if source.is_file():
        target=tree/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(subprocess.check_output(['git','-C',str(ROOT),'show',a.revision+':'+name])) if a.revision else shutil.copyfile(source,target)
# Verify the existing fixture manifests before copying any preset.
from deck_script import verify_fixtures
verify_fixtures(ROOT/'.showready/fixtures')
for source in (ROOT/'.showready/fixtures/mac/presets').glob('*.json'):
    shutil.copyfile(source,tree/'config/presets'/source.name)
preset = tree/'config/presets/EDM Show.json'
if not preset.is_file():
    raise RuntimeError('EDM Show fixture copy is required')
(tree/'config/presets/.active').write_text('EDM Show.json',encoding='ascii')
for port, kind in [(a.ui_port,socket.SOCK_STREAM),(a.listen_port,socket.SOCK_DGRAM)]:
    with socket.socket(socket.AF_INET,kind) as s:
        s.bind(('127.0.0.1',port))
        print(f'PASS free port {port}',flush=True)
env={**os.environ,'PYSTRAY_BACKEND':'dummy','BROWSER':'/usr/bin/true','TMPDIR':str(work),'PYTHONDONTWRITEBYTECODE':'1'}
argv=[sys.executable,'-B','-u','-m','windows.win_recv','--listen',f'127.0.0.1:{a.listen_port}','--map','config/windows_midi_map.json','--preset-section','windows','--dry-run','--no-engines','--no-pulse','--no-osc-relay','--ui-port',str(a.ui_port)]
checks=[]
bridge=None
exit_code=1
receipt={'work':str(work),'bridge_argv':argv,'checks':checks}
try:
    with (work/'bridge.log').open('w') as log:
        bridge=subprocess.Popen(argv,cwd=tree,env=env,stdout=log,stderr=subprocess.STDOUT)
    receipt['bridge_pid']=bridge.pid
    url=f'http://127.0.0.1:{a.ui_port}'
    for _ in range(100):
        if bridge.poll() is not None:raise RuntimeError('Bridge exited: '+(work/'bridge.log').read_text())
        try:
            with urllib.request.urlopen(url+'/api/settings',timeout=.5) as r: settings=json.load(r)
            break
        except OSError:time.sleep(.1)
    else:raise RuntimeError('Bridge readiness timeout')
    receipt['settings']=settings
    command=['node',str(ROOT/'tests/ui_controller_geometry.cjs'),url,a.chromium]
    if a.single_process:command+=['--single-process']
    def run(name, extra=()):
        cmd=command+['--out',str(work/name)]+list(extra)
        with (work/(name+'.log')).open('w') as log:
            result=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
        text=(work/(name+'.log')).read_text()
        print(text,end='',flush=True)
        checks.append({'name':name,'command':cmd,'exit':result.returncode,'log':str(work/(name+'.log'))})
        return result.returncode,text
    code,_=run('pristine')
    if code:raise RuntimeError('Pristine geometry failed; see '+str(work/'pristine.log'))
    if a.mutations:
        for name, tokens in [('m1',['FAIL 1440x900.closed.own-edge.btn_a','FAIL 1440x900.closed.own-edge.btn_b']),('m2',['FAIL 1440x900.closed.label-overlaps','btn_a','btn_b']),('m3',['FAIL 1440x900.closed.labels-topmost','btn_a'])]:
            code,text=run(name,['--mutation',name])
            if code!=1 or not all(t in text for t in tokens):raise RuntimeError('Mutation did not fail at its named assertion: '+name)
            code,_=run(name+'-restored')
            if code:raise RuntimeError('Restored geometry failed: '+name)
            print('PASS mutation RED and restored GREEN '+name,flush=True)
    exit_code=0
finally:
    if bridge:
        if bridge.poll() is None:bridge.send_signal(signal.SIGTERM)
        try:bridge.wait(timeout=15)
        except subprocess.TimeoutExpired:bridge.kill();bridge.wait(timeout=10)
        try:os.kill(bridge.pid,0)
        except ProcessLookupError:receipt['bridge_pid_gone']=True
        else:receipt['bridge_pid_gone']=False;exit_code=1
        print(f"{'PASS' if receipt['bridge_pid_gone'] else 'FAIL'} bridge PID {bridge.pid} gone={receipt['bridge_pid_gone']}",flush=True)
    receipt['exit']=exit_code
    (work/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('RECEIPT '+str(work/'receipt.json'),flush=True)
sys.exit(exit_code)
