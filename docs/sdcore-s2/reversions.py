"""Run S2 regression controls in scratch copies; never mutate the run root.

Usage: .venv/bin/python docs/sdcore-s2/reversions.py
Requires Node for the editor-script checks; no production dependency is added.
"""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = Path('/tmp/sdcore-s2/reversions')
SCRATCH.mkdir(parents=True, exist_ok=True)
COPY = SCRATCH / 'source'
COPY.mkdir(exist_ok=True)
for folder in ('windows', 'tests', 'shared', 'common'):
    source = ROOT / folder
    if source.exists():
        shutil.copytree(source, COPY / folder, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__'))
(COPY / 'docs').mkdir(exist_ok=True)
shutil.copyfile(ROOT / 'docs/api.md', COPY / 'docs/api.md')
ENV = {**os.environ, 'TMPDIR': str(SCRATCH), 'PYTHONDONTWRITEBYTECODE': '1'}
PYTHON = [sys.executable, '-B', '-m', 'unittest', 'tests.test_ui_server', 'tests.test_engine_states']
NODE = ['node', 'tests/ui_sections_check.cjs']
API = 'windows/ui_server.py'
HTML = 'windows/static/index.html'
originals = {name: (COPY / name).read_text() for name in (API, HTML)}
controls = [
    ('requested-section-ignored', API,
     'section = request.args.get("section", self.bridge_settings.preset_section)',
     'section = self.bridge_settings.preset_section', PYTHON),
    ('section-list-omitted', API, '"sections": list(raw.get("sections", {})),', '"sections": [],', PYTHON),
    ('save-flattens-preset', API, "raw = json.loads(content)\n    select_preset_section(raw, section)",
     "return json.dumps(document)\n    raw = json.loads(content)\n    select_preset_section(raw, section)", PYTHON),
    ('siblings-reserialized', API, 'return content[:start] + json.dumps(document, indent=2) + content[end:]',
     'raw["sections"][section] = document\n    return json.dumps(raw, indent=2)', PYTHON),
    ('loader-validation-omitted', API, 'load_midi_map(tmp_path, section)', 'pass', PYTHON),
    ('live-engine-state-bleeds-to-remote', API,
     'if "document" not in body and section == self.bridge_settings.preset_section:', 'if True:', PYTHON),
    ('copy-ignores-source', API, 'copy.deepcopy(sections[source]) if source else {"mappings": {}}', '{"mappings": {}}', PYTHON),
    ('own-delete-guard-omitted', API, 'if name == own:', 'if False:', PYTHON),
    ('last-delete-guard-omitted', API, 'if len(sections) == 1:', 'if False:', PYTHON),
    ('rename-identity-omitted', API, 'if first_section or (operation == "rename" and body["old"] == own):', 'if first_section:', PYTHON),
    ('first-identity-omitted', API, 'if first_section or (operation == "rename" and body["old"] == own):',
     'if operation == "rename" and body["old"] == own:', PYTHON),
    ('identity-failure-rollback-omitted', API, 'self._write_preset(active, original)', 'pass', PYTHON),
    ('reload-signals-omitted', API, 'self.reload_event.set()', 'pass', PYTHON),
    ('atomic-replacement-omitted', API, 'os.replace(tmp_path, target)', 'target.write_text(content)', PYTHON),
    ('save-as-engine-state-at-top-level', API, 'current_content = _section_content(current_content, section, document)',
     'current_content = json.dumps({**doc, "engines": engine_states})', PYTHON),
    ('section-list-switches-preset', API, 'raw = json.loads(target.read_text(encoding="utf-8"))',
     'set_active_preset(self.presets_dir, target.name)\n                raw = json.loads(target.read_text(encoding="utf-8"))', PYTHON),
    ('ui-section-query-omitted', HTML,
     "apiFetch('/api/mappings' + (section == null ? '' : '?section=' + encodeURIComponent(section))),",
     "apiFetch('/api/mappings'),", NODE),
    ('ui-unsaved-guard-omitted', HTML, 'if (!discardChanges()) { renderSectionSelector(); return; }', '', NODE),
    ('ui-load-skips-engine-render', HTML, '    await renderEngines();\n    if (selected) renderEditor(selected);',
     '    if (selected) renderEditor(selected);', NODE),
    ('ui-renders-local-engine-states', HTML,
     'Object.hasOwn(engineStates, e.type) ? engineStates[e.type] : (isLocalSection() ? e.active : null)', 'e.active', NODE),
    ('ui-save-targets-local-section', HTML, 'JSON.stringify({section: selectedSection, document: body})',
     'JSON.stringify({section: bridgeSection, document: body})', NODE),
    ('ui-remote-toggle-is-live', HTML, 'if (isLocalSection() && engineCatalog.some(e => e.type === type))',
     'if (engineCatalog.some(e => e.type === type))', NODE),
    ('ui-save-materializes-shared', HTML,
     'if (s && (Object.hasOwn(sectionDocument.mappings || {}, a) || JSON.stringify(s) !== JSON.stringify(sharedMappings[a]))) mappings[a] = s;',
     'if (s) mappings[a] = s;', NODE),
    ('api-bar-missing-route', HTML, "'/api/presets/sections/add'", "'/api/this-route-does-not-exist'", PYTHON),
    ('html-unclosed-element', HTML, '</body>', '<div></body>', PYTHON),
]
results = []
def run(label, command, expect_red=False):
    result = subprocess.run(command, cwd=COPY, env=ENV, capture_output=True, text=True)
    (SCRATCH / (label + '.log')).write_text(result.stdout + result.stderr)
    passed = (result.returncode != 0) if expect_red else (result.returncode == 0)
    row = {'name': label, 'expected': 'RED' if expect_red else 'GREEN',
           'exit': result.returncode, 'passed': passed}
    results.append(row)
    print(json.dumps(row), flush=True)
    if not passed:
        raise SystemExit(f'Unexpected control result: {label}; inspect {SCRATCH}')

run('pristine-python', PYTHON)
run('pristine-ui', NODE)
for label, filename, before, after, command in controls:
    content = originals[filename]
    if before not in content:
        raise SystemExit(f'Mutation anchor missing: {label}')
    target = COPY / filename
    try:
        target.write_text(content.replace(before, after))
        run(label, command, expect_red=True)
    finally:
        target.write_text(content)
run('restored-python', PYTHON)
run('restored-ui', NODE)
(SCRATCH / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
print(f'{len(controls)} regressions caught; pristine and restored Python/UI checks green')
