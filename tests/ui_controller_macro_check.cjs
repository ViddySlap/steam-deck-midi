// Execute the page's real macro/Save functions and compare with Flask disk writes.
// Run: node tests/ui_controller_macro_check.cjs [path/to/index.html]
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {spawnSync} = require('node:child_process');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(process.argv[2] || path.join(root, 'windows/static/index.html'), 'utf8');
const source = html.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/\nloadAll\(\);\s*$/, '');
const elements = new Map();
function element() {
  return {textContent:'', value:'', innerHTML:'', classList:{toggle(){},add(){},remove(){}},
    addEventListener(){}, querySelectorAll(){return []}, replaceChildren(){}, appendChild(){}};
}
const document = {getElementById(id){if(!elements.has(id)) elements.set(id,element());return elements.get(id)},
  createElement:element, addEventListener(){}, querySelectorAll(){return []}};
const context = vm.createContext({document, window:{}, setTimeout(){}, setInterval(){}});
vm.runInContext(source, context);
vm.runInContext(`
  renderEditor = renderMacroLibrary = refreshChip = updateCount = switchTab = toast = () => {};
  let savedDocument;
  apiFetch = async (url, opts) => {savedDocument = JSON.parse(opts.body).document; return {ok:true};};
`, context);
const macros = [
  {type:'macro_cc', gesture:'long_press'},
  {type:'macro_cc', gesture:'click', fade_duration_seconds:3},
  {type:'macro_cc', gesture:'click', fade_duration_seconds:8},
  {type:'macro_cc', gesture:'click', fade_duration_seconds:null},
  {type:'relative_cc', step_value:127, repeat_interval_ms:55},
  {type:'staged_note_macro', modifier_channel:4, trigger_channel:5, refresh_actions:['BTN_X']},
  {type:'staged_note_macro', modifier_channel:4, trigger_channel:5, macro_delay_ms:100, modifier_hold_ms:200},
  {type:'staged_note_macro'},
];
const currents = [null,
  {type:'note', note:36},
  {type:'macro_cc', channel:8, cc:65, gesture:'click', fade_duration_seconds:8},
  {type:'relative_cc', channel:8, cc:66, step_value:1, repeat_interval_ms:40},
  {type:'staged_note_macro', note:88, velocity:77, modifier_channel:0, trigger_channel:1,
    refresh_actions:['BTN_B'], macro_delay_ms:300, modifier_hold_ms:400},
];
(async () => {
  const cases = [];
  for (const flat of [false, true]) for (const inherited of [false, true]) {
    if (flat && inherited) continue;
    for (const current of currents) for (const macro of macros) {
      const document = {mappings: current && !inherited ? {BTN_A:current} : {}, engines:{}};
      const shared = current && inherited ? {BTN_A:current} : {};
      const setup = {current, macro, document, shared};
      context.input = JSON.parse(JSON.stringify(setup));
      const expected = await vm.runInContext(`(async () => {
        selected = 'BTN_A'; selectedSection = 'windows';
        sectionDocument = input.document; sharedMappings = input.shared;
        macroSettings = {}; analogSettings = {}; engineStates = {};
        state = input.current ? {BTN_A:input.current} : {};
        if (!macroCompatible(input.macro)) return {status:409};
        applyMacroToSelected(input.macro);
        await doSave();
        return {status:200, document:savedDocument};
      })()`, context);
      cases.push({flat, ...setup, expected:JSON.parse(JSON.stringify(expected))});
    }
  }
  const python = process.env.PYTHON || path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const result = spawnSync(python, ['-c', `
import json, sys
from tests.test_controller_routes import ControllerRouteTests
results = []
for case in json.load(sys.stdin):
    test = ControllerRouteTests()
    test.setUp()
    try:
        doc = case['document']
        raw = doc if case['flat'] else {'shared':{'mappings':case['shared']}, 'sections':{'windows':doc}}
        test.active.write_text(json.dumps(raw), encoding='utf-8')
        before = test.active.read_bytes()
        response = test.macro(case['macro'])
        results.append({'status':response.status_code, 'document':test.document(),
                        'unchanged':test.active.read_bytes() == before})
    finally:
        test.doCleanups()
print(json.dumps(results))
`], {cwd:root, input:JSON.stringify(cases), encoding:'utf8'});
  assert.equal(result.status, 0, result.stderr);
  const results = JSON.parse(result.stdout);
  assert.equal(results.length, cases.length);
  let accepted = 0, rejected = 0;
  cases.forEach((test, i) => {
    const actual = results[i];
    assert.equal(actual.status, test.expected.status, JSON.stringify(test));
    if (actual.status === 200) {assert.deepEqual(actual.document, test.expected.document); accepted++;}
    else {assert.equal(actual.unchanged, true); rejected++;}
  });
  assert.ok(accepted > 0 && rejected > 0);
  console.log(`Controller macro parity: ${accepted} disk writes match page Save; ${rejected} incompatible writes refused without byte changes`);
})().catch(error => {console.error(error); process.exitCode = 1;});
