"""Guarded E1 microbenchmarks. No timing credit if CPU-load checks are unreadable.

Run: .venv/bin/python -B docs/sdlive-e1/measure.py /tmp/sdlive-e1/timing.json
Bounds are watchdogs for accidental waits, not a claim of show-ready latency:
1000 datagrams may add at most 50 ms total (50 us each); 100000 full-buffer
publishes must finish within 1 second. E3/EG own the paced MIDI latency bar.
"""
import json
import logging
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.test_live_events import make_receiver
from protocol.messages import encode_action_event
from windows.live_events import LiveEvents


def guard():
    command = ["pgrep", "-f", "while True: pass"]
    result = subprocess.run(command, capture_output=True, text=True)
    return {"command": command, "exit": result.returncode, "stdout": result.stdout,
            "stderr": result.stderr, "empty": result.returncode == 1 and not result.stdout and not result.stderr}


def measure(operation, name, results):
    for attempt in range(3):
        pre = guard()
        row = {"arm": name, "attempt": attempt + 1, "before": pre}
        results.append(row)
        if not pre["empty"]:
            row["status"] = "UNVERIFIED-BY-EXECUTION: CPU inventory unavailable or occupied"
            row["after"] = guard()
            if pre["exit"] not in (0, 1):
                return None
            time.sleep(1)
            continue
        start = time.perf_counter_ns()
        observed = operation()
        elapsed = (time.perf_counter_ns() - start) / 1e9
        post = guard()
        row.update(after=post, elapsed_seconds=elapsed, observations=observed,
                   status="qualified" if post["empty"] else "discarded")
        if post["empty"]:
            return elapsed
    return None


def main():
    logging.disable(logging.CRITICAL)
    results = []
    full = LiveEvents(capacity=8)
    event = {"kind": "axis", "action": "X", "value": 123}
    def publish_full():
        for _ in range(100000):
            full.publish(event)
        snap = full.snapshot()
        assert snap["seq"] >= 100000 and snap["dropped"] >= 99992
        return {"seq": snap["seq"], "dropped": snap["dropped"], "clients": snap["clients"]}
    elapsed = measure(publish_full, "full-buffer-no-client", results)
    summary = {"command": [sys.executable, *sys.argv], "arms": results,
               "bounds": {"publish_seconds": 1, "stalled_minus_closed_seconds": .05}}
    code = 78
    if elapsed is not None:
        assert elapsed < 1, "full-buffer publication exceeded 1 second"
        payloads = [encode_action_event(action="BTN_A", state="down" if n % 2 == 0 else "up", seq=n)
                    for n in range(1000)]
        pairs = []
        for trial in range(5):
            pair = {}
            for opened in (False, True) if trial % 2 == 0 else (True, False):
                publisher = LiveEvents(capacity=8)
                receiver, backend = make_receiver(publisher)
                sub = publisher.subscribe() if opened else None
                stream = sub.stream() if sub else None
                if stream:
                    next(stream)
                assert publisher.snapshot()["clients"] == int(opened)
                def datagrams():
                    # Fresh sender identity on any discarded/retried arm.
                    receiver._sender_states.clear()
                    backend.order.clear()
                    for n, payload in enumerate(payloads):
                        assert receiver.handle_datagram(payload, ("127.0.0.1", 45678), now=10 + n * .001)
                    assert len(backend.order) == 1000
                    return {"midi_calls": len(backend.order), "clients": publisher.snapshot()["clients"]}
                try:
                    pair["open" if opened else "closed"] = measure(datagrams, f"trial-{trial}-{'open' if opened else 'closed'}", results)
                finally:
                    if stream:
                        stream.close()
            pairs.append(pair)
        summary["pairs"] = pairs
        if all(v is not None for p in pairs for v in p.values()):
            assert all(p["open"] - p["closed"] < .05 for p in pairs), "stalled consumer adds >=50 ms / 1000 datagrams"
            code = 0
    summary["status"] = "PASS" if code == 0 else "OWED TO THE GATE: no qualified timing arms"
    Path(sys.argv[1]).write_text(json.dumps(summary, indent=2) + "\n", encoding="ascii")
    print(json.dumps(summary, indent=2))
    if code == 78:
        print("HARNESS-SKIP: CPU inventory could not establish an empty synthetic-load set")
    return code


if __name__ == "__main__":
    sys.exit(main())
