"""Prove the power-floor and causal-segment assertions GREEN/RED/GREEN."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
scratch = Path('/tmp/sdlive-e4')
scratch.mkdir(exist_ok=True)
work = Path(tempfile.mkdtemp(prefix='mutations-', dir=scratch))
shutil.copytree(ROOT / 'scripts/showready', work / 'scripts/showready')
(work / 'tests').mkdir()
(work / 'tests/__init__.py').touch()
shutil.copyfile(ROOT / 'tests/test_showready_timing_script.py', work / 'tests/test_showready_timing_script.py')
source = work / 'scripts/showready/timing_ab.py'
original = source.read_bytes()
controls = [
    ('floor-classification', 'test_power_floor_999_is_invalid_and_blocks_otherwise_green_verdict',
     b"'VALID' if count >= MIN_TIMED_MIDI_MESSAGES else 'INVALID'", b"'VALID'",
     "AssertionError: 'VALID' != 'INVALID'"),
    ('floor-verdict', 'test_power_floor_999_is_invalid_and_blocks_otherwise_green_verdict',
     b' and sensitivity_visible and valid_arms}', b' and sensitivity_visible}',
     'AssertionError: True is not false'),
    ('segment-population', 'test_segment_statistics_use_only_own_causal_messages',
     b" if steps[s['cause_step']].get('segment') == worst_name", b'',
     'AssertionError: 1000 != 4'),
]
results = []
for name, selector, anchor, replacement, failure in controls:
    assert original.count(anchor) == 1, name
    command = [sys.executable, '-B', '-m', 'unittest',
               'tests.test_showready_timing_script.TimingScriptTests.' + selector, '-v']
    for phase in ('pristine', 'reverted', 'restored'):
        source.write_bytes(original.replace(anchor, replacement) if phase == 'reverted' else original)
        result = subprocess.run(command, cwd=work, capture_output=True, text=True)
        expected = 1 if phase == 'reverted' else 0
        assert result.returncode == expected, result.stdout + result.stderr
        if expected:
            assert failure in result.stderr, result.stderr
        results.append({'control': name, 'phase': phase, 'command': command,
                        'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
assert source.read_bytes() == original
receipt = {'work': str(work), 'restored_byte_identical': True, 'results': results}
target = ROOT / 'docs/sdlive-e4/evidence/mutations.json'
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(receipt, indent=2) + '\n', encoding='ascii')
print(json.dumps({'receipt': str(target), 'controls': len(controls), 'runs': len(results), 'passed': True}))
