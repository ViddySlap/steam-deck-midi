"""Prove controller assertions bite using source mutations in scratch only."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/sdview-v3/mutations').resolve()
BASE.mkdir(parents=True, exist_ok=True)
WORK = Path(tempfile.mkdtemp(prefix='proof-', dir=BASE))
shutil.copytree(ROOT / 'windows/static', WORK / 'static')
shutil.copy2(ROOT / 'tests/ui_controller_check.cjs', WORK / 'check.cjs')
NODE = shutil.which('node')
assert NODE, 'NODE-ABSENT: mutation proof requires node'
COMMAND = [NODE, str(WORK / 'check.cjs'), str(WORK / 'static/index.html')]
results = []


def run(name, red=False, assertion=''):
    result = subprocess.run(COMMAND, cwd=WORK, text=True, capture_output=True,
                            timeout=120, env={**os.environ, 'TMPDIR': str(BASE)})
    output = result.stdout + result.stderr
    log = WORK / (name + '.log')
    log.write_text(output)
    results.append({'name': name, 'command': COMMAND, 'cwd': str(WORK),
                    'exit': result.returncode, 'expected': 'RED' if red else 'GREEN',
                    'assertion': assertion, 'log': str(log)})
    (WORK / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    if red:
        assert result.returncode != 0 and 'AssertionError' in output and assertion in output, output
    else:
        assert result.returncode == 0, output
    print(name, 'RED' if red else 'GREEN', 'exit', result.returncode, flush=True)


run('pristine')
mutations = [
    ('field-apply', 'const spec = readFields(type.value, fields, prefix);',
     'const spec = {...DEFAULTS[type.value]};', 'note form commits its own fields'),
    ('draft-tracking', '      draft.dirty = true;\n      formDirty = true;\n      editRevision++;',
     '      draft.dirty = false;', 'typed inline field participates in draft listener'),
    ('foreign-json', "          if (!ids.includes(id)) throw new Error(id + ' does not belong to this control.');",
     '', 'bad Advanced input commits nothing'),
    ('shape-preflight', "            renderFields(spec.type, spec, document.createElement('div'), 'controller_check_', document.createElement('div'));",
     '', 'Advanced shape errors are inline before any commit'),
    ('conflict-mark', "        row.classList.toggle('controller-conflict', conflicting.has(action));",
     '', 'open control conflicting row marked'),
    ('macro-apply', '        applyMacroToAction(macro, action);', '', 'inline macro merge matches List'),
    ('sibling-draft', '  function refresh(action = null) {\n    if (!map) return;',
     '  function refresh(action = null) {\n    if (!map) return;\n    editors.clear();',
     'sibling commit preserves typed fields'),
]
target = WORK / 'static/controller/controller_view.js'
for name, before, after, assertion in mutations:
    original = target.read_text()
    assert original.count(before) == 1, (name, 'mutation must replace exactly once')
    try:
        target.write_text(original.replace(before, after))
        run(name, red=True, assertion=assertion)
    finally:
        target.write_text(original)
    run(name + '-restored')
print('Evidence:', WORK / 'results.json')
