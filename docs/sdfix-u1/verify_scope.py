"""Verify the U1 ownership boundary and immutable physical/controller mapping data."""
from pathlib import Path
import hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[2]
BASE='d67a13439028cfc983b34636e82d3de7282eab2a'
def git(*args):return subprocess.check_output(['git','-C',str(ROOT),*args])
head=git('rev-parse','HEAD').decode().strip()
paths=git('diff','--name-only',BASE,head).decode().splitlines()
assert all(p.startswith(('windows/static/','tests/','scripts/showready/','docs/')) for p in paths),paths
assert not any(p.startswith(('config/','.showready/','mac/')) for p in paths)
source='windows/static/controller/controller_map.json'
a=json.loads(git('show',BASE+':'+source));b=json.loads((ROOT/source).read_text())
assert a['view_box']==b['view_box'] and a['scene_view_box']==b['scene_view_box']
for old,new in zip(a['controls'],b['controls']):
    assert {k:v for k,v in old.items() if k!='label_anchor'}=={k:v for k,v in new.items() if k not in ('label_anchor','leader_via')}
svg='windows/static/controller/steam_deck.svg'
assert git('show',BASE+':'+svg)==(ROOT/svg).read_bytes()
protected=['config','mac','windows/midi.py','windows/receiver.py','windows/config.py','windows/ui_server.py','windows/win_recv.py','windows/engines','scripts/showready/ab_run.py','scripts/showready/deck_script.py','scripts/showready/capture_runner.py','scripts/showready/win_guard.ps1','scripts/showready/win_rail.sh']
assert not git('diff','--name-only',BASE,head,'--',*protected)
product_tree=git('rev-parse',head+':windows/static').decode().strip()
assert product_tree==git('rev-parse','a09b80d6034924013302e55362819924dbb00ff8:windows/static').decode().strip()
assert git('check-attr','eol','--','tests/ui_controller_geometry.cjs').decode().strip().endswith(': eol: lf')
for p in (ROOT/'windows/static/controller').iterdir():assert p.read_bytes().isascii(),p
for p in (ROOT/'docs/sdfix-u1').rglob('*'):
    if p.is_file() and p.suffix!='.png':assert p.read_bytes().isascii(),p
r={'base':BASE,'head':head,'changed_paths':paths,'protected_paths_unchanged':protected,'map_actions_anchors_unchanged':True,'svg_sha256':hashlib.sha256((ROOT/svg).read_bytes()).hexdigest(),'static_tree':product_tree,'static_tree_equals_initial_implementation':True,'ascii':True,'geometry_eol':'lf'}
(ROOT/'docs/sdfix-u1/evidence/scope.json').write_text(json.dumps(r,indent=2)+'\n')
print('PASS scoped changes, immutable map/shape geometry and MIDI instruments; ASCII; geometry LF')
