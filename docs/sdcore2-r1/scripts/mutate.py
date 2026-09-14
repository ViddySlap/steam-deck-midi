"""Run R1 reversions in a git export, with bytecode disabled and restored controls."""
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[3]
SCRATCH = Path('/tmp/sdcore-r1')
SCRATCH.mkdir(exist_ok=True)
PYTHON = ROOT / '.venv/bin/python'


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


with tempfile.TemporaryDirectory(dir=SCRATCH, prefix='mutation-') as tmp:
    tree = Path(tmp)
    with tarfile.open(fileobj=io.BytesIO(git('archive', 'HEAD'))) as archive:
        archive.extractall(tree, filter='data')
    # Also supports verification before the R1 commit. No ignored files copied.
    paths = set(git('diff', 'HEAD', '--name-only').decode().splitlines())
    paths.add('tests/test_upgrade_boot.py')
    for name in paths:
        source = ROOT / name
        if source.is_file():
            target = tree / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(tree), 'TMPDIR': str(SCRATCH)}

    def run(label, test, expected):
        result = subprocess.run([str(PYTHON), '-B', '-m', 'unittest', test], cwd=tree,
                                env=env, capture_output=True, text=True, timeout=30)
        (SCRATCH / (label + '.log')).write_text(result.stdout + result.stderr)
        assert (result.returncode == 0) == expected, (label, result.stdout, result.stderr)
        print(label, 'GREEN' if expected else 'RED', flush=True)

    run('pristine-focused', 'tests.test_upgrade_boot', True)
    startup = 'windows/win_recv.py'
    cases = [
        ('flat-default', 'config/presets/default.json', None,
         git('show', 'f809be1:config/presets/default.json').decode(),
         'test_git_pull_default_without_marker_or_local_file_boots_everywhere'),
        ('mac-default-disabled', startup, 'platform == "darwin"', 'False',
         'test_darwin_sectioned_first_run_loads_and_persists_macbook'),
        ('all-platforms-default', startup, 'platform == "darwin"', 'True',
         'test_other_platforms_keep_named_error_without_writing'),
        ('no-macbook-guard', startup, ' and "macbook" in raw["sections"]', '',
         'test_darwin_without_macbook_keeps_named_error_without_writing'),
        ('existing-selection-overwritten', 'windows/bridge_settings.py',
         '        if self.path.exists():\n            self.preset_section = self.load(self.path).preset_section\n            return False\n        return self._save(section, overwrite=False)',
         '        return self._save(section, overwrite=True)',
         'test_initialization_does_not_replace_file_created_since_load'),
        ('identity-not-persisted', startup, 'created = settings.save_if_missing(section)',
         'created = False', 'test_darwin_sectioned_first_run_loads_and_persists_macbook'),
        ('argv-ignored', startup, 'BridgeSettings.load(base_map_path.parent / "bridge.local.json", override)',
         'BridgeSettings.load(base_map_path.parent / "bridge.local.json")',
         'test_explicit_override_does_not_create_local_file'),
        ('launcher-not-initialized', 'scripts/mac/run_receiver.command', None,
         git('show', 'f809be1:scripts/mac/run_receiver.command').decode(),
         'tests.test_upgrade_boot.MacLauncherSnippetTests.test_section_snippet_creates_missing_file_and_preserves_existing_bytes'),
    ]
    for label, name, anchor, replacement, test in cases:
        if not test.startswith('tests.'):
            test = 'tests.test_upgrade_boot.UpgradeBootTests.' + test
        target = tree / name
        before = target.read_bytes()
        run(label + '-pristine', test, True)
        try:
            source = before.decode()
            if anchor is not None:
                assert source.count(anchor) == 1, (label, source.count(anchor))
                replacement = source.replace(anchor, replacement)
            target.write_text(replacement)
            run(label + '-mutant', test, False)
        finally:
            target.write_bytes(before)
        assert hashlib.sha256(target.read_bytes()).digest() == hashlib.sha256(before).digest()
        run(label + '-restored', test, True)
    print('ALL 8 MUTANTS BITE; RESTORED BYTES MATCH')
