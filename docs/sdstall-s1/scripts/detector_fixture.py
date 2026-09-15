"""Show the Recv-Q receiver-gap detector FIRES and DOES NOT FIRE, on fixtures.

No load is added to the machine: the positive arm's receiver sleeps, it does not
spin. Two arms, same sender rate as the pinned timing_script.json
(291.4 packets/s of 58.19 bytes, 16,954.8 bytes/s):

  NEGATIVE  receiver drains continuously  -> backlog must stay under 0.200 s
  POSITIVE  receiver sleeps STALL seconds -> backlog must exceed 1.000 s

It calls the SAME arm_watch.recvq() the real watch calls. Exit 0 only if the
negative arm stays below the fine trigger and the positive arm crosses the stack
trigger; any other combination is a detector that cannot be trusted.
"""
import json
import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from arm_watch import recvq, FINE_TRIGGER_S, STACK_TRIGGER_S, SCRIPT_BYTES_PER_S  # noqa: E402

RATE_HZ = 291.4
PAYLOAD = b'x' * 58
STALL_S = 2.5
RUN_S = 6.0


def arm(stall):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    stop = threading.Event()
    samples = []

    def receiver():
        sock.settimeout(0.1)
        t0 = time.time()
        slept = False
        while not stop.is_set():
            if stall and not slept and time.time() - t0 > 1.5:
                slept = True
                time.sleep(STALL_S)          # a sleep, not a spin: no CPU added
            try:
                sock.recv(2048)
            except socket.timeout:
                pass

    def sender():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        due = time.perf_counter()
        while not stop.is_set():
            due += 1.0 / RATE_HZ
            s.sendto(PAYLOAD, ('127.0.0.1', port))
            d = due - time.perf_counter()
            if d > 0:
                time.sleep(d)
        s.close()

    rt = threading.Thread(target=receiver, daemon=True)
    st = threading.Thread(target=sender, daemon=True)
    rt.start(); st.start()
    t0 = time.time()
    while time.time() - t0 < RUN_S:
        q = recvq(port)
        if q is not None:
            samples.append({'t': round(time.time() - t0, 3), 'recvq_bytes': q,
                            'backlog_s': round(q / SCRIPT_BYTES_PER_S, 4)})
        time.sleep(0.05)
    stop.set()
    rt.join(timeout=5); st.join(timeout=5)
    sock.close()
    return samples


out = {'fine_trigger_s': FINE_TRIGGER_S, 'stack_trigger_s': STACK_TRIGGER_S,
       'script_bytes_per_s': SCRIPT_BYTES_PER_S, 'sender_rate_hz': RATE_HZ,
       'stall_seconds_planted': STALL_S, 'arms': {}}
for name, stall in (('NEGATIVE-no-stall', False), ('POSITIVE-planted-stall', True)):
    s = arm(stall)
    mx = max((x['backlog_s'] for x in s), default=0.0)
    out['arms'][name] = {'samples': len(s), 'max_recvq_bytes': max((x['recvq_bytes'] for x in s), default=0),
                         'max_backlog_s': mx,
                         'crossed_fine_200ms': mx >= FINE_TRIGGER_S,
                         'crossed_stack_1s': mx >= STACK_TRIGGER_S,
                         'peak_samples': sorted(s, key=lambda x: -x['recvq_bytes'])[:3]}
neg, pos = out['arms']['NEGATIVE-no-stall'], out['arms']['POSITIVE-planted-stall']
out['detector_fires_on_a_stall'] = pos['crossed_stack_1s']
out['detector_silent_without_one'] = not neg['crossed_fine_200ms']
out['result'] = 'DETECTOR PROVEN BOTH WAYS' if (out['detector_fires_on_a_stall']
                                                and out['detector_silent_without_one']) else 'DETECTOR NOT PROVEN'
print(json.dumps(out, indent=1))
sys.exit(0 if out['result'] == 'DETECTOR PROVEN BOTH WAYS' else 1)
