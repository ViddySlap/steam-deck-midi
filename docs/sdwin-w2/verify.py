"""Verify W2's copied bytes and recorded PowerShell results, without a receiver."""
import argparse
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def verify(fixtures, arms):
    total = 0
    for host, expected in [('windows-installed', 11), ('mac', 5)]:
        entries = read(fixtures / host / 'MANIFEST.sha256')['entries']
        assert len(entries) == expected, (host, 'missing fixture observations')
        seen = set()
        for entry in entries:
            relative = entry['relative']
            assert relative not in seen, relative
            seen.add(relative)
            path = fixtures / host / relative
            assert path.is_relative_to(fixtures / host)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest == entry['sha256_before'] == entry['sha256_after'] == entry['sha256_copy'], path
            assert path.stat().st_size == entry['bytes'], path
        total += len(entries)
    records = read(arms)
    names = ['start_receiver.ps1', 'start_installed_receiver.ps1', 'start_installed_receiver_v2.ps1']
    expected = {(name, arm) for name in names for arm in ('missing-key', 'grandma', 'absent-file')}
    assert len(records) == 9 and {(r['launcher'], r['arm']) for r in records} == expected, 'missing/duplicate arms'
    for record in records:
        assert record['before'] and record['before'] == record['after'], 'process inventory missing/changed'
        assert record['all_child_pids_gone'] is True and record['receiver_started'] is False
        if record['arm'] == 'absent-file':
            assert record['exit_code'] == 1
            assert record['settings_sha256_before'] == record['settings_sha256_after'] == 'ABSENT'
            assert record['saved'] is None and record['calls'] == []
            continue
        assert record['exit_code'] == 0
        section = 'windows' if record['arm'] == 'missing-key' else 'grandma'
        assert record['saved']['preset_section'] == section
        calls = record['calls']
        assert len(calls) == (1 if record['launcher'] == names[0] else 2), 'missing argv observation'
        argv = calls[-1]['argv']
        assert argv[argv.index('--preset-section') + 1] == section
        assert '--tray' not in argv
        if record['launcher'] == names[0]:
            assert argv[:2] == ['-m', 'windows.win_recv']
        else:
            assert calls[0]['argv'][:2] == ['--check-midi-port', '--midi-port']
        if section == 'grandma':
            assert record['settings_sha256_before'] == record['settings_sha256_after'], 'existing settings changed'
        else:
            assert record['settings_sha256_before'] != record['settings_sha256_after'], 'backfill did not write'
    return total, len(records)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--arms', type=Path, required=True)
    args = parser.parse_args()
    files, arms = verify(args.fixtures.resolve(), args.arms)
    print(f'GREEN: {files} fixture hashes; {arms} executed arms; nonempty process/argv controls')
