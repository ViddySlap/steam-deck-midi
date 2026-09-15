// sdauto gate step 5: node header_gate.cjs URL CHROMIUM OUTDIR TAG header|engines
// header: at 1440x900 the header is ONE row (every visible header child's box shares one
//         horizontal band: max(top) < min(bottom)) with the Controller view open AND with
//         the List open; version label text; PNG <TAG>-header.png (Controller view).
// engines: Engines tab PNG <TAG>-engines.png.
const fs = require('node:fs');
const path = require('node:path');
const [url, exe, out, tag, mode] = process.argv.slice(2);
const {chromium} = require(process.env.PLAYWRIGHT_CORE || '/Users/viddyslap/Documents/project-workspaces/life-os-showday/web-ui-server/node_modules/playwright-core');
(async () => {
  const browser = await chromium.launch({executablePath: exe});
  const result = {tag, url, mode, browser_version: browser.version()};
  const errors = [];
  let code = 0;
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 900}});
    page.on('pageerror', e => errors.push(String(e)));
    await page.goto(url, {waitUntil: 'load'});
    await page.waitForFunction(() => document.getElementById('sectionSelect').options.length > 0, null, {timeout: 15000});
    await page.waitForTimeout(1500);
    const measure = () => page.evaluate(() => {
      const header = document.querySelector('header');
      const vis = el => { const b = el.getBoundingClientRect(); const cs = getComputedStyle(el); return b.width > 0 && b.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
      const items = [...header.children].flatMap(el => el.classList.contains('hdr-actions') ? [...el.children] : [el]).filter(vis)
        .map(el => { const b = el.getBoundingClientRect(); return {id: el.id || el.className || el.tagName, top: +b.top.toFixed(1), bottom: +b.bottom.toFixed(1), left: Math.round(b.left), right: Math.round(b.right)}; });
      const maxTop = Math.max(...items.map(i => i.top)), minBottom = Math.min(...items.map(i => i.bottom));
      const hb = header.getBoundingClientRect();
      const ver = document.getElementById('appVersion');
      return {items, item_count: items.length, max_top: maxTop, min_bottom: minBottom, one_row: items.length > 0 && maxTop < minBottom,
              header_height: Math.round(hb.height), section_select_width: Math.round(document.getElementById('sectionSelect').getBoundingClientRect().width),
              version_text: ver ? ver.textContent : null,
              controller_pressed: document.getElementById('viewController').getAttribute('aria-pressed'),
              list_pressed: document.getElementById('viewList').getAttribute('aria-pressed')};
    });
    if (mode === 'header') {
      await page.click('#viewController');
      await page.waitForTimeout(700);
      result.controller = await measure();
      await page.screenshot({path: path.join(out, `${tag}-header.png`)});
      await page.click('#viewList');
      await page.waitForTimeout(700);
      result.list = await measure();
      await page.screenshot({path: path.join(out, `${tag}-header-list.png`)});
      await page.click('#viewController');
    } else {
      await page.click('.tab[data-tab="engines"]');
      await page.waitForFunction(() => document.querySelectorAll('#enginesList .engine-toggle').length > 0, null, {timeout: 15000});
      await page.waitForTimeout(700);
      result.engines_rows = await page.evaluate(() => [...document.querySelectorAll('#enginesList .engine-toggle')].map(cb => ({type: cb.dataset.type, checked: cb.checked})));
      result.engines_text_has_channel_state = await page.evaluate(() => /beats|transition|layer_enabled|clip_mode/i.test(document.getElementById('tab-engines').textContent));
      await page.screenshot({path: path.join(out, `${tag}-engines.png`)});
    }
  } catch (e) {
    result.error = String(e);
    code = 2;
  } finally {
    result.page_errors = errors;
    await browser.close();
    fs.writeFileSync(path.join(out, `${tag}-${mode}.json`), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
    process.exit(code);
  }
})();
