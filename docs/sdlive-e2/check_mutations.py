"""Require pristine, named mutation RED, and byte-restored GREEN in scratch."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/sdlive-e2/mutations').resolve()
if not BASE.is_relative_to(Path('/tmp/sdlive-e2').resolve()):
    raise SystemExit('scratch must be under /tmp/sdlive-e2')
BASE.mkdir(parents=True, exist_ok=True)
WORK = Path(tempfile.mkdtemp(prefix='proof-', dir=BASE))
shutil.copytree(ROOT / 'windows/static', WORK / 'static')
shutil.copyfile(ROOT / 'tests/ui_controller_check.cjs', WORK / 'check.cjs')
NODE = shutil.which('node')
assert NODE, 'NODE-ABSENT'
COMMAND = [NODE, str(WORK / 'check.cjs'), str(WORK / 'static/index.html')]
results = []


def run(name, assertion=None):
    result = subprocess.run(COMMAND, cwd=WORK, capture_output=True, text=True,
                            timeout=120, env={**os.environ, 'TMPDIR': str(BASE)})
    output = result.stdout + result.stderr
    log = WORK / (name + '.log')
    log.write_text(output, encoding='ascii', errors='backslashreplace')
    results.append({'name': name, 'command': COMMAND, 'cwd': str(WORK),
                    'exit': result.returncode, 'expected': 'RED' if assertion else 'GREEN',
                    'assertion': assertion, 'log': str(log)})
    (WORK / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    if assertion:
        assert result.returncode == 1 and 'AssertionError' in output and assertion in output, output
    else:
        assert result.returncode == 0, output
    print(name, 'RED' if assertion else 'GREEN', 'exit', result.returncode, flush=True)


run('pristine')
mutations = [
    ('group-order', 'Object.keys(TAGS).filter(name => control.groups[name]?.some(id => pressed.has(id)))',
     'Object.keys(control.groups).filter(name => control.groups[name]?.some(id => pressed.has(id)))',
     'group tags use tap/hold/layer order'),
    ('highlight', "visual.shape.classList.toggle('control-down', down);",
     "visual.shape.classList.toggle('control-down', false);", 'input down lights the physical shape'),
    ('stick-position', "control.anchor.x + normalized(analog[0]) * 30",
     "control.anchor.x", 'axis moves stick dot to computed X'),
    ('row-flash', "row.classList.toggle('controller-midi-flash', flashes.has(row.dataset.action));",
     "row.classList.toggle('controller-midi-flash', false);", 'MIDI flashes matching row only'),
    ('follow-edit-guard', "if (!card.hasUnsavedEdit() && card.currentControl() !== pendingFollow)",
     "if (card.currentControl() !== pendingFollow)", 'follow cannot switch cards over an unsaved inline edit'),
    ('frame-coalescing', 'enabled() && frame === null && !painting',
     'enabled() && !painting', '500 axis events schedule one animation frame'),
    ('close-stream', 'source?.close(); source = null;',
     'source = null;', 'dropped stream closes before resync'),
]
target = WORK / 'static/controller/controller_live.js'
for name, before, after, assertion in mutations:
    original = target.read_bytes()
    assert original.count(before.encode()) == 1, (name, 'replace exactly once')
    try:
        target.write_bytes(original.replace(before.encode(), after.encode()))
        run(name, assertion)
    finally:
        target.write_bytes(original)
    assert target.read_bytes() == original
    run(name + '-restored')
print('Evidence:', WORK / 'results.json')
