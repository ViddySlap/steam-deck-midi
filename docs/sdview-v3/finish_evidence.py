import gzip
import hashlib
import json
import os
from pathlib import Path

root = Path('/Users/viddyslap/Documents/project-workspaces/steam-deck-midi')
scratch = Path('/tmp/sdview-v3')
expected = 'bb619c6f223f9e85a3022f3acf78e54dae0692b4'
command = "TMPDIR=/tmp/sdview-v3 .venv/bin/python -B scripts/showready/ab_run.py --candidate HEAD --preset '.showready/fixtures/mac/presets/EDM Show.json' --section windows --script /tmp/sdview-v3/deck-script.json --scratch /tmp/sdview-v3/ab-final --out /tmp/sdview-v3/mac-edm-final.json"
all_absence = {}
results = {}
for name in ('mac-edm', 'mac-edm-final'):
    path = scratch / (name + '.json.gz')
    if not path.exists():
        path = scratch / (name + '.json')
    payload = path.read_bytes()
    result = json.loads(gzip.decompress(payload) if path.suffix == '.gz' else payload)
    assert result['passed'] is True, (name, result.get('error'), result.get('comparisons'))
    assert set(result['arms']) == {'A', 'B1', 'B2'}
    absence = {}
    for arm, data in result['arms'].items():
        assert data['cleanup']['pid_gone'] is True
        try:
            os.kill(data['pid'], 0)
        except ProcessLookupError:
            absence[arm] = {'pid': data['pid'], 'gone': True, 'proof': 'os.kill(pid, 0) raised ProcessLookupError'}
        else:
            raise AssertionError((name, arm, data['pid'], 'still present'))
    all_absence[name] = absence
    results[name] = (result, path, hashlib.sha256(payload).hexdigest())
result, path, digest = results['mac-edm-final']
assert result['arms']['B1']['commit'] == expected
assert result['arms']['B2']['commit'] == expected
summary = {key: value for key, value in result.items() if key not in ('script', 'arms', 'comparisons')}
summary.update(command=command, raw_result=str(path), raw_result_sha256=digest,
               verdict_line=json.loads((scratch / 'ab-final.log').read_text().strip().splitlines()[-1]),
               arms={name: {key: value for key, value in data.items() if key != 'records'} for name, data in result['arms'].items()},
               comparisons={name: {key: value for key, value in data.items() if key != 'steps'} for name, data in result['comparisons'].items()},
               independent_pid_absence=all_absence['mac-edm-final'],
               earlier_replay={'raw_result': str(results['mac-edm'][1]), 'sha256': results['mac-edm'][2],
                               'candidate_commit': results['mac-edm'][0]['arms']['B1']['commit'],
                               'passed': True, 'independent_pid_absence': all_absence['mac-edm']})
(root / 'docs/sdview-v3/midi-verdict.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
print(json.dumps({'candidate_commit': expected, 'passed': result['passed'],
                  'comparisons': summary['verdict_line']['comparisons'],
                  'raw_result_sha256': digest, 'independent_pid_absence': all_absence}, indent=2))
