// The pinned geometry detector waits for networkidle before explicitly opening
// Controller. Seed a supported saved List preference on each navigation so that
// initial wait has no SSE client. All detector bytes/assertions remain unchanged;
// it opens the real Controller stream itself before measuring the real geometry.
const {chromium} = require(process.env.PLAYWRIGHT_CORE || '/Users/viddyslap/Documents/project-workspaces/life-os-showday/web-ui-server/node_modules/playwright-core');
const launch = chromium.launch.bind(chromium);
chromium.launch = async options => {
  const browser = await launch(options);
  const newContext = browser.newContext.bind(browser);
  browser.newContext = async options => {
    const context = await newContext(options);
    await context.addInitScript(() => localStorage.setItem('steamdeck.mappingView', 'list'));
    return context;
  };
  return browser;
};
