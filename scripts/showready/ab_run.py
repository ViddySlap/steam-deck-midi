"""Replay one pinned packet stream into archived v0.4.9 and candidate bridges."""
import argparse
from collections import defaultdict
import gzip
import io
import json
import os
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time

sys.dont_write_bytecode = True
from deck_script import canonical, effective, read_json, seal, sha, validate, verify_fixtures


KIT = Path(__file__).resolve().parent
ROOT = KIT.parents[1]


def default_scratch():
    if os.name == 'nt':
        return Path(os.environ['LOCALAPPDATA']) / 'Temp/sdwin/w3'
    return Path('/tmp/sdwin-w3')


def validate_scratch(path):
    allowed = Path(os.environ['LOCALAPPDATA']) / 'Temp/sdwin' if os.name == 'nt' else Path('/tmp')
    if not Path(path).resolve().is_relative_to(allowed.resolve()):
        raise ValueError('Scratch must be under ' + str(allowed))


def wait_gap(last_send_ns, interval_ns, clock=time.monotonic_ns, sleep=time.sleep):
    """No catch-up: preserve the gap even after a delayed wake or send."""
    due = last_send_ns + interval_ns
    while True:
        now = clock()
        if now >= due:
            return now
        sleep((due - now) / 1e9)


def pacing_summary(script, sends, speed):
    result = {}
    for arm, times in sends.items():
        result[arm] = {}
        for phase in ('axis-60hz', 'axis-10hz'):
            intervals = []
            minimums = []
            for left, right in zip(script['steps'], script['steps'][1:]):
                if left['phase'] == right['phase'] == phase and left['event']['action'] == right['event']['action']:
                    intervals.append(times[right['id']] - times[left['id']])
                    minimums.append(round((right['at_ns'] - left['at_ns']) / speed))
            result[arm][phase] = {'count': len(intervals), 'min_ns': min(intervals) if intervals else None,
                                 'median_ns': statistics.median(intervals) if intervals else None,
                                 'max_ns': max(intervals) if intervals else None,
                                 'no_overspeed': bool(intervals) and all(a >= b for a, b in zip(intervals, minimums))}
    return result


def git(repo, *args, binary=False):
    result = subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True)
    return result.stdout if binary else result.stdout.decode().strip()


def archive(repo, rev, target):
    commit = git(repo, 'rev-parse', rev + '^{commit}')
    data = git(repo, 'archive', commit, binary=True)
    target.mkdir()
    with tarfile.open(fileobj=io.BytesIO(data)) as bundle:
        for member in bundle.getmembers():
            if not (target / member.name).resolve().is_relative_to(target.resolve()) or member.issym() or member.islnk():
                raise ValueError('Unsafe archive member: ' + member.name)
        bundle.extractall(target, filter='data')
    return {'commit': commit, 'git_tree': git(repo, 'rev-parse', commit + '^{tree}'), 'archive_sha256': sha(data)}


def read_records(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='ascii').splitlines()]


def directed(message, mapping):
    status, number, _ = message
    if mapping['type'] in ('note', 'staged_note_macro'):
        channels = [mapping['channel']] if 'channel' in mapping else [mapping.get('modifier_channel', 0), mapping.get('trigger_channel', 1)]
        return status >> 4 in (8, 9) and status & 15 in channels and number == mapping['note']
    controls = [mapping['cc']] if 'cc' in mapping else [mapping.get('cc_positive'), mapping.get('cc_negative')]
    return status >> 4 == 11 and status & 15 == mapping.get('channel', 0) and number in controls


