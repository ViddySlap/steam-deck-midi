// sdlive gate step 1a-1f + AFTER PNGs. Real headless Chromium, real loopback UDP to a
// scratch dry-run bridge started by bridge.py, real SSE. Asserts DOM/computed style and
// the bridge's own JSON snapshot. Nothing in the page is stubbed.
// node live_gate.cjs URL CHROMIUM OUTDIR [--single-process] [--stress-seconds N]
const fs = require('node:fs');
const path = require('node:path');
const dgram = require('node:dgram');
const {chromium} = require(process.env.PLAYWRIGHT_CORE || '/Users/viddyslap/Documents/project-workspaces/life-os-showday/web-ui-server/node_modules/playwright-core');
const [url, executablePath, out, ...rest] = process.argv.slice(2);
const stressSeconds = rest.includes('--stress-seconds') ? Number(rest[rest.indexOf('--stress-seconds') + 1]) : 60;
const results = [];
let failed = 0;
const check = (name, pass, detail) => {
  results.push({name, pass: Boolean(pass), detail});
  if (!pass) failed++;
  console.log(`${pass ? 'PASS' : 'FAIL'} ${name} ${JSON.stringify(detail)}`);
};
const sleep = ms => new Promise(r => setTimeout(r, ms));
const u = new URL(url);
if (u.hostname !== '127.0.0.1' || ['7723', '45123'].includes(u.port)) throw Error('unsafe url');
fs.mkdirSync(out, {recursive: true});

