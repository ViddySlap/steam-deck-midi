"""sdstall S1 item b + c: per-arm environment record, receiver-gap watch, stall stacks.

One process per arm, started by closed_only.py just before the arm and stopped
just after it. It runs OUTSIDE the bridge process and reads only this arm's own
files, this arm's own UDP socket, and whole-machine counters.

  arm_watch.py --armdir DIR --label L --out DIR [--stack-budget-file F]

HOW THE GAP IS MEASURED, and why not the obvious way.
The declared stall is "the receiver's newest MIDI record is more than 1 s older
than the sender's newest send, equivalently an M_bridge sample > 1,000 ms".
The obvious live proxy - wall-clock silence in the arm's capture.jsonl - is
WRONG, and this link measured that before collecting any data. In the pinned
timing_script.json the SEND schedule never pauses (max gap between consecutive
packets 10.0 ms, 20,513 packets over 70.40 s, 291.4 packets/s, 16,954.8 bytes/s)
but the MIDI RECORD stream legitimately goes quiet for as long as 3,200 ms
(measured on an arm whose raw M_bridge max was 14.4 ms with ZERO samples over
100 ms). Record silence therefore does not mean the receiver stopped.

What does mean the receiver stopped is the arm's own UDP socket RECEIVE QUEUE:
the sender keeps delivering datagrams at 291/s into the kernel buffer, so if the
bridge's receive path stops, unconsumed bytes pile up there. This watch reads
Recv-Q for THIS ARM'S port from `netstat -an -p udp` (about 3 ms per read) and
converts it to a backlog in seconds at the script's own measured byte rate:

    backlog_s = recvq_bytes / 16954.8

That is the receiver's distance behind the sender, in the same units as the
declared rule. Observed healthy values are 0 with occasional single-digit
datagram bursts (305 bytes = 18 ms). 200 ms = 3,391 bytes; 1 s = 16,955 bytes.
Recv-Q is a kernel byte count and may include per-buffer overhead, so the
derived seconds are approximate; the RAW BYTES are recorded beside them.

The watch is a TRIGGER for sampling. The AUTHORITATIVE per-arm stall count is
recomputed afterwards from the arm's own bridge_samples (M_bridge = t3 - t1_pre)
in the raw result file, exactly as sdauto's census did. Record-stream silence is
still recorded, as a diagnostic, never as a stall.

ENVIRONMENT (item b): one record per second with a wall-clock timestamp -
vm_stat deltas (pageins, compressions, decompressions), the memory pressure
level from `sysctl -n kern.memorystatus_vm_pressure_level`, wired pages, load1.
`~/.lmstudio/bin/lms ps` STATUS every LMS_BASE_S seconds. READ-ONLY: `lms ps` is
the only lms verb this link runs; no model is ever loaded, unloaded or stopped.

FINE-GRAINED (MASTER 13 16:41 (2)): the moment the backlog exceeds
FINE_TRIGGER_S, `lms ps` and vm_stat are polled every FINE_INTERVAL_S until it
clears. Those records carry "fine": true. The lms thread wakes every 0.25 s and
decides then, so it cannot sleep through a whole episode. The continuous 1 s
record is a superset of the required 60 s ring around every stall.

STACKS (item c): when the backlog exceeds STACK_TRIGGER_S, `sample <bridge pid>
2 -file <path>` is run against THIS ARM'S OWN bridge process, found by matching
this arm's capture.jsonl path in `ps -A -o pid=,command=`. No process this link
did not start is ever sampled. ONE stack per gap episode, at most
STACK_MAX_PER_ARM per arm and --stack-budget per revision. `sample` suspends the
target while it walks stacks, so every stack record carries the wall seconds the
command took and the arm is marked as sampled.

Sampling runs in helper threads so a slow `lms ps` or `sample` never delays the
backlog poll itself.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import signal
import sys
import threading
import time

POLL_S = 0.05
ENV_INTERVAL_S = 1.0
LMS_BASE_S = 5.0
LMS_TICK_S = 0.25
FINE_TRIGGER_S = 0.200
FINE_INTERVAL_S = 0.5
STACK_TRIGGER_S = 1.0
STACK_MAX_PER_ARM = 3
SCRIPT_BYTES_PER_S = 16954.8   # timing_script.json: 1,193,616 payload bytes / 70.40 s
LMS = os.path.expanduser('~/.lmstudio/bin/lms')

stop = threading.Event()


def run(argv, timeout=20):
    t0 = time.time()
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return {'exit': p.returncode, 'out': p.stdout, 'err': p.stderr, 'seconds': time.time() - t0}
    except Exception as exc:
        return {'exit': None, 'error': repr(exc), 'seconds': time.time() - t0, 'out': '', 'err': ''}


def vm_stat():
    r = run(['vm_stat'], timeout=10)
    out = {}
    for line in (r.get('out') or '').splitlines():
        m = re.match(r'"?([A-Za-z][^":]*)"?:\s+(\d+)\.?', line)
        if m:
            out[m.group(1).strip()] = int(m.group(2))
    return out


def sysctl_int(name):
    r = run(['sysctl', '-n', name], timeout=10)
    try:
        return int((r.get('out') or '').strip())
    except ValueError:
        return None


def load1():
    r = run(['sysctl', '-n', 'vm.loadavg'], timeout=10)
    try:
        return float((r.get('out') or '').split()[1])
    except (IndexError, ValueError):
        return None


def lms_ps():
    """READ-ONLY. The only lms verb this link runs."""
    r = run([LMS, 'ps'], timeout=25)
    rows = []
    for line in (r.get('out') or '').splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0] != 'IDENTIFIER':
            rows.append({'identifier': parts[0], 'status': parts[2]})
    return {'rows': rows, 'exit': r.get('exit'), 'seconds': r.get('seconds'),
            'statuses': sorted({x['status'] for x in rows})}


def bridge_process(capture_path):
    """This arm's own capture_runner.py child: pid and its --listen UDP port."""
    r = run(['ps', '-A', '-o', 'pid=,command='], timeout=15)
    hits = []
    for line in (r.get('out') or '').splitlines():
        s = line.strip()
        if capture_path in s and 'capture_runner.py' in s and 'arm_watch.py' not in s:
            m = re.search(r'--listen 127\.0\.0\.1:(\d+)', s)
            hits.append((int(s.split(None, 1)[0]), int(m.group(1)) if m else None))
    return hits[0] if len(hits) == 1 else (None, None)


