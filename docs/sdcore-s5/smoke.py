"""Run the standalone service and CLI with system Python, using scratch settings."""
import http.client
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = Path('/tmp/sdcore-s5')
SCRATCH.mkdir(exist_ok=True)
python = shutil.which('python3')
for module in ("deck.control_api", "deck.launch_send"):
    with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
        folder = Path(folder)
        bindings = folder / 'bindings.json'
        bindings.write_text('{"profile_name":"smoke","bindings":{"14":"BTN_A"}}')
        settings = folder / 'settings.json'
        settings.write_text(json.dumps({'bindings_path': str(bindings), 'presets': [{'name': 'Mac', 'host': 'mac.local'}]}))
        env = {**os.environ, 'TMPDIR': str(SCRATCH), 'PYTHONUNBUFFERED': '1'}
        child = subprocess.Popen([python, '-m', module, '--settings', str(settings), '--api-port', '0'],
                                 cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                assert selector.select(5), 'standalone startup timed out'
                line = child.stdout.readline().strip()
            assert line.startswith('Deck control API: http://127.0.0.1:'), line
            port = int(line.rsplit(':', 1)[1])
            for args in [['status'], ['targets'], ['activate', 'Mac'], ['stop']]:
                result = subprocess.run([python, '-m', 'deck.deckctl', '--url', f'http://127.0.0.1:{port}', *args],
                                        cwd=ROOT, env=env, capture_output=True, text=True, timeout=5)
                assert result.returncode == 0, result.stderr + result.stdout
                document = json.loads(result.stdout)
                if args == ['status']:
                    assert document['running'] is False and document['profile_name'] == 'smoke', document
                if args == ['activate', 'Mac']:
                    assert document['active_targets'] == ['Mac'], document
            assert json.loads(settings.read_text())['active_targets'] == ['Mac']
            conn = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
            try:
                conn.request('POST', '/api/shutdown')
                response = conn.getresponse()
                assert response.status == 200 and json.loads(response.read()) == {'ok': True}
            finally:
                conn.close()
            child.wait(timeout=5)
            print(f'PASS: {module}: system Python HTTP + CLI, persisted activation, HTTP shutdown')
        finally:
            if child.poll() is None:
                child.send_signal(signal.SIGINT)
            try:
                stdout, stderr = child.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.communicate()
                raise
            assert child.returncode == 0, (child.returncode, stdout, stderr)
            print('PASS: child exited 0 and was reaped')
