// sdlive gate step 2 extras. Real Chromium + real loopback UDP.
// node extra_pngs.cjs hold URL CHROMIUM OUT.png      -> A down, left stick up-right, R2 70 percent held, then screenshot
// node extra_pngs.cjs offline URL CHROMIUM OUT.png MARKER -> wait live, write MARKER, wait for 'offline' (bridge stopped outside), screenshot
const fs = require('node:fs');
const dgram = require('node:dgram');
const {chromium} = require(process.env.PLAYWRIGHT_CORE || '/Users/viddyslap/Documents/project-workspaces/life-os-showday/web-ui-server/node_modules/playwright-core');
const [mode, url, executablePath, out, marker] = process.argv.slice(2);
const u = new URL(url);
if (u.hostname !== '127.0.0.1' || ['7723', '45123'].includes(u.port)) throw Error('unsafe url');
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const browser = await chromium.launch({executablePath, headless: true});
  const sock = dgram.createSocket('udp4');
  let code = 1;
  try {
    const page = await (await browser.newContext({viewport: {width: 1440, height: 900}})).newPage();
    await page.goto(url, {waitUntil: 'domcontentloaded'});
    await page.waitForFunction(() => document.querySelectorAll('.controller-label').length === 23, null, {timeout: 10000});
    const hasLive = await page.evaluate(() => !!document.getElementById('controllerLiveStatus'));
    if (mode === 'hold') {
      const settings = await (await fetch(url + '/api/settings')).json();
      const [host, port] = settings.listen.split(':');
      if (host !== '127.0.0.1' || Number(port) === 45123) throw Error('unsafe listen');
      let seq = 0;
      const send = o => new Promise((res, rej) => { const b = {...o, seq: ++seq}; sock.send(Buffer.from(JSON.stringify(Object.fromEntries(Object.keys(b).sort().map(k => [k, b[k]])))), Number(port), host, e => e ? rej(e) : res()); });
      const hb = setInterval(() => send({kind: 'heartbeat'}).catch(() => {}), 100);
      await send({kind: 'action', action: 'BTN_A', state: 'down'});
      await send({kind: 'axis', action: 'L_STICK_X_AXIS', value: 23085});
      await send({kind: 'axis', action: 'L_STICK_Y_AXIS', value: 22863});
      await send({kind: 'axis', action: 'R_TRIGGER_PRESSURE', value: 45875});
      await sleep(1500);
      const state = await page.evaluate(() => ({
        aDown: document.querySelector('.controller-art [data-control="btn_a"]').classList.contains('control-down'),
        dots: document.querySelectorAll('[data-live-dot]').length, bars: document.querySelectorAll('[data-live-bar]').length,
        liveStatus: document.getElementById('controllerLiveStatus')?.textContent ?? null}));
      const snap = await (await fetch(url + '/api/settings')).json();
      console.log('HOLD_STATE', JSON.stringify({...state, hasLiveTools: hasLive}));
      await page.screenshot({path: out});
      await send({kind: 'action', action: 'BTN_A', state: 'up'});
      clearInterval(hb);
    } else {
      await page.waitForFunction(() => document.getElementById('controllerLiveStatus').textContent === 'live', null, {timeout: 10000});
      fs.writeFileSync(marker, 'live\n');
      const t0 = Date.now();
      await page.waitForFunction(() => document.getElementById('controllerLiveStatus').textContent === 'offline', null, {timeout: 60000, polling: 100});
      console.log('OFFLINE_AFTER_MS', Date.now() - t0, 'status', await page.locator('#controllerLiveStatus').textContent());
      await page.screenshot({path: out});
    }
    console.log('PNG', out);
    code = 0;
  } catch (e) { console.error(String(e.stack || e)); }
  finally { sock.close(); await browser.close(); process.exitCode = code; }
})();
