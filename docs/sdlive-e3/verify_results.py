"""Recompute timing evidence from raw MIDI rows, never the summary verdict."""
import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/showready'))
from deck_script import validate
from timing_ab import stats, summarize

results = []
for argument in sys.argv[1:]:
    path = Path(argument)
    data = path.read_bytes()
    result = json.loads(gzip.decompress(data) if data[:2] == b'\x1f\x8b' else data)
    validate(result['script'])
    baseline = None
    arms = []
    for run in result['runs']:
        arm = run['arm']
        assert run['accepted'] and arm['passed']
        assert arm['cleanup']['pid_gone'] and arm['cleanup']['was_alive']
        assert len(run['attempts']) >= 1
        for attempt in run['attempts']:
            for key in ('before', 'after'):
                check = attempt[key]
                assert check['status'] in ('empty', 'unreadable', 'not applicable', 'load-present')
                if check['status'] != 'not applicable':
                    assert check['load_average'] is not None
                    assert 'exit_code' in check and 'stderr' in check
        midi = [row for row in arm['records'] if row['record'] == 'midi']
        sequence = [(r['step'], r['bytes']) for r in midi]
        if baseline is None:
            baseline = sequence
        assert sequence == baseline and len(sequence) > 0
        measured = [r for r in midi if r['step'] != -1]
        assert measured == arm['samples'] and measured
        for row in measured:
            assert row['send_perf_counter_ns'] == arm['sends'][str(row['cause_step'])]
            assert row['perf_counter_ns'] == row['monotonic_ns']
            latency = (row['perf_counter_ns'] - row['send_perf_counter_ns']) / 1e6
            assert latency >= 0 and latency == row['latency_ms']
        assert arm['received']['packets_received'] == len(result['script']['packets'])
        assert arm['received']['packet_stream_sha256'] == result['script']['packet_stream_sha256']
        if run['name'] == 'OPEN':
            stream = arm['stream']
            assert stream['data_events'] > 0 and all(n > 0 for n in arm['client_counts'])
            if 'events' in stream:
                assert sum(e.get('count', 0) for e in stream['events'] if e['kind'] == 'dropped') == stream['dropped']
            assert type(stream['dropped']) is int
        else:
            assert arm['snapshot_before']['clients'] == arm['snapshot_after']['clients'] == 0
        arms.append({'repeat': run['repeat'], 'arm': run['name'], 'midi_messages': len(midi),
                     'latency_samples': len(measured), 'pid_gone': True,
                     'statistics_ms': stats([r['latency_ms'] for r in measured])})
    assert len(arms) == 3 * result['repeats'] and result['repeats'] >= 5
    recomputed = summarize(result['runs'], result['script'])
    assert recomputed == result['summary']
    results.append({'path': str(path), 'arms': arms, 'raw_verified': True,
                    'rule': recomputed['rule'], 'bar3_counts': result['bar3_counts']})
print(json.dumps(results, indent=2))
