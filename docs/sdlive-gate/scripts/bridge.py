"""sdlive gate: boot or stop ONE scratch UI bridge from `git archive <rev>`.

  bridge.py start --tree DIR --rev SHA --ui-port P --listen-port L
  bridge.py stop  --tree DIR
The tree is a full `git archive <rev>`; config/presets gets byte copies of the
verified Mac fixtures (EDM Show active, sectioned, --preset-section windows) and
no bridge.local.json. Env PYSTRAY_BACKEND=dummy BROWSER=/usr/bin/true; argv
--dry-run --no-engines --no-pulse --no-osc-relay; loopback ports checked free.
stop sends SIGTERM, waits, and proves absence with os.kill(pid, 0).
"""
import argparse, json, os, shutil, signal, socket, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT = Path('/Users/viddyslap/Documents/project-workspaces/steam-deck-midi')
sys.path.insert(0, str(ROOT / 'scripts/showready'))
p = argparse.ArgumentParser()
p.add_argument('cmd', choices=['start', 'stop'])
p.add_argument('--tree', required=True)
p.add_argument('--rev')
p.add_argument('--ui-port', type=int)
p.add_argument('--listen-port', type=int)
p.add_argument('--mutate-js', choices=['c', 'd'], help='step 6 real-browser control: c EventSource stays open when hidden, d Follow default ON')
a = p.parse_args()
tree = Path(a.tree)
if not str(tree.resolve()).startswith(('/private/tmp/sdlive-gate/', '/tmp/sdlive-gate/')):
    sys.exit('tree must be under /tmp/sdlive-gate/')
pidfile = tree / 'bridge.pid'

if a.cmd == 'stop':
    pid = int(pidfile.read_text())
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    for _ in range(150):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            print(f'STOP pid={pid} gone=True (os.kill(pid,0) ProcessLookupError)')
            sys.exit(0)
        time.sleep(0.1)
    print(f'STOP pid={pid} gone=False after SIGTERM+15s')
    sys.exit(1)

assert a.rev and a.ui_port and a.listen_port
assert a.ui_port not in (7723, 45123) and a.listen_port not in (7723, 45123) and a.ui_port != a.listen_port
if tree.exists():
    sys.exit(f'tree exists: {tree}')
tree.mkdir(parents=True)
archive = subprocess.run(['git', '-C', str(ROOT), 'archive', a.rev], check=True, capture_output=True).stdout
subprocess.run(['tar', '-x', '-C', str(tree)], input=archive, check=True)
from deck_script import verify_fixtures
verify_fixtures(ROOT / '.showready/fixtures')
for name in os.listdir(tree / 'config/presets'):
    if name.endswith('.json') and name != 'default.json':
        (tree / 'config/presets' / name).unlink()
for name in ['EDM Show.json', 'PTZ.json', 'default.json']:
    shutil.copyfile(ROOT / '.showready/fixtures/mac/presets' / name, tree / 'config/presets' / name)
(tree / 'config/presets/.active').write_text('EDM Show.json', encoding='ascii')
assert not (tree / 'config/bridge.local.json').exists()
if a.mutate_js:
    js = tree / 'windows/static/controller/controller_live.js'
    text = js.read_text()
    needle, repl = {'c': ("      } else {\n        disconnect();\n", "      } else {\n"),
                    'd': ("follow = localStorage.getItem(FOLLOW_KEY) === 'true';", "follow = localStorage.getItem(FOLLOW_KEY) !== 'false';")}[a.mutate_js]
    assert text.count(needle) == 1
    js.write_text(text.replace(needle, repl))
    print('MUTATED', a.mutate_js)
for port, kind in [(a.ui_port, socket.SOCK_STREAM), (a.listen_port, socket.SOCK_DGRAM)]:
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind(('127.0.0.1', port))
print(f'PORTS free tcp {a.ui_port} udp {a.listen_port}')
env = {**os.environ, 'PYSTRAY_BACKEND': 'dummy', 'BROWSER': '/usr/bin/true', 'TMPDIR': str(tree), 'PYTHONDONTWRITEBYTECODE': '1'}
argv = [str(ROOT / '.venv/bin/python'), '-B', '-u', '-m', 'windows.win_recv', '--listen', f'127.0.0.1:{a.listen_port}',
        '--map', 'config/windows_midi_map.json', '--preset-section', 'windows', '--dry-run', '--no-engines',
        '--no-pulse', '--no-osc-relay', '--ui-port', str(a.ui_port)]
log = open(tree / 'bridge.log', 'w')
proc = subprocess.Popen(argv, cwd=tree, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
pidfile.write_text(str(proc.pid))
(tree / 'bridge.argv.json').write_text(json.dumps({'argv': argv, 'cwd': str(tree), 'rev': a.rev,
    'env': {k: env[k] for k in ('PYSTRAY_BACKEND', 'BROWSER', 'TMPDIR')}}, indent=1))
for _ in range(150):
    if proc.poll() is not None:
        sys.exit('bridge exited early: ' + (tree / 'bridge.log').read_text())
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{a.ui_port}/api/settings', timeout=0.5) as r:
            json.load(r)
        print(f'READY pid={proc.pid} url=http://127.0.0.1:{a.ui_port}')
        sys.exit(0)
    except OSError:
        time.sleep(0.1)
sys.exit('bridge readiness timeout')
