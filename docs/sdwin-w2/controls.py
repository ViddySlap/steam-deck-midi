"""Fault controls use temporary copies; the captured fixtures stay read-only."""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--fixtures', type=Path, required=True)
parser.add_argument('--arms', type=Path, required=True)
parser.add_argument('--scratch', type=Path, required=True)
args = parser.parse_args()
verify = Path(__file__).with_name('verify.py')
analyze = Path(__file__).with_name('analyze.py')
results = []
with tempfile.TemporaryDirectory(dir=args.scratch) as tmp:
    root = Path(tmp)
    fixtures = root / 'fixtures'
    shutil.copytree(args.fixtures, fixtures)
    for p in fixtures.rglob('*'):
        if p.is_file(): p.chmod(0o600)
    arms = root / 'arms.json'
    original_arms = args.arms.read_bytes()
    arms.write_bytes(original_arms)
    command = [sys.executable, str(verify), '--fixtures', str(fixtures), '--arms', str(arms)]
    def check(label, expected):
        result = subprocess.run(command, capture_output=True, text=True)
        assert result.returncode == expected, (label, result.stderr, result.stdout)
        results.append(dict(control=label, exit=result.returncode, expected=expected,
                            detail=(result.stdout or result.stderr).strip()))
    check('pristine', 0)
    path = fixtures / 'windows-installed/presets/EDM Show.json'
    original = path.read_bytes()
    path.write_bytes(original + b' ')
    check('changed fixture byte', 1)
    path.write_bytes(original)
    check('fixture restored', 0)
    for label, mutate in [
        ('zero arm observations', lambda rows: rows.clear()),
        ('zero argv observations', lambda rows: rows[0].update(calls=[])),
        ('wrong backfill value', lambda rows: rows[0]['saved'].update(preset_section='wrong')),
        ('grandma settings changed', lambda rows: rows[1].update(settings_sha256_after='0'*64)),
        ('both process observations empty', lambda rows: rows[0].update(before=[],after=[])),
    ]:
        rows = json.loads(original_arms.decode('utf-8-sig'))
        mutate(rows)
        arms.write_text(json.dumps(rows))
        check(label, 1)
        arms.write_bytes(original_arms)
        check(label + ' restored', 0)
    # Differences are information, not a failure: assert the named key is detected.
    doc = json.loads(original.decode('utf-8-sig'))
    key = next(k for k,v in doc['mappings'].items() if v['type'] == 'note')
    doc['mappings'][key]['note'] = (doc['mappings'][key]['note'] + 1) % 128
    path.write_text(json.dumps(doc))
    out = root / 'analysis.json'
    result = subprocess.run([sys.executable, str(analyze), '--fixtures', str(fixtures), '--out', str(out)], capture_output=True)
    assert result.returncode == 0, result.stderr
    compared = json.loads(out.read_text())['comparisons']
    assert all(c['differing_mapping_keys'] == [key] and not c['sorted_json_equal'] for c in compared if c['preset'] == 'EDM Show')
    results.append(dict(control='changed mapping detected', key=key, result='differing_mapping_keys contains exactly the changed key'))
    path.write_bytes(original)
    check('all restored', 0)
print(json.dumps(results, indent=2))
