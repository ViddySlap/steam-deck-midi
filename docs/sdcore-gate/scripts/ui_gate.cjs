// sdcore gate: real headless Chromium against the live bridge on 7723.
const { chromium } = require('/Users/viddyslap/Documents/project-workspaces/life-os-showday/web-ui-server/node_modules/playwright-core');
const { execFileSync } = require('child_process');
const fs = require('fs');
const SHOTS = '/tmp/sdcore-gate/shots';
const RUN = '/Users/viddyslap/Documents/project-workspaces/steam-deck-midi';
fs.mkdirSync(SHOTS, { recursive: true });
const log = [];
const note = (...a) => { const s = a.join(' '); log.push(s); console.log(s); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const api = async p => (await fetch('http://127.0.0.1:7723' + p)).json();

(async () => {
  const exe = process.env.CHROMIUM;
  const browser = await chromium.launch({ headless: true, executablePath: exe });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const dialogAnswers = [];
  page.on('dialog', async d => {
    const answer = dialogAnswers.shift();
    note(`  dialog ${d.type()}: "${d.message()}" -> ${JSON.stringify(answer)}`);
    if (answer === false) await d.dismiss();
    else await d.accept(typeof answer === 'string' ? answer : undefined);
  });
  page.on('pageerror', e => note('  PAGE ERROR:', e.message));
  await page.goto('http://127.0.0.1:7723', { waitUntil: 'networkidle' });
  await page.waitForFunction(() => document.getElementById('sectionSelect').options.length > 0);
  const opts = () => page.$$eval('#sectionSelect option', o => o.map(x => `${x.value}${x.selected ? '*' : ''}=${x.textContent}`));
  note('1 header options:', JSON.stringify(await opts()));
  note('1 sectionStatus:', await page.textContent('#sectionStatus'));
  await page.locator('header').screenshot({ path: `${SHOTS}/01-header-section-selector-macbook.png` });
  await page.locator('.hdr-actions').screenshot({ path: `${SHOTS}/02-section-add-rename-delete-controls.png` });
  note('2 control states:', JSON.stringify(await page.$$eval('#btnSectionAdd,#btnSectionRename,#btnSectionDelete', b => b.map(x => `${x.id}:${x.disabled ? 'disabled' : 'enabled'}`))));

  // Section switch, with BTN_A open so the note value is on screen.
  await page.click('.chip[data-action="BTN_A"]');
  note('3 macbook f_note =', await page.inputValue('#f_note'));
  await page.screenshot({ path: `${SHOTS}/03-editor-macbook-btn-a-note-48.png` });
  await page.selectOption('#sectionSelect', 'windows');
  await page.waitForFunction(() => document.getElementById('sectionSelect').value === 'windows');
  await sleep(400);
  await page.click('.chip[data-action="BTN_A"]');
  note('3 windows f_note =', await page.inputValue('#f_note'), 'options', JSON.stringify(await opts()));
  note('3 delete enabled on remote section:', !(await page.isDisabled('#btnSectionDelete')));
  await page.screenshot({ path: `${SHOTS}/04-editor-switched-to-windows-btn-a-note-36.png` });
  const settingsDuringRemote = await api('/api/settings');
  note('3 bridge preset_section while editing windows (must stay macbook):', settingsDuringRemote.preset_section);
  await page.selectOption('#sectionSelect', 'macbook');
  await page.waitForFunction(() => document.getElementById('sectionSelect').value === 'macbook');
  await sleep(400);

  // Section CRUD through the native dialogs.
  dialogAnswers.push('gatecheck', true);
  await page.click('#btnSectionAdd');
  await page.waitForFunction(() => document.getElementById('sectionSelect').value === 'gatecheck', null, { timeout: 5000 });
  note('4 after add:', JSON.stringify(await opts()), 'api sections', JSON.stringify((await api('/api/mappings?section=macbook')).sections));
  await page.locator('header').screenshot({ path: `${SHOTS}/05-section-added-gatecheck.png` });
  dialogAnswers.push('gatecheck-renamed');
  await page.click('#btnSectionRename');
  await page.waitForFunction(() => document.getElementById('sectionSelect').value === 'gatecheck-renamed', null, { timeout: 5000 });
  note('4 after rename:', JSON.stringify(await opts()));
  await page.locator('header').screenshot({ path: `${SHOTS}/06-section-renamed-gatecheck-renamed.png` });
  dialogAnswers.push(true);
  await page.click('#btnSectionDelete');
  await page.waitForFunction(() => ![...document.getElementById('sectionSelect').options].some(o => o.value === 'gatecheck-renamed'), null, { timeout: 5000 });
  note('4 after delete:', JSON.stringify(await opts()), 'api sections', JSON.stringify((await api('/api/mappings?section=macbook')).sections));
  await page.locator('header').screenshot({ path: `${SHOTS}/07-section-deleted-back-to-macbook.png` });
  await sleep(2500); // let the page absorb the watcher's duplicate version bumps from the CRUD writes

  // Unsaved edit survives a disk change.
  await page.click('.chip[data-action="BTN_A"]');
  await page.fill('#f_note', '61');
  await page.click('#btnApplyFields');
  note('5 edit applied locally: f_note', await page.inputValue('#f_note'), 'unsaved badge visible', await page.isVisible('#unsavedBadge'));
  const v0 = await api('/api/state-version');
  execFileSync('python3', ['-c', `
import json
p="config/presets/EDM Show.json"
d=json.load(open(p))
d["sections"]["macbook"]["mappings"]["BTN_B"]["note"]=50
open(p,"w").write(json.dumps(d, indent=2)+"\\n")
`], { cwd: RUN });
  note('5 second process changed macbook BTN_B note to 50 on disk; state-version was', v0);
  await page.waitForFunction(() => !document.getElementById('presetChangeNotice').hidden, null, { timeout: 8000 });
  const v1 = await api('/api/state-version');
  note('5 notice visible:', await page.isVisible('#presetChangeNotice'), 'text:', JSON.stringify((await page.textContent('#presetChangeNotice')).replace(/\s+/g, ' ').trim()));
  note('5 state-version now', v1, '; f_note still', await page.inputValue('#f_note'), '; unsaved badge', await page.isVisible('#unsavedBadge'));
  const disk = JSON.parse(fs.readFileSync(`${RUN}/config/presets/EDM Show.json`, 'utf8'));
  note('5 disk macbook BTN_A note (edit NOT saved, must be 48):', disk.sections.macbook.mappings.BTN_A.note, 'BTN_B:', disk.sections.macbook.mappings.BTN_B.note);
  await page.screenshot({ path: `${SHOTS}/08-changed-on-disk-notice-unsaved-edit-kept.png` });

  // Reload button: cancel keeps edits; accept loads disk.
  dialogAnswers.push(false);
  await page.click('#btnReloadPreset');
  await sleep(600);
  note('6 reload cancelled: f_note', await page.inputValue('#f_note'), 'notice', await page.isVisible('#presetChangeNotice'));
  dialogAnswers.push(true);
  await page.click('#btnReloadPreset');
  await page.waitForFunction(() => document.getElementById('presetChangeNotice').hidden, null, { timeout: 8000 });
  await sleep(500);
  await page.click('.chip[data-action="BTN_B"]');
  note('6 reload accepted: BTN_B f_note', await page.inputValue('#f_note'), 'unsaved badge', await page.isVisible('#unsavedBadge'));
  await page.screenshot({ path: `${SHOTS}/09-after-reload-disk-value-btn-b-50.png` });
  fs.writeFileSync('/tmp/sdcore-gate/ui-gate.log', log.join('\n') + '\n');
  await browser.close();
})().catch(e => { console.error('UI GATE ERROR', e); fs.writeFileSync('/tmp/sdcore-gate/ui-gate.log', log.join('\n') + '\nERROR ' + e.stack + '\n'); process.exit(1); });
