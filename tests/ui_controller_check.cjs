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

function harness(stored = null, storageFails = false, assetFails = false, liveOptions = {}) {
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
    remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter(c => c !== this); this.parentNode = null; }
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
  if (liveOptions.follow !== undefined) storage.set('steamdeck.controllerFollow', String(liveOptions.follow));
  const data = {snapshot: liveOptions.snapshot || {pressed:[], axes:{}, midi:[], seq:7}, streams: [], version: 0, calls: [], requests: [], conflicts: [], macros: [], copied: null, sections: {
    windows: {L2_SOFT: {type:'note', channel:0, note:36, velocity:100}, L_TRIGGER_PRESSURE: {type:'axis_to_cc', cc:11}},
    macbook: {L2_FULL: {type:'cc', channel:1, cc:22}},
  }};
  let now = 1000, timerId = 0, frameId = 0, renderedFrames = 0;
  const timers = new Map(), frames = new Map();
  const window = new Element('window'); window.confirm = () => true;
  const tick = ms => {
    const end = now + ms;
    for (;;) {
      const due = [...timers].filter(([,t]) => t.at <= end).sort((a,b) => a[1].at-b[1].at)[0];
      if (!due) break;
      now = due[1].at; timers.delete(due[0]); due[1].fn();
    }
    now = end;
  };
  const frame = () => {
    const batch = [...frames.values()]; frames.clear();
    for (const fn of batch) { renderedFrames++; fn(now); }
    return batch.length;
  };
  const context = vm.createContext({document, console, AbortController, setInterval() {},
    setTimeout(fn, ms = 0) { const id = ++timerId; timers.set(id, {fn, at:now+ms}); return id; },
    clearTimeout(id) { timers.delete(id); },
    requestAnimationFrame(fn) { const id = ++frameId; frames.set(id, fn); return id; },
    cancelAnimationFrame(id) { frames.delete(id); },
    performance: {now: () => now}, window,
    EventSource: class {
      constructor(url) { this.url = url; this.closed = false; this.listeners = {}; data.streams.push(this); }
      addEventListener(kind, fn) { this.listeners[kind] = fn; }
      close() { this.closed = true; }
      emit(kind, payload) { this.listeners[kind]?.({data:JSON.stringify(payload)}); }
      open() { this.onopen?.(); }
      error() { this.onerror?.(); }
    },
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
      // Flask serializes object keys in sorted order; arrays keep map order.
      if (url === '/api/controller-map') return response(liveOptions.sortedGroups ? {...relation, controls:relation.controls.map(c =>
        ({...c, groups:Object.fromEntries(Object.entries(c.groups).sort(([a],[b])=>a.localeCompare(b)))}))} : relation);
      if (url === '/api/live/snapshot') {
        if (data.deferSnapshot) return data.deferSnapshot;
        if (data.snapshotFails) return {ok:false, status:503};
        return response(data.snapshot);
      }
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
        if (data.saveFails) { data.requests.at(-1).failed=true; return {ok:false, status:500, json:async()=>({error:'Planted save failure'})}; }
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
  return {document, window, data, storage, tick, frame, frames, timers, get renderedFrames() { return renderedFrames; }, run: code => vm.runInContext(code, context)};
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
  assert.equal(arrows.length, 24, 'exactly 24 visible arrows');
  assert.equal(doc.querySelectorAll('.controller-label').length, 24);
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
  await checkLive();
  console.log('UI controller behavior: PASS (24 arrows, map anchors/shapes, front door, storage, drill-in, List handoff, commit, sections, reload, Escape, unique IDs, asset failure)');
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
    [JSON.stringify({L2_SOFT:{type:'note',note:11},L2_FULL:{type:'staged_note_macro',refresh_actions:'L_PAD_LEFT'}}), /JSON error/],
    ['[]',/Expected an object/], ['null',/Expected an object/],
  ]) {
    raw().value=value; await raw().fire('input');
    await assert.doesNotReject(apply(), 'Advanced shape errors are inline before any commit');
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
  const saves = () => data.requests.filter(r => r.url === '/api/save' && !r.failed);
  const saveCount=saves().length;
  await id('btnSave').fire('click');
  assert.equal(id('conflictOverlay').classList.contains('open'),true,'Save opens existing conflict modal');
  assert.equal(saves().length,saveCount,'conflict modal stops save');
  assert.ok(row('L2_SOFT').classList.contains('controller-conflict'),'open control conflicting row marked');
  assert.ok(!row('L2_FULL').classList.contains('controller-conflict'),'non-conflicting row unmarked');
  await id('btnConflictCancel').fire('click');
  assert.ok(row('L2_SOFT').classList.contains('controller-conflict'),'cancel retains row markers');
  assert.equal(id('conflictOverlay').classList.contains('open'),false,'marks readable after modal closes');
  assert.match(row('L2_SOFT').querySelector('.controller-conflict-message').textContent,/MIDI CC conflict/);
  await open('btn_a');
  assert.ok(row('BTN_A').classList.contains('controller-conflict'),'marks persist across card navigation');
  await open('l2');
  assert.equal(saves().length,saveCount);
  data.saveFails=true;
  await id('btnSave').fire('click'); await id('btnConflictForce').fire('click'); await settle();
  assert.ok(row('L2_SOFT').classList.contains('controller-conflict'),'failed Save retains marks after modal closes');
  assert.equal(id('conflictOverlay').classList.contains('open'),false);
  data.saveFails=false;
  await id('btnSave').fire('click'); await id('btnConflictForce').fire('click'); await settle();
  assert.equal(saves().length,saveCount+1,'force uses existing save path');
  assert.equal(JSON.parse(saves().at(-1).body).document.mappings.L2_SOFT.cc,72);
  assert.equal(id('conflictOverlay').classList.contains('open'),false);
  assert.ok(!row('L2_SOFT').classList.contains('controller-conflict'),'successful Save clears row markers');
  assert.equal(row('L2_SOFT').querySelector('.controller-conflict-message'),null,'successful Save clears messages');
  data.conflicts=[];
  run("ControllerView.markConflicts([{channel:0,cc:72,actions:['L2_SOFT','BTN_A']}]); commit('L2_SOFT',{type:'cc',channel:0,cc:73});");
  assert.ok(!row('L2_SOFT').classList.contains('controller-conflict'),'resolving the channel/CC collision clears marks');

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

async function checkLive() {
  const h = harness(null, false, false, {sortedGroups:true}); await settle();
  const {document:doc, data} = h;
  const id = name => doc.getElementById(name);
  const label = name => doc.querySelector(`.controller-label[data-control="${name}"]`);
  const shape = name => doc.querySelector('.controller-art').querySelector(`[data-control="${name}"]`);
  const row = action => id('controllerRows').querySelector(`[data-action="${action}"]`);
  const dot = name => doc.querySelector(`[data-live-dot="${name}"]`);
  const bar = name => doc.querySelector(`[data-live-bar="${name}"]`);
  const streams = () => data.streams.at(-1);
  let seq = 7;
  const emit = (kind, action, rest = {}) => streams().emit(kind, {kind, action, seq:++seq, ...rest});
  const input = (action, state) => emit('input', action, {state});
  const axis = (action, value) => emit('axis', action, {value});
  const midi = action => emit('midi', action, {bytes:[144,36,100]});
  assert.equal(data.streams.length, 1, 'visible Controller owns one EventSource');
  assert.equal(streams().url, '/api/live/events?since=7', 'snapshot cursor covers connection gap');
  assert.equal(data.calls.filter(url => url === '/api/live/snapshot').length, 1);
  assert.equal(data.requests.find(r => r.url === '/api/live/snapshot').cache, 'no-store');
  h.frame();
  assert.equal(id('controllerFollow').getAttribute('aria-pressed'), 'false', 'follow defaults OFF');
  assert.equal(id('controllerLiveStatus').textContent, 'offline');
  streams().open(); h.frame();
  assert.equal(id('controllerLiveStatus').textContent, 'live');
  input('BTN_A', 'down');
  assert.ok(!shape('btn_a').classList.contains('control-down'), 'events do not paint synchronously');
  h.frame();
  assert.ok(shape('btn_a').classList.contains('control-down'), 'input down lights the physical shape');
  assert.ok(label('btn_a').classList.contains('control-down'), 'input down lights the label');
  assert.ok(!shape('btn_b').classList.contains('control-down'), 'unrelated control stays dark');
  assert.equal(id('controllerCard').hidden, true, 'follow off opens nothing');
  input('BTN_A_LAYER_2', 'down'); h.frame();
  assert.equal(label('btn_a').querySelector('.controller-live-tag').textContent, 'tap L2', 'group tags use tap/hold/layer order');
  input('BTN_A', 'up'); h.frame();
  assert.ok(shape('btn_a').classList.contains('control-down'), 'second held ID keeps its control lit');
  assert.equal(label('btn_a').querySelector('.controller-live-tag').textContent, 'L2');
  input('BTN_A_LAYER_2', 'up'); h.frame();
  assert.ok(!shape('btn_a').classList.contains('control-down'), 'last up clears the physical shape');
  assert.ok(!label('btn_a').classList.contains('control-down'));
  assert.equal(label('btn_a').querySelector('.controller-live-tag').hidden, true);
  input('DPAD_UP_LONG_PRESS', 'down'); h.frame();
  assert.ok(shape('dpad_up').classList.contains('control-down'));
  assert.equal(label('dpad_up').querySelector('.controller-live-tag').textContent, 'hold');
  input('DPAD_UP_LONG_PRESS', 'up'); h.frame();
  assert.equal(label('dpad_up').querySelector('.controller-live-tag').hidden, true);

  // Anchors come from the owned map, not from literals: the drawn arrangement moves
  // when the map moves, and these assertions are about the live overlay's arithmetic.
  const anchorOf = id => relation.controls.find(c => c.id === id).anchor;
  const LS = anchorOf('left_stick'), RS = anchorOf('right_stick'), LP = anchorOf('left_pad');
  assert.equal(Number(dot('left_stick').getAttribute('cx')), LS.x, 'wire zero is centered; sender already subtracts rest offset');
  const stickCaptions=doc.querySelector('.controller-art').querySelectorAll('text').filter(t => ['L3','R3'].includes(t.textContent));
  assert.equal(stickCaptions.length,2,'both stick captions are observed');
  for (const caption of stickCaptions) {
    const own = caption.textContent === 'L3' ? 'left_stick' : 'right_stick';
    assert.ok(Number(caption.getAttribute('y')) < Number(dot(own).getAttribute('cy')),
      'stick caption stays above the centered live dot');
  }
  axis('L_STICK_X_AXIS', 16324); axis('L_STICK_Y_AXIS', -16601);
  axis('R_STICK_X_AXIS', -33048); axis('R_STICK_Y_AXIS', 33103);
  axis('L_TRIGGER_PRESSURE', 16384); axis('R_TRIGGER_PRESSURE', 32767);
  h.frame();
  assert.equal(Number(dot('left_stick').getAttribute('cx')), LS.x+16324/32649*30, 'axis moves stick dot to computed X');
  assert.equal(Number(dot('left_stick').getAttribute('cy')), LS.y+16601/33202*30, 'axis moves stick dot to computed Y');
  assert.equal(Number(dot('right_stick').getAttribute('cx')), RS.x-30);
  assert.equal(Number(dot('right_stick').getAttribute('cy')), RS.y-30, 'positive wire Y points up');
  assert.equal(Number(bar('l2').getAttribute('width')), 16384/32767*64, 'trigger pressure sets proportional bar width');
  assert.equal(Number(bar('r2').getAttribute('width')), 64);
  axis('L_STICK_X_AXIS', 99999); axis('R_TRIGGER_PRESSURE', -100); h.frame();
  assert.equal(Number(dot('left_stick').getAttribute('cx')), LS.x+30, 'stick values clamp');
  assert.equal(Number(bar('r2').getAttribute('width')), 0, 'trigger values clamp');
  axis('L_STICK_X_AXIS', 0); axis('L_STICK_Y_AXIS', 0); h.frame();
  assert.equal(Number(dot('left_stick').getAttribute('cx')), LS.x);
  assert.equal(Number(dot('left_stick').getAttribute('cy')), LS.y);
  assert.equal(dot('left_pad').style.opacity, '0', 'no touch is implied before pad events');
  axis('L_PAD_X_POS', 32767); axis('L_PAD_Y_POS', -32768); h.frame();
  assert.equal(Number(dot('left_pad').getAttribute('cx')), LP.x+30);
  assert.equal(Number(dot('left_pad').getAttribute('cy')), LP.y+30);
  assert.equal(dot('left_pad').style.opacity, '1');
  h.tick(299); h.frame(); assert.equal(dot('left_pad').style.opacity, '1');
  h.tick(1); h.frame(); assert.equal(dot('left_pad').style.opacity, '0', 'pad fades after 300 ms without position events');
  axis('R_PAD_X_POS', -32768); h.frame();
  h.tick(200); axis('R_PAD_Y_POS', 32767); h.frame();
  h.tick(100); h.frame(); assert.equal(dot('right_pad').style.opacity, '1', 'either pad axis refreshes touch age');
  h.tick(200); h.frame(); assert.equal(dot('right_pad').style.opacity, '0');
  for (const [action, value, x] of [['GYRO_PITCH',32767,643],['GYRO_YAW',-32767,601],['GYRO_ROLL',0,622]]) {
    axis(action,value); h.frame();
    assert.equal(Number(doc.querySelector(`[data-live-axis="${action}"]`).getAttribute('cx')),x,'gyro indicator uses its own axis');
  }

  await label('l2').fire('click'); h.frame();
  const originalRow = row('L2_SOFT');
  input('L2_SOFT','down'); h.frame();
  assert.ok(!row('L2_SOFT').classList.contains('controller-midi-flash'), 'receive alone does not flash MIDI row');
  for (const action of ['L2_SOFT','L2_SOFT_LAYER_2','L_TRIGGER_PRESSURE']) {
    midi(action); h.frame();
    assert.deepEqual(id('controllerRows').querySelectorAll('.controller-midi-flash').map(r=>r.dataset.action),[action], 'MIDI flashes matching row only');
    h.tick(100); midi(action); h.frame(); h.tick(50); h.frame();
    assert.ok(row(action).classList.contains('controller-midi-flash'), 'MIDI flash retriggers');
    h.tick(100); h.frame();
    assert.ok(!row(action).classList.contains('controller-midi-flash'), 'MIDI flash expires after 150 ms');
  }
  midi(null); midi('BTN_B'); h.frame();
  assert.equal(id('controllerRows').querySelectorAll('.controller-midi-flash').length,0,'null and other-card MIDI flash nothing');
  assert.equal(row('L2_SOFT'),originalRow,'live rendering never rebuilds the open rows');
  await label('dpad_up').fire('click'); h.frame(); midi('DPAD_UP_LONG_PRESS'); h.frame();
  assert.deepEqual(id('controllerRows').querySelectorAll('.controller-midi-flash').map(r=>r.dataset.action),['DPAD_UP_LONG_PRESS']);
  h.tick(150); h.frame();

  await id('controllerFollow').fire('click'); h.frame();
  assert.equal(h.storage.get('steamdeck.controllerFollow'),'true','follow preference persists');
  assert.equal(id('controllerFollow').getAttribute('aria-pressed'),'true');
  input('BTN_A_LAYER_2','down'); midi('BTN_A_LAYER_2'); h.frame();
  assert.equal(id('controllerTitle').textContent,'A','follow on opens pressed control');
  assert.ok(row('BTN_A_LAYER_2').classList.contains('controller-midi-flash'),'same-frame follow retains matching MIDI flash');
  await row('BTN_A').querySelector('.controller-edit').fire('click');
  const type = row('BTN_A').querySelector('.controller-type'); type.value='note'; await type.fire('change');
  const note = id('controller_BTN_A_f_note'); note.value='86'; await note.fire('input'); h.frame();
  input('BTN_B','down'); h.frame();
  assert.equal(id('controllerTitle').textContent,'A','follow cannot switch cards over an unsaved inline edit');
  assert.equal(id('controller_BTN_A_f_note'),note,'follow preserves the actual draft node');
  assert.equal(note.value,'86');
  assert.equal(id('controllerFollowNote').hidden,false,'follow explains paused editing');
  assert.equal(id('controllerFollowNote').textContent,'follow paused: unsaved edit');
  await row('BTN_A').querySelector('.controller-apply').fire('click'); h.frame();
  input('BTN_X','down'); h.frame();
  assert.equal(id('controllerTitle').textContent,'A','applied but unsaved inline edit also pauses follow');
  await id('btnSave').fire('click'); h.frame();
  assert.equal(id('controllerTitle').textContent,'A','blocked follow press is not replayed after Save');
  input('BTN_X','down'); h.frame();
  assert.equal(id('controllerTitle').textContent,'X','saved card allows follow again');
  assert.equal(id('controllerFollowNote').hidden,true);
  await id('controllerAdvancedTab').fire('click');
  const raw=doc.querySelector('.controller-json'); raw.value='{"BTN_X":'; await raw.fire('input');
  input('BTN_Y','down'); h.frame();
  assert.equal(id('controllerTitle').textContent,'X','Advanced unsaved draft pauses follow');
  assert.equal(raw.value,'{"BTN_X":');
  await id('controllerFollow').fire('click'); h.frame();
  assert.equal(id('controllerFollowNote').hidden,true,'follow off clears pause note');
  const writeCount=data.requests.filter(r=>r.method && r.method!=='GET').length;
  await id('controllerFollow').fire('click'); h.frame(); await id('controllerFollow').fire('click'); h.frame();
  assert.equal(data.requests.filter(r=>r.method && r.method!=='GET').length,writeCount,'follow toggle is view-only');

  // Measure callbacks and DOM writes, not a caption or a production counter.
  const before=h.renderedFrames, oldX=dot('left_stick').getAttribute('cx');
  let paints=0;
  const toggle=shape('left_stick').classList.toggle;
  shape('left_stick').classList.toggle=(name,force)=>{ if(name==='control-down') paints++; return toggle(name,force); };
  for (let i=0;i<500;i++) axis('L_STICK_X_AXIS', i);
  assert.equal(dot('left_stick').getAttribute('cx'),oldX,'burst does not render in event callbacks');
  assert.equal(h.frames.size,1,'500 axis events schedule one animation frame');
  assert.equal(h.frame(),1,'500 axis events produce at most one render per frame');
  assert.equal(h.renderedFrames-before,1);
  assert.equal(paints,1,'burst paints each shape exactly once');
  assert.equal(Number(dot('left_stick').getAttribute('cx')),LS.x+499/32649*30,'burst paints latest axis value');
  assert.equal(h.frame(),0,'burst leaves no rendering backlog');

  // Loss, reconnect, cancellation and late-delivery races use actual shipped handlers.
  const lost=streams();
  data.snapshot={pressed:['BTN_B'],axes:{R_TRIGGER_PRESSURE:65535,L_PAD_X_POS:32767},midi:[{action:'BTN_B'}],seq:9000};
  lost.emit('dropped',{seq:8999,count:1});
  assert.equal(lost.closed,true,'dropped stream closes before resync');
  h.tick(0); await settle(); h.frame();
  assert.equal(streams().url,'/api/live/events?since=9000','drop resumes from fresh snapshot');
  assert.ok(shape('btn_b').classList.contains('control-down'),'snapshot restores held input');
  streams().emit('input',{seq:8999,action:'BTN_B',state:'up'}); h.frame();
  assert.ok(shape('btn_b').classList.contains('control-down'),'old event cannot overwrite snapshot state');
  streams().emit('input',{seq:9001,action:'BTN_B',state:'up'}); h.frame();
  assert.ok(!shape('btn_b').classList.contains('control-down'),'newer event updates snapshot state');
  assert.ok(!shape('l2').classList.contains('control-down'),'snapshot clears missed releases');
  assert.equal(Number(bar('r2').getAttribute('width')),64,'snapshot restores axes');
  assert.equal(dot('left_pad').style.opacity,'0','snapshot cannot revive an old pad touch');
  assert.equal(id('controllerRows').querySelectorAll('.controller-midi-flash').length,0,'snapshot history never replays flashes');
  const prior=data.streams.length;
  streams().error(); h.frame();
  assert.equal(id('controllerLiveStatus').textContent,'offline');
  assert.equal(streams().closed,true,'error closes native reconnecting stream');
  h.tick(249); await settle(); assert.equal(data.streams.length,prior,'reconnect waits for backoff');
  h.tick(1); await settle(); assert.equal(data.streams.length,prior+1);
  streams().error(); h.tick(499); await settle(); assert.equal(data.streams.length,prior+1,'consecutive error doubles backoff');
  h.tick(1); await settle(); assert.equal(data.streams.length,prior+2);
  streams().open(); h.frame(); streams().error(); h.tick(250); await settle();
  assert.equal(data.streams.length,prior+3,'successful open resets backoff');
  streams().open(); h.frame();
  const hidden=streams();
  await id('viewList').fire('click');
  assert.equal(hidden.closed,true,'hiding Controller closes EventSource');
  assert.equal(h.frames.size,0,'hidden view cancels rendering');
  hidden.emit('input',{seq:9999,action:'BTN_A',state:'down'}); hidden.error();
  h.tick(10000); await settle();
  assert.equal(data.streams.length,prior+3,'hidden view ignores late events and retries');
  await id('viewController').fire('click'); await settle(); h.frame();
  assert.equal(data.streams.length,prior+4,'showing Controller opens a fresh stream');
  h.run("switchTab('engines')"); assert.equal(streams().closed,true,'changing app tabs closes EventSource');
  h.run("switchTab('editor')"); await settle(); h.frame();
  doc.hidden=true; await doc.fire('visibilitychange'); assert.equal(streams().closed,true,'hidden browser tab closes EventSource');
  doc.hidden=false; await doc.fire('visibilitychange'); await settle();
  await h.window.fire('pagehide'); assert.equal(streams().closed,true,'pagehide closes EventSource');
  await h.window.fire('pageshow'); await settle();
  streams().error(); await id('viewList').fire('click');
  const stopped=data.streams.length; h.tick(10000); await settle();
  assert.equal(data.streams.length,stopped,'hide cancels retry timer');
  let release;
  data.deferSnapshot=new Promise(resolve=>{ release=resolve; });
  await id('viewController').fire('click');
  const request=data.requests.at(-1); assert.equal(request.url,'/api/live/snapshot');
  await id('viewList').fire('click');
  assert.equal(request.signal.aborted,true,'hide aborts in-flight snapshot');
  release({ok:true,json:async()=>({pressed:[],axes:{},seq:50})}); await settle();
  assert.equal(data.streams.length,stopped,'late snapshot cannot create a hidden client');
  delete data.deferSnapshot;
  data.snapshotFails=true; await id('viewController').fire('click'); await settle(); h.frame();
  assert.equal(id('controllerLiveStatus').textContent,'offline');
  data.snapshotFails=false; h.tick(8000); await settle();
  assert.equal(data.streams.length,stopped+1,'snapshot failure retries from a new snapshot');
  await id('viewList').fire('click');
  assert.ok(data.streams.every(s=>s.closed),'all test clients explicitly closed');

  const remembered=harness('controller',false,false,{follow:true}); await settle(); remembered.frame();
  assert.equal(remembered.document.getElementById('controllerFollow').getAttribute('aria-pressed'),'true','browser follow restored');
  const denied=harness(null,true,false,{follow:true}); await settle(); denied.frame();
  assert.equal(denied.document.getElementById('controllerFollow').getAttribute('aria-pressed'),'false','denied storage defaults follow off');
  await denied.document.getElementById('controllerFollow').fire('click'); denied.frame();
  assert.equal(denied.document.getElementById('controllerFollow').getAttribute('aria-pressed'),'true','denied storage still toggles follow');
  const list=harness('list'); await settle();
  assert.equal(list.data.streams.length,0,'remembered List opens no live client');
  assert.equal(list.data.calls.includes('/api/live/snapshot'),false,'remembered List fetches no live snapshot');
  for (const client of [remembered,denied,list]) await client.document.getElementById('viewList').fire('click');
  console.log('UI controller live: PASS (snapshot/SSE lifecycle, highlights/groups, axes/clamps, pad expiry, gyro, exact MIDI rows, follow/drafts, 500-event frame bound)');
}
