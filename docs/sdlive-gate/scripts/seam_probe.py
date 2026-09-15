"""sdlive gate 4b: prove the pinned recorder sits BELOW E1's forward-first wrapper.

One bridge process (the pinned capture_runner, unchanged file) with two runtime
observers installed before it starts:
  * forwarded.jsonl: every call E1's LiveMidiOut._tap forwards to the backend,
    converted to raw MIDI bytes (status | channel, data1, data2).
  * Recorder.send is wrapped to note whether it runs INSIDE a wrapper forward.
The real capture file's midi rows are then compared to the forwarded sequence.
PASS requires nonempty, identical ordered byte sequences and every recorded row
emitted inside a forward. --plant-drop N drops the Nth recorder emit (must go RED).

  seam_probe.py launch TREE CAPTURE --script S [--plant-drop N] -- <bridge argv>   (child)
  seam_probe.py run REV SCRIPT OUTDIR [--plant-drop N]                               (driver)
"""
import json, os, signal, socket, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path('/Users/viddyslap/Documents/project-workspaces/steam-deck-midi')
KIT = ROOT / 'scripts/showready'

if sys.argv[1] == 'launch':
    tree, capture = Path(sys.argv[2]).resolve(), Path(sys.argv[3])
    rest = sys.argv[4:]
    plant = None
    if '--plant-drop' in rest:
        i = rest.index('--plant-drop'); plant = int(rest[i + 1]); del rest[i:i + 2]
    sys.path[:0] = [str(KIT), str(tree)]
    import capture_runner
    import windows.live_events as le
    fwd = open(str(capture) + '.forwarded.jsonl', 'w', buffering=1)
    depth = [0]
    names = {0x90: 'note_on', 0x80: 'note_off', 0xB0: 'control_change'}
    original_tap = le.LiveMidiOut._tap

    def tap(original, publisher, status, fields):
        def forward(*args, **kwargs):
            values = [args[i] if i < len(args) else kwargs.get(f, 0) for i, f in enumerate(fields)]
            fwd.write(json.dumps({'bytes': [status | values[0], values[1], values[2]], 'method': names[status]}) + '\n')
            depth[0] += 1
            try:
                return original(*args, **kwargs)
            finally:
                depth[0] -= 1
        forward.__name__ = getattr(original, '__name__', 'forward')
        return original_tap(forward, publisher, status, fields)
    le.LiveMidiOut._tap = staticmethod(tap)
    original_send = capture_runner.Recorder.send
    inside = open(str(capture) + '.inside.jsonl', 'w', buffering=1)
    sends = [0]

    def send(self, kind, channel, data1, data2):
        sends[0] += 1
        inside.write(json.dumps({'n': sends[0], 'inside_forward': depth[0] > 0}) + '\n')
        if plant is not None and sends[0] == plant:
            return None  # planted fault: the recorder misses one forwarded message
        return original_send(self, kind, channel, data1, data2)
    capture_runner.Recorder.send = send
    sys.argv = ['capture_runner.py', str(tree), str(tree / 'config'), str(capture)] + rest
    sys.exit(capture_runner.main())

# ---------------- driver ----------------
rev, script_path, outdir = sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])
plant = sys.argv[sys.argv.index('--plant-drop') + 1] if '--plant-drop' in sys.argv else None
outdir.mkdir(parents=True, exist_ok=False)
tree = outdir / 'tree'
tree.mkdir()
subprocess.run(['tar', '-x', '-C', str(tree)], input=subprocess.run(['git', '-C', str(ROOT), 'archive', rev], check=True, capture_output=True).stdout, check=True)
sys.path.insert(0, str(KIT))
from deck_script import verify_fixtures, read_json
verify_fixtures(ROOT / '.showready/fixtures')
preset = ROOT / '.showready/fixtures/mac/presets/EDM Show.json'
(tree / 'config/windows_midi_map.json').write_bytes(preset.read_bytes())
script = read_json(script_path)

def free(kind):
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind(('127.0.0.1', 0)); return s.getsockname()[1]
udp = free(socket.SOCK_DGRAM)
capture = outdir / 'capture.jsonl'
cmd = [str(ROOT / '.venv/bin/python'), '-B', __file__, 'launch', str(tree), str(capture), '--script', str(script_path), '--clock', 'script']
if plant:
    cmd += ['--plant-drop', plant]
cmd += ['--', '--map', str(tree / 'config/windows_midi_map.json'), '--preset-section', 'windows', '--listen', f'127.0.0.1:{udp}',
        '--ui-port', str(free(socket.SOCK_STREAM)), '--no-ui', '--no-engines', '--no-pulse', '--no-osc-relay']
env = {**os.environ, 'PYSTRAY_BACKEND': 'dummy', 'BROWSER': '/usr/bin/true', 'PYTHONDONTWRITEBYTECODE': '1', 'TMPDIR': str(outdir)}
log = open(outdir / 'bridge.log', 'wb')
proc = subprocess.Popen(cmd, cwd=tree, env=env, stdout=log, stderr=subprocess.STDOUT)
ready = Path(str(capture) + '.ready.json')
for _ in range(300):
    if ready.exists() or proc.poll() is not None:
        break
    time.sleep(0.05)
receipt = {'command': cmd, 'pid': proc.pid, 'rev': rev, 'script_sha256': script['sha256'], 'plant_drop': plant}
try:
    assert ready.exists(), 'bridge never bound: ' + (outdir / 'bridge.log').read_text()[-2000:]
    start = time.perf_counter_ns()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        for row in script['packets']:
            due = start + row['at_ns']
            while time.perf_counter_ns() < due:
                time.sleep(0.0005 if due - time.perf_counter_ns() > 2_000_000 else 0)
            s.sendto(bytes.fromhex(row['hex']), ('127.0.0.1', udp))
    done = Path(str(capture) + '.done.json')
    for _ in range(200):
        if done.exists():
            break
        time.sleep(0.05)
    time.sleep(2.5)  # timer horizon
    receipt['done'] = json.loads(done.read_text()) if done.exists() else None
finally:
    proc.send_signal(signal.SIGTERM)
    try:
        receipt['exit'] = proc.wait(15)
    except subprocess.TimeoutExpired:
        proc.kill(); receipt['exit'] = proc.wait(10)
    try:
        os.kill(proc.pid, 0); receipt['pid_gone'] = False
    except ProcessLookupError:
        receipt['pid_gone'] = True
rec = [json.loads(l)['bytes'] for l in capture.read_text().splitlines() if json.loads(l).get('record') == 'midi']
fwd = [json.loads(l)['bytes'] for l in Path(str(capture) + '.forwarded.jsonl').read_text().splitlines()]
inside = [json.loads(l)['inside_forward'] for l in Path(str(capture) + '.inside.jsonl').read_text().splitlines()]
first_diff = next((i for i, (a, b) in enumerate(zip(rec, fwd)) if a != b), None if len(rec) == len(fwd) else min(len(rec), len(fwd)))
receipt.update(recorded=len(rec), forwarded=len(fwd), recorder_sends=len(inside), sends_inside_forward=sum(inside),
               identical=rec == fwd, first_difference_index=first_diff,
               packets_received=(receipt.get('done') or {}).get('packets_received'), packets_scripted=len(script['packets']))
receipt['passed'] = bool(rec) and rec == fwd and len(inside) > 0 and all(inside) and receipt['pid_gone'] and receipt['packets_received'] == len(script['packets'])
(outdir / 'seam-receipt.json').write_text(json.dumps(receipt, indent=1))
print(json.dumps({k: v for k, v in receipt.items() if k != 'command'}))
sys.exit(0 if receipt['passed'] else 1)
