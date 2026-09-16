"""The pinned laptop bundle script keeps K1's parameters and its exact exit codes.

sdpolish P1 pins docs/sdpick-k1/scripts/pull_bundle.ps1 as scripts/showready/pull_bundle.ps1
with -Bundle in place of the hardcoded sdpick.bundle name. P3 is its first real use on the
laptop, so the only thing that can be checked here is the script's own text - and the exit
codes are the whole contract the rail reads, so a silent renumber has to fail this test.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/showready/pull_bundle.ps1'
ORIGINAL = ROOT / 'docs/sdpick-k1/scripts/pull_bundle.ps1'


class PullBundleScript(unittest.TestCase):
    def setUp(self):
        self.text = SCRIPT.read_text(encoding='utf-8')

    def test_both_parameters_are_declared_mandatory(self):
        param = self.text.splitlines()[0]
        for name in ('$Bundle', '$Expected'):
            self.assertIn(name, param, param)
            self.assertRegex(param, r'\[Parameter\(Mandatory=\$true\)\]\[string\]' + re.escape(name) + r'\b')

    def test_the_bundle_name_is_no_longer_hardcoded(self):
        self.assertNotIn('sdpick.bundle', self.text)
        self.assertNotIn('PSScriptRoot', self.text)
        self.assertIn('$bundle=$Bundle', self.text)

    def test_the_six_exit_codes_are_present_on_their_own_conditions(self):
        exits = re.findall(r'exit (\d)', self.text)
        self.assertEqual(sorted(set(exits)), ['0', '3', '4', '5', '6', '7', '8'], exits)
        for code, needle in [('3', 'Clone is not clean'), ('4', 'bundle verify'), ('5', 'fetch'),
                             ('6', '$fetched -ne $Expected'), ('7', 'merge --ff-only'),
                             ('8', '$head -ne $Expected')]:
            window = self.text[:self.text.index('exit %s' % code)]
            self.assertIn(needle, window, 'exit %s lost its own condition' % code)

    def test_the_two_verification_steps_survive(self):
        # Written as `git -C $clone bundle verify` in the script.
        self.assertRegex(self.text, r'git -C \$clone bundle verify \$bundle')
        self.assertIn('bundle verify', self.text)
        self.assertIn('merge --ff-only', self.text)

    def test_only_the_bundle_parameter_differs_from_the_K1_original(self):
        """Anything else changed is a behaviour change nobody asked for."""
        pinned = self.text.splitlines()
        original = ORIGINAL.read_text(encoding='utf-8').splitlines()
        self.assertEqual(len(pinned), len(original), 'line count drifted')
        differing = [(i, a, b) for i, (a, b) in enumerate(zip(pinned, original)) if a != b]
        self.assertEqual([i for i, _, _ in differing], [0, 4],
                         'only the param line and the $bundle assignment may differ: %r' % (differing,))
        self.assertEqual(pinned[4], '$bundle=$Bundle')
        self.assertEqual(original[4], "$bundle=Join-Path $PSScriptRoot 'sdpick.bundle'")
        self.assertEqual(pinned[0], 'param([Parameter(Mandatory=$true)][string]$Bundle,'
                                    '[Parameter(Mandatory=$true)][string]$Expected)')


if __name__ == '__main__':
    unittest.main()
