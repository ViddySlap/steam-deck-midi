// sdbar3 gate PNG: waits for an OPEN arm's instrument client to be live, then opens a SECOND
// headless browser on the same bridge UI and screenshots the controller view mid-replay.
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('/Users/viddyslap/Documents/project-workspaces/life-os-showday/web-ui-server/node_modules/playwright-core');
const [scratch, outDir, exe] = process.argv.slice(2);
const delay = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  let dir;
  for (let i = 0; i < 1800 && !dir; i++) {
    for (const work of fs.readdirSync(scratch).filter(n => n.startsWith('timing-'))) {
      const cand = path.join(scratch, work, process.env.ARM || 'r1-OPEN-try1');
      const receipt = path.join(cand, 'client.json');
      if (fs.existsSync(receipt)) {
        try { if (JSON.parse(fs.readFileSync(receipt, 'utf8')).ready) dir = cand; } catch (e) {}
      }
    }
    if (!dir) await delay(500);
  }
  if (!dir) throw Error('no live OPEN arm');
  const ready = JSON.parse(fs.readFileSync(path.join(dir, 'capture.jsonl.ready.json'), 'utf8'));
  const port = ready.argv[ready.argv.indexOf('--ui-port') + 1];
  const url = 'http://127.0.0.1:' + port;
  const server = await chromium.launchServer({executablePath: exe, headless: true});
  const pid = server.process().pid;
  const browser = await chromium.connect(server.wsEndpoint());
  const info = {url, arm_dir: dir, browser_pid: pid};
  try {
    const context = await browser.newContext({viewport: {width: 1440, height: 900}});
    await context.addInitScript(() => {
      localStorage.setItem('steamdeck.mappingView', 'controller');
      localStorage.setItem('steamdeck.controllerFollow', 'true');
    });
    const page = await context.newPage();
    await page.goto(url, {waitUntil: 'domcontentloaded'});
    await page.locator('#viewController').click();
    if (await page.locator('#controllerFollow').getAttribute('aria-pressed') !== 'true') await page.locator('#controllerFollow').click();
    await page.waitForFunction(() => document.getElementById('controllerLiveStatus').textContent === 'live');
    await delay(8000);
    fs.mkdirSync(outDir, {recursive: true});
    info.png = path.join(outDir, 'open-arm-controller-view-live.png');
    info.state = await page.evaluate(() => ({
      live: document.getElementById('controllerLiveStatus').textContent,
      follow: document.getElementById('controllerFollow').getAttribute('aria-pressed'),
      visible: !document.getElementById('controllerView').hidden}));
    const snap = await (await fetch(url + '/api/live/snapshot')).json();
    info.snapshot = {clients: snap.clients, seq: snap.seq, dropped: snap.dropped};
    await page.screenshot({path: info.png});
    info.at = new Date().toISOString();
  } finally {
    await browser.close();
    await server.close();
  }
  try { process.kill(pid, 0); info.browser_gone = false; } catch (e) { info.browser_gone = e.code === 'ESRCH'; }
  console.log(JSON.stringify(info));
})().catch(e => { console.error(String(e)); process.exit(1); });
