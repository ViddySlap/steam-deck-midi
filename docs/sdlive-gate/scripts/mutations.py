"""sdlive gate step 6: scratch-copy mutations (a)-(d) against the lap's own checks.

For each mutation: git archive <rev> into /tmp/sdlive-gate/mut/<m>, apply exactly one
planted fault (needle must match once), run the check -> must exit nonzero with an
assertion failure (not an import/syntax error), restore the original bytes (sha256
compared), rerun -> must exit 0. Never touches the repo checkout.
  mutations.py REV OUT.json
"""
import hashlib, json, os, re, subprocess, sys
from pathlib import Path

ROOT = Path('/Users/viddyslap/Documents/project-workspaces/steam-deck-midi')
PY = str(ROOT / '.venv/bin/python')
rev, out = sys.argv[1], Path(sys.argv[2])
BASE = Path('/tmp/sdlive-gate/mut')

MUTATIONS = {
    'a-forward-after-publish-plus-5ms': {
        'edits': [
            ('windows/live_events.py',
             "            result = original(*args, **kwargs)\n            try:\n"
             "                values = [args[i] if i < len(args) else kwargs.get(field, 0)\n"
             "                          for i, field in enumerate(fields)]\n"
             "                safe_publish(publisher, {\"kind\": \"midi\", \"bytes\": [status | values[0],\n"
             "                             values[1], values[2]], \"action\": current_action()})\n"
             "            except Exception:\n                pass\n            return result\n",
             "            try:\n"
             "                values = [args[i] if i < len(args) else kwargs.get(field, 0)\n"
             "                          for i, field in enumerate(fields)]\n"
             "                safe_publish(publisher, {\"kind\": \"midi\", \"bytes\": [status | values[0],\n"
             "                             values[1], values[2]], \"action\": current_action()})\n"
             "            except Exception:\n                pass\n"
             "            result = original(*args, **kwargs)\n            return result\n"),
            ('windows/live_events.py', "        ticket = next(self._tickets)\n",
             "        time.sleep(0.005)\n        ticket = next(self._tickets)\n"),
        ],
        'check': [PY, '-B', '-m', 'unittest', '-v', 'tests.test_live_events'],
    },
    'b-publish-out-of-order': {
        'edits': [
            ('windows/receiver.py',
             "                event.seq,\n                sender.last_seq,\n            )\n            return False\n",
             "                event.seq,\n                sender.last_seq,\n            )\n"
             "            if self._live_events is not None and isinstance(event, ActionEvent):\n"
             "                safe_publish(self._live_events, {\"kind\": \"input\", \"action\": event.action, \"state\": event.state})\n"
             "            return False\n"),
        ],
        'check': [PY, '-B', '-m', 'unittest', '-v', 'tests.test_live_events'],
    },
    'c-eventsource-stays-open-when-hidden': {
        'edits': [
            ('windows/static/controller/controller_live.js',
             "      } else {\n        disconnect();\n        clearTimeout(retry); retry = null;\n",
             "      } else {\n        clearTimeout(retry); retry = null;\n"),
        ],
        'check': ['node', 'tests/ui_controller_check.cjs'],
    },
    'd-follow-default-on': {
        'edits': [
            ('windows/static/controller/controller_live.js',
             "follow = localStorage.getItem(FOLLOW_KEY) === 'true';",
             "follow = localStorage.getItem(FOLLOW_KEY) !== 'false';"),
        ],
        'check': ['node', 'tests/ui_controller_check.cjs'],
    },
}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run(cmd, cwd, name):
    env = {**os.environ, 'PYSTRAY_BACKEND': 'dummy', 'BROWSER': '/usr/bin/true', 'TMPDIR': str(cwd), 'PYTHONDONTWRITEBYTECODE': '1'}
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=900)
    log = cwd / f'{name}.log'
    log.write_text(p.stdout + p.stderr)
    text = p.stdout + p.stderr
    fails = sorted(set(re.findall(r'^(?:FAIL|ERROR): (\S+ \([^)]*\))', text, re.M)))
    return {'command': cmd, 'exit': p.returncode, 'log': str(log), 'failing_tests': fails,
            'assertion_error': 'AssertionError' in text, 'import_or_syntax_error': bool(re.search(r'SyntaxError|ModuleNotFoundError|ImportError', text)),
            'tail': text.strip().splitlines()[-4:]}


results = {}
ok = True
for name, spec in MUTATIONS.items():
    tree = BASE / name
    if tree.exists():
        sys.exit(f'exists: {tree}')
    tree.mkdir(parents=True)
    archive = subprocess.run(['git', '-C', str(ROOT), 'archive', rev], check=True, capture_output=True).stdout
    subprocess.run(['tar', '-x', '-C', str(tree)], input=archive, check=True)
    originals = {}
    for rel, needle, replacement in spec['edits']:
        path = tree / rel
        originals.setdefault(rel, (path.read_bytes(), sha(path)))
        text = path.read_text()
        assert text.count(needle) == 1, (name, rel, 'needle count', text.count(needle))
        path.write_text(text.replace(needle, replacement))
    red = run(spec['check'], tree, 'red')
    for rel, (data, digest) in originals.items():
        (tree / rel).write_bytes(data)
        assert sha(tree / rel) == digest
    green = run(spec['check'], tree, 'restored')
    passed = red['exit'] != 0 and red['assertion_error'] and not red['import_or_syntax_error'] and green['exit'] == 0
    ok &= passed
    results[name] = {'tree': str(tree), 'mutated_files': list(originals), 'red': red, 'restored_bytes_equal': True, 'green': green, 'passed': passed}
    print(name, 'RED exit', red['exit'], red['failing_tests'][:6], red['tail'][-1:], '| restored exit', green['exit'], '| PASS' if passed else '| FAIL', flush=True)
out.write_text(json.dumps(results, indent=1))
sys.exit(0 if ok else 1)
