import json, sys, tempfile, time, statistics
from pathlib import Path
sys.path.insert(0, ".")
from tests._engine_helpers import FakeOscClient, FakeRestClient, RecordingMidiOut
from windows.engines.autopilot import AutopilotEngine
cfg = json.loads(Path("config/engines.factory/autopilot.json").read_text())
def bench(state_dir, n=20000):
    e = AutopilotEngine("Autopilot", cfg, RecordingMidiOut(), rest_client=FakeRestClient(), osc_client=FakeOscClient(), state_dir=state_dir)
    e.on_midi_in(14, 64, 127, 0.0)
    samples = []
    for k in range(n):
        v = k % 128
        t0 = time.perf_counter_ns(); e.on_midi_in(14, 62, v, 0.0); samples.append(time.perf_counter_ns() - t0)
    t0 = time.perf_counter_ns(); e.shutdown(); close_ns = time.perf_counter_ns() - t0
    samples.sort()
    q = lambda p: samples[int(p * (len(samples) - 1))]
    return {"n": n, "p50_us": q(0.5) / 1000, "p99_us": q(0.99) / 1000, "max_us": samples[-1] / 1000, "shutdown_ms": close_ns / 1e6}
with tempfile.TemporaryDirectory(dir="/tmp/sdauto-a1") as d:
    print("no_state_dir", bench(None))
    print("state_dir   ", bench(Path(d) / "state"))
