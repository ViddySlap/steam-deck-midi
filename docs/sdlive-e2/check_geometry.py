"""Run the unchanged pinned detector with a saved List preference at navigation."""
import os
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/showready'))
preload = ROOT / 'docs/sdlive-e2/geometry_preload.cjs'
os.environ['NODE_OPTIONS'] = '--require=' + str(preload)
source = (ROOT / 'scripts/showready/ui_geometry.py').read_text()
for before, after in [
    ("startswith('/private/tmp/sdfix-')", "startswith('/private/tmp/sdlive-')"),
    ("startswith('/tmp/sdfix-')", "startswith('/tmp/sdlive-')"),
    ('/tmp/sdfix-<link>/', '/tmp/sdlive-<link>/'),
]:
    assert source.count(before) == 1, ('rail adaptation must match once', before)
    source = source.replace(before, after)
exec(compile(source, str(ROOT / 'scripts/showready/ui_geometry.py'), 'exec'))
