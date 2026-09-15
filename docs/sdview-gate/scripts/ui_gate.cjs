// sdview gate: real headless Chromium against a bridge booted from a git-archive tree.
// Usage: node ui_gate.cjs <mode> <ui_port> <tree_dir> <out_dir>
//   mode full      : a, b at 1440x900 and 1024x768; c, d, e, e2 edits at 1440x900; PNGs
//   mode frontdoor : only the default-sub-view assertion (used by mutation e)
//   mode before    : one PNG of the Mappings tab (BASE OF LAP bridge)
const { chromium } = require('/Users/viddyslap/Documents/project-workspaces/life-os-showday/web-ui-server/node_modules/playwright-core');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execFileSync } = require('child_process');

const [mode, port, TREE, OUT] = process.argv.slice(2);
const BASE = `http://127.0.0.1:${port}`;
const PRESET = path.join(TREE, 'config/presets/EDM Show.json');
const SECTION = 'windows';
fs.mkdirSync(path.join(OUT, 'shots'), { recursive: true });
const results = [];   // {id, pass, detail}
const steps = [];     // disk steps: {id, op, before_sha, after_sha, diff, expected, pass, snapshot}
const log = [];
const note = (...a) => { const s = a.map(x => typeof x === 'string' ? x : JSON.stringify(x)).join(' '); log.push(s); console.log(s); };
const check = (id, pass, detail) => { results.push({ id, pass: Boolean(pass), detail }); note(pass ? 'PASS' : 'FAIL', id, detail === undefined ? '' : detail); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const sha = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const readJson = file => JSON.parse(fs.readFileSync(file, 'utf8'));
const api = async (p, opts) => { const r = await fetch(BASE + p, opts); const t = await r.text(); let j = null; try { j = JSON.parse(t); } catch (_) {} return { status: r.status, json: j, text: t }; };

function jsonDiff(a, b, p = '') {
  const out = [];
  const isObj = x => x && typeof x === 'object';
  if (isObj(a) && isObj(b) && Array.isArray(a) === Array.isArray(b)) {
    const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
    for (const k of [...keys].sort()) {
      const q = p ? `${p}.${k}` : k;
      if (!(k in a)) out.push({ path: q, before: '<absent>', after: b[k] });
      else if (!(k in b)) out.push({ path: q, before: a[k], after: '<absent>' });
      else out.push(...jsonDiff(a[k], b[k], q));
    }
    return out;
  }
  if (JSON.stringify(a) !== JSON.stringify(b)) out.push({ path: p, before: a, after: b });
  return out;
}
const sameDiff = (got, want) => JSON.stringify(got) === JSON.stringify(want);

async function waitSha(prev, timeout = 10000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) { const s = sha(PRESET); if (s !== prev) return s; await sleep(100); }
  return sha(PRESET);
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: BASE });
  const page = await context.newPage();
  const dialogAnswers = [];
  page.on('dialog', async d => {
    const unexpected = dialogAnswers.length === 0;
    const answer = unexpected ? false : dialogAnswers.shift();
    note(`  dialog ${d.type()}: "${d.message()}" -> ${JSON.stringify(answer)}${unexpected ? ' UNEXPECTED (no queued answer)' : ''}`);
    if (unexpected) results.push({ id: 'no-unexpected-dialogs', pass: false, detail: d.message() });
    if (answer === false) await d.dismiss(); else await d.accept();
  });
  page.on('pageerror', e => { note('  PAGE ERROR:', e.message); results.push({ id: 'no-page-errors', pass: false, detail: e.message }); });
  const shot = async name => { const f = path.join(OUT, 'shots', name); await page.screenshot({ path: f, fullPage: true }); note('  PNG', f); };
  const ready = async () => {
    await page.goto(BASE, { waitUntil: 'networkidle' });
    await page.waitForFunction(() => document.getElementById('sectionSelect').options.length > 0);
  };

  if (mode === 'before') {
    await ready();
    await sleep(800);
    await shot('before-mappings.png');
    note('before: editorContent visible', await page.isVisible('#editorContent'), 'controllerView present', await page.$('#controllerView') !== null);
    fs.writeFileSync(path.join(OUT, 'before.log'), log.join('\n') + '\n');
    await browser.close();
    return;
  }

  // ---------- a. front door, arrows, labels, geometry, List switch + reload memory ----------
  const map = (await api('/api/controller-map')).json;
  const controls = map.controls;
  async function frontDoor(vw, vh) {
    await page.setViewportSize({ width: vw, height: vh });
    await page.evaluate(() => { try { localStorage.clear(); } catch (_) {} });
    await ready();
    await page.waitForFunction(() => document.querySelectorAll('.controller-label').length > 0, null, { timeout: 8000 }).catch(() => {});
    const tag = `${vw}x${vh}`;
    const st = await page.evaluate(() => ({
      controllerVisible: !document.getElementById('controllerView').hidden && document.getElementById('controllerView').offsetParent !== null,
      listHidden: document.getElementById('editorContent').hidden,
      pressed: document.getElementById('viewController').getAttribute('aria-pressed'),
      activeTab: document.querySelector('.tab.active')?.dataset.tab,
      section: document.getElementById('sectionSelect').value,
    }));
    check(`a.${tag}.opens-on-controller`, st.controllerVisible && st.listHidden && st.pressed === 'true' && st.activeTab === 'editor', st);
    check(`a.${tag}.section-is-windows`, st.section === SECTION, st.section);
    return tag;
  }
  async function geometry(tag) {
    const g = await page.evaluate(() => {
      const vw = window.innerWidth, vh = window.innerHeight;
      const arrows = [...document.querySelectorAll('.controller-arrow')].map(a => { const r = a.getBoundingClientRect(); return { id: a.dataset.controlArrow, w: r.width, h: r.height }; });
      const labels = [...document.querySelectorAll('.controller-label')].map(l => { const r = l.getBoundingClientRect(); return { id: l.dataset.control, text: l.textContent, x: r.left, y: r.top, r: r.right, b: r.bottom }; });
      const docW = document.documentElement.scrollWidth;
      return { vw, vh, arrows, labels, docW };
    });
    check(`a.${tag}.23-arrows`, g.arrows.length === 23 && new Set(g.arrows.map(a => a.id)).size === 23 && g.arrows.every(a => a.w + a.h > 0), `${g.arrows.length} arrows, ${new Set(g.arrows.map(a => a.id)).size} unique, zero-size: ${g.arrows.filter(a => a.w + a.h === 0).map(a => a.id)}`);
    check(`a.${tag}.23-labels`, g.labels.length === 23 && new Set(g.labels.map(l => l.id)).size === 23, `${g.labels.length} labels`);
    const mapIds = controls.map(c => c.id).sort();
    check(`a.${tag}.labels-equal-map`, JSON.stringify(g.labels.map(l => l.id).sort()) === JSON.stringify(mapIds), 'label ids vs /api/controller-map ids');
    const outside = g.labels.filter(l => l.x < 0 || l.y < 0 || l.r > g.vw || l.b > g.vh);
    check(`a.${tag}.labels-inside-viewport`, outside.length === 0, outside.length ? outside : `all 23 inside ${g.vw}x${g.vh}`);
    const hits = [];
    for (let i = 0; i < g.labels.length; i++) for (let j = i + 1; j < g.labels.length; j++) {
      const A = g.labels[i], B = g.labels[j];
      if (A.x < B.r && B.x < A.r && A.y < B.b && B.y < A.b) hits.push(`${A.id}x${B.id}`);
    }
    check(`a.${tag}.no-label-intersections`, hits.length === 0, hits.length ? hits : '253 pairs, 0 intersect');
    check(`a.${tag}.no-horizontal-page-scroll`, g.docW <= g.vw, `scrollWidth ${g.docW} vs ${g.vw}`);
    fs.writeFileSync(path.join(OUT, `geometry-${tag}.json`), JSON.stringify(g, null, 2));
  }
  async function listSwitch(tag) {
    await page.click('#viewList');
    const s1 = await page.evaluate(() => ({ list: !document.getElementById('editorContent').hidden, sidebar: !document.getElementById('mappingSidebar').hidden, ctrl: document.getElementById('controllerView').hidden, chips: document.querySelectorAll('.chip[data-action]').length }));
    check(`a.${tag}.list-switch-shows-list-editor`, s1.list && s1.sidebar && s1.ctrl && s1.chips > 0, s1);
    await page.reload({ waitUntil: 'networkidle' });
    await sleep(500);
    const s2 = await page.evaluate(() => ({ list: !document.getElementById('editorContent').hidden, pressed: document.getElementById('viewList').getAttribute('aria-pressed'), stored: localStorage.getItem('steamdeck.mappingView') }));
    check(`a.${tag}.reload-remembers-list`, s2.list && s2.pressed === 'true', s2);
    await page.click('#viewController');
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForFunction(() => document.querySelectorAll('.controller-label').length === 23, null, { timeout: 8000 }).catch(() => {});
    const s3 = await page.evaluate(() => ({ ctrl: !document.getElementById('controllerView').hidden, stored: localStorage.getItem('steamdeck.mappingView') }));
    check(`a.${tag}.reload-remembers-controller`, s3.ctrl, s3);
  }

  // ---------- b. every control drill-in equals GET /api/controller-map/<id>?section=windows ----------
  async function openControl(id) {
    await page.click(`.controller-label[data-control="${id}"]`);
    await page.waitForFunction(i => !document.getElementById('controllerCard').hidden && document.querySelector(`.controller-label[data-control="${i}"]`).getAttribute('aria-expanded') === 'true', id, { timeout: 4000 });
  }
  async function drillAll(tag) {
    const rows = [];
    for (const c of controls) {
      await openControl(c.id);
      const shown = await page.evaluate(() => ({
        title: document.getElementById('controllerTitle').textContent,
        groups: [...document.querySelectorAll('#controllerRows .controller-group')].map(g => ({ group: g.dataset.group, heading: g.querySelector('h3').textContent, actions: [...g.querySelectorAll('.controller-row')].map(r => ({ id: r.dataset.action, badge: r.querySelector('.chip-badge').textContent })) })),
      }));
      const got = (await api(`/api/controller-map/${c.id}?section=${SECTION}`)).json;
      const want = {};
      for (const [k, v] of Object.entries(got.groups)) want[k] = v.map(x => x.action_id);
      const have = {};
      for (const g of shown.groups) have[g.group] = g.actions.map(a => a.id);
      const order = ['tap', 'long_press', 'layer_2', 'analog'];
      const wantOrder = order.filter(k => k in want);
      const eq = JSON.stringify(Object.keys(have)) === JSON.stringify(wantOrder) && wantOrder.every(k => JSON.stringify(have[k]) === JSON.stringify(want[k])) && shown.title === got.label;
      const typeBadge = { note: 'NOTE', cc: 'CC', macro_cc: 'MACRO', relative_cc: 'REL', staged_note_macro: 'STAGED', axis_to_cc: 'AXIS', axis_split_cc: 'AXIS+/-' };
      const badgeMismatch = [];
      for (const g of shown.groups) for (const a of g.actions) {
        const m = got.groups[g.group].find(x => x.action_id === a.id)?.mapping;
        const expect = m ? typeBadge[m.type] : 'unmapped';
        if (expect !== a.badge) badgeMismatch.push(`${a.id}:${a.badge}!=${expect}`);
      }
      rows.push({ control: c.id, label: got.label, groups: have, api: want, equal: eq, badgeMismatch });
      await page.keyboard.press('Escape');
      const closed = await page.evaluate(() => document.getElementById('controllerCard').hidden);
      if (!eq || badgeMismatch.length || !closed) note('  mismatch', c.id, { have, want, badgeMismatch, closed });
      rows[rows.length - 1].escapeClosed = closed;
    }
    fs.writeFileSync(path.join(OUT, `drill-${tag}.json`), JSON.stringify(rows, null, 2));
    check(`b.${tag}.all-23-groups-equal-api`, rows.length === 23 && rows.every(r => r.equal), `${rows.filter(r => r.equal).length}/23 equal`);
    check(`b.${tag}.all-badges-equal-api-mapping-type`, rows.every(r => r.badgeMismatch.length === 0), rows.flatMap(r => r.badgeMismatch));
    check(`b.${tag}.escape-closes-all-23`, rows.every(r => r.escapeClosed), `${rows.filter(r => r.escapeClosed).length}/23 closed`);
  }

  if (mode === 'geometry') {
    // Occlusion and overlap, card closed and card open, at both viewports, scrolled to top.
    const rows = [];
    for (const [vw, vh] of [[1440, 900], [1024, 768]]) {
      await page.setViewportSize({ width: vw, height: vh });
      await ready();
      await page.waitForFunction(() => document.querySelectorAll('.controller-label').length === 23, null, { timeout: 8000 });
      for (const state of ['card-closed', 'card-open-btn_a']) {
        if (state === 'card-open-btn_a') await openControl('btn_a');
        await page.evaluate(() => { document.getElementById('tab-editor').scrollTop = 0; window.scrollTo(0, 0); });
        await sleep(300);
        const g = await page.evaluate(() => {
          const vw = window.innerWidth, vh = window.innerHeight;
          const labels = [...document.querySelectorAll('.controller-label')].map(l => {
            const r = l.getBoundingClientRect();
            const pts = [[(r.left + r.right) / 2, (r.top + r.bottom) / 2], [r.left + 3, r.top + 3], [r.right - 3, r.top + 3], [r.left + 3, r.bottom - 3], [r.right - 3, r.bottom - 3]];
            const covered = pts.filter(([x, y]) => { const e = document.elementFromPoint(x, y); return !e || !l.contains(e); })
              .map(([x, y]) => { const e = document.elementFromPoint(x, y); return e ? (e.id || e.className?.baseVal || e.className || e.tagName) : 'offscreen'; });
            return { id: l.dataset.control, x: r.left, y: r.top, r: r.right, b: r.bottom, covered };
          });
          const scrollers = [...document.querySelectorAll('*')].filter(e => { const cs = getComputedStyle(e); return /(auto|scroll)/.test(cs.overflowY) && e.scrollHeight > e.clientHeight + 1; }).map(e => ({ el: e.id || e.className, scrollHeight: e.scrollHeight, clientHeight: e.clientHeight }));
          return { vw, vh, labels, scrollers, docScroll: document.documentElement.scrollHeight };
        });
        const inter = [];
        for (let i = 0; i < g.labels.length; i++) for (let j = i + 1; j < g.labels.length; j++) {
          const A = g.labels[i], B = g.labels[j];
          if (A.x < B.r && B.x < A.r && A.y < B.b && B.y < A.b) inter.push(`${A.id}x${B.id}`);
        }
        const outside = g.labels.filter(l => l.x < 0 || l.y < 0 || l.r > g.vw || l.b > g.vh).map(l => l.id);
        const occluded = g.labels.filter(l => l.covered.length).map(l => ({ id: l.id, by: [...new Set(l.covered)] }));
        const row = { viewport: `${vw}x${vh}`, state, outside, intersections: inter, occluded, scrollers: g.scrollers };
        rows.push(row);
        note('GEOMETRY', row);
        await page.screenshot({ path: path.join(OUT, 'shots', `geometry-${vw}x${vh}-${state}.png`) });
        if (state === 'card-open-btn_a') await page.keyboard.press('Escape');
      }
    }
    fs.writeFileSync(path.join(OUT, 'geometry.json'), JSON.stringify(rows, null, 2));
    await browser.close();
    return;
  }

  if (mode === 'cards') {
    // Whole drill-in card elements. The editor pane scrolls inside a 1440x900 page, which clips
    // long cards, so these supplementary card PNGs use a 1440x1800 viewport.
    await page.setViewportSize({ width: 1440, height: 1800 });
    await ready();
    await page.waitForFunction(() => document.querySelectorAll('.controller-label').length === 23, null, { timeout: 8000 });
    for (const [id, name] of [['btn_a', 'a'], ['l2', 'l2'], ['left_stick', 'left-stick'], ['left_pad', 'left-trackpad'], ['gyro', 'gyro']]) {
      await openControl(id);
      await sleep(200);
      const f = path.join(OUT, 'shots', `after-drill-${name}-card.png`);
      await page.locator('#controllerCard').screenshot({ path: f });
      note('  PNG', f);
    }
    await browser.close();
    return;
  }

  if (mode === 'frontdoor') {
    const tag = await frontDoor(1440, 900);
    fs.writeFileSync(path.join(OUT, 'results.json'), JSON.stringify({ results }, null, 2));
    await browser.close();
    process.exit(results.every(r => r.pass) ? 0 : 1);
  }

  let tag = await frontDoor(1440, 900);
  await geometry(tag);
  await shot('after-controller-front-door.png');
  await listSwitch(tag);
  await drillAll(tag);

  // keyboard: Tab focus, Enter opens, Escape returns focus to label (V2 owed)
  await page.focus('.controller-label[data-control="btn_b"]');
  await page.keyboard.press('Enter');
  const kb1 = await page.evaluate(() => ({ open: !document.getElementById('controllerCard').hidden, title: document.getElementById('controllerTitle').textContent, focus: document.activeElement.id }));
  await page.keyboard.press('Escape');
  const kb2 = await page.evaluate(() => ({ closed: document.getElementById('controllerCard').hidden, focus: document.activeElement.dataset.control, focusVisible: getComputedStyle(document.activeElement).outlineStyle }));
  check('b.keyboard-enter-opens-escape-returns-focus', kb1.open && kb1.title === 'B' && kb1.focus === 'controllerTitle' && kb2.closed && kb2.focus === 'btn_b', { kb1, kb2 });

  // PNGs of drill-ins
  for (const [id, name] of [['btn_a', 'a'], ['l2', 'l2'], ['left_stick', 'left-stick'], ['left_pad', 'left-trackpad'], ['gyro', 'gyro']]) {
    await openControl(id);
    await sleep(150);
    await shot(`after-drill-${name}.png`);
  }

  // ---------- c/d. edits through the UI, Save, read the disk ----------
  const rowSel = a => `#controllerRows .controller-row[data-action="${a}"]`;
  async function openEditor(control, action) {
    await openControl(control);
    const hidden = await page.evaluate(a => document.getElementById(`controller_${a}_editor`)?.hidden ?? true, action);
    if (hidden) await page.click(`${rowSel(action)} .controller-edit`);
    await page.waitForSelector(`#controller_${action}_editor:not([hidden])`, { timeout: 3000 });
  }
  const applyRow = async action => page.click(`#controller_${action}_editor .controller-apply`);
  const badgeShown = () => page.evaluate(() => document.getElementById('unsavedBadge').classList.contains('show'));
  async function saveAndDiff(id, op, expected) {
    const before = readJson(PRESET), beforeSha = sha(PRESET);
    await page.click('#btnSave');
    const afterSha = await waitSha(beforeSha);
    await sleep(2800); // bridge reload + page poll/loadAll
    const after = readJson(PRESET);
    const diff = jsonDiff(before, after);
    const pass = afterSha !== beforeSha && sameDiff(diff, expected);
    steps.push({ id, op, before_sha: beforeSha, after_sha: afterSha, diff, expected, pass, snapshot: after });
    check(`${id}.disk-diff`, pass, { op, diff });
    check(`${id}.page-clean-after-save`, !(await badgeShown()), 'UNSAVED badge cleared');
  }
  const W = k => `sections.windows.mappings.${k}`;

  // c1 note number
  await openEditor('btn_a', 'BTN_A');
  await page.fill('#controller_BTN_A_f_note', '50');
  await shot('after-row-open-in-edit.png');
  await applyRow('BTN_A');
  await saveAndDiff('c1', 'BTN_A note 36 -> 50 (row form)', [{ path: W('BTN_A.note'), before: 36, after: 50 }]);
  // c2 axis_split_cc deadzone
  await openEditor('right_stick', 'R_STICK_X_AXIS');
  await page.fill('#controller_R_STICK_X_AXIS_f_dz', '4000');
  await applyRow('R_STICK_X_AXIS');
  await saveAndDiff('c2', 'R_STICK_X_AXIS axis_split_cc deadzone 3500 -> 4000', [{ path: W('R_STICK_X_AXIS.deadzone'), before: 3500, after: 4000 }]);
  // c3 clear
  const yl2 = readJson(PRESET).sections.windows.mappings.BTN_Y_LAYER_2;
  await openEditor('btn_y', 'BTN_Y_LAYER_2');
  await page.click('#controller_BTN_Y_LAYER_2_editor .controller-clear');
  await saveAndDiff('c3', 'Clear BTN_Y_LAYER_2', [{ path: W('BTN_Y_LAYER_2'), before: yl2, after: '<absent>' }]);
  // c4 macro from the library onto a compatible action
  await openControl('dpad_down');
  const macroOpts = await page.evaluate(s => [...document.querySelector(`${s} select.controller-macro`).options].map(o => ({ v: o.value, d: o.disabled, t: o.textContent })), rowSel('DPAD_DOWN_LONG_PRESS'));
  check('c4.incompatible-macros-disabled', macroOpts.filter(o => o.v).every(o => o.d === !['click-toggle', 'animated-fade'].includes(o.v)), macroOpts);
  await page.selectOption(`${rowSel('DPAD_DOWN_LONG_PRESS')} select.controller-macro`, 'click-toggle');
  await saveAndDiff('c4', 'Apply macro click-toggle to DPAD_DOWN_LONG_PRESS (macro_cc long_press)', [{ path: W('DPAD_DOWN_LONG_PRESS.gesture'), before: 'long_press', after: 'click' }]);
  // c5 Advanced tab
  await openControl('l5');
  await page.click('#controllerAdvancedTab');
  await page.fill('#controller_l5_json', JSON.stringify({ L5: { type: 'note', channel: 0, note: 80, velocity: 100 } }, null, 2));
  await shot('after-advanced-tab.png');
  await page.click('.controller-json-apply');
  await saveAndDiff('c5', 'Advanced JSON: L5 note 75 -> 80, velocity 127 -> 100', [{ path: W('L5.note'), before: 75, after: 80 }, { path: W('L5.velocity'), before: 127, after: 100 }]);
  await page.click('#controllerMappingsTab');
  // c6 conflict: START cc 78 -> 79 collides with SELECT ch2 cc79
  await openEditor('start', 'START');
  await page.fill('#controller_START_f_cc', '79');
  await applyRow('START');
  const shaC6 = sha(PRESET);
  await page.click('#btnSave');
  await page.waitForSelector('#conflictOverlay.open', { timeout: 5000 });
  const marked = await page.evaluate(() => ({ rows: [...document.querySelectorAll('#controllerRows .controller-row.controller-conflict')].map(r => r.dataset.action), msg: [...document.querySelectorAll('.controller-conflict-message')].map(m => m.textContent), details: document.getElementById('conflictDetails').textContent }));
  check('c6.conflict-modal-and-marked-rows', marked.rows.includes('START') && /SELECT/.test(marked.details) && /START/.test(marked.details), marked);
  await shot('after-conflict-modal-marked-rows.png');
  await page.click('#btnConflictCancel');
  await sleep(3000);
  const afterCancel = sha(PRESET);
  const unmarked = await page.evaluate(() => document.querySelectorAll('.controller-row.controller-conflict').length);
  check('c6.cancel-writes-nothing', afterCancel === shaC6, `sha before ${shaC6} after cancel+3s ${afterCancel}; marked rows after cancel ${unmarked}`);
  check('c6.cancel-clears-marks', unmarked === 0, unmarked);
  steps.push({ id: 'c6-cancel', op: 'conflict Cancel', before_sha: shaC6, after_sha: afterCancel, diff: [], expected: [], pass: afterCancel === shaC6, snapshot: readJson(PRESET) });
  {
    const before = readJson(PRESET), beforeSha = sha(PRESET);
    await page.click('#btnSave');
    await page.waitForSelector('#conflictOverlay.open', { timeout: 5000 });
    await page.click('#btnConflictForce');
    const afterSha = await waitSha(beforeSha);
    await sleep(2800);
    const after = readJson(PRESET);
    const diff = jsonDiff(before, after);
    const expected = [{ path: W('START.cc'), before: 78, after: 79 }];
    steps.push({ id: 'c6', op: 'START cc 78 -> 79, Save anyway', before_sha: beforeSha, after_sha: afterSha, diff, expected, pass: sameDiff(diff, expected), snapshot: after });
    check('c6.save-anyway-writes', sameDiff(diff, expected), diff);
  }
  // d8 Advanced null clears SELECT (also resolves the forced conflict)
  const selSpec = readJson(PRESET).sections.windows.mappings.SELECT;
  await openControl('select');
  await page.click('#controllerAdvancedTab');
  await page.fill('#controller_select_json', '{"SELECT": null}');
  await page.click('.controller-json-apply');
  await page.click('#controllerMappingsTab');
  await saveAndDiff('d8', 'Advanced JSON null clears SELECT', [{ path: W('SELECT'), before: selSpec, after: '<absent>' }]);
  // Advanced refuses a foreign Action ID atomically (no draft)
  await openControl('l4');
  await page.click('#controllerAdvancedTab');
  await page.fill('#controller_l4_json', '{"L4": {"type":"note","channel":0,"note":1,"velocity":1}, "BTN_A": null}');
  await page.click('.controller-json-apply');
  const refused = await page.evaluate(() => ({ err: document.querySelector('#controllerAdvanced .json-err')?.textContent, save: document.getElementById('btnSave').disabled }));
  check('d.advanced-foreign-id-refused-atomically', /does not belong/.test(refused.err || '') && refused.save, refused);
  await page.click('#controllerMappingsTab');
  // discard that refused Advanced draft with a plain browser reload (no confirm dialog involved)
  dialogAnswers.length = 0;
  await page.reload({ waitUntil: 'networkidle' }); await sleep(1200);
  check('d.reload-discards-refused-draft', !(await page.evaluate(() => ControllerView.hasDrafts())) && !(await badgeShown()), 'no drafts, no UNSAVED badge');

  // d1 set type on an unmapped action
  await openEditor('gyro', 'GYRO_FORWARD');
  await page.selectOption('#controller_GYRO_FORWARD_type', 'note');
  await applyRow('GYRO_FORWARD');
  await saveAndDiff('d1', 'Set type: GYRO_FORWARD unmapped -> note (DEFAULTS)', [{ path: W('GYRO_FORWARD'), before: '<absent>', after: { type: 'note', channel: 0, note: 36, velocity: 127 } }]);
  // d2 cc fields
  await openEditor('l4', 'L4');
  await page.fill('#controller_L4_f_on', '100');
  await applyRow('L4');
  await saveAndDiff('d2', 'cc: L4 on_value 127 -> 100', [{ path: W('L4.on_value'), before: 127, after: 100 }]);
  // d3 macro_cc fields
  await openEditor('dpad_right', 'DPAD_RIGHT');
  await page.fill('#controller_DPAD_RIGHT_f_fade', '1.5');
  await applyRow('DPAD_RIGHT');
  await saveAndDiff('d3', 'macro_cc: DPAD_RIGHT fade override 1.5', [{ path: W('DPAD_RIGHT.fade_duration_seconds'), before: '<absent>', after: 1.5 }]);
  // d4 relative_cc fields
  await openEditor('right_pad', 'R_PAD_DOWN');
  await page.fill('#controller_R_PAD_DOWN_f_ri', '60');
  await applyRow('R_PAD_DOWN');
  await saveAndDiff('d4', 'relative_cc: R_PAD_DOWN repeat_interval_ms 40 -> 60', [{ path: W('R_PAD_DOWN.repeat_interval_ms'), before: 40, after: 60 }]);
  // d5 staged_note_macro fields
  await openEditor('left_pad', 'L_PAD_LEFT_LONG_PRESS');
  await page.fill('#controller_L_PAD_LEFT_LONG_PRESS_f_delay', '120');
  await applyRow('L_PAD_LEFT_LONG_PRESS');
  await saveAndDiff('d5', 'staged_note_macro: L_PAD_LEFT_LONG_PRESS macro_delay_ms 120', [{ path: W('L_PAD_LEFT_LONG_PRESS.macro_delay_ms'), before: '<absent>', after: 120 }]);
  // d6 axis_to_cc fields
  await openEditor('l2', 'L_TRIGGER_PRESSURE');
  await page.fill('#controller_L_TRIGGER_PRESSURE_f_dz', '6000');
  await page.selectOption('#controller_L_TRIGGER_PRESSURE_f_curve', 'quadratic');
  await applyRow('L_TRIGGER_PRESSURE');
  await saveAndDiff('d6', 'axis_to_cc: L_TRIGGER_PRESSURE deadzone 5000 -> 6000, curve linear -> quadratic', [{ path: W('L_TRIGGER_PRESSURE.curve'), before: 'linear', after: 'quadratic' }, { path: W('L_TRIGGER_PRESSURE.deadzone'), before: 5000, after: 6000 }]);
  // d9 Copy JSON
  await openControl('btn_a');
  await page.click('#controllerAdvancedTab');
  const text = await page.inputValue('#controller_btn_a_json');
  await page.click('#controllerAdvanced .controller-json-copy');
  await sleep(300);
  const clip = await page.evaluate(() => navigator.clipboard.readText());
  check('d9.copy-json-to-clipboard', clip === text.trim() && JSON.parse(clip).BTN_A.note === 50, clip.slice(0, 120));
  await page.click('#controllerMappingsTab');
  // d10 section switch confirm: dismiss keeps draft, accept switches
  await openEditor('btn_b', 'BTN_B');
  await page.fill('#controller_BTN_B_f_note', '57');
  dialogAnswers.push(false);
  await page.selectOption('#sectionSelect', 'macbook');
  await sleep(600);
  const d10a = await page.evaluate(() => ({ section: document.getElementById('sectionSelect').value, v: document.getElementById('controller_BTN_B_f_note')?.value }));
  check('d10.section-switch-dismiss-keeps-draft', d10a.section === 'windows' && d10a.v === '57', d10a);
  dialogAnswers.push(true);
  await page.selectOption('#sectionSelect', 'macbook');
  await page.waitForFunction(() => document.getElementById('sectionSelect').value === 'macbook', null, { timeout: 5000 });
  await sleep(600);
  await openControl('btn_b');
  const d10b = await page.evaluate(() => document.querySelector('#controllerRows .controller-row[data-action="BTN_B"] .controller-description').textContent);
  check('d10.section-switch-accept-shows-macbook', /note 38/.test(d10b), d10b);
  await page.selectOption('#sectionSelect', 'windows');
  await page.waitForFunction(() => document.getElementById('sectionSelect').value === 'windows', null, { timeout: 5000 });
  await sleep(600);
  // d11 one-click List from the drill-in
  await openControl('btn_a');
  await page.click(`${rowSel('BTN_A')} .controller-open-list`);
  await sleep(300);
  const d11 = await page.evaluate(() => ({ list: !document.getElementById('editorContent').hidden, badge: document.querySelector('#editorContent .action-badge')?.textContent, note: document.getElementById('f_note')?.value }));
  check('d11.open-in-list-one-click', d11.list && d11.badge === 'BTN_A' && d11.note === '50', d11);
  await shot('after-list-view.png');
  await page.click('#viewController');
  await sleep(300);

  // ---------- e. draft survives an outside disk change ----------
  await openEditor('btn_b', 'BTN_B');
  await page.fill('#controller_BTN_B_f_note', '55');
  {
    const before = readJson(PRESET), beforeSha = sha(PRESET);
    const d = readJson(PRESET); d.sections.macbook.mappings.BTN_A.note = 37;
    fs.writeFileSync(PRESET, JSON.stringify(d, null, 2) + '\n');
    await page.waitForFunction(() => !document.getElementById('presetChangeNotice').hidden, null, { timeout: 10000 }).catch(() => {});
    const e = await page.evaluate(() => ({ notice: !document.getElementById('presetChangeNotice').hidden, text: document.getElementById('presetChangeNotice').textContent.replace(/\s+/g, ' ').trim(), v: document.getElementById('controller_BTN_B_f_note')?.value }));
    const after = readJson(PRESET);
    const diff = jsonDiff(before, after);
    check('e.notice-appears-and-typed-value-survives', e.notice && e.v === '55', e);
    steps.push({ id: 'e', op: 'outside write: macbook BTN_A note 36 -> 37', before_sha: beforeSha, after_sha: sha(PRESET), diff, expected: [{ path: 'sections.macbook.mappings.BTN_A.note', before: 36, after: 37 }], pass: sameDiff(diff, [{ path: 'sections.macbook.mappings.BTN_A.note', before: 36, after: 37 }]), snapshot: after });
    await sleep(2500);
    const e2 = await page.evaluate(() => ({ notice: !document.getElementById('presetChangeNotice').hidden, v: document.getElementById('controller_BTN_B_f_note')?.value }));
    check('e.typed-value-survives-further-polls', e2.notice && e2.v === '55', e2);
    await shot('after-draft-notice.png');
  }
  dialogAnswers.push(true);
  await page.click('#btnReloadPreset');
  await page.waitForFunction(() => document.getElementById('presetChangeNotice').hidden, null, { timeout: 8000 }).catch(() => {});
  await sleep(800);

  // ---------- e2. agent PUT on the same action while a draft is typed ----------
  check('e.reload-accepted-hides-notice', await page.evaluate(() => document.getElementById('presetChangeNotice').hidden), 'after Reload accept');
  await sleep(3000); // absorb the receiver's own reload version bump while clean
  await openEditor('btn_x', 'BTN_X');
  await page.fill('#controller_BTN_X_f_note', '60');
  {
    const before = readJson(PRESET), beforeSha = sha(PRESET);
    const noticeBefore = await page.evaluate(() => !document.getElementById('presetChangeNotice').hidden);
    const out = execFileSync('curl', ['-sS', '-o', path.join(OUT, 'e2-put-body.json'), '-w', '%{http_code}', '-X', 'PUT', '-H', 'content-type: application/json', '--data', '{"type":"note","channel":0,"note":44,"velocity":127}', `${BASE}/api/mappings/BTN_X?section=windows`]).toString();
    await page.waitForFunction(() => !document.getElementById('presetChangeNotice').hidden, null, { timeout: 10000 }).catch(() => {});
    await sleep(2500);
    const s = await page.evaluate(() => ({ notice: !document.getElementById('presetChangeNotice').hidden, v: document.getElementById('controller_BTN_X_f_note')?.value, desc: document.querySelector('#controllerRows .controller-row[data-action="BTN_X"] .controller-description')?.textContent }));
    const after = readJson(PRESET);
    const diff = jsonDiff(before, after);
    const expected = [{ path: W('BTN_X.note'), before: 40, after: 44 }];
    check('e2.put-200', out === '200', out);
    check('e2.notice-and-draft-kept', !noticeBefore && s.notice && s.v === '60', { noticeBefore, ...s });
    steps.push({ id: 'e2', op: 'curl PUT BTN_X note 44 under a typed draft of 60', before_sha: beforeSha, after_sha: sha(PRESET), diff, expected, pass: sameDiff(diff, expected), snapshot: after });
    check('e2.file-after', sameDiff(diff, expected), { diff, sha: sha(PRESET) });
  }
  dialogAnswers.push(true);
  await page.click('#btnReloadPreset');
  await page.waitForFunction(() => document.getElementById('presetChangeNotice').hidden, null, { timeout: 8000 }).catch(() => {});
  await sleep(800);
  await openControl('btn_x');
  const x44 = await page.evaluate(() => document.querySelector('#controllerRows .controller-row[data-action="BTN_X"] .controller-description').textContent);
  check('e2.reload-shows-agent-value', /note 44/.test(x44), x44);

  // ---------- d12 factory reset (last write) ----------
  {
    const before = readJson(PRESET), beforeSha = sha(PRESET);
    await page.click('#btnReset');
    await page.click('#btnResetConfirm');
    const afterSha = await waitSha(beforeSha);
    await sleep(2800);
    const after = readJson(PRESET);
    const diff = jsonDiff(before, after);
    const factory = readJson(path.join(TREE, 'config/windows_midi_map.json'));
    const macbookSame = JSON.stringify(before.sections.macbook) === JSON.stringify(after.sections.macbook);
    const mappingsFactory = JSON.stringify(after.sections.windows.mappings) === JSON.stringify(factory.mappings);
    const onlyWindows = diff.every(d => d.path.startsWith('sections.windows.'));
    steps.push({ id: 'd12', op: 'Factory reset windows section', before_sha: beforeSha, after_sha: afterSha, diff, expected: 'windows section replaced by factory; macbook unchanged', pass: macbookSame && mappingsFactory && onlyWindows && afterSha !== beforeSha, snapshot: after });
    check('d12.reset-writes-only-windows-to-factory', macbookSame && mappingsFactory && onlyWindows, { macbookSame, mappingsFactory, onlyWindows, paths: diff.length });
  }

  // ---------- a + b at 1024x768 ----------
  tag = await frontDoor(1024, 768);
  await geometry(tag);
  await shot('after-controller-front-door-1024.png');
  await listSwitch(tag);
  await drillAll(tag);
  const f4 = await page.evaluate(() => { const h = document.querySelector('header'); return h ? Math.round(h.getBoundingClientRect().height) : null; });
  note('F4 note: header height at 1024x768', f4);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.reload({ waitUntil: 'networkidle' });
  const f4b = await page.evaluate(() => Math.round(document.querySelector('header').getBoundingClientRect().height));
  note('F4 note: header height at 1440x900', f4b);

  check('dialog-queue-empty-at-end', dialogAnswers.length === 0, dialogAnswers);
  check('no-page-errors-final', !results.some(r => r.id === 'no-page-errors'), '');
  fs.writeFileSync(path.join(OUT, 'results.json'), JSON.stringify({ results, header_height: { '1024x768': f4, '1440x900': f4b } }, null, 2));
  fs.writeFileSync(path.join(OUT, 'steps.json'), JSON.stringify(steps, null, 2));
  fs.writeFileSync(path.join(OUT, 'ui-gate.log'), log.join('\n') + '\n');
  await browser.close();
  const failed = results.filter(r => !r.pass);
  note(`SUMMARY ${results.length - failed.length}/${results.length} PASS`);
  process.exit(failed.length ? 1 : 0);
})().catch(e => { console.error('UI GATE ERROR', e); fs.writeFileSync(path.join(OUT, 'ui-gate.log'), log.join('\n') + '\nERROR ' + e.stack + '\n'); fs.writeFileSync(path.join(OUT, 'results-partial.json'), JSON.stringify({ results, steps }, null, 2)); process.exit(2); });
