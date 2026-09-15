"""Reuse the pinned scratch/port/fixture/cleanup rail for E2's browser check.

Only the scratch-prefix acceptance and detector path change. This does not edit
or repin the showready kit. Commands and exact PID teardown land in receipt.json.
"""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/showready'))
source = (ROOT / 'scripts/showready/ui_geometry.py').read_text()
for before, after in [
    ("startswith('/private/tmp/sdfix-')", "startswith('/private/tmp/sdlive-')"),
    ("startswith('/tmp/sdfix-')", "startswith('/tmp/sdlive-')"),
    ('/tmp/sdfix-<link>/', '/tmp/sdlive-<link>/'),
    ("str(ROOT/'tests/ui_controller_geometry.cjs')", "str(ROOT/'docs/sdlive-e2/check_browser.cjs')"),
]:
    assert source.count(before) == 1, ('rail adaptation must match once', before)
    source = source.replace(before, after)
exec(compile(source, str(ROOT / 'scripts/showready/ui_geometry.py'), 'exec'))
