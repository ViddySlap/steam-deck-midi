"""The geometry instrument's scratch guard is a PATTERN, not a hard-coded lap name.

sdfix pinned `/tmp/sdfix-<link>/`, so every later lap had to edit the instrument to run it.
sdpolish P1 widens it to `/tmp/sd<lap>-<link>/` (and the `/private/tmp` form macOS resolves
it to) while keeping the refusal that matters: no scratch in the run root, a vault, a home
directory or a bare temp directory. Both directions are asserted here, because a guard that
only ever says yes and a guard that only ever says no are indistinguishable from one sample.
"""
import unittest
from pathlib import Path
import sys

sys.dont_write_bytecode = True  # Never leave a __pycache__ beside the pinned instruments.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/showready'))
from deck_script import scratch_ok  # noqa: E402


ACCEPTED = [
    '/tmp/sdfix-u1/geometry',
    '/tmp/sdpolish-p1/geometry',
    '/private/tmp/sdpolish-p1/geometry',
    '/private/tmp/sdrc-cg',
    '/tmp/sdrc-cg/',
    '/tmp/sdlive-eg/geometry/geometry-abc123',
    '/tmp/sdwin-w1',
]
REFUSED = [
    '/tmp',
    '/tmp/',
    '/tmp/sdfix',                # a lap with no link
    '/tmp/sd-u1',                # no lap name
    '/tmp/scratch',
    '/tmp/xsdpolish-p1',         # not anchored at the start
    '/private/tmp/other-p1',
    '/var/folders/zz/T/sdpolish-p1',
    '/Users/viddyslap/Documents/project-workspaces/steam-deck-midi',
    '/Users/viddyslap/Documents/ViddyVault/tmp/sdpolish-p1',
    '/Users/viddyslap/private/sdpolish-p1',
    '/Users/viddyslap/tmp/sdpolish-p1',
    'tmp/sdpolish-p1',
    '',
]


class ScratchPattern(unittest.TestCase):
    def test_every_lap_shaped_scratch_is_accepted(self):
        for path in ACCEPTED:
            with self.subTest(path=path):
                self.assertTrue(scratch_ok(path), path)

    def test_everything_else_is_refused(self):
        for path in REFUSED:
            with self.subTest(path=path):
                self.assertFalse(scratch_ok(path), path)

    def test_a_new_lap_name_needs_no_edit(self):
        """The point of the change: a lap nobody has thought of yet already works."""
        self.assertTrue(scratch_ok('/tmp/sdnotalapyet-z9/scratch'))
        self.assertTrue(scratch_ok('/private/tmp/sd2027q1-a1'))

    def test_a_lookalike_prefix_does_not_slip_through(self):
        """`/tmp/sdpolish-p1extra` is a DIFFERENT directory from `/tmp/sdpolish-p1`."""
        self.assertTrue(scratch_ok('/tmp/sdpolish-p1extra'))
        self.assertFalse(scratch_ok('/tmp/sdpolish-p1/../../Users'))

    def test_the_instrument_actually_calls_the_guard(self):
        """A guard nothing invokes is not a guard."""
        source = (Path(__file__).resolve().parents[1] / 'scripts/showready/ui_geometry.py').read_text()
        self.assertIn('from deck_script import scratch_ok', source)
        self.assertIn('if not scratch_ok(scratch):', source)
        self.assertNotIn("startswith('/tmp/sdfix-')", source)


if __name__ == '__main__':
    unittest.main()
