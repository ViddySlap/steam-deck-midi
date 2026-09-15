"""Bar 3: interleaved same-candidate MIDI latency, with fail-closed controls."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shlex
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

sys.dont_write_bytecode = True
from ab_run import (KIT, ROOT, archive, compare, free_port, git, pacing_summary,
                    read_records, validate_scratch, wait_gap, write_result)
from deck_script import canonical, effective, read_json, sha, validate, verify_fixtures

BAR3_TOLERANCE_MS = 1.0
MIN_TIMED_MIDI_MESSAGES = 1000
STATISTICS = ('p50', 'p95', 'p99')
ARMS = ('CLOSED', 'OPEN', 'CLOSED-B')
RULES = ('locked', 'm_bridge')
M_BRIDGE_INVALID = 'M_BRIDGE RULE INVALID: sensitivity control did not go RED'
# MASTER sdbar3 LOAD RULES: harness engine test runners are foreign load on the Mac.
FOREIGN_TESTS = '/Users/viddyslap/Documents/project-workspaces/local-LLM-h14/engine/tests/'
# webbrowser runs BROWSER via shlex.split; every cmd.exe form returns nonzero on Windows,
# which falls through to the default browser (a real live client). Python -c pass exits 0.
NOOP_BROWSER = shlex.quote(sys.executable.replace('\\', '/')) + ' -c pass %s' if os.name == 'nt' else '/usr/bin/true'


def percentile(values, percent):
    """Linear interpolation at (n-1)*p, including endpoints; empty is an error."""
    values = sorted(values)
    if not values or not 0 <= percent <= 100 or not all(math.isfinite(x) for x in values):
        raise ValueError('Nonempty finite samples and percentile 0..100 required')
    at = (len(values) - 1) * percent / 100
    lo, hi = math.floor(at), math.ceil(at)
    return values[lo] + (values[hi] - values[lo]) * (at - lo)


def stats(values):
    return {**{key: percentile(values, p) for key, p in zip(STATISTICS, (50, 95, 99))},
            'max': max(values), 'count': len(values)}


def verdict(closed, opened, closed_b, *, identical, dropped_reported, live, valid_arms=True,
            require_floor_resolution=True):
    floor = {key: abs(closed[key] - closed_b[key]) for key in STATISTICS}
    delta = {key: abs(opened[key] - closed[key]) for key in STATISTICS}
    within = {key: delta[key] <= floor[key] + BAR3_TOLERANCE_MS for key in STATISTICS}
    # A known +2 ms shift must not fit inside this measured floor.
    sensitivity_visible = any(2.0 > floor[k] + BAR3_TOLERANCE_MS for k in STATISTICS)
    # The declared M_bridge rule proves resolution by its own sensitivity run instead.
    resolved = sensitivity_visible or not require_floor_resolution
    return {'noise_floor_ms': floor, 'open_delta_ms': delta, 'within': within,
            'floor_can_resolve_2ms': sensitivity_visible,
            'valid_arms': valid_arms,
            'passed': all(within.values()) and identical and dropped_reported and live and resolved and valid_arms}


def power_floor(samples):
    count = len(samples)
    return {'timed_midi_messages': count, 'minimum_timed_midi_messages': MIN_TIMED_MIDI_MESSAGES,
            'timing_status': 'VALID' if count >= MIN_TIMED_MIDI_MESSAGES else 'INVALID'}


def every_message_floor(joined):
    count = len(joined)
    return {'every_message_timed_midi_messages': count, 'minimum_timed_midi_messages': MIN_TIMED_MIDI_MESSAGES,
            'every_message_timing_status': 'VALID' if count >= MIN_TIMED_MIDI_MESSAGES else 'INVALID'}


def m_total_ms(t3_ns, t0_ns):
    """The locked rule's latency: recorder perf_counter minus the cause step's send stamp."""
    return (t3_ns - t0_ns) / 1e6


def bridge_join(timed, t1_pre, t1_post):
    """Attach the causing packet's t1_pre/t1_post to EVERY timed MIDI message.

    A timed message is joined to the packet the bridge was handling when it
    wrote the MIDI (step and script instant of the last datagram received).
    A missing stamp or an impossible order is an error, never a skip.
    """
    joined = []
    for row in timed:
        packet = row.get('cause_packet')
        known = type(packet) is int and 0 <= packet < min(len(t1_pre), len(t1_post))
        pre, post = (t1_pre[packet], t1_post[packet]) if known else (None, None)
        if pre is None or post is None:
            raise ValueError('Timed MIDI without t1_pre/t1_post: step %s packet %s' % (row.get('step'), packet))
        if post < pre or row['t3_ns'] < pre:
            raise ValueError('Impossible send/MIDI order at packet %s' % packet)
        joined.append({**row, 't1_pre_ns': pre, 't1_post_ns': post,
                       'm_bridge_ms': (row['t3_ns'] - pre) / 1e6, 'm_post_ms': (row['t3_ns'] - post) / 1e6})
    return joined


def sensitivity_delay(clock=time.perf_counter_ns, pause=lambda: time.sleep(0)):
    """Plant 2 ms without a coarse positive sleep expanding it to a timer tick."""
    deadline = clock() + 2_000_000
    while clock() < deadline:
        pause()


def timing_pacing(script, sends, speed):
    if script.get('schema') != 'sdlive-timing-script/1':
        return pacing_summary(script, {'arm': sends}, speed)['arm']
    grouped = {}
    for step in script['steps']:
        if step['event']['kind'] == 'axis':
            key = step['segment'] + '/' + step['event']['action']
            grouped.setdefault(key, []).append(step)
    result = {}
    for key, steps in grouped.items():
        intervals = [sends[b['id']] - sends[a['id']] for a, b in zip(steps, steps[1:])]
        minimums = [round((b['at_ns'] - a['at_ns']) / speed) for a, b in zip(steps, steps[1:])]
        result[key] = {'count': len(intervals), 'min_ns': min(intervals) if intervals else None,
                       'median_ns': statistics.median(intervals) if intervals else None,
                       'max_ns': max(intervals) if intervals else None,
                       'no_overspeed': bool(intervals) and all(a >= b for a, b in zip(intervals, minimums))}
    if not result:
        raise ValueError('Zero axis pacing observations')
    return result


def measurement_qualified(args, runs):
    minimum_repeats = 3 if args.control == 'sensitivity' else 5
    return (args.repeats >= minimum_repeats and args.speed == 1 and
            (os.name == 'nt' or bool(args.client_cmd)) and
            len(runs) == args.repeats * len(ARMS) and
            all(r['load_status'] == 'verified' and r['arm']['passed'] and
                power_floor(r['arm']['samples'])['timing_status'] == 'VALID' and
                (getattr(args, 'rule', 'locked') != 'm_bridge' or
                 every_message_floor(r['arm'].get('bridge_samples', []))['every_message_timing_status'] == 'VALID')
                for r in runs))


def sensitivity_matches(control, result, rule='locked'):
    if rule == 'm_bridge':
        red = (control.get('rule') == 'm_bridge' and control.get('m_bridge_sensitivity_timing_red') and
               control.get('m_bridge', {}).get('rule', {}).get('valid_arms'))
    else:
        red = control.get('sensitivity_timing_red') and control.get('summary', {}).get('rule', {}).get('valid_arms')
    return bool(red and
        control.get('summary', {}).get('byte_identical') and
        control.get('measurement_qualified') and control.get('control') == 'sensitivity' and
        control.get('repeats', 0) >= 3 and
        all(control.get(k) == result.get(k) for k in
            ('host', 'candidate', 'preset_sha256', 'client', 'receiver_clock', 'instrument_sha256')) and
        control.get('script', {}).get('sha256') == result['script']['sha256'])


def load_check():
    result = {'command': 'pgrep -f "while True: pass"', 'load_average': None}
    try:
        result['load_average'] = list(os.getloadavg())
    except (AttributeError, OSError) as exc:
        result['load_average_note'] = 'not applicable on Windows' if os.name == 'nt' else str(exc)
    if os.name == 'nt':
        return {**result, 'status': 'not applicable', 'exit_code': None}
    try:
        check = subprocess.run(['pgrep', '-f', 'while True: pass'], capture_output=True, text=True)
        result.update(exit_code=check.returncode, stdout=check.stdout, stderr=check.stderr)
        if check.returncode == 1 and not check.stdout.strip() and not check.stderr.strip():
            result['status'] = 'empty'
        elif check.returncode == 0 and check.stdout.strip() and not check.stderr.strip():
            result['status'] = 'load-present'
        else:
            result['status'] = 'unreadable'
    except OSError as exc:
        result.update(status='unreadable', error=repr(exc))
    if result['load_average'] is None:
        result['status'] = 'unreadable'
    return result


def foreign_lines(ps_stdout):
    """`ps -A -o pid=,command=` rows running a harness engine test or run-all.sh."""
    matched = []
    for line in ps_stdout.splitlines():
        command = line.strip().partition(' ')[2]
        tokens = command.split()
        if 'codex exec' in command or not tokens or os.path.basename(tokens[0]) not in ('zsh', 'bash', 'sh', 'node'):
            continue
        rest, script, i = tokens[1:], None, 0
        while i < len(rest):
            if rest[i] == '-c':
                i += 2  # The command string is an option value, not a script.
            elif rest[i].startswith('-'):
                i += 1
            else:
                script = rest[i]
                break
        if script and (script.startswith(FOREIGN_TESTS) or os.path.basename(script) == 'run-all.sh'):
            matched.append(line.strip()[:220])
    return matched


def foreign_load_check(check=load_check):
    """load_check plus foreign_lines and sysctl load1; any foreign line is present load."""
    result = check()
    if result['status'] == 'not applicable':
        return result
    foreign = {'command': 'ps -A -o pid=,command=', 'foreign_lines': None, 'load1': None}
    try:
        ps = subprocess.run(['ps', '-A', '-o', 'pid=,command='], capture_output=True, text=True)
        foreign.update(ps_exit=ps.returncode)
        if ps.returncode == 0 and ps.stdout.strip():
            foreign['matched'] = foreign_lines(ps.stdout)
            foreign['foreign_lines'] = len(foreign['matched'])
        loadavg = subprocess.run(['sysctl', '-n', 'vm.loadavg'], capture_output=True, text=True)
        foreign['load1'] = float(loadavg.stdout.split()[1])
    except (OSError, IndexError, ValueError) as exc:
        foreign['error'] = repr(exc)
    result['foreign'] = foreign
    if foreign['foreign_lines']:
        result['status'] = 'load-present'
    elif foreign['foreign_lines'] is None and result['status'] == 'empty':
        result['status'] = 'unreadable'
    return result


def guarded_arm(run, check=load_check, *, allow_unverified=False, retries=3, pause=time.sleep):
    """Every attempt retains both checks, even a skipped/failed attempt."""
    attempts = []
    for number in range(1, retries + 1):
        before = check()
        outcome = None
        error = None
        try:
            if before['status'] in ('empty', 'not applicable') or (
                    before['status'] == 'unreadable' and allow_unverified):
                outcome = run(number)
        except Exception as exc:
            error = type(exc).__name__ + ': ' + str(exc)
        after = check()
        row = {'attempt': number, 'before': before, 'after': after, 'arm': outcome, 'error': error}
        attempts.append(row)
        dirty = any(c['status'] == 'load-present' for c in (before, after))
        unreadable = any(c['status'] == 'unreadable' for c in (before, after))
        row['load_status'] = 'UNVERIFIED-LOAD' if unreadable else 'CONTAMINATED' if dirty else 'verified'
        if dirty:
            if number < retries:
                pause(30)
                continue
            break
        if error or outcome is None or (unreadable and not allow_unverified):
            break
        return {'accepted': True, 'load_status': row['load_status'], 'attempts': attempts, 'arm': outcome}
    return {'accepted': False, 'attempts': attempts, 'load_status': attempts[-1]['load_status']}


class CaptureTiming:
    """Loaded ONLY in the archived bridge process by the pinned recorder.

    Sender and recorder call perf_counter_ns in this same process. The optional
    script clock is receiver scheduling only, never a latency timestamp.
    """
    def __init__(self, config, script, context):
        self.config, self.script, self.context = config, script, context
        self.sent, self.origins = {}, {}
        self.live = None
        self.invalid = []
        self.samples = []
        self.completed_packets = 0
        self.mappings = config['mappings']
        packets = script.get('packets', [])
        # (step, script instant) names ONE packet; capture_runner sets both at each receipt.
        self.packet_index = {(p['step'], p['at_ns']): i for i, p in enumerate(packets)}
        starts = {s['id']: s['at_ns'] for s in script.get('steps', [])}
        self.first_packets = {i for i, p in enumerate(packets) if p['at_ns'] == starts.get(p['step'])}
        self.t1_pre, self.t1_post = [None] * len(packets), [None] * len(packets)
        self.timed = []

    def install(self, module):
        self.action = module.current_action
        original = module.LiveEvents.publish
        owner = self

        def observed(publisher, event):
            owner.live = publisher
            if event['kind'] in ('input', 'axis'):
                action = event['action']
                kind = owner.mappings.get(action, {}).get('type')
                # Delayed fade/repeat/staged output belongs to its DOWN even
                # after UP. Immediate note/CC releases belong to the UP.
                if event.get('state') != 'up' or kind not in ('macro_cc', 'relative_cc', 'staged_note_macro'):
                    owner.origins[action] = owner.context['step']
            return original(publisher, event)
        module.LiveEvents.publish = observed
        original_init = module.LiveEvents.__init__

        def init(publisher, *a, **kw):
            original_init(publisher, *a, **kw)
            owner.live = publisher
        module.LiveEvents.__init__ = init

    def enrich(self, row):
        if row['record'] != 'midi':
            return
        row['perf_counter_ns'] = row['monotonic_ns']  # Existing Recorder uses perf_counter_ns.
        action = self.action()
        cause = self.origins.get(action)
        sent = self.sent.get(cause)
        row.update(action=action, cause_step=cause, send_perf_counter_ns=sent)
        if row['step'] == -1:
            row['latency_ms'] = None  # Startup has no physical input; bytes still compared.
        elif sent is None or row['perf_counter_ns'] < sent:
            self.invalid.append(dict(row))
        else:
            row['latency_ms'] = m_total_ms(row['perf_counter_ns'], sent)
            self.samples.append(dict(row))
        if row['step'] != -1:
            packet = self.packet_index.get((row['step'], row.get('logical_ns')))
            row['cause_packet'] = packet
            self.timed.append({'step': row['step'], 'cause_step': cause, 'cause_packet': packet,
                               'first_packet': packet in self.first_packets,
                               't3_ns': row['perf_counter_ns'], 'latency_ms': row.get('latency_ms')})

    def start(self, host, port, capture):
        def replay():
            result = {'timestamp_clock': vars(time.get_clock_info('perf_counter')),
                      'clock_method': 'sender and Recorder perf_counter_ns in the same PID',
                      'pid': os.getpid(), 'passed': False}
            try:
                start_file = Path(self.config['start'])
                deadline = time.perf_counter() + 60
                while not start_file.exists():
                    if time.perf_counter() >= deadline:
                        raise TimeoutError('Parent never authorized replay')
                    time.sleep(.01)
                result['snapshot_before'] = self.live.snapshot()
                steps = {s['id']: s for s in self.script['steps']}
                start = last = step_start = time.perf_counter_ns()
                previous_at = 0
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                    for index, row in enumerate(self.script['packets']):
                        step = steps[row['step']]
                        event = row['at_ns'] == step['at_ns']
                        sleeper = (lambda _: time.sleep(0)) if step['event']['kind'] == 'axis' else time.sleep
                        if event:
                            wait_gap(last, round((row['at_ns'] - previous_at) / self.config['speed']), sleep=sleeper)
                        else:
                            wait_gap(step_start, round((row['at_ns'] - step['at_ns']) / self.config['speed']), sleep=sleeper)
                        # Accelerated diagnostics cannot earn timing credit.
                        # Drain the prior loop so compressed timer probes do
                        # not overflow UDP during the planted sleep control.
                        if self.config['speed'] != 1:
                            ack_deadline = time.perf_counter() + 10
                            while self.completed_packets < index:
                                if time.perf_counter() >= ack_deadline:
                                    raise TimeoutError('Diagnostic packet drain')
                                time.sleep(0)
                        payload = bytes.fromhex(row['hex'])
                        sent_at = time.perf_counter_ns()
                        if event:
                            self.sent[row['step']] = sent_at
                        t1_pre = time.perf_counter_ns()  # t1_pre: IMMEDIATELY before sendto (M_bridge).
                        written = sender.sendto(payload, (host, port))
                        t1_post = time.perf_counter_ns()  # t1_post: immediately after it returns (diagnostic).
                        self.t1_pre[index], self.t1_post[index] = t1_pre, t1_post
                        if written != len(payload):
                            raise RuntimeError('Partial datagram')
                        if event:
                            last = step_start = time.perf_counter_ns()
                            previous_at = row['at_ns']
                result['wall_seconds'] = (time.perf_counter_ns() - start) / 1e9
                done = Path(str(capture) + '.done.json')
                deadline = time.perf_counter() + 10
                while not done.exists():
                    if time.perf_counter() >= deadline:
                        raise TimeoutError('Packet capture incomplete')
                    time.sleep(.01)
                size = capture.stat().st_size
                time.sleep(.3)
                if capture.stat().st_size != size:
                    raise ValueError('MIDI not quiescent after timer horizon')
                joined = bridge_join(self.timed, self.t1_pre, self.t1_post)
                result.update(snapshot_after=self.live.snapshot(), received=read_json(done),
                              sends=self.sent, invalid=self.invalid, samples=self.samples,
                              pacing=timing_pacing(self.script, self.sent, self.config['speed']),
                              **power_floor(self.samples))
                result.update(t1_pre_ns=self.t1_pre, t1_post_ns=self.t1_post, bridge_samples=joined,
                              **every_message_floor(joined))
                result['passed'] = bool(self.samples) and not self.invalid and all(
                    p['no_overspeed'] for p in result['pacing'].values()) and result['timing_status'] == 'VALID'
            except Exception as exc:
                result['error'] = type(exc).__name__ + ': ' + str(exc)
            target = Path(self.config['result'])
            temporary = target.with_suffix('.tmp')
            temporary.write_bytes(canonical(result))
            temporary.replace(target)
        threading.Thread(target=replay, name='bar3-sender', daemon=True).start()


def snapshot(url):
    with urllib.request.urlopen(url + '/api/live/snapshot', timeout=2) as response:
        return json.load(response)


class StreamingClient:
    """Initial snapshot, drain SSE immediately, refresh snapshot on every loss."""
    def __init__(self, url):
        self.url = url
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.events = []
        self.snapshots = []
        self.error = None
        self.response = None
        self.thread = threading.Thread(target=self.read, name='bar3-stream', daemon=True)
        self.thread.start()

    def read(self):
        try:
            state = snapshot(self.url)
            self.snapshots.append(state)
            while not self.stop.is_set():
                with urllib.request.urlopen(self.url + '/api/live/events?since=' + str(state['seq']), timeout=3) as response:
                    self.response = response
                    if response.headers.get_content_type() != 'text/event-stream':
                        raise ValueError('Not an SSE stream')
                    self.ready.set()
                    refresh = False
                    for line in response:
                        if self.stop.is_set():
                            break
                        if line.startswith(b'data: '):
                            event = json.loads(line[6:])
                            self.events.append(event)
                            if event['kind'] == 'dropped':
                                state = snapshot(self.url)
                                self.snapshots.append(state)
                                refresh = True
                                break
                    if not refresh and not self.stop.is_set():
                        raise ValueError('Unexpected stream EOF')
        except Exception as exc:
            if not self.stop.is_set():
                self.error = type(exc).__name__ + ': ' + str(exc)
        finally:
            self.ready.set()

    def close(self):
        self.stop.set()
        self.thread.join(4)
        return {'events': self.events, 'snapshots': self.snapshots, 'error': self.error,
                'thread_gone': not self.thread.is_alive(),
                'data_events': sum(e['kind'] != 'dropped' for e in self.events),
                'dropped': sum(e.get('count', 0) for e in self.events if e['kind'] == 'dropped')}


def live_valid(evidence):
    counts = evidence.get('client_counts', [])
    stream = evidence.get('stream', {})
    return bool(counts) and all(c > 0 for c in counts) and stream.get('data_events', 0) > 0 and (
        type(stream.get('dropped')) is int) and not stream.get('error')


def stop_process(process):
    was_alive = process.poll() is None
    if was_alive:
        process.terminate()
    try:
        code = process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        code = process.wait(timeout=10)
    gone = process.poll() is not None
    if os.name == 'posix':
        try:
            os.kill(process.pid, 0)
            gone = False
        except ProcessLookupError:
            pass
    return {'pid': process.pid, 'exit_code': code, 'pid_gone': gone,
            'was_alive': was_alive, 'proof': 'Popen.wait + kill(pid,0)' if os.name == 'posix' else 'Popen.wait signaled handle'}


def verify_client_pids(pids, work):
    if not pids or any(type(p) is not int or p <= 1 for p in pids):
        raise ValueError('External client must report its browser PIDs')
    if os.name == 'nt':
        script = work / 'client-gone.ps1'
        script.write_text('$ErrorActionPreference = "Stop"\n' +
                          '$found = @(Get-Process -Id ' + ','.join(map(str, pids)) +
                          ' -ErrorAction SilentlyContinue)\nif ($found.Count) { exit 1 }\nexit 0\n', encoding='ascii')
        check = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)], capture_output=True, text=True)
        return {'pids': pids, 'gone': check.returncode == 0, 'command': str(script), 'exit_code': check.returncode,
                'stdout': check.stdout, 'stderr': check.stderr}
    found = []
    for pid in pids:
        try:
            os.kill(pid, 0)
            found.append(pid)
        except ProcessLookupError:
            pass
    return {'pids': pids, 'gone': not found, 'found': found, 'proof': 'kill(pid,0)'}


def wait_json(path, process, timeout=30):
    deadline = time.perf_counter() + timeout
    while not path.exists():
        if process.poll() is not None:
            raise RuntimeError('Process exited before ' + path.name)
        if time.perf_counter() >= deadline:
            raise TimeoutError(path.name)
        time.sleep(.02)
    return read_json(path)


def run_arm(args, tree, work, script, mappings, label):
    directory = work / label
    directory.mkdir()
    capture = directory / 'capture.jsonl'
    start = directory / 'start'
    result_file = directory / 'timing.json'
    options = directory / 'options.json'
    options.write_bytes(canonical({'start': str(start), 'result': str(result_file), 'speed': args.speed, 'mappings': mappings}))
    udp, ui = free_port(socket.SOCK_DGRAM), free_port(socket.SOCK_STREAM)
    while ui == udp:
        ui = free_port(socket.SOCK_STREAM)
    command = [sys.executable, '-B', str(KIT / 'capture_runner.py'), str(tree), str(tree / 'config'), str(capture),
               '--script', str(work / 'script.json'), '--clock', args.clock, '--timing-config', str(options),
               '--', '--map', str(tree / 'config/windows_midi_map.json'), '--preset-section', 'windows',
               '--listen', '127.0.0.1:' + str(udp), '--ui-port', str(ui), '--no-engines', '--no-pulse', '--no-osc-relay']
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYSTRAY_BACKEND': 'dummy',
           'BROWSER': NOOP_BROWSER}
    result = {'command': command, 'udp_port': udp, 'ui_port': ui, 'passed': False, 'client_counts': []}
    client = external = process = None
    client_stop, receipt = directory / 'client-stop', directory / 'client.json'
    is_open = '-OPEN-' in label
    with (directory / 'bridge.log').open('wb') as log, (directory / 'client.log').open('wb') as client_log:
        try:
            process = subprocess.Popen(command, cwd=tree, stdout=log, stderr=subprocess.STDOUT, env=env)
            result['ready'] = wait_json(Path(str(capture) + '.ready.json'), process)
            url = 'http://127.0.0.1:' + str(ui)
            if is_open:
                if args.control == 'dead-client':
                    pass  # Plant absence; the ordinary presence check must fail.
                elif args.client_cmd:
                    argv = [s.replace('{url}', url).replace('{stop}', str(client_stop)).replace('{receipt}', str(receipt)) for s in args.client_cmd]
                    result['client_command'] = argv
                    external = subprocess.Popen(argv, env=env, stdout=client_log, stderr=subprocess.STDOUT)
                    deadline = time.perf_counter() + 30
                    while True:
                        ready = read_json(receipt) if receipt.exists() else {}
                        if ready.get('error') or external.poll() is not None:
                            raise ValueError('External client failed: ' + str(ready))
                        if ready.get('ready'):
                            result['client_ready'] = ready
                            break
                        if time.perf_counter() >= deadline:
                            raise TimeoutError('External client not ready')
                        time.sleep(.02)
                else:
                    client = StreamingClient(url)
                    if not client.ready.wait(10) or client.error:
                        raise ValueError('DEAD CLIENT: ' + str(client.error))
                count = snapshot(url)['clients']
                result['client_counts'].append(count)
                if count == 0:
                    raise ValueError('DEAD CLIENT: snapshot clients=0')
            start.touch()
            deadline = time.perf_counter() + script['duration_ns'] / 1e9 / args.speed * 2 + 60
            while not result_file.exists():
                if process.poll() is not None or (external and external.poll() is not None):
                    raise ValueError('Arm/client exited during replay')
                if client and client.error:
                    raise ValueError('Client failed: ' + client.error)
                if time.perf_counter() >= deadline:
                    raise TimeoutError('Replay did not finish')
                if is_open:
                    count = snapshot(url)['clients']
                    result['client_counts'].append(count)
                    if count == 0:
                        raise ValueError('DEAD CLIENT: stream disappeared')
                time.sleep(.25)
            result.update(read_json(result_file))
            records = read_records(capture)
            result['records'] = records
            result['capture_sha256'] = sha(capture.read_bytes())
            result['coverage'] = compare(script, records, records, mappings, mappings)
            result['passed'] = result['passed'] and result['coverage']['passed'] and (
                result['received']['packet_stream_sha256'] == script['packet_stream_sha256'] and
                result['received']['packets_received'] == len(script['packets']))
            if not is_open:
                result['passed'] &= all(result[k]['clients'] == 0 for k in ('snapshot_before', 'snapshot_after'))
        except Exception as exc:
            result.update(passed=False, error=type(exc).__name__ + ': ' + str(exc))
        finally:
            if client:
                result['stream'] = client.close()
                result['passed'] &= result['stream']['thread_gone']
            if external:
                client_stop.touch()
                try:
                    external.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    result['passed'] = False
                result['client_cleanup'] = stop_process(external)
                if receipt.exists():
                    final = read_json(receipt)
                    result['stream'] = final
                    try:
                        result['browser_cleanup'] = verify_client_pids(final.get('browser_pids'), directory)
                    except Exception as exc:
                        result['browser_cleanup'] = {'gone': False, 'error': str(exc)}
                result['passed'] &= (result['client_cleanup']['pid_gone'] and result['client_cleanup']['exit_code'] == 0 and
                                     result.get('browser_cleanup', {}).get('gone', False))
            if is_open:
                result['live_valid'] = live_valid(result)
                result['passed'] &= result['live_valid']
            if process:
                result['cleanup'] = stop_process(process)
                result['passed'] &= result['cleanup']['pid_gone'] and result['cleanup']['was_alive']
            result.update(power_floor(result.get('samples', [])))
            result.update(every_message_floor(result.get('bridge_samples', [])))
            result['passed'] &= result['timing_status'] == 'VALID'
            if args.rule == 'm_bridge':
                result['passed'] &= result['every_message_timing_status'] == 'VALID'
    return result


def open_flags(runs):
    drops = all(type(i['arm'].get('stream', {}).get('dropped')) is int for i in runs if i['name'] == 'OPEN')
    live = all(i['arm'].get('live_valid') for i in runs if i['name'] == 'OPEN')
    return drops, live


def summarize_bridge(runs, script, identical):
    """Declared sdbar3 rule: M_bridge = t3 - t1_pre, M_post and the locked M_total beside it."""
    metrics = ('m_bridge_ms', 'm_post_ms', 'm_total_ms')
    worst_name = script.get('worst_case_segment')
    steps = {s['id']: s for s in script['steps']}
    grouped = {m: {name: [] for name in ARMS} for m in metrics}
    worst = {m: {name: [] for name in ARMS} for m in metrics}
    rows = []
    for item in runs:
        arm, name = item['arm'], item['name']
        joined = arm.get('bridge_samples', [])
        if not joined:
            raise ValueError('Zero M_bridge observations')
        values = {'m_bridge_ms': [s['m_bridge_ms'] for s in joined], 'm_post_ms': [s['m_post_ms'] for s in joined],
                  'm_total_ms': [s['latency_ms'] for s in arm['samples']]}
        row = {'repeat': item['repeat'], 'arm': name, 'load_status': item['load_status'],
               'counts': {'first_packet_join': len(arm['samples']), 'every_message': len(joined),
                          'every_message_cause_first_packet': sum(bool(s['first_packet']) for s in joined),
                          'every_message_cause_later_packet': sum(not s['first_packet'] for s in joined)},
               'statistics_ms': {m: stats(v) for m, v in values.items()}, **every_message_floor(joined)}
        for m in metrics:
            grouped[m][name].extend(values[m])
        if worst_name:
            chosen = [s for s in joined if s['cause_step'] is not None and steps[s['cause_step']].get('segment') == worst_name]
            locked = [s for s in arm['samples'] if steps[s['cause_step']].get('segment') == worst_name]
            if not chosen or not locked:
                raise ValueError('Zero worst-case M_bridge observations')
            picked = {'m_bridge_ms': [s['m_bridge_ms'] for s in chosen], 'm_post_ms': [s['m_post_ms'] for s in chosen],
                      'm_total_ms': [s['latency_ms'] for s in locked]}
            row['worst_case_statistics_ms'] = {m: stats(v) for m, v in picked.items()}
            for m in metrics:
                worst[m][name].extend(picked[m])
        rows.append(row)
    pooled = {m: {name: stats(v) for name, v in grouped[m].items()} for m in metrics}
    drops, live = open_flags(runs)
    rule = lambda triplet, valid: verdict(*triplet, identical=identical, dropped_reported=drops, live=live,
                                          valid_arms=valid, require_floor_resolution=False)
    outcome = rule([pooled['m_bridge_ms'][n] for n in ARMS],
                   all(r['every_message_timing_status'] == 'VALID' for r in rows))
    per_repeat = []
    for repeat in sorted({i['repeat'] for i in runs}):
        triplet = {r['arm']: r for r in rows if r['repeat'] == repeat}
        per_repeat.append({'repeat': repeat, **rule([triplet[n]['statistics_ms']['m_bridge_ms'] for n in ARMS],
            all(r['every_message_timing_status'] == 'VALID' for r in triplet.values()))})
    return {'metric': 'M_bridge = t3 - t1_pre (binding); M_post = t3 - t1_post and M_total = t3 - t0 (reported)',
            'rows': rows, 'pooled_ms': pooled, 'rule': outcome, 'per_repeat': per_repeat,
            'diagnostic_m_post_rule': rule([pooled['m_post_ms'][n] for n in ARMS], outcome['valid_arms']),
            'worst_case': {'name': worst_name, 'pooled_ms': {m: {n: stats(v) for n, v in worst[m].items()} for m in metrics}}
                          if worst_name else None}


def beside(result):
    """Both rules' pooled deltas on one line; the locked RED stays visible under --rule m_bridge."""
    line = {'rule': result.get('rule')}
    for key, summary in (('locked', result.get('summary')), ('m_bridge', result.get('m_bridge'))):
        if summary:
            line[key] = {'passed': summary['rule']['passed'], 'open_delta_ms': summary['rule']['open_delta_ms'],
                         'noise_floor_ms': summary['rule']['noise_floor_ms'], 'within': summary['rule']['within']}
    return line