def recvq(port):
    """Recv-Q bytes on this arm's UDP port, from netstat. None if not readable."""
    r = run(['netstat', '-an', '-p', 'udp'], timeout=10)
    for line in (r.get('out') or '').splitlines():
        f = line.split()
        if len(f) >= 4 and f[0].startswith('udp') and f[3].endswith('.' + str(port)):
            try:
                return int(f[1])
            except ValueError:
                return None
    return None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--armdir', type=Path, required=True)
    p.add_argument('--label', required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--stack-budget-file', type=Path)
    p.add_argument('--stack-budget', type=int, default=10)
    p.add_argument('--fine-always', action='store_true',
                   help='MASTER 13 17:39: arm fine sampling FROM THE FIRST ARM instead of at the '
                        '200 ms trigger. For the DIAGNOSTIC-UNDER-LOAD session only.')
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    stacks_dir = a.out / (a.label + '.stacks')
    capture = a.armdir / 'capture.jsonl'
    result_file = a.armdir / 'timing.json'

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())

    envf = (a.out / (a.label + '.env.jsonl')).open('w', buffering=1)
    gapf = (a.out / (a.label + '.gaps.jsonl')).open('w', buffering=1)
    qf = (a.out / (a.label + '.recvq.jsonl')).open('w', buffering=1)
    lock = threading.Lock()
    st = {'fine': bool(a.fine_always), 'fine_always': bool(a.fine_always), 'bridge_pid': None, 'udp_port': None, 'stacks': 0, 'episode_sampled': False,
          'max_recvq_bytes': 0, 'max_backlog_s': 0.0, 'episodes_over_200ms': 0, 'episodes_over_1s': 0,
          'max_record_silence_s': 0.0, 'lms_polls': 0, 'lms_seconds': 0.0, 'sample_seconds': 0.0,
          'statuses_seen': set(), 'fine_statuses_seen': set(), 'fine_samples': 0,
          'processingprompt_fine': 0, 'processingprompt_any': 0, 'recvq_unreadable': 0}

    def env_sample(fine, backlog_s, recvq_bytes):
        now = time.time()
        vs = vm_stat()
        return {'t': now, 'hms': time.strftime('%H:%M:%S', time.localtime(now)),
                'ms': int(now * 1000) % 1000, 'fine': fine,
                'backlog_s': backlog_s, 'recvq_bytes': recvq_bytes,
                'load1': load1(),
                'pressure_level': sysctl_int('kern.memorystatus_vm_pressure_level'),
                'pressure_source': 'sysctl -n kern.memorystatus_vm_pressure_level',
                'wired_pages': vs.get('Pages wired down'), 'pages_free': vs.get('Pages free'),
                'vm_stat': {k: vs.get(k) for k in
                            ('Pageins', 'Pageouts', 'Swapins', 'Swapouts', 'Compressions',
                             'Decompressions', 'Pages stored in compressor',
                             'Pages occupied by compressor')}}

    def emit(rec):
        with lock:
            envf.write(json.dumps(rec) + '\n')

    def lms_thread():
        last = 0.0
        while not stop.is_set():
            due = FINE_INTERVAL_S if st['fine'] else LMS_BASE_S
            now = time.time()
            if now - last >= due:
                fine = st['fine']
                ps = lms_ps()
                last = time.time()
                with lock:
                    st['lms_polls'] += 1
                    st['lms_seconds'] += ps.get('seconds') or 0
                    st['statuses_seen'].update(ps['statuses'])
                    if 'PROCESSINGPROMPT' in ps['statuses']:
                        st['processingprompt_any'] += 1
                    if fine:
                        st['fine_statuses_seen'].update(ps['statuses'])
                        st['fine_samples'] += 1
                        if 'PROCESSINGPROMPT' in ps['statuses']:
                            st['processingprompt_fine'] += 1
                    envf.write(json.dumps({'t': last, 'hms': time.strftime('%H:%M:%S', time.localtime(last)),
                                           'record': 'lms', 'fine': fine, 'lms': ps}) + '\n')
            stop.wait(LMS_TICK_S)

    def take_stack(backlog_s, recvq_bytes):
        pid = st['bridge_pid']
        if pid is None:
            return
        if a.stack_budget_file is not None:
            try:
                used = int(a.stack_budget_file.read_text()) if a.stack_budget_file.exists() else 0
            except ValueError:
                used = 0
            if used >= a.stack_budget:
                return
            a.stack_budget_file.write_text(str(used + 1))
        stacks_dir.mkdir(parents=True, exist_ok=True)
        path = stacks_dir / ('%s-%s-%.3fs.txt' % (a.label, time.strftime('%H%M%S'), backlog_s))
        t0 = time.time()
        r = run(['sample', str(pid), '2', '-file', str(path)], timeout=60)
        cost = time.time() - t0
        with lock:
            st['sample_seconds'] += cost
            gapf.write(json.dumps({'record': 'stack', 't': t0,
                                   'hms': time.strftime('%H:%M:%S', time.localtime(t0)),
                                   'backlog_s': backlog_s, 'recvq_bytes': recvq_bytes, 'pid': pid,
                                   'file': str(path),
                                   'sample_command': 'sample %d 2 -file %s' % (pid, path),
                                   'sample_wall_seconds': cost, 'exit': r.get('exit'),
                                   'stderr': (r.get('err') or '')[:400]}) + '\n')

    threading.Thread(target=lms_thread, daemon=True).start()

    last_size, last_change, next_env = -1, None, 0.0
    next_fine, episode_start, started = 0.0, None, False
    while not stop.is_set():
        now = time.time()
        if st['bridge_pid'] is None:
            st['bridge_pid'], st['udp_port'] = bridge_process(str(capture))
        q = recvq(st['udp_port']) if st['udp_port'] else None
        if st['udp_port'] and q is None:
            st['recvq_unreadable'] += 1
        backlog = (q / SCRIPT_BYTES_PER_S) if q is not None else None
        try:
            size = capture.stat().st_size
        except OSError:
            size = -1
        if size > last_size:
            last_size, last_change = size, now
            started = started or size > 0
        elif started and last_change is not None and not result_file.exists():
            st['max_record_silence_s'] = max(st['max_record_silence_s'], now - last_change)
        if q is not None:
            with lock:
                qf.write(json.dumps({'t': now, 'hms': time.strftime('%H:%M:%S', time.localtime(now)),
                                     'recvq_bytes': q, 'backlog_s': round(backlog, 4),
                                     'record_silence_s': round(now - last_change, 3) if last_change else None}) + '\n')
            st['max_recvq_bytes'] = max(st['max_recvq_bytes'], q)
            st['max_backlog_s'] = max(st['max_backlog_s'], backlog)
            if backlog >= FINE_TRIGGER_S:
                if not st['fine']:
                    st['fine'] = True
                    st['episodes_over_200ms'] += 1
                    st['episode_sampled'] = False
                    episode_start = now
                    with lock:
                        gapf.write(json.dumps({'record': 'gap_open', 't': now,
                                               'hms': time.strftime('%H:%M:%S', time.localtime(now)),
                                               'backlog_s': backlog, 'recvq_bytes': q,
                                               'threshold_s': FINE_TRIGGER_S,
                                               'bridge_pid': st['bridge_pid'], 'udp_port': st['udp_port']}) + '\n')
                    next_fine = 0.0
                if backlog >= STACK_TRIGGER_S and not st['episode_sampled'] and st['stacks'] < STACK_MAX_PER_ARM:
                    st['episode_sampled'] = True
                    st['stacks'] += 1
                    st['episodes_over_1s'] += 1
                    threading.Thread(target=take_stack, args=(backlog, q), daemon=True).start()
                if now >= next_fine:
                    next_fine = now + FINE_INTERVAL_S
                    threading.Thread(target=lambda b=backlog, n=q: emit(env_sample(True, b, n)), daemon=True).start()
            elif st['fine'] and not a.fine_always:
                st['fine'] = False
                with lock:
                    gapf.write(json.dumps({'record': 'gap_closed', 't': now,
                                           'hms': time.strftime('%H:%M:%S', time.localtime(now)),
                                           'episode_seconds': now - episode_start if episode_start else None,
                                           'backlog_s': backlog, 'recvq_bytes': q}) + '\n')
        if a.fine_always and now >= next_fine:
            next_fine = now + FINE_INTERVAL_S
            threading.Thread(target=lambda b=backlog, n=q: emit(env_sample(True, b, n)), daemon=True).start()
        if now >= next_env:
            next_env = now + ENV_INTERVAL_S
            threading.Thread(target=lambda b=backlog, n=q: emit(env_sample(False, b, n)), daemon=True).start()
        time.sleep(POLL_S)

    summary = {k: (sorted(v) if isinstance(v, set) else v) for k, v in st.items()}
    summary.update(label=a.label, armdir=str(a.armdir), script_bytes_per_s=SCRIPT_BYTES_PER_S,
                   fine_trigger_s=FINE_TRIGGER_S, stack_trigger_s=STACK_TRIGGER_S,
                   note='backlog_s = Recv-Q bytes on this arm UDP port / 16954.8 bytes-per-second; '
                        'record_silence is a diagnostic only (natural silences reach 3.2 s)')
    (a.out / (a.label + '.watch.json')).write_text(json.dumps(summary, indent=1))
    envf.close(); gapf.close(); qf.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
