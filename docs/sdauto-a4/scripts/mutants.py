"""A4 mutant sweep in a scratch copy: each mutant must turn its named test RED; the pristine copy must be GREEN."""
import shutil, subprocess, sys
from pathlib import Path
ROOT = Path('/Users/viddyslap/Documents/project-workspaces/steam-deck-midi')
PY = str(ROOT / '.venv/bin/python')
COPY = Path('/tmp/sdauto-a4/mutcopy')
TESTS = ['tests.test_ui_node', 'tests.test_ui_server.VersionApiTests', 'tests.test_ui_server.VersionAgreementTests',
         'tests.test_ui_server.BridgeSettingsApiTests.test_api_inventory_matches_registered_method_paths', 'tests.test_ui_server.HtmlApiBarTests']
MUTANTS = [
    ('M1 F4 rule removed', 'windows/static/index.html', '  header select { width: auto; }\n', '', ['test_all_ui_node_checks', 'test_version_check_fires_on_planted_header_faults']),
    ('M2 route removed', 'windows/ui_server.py', '@app.route("/api/version", methods=["GET"])', '@app.route("/api/version-gone", methods=["GET"])', ['test_version_route_reports_the_fingerprint_and_unfrozen_source', 'test_api_inventory_matches_registered_method_paths', 'test_html_parses_and_all_api_paths_are_registered']),
    ('M3 api.md row removed', 'docs/api.md', '| GET | `/api/version` |', '| GETX | `/api/version` |', ['test_api_inventory_matches_registered_method_paths']),
    ('M4 VERSION diverges', 'VERSION', '0.5.0', '0.4.9', ['test_version_file_and_fingerprint_agree']),
    ('M5 frozen always true', 'windows/ui_server.py', '"frozen": bool(getattr(sys, "frozen", False)),', '"frozen": True,', ['test_version_route_reports_the_fingerprint_and_unfrozen_source', 'test_version_route_serves_the_checked_in_fingerprint']),
    ('M6 source marker dropped', 'windows/static/index.html', "${info.frozen ? '' : ' (source)'}", '', ['test_all_ui_node_checks']),
    ('M7 build template loses GIT_COMMIT', 'scripts/windows/build_exe_v2.ps1', 'GIT_COMMIT = "$gitCommit"\n', '', ['test_build_exe_v2_regenerates_every_fingerprint_name_from_version_and_git']),
    ('M8 boot call removed', 'windows/static/index.html', 'setInterval(pollStateVersion, 2000);\nloadVersion();\n', 'setInterval(pollStateVersion, 2000);\n', ['test_all_ui_node_checks']),
    ('M9 route reads short commit', 'windows/ui_server.py', '"git_commit": build_fingerprint.GIT_COMMIT,', '"git_commit": build_fingerprint.GIT_COMMIT_SHORT,', ['test_version_route_reports_the_fingerprint_and_unfrozen_source']),
]
def fresh():
    if COPY.exists(): shutil.rmtree(COPY)
    subprocess.run(['rsync', '-a', '--exclude', '.venv', '--exclude', '.git', '--exclude', '.showready', '--exclude', '__pycache__', f'{ROOT}/', f'{COPY}/'], check=True)
def run():
    r = subprocess.run([PY, '-B', '-m', 'unittest', *TESTS], cwd=COPY, capture_output=True, text=True, timeout=600)
    return r.returncode, r.stdout + r.stderr
fresh(); code, out = run()
print('PRISTINE exit', code, [l for l in out.splitlines() if l.startswith(('Ran ', 'OK', 'FAILED'))]); ok = code == 0
for name, rel, old, new, reds in MUTANTS:
    fresh(); f = COPY / rel; text = f.read_text()
    assert text.count(old) == 1, (name, text.count(old)); f.write_text(text.replace(old, new))
    code, out = run()
    missing = [t for t in reds if not any(l.startswith(('FAIL: ' + t, 'ERROR: ' + t)) for l in out.splitlines())]
    verdict = code != 0 and not missing
    ok &= verdict
    print(f"{'RED-AS-NAMED' if verdict else 'NOT-RED'} {name} exit={code} missing={missing} " + str([l for l in out.splitlines() if l.startswith(('FAIL: ', 'ERROR: ', 'FAILED'))]))
shutil.rmtree(COPY)
print('SWEEP', 'PASS' if ok else 'FAIL'); sys.exit(0 if ok else 1)