def summarize(runs, script):
    grouped = {name: [] for name in ARMS}
    worst_grouped = {name: [] for name in ARMS}
    worst_name = script.get('worst_case_segment')
    steps = {s['id']: s for s in script['steps']}
    rows, per_repeat = [], []
    baseline = runs[0]['arm'].get('records', [])
    baseline_bytes = [(r['step'], r['bytes']) for r in baseline if r['record'] == 'midi']
    identical = bool(baseline_bytes)
    for item in runs:
        arm = item['arm']
        samples = arm.get('samples', [])
        values = [r['latency_ms'] for r in samples]
        if not values:
            raise ValueError('Zero latency observations')
        name = item['name']
        grouped[name].extend(values)
        same = [(r['step'], r['bytes']) for r in arm['records'] if r['record'] == 'midi'] == baseline_bytes
        identical &= same
        row = {'repeat': item['repeat'], 'arm': name, 'statistics_ms': stats(values), 'identical': same,
               'load_status': item['load_status'], 'publisher_dropped': arm['snapshot_after']['dropped'],
               'stream_dropped': arm.get('stream', {}).get('dropped'),
               'midi_messages': sum(r['record'] == 'midi' for r in arm['records']),
               **power_floor(samples)}
        if worst_name:
            worst_values = [s['latency_ms'] for s in samples if steps[s['cause_step']].get('segment') == worst_name]
            if not worst_values:
                raise ValueError('Zero worst-case latency observations')
            row['worst_case_statistics_ms'] = stats(worst_values)
            worst_grouped[name].extend(worst_values)
        rows.append(row)
    pooled = {name: stats(values) for name, values in grouped.items()}
    drops, live = open_flags(runs)
    outcome = verdict(pooled['CLOSED'], pooled['OPEN'], pooled['CLOSED-B'], identical=identical,
                      dropped_reported=drops, live=live,
                      valid_arms=all(r['timing_status'] == 'VALID' for r in rows))
    for repeat in sorted({i['repeat'] for i in runs}):
        triplet = {r['arm']: r for r in rows if r['repeat'] == repeat}
        per_repeat.append({'repeat': repeat, **verdict(*(triplet[n]['statistics_ms'] for n in ARMS),
            identical=all(r['identical'] for r in triplet.values()), dropped_reported=drops, live=live,
            valid_arms=all(r['timing_status'] == 'VALID' for r in triplet.values()))})
    outliers = sorted(({**s, 'repeat': i['repeat'], 'arm': i['name'], 'input': steps[s['cause_step']]}
                       for i in runs for s in i['arm']['samples']), key=lambda s: s['latency_ms'], reverse=True)[:5]
    return {'rows': rows, 'pooled_ms': pooled, 'rule': outcome, 'per_repeat': per_repeat,
            'worst_case': {'name': worst_name, 'pooled_ms': {n: stats(v) for n, v in worst_grouped.items()}} if worst_name else None,
            'byte_identical': identical, 'top_five_outliers': outliers,
            'null_control': {'passed': identical and all(
                abs(pooled['CLOSED'][k] - pooled['CLOSED-B'][k]) <=
                outcome['noise_floor_ms'][k] + BAR3_TOLERANCE_MS for k in STATISTICS),
                'note': 'Closed contrast uses the measured floor by definition; also requires nonempty identical bytes.'}}


