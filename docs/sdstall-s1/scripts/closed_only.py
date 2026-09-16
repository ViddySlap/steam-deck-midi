"""sdstall S1: drive the PINNED instrument's own CLOSED-arm code, CLOSED arms only.

`scripts/showready/timing_ab.py` has no CLOSED-only order: `run()` iterates
`ARMS = ('CLOSED', 'OPEN', 'CLOSED-B')` (timing_ab.py:28, :799). The stalls this
lap attributes hit CLOSED, so this wrapper imports timing_ab UNCHANGED and calls
the SAME two functions run() calls per arm:

    timing_ab.guarded_arm(lambda attempt: timing_ab.run_arm(args, tree, work,
                          script, mappings, label), timing_ab.foreign_load_check,
                          allow_unverified=False, retries=args.load_retries)

The preamble (scratch validation, candidate `git archive`, fixture verification,
preset sectioning, canonical script, mappings) calls the same timing_ab/ab_run/
deck_script functions run() calls, in the same order.

Two deliberate differences from run(), both declared in the report before data:
  1. Only CLOSED arms are run, which is the point.
  2. run() raises on the first non-accepted or non-passing arm, ending the run.
     This wrapper RECORDS such an arm, keeps every raw file, and continues, so
     an INVALID-by-load arm still enters the ALL-arms reading. It keeps running
     until --valid-target CLOSED arms have been accepted, or --max-arms tried.

It never calls summarize()/summarize_bridge() (those need all three arms) and it
computes no verdict: the raw per-arm `bridge_samples` decide, downstream.

  closed_only.py --candidate REV --scratch DIR --out FILE.json.gz
                 --script scripts/showready/timing_script.json
                 --valid-target 8 [--max-arms 14] [--watch-cmd JSON-ARGV]

On the laptop the two revisions do NOT come from a local `git archive`: they are
built as `git archive` trees on the Mac, railed over and extracted, then named
with --tree-from DIR. --tree-from copies that directory to the arm tree with
shutil.copytree and records its sha256 manifest in place of archive()'s; nothing
else changes, and the clone is never modified. --kit-root names the checkout
whose scripts/showready is the pinned instrument (default: the Mac run root).

--watch-cmd is a JSON argv started just before each arm and stopped after it.
{armdir} and {label} are substituted. It is the environment/gap/stack watcher;
it runs OUTSIDE the bridge process and touches only this arm's own files.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(os.environ.get('SDSTALL_KIT_ROOT',
                           '/Users/viddyslap/Documents/project-workspaces/steam-deck-midi'))
sys.path.insert(0, str(ROOT / 'scripts/showready'))
sys.dont_write_bytecode = True

import timing_ab                                                  # noqa: E402  (imported UNCHANGED)
from ab_run import archive, validate_scratch, write_result        # noqa: E402
from deck_script import canonical, effective, read_json, sha, validate, verify_fixtures  # noqa: E402


def tree_manifest(tree):
    """sha256 of every file in a --tree-from tree, in place of archive()'s."""
    files = sorted(p for p in tree.rglob('*') if p.is_file())
    digest = __import__('hashlib').sha256()
    for f in files:
        digest.update(str(f.relative_to(tree)).encode() + b'\0' + sha(f.read_bytes()).encode() + b'\n')
    return {'source': 'tree-from', 'files': len(files), 'manifest_sha256': digest.hexdigest()}


