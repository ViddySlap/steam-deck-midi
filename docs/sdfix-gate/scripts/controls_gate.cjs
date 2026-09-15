// sdfix gate step 4: every control still works at 1440x900, one drill-in edit lands exactly on disk,
// and conflict marks survive the modal closing and clear after a successful Save.
// Usage: node controls_gate.cjs PORT TREE OUT_DIR
const { chromium } = require('/Users/viddyslap/Documents/project-workspaces/life-os-showday/web-ui-server/node_modules/playwright-core');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const CHROMIUM = '/Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell';
const [PORT, TREE, OUT] = process.argv.slice(2);
const BASE = `http://127.0.0.1:${PORT}`;
const PRESET = path.join(TREE, 'config/presets/EDM Show.json');
fs.mkdirSync(OUT, { recursive: true });
const results = [];
const check = (id, pass, detail) => { results.push({ id, pass: Boolean(pass), detail }); console.log(pass ? 'PASS' : 'FAIL', id, JSON.stringify(detail)); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const sha = f => crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');
const readJson = f => JSON.parse(fs.readFileSync(f, 'utf8'));
function diff(a, b, p = '') {
  const obj = x => x && typeof x === 'object';
  if (obj(a) && obj(b) && Array.isArray(a) === Array.isArray(b)) {
    return [...new Set([...Object.keys(a), ...Object.keys(b)])].sort().flatMap(k => {
      const q = p ? `${p}.${k}` : k;
      if (!(k in a)) return [{ path: q, before: '<absent>', after: b[k] }];
      if (!(k in b)) return [{ path: q, before: a[k], after: '<absent>' }];
      return diff(a[k], b[k], q);
    });
  }
  return JSON.stringify(a) === JSON.stringify(b) ? [] : [{ path: p, before: a, after: b }];
}
async function waitChange(prev, ms = 10000) { const t = Date.now(); while (Date.now() - t < ms) { if (sha(PRESET) !== prev) return true; await sleep(100); } return false; }
const GROUPS = ['tap', 'long_press', 'layer_2', 'analog'];

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: CHROMIUM });
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  page.on('dialog', d => { console.log('UNEXPECTED dialog', d.message()); d.dismiss(); });
  page.on('pageerror', e => check('page-error', false, e.message));
  await page.goto(BASE, { waitUntil: 'load' });
  await page.waitForFunction(() => document.querySelectorAll('#controllerPicture .controller-label').length === 23, null, { timeout: 15000 });
  const map = await (await fetch(`${BASE}/api/controller-map`)).json();
  const labelIds = await page.evaluate(() => [...document.querySelectorAll('#controllerPicture .controller-label')].map(l => l.dataset.control));
  check('labels.23-and-match-map', labelIds.length === 23 && JSON.stringify([...labelIds].sort()) === JSON.stringify(map.controls.map(c => c.id).sort()), labelIds);

  // ---- 4a: each label opens its own drill-in; rows equal the per-control API ----
  const drill = [];
  for (const c of map.controls) {
    await page.click(`#controllerPicture .controller-label[data-control="${c.id}"]`);
    await page.waitForFunction(t => !document.getElementById('controllerCard').hidden && document.getElementById('controllerTitle').textContent === t, c.label, { timeout: 5000 });
    const ui = await page.evaluate(() => ({ title: document.getElementById('controllerTitle').textContent,
      expanded: [...document.querySelectorAll('.controller-label[aria-expanded="true"]')].map(l => l.dataset.control),
      groups: Object.fromEntries([...document.querySelectorAll('#controllerRows .controller-group')].map(g => [g.dataset.group, [...g.querySelectorAll('.controller-row')].map(r => r.dataset.action)])) }));
    const api = await (await fetch(`${BASE}/api/controller-map/${c.id}?section=windows`)).json();
    const apiGroups = Object.fromEntries(GROUPS.filter(g => api.groups[g]).map(g => [g, api.groups[g].map(e => e.action_id)]));
    const uiFlat = GROUPS.flatMap(g => ui.groups[g] || []), apiFlat = GROUPS.flatMap(g => apiGroups[g] || []);
    const pass = ui.title === c.label && api.id === c.id && JSON.stringify(ui.expanded) === JSON.stringify([c.id]) && JSON.stringify(ui.groups) === JSON.stringify(apiGroups) && uiFlat.length > 0;
    drill.push({ control: c.id, title: ui.title, ui: uiFlat, api: apiFlat, pass });
    check(`drill.${c.id}`, pass, { title: ui.title, n: uiFlat.length, ids: uiFlat });
  }
  fs.writeFileSync(path.join(OUT, 'drill-1440x900.json'), JSON.stringify(drill, null, 1));
  check('drill.all-23', drill.length === 23 && drill.every(d => d.pass), `${drill.filter(d => d.pass).length}/23`);

  const openControl = async id => { await page.click(`#controllerPicture .controller-label[data-control="${id}"]`); await page.waitForFunction(i => document.querySelector(`.controller-label[data-control="${i}"]`).getAttribute('aria-expanded') === 'true', id); };
  const openEditor = async (control, action) => {
    await openControl(control);
    if (await page.evaluate(a => document.getElementById(`controller_${a}_editor`).hidden, action)) await page.click(`#controllerRows .controller-row[data-action="${action}"] .controller-edit`);
    await page.waitForSelector(`#controller_${action}_editor:not([hidden])`);
  };
  const W = k => `sections.windows.mappings.${k}`;

  // ---- 4b: one edit through the drill-in plus Save lands exactly on disk ----
  {
    await openEditor('btn_a', 'BTN_A');
    const before = readJson(PRESET), s0 = sha(PRESET);
    await page.fill('#controller_BTN_A_f_note', '50');
    await page.click('#controller_BTN_A_editor .controller-apply');
    await page.click('#btnSave');
    const changed = await waitChange(s0);
    await sleep(2500);
    const d = diff(before, readJson(PRESET));
    const want = [{ path: W('BTN_A.note'), before: 36, after: 50 }];
    check('edit.btn_a-note-36-to-50-exact-disk-diff', changed && JSON.stringify(d) === JSON.stringify(want), d);
  }

  // ---- 4c: conflict marks (C) ----
  {
    await openEditor('start', 'START');
    await page.fill('#controller_START_f_cc', '79');
    await page.click('#controller_START_editor .controller-apply');
    const s0 = sha(PRESET), before = readJson(PRESET);
    await page.click('#btnSave');
    await page.waitForSelector('#conflictOverlay.open', { timeout: 5000 });
    const inModal = await page.evaluate(() => ({ rows: [...document.querySelectorAll('#controllerRows .controller-row.controller-conflict')].map(r => r.dataset.action), details: document.getElementById('conflictDetails').textContent }));
    check('conflict.modal-open-with-marks', inModal.rows.includes('START') && /START/.test(inModal.details) && /SELECT/.test(inModal.details), inModal);
    await page.click('#btnConflictCancel');
    await sleep(600);
    const vis = async action => page.evaluate(a => {
      const row = document.querySelector(`#controllerRows .controller-row[data-action="${a}"]`);
      const msg = row?.querySelector('.controller-conflict-message');
      if (!row || !msg) return { row: Boolean(row), marked: row?.classList.contains('controller-conflict'), msg: false };
      msg.scrollIntoView({ block: 'center' });
      const r = msg.getBoundingClientRect(); const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      const ov = document.getElementById('conflictOverlay');
      return { row: true, marked: row.classList.contains('controller-conflict'), msg: true, text: msg.textContent, uncovered: hit === msg || msg.contains(hit),
        hit: hit && (hit.id || hit.className), overlayOpen: ov.classList.contains('open'), overlayDisplay: getComputedStyle(ov).display,
        inViewport: r.top >= 0 && r.bottom <= innerHeight && r.width > 0, bodyFilter: getComputedStyle(document.querySelector('.controller-layout')).filter };
    }, action);
    const afterCancel = await vis('START');
    await page.screenshot({ path: path.join(OUT, 'conflict-after-cancel-1440x900.png') });
    check('conflict.start-marked-and-visible-after-modal-closed', afterCancel.marked && afterCancel.msg && afterCancel.uncovered && !afterCancel.overlayOpen && afterCancel.inViewport, afterCancel);
    check('conflict.cancel-writes-nothing', sha(PRESET) === s0, sha(PRESET));
    await openControl('select');
    const selectMarked = await vis('SELECT');
    check('conflict.select-marked-on-navigation', selectMarked.marked && selectMarked.uncovered, selectMarked);
    await openControl('start');
    const back = await vis('START');
    check('conflict.start-still-marked-after-navigation', back.marked && back.uncovered, back);
    await page.click('#btnSave');
    await page.waitForSelector('#conflictOverlay.open', { timeout: 5000 });
    await page.click('#btnConflictForce');
    const changed = await waitChange(s0);
    await sleep(2500);
    const d = diff(before, readJson(PRESET));
    const want = [{ path: W('START.cc'), before: 78, after: 79 }];
    check('conflict.save-anyway-exact-disk-diff', changed && JSON.stringify(d) === JSON.stringify(want), d);
    const cleared = await page.evaluate(() => ({ rows: document.querySelectorAll('.controller-row.controller-conflict').length, msgs: document.querySelectorAll('.controller-conflict-message').length }));
    await openControl('select');
    const clearedSelect = await page.evaluate(() => ({ rows: document.querySelectorAll('.controller-row.controller-conflict').length, msgs: document.querySelectorAll('.controller-conflict-message').length }));
    check('conflict.marks-clear-after-successful-save', cleared.rows === 0 && cleared.msgs === 0 && clearedSelect.rows === 0 && clearedSelect.msgs === 0, { start: cleared, select: clearedSelect });
    await page.screenshot({ path: path.join(OUT, 'conflict-after-save-1440x900.png') });
  }
  await browser.close();
  fs.writeFileSync(path.join(OUT, 'controls-results.json'), JSON.stringify(results, null, 1));
  const bad = results.filter(r => !r.pass).length;
  console.log(`CONTROLS ${results.length - bad}/${results.length} PASS`);
  process.exit(bad ? 1 : 0);
})().catch(e => { console.error('RIG ERROR', e); process.exit(2); });
