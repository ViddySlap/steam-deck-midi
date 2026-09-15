// node header_measure.cjs URL CHROMIUM OUTDIR TAG
// Real Chromium: header row geometry at 1440x900 and 1024x768, the version label,
// and the width of every form control outside the header (for a cross-arm diff).
const fs = require('node:fs');
const path = require('node:path');
const [url, exe, out, tag] = process.argv.slice(2);
const {chromium} = require(process.env.PLAYWRIGHT_CORE || '/Users/viddyslap/Documents/project-workspaces/life-os-showday/web-ui-server/node_modules/playwright-core');
(async () => {
  const browser = await chromium.launch({executablePath: exe});
  const result = {tag, url, viewports: {}};
  const errors = [];
  const page = await browser.newPage({viewport: {width: 1440, height: 900}});
  page.on('pageerror', e => errors.push(String(e)));
  for (const [w, h] of [[1440, 900], [1024, 768]]) {
    await page.setViewportSize({width: w, height: h});
    await page.goto(url, {waitUntil: 'load'});
    await page.waitForFunction(() => document.getElementById('sectionSelect').options.length > 0, null, {timeout: 10000});
    await page.waitForTimeout(500);
    const m = await page.evaluate(() => {
      const r = el => { const b = el.getBoundingClientRect(); return {top: Math.round(b.top), bottom: Math.round(b.bottom), left: Math.round(b.left), right: Math.round(b.right), width: Math.round(b.width), height: Math.round(b.height)}; };
      const header = document.querySelector('header');
      const visible = el => { const b = el.getBoundingClientRect(); return b.width > 0 && b.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
      const items = [...header.querySelectorAll('.logo, h1, .hdr-actions > *')].filter(visible)
        .map(el => ({id: el.id || el.className || el.tagName, text: (el.textContent || '').trim().slice(0, 30), ...r(el)}));
      const centers = items.map(i => (i.top + i.bottom) / 2);
      const controls = [...document.querySelectorAll('input, select, textarea')].filter(el => !header.contains(el))
        .map((el, i) => ({key: el.id || `${el.tagName}#${i}`, computed_width: getComputedStyle(el).width, box_width: Math.round(el.getBoundingClientRect().width)}));
      const sel = document.getElementById('sectionSelect');
      const ver = document.getElementById('appVersion');
      return {
        header: r(header), items, center_spread_px: Math.round(Math.max(...centers) - Math.min(...centers)),
        section_select: {computed_width: getComputedStyle(sel).width, ...r(sel), options: [...sel.options].map(o => o.textContent)},
        scroll_width: document.documentElement.scrollWidth,
        version_label: ver ? {text: ver.textContent, title: ver.title, ...r(ver)} : null,
        controls,
      };
    });
    m.one_row = m.center_spread_px <= 4 && m.header.height <= 50;
    result.viewports[`${w}x${h}`] = m;
    await page.screenshot({path: path.join(out, `${tag}-${w}x${h}.png`)});
  }
  result.page_errors = errors;
  await browser.close();
  fs.writeFileSync(path.join(out, `${tag}.json`), JSON.stringify(result, null, 2));
  for (const [vp, m] of Object.entries(result.viewports))
    console.log(`${tag} ${vp} header_height=${m.header.height} center_spread_px=${m.center_spread_px} one_row=${m.one_row} section_select_width=${m.section_select.width} scroll_width=${m.scroll_width} version=${JSON.stringify(m.version_label && m.version_label.text)}`);
  console.log(`${tag} page_errors=${errors.length}`);
})().catch(e => { console.error(e); process.exit(1); });
