"""Execute the named timing-rule assertion pristine, weakened, and restored."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
work = Path(tempfile.mkdtemp(prefix='mutation-', dir='/tmp/sdlive-e3'))
shutil.copytree(ROOT / 'scripts/showready', work / 'scripts/showready')
(work / 'tests').mkdir()
(work / 'tests/__init__.py').touch()
shutil.copyfile(ROOT / 'tests/test_showready_timing.py', work / 'tests/test_showready_timing.py')
source = work / 'scripts/showready/timing_ab.py'
original = source.read_bytes()
selector = 'tests.test_showready_timing.TimingTests.test_two_ms_shift_fails_and_small_shift_within_floor_passes'
command = [sys.executable, '-B', '-m', 'unittest', selector, '-v']
results = []
for phase in ('pristine', 'weakened', 'restored'):
    source.write_bytes(original.replace(b'within = {key: delta[key] <= floor[key] + BAR3_TOLERANCE_MS for key in STATISTICS}', b'within = {key: True for key in STATISTICS}') if phase == 'weakened' else original)
    run = subprocess.run(command, cwd=work, capture_output=True, text=True)
    (work / (phase + '.log')).write_text(run.stdout + run.stderr, encoding='utf-8')
    expected = 1 if phase == 'weakened' else 0
    assert run.returncode == expected, run.stdout + run.stderr
    if expected:
        assert 'AssertionError: True is not false' in run.stderr, run.stderr
    results.append({'phase': phase, 'command': command, 'exit_code': run.returncode,
                    'stdout': run.stdout, 'stderr': run.stderr})
assert source.read_bytes() == original
out = {'work': str(work), 'selector': selector, 'results': results, 'restored_byte_identical': True}
(ROOT / 'docs/sdlive-e3/mutation.json').write_text(json.dumps(out, indent=2) + '\n', encoding='ascii')
print(json.dumps(out))
