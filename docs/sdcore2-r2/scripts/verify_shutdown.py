"""Boot source with Mac launcher argv plus dry-run; curl Quit and rebind both ports."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
SCRATCH = Path('/tmp/sdcore-r2')
SCRATCH.mkdir(exist_ok=True)


def hashes():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / 'config').rglob('*')) if p.is_file()}


def ports_free():
    for kind, host, port in [(socket.SOCK_DGRAM, '0.0.0.0', 45123),
                             (socket.SOCK_STREAM, '127.0.0.1', 7723)]:
        with socket.socket(socket.AF_INET, kind) as probe:
            if kind == socket.SOCK_STREAM:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind((host, port))
            if kind == socket.SOCK_STREAM:
                probe.listen()
    print('UDP 45123 and TCP 7723 successfully rebound', flush=True)


parser = argparse.ArgumentParser()
parser.add_argument('--headless-tray', action='store_true', help='Use pystray dummy backend in a headless executor')
args = parser.parse_args()
child_env = {**os.environ, 'BROWSER': '/usr/bin/true', 'TMPDIR': str(SCRATCH)}
if args.headless_tray:
    child_env['PYSTRAY_BACKEND'] = 'dummy'
print('HEADLESS_TRAY', args.headless_tray, flush=True)
ports_free()  # Refuse to touch a pre-existing listener.
before = hashes()
local = ROOT / 'config/bridge.local.json'
section = json.loads(local.read_text()).get('preset_section') if local.exists() else 'macbook'
argv = [str(ROOT / '.venv/bin/python'), '-B', '-u', '-m', 'windows.win_recv']
if section:
    argv += ['--preset-section', section]
argv += ['--listen', '0.0.0.0:45123', '--map', 'config/windows_midi_map.json',
         '--midi-port', 'IAC Driver DECK_IN', '--feedback-port', 'IAC Driver DECK_OUT',
         '--pulse-port', 'IAC Driver PULSE_OUT', '--timeout', '2.0', '--ui-port', '7723', '--dry-run']
print('ARGV', json.dumps(argv), flush=True)
with (SCRATCH / 'bridge.log').open('w') as log:
    child = subprocess.Popen(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                             env=child_env)
    try:
        deadline = time.monotonic() + 15
        while True:
            assert child.poll() is None, f'bridge exited early: {child.returncode}'
            try:
                with urllib.request.urlopen('http://127.0.0.1:7723/api/settings', timeout=0.5) as response:
                    settings = json.load(response)
                break
            except OSError:
                assert time.monotonic() < deadline, 'HTTP did not bind'
                time.sleep(0.05)
        print('SETTINGS', json.dumps(settings), flush=True)
        # Query sockets of our exact child, rather than trusting a listening log.
        owned = subprocess.check_output(['lsof', '-nP', '-a', '-p', str(child.pid), '-i'], text=True)
        print(owned, end='', flush=True)
        assert ':45123' in owned and ':7723 (LISTEN)' in owned, owned
        start = time.monotonic()
        curl = subprocess.run(['curl', '-sS', '--max-time', '5', '-X', 'POST',
                               'http://127.0.0.1:7723/api/shutdown', '-w', '\n%{http_code}'],
                              capture_output=True, text=True, check=True)
        body, code = curl.stdout.rsplit('\n', 1)
        assert code == '202' and json.loads(body) == {'stopping': True}, curl.stdout
        print('CURL', curl.stdout, flush=True)
        result = child.wait(timeout=10)
        print('EXIT', result, 'elapsed_seconds', round(time.monotonic() - start, 3), flush=True)
        assert result == 0, result
    finally:
        if child.poll() is None:
            child.terminate()  # SIGTERM only; F2 remains backlog.
            child.wait(timeout=10)
        after = hashes()
        changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
        (SCRATCH / 'config-preservation.json').write_text(json.dumps({
            'before': before, 'after': after, 'changed': changed,
        }, indent=2) + '\n')
        print('CONFIG', len(before), 'files; changed:', changed, flush=True)
        assert not changed, changed
ports_free()
print('SHUTDOWN_PASS', flush=True)
