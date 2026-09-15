"""Same one-process repetition as sdfix flake_rate.py, with pinned roots and a gate."""
import collections
import json
import os
from pathlib import Path
import sys
import unittest
root, n, name, expected, output = Path(sys.argv[1]).resolve(), int(sys.argv[2]), sys.argv[3], sys.argv[4], Path(sys.argv[5])
os.chdir(root)
sys.path[:0] = [str(root), str(root / 'tests')]
kinds = collections.Counter()
cases = collections.Counter()
bad = 0
for i in range(n):
    suite = unittest.defaultTestLoader.loadTestsFromName('test_deck_control_api.DeckControlAPITests.' + name)
    result = unittest.TestResult()
    suite.run(result)
    problems = result.errors + result.failures
    if problems:
        bad += 1
        for test, tb in problems:
            kinds[tb.strip().splitlines()[-1]] += 1
            cases[str(test)] += 1
print(f'RUNS {n} RUNS_WITH_ERROR {bad}')
for kind, count in kinds.most_common():
    print(f'KIND {count} {kind}')
value = dict(root=str(root),runs=n,runs_with_error=bad,kinds=dict(kinds),cases=dict(cases),test=name,expected=expected)
output.write_text(json.dumps(value,indent=2)+'\n', encoding='utf-8')
if expected == 'red':
    # An import failure or unrelated assertion cannot pay the reset control.
    passed = bad > 0 and any('WinError 10053' in k or 'WinError 10054' in k or 'all declared body bytes' in k for k in kinds)
else:
    passed = bad == 0
raise SystemExit(0 if passed else 1)
