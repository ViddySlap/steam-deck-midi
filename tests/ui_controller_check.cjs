// Real page + external controller script; fake DOM/HTTP, no receiver or MIDI.
// Run: node tests/ui_controller_check.cjs [path/to/index.html]
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const pagePath = path.resolve(process.argv[2] || 'windows/static/index.html');
const staticRoot = path.dirname(pagePath);
const html = fs.readFileSync(pagePath, 'utf8');
const relation = JSON.parse(fs.readFileSync(path.join(staticRoot, 'controller/controller_map.json')));
const artwork = fs.readFileSync(path.join(staticRoot, 'controller/steam_deck.svg'), 'utf8');
const decode = s => s.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'");

function harness(stored = null, storageFails = false, assetFails = false) {
  let document;
  class Element {
    constructor(tag = 'div') {
      this.localName = tag; this.children = []; this.dataset = {}; this.style = {};
      this.attrs = {}; this.listeners = {}; this.className = ''; this.hidden = false;
      this.value = ''; this._text = ''; this.id = '';
      this.classList = {
        contains: name => this.className.split(/\s+/).includes(name),
        toggle: (name, force) => {
          const classes = new Set(this.className.split(/\s+/).filter(Boolean));
          if (force ?? !classes.has(name)) classes.add(name); else classes.delete(name);
          this.className = [...classes].join(' ');
        },
        add: name => this.classList.toggle(name, true),
        remove: name => this.classList.toggle(name, false),
      };
    }
    setAttribute(name, value) {
      value = String(value); this.attrs[name] = value;
      if (name === 'class') this.className = value;
      if (name === 'id') this.id = value;
      if (name === 'value') this.value = value;
      if (name === 'hidden') this.hidden = true;
      if (name === 'selected') this.selected = true;
      if (name.startsWith('data-')) this.dataset[name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = value;
    }
    getAttribute(name) { return this.attrs[name]; }
    appendChild(child) {
      if (child.parentNode) child.parentNode.children = child.parentNode.children.filter(c => c !== child);
      this.children.push(child); child.parentNode = this;
      if (this.localName === 'select' && (child.selected || this.children.length === 1)) this.value = child.value;
      return child;
    }
    replaceChildren(...children) { this.children = []; this._text = ''; children.forEach(c => this.appendChild(c)); }
    addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
    async fire(name, event = {}) {
      if (this.disabled && name === 'click') return;
      const e = {target: this, preventDefault() {}, ...event};
      for (const fn of this.listeners[name] || []) await fn(e);
      if (this['on' + name]) await this['on' + name](e);
      if (['input', 'change'].includes(name) && this.parentNode) await this.parentNode.fire(name, e);
    }
    focus() { document.activeElement = this; }
    set textContent(value) { this.replaceChildren(); this._text = String(value); }
    get textContent() { return this._text + this.children.map(c => c.textContent).join(''); }
    set innerHTML(value) { this.replaceChildren(); parse(value, this); }
    get innerHTML() { return this.textContent; }
    matches(selector) {
      const attr = selector.match(/\[([^=\]]+)(?:="([^"]*)")?\]/);
      const base = selector.replace(/\[.*\]/, '');
      const baseOk = !base || (base[0] === '.' ? this.classList.contains(base.slice(1)) :
        base[0] === '#' ? this.id === base.slice(1) : this.localName === base);
      const val = attr && (attr[1].startsWith('data-') ? this.dataset[attr[1].slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] : this.getAttribute(attr[1]));
      return baseOk && (!attr || (attr[2] === undefined ? val !== undefined : val === attr[2]));
    }
    querySelectorAll(selector) {
      return this.children.flatMap(child => [...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector)]);
    }
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  }
  function parse(markup, parent = new Element('root')) {
    const stack = [parent];
    for (const token of markup.replace(/<!--[\s\S]*?-->/g, '').match(/<[^>]*>|[^<]+/g) || []) {
      if (token.startsWith('</')) { if (stack.length > 1) stack.pop(); continue; }
      if (token.startsWith('<!')) continue;
      if (token[0] === '<') {
        const tag = token.match(/^<([\w-]+)/)?.[1]; if (!tag) continue;
        const node = new Element(tag);
        for (const m of token.slice(tag.length + 1, -1).matchAll(/([\w:-]+)(?:="([^"]*)"|='([^']*)')?/g)) node.setAttribute(m[1], decode(m[2] ?? m[3] ?? ''));
        stack.at(-1).appendChild(node);
        if (!token.endsWith('/>') && !['input','link','meta','br','hr','img'].includes(tag)) stack.push(node);
      } else {
        const node = new Element('#text'); node._text = decode(token); stack.at(-1).appendChild(node);
      }
    }
    for (const select of parent.querySelectorAll('select')) select.value = (select.children.find(c => c.selected) || select.children[0])?.value || '';
    return parent;
  }
  document = parse(html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/g, '').replace(/<style>[\s\S]*?<\/style>/g, ''));
  document.getElementById = id => document.querySelector('#' + id);
  document.createElement = tag => new Element(tag);
  document.createElementNS = (_, tag) => new Element(tag);
  document.importNode = node => node;
  const storage = new Map(stored === null ? [] : [['steamdeck.mappingView', stored]]);
  const data = {version: 0, calls: [], requests: [], conflicts: [], macros: [], copied: null, sections: {
    windows: {L2_SOFT: {type:'note', channel:0, note:36, velocity:100}, L_TRIGGER_PRESSURE: {type:'axis_to_cc', cc:11}},
    macbook: {L2_FULL: {type:'cc', channel:1, cc:22}},
  }};
  const context = vm.createContext({document, console, setTimeout() {}, setInterval() {},
    window: {confirm: () => true},
    navigator: {clipboard: {writeText: async text => { data.copied = text; }}},
    localStorage: {
      getItem(key) { if (storageFails) throw new Error('Storage denied'); return storage.get(key) ?? null; },
      setItem(key, value) { if (storageFails) throw new Error('Storage denied'); storage.set(key, value); },
    },
    DOMParser: class { parseFromString(text) { const root = parse(text); return {documentElement:root.children[0], querySelector:s => root.querySelector(s)}; } },
    fetch: async (url, options = {}) => {
      data.calls.push(url);
      data.requests.push({url, ...options});
      const response = body => ({ok:true, json:async() => JSON.parse(JSON.stringify(body))});
      if (url === '/static/controller/steam_deck.svg') return {ok:!assetFails, status:503, text:async() => artwork};
      if (url === '/api/controller-map') return response(relation);
      if (url === '/api/state-version') return response(data.version);
      if (url === '/api/actions') return response({actions:relation.controls.flatMap(c => Object.values(c.groups).flat())});
      if (url.startsWith('/api/mappings')) {
        const section = url.includes('?') ? decodeURIComponent(url.split('=')[1]) : 'windows';
        return response({mappings:data.sections[section], document:{mappings:data.sections[section]}, shared_mappings:{},
          section, bridge_section:'windows', sections:Object.keys(data.sections), preset:'Scratch.json', legacy:false});
      }
      if (url === '/api/engines') return response({engines:[]});
      if (url === '/api/presets') return response({presets:[]});
      if (url === '/api/macros') return response({macros:data.macros});
      if (url === '/api/conflicts') return response({conflicts:data.conflicts});
      if (url === '/api/save') {
        const body = JSON.parse(options.body);
        data.sections[body.section] = body.document.mappings;
        return response({saved_to:'Scratch.json'});
      }
      if (url === '/api/reset') {
        data.sections[JSON.parse(options.body).section] = {};
        return response({ok:true});
      }
      if (url === '/api/reload') return response({ok:true});
      throw new Error('Unexpected request: ' + url);
    },
  });
  // Load scripts in the exact document order, including the shipped boot calls.
  for (const match of html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)) {
    const src = match[1].match(/src="\/static\/([^"]+)"/);
    vm.runInContext(src ? fs.readFileSync(path.join(staticRoot, src[1]), 'utf8') : match[2], context);
  }
  return {document, data, storage, run: code => vm.runInContext(code, context)};
}
const settle = async () => { for (let i = 0; i < 40; i++) await Promise.resolve(); };
(async () => {
  const h = harness(); await settle();
  const {document: doc, run, data} = h;
  const id = name => doc.getElementById(name);
  const label = name => doc.querySelector(`.controller-label[data-control="${name}"]`);
  const row = name => id('controllerRows').querySelector(`[data-action="${name}"]`);
  assert.equal(id('controllerView').hidden, false, 'Controller is the default front door');
  assert.equal(id('editorContent').hidden, true);
  assert.equal(id('mappingSidebar').hidden, true);
  assert.equal(id('viewController').getAttribute('aria-pressed'), 'true');
  const arrows = doc.querySelectorAll('.controller-arrow');
  assert.equal(arrows.length, 23, 'exactly 23 visible arrows');
  assert.equal(doc.querySelectorAll('.controller-label').length, 23);
  assert.deepEqual(arrows.map(a => a.getAttribute('data-control-arrow')), relation.controls.map(c => c.id));
  const art = doc.querySelector('.controller-art');
  assert.deepEqual(art.querySelectorAll('[data-control]').map(n => n.dataset.control).sort(), relation.controls.map(c => c.id).sort(), 'original artwork covers each control once');
  for (const c of relation.controls) {
    const arrow = arrows.find(a => a.getAttribute('data-control-arrow') === c.id);
    assert.equal(Number(arrow.getAttribute('x2')), c.anchor.x);
    assert.equal(Number(arrow.getAttribute('y2')), c.anchor.y);
    assert.equal(label(c.id).localName, 'button', 'native keyboard activation');
    assert.ok(art.querySelector(`[data-control="${c.id}"]`).listeners.click.length);
  }
  assert.equal(label('l2').querySelector('small').textContent, '2/5', 'initial load refreshes counts');
  assert.ok(label('btn_a').classList.contains('control-unmapped'));
  assert.ok(!label('l2').classList.contains('control-unmapped'));
  await id('viewList').fire('click');
  assert.equal(id('controllerView').hidden, true);
  assert.equal(id('editorContent').hidden, false);
  assert.equal(id('mappingSidebar').hidden, false);
  assert.equal(h.storage.get('steamdeck.mappingView'), 'list');
  await id('viewController').fire('click');
  assert.equal(h.storage.get('steamdeck.mappingView'), 'controller');
  await label('l2').fire('click');
  assert.equal(id('controllerCard').hidden, false);
  assert.equal(id('controllerTitle').textContent, 'L2');
  assert.equal(doc.activeElement, id('controllerTitle'));
  assert.deepEqual(id('controllerRows').querySelectorAll('h3').map(n => n.textContent), ['TAP', 'LAYER 2', 'ANALOG']);
  assert.deepEqual(id('controllerRows').querySelectorAll('.controller-row').map(n => n.dataset.action),
    Object.values(relation.controls.find(c => c.id === 'l2').groups).flat());
  assert.equal(row('L2_SOFT').querySelector('.controller-description').textContent, run('mappingDesc(state.L2_SOFT)'));
  assert.equal(row('L2_SOFT').querySelector('.chip-badge').textContent, run('mappingBadge(state.L2_SOFT)'));
  assert.equal(row('L2_FULL').querySelector('.controller-description').textContent, 'unmapped');
  const types = [
    {type:'note', channel:2, note:60, velocity:90},
    {type:'cc', channel:2, cc:21},
    {type:'macro_cc', channel:2, cc:22, gesture:'long_press'},
    {type:'relative_cc', channel:2, cc:23, step_value:127},
    {type:'staged_note_macro', note:61},
    {type:'axis_to_cc', channel:2, cc:24},
    {type:'axis_split_cc', channel:2, cc_positive:25, cc_negative:26},
    null,
  ];
  for (const spec of types) {
    run(`commit('L2_SOFT', ${JSON.stringify(spec)})`);
    assert.equal(row('L2_SOFT').querySelector('.controller-description').textContent, run('mappingDesc(state.L2_SOFT)'));
    assert.equal(row('L2_SOFT').querySelector('.chip-badge').textContent, run("mappingBadge(state.L2_SOFT) || 'unmapped'"));
    assert.equal(label('l2').querySelector('small').textContent, spec ? '2/5' : '1/5');
    assert.match(row('L2_SOFT').textContent, /^[\x00-\x7f]*$/, 'new row text is ASCII');
  }
  run("commit('L2_SOFT', {type:'cc',channel:3,cc:77})");
  assert.equal(row('L2_SOFT').querySelector('.controller-description').textContent, 'ch4 | CC 77', 'commit refreshes open row');
  assert.equal(row('L2_SOFT').querySelector('.chip-badge').textContent, 'CC');
  assert.equal(doc.querySelector('.chip[data-action="L2_SOFT"]').querySelector('.chip-desc').textContent,
    row('L2_SOFT').querySelector('.controller-description').textContent, 'List and Controller share descriptions');
  assert.equal(run('dirty'), true);
  await row('L2_SOFT').querySelector('.controller-open-list').fire('click');
  assert.equal(run('selected'), 'L2_SOFT');
  assert.equal(id('editorContent').hidden, false);
  assert.equal(id('typeSelect').value, 'cc', 'original List form is mounted for this action');
  assert.equal(id('f_cc').value, 77);
  await id('viewController').fire('click');
  await run("switchSection('macbook')");
  assert.equal(label('l2').querySelector('small').textContent, '1/5', 'section changes update counts');
  assert.equal(row('L2_SOFT').querySelector('.controller-description').textContent, 'unmapped');
  assert.equal(row('L2_FULL').querySelector('.controller-description').textContent, 'ch2 | CC 22');
  data.sections.macbook.L2_FULL.cc = 91; data.version++;
  await run('pollStateVersion()');
  assert.equal(row('L2_FULL').querySelector('.controller-description').textContent, 'ch2 | CC 91', 'clean hot reload reaches card');
  run("commit('L2_FULL', {type:'note',note:99})");
  data.sections.macbook.L2_FULL.cc = 50; data.version++;
  await run('pollStateVersion()');
  assert.equal(row('L2_FULL').querySelector('.controller-description').textContent, 'ch1 | note 99  vel 127', 'dirty draft survives hot reload');
  assert.equal(id('presetChangeNotice').hidden, false);
  await doc.fire('keydown', {key:'Escape'});
  assert.equal(id('controllerCard').hidden, true);
  assert.equal(doc.activeElement, label('l2'));
  assert.equal(label('l2').getAttribute('aria-expanded'), 'false');
  await art.querySelector('[data-control="left_pad"]').fire('click');
  assert.equal(id('controllerTitle').textContent, 'Left trackpad');
  assert.deepEqual(id('controllerRows').querySelectorAll('h3').map(n => n.textContent), ['TAP','LONG PRESS','ANALOG']);
  await id('controllerClose').fire('click');
  assert.equal(id('controllerCard').hidden, true);
  await doc.querySelector('.controller-arrow-hit[data-control="btn_a"]').fire('click');
  assert.equal(id('controllerTitle').textContent, 'A');
  run("switchTab('macrolib')");
  assert.equal(id('mappingSidebar').hidden, false, 'library keeps its original action selection');
  run("switchTab('editor')");
  assert.equal(id('mappingSidebar').hidden, true);
  const ids = doc.querySelectorAll('[id]').map(n => n.id);
  assert.equal(new Set(ids).size, ids.length, 'dynamic page IDs remain unique');
  const remembered = harness('list'); await settle();
  assert.equal(remembered.document.getElementById('editorContent').hidden, false, 'browser choice restored');
  const denied = harness('list', true); await settle();
  assert.equal(denied.document.getElementById('controllerView').hidden, false, 'denied storage defaults safely');
  await denied.document.getElementById('viewList').fire('click');
  assert.equal(denied.document.getElementById('editorContent').hidden, false, 'denied storage still switches');
  const failed = harness(null, false, true); await settle();
  assert.match(failed.document.getElementById('controllerPicture').textContent, /Controller could not load/);
  await failed.document.getElementById('viewList').fire('click');
  assert.equal(failed.document.getElementById('editorContent').hidden, false, 'asset failure leaves List usable');
  await checkEditing();
  console.log('UI controller behavior: PASS (23 arrows, map anchors/shapes, front door, storage, drill-in, List handoff, commit, sections, reload, Escape, unique IDs, asset failure)');
})().catch(error => { console.error(error); process.exitCode = 1; });

