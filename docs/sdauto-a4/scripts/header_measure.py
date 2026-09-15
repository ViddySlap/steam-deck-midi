"""Boot a scratch-only UI bridge for one revision, run header_measure.cjs, reap the PID.

python header_measure.py --root RUNROOT --revision HEAD|WORKTREE --tag NAME --out DIR --ui-port N --listen-port N
"""
import argparse, json, os, shutil, signal, socket, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--root', required=True); p.add_argument('--revision', required=True)
p.add_argument('--tag', required=True); p.add_argument('--out', required=True)
p.add_argument('--ui-port', type=int, required=True); p.add_argument('--listen-port', type=int, required=True)
p.add_argument('--geometry', action='store_true'); p.add_argument('--plant-old'); p.add_argument('--plant-new')
p.add_argument('--chromium', default='/Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell')
a = p.parse_args()
ROOT = Path(a.root); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
assert str(out.resolve()).startswith(('/private/tmp/sdauto-a4', '/tmp/sdauto-a4'))
assert {a.ui_port, a.listen_port}.isdisjoint({7723, 45123}) and a.ui_port != a.listen_port
work = Path(tempfile.mkdtemp(prefix=f'{a.tag}-', dir=out)); tree = work / 'tree'; tree.mkdir()
for name in filter(None, subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '-z', 'windows', 'protocol', 'config']).decode().split('\0')):
    target = tree / name; target.parent.mkdir(parents=True, exist_ok=True)
    if a.revision == 'WORKTREE':
        if (ROOT / name).is_file(): shutil.copyfile(ROOT / name, target)
    else:
        target.write_bytes(subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{a.revision}:{name}']))
if a.plant_old is not None:
    page = tree / 'windows/static/index.html'; text = page.read_text(encoding='utf-8')
    assert text.count(a.plant_old) == 1, 'plant target must occur exactly once'
    page.write_text(text.replace(a.plant_old, a.plant_new), encoding='utf-8'); print('PLANTED', repr(a.plant_old), '->', repr(a.plant_new), flush=True)
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'scripts/showready'))
from deck_script import verify_fixtures
verify_fixtures(ROOT / '.showready/fixtures')
for src in (ROOT / '.showready/fixtures/mac/presets').glob('*.json'):
    shutil.copyfile(src, tree / 'config/presets' / src.name)
(tree / 'config/presets/.active').write_text('EDM Show.json', encoding='ascii')
for port, kind in [(a.ui_port, socket.SOCK_STREAM), (a.listen_port, socket.SOCK_DGRAM)]:
    with socket.socket(socket.AF_INET, kind) as s: s.bind(('127.0.0.1', port))
    print(f'PASS free port {port}', flush=True)
env = {**os.environ, 'PYSTRAY_BACKEND': 'dummy', 'BROWSER': '/usr/bin/true', 'TMPDIR': str(work), 'PYTHONDONTWRITEBYTECODE': '1'}
argv = [str(ROOT / '.venv/bin/python'), '-B', '-u', '-m', 'windows.win_recv', '--listen', f'127.0.0.1:{a.listen_port}', '--map', 'config/windows_midi_map.json',
        '--preset-section', 'windows', '--dry-run', '--no-engines', '--no-pulse', '--no-osc-relay', '--no-browser', '--ui-port', str(a.ui_port)]
receipt = {'tag': a.tag, 'revision': a.revision, 'work': str(work), 'bridge_argv': argv}
bridge = None; code = 1
try:
    with (work / 'bridge.log').open('w') as log:
        bridge = subprocess.Popen(argv, cwd=tree, env=env, stdout=log, stderr=subprocess.STDOUT)
    receipt['bridge_pid'] = bridge.pid
    url = f'http://127.0.0.1:{a.ui_port}'
    for _ in range(150):
        if bridge.poll() is not None: raise RuntimeError('bridge exited: ' + (work / 'bridge.log').read_text())
        try:
            with urllib.request.urlopen(url + '/api/settings', timeout=.5) as r: json.load(r); break
        except OSError: time.sleep(.1)
    else: raise RuntimeError('bridge readiness timeout')
    try:
        with urllib.request.urlopen(url + '/api/version', timeout=2) as r:
            receipt['api_version'] = {'status': r.status, 'content_type': r.headers.get('content-type'), 'body': json.load(r)}
    except urllib.error.HTTPError as e:
        receipt['api_version'] = {'status': e.code, 'content_type': e.headers.get('content-type')}
    print('API_VERSION ' + json.dumps(receipt['api_version']), flush=True)
    res = subprocess.run(['node', str(Path(__file__).resolve().parent / 'header_measure.cjs'), url, a.chromium, str(out), a.tag], capture_output=True, text=True, timeout=180)
    print(res.stdout + res.stderr, end='', flush=True)
    receipt['measure_exit'] = res.returncode
    code = res.returncode
    if a.geometry:
        (out / f'{a.tag}-geometry').mkdir(exist_ok=True); gcmd = ['node', str(ROOT / 'docs/sdlive-gate/scripts/geom_live.cjs'), url, a.chromium, str(out / f'{a.tag}-geometry')]
        g = subprocess.run(gcmd, capture_output=True, text=True, timeout=300)
        (out / f'{a.tag}-geometry.log').write_text(g.stdout + g.stderr)
        receipt['geometry'] = {'command': gcmd, 'exit': g.returncode}
        print('GEOMETRY', g.returncode, [l for l in g.stdout.splitlines() if l.startswith(('FAIL', 'SUMMARY'))][-12:], flush=True)
        code = code or g.returncode
finally:
    if bridge:
        if bridge.poll() is None: bridge.send_signal(signal.SIGTERM)
        try: bridge.wait(timeout=15)
        except subprocess.TimeoutExpired: bridge.kill(); bridge.wait(timeout=10)
        try: os.kill(bridge.pid, 0); receipt['bridge_pid_gone'] = False; code = 1
        except ProcessLookupError: receipt['bridge_pid_gone'] = True
        print(f"bridge PID {bridge.pid} gone={receipt['bridge_pid_gone']}", flush=True)
    receipt['exit'] = code
    (out / f'{a.tag}-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
sys.exit(code)
