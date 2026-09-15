"""Bounded real-browser hook control; accelerated and never bar 3 credit."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/showready'))
from timing_ab import guarded_arm, run_arm
from ab_run import archive, write_result
from deck_script import canonical, effective, read_json, validate, verify_fixtures

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--script', type=Path, required=True)
parser.add_argument('--chromium', required=True)
args = parser.parse_args()
verified = verify_fixtures(ROOT / '.showready/fixtures')
preset = ROOT / '.showready/fixtures/mac/presets/EDM Show.json'
assert str(preset.resolve()) in verified
script = read_json(args.script)
validate(script)
work = Path(tempfile.mkdtemp(prefix='browser-hook-', dir='/tmp/sdlive-e3')).resolve()
tree = work / 'candidate'
identity = archive(ROOT, 'HEAD', tree)
config = tree / 'config'
shutil.rmtree(config / 'presets')
(config / 'presets').mkdir()
(config / 'presets/replay.json').write_bytes(preset.read_bytes())
(config / 'presets/.active').write_text('replay.json')
(config / 'windows_midi_map.json').write_bytes(preset.read_bytes())
(work / 'script.json').write_bytes(canonical(script))
args.control = None
args.speed = 50
args.clock = 'script'
args.client_cmd = ['node', str(ROOT / 'scripts/showready/timing_browser.cjs'),
                   '{url}', '{stop}', '{receipt}', args.chromium, '--single-process']
result = guarded_arm(lambda n: run_arm(args, tree, work, script, effective(read_json(preset), 'windows')['mappings'],
                                       f'r1-OPEN-try{n}'), allow_unverified=True)
result.update(candidate=identity, command=[sys.executable, *sys.argv], qualification='ACCELERATED HOOK CONTROL ONLY')
out = write_result(Path('/tmp/sdlive-e3/browser-hook.json.gz'), result)
print(json.dumps({'out': str(out), 'accepted': result['accepted'], 'passed': result.get('arm', {}).get('passed'),
                  'error': result.get('arm', {}).get('error')}))
assert result['accepted'] and result['arm']['passed'], result.get('arm', {}).get('error')
