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

ROOT = Path(__file__).resolve().parents[2]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--chromium', required=True)
p.add_argument('--scratch', required=True)
p.add_argument('--single-process', action='store_true')
p.add_argument('--revision', help='Optional Git revision for a before-repair control; default is tracked working bytes')
p.add_argument('--mutations', action='store_true')
p.add_argument('--only-mutation', help='Run one named mutation (m1..m6); the default is all six')
p.add_argument('--pristine-may-fail', action='store_true', help='Record a RED pristine run instead of aborting; a mutation is still only proven where its own assertion passed pristine')
p.add_argument('--ui-port', type=int, default=17841)
p.add_argument('--listen-port', type=int, default=47841)
a = p.parse_args()
from deck_script import scratch_ok, verify_fixtures
scratch = Path(a.scratch).resolve()
if not scratch_ok(scratch):
    p.error('scratch must be under /tmp/sd<lap>-<link>/')
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

def _map_patch(edit):
    def patch(raw):
        document=json.loads(raw.decode('utf-8'))
        by_id={control['id']:control for control in document['controls']}
        edit(by_id)
        return (json.dumps(document,indent=2,ensure_ascii=True)+'\n').encode('utf-8')
    return patch


def _m4(by_id):
    # Route dpad_up's leader straight through the L2 trigger track (L2 anchor 210,50;
    # its live track is the 64x8 rect at x-32,y+4). Criterion b must see it.
    by_id['dpad_up']['leader_via']=[[210,58]]


def _m5(by_id):
    # dpad_right's waypoint drops three scene pixels toward left_pad's horizontal leg.
    # A NEAR MISS on purpose: measured 4.63 px at 1920x1080 against the 6 px floor, with
    # leader-intersections still GREEN, so criterion c is the only thing that can catch it.
    by_id['dpad_right']['leader_via']=[[240,393]]


def _m6(raw):
    # Push the card header down only for controls that own an analog group - r2 does,
    # btn_a and dpad_up do not - so the 1024x768 drawer clips the title, tabs and rows.
    return raw+b'\n#controllerCard:has(.controller-group[data-group="analog"]) .controller-card-header { margin-top: 260px; }\n'


