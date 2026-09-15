"""sdfix gate: plant ONE layout fault in a scratch tree's static files.

m1 swap the leader targets of btn_a and btn_b (anchor + shape box) in controller_view.js
m2 move the btn_b label onto the btn_a label (controller_view.css)
m3 move the btn_a label under the status bar (controller_view.css)
Each replace must match exactly once, or the mutation refuses.
"""
import sys
from pathlib import Path

tree, name = Path(sys.argv[1]), sys.argv[2]
static = tree / 'windows/static/controller'


def replace_once(path, old, new):
    text = path.read_text()
    if text.count(old) != 1:
        sys.exit(f'{name}: expected exactly one match in {path.name}, found {text.count(old)}')
    path.write_text(text.replace(old, new))


if name == 'm1':
    js = static / 'controller_view.js'
    replace_once(js, 'const target = project(c.anchor.x, c.anchor.y);',
                 "const swapId = c.id === 'btn_a' ? 'btn_b' : c.id === 'btn_b' ? 'btn_a' : c.id;"
                 " const swapC = map.controls.find(item => item.id === swapId);"
                 " const target = project(swapC.anchor.x, swapC.anchor.y);")
    replace_once(js, 'const b = shapes.get(c.id).getBBox();', 'const b = shapes.get(swapId).getBBox();')
    replace_once(js, 'const bends = (c.leader_via || [])', 'const bends = ((swapId === c.id ? c.leader_via : null) || [])')
elif name == 'm2':
    css = static / 'controller_view.css'
    css.write_text(css.read_text() + '\n/* gate m2 */ .controller-label[data-control="btn_b"] { top: var(--m2-top) !important; }\n')
    js = static / 'controller_view.js'
    # After layout, park btn_b's label 10 px below btn_a's centre.
    replace_once(js, "label.style.left = `${center.x}px`; label.style.top = `${center.y}px`;",
                 "label.style.left = `${center.x}px`; label.style.top = `${center.y}px`;"
                 " if (c.id === 'btn_a') picture.style.setProperty('--m2-top', `${center.y + 10}px`);")
elif name == 'm3':
    css = static / 'controller_view.css'
    css.write_text(css.read_text() + '\n/* gate m3 */ .controller-label[data-control="btn_a"] { position: fixed !important; top: auto !important; bottom: 0 !important; left: 60% !important; transform: none !important; z-index: -1 !important; }\n')
else:
    sys.exit('unknown mutation ' + name)
print(f'MUTATED {name} in {static}')
