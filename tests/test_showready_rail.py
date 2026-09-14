"""Pin the Windows kit and exercise transport/compare failure contracts."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / 'scripts/showready'


def verify_pins(root):
    kit = root / 'scripts/showready'
    pins = {}
    for line in (kit / 'SHA256SUMS').read_text(encoding='ascii').splitlines():
        digest, name = line.split('  ', 1)
        if name in pins or not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise AssertionError('Invalid or duplicate pin: ' + name)
        pins[name] = digest
    actual = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in kit.rglob('*') if p.is_file() and p.name != 'SHA256SUMS'}
    if not actual or pins != actual:
        raise AssertionError('SHA256SUMS mismatch: ' + repr(sorted(set(pins) ^ set(actual)))
                             + ' changed=' + repr([p for p in pins if p in actual and pins[p] != actual[p]]))


class ShowreadyPinTests(unittest.TestCase):
    def test_pins_match_exact_file_set_and_bytes(self):
        verify_pins(ROOT)

    def test_unpinned_edit_and_extra_file_are_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(KIT, root / 'scripts/showready')
            verify_pins(root)
            rail = root / 'scripts/showready/win_rail.sh'
            original = rail.read_bytes()
            rail.write_bytes(original + b'\n# unpinned fault\n')
            with self.assertRaisesRegex(AssertionError, 'SHA256SUMS mismatch'):
                verify_pins(root)
            rail.write_bytes(original)
            verify_pins(root)
            (rail.parent / 'unexpected.txt').write_bytes(b'fault')
            with self.assertRaisesRegex(AssertionError, 'SHA256SUMS mismatch'):
                verify_pins(root)

    def test_every_transport_invocation_uses_the_required_options(self):
        source = (KIT / 'win_rail.sh').read_text(encoding='ascii')
        self.assertNotIn('-Command', source)
        option_line, = re.findall(r'^SSH_OPTIONS=\(.*\)$', source, re.M)
        for option in ('-i "$HOME/.ssh/claude-mac-win-key"', '-o IdentitiesOnly=yes',
                       '-o BatchMode=yes', '-o StrictHostKeyChecking=yes', '-o ConnectTimeout=10'):
            self.assertIn(option, option_line)
        calls = [line.strip() for line in source.splitlines()
                 if re.match(r'\s*(?:exec )?(?:ssh|scp)\s', line)]
        self.assertEqual(len(calls), 4)
        for call in calls:
            self.assertRegex(call, r'^(?:exec )?(?:ssh|scp) "\$\{SSH_OPTIONS\[@\]\}" ')


@unittest.skipUnless(os.name == 'posix' and shutil.which('bash'), 'Mac rail execution requires POSIX bash')
class ShowreadyTransportTests(unittest.TestCase):
    def test_remote_status_stderr_arguments_and_scp_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / 'calls.jsonl'
            # bash stubs avoid relying on an executable Python shebang path.
            for name in ('ssh', 'scp'):
                script = root / name
                script.write_text('#!/bin/bash\n'
                                  'printf "%s\\n" "$*" >> "$CALL_LOG"\n'
                                  'if [[ "$0" == */scp ]]; then exit "${SCP_EXIT:-0}"; fi\n'
                                  'if [[ "$*" == *" -File "* ]]; then\n'
                                  '  echo "stderr fixture" >&2\n'
                                  '  exit "${REMOTE_EXIT:-0}"\nfi\n', encoding='ascii')
                script.chmod(0o755)
            ps1 = root / 'fixture space.ps1'
            ps1.write_text('exit 7\n')
            env = {**os.environ, 'PATH': str(root) + os.pathsep + os.environ['PATH'], 'CALL_LOG': str(log)}
            command = ['bash', str(KIT / 'win_rail.sh'), 'run', 'unit', str(ps1), '-Value', 'spaces , * literal']
            for code in (7, 0):
                result = subprocess.run(command, env={**env, 'REMOTE_EXIT': str(code)}, capture_output=True, text=True)
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertIn('stderr fixture', result.stderr)
                self.assertIn('"spaces , * literal"', log.read_text())
            log.unlink()
            result = subprocess.run(command, env={**env, 'SCP_EXIT': '9'}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 9)
            self.assertNotIn(' -File ', log.read_text())

    def test_unsafe_arguments_are_refused_before_transport(self):
        for arg in ('%TEMP%', 'bad"quote', 'bad\nline', 'x&whoami'):
            result = subprocess.run(['bash', str(KIT / 'win_rail.sh'), 'run', 'unit', 'absent.ps1', arg],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 64)
            self.assertIn('Unsupported remote argument', result.stderr)


POWERSHELL = shutil.which('powershell') or shutil.which('pwsh')


@unittest.skipUnless(POWERSHELL, 'PowerShell guard execution requires powershell or pwsh')
class ShowreadyGuardTests(unittest.TestCase):
    def test_clean_changed_missing_and_python_observations(self):
        # Execute the real compare/output/exit code path with a synthetic
        # snapshot provider. No installed files or live processes are touched.
        source = (KIT / 'win_guard.ps1').read_text(encoding='ascii')
        seam = '\ntry {\n    $outPath ='
        self.assertEqual(source.count(seam), 1)
        setup = '''
$work = $PSScriptRoot
function Get-Snapshot {
    return (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'current.json') -Raw -Encoding UTF8 | ConvertFrom-Json)
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            guard = root / 'guard.ps1'
            guard.write_text(source.replace(seam, setup + seam), encoding='ascii')
            data = {'udp45123': [{'pid': 17}], 'tcp7723': [{'pid': 17}],
                    'protectedProcesses': [{'pid': 17}], 'install': {'fileCount': 1},
                    'userConfig': {'locations': [{'files': [{'path': 'x', 'sha256': 'abc'}]}]},
                    'pythonProcesses': [], 'scalar': True, 'empty': [], 'nullable': None,
                    'filename': '\u00e9.json'}
            baseline = root / 'baseline.json'
            baseline.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            command = [POWERSHELL, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(guard),
                       '-Mode', 'compare', '-Out', str(root / 'out.json'), '-Baseline', str(baseline)]

            def run(current):
                (root / 'current.json').write_text(json.dumps(current, ensure_ascii=False), encoding='utf-8')
                result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                self.assertEqual(json.loads((root / 'out.json').read_text(encoding='utf-8')), current)
                return result

            clean = run(data)
            self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
            mutant = {**data, 'protectedProcesses': [{'pid': 18}]}
            red = run(mutant)
            self.assertEqual(red.returncode, 1, red.stderr)
            self.assertIn('$.protectedProcesses[0].pid', red.stdout)
            for field, value in [('pythonProcesses', [{'pid': 99, 'path': 'fixture'}]),
                                 ('udp45123', []), ('tcp7723', []), ('scalar', False)]:
                with self.subTest(field=field):
                    self.assertEqual(run({**data, field: value}).returncode, 1)
            # Equal empty sides still fail the required-observation check.
            empty = {**data, 'udp45123': []}
            baseline.write_text(json.dumps(empty), encoding='ascii')
            self.assertEqual(run(empty).returncode, 1)
            baseline.write_text(json.dumps(data), encoding='ascii')
            self.assertEqual(run(data).returncode, 0)


if __name__ == '__main__':
    unittest.main()