def compare(script, a, b, mappings_a, mappings_b):
    groups = []
    inputs = []
    for records in (a, b):
        group = defaultdict(list)
        received = defaultdict(list)
        for row in records:
            if row['record'] == 'midi':
                group[row['step']].append(row)
            elif row['record'] == 'input':
                received[row['step']].append(row)
        groups.append(group)
        inputs.append(received)
    steps = []
    for step in [{'id': -1, 'event': {'kind': 'startup'}}] + script['steps']:
        index = step['id']
        left, right = ([r['bytes'] for r in g[index]] for g in groups)
        steps.append({**step, 'A': left, 'B': right, 'identical': left == right})
    coverage = []
    for key in sorted(set(mappings_a) | set(mappings_b)):
        relevant = [s for s in steps if s['event'].get('action') == key]
        exercised = []
        for arm, mappings in enumerate((mappings_a, mappings_b)):
            mapping = mappings.get(key)
            received_all = bool(relevant) and all(len(inputs[arm][s['id']]) == 1 and
                (inputs[arm][s['id']][0]['handled'] or s['event']['kind'] == 'axis') for s in relevant)
            sent = mapping is not None and any(directed(r['bytes'], mapping)
                for s in relevant for r in groups[arm][s['id']])
            exercised.append(bool(received_all and sent))
        coverage.append({'mapping': key, 'exercised_A': exercised[0], 'exercised_B': exercised[1],
                         'exercised': all(exercised), 'identical': bool(relevant) and all(s['identical'] for s in relevant),
                         'reason': None if all(exercised) else 'NOT EXERCISED: missing input, unhandled input or no mapping-directed MIDI'})
    totals = {'steps': len(script['steps']), 'mappings': len(coverage),
              'mappings_exercised': sum(r['exercised'] for r in coverage),
              'messages_A': sum(len(v) for v in groups[0].values()),
              'messages_B': sum(len(v) for v in groups[1].values())}
    identical = all(s['identical'] for s in steps)
    passed = identical and all(r['exercised'] for r in coverage) and totals['messages_A'] > 0 and totals['messages_B'] > 0
    return {'passed': passed, 'identical': identical, 'steps': steps, 'mappings': coverage, 'totals': totals,
            'not_covered': [], 'different_mappings': [r['mapping'] for r in coverage if not r['identical']],
            'unexercised_mappings': [r['mapping'] for r in coverage if not r['exercised']]}


def free_port(kind):
    with socket.socket(socket.AF_INET, kind) as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    if port in (45123, 7723):
        return free_port(kind)
    return port


def wait_file(path, process, seconds=20):
    deadline = time.monotonic() + seconds
    while not path.exists():
        if process.poll() is not None:
            raise RuntimeError('Arm exited early: ' + str(process.returncode))
        if time.monotonic() >= deadline:
            raise TimeoutError('Arm file not written: ' + str(path))
        time.sleep(0.01)
    return read_json(path)


def write_result(path, result):
    data = canonical(result) + b'\n'
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if len(data) > 1_000_000 or path.suffix == '.gz':
        if path.suffix != '.gz':
            path = Path(str(path) + '.gz')
        path.write_bytes(gzip.compress(data, mtime=0))
    else:
        path.write_bytes(data)
    return path


