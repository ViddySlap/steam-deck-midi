"""Execute conflict decoration reversions in scratch; require named RED/restored GREEN."""
from pathlib import Path
import json
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
WORK = Path('/tmp/sdfix-u1/conflict-mutations')
WORK.mkdir(parents=True, exist_ok=True)
rows=[]
for name, file, old, new, marker in [
    ('cancel', 'index.html', "    ov.classList.remove('open');\n  };", "    ov.classList.remove('open');\n    if (typeof ControllerView !== 'undefined') ControllerView.markConflicts([]);\n  };", 'cancel retains row markers'),
    ('save', 'index.html', "    if (typeof ControllerView !== 'undefined') ControllerView.markConflicts([]);\n    setDirty(false);", '    setDirty(false);', 'successful Save clears row markers'),
    ('resolve', 'controller/controller_view.js', '    if (action && conflicting.has(action)) {', '    if (false && action && conflicting.has(action)) {', 'resolving the channel/CC collision clears marks'),
]:
    tree=WORK/name
    shutil.copytree(ROOT/'windows/static',tree,dirs_exist_ok=True)
    target=tree/file
    pristine=target.read_text()
    assert pristine.count(old)==1,(name,pristine.count(old))
    command=['node',str(ROOT/'tests/ui_controller_check.cjs'),str(tree/'index.html')]
    target.write_text(pristine.replace(old,new))
    red=subprocess.run(command,capture_output=True,text=True,env={**os.environ,'TMPDIR':str(WORK)})
    (WORK/(name+'-red.log')).write_text(red.stdout+red.stderr)
    target.write_text(pristine)
    green=subprocess.run(command,capture_output=True,text=True,env={**os.environ,'TMPDIR':str(WORK)})
    (WORK/(name+'-green.log')).write_text(green.stdout+green.stderr)
    row={'name':name,'command':command,'red_exit':red.returncode,'named_failure':marker,'named_failure_seen':marker in red.stdout+red.stderr,'green_exit':green.returncode,'restored_bytes':target.read_bytes()==(ROOT/'windows/static'/file).read_bytes()}
    rows.append(row)
    assert red.returncode==1 and row['named_failure_seen'] and green.returncode==0 and row['restored_bytes'],row
    print('PASS',name,'RED then restored GREEN')
(ROOT/'docs/sdfix-u1/conflict-mutations.json').write_text(json.dumps(rows,indent=2)+'\n')
