"""Source bridge + second-process disk edit; scratch only, no live config writes."""
import json
import os
from pathlib import Path
import queue
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = Path('/tmp/sdcore-s3')
SCRATCH.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=SCRATCH, prefix='smoke-') as temp:
    root = Path(temp)
    config = {'sections':{'macbook':{'mappings':{'BTN_A':{'type':'note','channel':0,'note':36}}}}}
    base = root / 'windows_midi_map.json'
    base.write_text(json.dumps(config))
    (root / 'bridge.local.json').write_text('{"preset_section":"macbook"}')
    with socket.socket() as port_probe:
        port_probe.bind(('127.0.0.1',0))
        port = port_probe.getsockname()[1]
    child_code = '''
import sys, types
from windows import win_recv
win_recv._open_browser_delayed=lambda *_:None
sys.modules['windows.tray']=types.SimpleNamespace(ReceiverTray=lambda **kw:None)
raise SystemExit(win_recv.main(sys.argv[1:]))
'''
    log_path = SCRATCH / 'source-smoke.log'
    events = queue.Queue()
    proc = subprocess.Popen([sys.executable,'-u','-c',child_code,'--map',str(base),
        '--listen','127.0.0.1:0','--ui-port',str(port),'--dry-run','--no-engines',
        '--no-pulse','--no-osc-relay'],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    def read_output():
        with log_path.open('w') as log:
            for line in proc.stdout:
                log.write(line); log.flush()
                events.put((time.monotonic(),line.strip()))
    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    try:
        def get(path):
            with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}',timeout=0.3) as response:
                return json.load(response)
        deadline = time.monotonic()+8
        while True:
            try:
                version = get('/api/state-version'); break
            except Exception:
                if proc.poll() is not None or time.monotonic()>deadline:
                    raise RuntimeError('source boot failed; inspect '+str(log_path))
                time.sleep(0.025)
        active = Path(get('/api/settings')['map_path'])
        edit_code = '''
import json, pathlib, sys, time
p=pathlib.Path(sys.argv[1]); raw=json.loads(p.read_text())
raw['sections']['macbook']['mappings']['BTN_A']['note']=64
p.write_text(json.dumps(raw)); print(time.monotonic())
'''
        edit = subprocess.run([sys.executable,'-c',edit_code,str(active)],check=True,capture_output=True,text=True)
        written = float(edit.stdout)
        while True:
            received, line = events.get(timeout=2)
            if 'hot-reloaded mappings' in line:
                elapsed = received-written; break
        assert 0 <= elapsed < 1, elapsed
        assert get('/api/state-version') > version
        assert get('/api/mappings')['mappings']['BTN_A']['note'] == 64
        result = {'source_root':str(ROOT),'elapsed_seconds':round(elapsed,6),
                  'log_line':line,'state_version':get('/api/state-version'),
                  'note_returned':64,'second_process_exit':edit.returncode}
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGINT)
        proc.wait(timeout=5)
        reader.join(timeout=2)
        proc.stdout.close()
    result['child_exit'] = proc.returncode
    result['child_reaped'] = proc.poll() is not None
    (SCRATCH/'source-smoke.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