def run(args):
    verified = verify_fixtures(args.fixtures)
    preset = args.preset.resolve()
    if str(preset) not in verified:
        raise ValueError('Preset not present in verified fixture manifests')
    raw = read_json(preset)
    if 'sections' in raw:
        if not args.section:
            raise ValueError('Sectioned fixture needs --section')
        flat_path = Path(str(preset) + '.v049.bak')
        if str(flat_path) not in verified:
            raise ValueError('Missing verified flat backup')
        flat = read_json(flat_path)
    else:
        flat_path, flat = preset, raw
        if args.section:
            raise ValueError('--section requires a sectioned fixture')
    script = read_json(args.script)
    validate(script)
    if args.control == 'coverage':
        removed = {s['id'] for s in script['steps'] if s['event'].get('action') == args.mapping}
        script['steps'] = [s for s in script['steps'] if s['id'] not in removed]
        script['packets'] = [p for p in script['packets'] if p['step'] not in removed]
        for seq, row in enumerate(script['packets'], 1):
            event = json.loads(bytes.fromhex(row['hex']))
            event['seq'] = seq
            row['hex'] = canonical(event).hex()
        seal(script)
    result = {'schema': 'sdwin-ab/1', 'candidate': args.candidate, 'preset': str(preset), 'section': args.section,
              'clock': args.clock, 'wall_speed': args.speed, 'control': args.control,
              'fixture_sha256': verified, 'script_sha256': script['sha256'],
              'script_file_sha256': sha(args.script.read_bytes()), 'packet_stream_sha256': script['packet_stream_sha256'],
              'script_parameters': script['parameters'],
              'instrument_sha256': {name: sha((KIT / name).read_bytes()) for name in ('deck_script.py', 'capture_runner.py', 'ab_run.py')},
              'arms': {}, 'comparisons': {}, 'passed': False}
    validate_scratch(args.scratch)
    args.scratch.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='ab-', dir=args.scratch)).resolve()
    result['work'] = str(work)
    (work / 'script.json').write_bytes(canonical(script) + b'\n')
    processes = {}
    logs = []
    captures = {}
    try:
        names = ['A', 'B1'] + (['B2'] if args.section else [])
        mappings = {}
        for name in names:
            tree = work / name
            identity = archive(args.repo, 'v0.4.9' if name == 'A' else args.candidate, tree)
            config = tree / 'config'
            # Only disposable archived files. Clear presets so the explicit
            # copied preset and .active cannot fall back to an archived preset.
            shutil.rmtree(config / 'presets')
            (config / 'presets').mkdir()
            selected = raw if name == 'B2' else flat
            selected = json.loads(json.dumps(selected))
            if args.control == 'sensitivity' and name != 'A':
                target = effective(selected, args.section if name == 'B2' else None)['mappings'][args.mapping]
                field = 'note' if 'note' in target else 'cc'
                before = target[field]
                if before >= 127:
                    raise ValueError('Sensitivity mapping needs room to increment')
                target[field] += 1
                identity['mutation'] = {'mapping': args.mapping, 'field': field, 'before': before, 'after': target[field]}
            payload = (preset if name == 'B2' else flat_path).read_bytes()
            if args.control == 'sensitivity' and name != 'A':
                payload = canonical(selected) + b'\n'
            (config / 'presets/replay.json').write_bytes(payload)
            (config / 'presets/.active').write_text('replay.json', encoding='ascii')
            (config / 'windows_midi_map.json').write_bytes(payload)
            mappings[name] = effective(selected, args.section if name == 'B2' else None)['mappings']
            identity['preset_sha256'] = sha(payload)
            port, ui_port = free_port(socket.SOCK_DGRAM), free_port(socket.SOCK_STREAM)
            capture = work / (name + '.jsonl')
            captures[name] = capture
            argv = [sys.executable, '-B', str(KIT / 'capture_runner.py'), str(tree), str(config), str(capture),
                    '--script', str(work / 'script.json'), '--clock', args.clock]
            if args.control == 'dead-seam':
                argv.append('--dead-recorder')
            argv += ['--', '--map', str(config / 'windows_midi_map.json'), '--listen', '127.0.0.1:' + str(port),
                     '--ui-port', str(ui_port), '--no-engines', '--no-pulse', '--no-osc-relay', '--no-ui']
            if name == 'B2':
                argv += ['--preset-section', args.section]
            log = (work / (name + '.log')).open('wb')
            logs.append(log)
            process = subprocess.Popen(argv, cwd=tree, stdout=log, stderr=subprocess.STDOUT,
                                       env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYSTRAY_BACKEND': 'dummy', 'BROWSER': 'true'})
            processes[name] = process
            identity.update(pid=process.pid, argv=argv, udp_port=port, ui_port=ui_port)
            result['arms'][name] = identity
            identity['ready'] = wait_file(Path(str(capture) + '.ready.json'), process)
        sends = {name: {} for name in names}
        wire_digest = __import__('hashlib').sha256()
        step_events = {s['id']: s for s in script['steps']}
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            start = time.monotonic_ns()
            last_send, previous_at = start, 0
            for row in script['packets']:
                wait_gap(last_send, round((row['at_ns'] - previous_at) / args.speed))
                payload = bytes.fromhex(row['hex'])
                wire_digest.update(__import__('struct').pack('!I', len(payload)))
                wire_digest.update(payload)
                for name in names:
                    if processes[name].poll() is not None:
                        raise RuntimeError('Arm died during replay: ' + name)
                    sent_at = time.monotonic_ns()
                    sent = sender.sendto(payload, ('127.0.0.1', result['arms'][name]['udp_port']))
                    if sent != len(payload):
                        raise RuntimeError('Partial UDP send')
                    if row['at_ns'] == step_events[row['step']]['at_ns']:
                        sends[name][row['step']] = sent_at
                last_send, previous_at = time.monotonic_ns(), row['at_ns']
            result['replay_wall_seconds'] = (time.monotonic_ns() - start) / 1e9
        result['pacing'] = pacing_summary(script, sends, args.speed)
        result['sent_packet_stream_sha256'] = wire_digest.hexdigest()
        for name in names:
            done = wait_file(Path(str(captures[name]) + '.done.json'), processes[name])
            result['arms'][name]['received'] = done
            if done['packet_stream_sha256'] != script['packet_stream_sha256'] or done['packets_received'] != len(script['packets']):
                raise ValueError('Incomplete/changed packet stream')
        # Timer horizon already drained in the script. Observe another real
        # socket-poll interval and reject any late MIDI before termination.
        before = {name: captures[name].stat().st_size for name in names}
        time.sleep(0.3)
        if any(captures[n].stat().st_size != before[n] for n in names):
            raise ValueError('Not quiescent after final timer horizon')
        result['quiescent'] = True
        records = {name: read_records(captures[name]) for name in names}
        for name in names[1:]:
            comparison = compare(script, records['A'], records[name], mappings['A'], mappings[name])
            for row in comparison['steps']:
                index = row['id']
                row['latency_ns'] = {}
                row['send_monotonic_ns'] = {}
                for arm in ('A', name):
                    midi = [r for r in records[arm] if r['record'] == 'midi' and r['step'] == index]
                    sent = sends[arm].get(index)
                    row['send_monotonic_ns'][arm] = sent
                    row['latency_ns'][arm] = midi[0]['monotonic_ns'] - sent if midi and sent is not None else None
            result['comparisons'][name] = comparison
        result['passed'] = (all(c['passed'] for c in result['comparisons'].values()) and
                            all(phase['no_overspeed'] for arm in result['pacing'].values() for phase in arm.values()))
    except Exception as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        for name, process in processes.items():
            was_alive = process.poll() is None
            method = 'terminate' if was_alive else 'already-exited'
            if was_alive:
                process.terminate()
            try:
                code = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                code = process.wait(timeout=10)
                method = 'terminate-then-kill'
            gone = process.poll() is not None
            if os.name == 'posix':
                try:
                    os.kill(process.pid, 0)
                    gone = False
                except ProcessLookupError:
                    pass
            result['arms'][name]['cleanup'] = {'method': method, 'exit_code': code, 'pid_gone': gone,
                                               'proof': 'Popen.wait plus kill(pid,0)' if os.name == 'posix' else 'Popen.wait process handle signaled'}
            if not gone or not was_alive:
                result['passed'] = False
        for log in logs:
            log.close()
        for name, path in captures.items():
            if path.exists():
                # Retain exact bytes/timestamps inline in the result artifact.
                result['arms'][name]['capture_sha256'] = sha(path.read_bytes())
                result['arms'][name]['records'] = read_records(path)
        result['script'] = script
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--preset', type=Path, required=True)
    parser.add_argument('--section')
    parser.add_argument('--script', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--repo', type=Path, default=ROOT)
    parser.add_argument('--fixtures', type=Path, default=ROOT / '.showready/fixtures')
    parser.add_argument('--scratch', type=Path, default=default_scratch())
    parser.add_argument('--clock', choices=('script', 'wall'), default='script')
    parser.add_argument('--speed', type=float, default=1.0, help='1 = real wall pacing; other values are explicitly synthetic controls')
    parser.add_argument('--control', choices=('sensitivity', 'coverage', 'dead-seam'))
    parser.add_argument('--mapping', default='BTN_A')
    args = parser.parse_args()
    if args.speed <= 0 or args.speed > 50:
        parser.error('--speed must be >0 and <=50')
    result = run(args)
    output = write_result(args.out, result)
    print(json.dumps({'result': str(output), 'passed': result['passed'], 'error': result.get('error'),
                      'comparisons': {k: {f: v[f] for f in ('totals', 'different_mappings', 'unexercised_mappings')}
                                      for k, v in result['comparisons'].items()}}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