FILE_MUTATIONS=[
    # (name, served file, patch, extra check args, assertion, planted markers, must-be-unchanged)
    ('m4','controller_map.json',_map_patch(_m4),('--only-viewport','1440x900','--closed-only'),
     '1440x900.closed.b.no-leader-through-other-control',
     ('{"leader":"dpad_up","part":"segment","hits":"l2.track"}',),()),
    ('m5','controller_map.json',_map_patch(_m5),('--only-viewport','1920x1080','--closed-only'),
     '1920x1080.closed.c.leader-clearance-6px',(),()),
    ('m6','controller_view.css',_m6,('--only-viewport','1024x768',),
     '1024x768.open-r2.d.drawer-rows-visible',('!"scrollTop":0',),
     ('1024x768.open-btn_a.d.drawer-rows-visible',)),
]
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
            result=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
        text=(work/(name+'.log')).read_text()
        print(text,end='',flush=True)
        checks.append({'name':name,'command':cmd,'exit':result.returncode,'log':str(work/(name+'.log'))})
        return result.returncode,text
    code,text=run('pristine')
    def lines_of(text):
        found={}
        for line in text.splitlines():
            parts=line.split(' ',2)
            if len(parts)>=2 and parts[0] in ('PASS','FAIL'):found[parts[1]]=line
        return found
    pristine=lines_of(text)
    receipt['pristine_failures']=sorted(name for name,line in pristine.items() if line.startswith('FAIL'))
    print(f"PRISTINE {sum(1 for l in pristine.values() if l.startswith('PASS'))}/{len(pristine)} PASS failures={len(receipt['pristine_failures'])}",flush=True)
    if code and not a.pristine_may_fail:raise RuntimeError('Pristine geometry failed; see '+str(work/'pristine.log'))
    def proven(name,assertion,text,markers=(),unchanged=()):
        """A mutation is proven by what it CHANGED in its own assertion's line.

        A boolean flip (PASS pristine -> FAIL mutated) is the strong case. Where an
        assertion is ALREADY RED on today's picture, a flip is unavailable and proves
        nothing, so the mutation must instead put a planted marker into that assertion's
        detail that the pristine detail does not contain - and the restored run must
        return the line to the pristine line byte for byte. Named assertions listed in
        `unchanged` must be identical to pristine, which is how selectivity is shown.
        """
        mutated=lines_of(text)
        line=mutated.get(assertion)
        if line is None:raise RuntimeError(f'{name}: assertion {assertion} was not reported at all')
        if not line.startswith('FAIL'):raise RuntimeError(f'{name}: assertion {assertion} did not go RED')
        was=pristine.get(assertion)
        if was is None:raise RuntimeError(f'{name}: assertion {assertion} has no pristine line to compare against')
        if was.startswith('FAIL') and not markers:
            raise RuntimeError(f'{name}: assertion {assertion} was already RED pristine and no marker was declared, so its RED proves nothing')
        for marker in markers:
            # A leading '!' inverts the marker: it must be in the PRISTINE line and gone
            # from the mutated one, which is how a fault that REMOVES a good property
            # (a drawer that no longer sits at scrollTop 0) is pinned down.
            if marker.startswith('!'):
                gone=marker[1:]
                if gone not in was:raise RuntimeError(f'{name}: inverted marker {gone!r} was not in the PRISTINE {assertion} line')
                if gone in line:raise RuntimeError(f'{name}: inverted marker {gone!r} is still in the mutated {assertion} line')
                continue
            if marker not in line:raise RuntimeError(f'{name}: marker {marker!r} absent from the mutated {assertion} line')
            if marker in was:raise RuntimeError(f'{name}: marker {marker!r} is already in the PRISTINE {assertion} line, so it is not this mutation')
        for other in unchanged:
            if mutated.get(other)!=pristine.get(other):raise RuntimeError(f'{name}: assertion {other} was expected unchanged\n  pristine {pristine.get(other)}\n  mutated  {mutated.get(other)}')
        return {'assertion':assertion,'pristine':was,'mutated':line,'markers':list(markers),'unchanged':list(unchanged)}
    def restored(name,assertion,text):
        line=lines_of(text).get(assertion)
        if line!=pristine.get(assertion):raise RuntimeError(f'{name}: restored line is not the pristine line\n  pristine {pristine.get(assertion)}\n  restored {line}')
    if a.mutations:
        receipt['mutations']=[]
        # m1-m3 are planted in the live DOM by the check itself. m4-m6 are planted in the
        # SERVED STATIC FILES of the scratch tree, so the fault reaches the browser the way
        # a real layout regression would, and the original bytes are restored after each.
        for name, assertion, tokens in [x for x in [
                ('m1','1440x900.closed.own-edge.btn_a',['FAIL 1440x900.closed.own-edge.btn_a','FAIL 1440x900.closed.own-edge.btn_b']),
                ('m2','1440x900.closed.label-overlaps',['FAIL 1440x900.closed.label-overlaps','btn_a','btn_b']),
                ('m3','1440x900.closed.labels-topmost',['FAIL 1440x900.closed.labels-topmost','btn_a'])] if not a.only_mutation or x[0]==a.only_mutation]:
            code,text=run(name,['--mutation',name])
            receipt['mutations'].append(proven(name,assertion,text))
            if code!=1 or not all(token in text for token in tokens):raise RuntimeError('Mutation did not fail at its named assertion: '+name)
            code,text=run(name+'-restored',['--only-viewport','1440x900','--closed-only'])
            restored(name,assertion,text)
            print('PASS mutation RED and restored to the pristine line '+name,flush=True)
        static=tree/'windows/static/controller'
        for name, target, patch, extra, assertion, markers, unchanged in [x for x in FILE_MUTATIONS if not a.only_mutation or x[0]==a.only_mutation]:
            file=static/target
            saved=file.read_bytes()
            try:
                file.write_bytes(patch(saved))
                code,text=run(name,extra)
                receipt['mutations'].append(proven(name,assertion,text,markers,unchanged))
                if code!=1:raise RuntimeError('Mutation did not fail: '+name+' exit='+str(code))
            finally:
                file.write_bytes(saved)
            if file.read_bytes()!=saved:raise RuntimeError('Restore did not return the original bytes: '+name)
            code,text=run(name+'-restored',extra)
            restored(name,assertion,text)
            print('PASS mutation RED and restored to the pristine line '+name,flush=True)
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