def run(args):
    started = time.perf_counter()
    result = {'schema': 'sdlive-timing/1', 'passed': False, 'bar3_counts': False, 'runs': [],
              'command': [sys.executable, *sys.argv], 'repeats': args.repeats, 'speed': args.speed,
              'receiver_clock': args.clock, 'control': args.control, 'rule': args.rule,
              'tolerance_ms': BAR3_TOLERANCE_MS, 'client': args.client_cmd or 'python streaming reader',
              'clock_method': 'Sender and recorder use perf_counter_ns in ONE bridge process per arm.'}
    result['host'] = {'hostname': socket.gethostname(), 'platform': platform.platform(), 'python': sys.version}
    try:
        validate_scratch(args.scratch)
        args.scratch.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix='timing-', dir=args.scratch)).resolve()
        result['work'] = str(work)
        script = read_json(args.script)
        validate(script)
        result['script'] = script
        result['script_file_sha256'] = sha(args.script.read_bytes())
        result['instrument_sha256'] = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in KIT.iterdir() if p.is_file()}
        verified = verify_fixtures(args.fixtures)
        preset = args.preset.resolve()
        if str(preset) not in verified or preset.name != 'EDM Show.json':
            raise ValueError('Requires verified EDM Show fixture')
        raw = read_json(preset)
        if 'windows' not in raw.get('sections', {}):
            raise ValueError('Requires sectioned EDM Show and --preset-section windows')
        result['preset_sha256'] = sha(preset.read_bytes())
        tree = work / 'candidate'
        result['candidate'] = archive(args.repo, args.candidate, tree)
        config = tree / 'config'
        shutil.rmtree(config / 'presets')
        (config / 'presets').mkdir()
        (config / 'presets/replay.json').write_bytes(preset.read_bytes())
        (config / 'presets/.active').write_text('replay.json', encoding='ascii')
        (config / 'windows_midi_map.json').write_bytes(preset.read_bytes())
        (work / 'script.json').write_bytes(canonical(script))
        mappings = effective(raw, 'windows')['mappings']
        if args.control == 'sensitivity':
            source = tree / 'windows/live_events.py'
            original = source.read_text(encoding='utf-8')
            anchor = '        ticket = next(self._tickets)'
            if original.count(anchor) != 1:
                raise ValueError('Sensitivity mutation anchor drift')
            mutated = original.replace(anchor, '        if self._clients:\n            from timing_ab import sensitivity_delay\n            sensitivity_delay()\n' + anchor)
            source.write_text(mutated, encoding='utf-8')
            result['mutation'] = {'path': 'windows/live_events.py', 'before': sha(original.encode()),
                                  'after': sha(source.read_bytes()), 'sleep_seconds': .002,
                                  'delay_method': 'perf_counter_ns deadline + sleep(0) yields; minimum 2 ms'}
        names = ('OPEN',) if args.control == 'dead-client' else ARMS
        for repeat in range(1, args.repeats + 1):
            for name in names:
                guarded = guarded_arm(lambda attempt: run_arm(args, tree, work, script, mappings,
                    f'r{repeat}-{name}-try{attempt}'), foreign_load_check if args.rule == 'm_bridge' else load_check,
                    allow_unverified=args.allow_unverified_load, retries=args.load_retries)
                guarded.update(repeat=repeat, name=name)
                result['runs'].append(guarded)
                # Persist after each arm; all attempts and errors remain reviewable.
                write_result(args.out, result)
                print(json.dumps({'repeat': repeat, 'arm': name, 'load': guarded['load_status'],
                                  'accepted': guarded['accepted'], 'passed': guarded.get('arm', {}).get('passed'),
                                  **power_floor((guarded.get('arm') or {}).get('samples', [])),
                                  **every_message_floor((guarded.get('arm') or {}).get('bridge_samples', []))}), flush=True)
                if not guarded['accepted'] or not guarded['arm']['passed']:
                    raise ValueError('Invalid arm: ' + name)
        result['summary'] = summarize(result['runs'], script)
        result['m_bridge'] = summarize_bridge(result['runs'], script, result['summary']['byte_identical'])
        result['locked_rule_passed'] = result['summary']['rule']['passed']
        result['m_bridge_rule_passed'] = result['m_bridge']['rule']['passed']
        result['passed'] = result['m_bridge_rule_passed'] if args.rule == 'm_bridge' else result['locked_rule_passed']
        qualified = measurement_qualified(args, result['runs'])
        result['measurement_qualified'] = qualified
        if args.control == 'sensitivity':
            result['sensitivity_detected'] = not result['summary']['rule']['passed']
            result['sensitivity_timing_red'] = not all(result['summary']['rule']['within'].values())
            result['m_bridge_sensitivity_timing_red'] = not all(result['m_bridge']['rule']['within'].values())
            if args.rule == 'm_bridge' and not result['m_bridge_sensitivity_timing_red']:
                result['limitation'] = M_BRIDGE_INVALID
            elif not result['sensitivity_timing_red']:
                result['limitation'] = 'Instrument cannot see a 2 ms publisher delay with this noise floor; bar 3 does not count.'
        elif args.control is None:
            if args.sensitivity_result:
                import gzip
                payload = args.sensitivity_result.read_bytes()
                control = json.loads(gzip.decompress(payload) if payload[:2] == b'\x1f\x8b' else payload)
                result['sensitivity_receipt_sha256'] = sha(payload)
                result['sensitivity_valid'] = sensitivity_matches(control, result, args.rule)
            result['bar3_counts'] = result['passed'] and qualified and result.get('sensitivity_valid', False)
    except Exception as exc:
        result.update(passed=False, error=type(exc).__name__ + ': ' + str(exc))
    result['wall_seconds'] = time.perf_counter() - started
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', default='HEAD')
    parser.add_argument('--repo', type=Path, default=ROOT)
    parser.add_argument('--fixtures', type=Path, default=ROOT / '.showready/fixtures')
    parser.add_argument('--preset', type=Path, default=ROOT / '.showready/fixtures/mac/presets/EDM Show.json')
    parser.add_argument('--preset-section', choices=['windows'], default='windows')
    parser.add_argument('--script', type=Path, required=True)
    parser.add_argument('--scratch', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--speed', type=float, default=1)
    parser.add_argument('--clock', choices=['script', 'wall'], default='script')
    parser.add_argument('--allow-unverified-load', action='store_true', help='Diagnostics only; never bar 3 credit')
    parser.add_argument('--load-retries', type=int, default=3)
    parser.add_argument('--control', choices=['sensitivity', 'dead-client'])
    parser.add_argument('--rule', choices=RULES, default='locked',
                        help='locked (default) or the declared sdbar3 m_bridge rule; both are always printed')
    parser.add_argument('--sensitivity-result', type=Path)
    client = parser.add_mutually_exclusive_group()
    client.add_argument('--client-cmd', type=json.loads, help='JSON argv array; {url}, {stop}, {receipt} placeholders')
    client.add_argument('--client-cmd-file', type=Path, help='File-backed JSON argv for PowerShell native arguments')
    args = parser.parse_args()
    if args.client_cmd_file:
        args.client_cmd = read_json(args.client_cmd_file)
    if args.repeats < 1 or not 0 < args.speed <= 50 or args.load_retries < 1:
        parser.error('Requires repeats >=1 (clean qualification >=5; sensitivity >=3), 0<speed<=50, load-retries >=1')
    if args.client_cmd is not None and (not isinstance(args.client_cmd, list) or not args.client_cmd or
            not all(isinstance(s, str) for s in args.client_cmd) or
            not all(any(p in s for s in args.client_cmd) for p in ('{url}', '{stop}', '{receipt}'))):
        parser.error('--client-cmd requires a nonempty JSON argv array containing all three placeholders')
    result = run(args)
    path = write_result(args.out, result)
    # A provisional numeric pass is not an authoritative bar 3 pass.
    code = 0 if result['bar3_counts'] else 1 if not result['passed'] else 78
    # An M_bridge sensitivity run that is not a timing RED (or never produced a verdict) is INVALID.
    invalid = args.rule == 'm_bridge' and args.control == 'sensitivity' and result.get('m_bridge_sensitivity_timing_red') is not True
    if invalid:
        code = 3
    print(json.dumps({'BESIDE': beside(result)}))
    print(json.dumps({'result': str(path), 'rule': args.rule, 'rule_passed': result['passed'],
                      'locked_rule_passed': result.get('locked_rule_passed'), 'm_bridge_rule_passed': result.get('m_bridge_rule_passed'),
                      'bar3_counts': result['bar3_counts'],
                      'error': result.get('error'), 'limitation': result.get('limitation'), 'exit_code': code}))
    if invalid:
        print(M_BRIDGE_INVALID)
    if code == 78:
        print('HARNESS-SKIP: diagnostic or missing qualified sensitivity control; no bar 3 credit')
    return code


if __name__ == '__main__':
    sys.exit(main())
