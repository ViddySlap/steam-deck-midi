"""S3 mutation controls, run only in /tmp/sdcore-s3. Node is a test tool only."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = Path('/tmp/sdcore-s3/reversions')
SCRATCH.mkdir(parents=True, exist_ok=True)
COPY = Path(tempfile.mkdtemp(dir=SCRATCH, prefix='source-'))
for folder in ('windows', 'tests', 'shared', 'common', 'protocol'):
    if (ROOT / folder).exists():
        shutil.copytree(ROOT / folder, COPY / folder, ignore=shutil.ignore_patterns('__pycache__'))
(COPY / 'docs').mkdir()
shutil.copyfile(ROOT / 'docs/api.md', COPY / 'docs/api.md')
ENV = {**os.environ, 'TMPDIR':str(SCRATCH), 'PYTHONDONTWRITEBYTECODE':'1'}
PYTHON = [sys.executable, '-B', '-m', 'unittest', 'tests.test_preset_watch',
          'tests.test_win_recv_settings', 'tests.test_ui_server', 'tests.test_engine_states']
NODE = ['node', 'tests/ui_reload_check.cjs']
SECTIONS = ['node', 'tests/ui_sections_check.cjs']
def case(name):
    return [sys.executable,'-B','-m','unittest','tests.test_preset_watch.'+name]
WATCH = 'windows/preset_watch.py'
MAIN = 'windows/win_recv.py'
RECV = 'windows/receiver.py'
API = 'windows/ui_server.py'
HTML = 'windows/static/index.html'
originals = {p:(COPY / p).read_text() for p in (WATCH,MAIN,RECV,API,HTML)}
controls = [
    ('watch-event-omitted',WATCH,'self.reload_event.set()','pass',case('PresetWatcherTests.test_default_poll_change_within_one_second_and_daemon')),
    ('watch-marker-omitted',WATCH,"self.presets_dir / '.active', self.settings_path",'self.settings_path,',case('PresetWatcherTests.test_touch_add_delete_marker_and_local_settings')),
    ('watch-local-settings-omitted',WATCH,"self.presets_dir / '.active', self.settings_path","self.presets_dir / '.active',",case('PresetWatcherTests.test_touch_add_delete_marker_and_local_settings')),
    ('watch-debounce-omitted',WATCH,'remaining = self.debounce - (now - pending_since)','remaining = 0',case('PresetWatcherTests.test_temp_files_ignored_and_rename_debounced')),
    ('watch-exception-exits',WATCH,"LOGGER.exception('preset watch poll failed; retrying')",'return',case('PresetWatcherTests.test_event_exception_is_retried')),
    ('watch-not-started',MAIN,'    preset_watcher.start()','    pass',case('ReloadIntegrationTests.test_half_write_keeps_last_good_then_full_write_applies')),
    ('tray-only-watch-stopped',MAIN,'    if args.tray:\n        # Auto-start tray mode:', '    if args.tray:\n        preset_watcher.stop()\n        # Auto-start tray mode:',case('ReloadIntegrationTests.test_watcher_runs_in_tray_path_and_stops_with_main')),
    ('reload-loop-application-omitted',RECV,'receiver.reload_mappings(new_mappings, new_macro_settings)','pass',case('ReloadIntegrationTests.test_save_and_disk_reload_versions_and_real_midi')),
    ('last-good-cleared-on-error',RECV,'LOGGER.error("hot-reload failed: %s", exc)','receiver.reload_mappings({}, MacroSettings())',case('ReloadIntegrationTests.test_half_write_keeps_last_good_then_full_write_applies')),
    ('applied-version-omitted',RECV,'self.state_version += 1','pass',case('ReloadIntegrationTests.test_save_and_disk_reload_versions_and_real_midi')),
    ('api-version-disconnected',MAIN,'state_version_fn=lambda: receiver.state_version','state_version_fn=lambda: 0',case('ReloadIntegrationTests.test_explicit_reload_requests_event_without_claiming_application')),
    ('api-reload-event-omitted',API,'def reload_now() -> Response:\n            self.reload_event.set()','def reload_now() -> Response:\n            pass',case('ReloadIntegrationTests.test_explicit_reload_requests_event_without_claiming_application')),
    ('disk-identity-not-read',MAIN,'if new_stamp != settings_stamp:', 'if False:',case('ReloadIntegrationTests.test_disk_identity_changes_and_bad_settings_keep_last_good')),
    ('ui-timer-omitted',HTML,'setInterval(pollStateVersion, 2000);','',NODE),
    ('ui-clean-refresh-omitted',HTML,'else await loadAll(selectedSection, {preserveEdits: true});','else {}',NODE),
    ('ui-dirty-notice-omitted',HTML,"document.getElementById('presetChangeNotice').hidden = false;",'return;',NODE),
    ('ui-all-draft-guards-omitted',HTML,'return dirty || formDirty;', 'return false;',NODE),
    ('ui-inflight-guard-omitted',HTML,'editRevision !== revision || (preserveEdits && hasUnsavedEdits())','false',NODE),
    ('ui-unapplied-fields-unguarded',HTML,'return dirty || formDirty;', 'return dirty;',NODE),
    ('ui-settings-draft-unguarded',HTML,"document.getElementById(grid).addEventListener(event, () => {","document.getElementById(grid).addEventListener(event, () => { return;",NODE),
    ('ui-engine-render-omitted',HTML,'    renderEngines();\n    if (selected) renderEditor(selected);','    if (selected) renderEditor(selected);',NODE),
    ('ui-editor-render-omitted',HTML,'    if (selected) renderEditor(selected);','',NODE),
    ('ui-explicit-reload-omitted',HTML,"await apiFetch('/api/reload', {method: 'POST'});",'',NODE),
    ('ui-explicit-reload-loses-later-edit',HTML,'if (editRevision !== revision) { showPresetChangeNotice(); return; }','',NODE),
    ('ui-missing-section-fallback-omitted',HTML,'if (e.httpStatus === 422 && section != null) return loadAll(null, {preserveEdits});','',NODE),
]
results = []
def run(name, cmd, red=False):
    proc = subprocess.run(cmd,cwd=COPY,env=ENV,capture_output=True,text=True,timeout=30)
    output = proc.stdout+proc.stderr
    (SCRATCH / (name+'.log')).write_text(output)
    passed = proc.returncode != 0 if red else proc.returncode == 0
    if red and any(error in output for error in ('SyntaxError:', 'IndentationError:', 'ModuleNotFoundError:')):
        passed = False
    result = {'name':name,'expected':'RED' if red else 'GREEN','exit':proc.returncode,'passed':passed}
    results.append(result)
    print(json.dumps(result),flush=True)
    if not passed:
        raise SystemExit('Unexpected control result: '+name)
run('pristine-python',PYTHON)
run('pristine-ui',NODE)
run('pristine-sections',SECTIONS)
for name,path,before,after,cmd in controls:
    source = originals[path]
    assert before in source, name
    try:
        (COPY/path).write_text(source.replace(before,after))
        run(name,cmd,True)
    finally:
        (COPY/path).write_text(source)
run('restored-python',PYTHON)
run('restored-ui',NODE)
run('restored-sections',SECTIONS)
(SCRATCH/'results.json').write_text(json.dumps(results,indent=2)+'\n')
print(f'{len(controls)} regressions caught; pristine and restored checks green')
