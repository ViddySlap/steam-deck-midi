"""Verify BASE assertions and all existing product function bodies are retained."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

base='14aa21824843dbe148dc3ac3d0bf58929ef34c3a'
root=Path(__file__).resolve().parents[3] if '/docs/sdlive-e0/scripts/' in str(Path(__file__).resolve()) else Path.cwd()
def original(path):
    return subprocess.check_output(['git','-C',str(root),'show',base+':'+path],text=True)
def methods(text):
    tree=ast.parse(text)
    return {(c.name,m.name):m for c in tree.body if isinstance(c,ast.ClassDef) for m in c.body if isinstance(m,ast.FunctionDef)}
a=methods(original('tests/test_deck_control_api.py'))
b=methods((root/'tests/test_deck_control_api.py').read_text())
assert all(k in b and ast.dump(v)==ast.dump(b[k]) for k,v in a.items())
print('EXISTING_TEST_METHODS_IDENTICAL',len(a))
class RemoveReadMarker(ast.NodeTransformer):
    removed=0
    def visit_Assign(self,node):
        target=ast.parse('self._body_read = True').body[0]
        if ast.dump(node)==ast.dump(target):
            self.removed+=1
            return None
        return node
before=methods(original('deck/control_api.py'))
after=methods((root/'deck/control_api.py').read_text())
marker=RemoveReadMarker()
marker.visit(after[('_Handler','_request')])
assert marker.removed==1
assert all(k in after and ast.dump(v)==ast.dump(after[k]) for k,v in before.items())
assert set(after)-set(before)=={('_Handler','finish')}
print('EXISTING_PRODUCT_METHODS_IDENTICAL_EXCEPT_READ_MARKER',len(before))
paths=['windows','protocol','config','mac','scripts/showready','docs/api.md']
changed=subprocess.check_output(['git','-C',str(root),'diff','--name-only',base,'--',*paths],text=True)
assert not changed,changed
print('CHANGES_IN_WINDOWS_PROTOCOL_CONFIG_MAC_PINNED_KIT_API_DOC',0)
print(json.dumps({p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in ['deck/control_api.py','tests/test_deck_control_api.py']},sort_keys=True))
