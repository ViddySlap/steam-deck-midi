"""Run the conflict browser proof on an existing wrapper-created scratch copy."""
from pathlib import Path
import json,os,signal,subprocess,sys,time,urllib.request
ROOT=Path(__file__).resolve().parents[2]
TREE=Path(sys.argv[1]).resolve()
assert str(TREE).startswith('/private/tmp/sdfix-u1/'),TREE
OUT=ROOT/'docs/sdfix-u1/evidence'
WORK=Path('/tmp/sdfix-u1/conflict-browser');WORK.mkdir(exist_ok=True)
# The wrapper left verified fixture copies and an isolated tracked tree.
assert (TREE/'config/presets/EDM Show.json').read_bytes()==(ROOT/'.showready/fixtures/mac/presets/EDM Show.json').read_bytes()
import socket
for port,kind in [(17841,socket.SOCK_STREAM),(47841,socket.SOCK_DGRAM)]:
    with socket.socket(socket.AF_INET,kind) as s:s.bind(('127.0.0.1',port))
env={**os.environ,'PYSTRAY_BACKEND':'dummy','BROWSER':'/usr/bin/true','TMPDIR':str(WORK),'PYTHONDONTWRITEBYTECODE':'1'}
argv=[str(ROOT/'.venv/bin/python'),'-B','-u','-m','windows.win_recv','--listen','127.0.0.1:47841','--map','config/windows_midi_map.json','--preset-section','windows','--dry-run','--no-engines','--no-pulse','--no-osc-relay','--ui-port','17841']
command=['node',str(ROOT/'docs/sdfix-u1/browser_conflicts.cjs'),'http://127.0.0.1:17841','/Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell',str(TREE),str(WORK)]
with (WORK/'bridge.log').open('w') as log:p=subprocess.Popen(argv,cwd=TREE,env=env,stdout=log,stderr=subprocess.STDOUT)
receipt={'argv':argv,'pid':p.pid,'command':command}
try:
    for _ in range(100):
        assert p.poll() is None,'bridge exited'
        try:
            with urllib.request.urlopen('http://127.0.0.1:17841/api/settings',timeout=.5) as r:receipt['settings']=json.load(r)
            break
        except OSError:time.sleep(.1)
    else:raise RuntimeError('bridge readiness timeout')
    result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=90)
    (OUT/'conflict-browser.log').write_text(result.stdout+result.stderr)
    print(result.stdout+result.stderr,end='')
    assert result.returncode==0,result.returncode
    import shutil
    shutil.copyfile(WORK/'conflict-browser.json',OUT/'conflict-browser.json')
    shutil.copyfile(WORK/'conflict-after-cancel.png',ROOT/'docs/sdfix-u1/screenshots/conflict-after-cancel.png')
finally:
    if p.poll() is None:p.send_signal(signal.SIGTERM)
    try:p.wait(timeout=15)
    except subprocess.TimeoutExpired:p.kill();p.wait(timeout=10)
    try:os.kill(p.pid,0)
    except ProcessLookupError:receipt['pid_gone']=True
    else:receipt['pid_gone']=False
    (OUT/'conflict-browser-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    assert receipt['pid_gone'],receipt
    print('PASS bridge PID gone',p.pid)
