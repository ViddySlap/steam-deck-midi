"""sdfix gate: repeat ONE pre-existing test N times in one process and count outcomes by type."""
import collections, os, sys, unittest
clone = r'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
os.chdir(clone); sys.path.insert(0, clone); sys.path.insert(0, os.path.join(clone, 'tests'))
name = 'test_deck_control_api.DeckControlAPITests.test_malformed_json_and_unsupported_method_are_json'
n = int(sys.argv[1]); kinds = collections.Counter(); bad = 0
for i in range(n):
    suite = unittest.defaultTestLoader.loadTestsFromName(name)
    result = unittest.TestResult(); suite.run(result)
    problems = result.errors + result.failures
    if problems:
        bad += 1
        for test, tb in problems:
            kinds[tb.strip().splitlines()[-1][:160]] += 1
print(f'RUNS {n} RUNS_WITH_ERROR {bad}')
for k, v in kinds.most_common(): print(f'KIND {v} {k}')