async function checkEditing() {
  const h = harness(); await settle();
  const {document:doc, data, run} = h;
  const id = name => doc.getElementById(name);
  const row = action => id('controllerRows').querySelector(`[data-action="${action}"]`);
  const open = control => doc.querySelector(`.controller-label[data-control="${control}"]`).fire('click');
  const click = (action, selector) => row(action).querySelector(selector).fire('click');
  const input = async (action, field, value) => {
    const node = id(`controller_${action}_${field}`);
    assert.ok(node, `scoped field exists: ${action}/${field}`);
    node.value = String(value); await node.fire('input');
  };
  const type = async (action, value) => {
    const node = row(action).querySelector('.controller-type'); node.value = value; await node.fire('change');
  };
  const spec = action => JSON.parse(run(`JSON.stringify(state[${JSON.stringify(action)}])`));
  const stateJson = () => run('JSON.stringify(state)');
  await open('l2');
  await click('L2_SOFT', '.controller-edit');
  assert.equal(row('L2_SOFT').querySelector('.controller-inline-editor').hidden, false, 'Edit expands inline form');
  assert.deepEqual(row('L2_SOFT').querySelector('.controller-type').children.map(n => n.value),
    ['', 'note','cc','macro_cc','relative_cc','staged_note_macro','axis_to_cc','axis_split_cc']);
  await click('L2_FULL', '.controller-edit');
  await type('L2_FULL', 'note');
  assert.equal(id('controller_L2_FULL_f_note').value, 36, 'type change uses shared DEFAULTS');
  await input('L2_SOFT','f_note',65);
  await input('L2_FULL','f_note',89);
  await input('L2_SOFT','f_ch',3);
  await input('L2_SOFT','f_vel',91);
  await click('L2_SOFT','.controller-apply');
  assert.deepEqual(spec('L2_SOFT'), {type:'note',channel:3,note:65,velocity:91}, 'note form commits its own fields');
  assert.equal(id('controller_L2_FULL_f_note')?.value, '89', 'sibling commit preserves typed fields');
  await click('L2_FULL','.controller-apply');
  assert.equal(spec('L2_FULL').note, 89, 'second row reads its own values');
  assert.equal(run('dirty'), true);
  assert.equal(id('btnSave').disabled, false);
  run("selectAction('L2_SOFT')");
  await input('L2_SOFT','f_note',66); await click('L2_SOFT','.controller-apply');
  await id('viewList').fire('click');
  assert.equal(Number(id('f_note').value),66,'one-click List shows committed Controller edit');
  await id('viewController').fire('click');
  const openIds=doc.querySelectorAll('[id]').map(n => n.id);
  assert.equal(new Set(openIds).size,openIds.length,'two open rows and List use distinct field IDs');

  const forms = [
    ['cc', {f_ch:4,f_cc:51,f_on:110,f_off:2}, {type:'cc',channel:4,cc:51,on_value:110,off_value:2}],
    ['macro_cc', {f_ch:4,f_cc:52,f_gesture:'long_press',f_fade:2.5}, {type:'macro_cc',channel:4,cc:52,gesture:'long_press',fade_duration_seconds:2.5}],
    ['relative_cc', {f_ch:4,f_cc:53,f_step:127,f_ri:65}, {type:'relative_cc',channel:4,cc:53,step_value:127,repeat_interval_ms:65}],
    ['staged_note_macro', {f_note:74,f_vel:105,f_mch:2,f_tch:5,f_ra:'L_PAD_LEFT, L_PAD_RIGHT',f_delay:123,f_hold:456},
      {type:'staged_note_macro',note:74,velocity:105,modifier_channel:2,trigger_channel:5,refresh_actions:['L_PAD_LEFT','L_PAD_RIGHT'],macro_delay_ms:123,modifier_hold_ms:456}],
    ['axis_to_cc', {f_ch:7,f_cc:64,f_irmin:-20000,f_irmax:21000,f_ormin:4,f_ormax:120,f_dz:900,f_curve:'quadratic'},
      {type:'axis_to_cc',channel:7,cc:64,input_range:[-20000,21000],output_range:[4,120],deadzone:900,curve:'quadratic'}],
    ['axis_split_cc', {f_ch:9,f_ccp:80,f_ccn:81,f_imax:30000,f_dz:650,f_curve:'s_curve'},
      {type:'axis_split_cc',channel:9,cc_positive:80,cc_negative:81,input_max:30000,deadzone:650,curve:'s_curve'}],
  ];
  for (const [name, fields, expected] of forms) {
    const action = name.startsWith('axis') ? 'L_TRIGGER_PRESSURE' : 'L2_SOFT';
    if (row(action).querySelector('.controller-inline-editor').hidden) await click(action,'.controller-edit');
    await type(action,name);
    for (const [key,value] of Object.entries(fields)) await input(action,key,value);
    await click(action,'.controller-apply');
    assert.deepEqual(spec(action),expected, `${name} form commits its fields`);
  }
  const beforeInvalid = stateJson();
  await input('L_TRIGGER_PRESSURE','f_ch',16);
  await click('L_TRIGGER_PRESSURE','.controller-apply');
  assert.equal(stateJson(),beforeInvalid,'invalid fields commit nothing');
  assert.match(row('L_TRIGGER_PRESSURE').querySelector('.json-err').textContent,/Invalid value/);
  await input('L_TRIGGER_PRESSURE','f_ch',9);
  await click('L_TRIGGER_PRESSURE','.controller-apply');
  await click('L2_FULL','.controller-clear');
  assert.equal(spec('L2_FULL'),null,'Clear commits null');

  // Execute the actual List wrapper and inline picker on the same target/spec.
  const macros = [
    {id:'fade',name:'Fade',type:'macro_cc',gesture:'long_press'},
    {id:'tick',name:'Tick',type:'relative_cc',step_value:127,repeat_interval_ms:80},
    {id:'stage',name:'Stage',type:'staged_note_macro',modifier_channel:6,trigger_channel:8,refresh_actions:['L_PAD_LEFT']},
  ];
  for (const macro of macros) {
    const original = {...(forms.find(f => f[0] === macro.type)[2])};
    run(`macroLibrary = ${JSON.stringify(macros)}; state.L2_SOFT = ${JSON.stringify(original)}; selected = 'L2_SOFT'; applyMacroToSelected(${JSON.stringify(macro)});`);
    const listResult = spec('L2_SOFT');
    run(`commit('L2_SOFT', ${JSON.stringify(original)});`);
    const picker = row('L2_SOFT').querySelector('.controller-macro');
    assert.equal(picker.children.find(n => n.value === macro.id).disabled,false,'compatible macro is enabled');
    picker.value = macro.id; await picker.fire('change');
    assert.deepEqual(spec('L2_SOFT'),listResult,'inline macro merge matches List');
    assert.equal(id('controllerView').hidden,false,'macro stays in Controller view');
  }
  const picker = row('L2_SOFT').querySelector('.controller-macro');
  assert.equal(picker.children.find(n => n.value === 'fade').disabled,true,'incompatible macro is disabled');
  const beforeMacro = stateJson(); picker.value='fade'; await picker.fire('change');
  assert.equal(stateJson(),beforeMacro,'incompatible picker refuses without commits');

  await id('controllerAdvancedTab').fire('click');
  assert.equal(id('controllerRows').hidden,true);
  assert.equal(id('controllerAdvanced').hidden,false);
  const raw = () => id('controllerAdvanced').querySelector('.controller-json');
  const apply = () => id('controllerAdvanced').querySelector('.controller-json-apply').fire('click');
  assert.deepEqual(Object.keys(JSON.parse(raw().value)),Object.values(relation.controls.find(c => c.id === 'l2').groups).flat());
  const beforeJson = stateJson();
  for (const [value,pattern] of [
    ['{"L2_SOFT":', /JSON error/],
    [JSON.stringify({L2_SOFT:{type:'note',note:11},BTN_A:{type:'note',note:12}}), /does not belong/],
    [JSON.stringify({L2_SOFT:{type:'note',note:11},L2_FULL:[]}), /expected a mapping object/],
    ['[]',/Expected an object/], ['null',/Expected an object/],
  ]) {
    raw().value=value; await raw().fire('input'); await apply();
    assert.equal(stateJson(),beforeJson,'bad Advanced input commits nothing');
    assert.match(id('controllerAdvanced').querySelector('.json-err').textContent,pattern);
  }
  raw().value=JSON.stringify({L2_SOFT:{type:'note',channel:1,note:101,velocity:99},L2_FULL:null});
  await raw().fire('input'); await apply();
  assert.deepEqual(spec('L2_SOFT'),{type:'note',channel:1,note:101,velocity:99},'Advanced commits mapping');
  assert.equal(spec('L2_FULL'),null,'Advanced explicit null clears');
  assert.equal(spec('L_TRIGGER_PRESSURE'),null,'Advanced omitted ID clears');
  await id('controllerAdvanced').querySelector('.controller-json-copy').fire('click');
  assert.equal(data.copied,raw().value.trim(),'Copy writes current JSON to clipboard');

  await id('controllerMappingsTab').fire('click');
  await type('L2_SOFT','cc'); await input('L2_SOFT','f_cc',72); await click('L2_SOFT','.controller-apply');
  data.conflicts=[{channel:0,cc:72,actions:['L2_SOFT','BTN_A']}];
  const saves = () => data.requests.filter(r => r.url === '/api/save');
  const saveCount=saves().length;
  await id('btnSave').fire('click');
  assert.equal(id('conflictOverlay').classList.contains('open'),true,'Save opens existing conflict modal');
  assert.equal(saves().length,saveCount,'conflict modal stops save');
  assert.ok(row('L2_SOFT').classList.contains('controller-conflict'),'open control conflicting row marked');
  assert.ok(!row('L2_FULL').classList.contains('controller-conflict'),'non-conflicting row unmarked');
  await id('btnConflictCancel').fire('click');
  assert.ok(!row('L2_SOFT').classList.contains('controller-conflict'),'cancel clears row markers');
  assert.equal(saves().length,saveCount);
  await id('btnSave').fire('click'); await id('btnConflictForce').fire('click'); await settle();
  assert.equal(saves().length,saveCount+1,'force uses existing save path');
  assert.equal(JSON.parse(saves().at(-1).body).document.mappings.L2_SOFT.cc,72);
  assert.equal(id('conflictOverlay').classList.contains('open'),false);
  assert.ok(!row('L2_SOFT').classList.contains('controller-conflict'));
  data.conflicts=[];

  await run('loadAll()');
  await click('L2_SOFT','.controller-edit');
  await input('L2_SOFT','f_cc',93);
  assert.equal(run('dirty'),false,'typed row remains unapplied');
  assert.equal(run('formDirty'),true,'typed inline field participates in draft listener');
  assert.equal(run('hasUnsavedEdits()'),true);
  const loads = data.calls.filter(url => url.startsWith('/api/mappings')).length;
  data.version++;
  await run('pollStateVersion()');
  assert.equal(data.calls.filter(url => url.startsWith('/api/mappings')).length,loads,'typed row prevents hot reload');
  assert.equal(id('controller_L2_SOFT_f_cc').value,'93','typed row survives hot reload');
  assert.equal(id('presetChangeNotice').hidden,false);
  // A sibling commit and Save must not clear this unapplied draft.
  await click('L2_FULL','.controller-clear');
  await id('btnSave').fire('click');
  assert.equal(run('hasUnsavedEdits()'),true,'sibling commit/save retains other row draft');
  await open('btn_a'); await open('l2');
  assert.equal(id('controller_L2_SOFT_f_cc').value,'93','control navigation preserves draft');
  run('window.confirm = () => false');
  await run("switchSection('macbook')");
  assert.equal(run('selectedSection'),'windows','section switch confirms unapplied draft');
  assert.equal(id('controller_L2_SOFT_f_cc').value,'93');
  run('window.confirm = () => true');
  await run("switchSection('macbook')");
  assert.equal(run('selectedSection'),'macbook');
  assert.equal(row('L2_SOFT').querySelector('.controller-type').value,'','accepted section load discards old draft');
  assert.equal(run('hasUnsavedEdits()'),false);
  await id('controllerAdvancedTab').fire('click');
  raw().value='{"L2_SOFT":'; await raw().fire('input'); data.version++;
  await run('pollStateVersion()');
  assert.equal(raw().value,'{"L2_SOFT":','Advanced draft survives poll');
  await id('btnReloadPreset').fire('click');
  assert.doesNotThrow(() => JSON.parse(raw().value),'explicit reload replaces Advanced draft');
  await id('btnReset').fire('click');
  assert.equal(id('resetOverlay').classList.contains('open'),true,'global Reset available from Controller');
  await id('btnResetConfirm').fire('click');
  assert.equal(spec('L2_FULL'),null,'Reset refreshes controller state');
  assert.equal(raw().value.includes('"type"'),false,'Reset refreshes Advanced JSON');
  const ids=doc.querySelectorAll('[id]').map(n => n.id);
  assert.equal(new Set(ids).size,ids.length,'multiple scoped editors and List have unique IDs');
  assert.match(id('controllerCard').textContent,/^[\x00-\x7f]*$/,'drill-in UI uses ASCII');
  await id('controllerMappingsTab').fire('click');
  await type('L2_SOFT','note'); await click('L2_SOFT','.controller-apply');
  await id('btnSave').fire('click'); await run('loadAll()');
  await click('L2_SOFT','.controller-edit');
  const pendingLoad = run('loadAll(selectedSection, {preserveEdits:true})');
  await input('L2_SOFT','f_note',112);
  assert.equal(await pendingLoad,false,'in-flight load cannot overwrite newly typed row');
  assert.equal(id('controller_L2_SOFT_f_note').value,'112','revision guard preserves inline input');
  console.log('UI controller editing: PASS (all seven forms, isolation, validation, clear, macro parity, Advanced, conflict guard, drafts, sections, reset)');
}
