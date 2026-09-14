"""Gate F1 boot controls from git exports; stop only these children with SIGTERM."""
import argparse
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
PYTHON = ROOT / '.venv/bin/python'
SCRATCH = Path('/tmp/sdcore-r1')
SCRATCH.mkdir(exist_ok=True)
PORT = 45199
parser = argparse.ArgumentParser()
parser.add_argument('--revision', default='HEAD')
args = parser.parse_args()


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(('127.0.0.1', PORT))


arms = [
    ('v049', '5d778eb', False, False, True),
    ('before', 'f809be1', False, False, False),
    ('before-withlocal', 'f809be1', True, False, True),
    ('after', args.revision, False, False, True),
    ('after-sectioned', args.revision, False, True, True),
]
for label, revision, local, sectioned, should_boot in arms:
    with tempfile.TemporaryDirectory(dir=SCRATCH, prefix='boot-' + label + '-') as tmp:
        tree = Path(tmp)
        with tarfile.open(fileobj=io.BytesIO(git('archive', revision))) as archive:
            archive.extractall(tree, filter='data')
        local_path = tree / 'config/bridge.local.json'
        marker = tree / 'config/presets/.active'
        assert not local_path.exists() and not marker.exists()
        if local:
            local_path.write_text('{"preset_section":"macbook"}\n')
        if sectioned:
            (tree / 'config/presets/show.json').write_bytes(
                git('show', 'f809be1:config/presets/default.json'))
            marker.write_text('show.json')
        free_port()
        command = [str(PYTHON), '-B', '-u', '-m', 'windows.win_recv',
                   '--map', 'config/windows_midi_map.json', '--listen', f'127.0.0.1:{PORT}',
                   '--dry-run', '--no-ui', '--no-engines', '--no-pulse', '--no-osc-relay']
        log_path = SCRATCH / ('upgrade-boot-' + label + '.log')
        with log_path.open('w') as log:
            process = subprocess.Popen(command, cwd=tree, stdout=log, stderr=subprocess.STDOUT,
                                       env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(tree)},
                                       start_new_session=True)
            try:
                if not should_boot:
                    assert process.wait(timeout=10) == 2
                    assert 'preset section None is not available; available sections: macbook, windows' in log_path.read_text()
                    print(label, 'EXPECTED EXIT 2', flush=True)
                else:
                    ownership = None
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline:
                        assert process.poll() is None, log_path.read_text()
                        result = subprocess.run(['lsof', '-nP', '-a', '-p', str(process.pid), '-iUDP:' + str(PORT)],
                                                capture_output=True, text=True, timeout=3)
                        if result.returncode == 0 and f'127.0.0.1:{PORT}' in result.stdout:
                            ownership = result.stdout
                            break
                        time.sleep(0.1)
                    assert ownership is not None, log_path.read_text()
                    assert process.poll() is None
                    if sectioned:
                        assert json.loads(local_path.read_text()) == {'preset_section': 'macbook'}
                    elif not local:
                        assert not local_path.exists()
                    print(label, 'BOOTS; child PID', process.pid, 'OWNS UDP', PORT, flush=True)
                    print(ownership.strip(), flush=True)
            finally:
                if process.poll() is None:
                    process.terminate()
                code = process.wait(timeout=5)
                print(label, 'REAPED', code, flush=True)
        free_port()
        print(label, 'PORT RELEASED', flush=True)
print('ALL FIVE BOOT CONTROLS PASS', flush=True)