def build(args):
    """timing_ab.run()'s preamble, same calls in the same order."""
    validate_scratch(args.scratch)
    args.scratch.mkdir(parents=True, exist_ok=True)
    # `.metadata_never_index` keeps Spotlight (fseventsd/mds/mds_stores) off the
    # candidate tree. Extracting a fresh tree drove load1 from 2.2 to 13.5 on this
    # Mac and made every arm INVALID under the EXTENDED LOAD VALIDITY cap; the
    # flag file is the unprivileged, reversible way to stop it. See the report.
    (args.scratch / '.metadata_never_index').touch()
    if args.work:
        work = Path(args.work).resolve()
        reused = (work / 'candidate').is_dir() and (work / 'script.json').is_file()
        work.mkdir(parents=True, exist_ok=True)
        (work / '.metadata_never_index').touch()
        if reused:
            # The pinned instrument builds ONE candidate tree per run and serves
            # every arm from it (timing_ab.run() lines 787-800). Reusing it across
            # this revision's arms is the same design, and it is what keeps
            # Spotlight from re-indexing a new copy before every single arm.
            script = read_json(args.script)
            validate(script)
            verified = verify_fixtures(args.fixtures)
            preset = args.preset.resolve()
            if str(preset) not in verified or preset.name != 'EDM Show.json':
                raise ValueError('Requires verified EDM Show fixture')
            raw = read_json(preset)
            meta = {'work': str(work), 'candidate': read_json(work / 'candidate.json'),
                    'candidate_tree_reused': True,
                    'script_file_sha256': sha(args.script.read_bytes()),
                    'preset_sha256': sha(preset.read_bytes()),
                    'instrument_sha256': {str(p.relative_to(timing_ab.ROOT)): sha(p.read_bytes())
                                          for p in timing_ab.KIT.iterdir() if p.is_file()}}
            return work, work / 'candidate', script, effective(raw, 'windows')['mappings'], meta
    else:
        work = Path(tempfile.mkdtemp(prefix='timing-', dir=args.scratch)).resolve()
    script = read_json(args.script)
    validate(script)
    verified = verify_fixtures(args.fixtures)
    preset = args.preset.resolve()
    if str(preset) not in verified or preset.name != 'EDM Show.json':
        raise ValueError('Requires verified EDM Show fixture')
    raw = read_json(preset)
    if 'windows' not in raw.get('sections', {}):
        raise ValueError('Requires sectioned EDM Show and --preset-section windows')
    tree = work / 'candidate'
    if args.tree_from:
        shutil.copytree(args.tree_from, tree)
        candidate = {**tree_manifest(tree), 'declared_commit': args.candidate}
    else:
        candidate = archive(args.repo, args.candidate, tree)
    config = tree / 'config'
    shutil.rmtree(config / 'presets')
    (config / 'presets').mkdir()
    (config / 'presets/replay.json').write_bytes(preset.read_bytes())
    (config / 'presets/.active').write_text('replay.json', encoding='ascii')
    (config / 'windows_midi_map.json').write_bytes(preset.read_bytes())
    (work / 'script.json').write_bytes(canonical(script))
    mappings = effective(raw, 'windows')['mappings']
    (work / 'candidate.json').write_bytes(canonical(candidate))
    meta = {'work': str(work), 'candidate': candidate, 'candidate_tree_reused': False,
            'script_file_sha256': sha(args.script.read_bytes()),
            'preset_sha256': sha(preset.read_bytes()),
            'instrument_sha256': {str(p.relative_to(timing_ab.ROOT)): sha(p.read_bytes())
                                  for p in timing_ab.KIT.iterdir() if p.is_file()}}
    return work, tree, script, mappings, meta


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate', required=True)
    p.add_argument('--work', type=Path,
                   help='Explicit work dir; reused across this revision arms if it already '
                        'holds candidate/ and script.json, so the tree is extracted ONCE')
    p.add_argument('--tree-from', type=Path,
                   help='Use this already-extracted tree instead of a local git archive (laptop)')
    p.add_argument('--repo', type=Path, default=ROOT)
    p.add_argument('--fixtures', type=Path, default=ROOT / '.showready/fixtures')
    p.add_argument('--preset', type=Path, default=ROOT / '.showready/fixtures/mac/presets/EDM Show.json')
    p.add_argument('--preset-section', choices=['windows'], default='windows')
    p.add_argument('--script', type=Path, required=True)
    p.add_argument('--scratch', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--valid-target', type=int, default=8)
    p.add_argument('--max-arms', type=int, default=14)
    p.add_argument('--first-repeat', type=int, default=1)
    p.add_argument('--speed', type=float, default=1)
    p.add_argument('--clock', choices=['script', 'wall'], default='script')
    p.add_argument('--load-retries', type=int, default=3)
    p.add_argument('--rule', choices=timing_ab.RULES, default='m_bridge')
    p.add_argument('--watch-cmd', type=json.loads)
    p.add_argument('--label', default='sdstall')
    a = p.parse_args()
    # timing_ab.run_arm reads these attributes off `args`.
    a.control = None
    a.client_cmd = None
    a.allow_unverified_load = False
    a.repeats = a.max_arms
    a.sensitivity_result = None

    result = {'schema': 'sdstall-closed/1', 'wrapper': 'docs/sdstall-s1/scripts/closed_only.py',
              'drives': 'timing_ab.guarded_arm(timing_ab.run_arm(...)) - the same calls as timing_ab.run() lines 803-806',
              'command': [sys.executable, *sys.argv], 'runs': [], 'rule': a.rule, 'speed': a.speed,
              'receiver_clock': a.clock, 'arm_order': ['CLOSED'], 'valid_target': a.valid_target,
              'max_arms': a.max_arms, 'label': a.label,
              'timing_ab_sha256': sha((ROOT / 'scripts/showready/timing_ab.py').read_bytes())}
    started = time.perf_counter()
    try:
        work, tree, script, mappings, meta = build(a)
        result.update(meta)
        accepted = 0
        for repeat in range(a.first_repeat, a.first_repeat + a.max_arms):
            if accepted >= a.valid_target:
                break
            label = 'r%d-CLOSED' % repeat
            watch = None
            armdir = work / (label + '-try1')
            if a.watch_cmd:
                argv = [s.replace('{armdir}', str(armdir)).replace('{label}', label) for s in a.watch_cmd]
                watch = subprocess.Popen(argv)
            t0 = time.time()
            try:
                guarded = timing_ab.guarded_arm(
                    lambda attempt: timing_ab.run_arm(a, tree, work, script, mappings,
                                                      '%s-try%d' % (label, attempt)),
                    timing_ab.foreign_load_check, allow_unverified=a.allow_unverified_load,
                    retries=a.load_retries)
            finally:
                if watch is not None:
                    watch.terminate()
                    try:
                        watch.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        watch.kill(); watch.wait()
            guarded.update(repeat=repeat, name='CLOSED', wall_start=t0, wall_end=time.time(),
                           arm_dir=str(armdir))
            arm = guarded.get('arm') or {}
            guarded['arm_passed'] = arm.get('passed')
            accepted += 1 if (guarded['accepted'] and arm.get('passed')) else 0
            result['runs'].append(guarded)
            write_result(a.out, result)
            print(json.dumps({'repeat': repeat, 'arm': 'CLOSED', 'load': guarded['load_status'],
                              'accepted': guarded['accepted'], 'passed': arm.get('passed'),
                              'accepted_so_far': accepted,
                              **timing_ab.power_floor(arm.get('samples', [])),
                              **timing_ab.every_message_floor(arm.get('bridge_samples', []))}), flush=True)
        result['accepted_arms'] = accepted
        result['reached_target'] = accepted >= a.valid_target
    except Exception as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
    result['wall_seconds'] = time.perf_counter() - started
    written = write_result(a.out, result)
    print('WROTE', written, flush=True)
    return 0 if result.get('reached_target') else 1


if __name__ == '__main__':
    sys.exit(main())
