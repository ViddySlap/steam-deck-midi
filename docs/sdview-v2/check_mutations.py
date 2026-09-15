"""Run the shipped checks against planted faults in scratch, then restore GREEN."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/sdview-v2/mutations')
BASE.mkdir(parents=True, exist_ok=True)
WORK = Path(tempfile.mkdtemp(prefix='proof-', dir=BASE))
for directory in ('windows', 'tests'):
    shutil.copytree(ROOT / directory, WORK / directory, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
(WORK / 'config').mkdir()
shutil.copy2(ROOT / 'config/actions.yaml', WORK / 'config/actions.yaml')
(WORK / 'docs').mkdir()
shutil.copy2(ROOT / 'docs/api.md', WORK / 'docs/api.md')
NODE = shutil.which('node')
if not NODE:
    raise SystemExit('NODE-ABSENT: mutation proof requires node')
NODE_CMD = [NODE, str(WORK / 'tests/ui_controller_check.cjs'), str(WORK / 'windows/static/index.html')]
API_CMD = [sys.executable, '-B', '-m', 'unittest', 'tests.test_ui_server.HtmlApiBarTests']
results = []

def run(name, command, red=False, expected='AssertionError'):
    result = subprocess.run(command, cwd=WORK, text=True, capture_output=True,
                            timeout=120, env={**os.environ, 'TMPDIR':str(BASE.resolve())})
    log = WORK / (name + '.log')
    log.write_text(result.stdout + result.stderr)
    results.append({'name':name, 'command':command, 'cwd':str(WORK), 'exit':result.returncode,
                    'expected':'RED' if red else 'GREEN', 'log':str(log)})
    (WORK / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    if red:
        assert result.returncode != 0 and expected in log.read_text(), f'{name} did not fire: {log}'
    else:
        assert result.returncode == 0, f'{name} failed: {log}'
    print(name, 'RED' if red else 'GREEN', 'exit', result.returncode, flush=True)

run('pristine-controller', NODE_CMD)
run('pristine-api', API_CMD)
page = 'windows/static/index.html'
view = 'windows/static/controller/controller_view.js'
mutations = [
    ('commit-refresh', page, "  refreshChip(action);\n  if (typeof ControllerView !== 'undefined') ControllerView.refresh();",
     '  refreshChip(action);', 'AssertionError'),
    ('load-refresh', page, "    if (typeof ControllerView !== 'undefined') ControllerView.refresh();\n", '', 'initial load refreshes counts'),
    ('default-view', view, "=== 'list' ? 'list' : 'controller'; } catch", "=== 'list' ? 'list' : 'list'; } catch", 'Controller is the default front door'),
    ('arrow', view, '      scene.appendChild(arrow);', "      if (control.id !== 'l2') scene.appendChild(arrow);", 'exactly 23 visible arrows'),
    ('open-label', view, "      label.addEventListener('click', () => openControl(control.id));", '', 'AssertionError'),
    ('svg-shape', 'windows/static/controller/steam_deck.svg', 'data-control="l2"', 'data-control="removed_l2"', 'exactly 23 visible arrows'),
]
for name, relative, before, after, assertion in mutations:
    target = WORK / relative
    original = target.read_text()
    assert original.count(before) == 1, (name, 'mutation must replace exactly once')
    try:
        target.write_text(original.replace(before, after))
        assert before not in target.read_text()
        run(name, NODE_CMD, red=True, expected=assertion)
    finally:
        target.write_text(original)
    run(name + '-restored', NODE_CMD)

# A literal in a new, nested static JS file must reach the real HTML API bar.
planted = WORK / 'windows/static/controller/planted/fault.js'
planted.parent.mkdir()
planted.write_text("fetch('/api/sdview-planted-missing-route');\n")
try:
    run('external-api-literal', API_CMD, red=True, expected='HTML API path has no registered route: /api/sdview-planted-missing-route')
finally:
    planted.unlink()
run('external-api-literal-restored', API_CMD)
print('Evidence:', WORK / 'results.json')
