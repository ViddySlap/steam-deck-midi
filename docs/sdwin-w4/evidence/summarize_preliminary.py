"""Exact local command used to recompute retained preliminary MIDI byte rows."""
import gzip
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/showready'))
from ab_run import compare
from deck_script import effective, read_json, verify_fixtures

fixtures = ROOT / '.showready/fixtures'
verify_fixtures(fixtures)
rows = []
cross = []
for label, relative, section, previous in [
    ('windows-edm', 'windows-installed/presets/EDM Show.json', None, 'windows-installed-edm-show'),
    ('windows-ptz', 'windows-installed/presets/PTZ.json', None, 'windows-installed-ptz'),
    ('windows-default', 'windows-installed/presets/default.json', None, 'windows-installed-default'),
    ('tracked-default', 'mac/presets/default.json', None, 'mac-default'),
    ('sectioned-edm', 'mac/presets/EDM Show.json', 'windows', 'mac-edm-show'),
    ('sectioned-ptz', 'mac/presets/PTZ.json', 'windows', 'mac-ptz'),
]:
    result = json.load(gzip.open(ROOT / 'docs/sdwin-w4/results/preliminary' / (label + '.json.gz')))
    mac = json.load(gzip.open(ROOT / 'docs/sdwin-w3/results' / (previous + '.json.gz')))
    raw = read_json(fixtures / relative)
    flat = read_json(Path(str(fixtures / relative) + '.v049.bak')) if section else raw
    def midi(arm):
        return [(r['step'], r['bytes']) for r in arm['records'] if r['record'] == 'midi']
    for arm in result['comparisons']:
        actual = compare(result['script'], result['arms']['A']['records'], result['arms'][arm]['records'], flat['mappings'], effective(raw, section)['mappings'])
        assert actual['passed'] and midi(result['arms']['A']) == midi(result['arms'][arm]) and midi(result['arms'][arm])
        rows.append({'preset': label, 'arm': arm, 'totals': actual['totals'], 'identical': True, 'not_covered': actual['not_covered'], 'credit': 'PRELIMINARY ONLY - coarse Windows clock'})
        cross.append({'preset': label, 'arm': arm, 'w3': previous, 'same_steps': result['script']['steps'] == mac['script']['steps'], 'same_packets': result['script']['packets'] == mac['script']['packets'], 'same_candidate_bytes': midi(result['arms'][arm]) == midi(mac['arms'][arm])})
output = ROOT / 'docs/sdwin-w4/evidence/preliminary/raw-summary.json'
output.write_text(json.dumps({'matrix': rows, 'cross_platform': cross}, indent=2) + '\n', encoding='ascii')
print(json.dumps({'matrix_rows': len(rows), 'all_raw_comparisons_pass': True, 'cross_platform_rows': cross}))
