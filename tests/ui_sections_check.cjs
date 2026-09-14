// Behavioral checks for the actual editor script, using a small DOM/HTTP double.
// Run: node tests/ui_sections_check.cjs [path/to/index.html]
// Real browser layout and native dialogs are owned by the chain gate.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(process.argv[2] || 'windows/static/index.html', 'utf8');
const source = html.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/\nloadAll\(\);\s*$/, '');
const elements = new Map();
function element() {
  return {
    textContent: '', innerHTML: '', value: '', children: [], listeners: {},
    classList: {toggle() {}, add() {}, remove() {}},
    addEventListener(name, handler) { this.listeners[name] = handler; },
    replaceChildren() { this.children = []; },
    appendChild(child) { this.children.push(child); },
    querySelectorAll(selector) {
      if (selector !== '.engine-toggle') return [];
      return [...this.innerHTML.matchAll(/<input[^>]+data-type="([^"]+)"[^>]*>/g)].map(match => ({
        dataset: {type: match[1]}, checked: /\schecked/.test(match[0]), addEventListener() {},
      }));
    },
  };
}
const document = {
  getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
  createElement: element, addEventListener() {}, querySelectorAll() { return []; },
};
const context = vm.createContext({document, assert, window: {confirm: () => true}, setTimeout() {}});
vm.runInContext(source, context);
vm.runInContext(`
  // Suppress unrelated rendering; execute the actual section, engine and save flows.
  renderSidebar = renderSettingsGrids = renderPresetDropdown = renderMacroLibrary = () => {};
  renderEditor = () => {};
  toast = () => {};
  let calls = [];
  let own = 'macbook';
  const documents = {
    macbook: {mappings: {BTN_A: {type:'note', channel:0, note:36}}, engines:{rec:true}},
    windows: {mappings: {BTN_A: {type:'note', channel:0, note:80}}, engines:{rec:false}},
  };
  const inherited = {BTN_B: {type:'note', channel:0, note:42}};
  apiFetch = async (path, opts = {}) => {
    const body = opts.body ? JSON.parse(opts.body) : null;
    calls.push({path, body});
    if (path.startsWith('/api/mappings')) {
      const section = path.includes('?section=') ? decodeURIComponent(path.split('?section=')[1]) : own;
      const doc = JSON.parse(JSON.stringify(documents[section]));
      return {...doc, mappings:{...inherited,...doc.mappings}, document:doc, shared_mappings:inherited,
              section, bridge_section:own, sections:Object.keys(documents), preset:'Show.json', legacy:false};
    }
    if (path === '/api/actions') return {actions:['BTN_A','BTN_B']};
    if (path === '/api/presets') return {presets:[]};
    if (path === '/api/macros') return {macros:[]};
    if (path === '/api/engines') return {engines:[{type:'rec',name:'Recorder',active:true}]};
    if (path === '/api/save') { documents[body.section] = body.document; return {ok:true,saved_to:'Show.json'}; }
    if (path === '/api/presets/sections/add') documents[body.name] = body.copy_from ? structuredCloneForTest(documents[body.copy_from]) : {mappings:{}};
    if (path === '/api/presets/sections/rename') {
      documents[body.new] = documents[body.old]; delete documents[body.old];
      if (own === body.old) own = body.new;
    }
    if (path === '/api/presets/sections/delete') delete documents[body.name];
    return {ok:true, bridge_section:own};
  };
  function structuredCloneForTest(value) {return JSON.parse(JSON.stringify(value));}
`, context);
(async () => {
  await vm.runInContext(`(async () => {
    assert.equal(await loadAll(), true);
    assert.equal(selectedSection, 'macbook');
    assert.equal(document.getElementById('sectionSelect').children.find(x => x.selected).textContent, 'macbook (this machine)');
    assert.equal(document.getElementById('sectionStatus').textContent, 'Machine: macbook | Preset: Show.json');
    assert.equal(document.getElementById('enginesList').querySelectorAll('.engine-toggle')[0].checked, true);
    setDirty(true); state.BTN_A.note = 99;
    window.confirm = () => false;
    const count = calls.length;
    await switchSection('windows');
    assert.equal(calls.length, count);
    assert.equal(selectedSection, 'macbook');
    assert.equal(state.BTN_A.note, 99);
    assert.equal(dirty, true);
    window.confirm = () => true;
    await switchSection('windows');
    assert.equal(selectedSection, 'windows');
    assert.equal(state.BTN_A.note, 80);
    assert.equal(document.getElementById('enginesList').querySelectorAll('.engine-toggle')[0].checked, false);
    assert.equal(document.getElementById('btnResyncOscWiggles').disabled, true);
    documents.windows.engines.rec = true;
    await loadAll();
    assert.equal(document.getElementById('enginesList').querySelectorAll('.engine-toggle')[0].checked, true);
    const togglesBefore = calls.filter(x => x.path.endsWith('/active')).length;
    await toggleEngine({dataset:{type:'rec'}, checked:false});
    assert.equal(dirty, true);
    assert.equal(calls.filter(x => x.path.endsWith('/active')).length, togglesBefore);
    await doSave();
    const saved = calls.findLast(x => x.path === '/api/save').body;
    assert.equal(saved.section, 'windows');
    assert.equal(saved.document.engines.rec, false);
    assert.equal(saved.document.mappings.BTN_A.note, 80);
    assert.equal('BTN_B' in saved.document.mappings, false, 'shared defaults must remain inherited');
    assert.equal(documents.macbook.engines.rec, true);
    assert.equal(dirty, false);
    await switchSection('macbook');
    await toggleEngine({dataset:{type:'rec'}, checked:false});
    assert.equal(calls.findLast(x => x.path.endsWith('/active')).path, '/api/engines/rec/active');
    assert.equal(calls.findLast(x => x.path.endsWith('/active')).body.active, false);
    setDirty(false);
    window.prompt = () => 'grandma';
    await document.getElementById('btnSectionAdd').listeners.click();
    assert.equal(calls.find(x => x.path === '/api/presets/sections/add').body.copy_from, 'macbook');
    assert.equal(selectedSection, 'grandma');
    window.prompt = () => 'grandma2';
    await document.getElementById('btnSectionRename').listeners.click();
    assert.equal(calls.find(x => x.path === '/api/presets/sections/rename').body.old, 'grandma');
    assert.equal(selectedSection, 'grandma2');
    await document.getElementById('btnSectionDelete').listeners.click();
    assert.equal(calls.find(x => x.path === '/api/presets/sections/delete').body.name, 'grandma2');
    assert.equal(selectedSection, 'macbook');
  })()`, context);
  console.log('UI section behavior: PASS (selection, dirty guard, engine refresh, remote save, shared inheritance, CRUD calls)');
})().catch(error => {console.error(error); process.exitCode = 1;});
