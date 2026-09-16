#!/usr/bin/env node
// sdpolish gate: screenshots of the controller view, with the live stream up.
// Usage: node gate_shots.cjs URL CHROMIUM HOST:PORT OUTDIR PREFIX [--open CONTROL]
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const dgram = require('node:dgram');
const PW = process.env.PLAYWRIGHT_CORE
  || '/Users/viddyslap/Documents/project-workspaces/life-os-showday/web-ui-server/node_modules/playwright-core';
const {chromium} = require(PW);

const VIEWPORTS = [[1024, 768], [1366, 768], [1440, 900], [1920, 1080]];

function driver(host, port) {
  const sock = dgram.createSocket('udp4');
  let seq = 0;
  const send = (o) => { seq += 1; sock.send(Buffer.from(JSON.stringify({seq, ...o})), port, host); };
  const frame = () => {
    const a = (action, value) => send({kind: 'axis', action, value});
    a('L_STICK_X_AXIS', 22000); a('L_STICK_Y_AXIS', -18000);
    a('R_STICK_X_AXIS', -21000); a('R_STICK_Y_AXIS', 19000);
    a('L_TRIGGER_PRESSURE', 45000); a('R_TRIGGER_PRESSURE', 61000);
    a('L_PAD_X_POS', 16000); a('L_PAD_Y_POS', -14000);
    a('R_PAD_X_POS', -17000); a('R_PAD_Y_POS', 15000);
    a('GYRO_PITCH', 20000); a('GYRO_YAW', -22000); a('GYRO_ROLL', 24000);
    send({kind: 'heartbeat'});
  };
  frame();
  const t = setInterval(frame, 120);
  return {stop: () => { clearInterval(t); sock.close(); }, frame};
}

(async () => {
  const [url, chromiumPath, listen, outDir, prefix] = process.argv.slice(2);
  const openIdx = process.argv.indexOf('--open');
  const openControl = openIdx > 0 ? process.argv[openIdx + 1] : null;
  fs.mkdirSync(outDir, {recursive: true});
  const [host, port] = listen.split(':');
  const d = driver(host, Number(port));
  for (const [w, h] of VIEWPORTS) {
    const browser = await chromium.launch({executablePath: chromiumPath,
      args: ['--no-sandbox', '--disable-gpu', '--single-process']});
    const page = await browser.newPage({viewport: {width: w, height: h}});
    await page.goto(url, {waitUntil: 'domcontentloaded'});
    await page.waitForFunction(() => document.querySelectorAll('button.controller-label').length === 23, {timeout: 30000});
    await page.waitForFunction(() => (document.getElementById('controllerLiveStatus') || {}).textContent === 'live', {timeout: 30000});
    await page.waitForFunction(() => [...document.querySelectorAll('[data-live-bar]')]
      .filter((b) => Number(b.getAttribute('width')) > 0).length >= 2, {timeout: 30000});
    if (openControl) {
      await page.click(`button.controller-label[data-control="${openControl}"]`);
      await page.waitForFunction(() => { const c = document.getElementById('controllerCard'); return c && !c.hidden; }, {timeout: 10000});
    }
    d.frame();
    await page.waitForTimeout(250);
    const name = `${prefix}-${w}x${h}-${openControl ? `card-open-${openControl}` : 'card-closed'}.png`;
    await page.screenshot({path: path.join(outDir, name)});
    console.log(`WROTE ${path.join(outDir, name)}`);
    await page.close();
    await browser.close();
  }
  d.stop();
})();