(async () => {
  const launchArgs = rest.includes('--single-process') ? ['--single-process'] : [];
  const browser = await chromium.launch({executablePath, headless: true, args: launchArgs});
  console.log('BROWSER_PID', browser.process ? browser.process()?.pid : 'n/a', 'args', JSON.stringify(launchArgs));
  const sock = dgram.createSocket('udp4');
  const settings = await (await fetch(url + '/api/settings')).json();
  const [host, portText] = settings.listen.split(':');
  const port = Number(portText);
  if (host !== '127.0.0.1' || port === 45123) throw Error('unsafe listen ' + settings.listen);
  let seq = 0, sent = 0;
  // Same compact sorted-key encoding as the pinned deck script packets.
  const send = body => new Promise((res, rej) => {
    const obj = {...body, seq: ++seq};
    const ordered = Object.fromEntries(Object.keys(obj).sort().map(k => [k, obj[k]]));
    sock.send(Buffer.from(JSON.stringify(ordered)), port, host, e => { if (e) rej(e); else { sent++; res(Date.now()); } });
  });
  const press = (action, state) => send({kind: 'action', action, state});
  const axis = (action, value) => send({kind: 'axis', action, value});
  const heartbeat = setInterval(() => send({kind: 'heartbeat'}).catch(() => {}), 100);
  const snap = async () => (await fetch(url + '/api/live/snapshot', {cache: 'no-store'})).json();
  const waitFor = async (page, fn, arg, timeout = 2000) => {
    const t0 = Date.now();
    try { await page.waitForFunction(fn, arg, {timeout, polling: 'raf'}); return {ok: true, ms: Date.now() - t0}; }
    catch (e) { return {ok: false, ms: Date.now() - t0, error: String(e).split('\n')[0]}; }
  };
  const clientsReach = async (wanted, timeout) => {
    const t0 = Date.now();
    const seen = [];
    while (Date.now() - t0 <= timeout) {
      const s = await snap();
      seen.push(s.clients);
      if (s.clients === wanted) return {ok: true, ms: Date.now() - t0, seen};
      await sleep(20);
    }
    return {ok: false, ms: Date.now() - t0, seen};
  };
  const openPage = async () => {
    const context = await browser.newContext({viewport: {width: 1440, height: 900}});
    await context.addInitScript(() => {
      window.gateStream = {data_events: 0, dropped_events: 0, dropped_count: 0};
      const Native = window.EventSource;
      window.EventSource = class extends Native {
        constructor(...argv) {
          super(...argv);
          for (const kind of ['input', 'axis', 'midi', 'dropped']) this.addEventListener(kind, event => {
            if (kind === 'dropped') { window.gateStream.dropped_events++; window.gateStream.dropped_count += JSON.parse(event.data).count || 0; }
            else window.gateStream.data_events++;
          });
        }
      };
    });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('dialog', d => d.dismiss());
    await page.goto(url, {waitUntil: 'domcontentloaded'});
    const ready = await waitFor(page, () => document.querySelectorAll('.controller-label').length === 23 &&
      document.getElementById('controllerLiveStatus').textContent === 'live', null, 10000);
    return {context, page, errors, ready};
  };
  const shapeState = (page, id) => page.evaluate(id => {
    const shape = document.querySelector(`.controller-art [data-control="${id}"]`);
    const label = document.querySelector(`.controller-label[data-control="${id}"]`);
    const tag = label.querySelector('.controller-live-tag');
    const cs = getComputedStyle(shape), ls = getComputedStyle(label);
    return {shapeDown: shape.classList.contains('control-down'), labelDown: label.classList.contains('control-down'),
      fill: cs.fill, stroke: cs.stroke, labelBg: ls.backgroundColor, labelBorder: ls.borderColor,
      tag: tag ? tag.textContent : null, tagHidden: tag ? tag.hidden : null};
  }, id);
  const shot = async (page, name) => { const p = path.join(out, name); await page.screenshot({path: p}); console.log('PNG', p); };

  try {
    // ---------- fresh profile ----------
    const s0 = await snap();
    check('pre: bridge has zero live clients before any page', s0.clients === 0, {clients: s0.clients});
    const A = await openPage();
    const {page} = A;
    check('pre: Controller ready (23 labels, live)', A.ready.ok, A.ready);
    const c1 = await clientsReach(1, 3000);
    check('pre: one live client while Controller visible', c1.ok, c1);
    check('1d: Follow default OFF on a fresh profile', await page.locator('#controllerFollow').getAttribute('aria-pressed') === 'false',
      {aria: await page.locator('#controllerFollow').getAttribute('aria-pressed'), text: await page.locator('#controllerFollow').textContent()});

    // ---------- 1a highlight ----------
    const aIdle = await shapeState(page, 'btn_a');
    await press('BTN_A', 'down');
    const aLit = await waitFor(page, () => document.querySelector('.controller-art [data-control="btn_a"]').classList.contains('control-down'));
    const aDown = await shapeState(page, 'btn_a');
    const snapA = await snap();
    check('1a: BTN_A down lights A shape and label', aLit.ok && aDown.shapeDown && aDown.labelDown, {wait: aLit, idle: aIdle, down: aDown});
    check('1a: lit computed style differs from idle', aDown.fill !== aIdle.fill || aDown.stroke !== aIdle.stroke || aDown.labelBg !== aIdle.labelBg || aDown.labelBorder !== aIdle.labelBorder,
      {idle: [aIdle.fill, aIdle.stroke, aIdle.labelBg, aIdle.labelBorder], down: [aDown.fill, aDown.stroke, aDown.labelBg, aDown.labelBorder]});
    check('1a: bridge snapshot shows BTN_A pressed', snapA.pressed.includes('BTN_A'), {pressed: snapA.pressed});
    check('1a: follow OFF leaves card closed on press', await page.locator('#controllerCard').isHidden(), {});
    await press('BTN_A', 'up');
    const aClear = await waitFor(page, () => !document.querySelector('.controller-art [data-control="btn_a"]').classList.contains('control-down'));
    const aUp = await shapeState(page, 'btn_a');
    check('1a: BTN_A up clears shape and label', aClear.ok && !aUp.shapeDown && !aUp.labelDown && aUp.fill === aIdle.fill, {wait: aClear, up: aUp});
    await press('L2_SOFT_LAYER_2', 'down');
    const l2Lit = await waitFor(page, () => document.querySelector('.controller-art [data-control="l2"]').classList.contains('control-down'));
    const l2 = await shapeState(page, 'l2');
    check('1a: L2_SOFT_LAYER_2 lights L2 with its group tag L2', l2Lit.ok && l2.shapeDown && l2.labelDown && l2.tag === 'L2' && l2.tagHidden === false, {wait: l2Lit, l2});
    await press('L2_SOFT_LAYER_2', 'up');
    const l2Clear = await waitFor(page, () => !document.querySelector('.controller-art [data-control="l2"]').classList.contains('control-down'));
    check('1a: L2 clears on up', l2Clear.ok, l2Clear);

    // ---------- 1b dots and bars ----------
    const geo = id => page.evaluate(id => {
      const dot = document.querySelector(`[data-live-dot="${id}"]`) || document.querySelector(`[data-live-bar="${id}"]`);
      const shape = document.querySelector(`.controller-art [data-control="${id}"]`);
      const b = shape.getBBox(), r = shape.getBoundingClientRect(), d = dot.getBoundingClientRect();
      return {cx: dot.getAttribute('cx'), cy: dot.getAttribute('cy'), width: dot.getAttribute('width'), opacity: getComputedStyle(dot).opacity,
        shapeBBox: {x: b.x, y: b.y, w: b.width, h: b.height}, shapeScreen: {x: r.x, y: r.y, w: r.width, h: r.height},
        dotScreen: {cx: d.x + d.width / 2, cy: d.y + d.height / 2, w: d.width, h: d.height}};
    }, id);
    await axis('L_STICK_X_AXIS', 32767); await axis('L_STICK_Y_AXIS', 0);
    const stickW = await waitFor(page, () => document.querySelector('[data-live-dot="left_stick"]').getAttribute('cx') === '310');
    const st = await geo('left_stick');
    const travel = 30, anchor = {x: 280, y: 175};
    const dx = Number(st.cx) - anchor.x, dy = Number(st.cy) - anchor.y;
    // Right edge centre of the dot's travel circle; 5 percent of the full travel diameter.
    check('1b: left stick dot at right edge centre within 5 percent', Math.abs(dx - travel) <= 0.05 * 2 * travel && Math.abs(dy) <= 0.05 * 2 * travel,
      {wait: stickW, cx: st.cx, cy: st.cy, dx, dy, travel, shapeBBox: st.shapeBBox,
       shapeRightEdgeCentre: {x: st.shapeBBox.x + st.shapeBBox.w, y: st.shapeBBox.y + st.shapeBBox.h / 2},
       screen: {dot: st.dotScreen, shape: st.shapeScreen,
         normX: (st.dotScreen.cx - (st.shapeScreen.x + st.shapeScreen.w / 2)) / (st.shapeScreen.w / 2),
         normY: (st.dotScreen.cy - (st.shapeScreen.y + st.shapeScreen.h / 2)) / (st.shapeScreen.h / 2)}});
    await axis('R_TRIGGER_PRESSURE', 32768);
    const barW = await waitFor(page, () => Math.abs(Number(document.querySelector('[data-live-bar="r2"]').getAttribute('width')) - 32) < 0.01);
    const bar = await geo('r2');
    check('1b: R2 bar about half at R_TRIGGER_PRESSURE 32768 of 65535', Math.abs(Number(bar.width) / 64 - 0.5) <= 0.05, {wait: barW, width: bar.width, fraction: Number(bar.width) / 64});
    const padSamples = [];
    const padStart = Date.now();
    let i = 0;
    while (Date.now() - padStart < 1000) {
      await axis('L_PAD_X_POS', Math.round(20000 * Math.cos(i / 10))); await axis('L_PAD_Y_POS', Math.round(20000 * Math.sin(i / 10)));
      i++;
      if (i % 6 === 0) padSamples.push((await geo('left_pad')).opacity);
      await sleep(16);
    }
    const padStop = Date.now();
    const visibleWhileFlowing = padSamples.filter(o => o === '1').length;
    check('1b: trackpad dot visible while its events flow', padSamples.length > 0 && padSamples.slice(1).every(o => o === '1'), {samples: padSamples, visibleWhileFlowing, packetsTicks: i});
    const fade = await waitFor(page, () => getComputedStyle(document.querySelector('[data-live-dot="left_pad"]')).opacity === '0', null, 3000);
    check('1b: trackpad dot fades after events stop', fade.ok && fade.ms >= 250, {msAfterStop: Date.now() - padStop, wait: fade});

    // ---------- AFTER PNG 1: A held, stick up-right, R2 70 percent, live ----------
    await press('BTN_A', 'down');
    await axis('L_STICK_X_AXIS', 23085); await axis('L_STICK_Y_AXIS', 22863);
    await axis('R_TRIGGER_PRESSURE', 45875);
    const pngReady = await waitFor(page, () => document.querySelector('.controller-art [data-control="btn_a"]').classList.contains('control-down') &&
      Math.abs(Number(document.querySelector('[data-live-bar="r2"]').getAttribute('width')) - 44.8) < 0.2 &&
      Number(document.querySelector('[data-live-dot="left_stick"]').getAttribute('cy')) < 175);
    check('2: AFTER inputs rendered (A lit, stick up-right, R2 70 percent)', pngReady.ok, {wait: pngReady, stick: await geo('left_stick'), r2: await geo('r2')});
    await shot(page, 'after-1-a-lit-stick-upright-r2-70-live.png');
    await press('BTN_A', 'up');
    await axis('L_STICK_X_AXIS', 0); await axis('L_STICK_Y_AXIS', 0); await axis('R_TRIGGER_PRESSURE', 0);

    // ---------- 1c row flash ----------
    await page.click('.controller-label[data-control="dpad_up"]');
    const cardOpen = await waitFor(page, () => !document.getElementById('controllerCard').hidden && document.getElementById('controllerTitle').textContent === 'D-pad Up');
    const rows = await page.evaluate(() => [...document.querySelectorAll('#controllerRows [data-action]')].map(e => e.dataset.action));
    check('1c: D-pad Up card open with tap and long-press rows', cardOpen.ok && rows.includes('DPAD_UP') && rows.includes('DPAD_UP_LONG_PRESS'), {wait: cardOpen, rows});
    await page.evaluate(() => {
      window.gateFlash = [];
      const rec = () => {
        const t = performance.timeOrigin + performance.now();
        for (const row of document.querySelectorAll('#controllerRows [data-action]')) if (row.classList.contains('controller-midi-flash')) window.gateFlash.push({t, action: row.dataset.action});
      };
      new MutationObserver(rec).observe(document.getElementById('controllerRows'), {subtree: true, attributes: true, attributeFilter: ['class']});
      const loop = () => { rec(); if (window.gateFlashLoop) requestAnimationFrame(loop); };
      window.gateFlashLoop = true; requestAnimationFrame(loop);
    });
    const midiBefore = (await snap()).midi.length;
    const sentAt = await press('DPAD_UP_LONG_PRESS', 'down');
    await sleep(50);
    const at50 = await page.evaluate(() => Object.fromEntries([...document.querySelectorAll('#controllerRows [data-action]')].map(e => [e.dataset.action, e.classList.contains('controller-midi-flash')])));
    const flashSeen = await waitFor(page, () => window.gateFlash.some(f => f.action === 'DPAD_UP_LONG_PRESS'), null, 1000);
    if (flashSeen.ok) await shot(page, 'after-2-dpad-up-long-press-row-flash.png');
    await sleep(1000);
    const flashLog = await page.evaluate(() => { window.gateFlashLoop = false; return window.gateFlash; });
    const snapC = await snap();
    const firstLong = flashLog.find(f => f.action === 'DPAD_UP_LONG_PRESS');
    const tapFlashes = flashLog.filter(f => f.action === 'DPAD_UP');
    const midiLong = snapC.midi.filter(m => m.action === 'DPAD_UP_LONG_PRESS');
    check('1c: bridge sent MIDI attributed to DPAD_UP_LONG_PRESS', midiLong.length > 0, {midiTotalBefore: midiBefore, lastMidi: snapC.midi.slice(-5)});
    check('1c: long-press row flashes within 100 ms of the press', firstLong && firstLong.t - sentAt <= 100, {sentAt, firstFlashAt: firstLong && firstLong.t, deltaMs: firstLong && firstLong.t - sentAt, domAt50ms: at50});
    check('1c: tap row does not flash', tapFlashes.length === 0 && at50.DPAD_UP === false, {tapFlashes: tapFlashes.length, domAt50ms: at50, otherRowsFlashed: [...new Set(flashLog.map(f => f.action))]});
    await press('DPAD_UP_LONG_PRESS', 'up');
    await sleep(2500); // let the macro fade finish
    await page.click('#controllerClose');

    // ---------- 1e closed means closed ----------
    await page.click('#viewList');
    const closed = await clientsReach(0, 2000);
    check('1e: List view -> zero live clients within 2 s (bridge snapshot)', closed.ok, closed);
    const statusList = await page.locator('#controllerLiveStatus').textContent();
    await page.click('#viewController');
    const reopened = await clientsReach(1, 3000);
    check('1e: back to Controller -> one live client', reopened.ok, {reopened, statusWhileList: statusList});
    await waitFor(page, () => document.getElementById('controllerLiveStatus').textContent === 'live', null, 3000);

    // ---------- 1d follow ----------
    await page.click('#controllerFollow');
    const followOn = await waitFor(page, () => document.getElementById('controllerFollow').getAttribute('aria-pressed') === 'true');
    check('1d: Follow toggles ON', followOn.ok, {wait: followOn, text: await page.locator('#controllerFollow').textContent()});
    await press('BTN_Y', 'down');
    const yOpen = await waitFor(page, () => !document.getElementById('controllerCard').hidden && document.getElementById('controllerTitle').textContent === 'Y');
    check('1d: Follow ON + BTN_Y press opens Y card', yOpen.ok, yOpen);
    if (yOpen.ok) await shot(page, 'after-3-follow-on-card-opened-by-press.png');
    await press('BTN_Y', 'up');
    await page.locator('[data-action="BTN_Y"] .controller-edit').click();
    await page.locator('#controller_BTN_Y_f_note').fill('99');
    const noteShown = await waitFor(page, () => !document.getElementById('controllerFollowNote').hidden);
    await press('BTN_X', 'down');
    const xLit = await waitFor(page, () => document.querySelector('.controller-art [data-control="btn_x"]').classList.contains('control-down'));
    await sleep(400);
    const afterX = await page.evaluate(() => ({title: document.getElementById('controllerTitle').textContent, hidden: document.getElementById('controllerCard').hidden,
      note: document.getElementById('controllerFollowNote').hidden ? null : document.getElementById('controllerFollowNote').textContent,
      typed: document.getElementById('controller_BTN_Y_f_note')?.value}));
    check('1d: unsaved inline edit + BTN_X press -> card does not switch, paused note shows', noteShown.ok && xLit.ok && afterX.title === 'Y' && !afterX.hidden && afterX.note === 'follow paused: unsaved edit' && afterX.typed === '99', {noteShown, xLit, afterX});
    await shot(page, 'after-3b-follow-paused-unsaved-edit.png');
    await press('BTN_X', 'up');
    check('1a-1e: no page JavaScript errors', A.errors.length === 0, A.errors);
    await A.context.close();
    const afterClose = await clientsReach(0, 3000);
    check('post: closing the page returns clients to 0', afterClose.ok, afterClose);

    // ---------- 1f stress ----------
    const B = await openPage();
    const sp = B.page;
    check('1f: stress page ready', B.ready.ok, B.ready);
    const cdp = await B.context.newCDPSession(sp);
    await cdp.send('Performance.enable');
    const heap = async gc => { if (gc) await cdp.send('HeapProfiler.collectGarbage'); const m = (await cdp.send('Performance.getMetrics')).metrics; return Object.fromEntries(m.filter(x => ['JSHeapUsedSize', 'JSHeapTotalSize', 'Nodes', 'JSEventListeners'].includes(x.name)).map(x => [x.name, x.value])); };
    const heapBefore = await heap(true);
    const snapBefore = await snap();
    const axes = ['L_STICK_X_AXIS', 'L_STICK_Y_AXIS', 'R_STICK_X_AXIS', 'R_STICK_Y_AXIS', 'L_TRIGGER_PRESSURE', 'R_TRIGGER_PRESSURE', 'L_PAD_X_POS', 'L_PAD_Y_POS', 'R_PAD_X_POS', 'R_PAD_Y_POS', 'GYRO_PITCH', 'GYRO_YAW', 'GYRO_ROLL'];
    const tick = 1000 / 60;
    let ticks = 0, streamErr = null, stressSent0 = sent;
    const t0 = performance.now();
    const streamer = (async () => {
      while (performance.now() - t0 < stressSeconds * 1000) {
        const phase = ticks / 60;
        for (const [k, a] of axes.entries()) {
          const trig = a.includes('TRIGGER');
          const v = trig ? Math.round(32767 + 32767 * Math.sin(phase * 2 + k)) : Math.round(32000 * Math.sin(phase * 2 + k));
          send({kind: 'axis', action: a, value: v}).catch(e => { streamErr = String(e); });
        }
        ticks++;
        const due = t0 + ticks * tick;
        const wait = due - performance.now();
        if (wait > 0) await sleep(wait);
      }
    })();
    const clicks = [];
    const heapDuring = [];
    const labelsToClick = ['btn_a', 'btn_b', 'dpad_up', 'l2', 'left_stick', 'r1', 'start', 'gyro'];
    const titles = {btn_a: 'A', btn_b: 'B', dpad_up: 'D-pad Up', l2: 'L2', left_stick: 'Left stick', r1: 'R1', start: 'START', gyro: 'Gyro'};
    let n = 0;
    while (performance.now() - t0 < stressSeconds * 1000 - 3000) {
      await sleep(5000);
      const id = labelsToClick[n++ % labelsToClick.length];
      const c0 = Date.now();
      await sp.click(`.controller-label[data-control="${id}"]`, {timeout: 5000});
      const w = await waitFor(sp, title => !document.getElementById('controllerCard').hidden && document.getElementById('controllerTitle').textContent === title, titles[id], 5000);
      clicks.push({id, clickToOpenMs: Date.now() - c0, ok: w.ok, atS: Math.round((performance.now() - t0) / 1000)});
      heapDuring.push(await heap(false));
    }
    await streamer;
    const elapsedS = (performance.now() - t0) / 1000;
    const stressPackets = sent - stressSent0;
    await sleep(1000);
    const heapAfter = await heap(true);
    const snapAfter = await snap();
    const pageStream = await sp.evaluate(() => ({...window.gateStream, live: document.getElementById('controllerLiveStatus').textContent}));
    check('1f: streamed 13 axes at 60 Hz for the duration', !streamErr && elapsedS >= stressSeconds - 0.5 && ticks >= 58 * stressSeconds, {elapsedS, ticks, axisPackets: stressPackets, hz: ticks / elapsedS, streamErr});
    check('1f: every click opened its card within 500 ms', clicks.length >= Math.floor(stressSeconds / 5) - 1 && clicks.every(c => c.ok && c.clickToOpenMs <= 500), clicks);
    check('1f: page still live after stress, no JS errors', pageStream.live === 'live' && B.errors.length === 0, {pageStream, errors: B.errors});
    const growth = heapAfter.JSHeapUsedSize - heapBefore.JSHeapUsedSize;
    check('1f: browser heap growth recorded (post-GC)', Number.isFinite(growth), {heapBefore, heapAfter, growthBytes: growth, heapDuring});
    check('1f: bridge dropped count recorded', Number.isInteger(snapAfter.dropped) && Number.isInteger(snapBefore.dropped),
      {bridgeDroppedBefore: snapBefore.dropped, bridgeDroppedAfter: snapAfter.dropped, bridgeDroppedDuringStress: snapAfter.dropped - snapBefore.dropped,
       pageDataEvents: pageStream.data_events, pageDroppedEvents: pageStream.dropped_events, pageDroppedCount: pageStream.dropped_count, clients: snapAfter.clients});
    await B.context.close();
    const endClients = await clientsReach(0, 3000);
    check('post: stress page closed -> clients 0', endClients.ok, endClients);
  } catch (e) {
    check('script error', false, String(e.stack || e));
  } finally {
    clearInterval(heartbeat);
    sock.close();
    await browser.close();
    fs.writeFileSync(path.join(out, 'live-results.json'), JSON.stringify({results, failed}, null, 2) + '\n');
    console.log(`SUMMARY ${results.filter(r => r.pass).length}/${results.length} PASS`);
    process.exitCode = failed ? 1 : 0;
  }
})();
