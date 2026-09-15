"""Recompute E4 counts, causal latencies, segment stats and raw-byte equality."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path


def distribution(values):
    ordered = sorted(values)
    assert ordered
    result = {'count': len(ordered), 'max': ordered[-1]}
    for name, percent in (('p50', 50), ('p95', 95), ('p99', 99)):
        position = (len(ordered) - 1) * percent / 100
        low = int(position)
        high = min(low + 1, len(ordered) - 1)
        result[name] = ordered[low] + (ordered[high] - ordered[low]) * (position - low)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('result', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    payload = args.result.read_bytes()
    result = json.loads(gzip.decompress(payload))
    script = result['script']
    steps = {s['id']: s for s in script['steps']}
    worst_name = script['worst_case_segment']
    baseline = None
    rows = []
    for run, summary in zip(result['runs'], result['summary']['rows'], strict=True):
        arm = run['arm']
        assert run['accepted'] and arm['passed'] and not arm['invalid']
        assert arm['received']['packets_received'] == len(script['packets'])
        assert arm['received']['packet_stream_sha256'] == script['packet_stream_sha256']
        assert arm['cleanup']['pid_gone'] and arm['cleanup']['was_alive']
        raw = [r for r in arm['records'] if r['record'] == 'midi']
        samples = [r for r in raw if r['step'] != -1]
        assert samples == arm['samples'] and len(samples) >= 1000
        assert len(samples) == arm['timed_midi_messages'] == summary['timed_midi_messages']
        assert arm['timing_status'] == summary['timing_status'] == 'VALID'
        values, worst = [], []
        for sample in samples:
            send = arm['sends'][str(sample['cause_step'])]
            assert sample['send_perf_counter_ns'] == send
            latency = (sample['perf_counter_ns'] - send) / 1e6
            assert latency >= 0 and latency == sample['latency_ms']
            values.append(latency)
            if steps[sample['cause_step']]['segment'] == worst_name:
                worst.append(latency)
        assert distribution(values) == summary['statistics_ms']
        assert distribution(worst) == summary['worst_case_statistics_ms']
        sequence = [(r['step'], r['bytes']) for r in raw]
        baseline = sequence if baseline is None else baseline
        assert sequence == baseline
        assert all(p['count'] > 0 and p['no_overspeed'] for p in arm['pacing'].values())
        if run['name'] == 'OPEN':
            assert arm['live_valid'] and arm['stream']['data_events'] > 0
            assert arm['stream']['thread_gone'] and not arm['stream']['error']
            assert all(c > 0 for c in arm['client_counts'])
        checks = [{k: a[k] for k in ('before', 'after', 'load_status')} for a in run['attempts']]
        assert all('exit_code' in a[k] for a in checks for k in ('before', 'after'))
        rows.append({**summary, 'wall_seconds': arm['wall_seconds'], 'checks': checks,
                     'cleanup': arm['cleanup'], 'stream_data_events': arm.get('stream', {}).get('data_events'),
                     'pacing': arm['pacing']})
    assert len(rows) == 3 and {r['arm'] for r in rows} == {'CLOSED', 'OPEN', 'CLOSED-B'}
    receipt = {'source': str(args.result), 'source_sha256': hashlib.sha256(payload).hexdigest(),
               'command': result['command'], 'candidate': result['candidate'],
               'instrument_sha256': result['instrument_sha256'], 'rows': rows,
               'worst_case': result['summary']['worst_case'], 'rule': result['summary']['rule'],
               'bar3_counts': result['bar3_counts'], 'measurement_qualified': result['measurement_qualified'],
               'wall_seconds': result.get('wall_seconds'), 'raw_verified': True}
    args.out.write_text(json.dumps(receipt, indent=2) + '\n', encoding='ascii')
    print(json.dumps({'raw_verified': True, 'rows': len(rows), 'out': str(args.out)}))


if __name__ == '__main__':
    main()
