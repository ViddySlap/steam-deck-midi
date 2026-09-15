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
    appendChild(child) { this.children.push(child); child.parentNode = this; return child; }
    replaceChildren(...children) { this.children = []; this._text = ''; children.forEach(c => this.appendChild(c)); }
    addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
    async fire(name, event = {}) { for (const fn of this.listeners[name] || []) await fn({target: this, preventDefault() {}, ...event}); }
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
  const data = {version: 0, calls: [], sections: {
    windows: {L2_SOFT: {type:'note', channel:0, note:36, velocity:100}, L_TRIGGER_PRESSURE: {type:'axis_to_cc', cc:11}},
    macbook: {L2_FULL: {type:'cc', channel:1, cc:22}},
  }};
  const context = vm.createContext({document, console, setTimeout() {}, setInterval() {},
    window: {confirm: () => true},
    localStorage: {
      getItem(key) { if (storageFails) throw new Error('Storage denied'); return storage.get(key) ?? null; },
      setItem(key, value) { if (storageFails) throw new Error('Storage denied'); storage.set(key, value); },
    },
    DOMParser: class { parseFromString(text) { const root = parse(text); return {documentElement:root.children[0], querySelector:s => root.querySelector(s)}; } },
    fetch: async url => {
      data.calls.push(url);
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
      if (url === '/api/macros') return response({macros:[]});
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
  console.log('UI controller behavior: PASS (23 arrows, map anchors/shapes, front door, storage, drill-in, List handoff, commit, sections, reload, Escape, unique IDs, asset failure)');
})().catch(error => { console.error(error); process.exitCode = 1; });
