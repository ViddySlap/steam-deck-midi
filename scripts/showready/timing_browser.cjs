// Foreground --client-cmd adapter. Owns an isolated browser and closes it on stop.
const fs = require('node:fs');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || '/Users/viddyslap/Documents/project-workspaces/life-os-showday/web-ui-server/node_modules/playwright-core');
const [url, stop, receipt, executablePath, ...args] = process.argv.slice(2);
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const write = value => { fs.writeFileSync(receipt + '.tmp', JSON.stringify(value)); fs.renameSync(receipt + '.tmp', receipt); };
(async () => {
  if (new URL(url).hostname !== '127.0.0.1' || ['7723', '45123'].includes(new URL(url).port)) throw Error('Unsafe UI URL');
  let server, browser;
  const result = { browser_pids: [], data_events: 0, dropped: 0, error: null, page_checks: [] };
  try {
    server = await chromium.launchServer({executablePath, headless: true,
      args: args.includes('--single-process') ? ['--single-process'] : []});
    result.browser_pids = [server.process().pid];
    write(result); // Retain owned PID even if navigation fails.
    browser = await chromium.connect(server.wsEndpoint());
    const context = await browser.newContext({viewport: {width:1440,height:900}});
    await context.addInitScript(() => {
      localStorage.setItem('steamdeck.mappingView', 'controller');
      localStorage.setItem('steamdeck.controllerFollow', 'true');
      window.bar3Stream = {data_events:0, dropped:0};
      const Native = window.EventSource;
      window.EventSource = class extends Native {
        constructor(...argv) {
          super(...argv);
          for (const kind of ['input','axis','midi','dropped']) this.addEventListener(kind, event => {
            const data = JSON.parse(event.data);
            if(kind === 'dropped') window.bar3Stream.dropped += data.count;
            else window.bar3Stream.data_events++;
          });
        }
      };
    });
    const page = await context.newPage();
    page.on('pageerror', error => {result.error = String(error);});
    await page.goto(url, {waitUntil:'domcontentloaded'});
    await page.locator('#viewController').click();
    if(await page.locator('#controllerFollow').getAttribute('aria-pressed') !== 'true') await page.locator('#controllerFollow').click();
    await page.waitForFunction(() => document.getElementById('controllerLiveStatus').textContent === 'live');
    result.ready = true;
    write(result);
    while(!fs.existsSync(stop)) {
      const observed = await page.evaluate(() => ({
        ...window.bar3Stream,
        visible: document.visibilityState === 'visible' && !document.getElementById('controllerView').hidden,
        follow: document.getElementById('controllerFollow').getAttribute('aria-pressed') === 'true',
        live: document.getElementById('controllerLiveStatus').textContent === 'live'
      }));
      result.page_checks.push(observed);
      result.data_events = observed.data_events;
      result.dropped = observed.dropped;
      if(!observed.visible || !observed.follow || !observed.live || result.error) throw Error('Controller/follow/live lost');
      await delay(100);
    }
    Object.assign(result, await page.evaluate(() => window.bar3Stream));
  } catch(error) {
    result.error = String(error);
    process.exitCode = 1;
  } finally {
    if(browser) await browser.close();
    if(server) await server.close();
    result.closed = true;
    write(result);
  }
})();
