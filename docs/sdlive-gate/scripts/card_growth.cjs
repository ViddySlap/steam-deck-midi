// sdlive gate: DOM node / listener counts (post-GC, CDP Performance.getMetrics) across 24 card opens, no input traffic.
// node card_growth.cjs URL CHROMIUM
const {chromium} = require(process.env.PLAYWRIGHT_CORE || '/Users/viddyslap/Documents/project-workspaces/life-os-showday/web-ui-server/node_modules/playwright-core');
const [url, executablePath] = process.argv.slice(2);
(async () => {
  const browser = await chromium.launch({executablePath, headless: true});
  const page = await (await browser.newContext({viewport: {width: 1440, height: 900}})).newPage();
  await page.goto(url, {waitUntil: 'domcontentloaded'});
  await page.waitForFunction(() => document.querySelectorAll('.controller-label').length === 23, null, {timeout: 10000});
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Performance.enable');
  const m = async () => { await cdp.send('HeapProfiler.collectGarbage'); const x = (await cdp.send('Performance.getMetrics')).metrics; return Object.fromEntries(x.filter(e => ['Nodes', 'JSEventListeners', 'JSHeapUsedSize'].includes(e.name)).map(e => [e.name, e.value])); };
  const ids = ['btn_a', 'btn_b', 'dpad_up', 'l2', 'left_stick', 'r1', 'start', 'gyro'];
  const series = [await m()];
  for (let i = 0; i < 24; i++) {
    await page.click(`.controller-label[data-control="${ids[i % ids.length]}"]`);
    await page.waitForFunction(() => !document.getElementById('controllerCard').hidden);
    if ((i + 1) % 8 === 0) series.push(await m());
  }
  console.log(JSON.stringify({url, series, perOpenNodes: (series.at(-1).Nodes - series[0].Nodes) / 24, perOpenListeners: (series.at(-1).JSEventListeners - series[0].JSEventListeners) / 24}));
  await browser.close();
})().catch(e => { console.error(e); process.exitCode = 1; });
