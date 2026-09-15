"""sdfix gate: boot or stop ONE scratch bridge from a git-archive tree.

Independent of scripts/showready/ui_geometry.py. Usage:
  bridge.py start --tree DIR --rev SHA --ui-port P --listen-port L [--mutation m1|m2|m3]
  bridge.py stop  --tree DIR
The tree gets `git archive <rev> windows protocol config`, byte copies of the
three Mac fixture presets (EDM Show active), and no bridge.local.json.
Env: PYSTRAY_BACKEND=dummy BROWSER=/usr/bin/true; argv --dry-run --no-engines
--no-pulse --no-osc-relay on loopback non-default ports checked free first.
stop sends SIGTERM, waits, and prints the os.kill(pid, 0) absence proof.
"""
import argparse, json, os, shutil, signal, socket, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT = Path('/Users/viddyslap/Documents/project-workspaces/steam-deck-midi')
FIXTURES = ROOT / '.showready/fixtures/mac/presets'
PRESETS = ['EDM Show.json', 'PTZ.json', 'default.json']
p = argparse.ArgumentParser()
p.add_argument('cmd', choices=['start', 'stop'])
p.add_argument('--tree', required=True)
p.add_argument('--rev')
p.add_argument('--ui-port', type=int)
p.add_argument('--listen-port', type=int)
p.add_argument('--mutation')
p.add_argument('--reuse', action='store_true', help='restart on an existing tree (after restore)')
a = p.parse_args()
tree = Path(a.tree)
if not str(tree.resolve()).startswith(('/private/tmp/sdfix-gate/', '/tmp/sdfix-gate/')):
    sys.exit('tree must be under /tmp/sdfix-gate/')
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
assert a.ui_port not in (7723, 45123) and a.listen_port not in (7723, 45123)
if a.reuse:
    assert (tree / 'windows').is_dir()
elif tree.exists():
    sys.exit(f'tree exists: {tree}')
else:
    tree.mkdir(parents=True)
    archive = subprocess.run(['git', '-C', str(ROOT), 'archive', a.rev, 'windows', 'protocol', 'config'], check=True, capture_output=True).stdout
    subprocess.run(['tar', '-x', '-C', str(tree)], input=archive, check=True)
    for name in os.listdir(tree / 'config/presets'):
        if name.endswith('.json') and name != 'default.json':
            (tree / 'config/presets' / name).unlink()
    for name in PRESETS:
        shutil.copyfile(FIXTURES / name, tree / 'config/presets' / name)
    (tree / 'config/presets/.active').write_text('EDM Show.json', encoding='ascii')
assert not (tree / 'config/bridge.local.json').exists()
if a.mutation:
    subprocess.run([sys.executable, str(Path(__file__).with_name('mutate.py')), str(tree), a.mutation], check=True)
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
(tree / 'bridge.argv.json').write_text(json.dumps({'argv': argv, 'cwd': str(tree), 'rev': a.rev, 'mutation': a.mutation,
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
