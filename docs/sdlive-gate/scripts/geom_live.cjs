// sdlive gate 1g: independent controller geometry with the LIVE view connected.
// Default Controller entry (no saved preference), waits for 23 labels AND the live
// indicator (never networkidle), then drives real UDP axes so stick dots, trigger bars
// and gyro dots are drawn, proves the stream is connected from the bridge snapshot, and
// measures label overlaps, leader crossings, endpoint-on-own-shape, glyph/label cover
// by leaders, arrowheads AND the live overlays, pane containment and hit-testing.
// node geom_live.cjs URL CHROMIUM OUTDIR [--mutation overlay-on-label|label-overlap]
const fs = require('node:fs');
const path = require('node:path');
const dgram = require('node:dgram');
const {chromium} = require(process.env.PLAYWRIGHT_CORE || '/Users/viddyslap/Documents/project-workspaces/life-os-showday/web-ui-server/node_modules/playwright-core');
const [url, executablePath, out, ...rest] = process.argv.slice(2);
const mutation = rest.includes('--mutation') ? rest[rest.indexOf('--mutation') + 1] : null;
const u = new URL(url);
if (u.hostname !== '127.0.0.1' || ['7723', '45123'].includes(u.port)) throw Error('unsafe url');
fs.mkdirSync(out, {recursive: true});
const results = [];
const check = (name, pass, detail) => { results.push({name, pass: !!pass, detail}); console.log(`${pass ? 'PASS' : 'FAIL'} ${name} ${JSON.stringify(detail)}`); };
const sleep = ms => new Promise(r => setTimeout(r, ms));

// Geometry helpers (page coordinates).
const boxesOverlap = (a, b) => a.x < b.r && b.x < a.r && a.y < b.b && b.y < a.b;
const orient = (p, q, s) => (q.x - p.x) * (s.y - p.y) - (q.y - p.y) * (s.x - p.x);
const same = (p, q) => Math.abs(p.x - q.x) < 0.01 && Math.abs(p.y - q.y) < 0.01;
function segsCross(a, b, c, d) {
  const d1 = orient(c, d, a), d2 = orient(c, d, b), d3 = orient(a, b, c), d4 = orient(a, b, d), e = 1e-6;
  if (((d1 > e && d2 < -e) || (d1 < -e && d2 > e)) && ((d3 > e && d4 < -e) || (d3 < -e && d4 > e))) return true;
  const on = (p, q, s) => Math.abs(orient(p, q, s)) <= e && Math.min(p.x, q.x) - e <= s.x && s.x <= Math.max(p.x, q.x) + e && Math.min(p.y, q.y) - e <= s.y && s.y <= Math.max(p.y, q.y) + e;
  return on(c, d, a) || on(c, d, b) || on(a, b, c) || on(a, b, d);
}
const inBox = (p, r) => p.x >= r.x && p.x <= r.r && p.y >= r.y && p.y <= r.b;
function segHitsBox(a, b, r) {
  if (inBox(a, r) || inBox(b, r)) return true;
  const c = [{x: r.x, y: r.y}, {x: r.r, y: r.y}, {x: r.r, y: r.b}, {x: r.x, y: r.b}];
  return c.some((p, i) => segsCross(a, b, p, c[(i + 1) % 4]));
}
function polyHitsBox(poly, r) {
  if (poly.some((p, i) => segHitsBox(p, poly[(i + 1) % poly.length], r))) return true;
  const mid = {x: (r.x + r.r) / 2, y: (r.y + r.b) / 2};
  const s = poly.map((p, i) => orient(p, poly[(i + 1) % poly.length], mid));
  return s.every(v => v >= 0) || s.every(v => v <= 0);
}
function distToBoxEdge(p, r) {
  const edges = [[{x: r.x, y: r.y}, {x: r.r, y: r.y}], [{x: r.r, y: r.y}, {x: r.r, y: r.b}], [{x: r.r, y: r.b}, {x: r.x, y: r.b}], [{x: r.x, y: r.b}, {x: r.x, y: r.y}]];
  return Math.min(...edges.map(([a, b]) => {
    const L = (b.x - a.x) ** 2 + (b.y - a.y) ** 2, t = L ? Math.max(0, Math.min(1, ((p.x - a.x) * (b.x - a.x) + (p.y - a.y) * (b.y - a.y)) / L)) : 0;
    return Math.hypot(p.x - a.x - t * (b.x - a.x), p.y - a.y - t * (b.y - a.y));
  }));
}

async function measure(page) {
  return page.evaluate(() => {
    const bx = e => { const r = e.getBoundingClientRect(); return {x: r.left, y: r.top, r: r.right, b: r.bottom}; };
    const shown = e => { const cs = getComputedStyle(e); const r = e.getBoundingClientRect(); return cs.display !== 'none' && cs.visibility !== 'hidden' && Number(cs.opacity) > 0 && r.width > 0 && r.height > 0; };
    const pts = e => {
      const m = e.getScreenCTM(), t = (x, y) => { const p = new DOMPoint(x, y).matrixTransform(m); return {x: p.x, y: p.y}; };
      if (e.tagName.toLowerCase() === 'line') return [t(e.x1.baseVal.value, e.y1.baseVal.value), t(e.x2.baseVal.value, e.y2.baseVal.value)];
      return Array.from({length: e.points.numberOfItems}, (_, i) => { const p = e.points.getItem(i); return t(p.x, p.y); });
    };
    const header = bx(document.querySelector('header')), status = bx(document.querySelector('.statusbar')), pane = bx(document.getElementById('tab-editor'));
    pane.y = Math.max(pane.y, header.b, 0); pane.b = Math.min(pane.b, status.y, innerHeight); pane.x = Math.max(pane.x, 0); pane.r = Math.min(pane.r, innerWidth);
    const card = document.getElementById('controllerCard');
    return {
      pane, card: card.hidden ? null : bx(card),
      labels: [...document.querySelectorAll('.controller-label')].map(e => { const b = bx(e), hit = document.elementFromPoint((b.x + b.r) / 2, (b.y + b.b) / 2); return {id: e.dataset.control, box: b, topmost: !!hit && e.contains(hit), hit: hit && (hit.id || hit.className?.baseVal || hit.className || hit.tagName)}; }),
      shapes: [...document.querySelectorAll('.controller-art [data-control]')].map(e => ({id: e.dataset.control, box: bx(e)})),
      glyphs: [...document.querySelectorAll('.controller-art text')].filter(shown).map(e => ({text: e.textContent, box: bx(e), live: !!e.closest('.controller-live-overlay')})),
      leaders: [...document.querySelectorAll('.controller-arrow')].map(e => ({id: e.dataset.controlArrow, points: pts(e)})),
      heads: [...document.querySelectorAll('.controller-arrow-head')].map(e => ({id: e.dataset.controlHead, points: pts(e)})),
      overlays: [...document.querySelectorAll('.controller-live-overlay circle, .controller-live-overlay rect, .controller-live-overlay line')].filter(shown).map(e => ({
        what: e.getAttribute('data-live-dot') ? 'dot:' + e.getAttribute('data-live-dot') : e.getAttribute('data-live-bar') ? 'bar:' + e.getAttribute('data-live-bar') : e.getAttribute('data-live-axis') ? 'gyro:' + e.getAttribute('data-live-axis') : e.tagName + '.' + e.getAttribute('class'),
        owner: [...document.querySelectorAll('.controller-live-overlay')].indexOf(e.closest('.controller-live-overlay')), box: bx(e)})),
      scroll: [document.documentElement, document.body, document.getElementById('tab-editor'), document.querySelector('.controller-picture-scroll')].map(e => ({id: e.id || e.tagName, sw: e.scrollWidth, cw: e.clientWidth, sh: e.scrollHeight, ch: e.clientHeight, st: e.scrollTop, sl: e.scrollLeft})),
      live: document.getElementById('controllerLiveStatus').textContent,
      dots: Object.fromEntries([...document.querySelectorAll('[data-live-dot]')].map(e => [e.dataset.liveDot, [e.getAttribute('cx'), e.getAttribute('cy')]])),
      bars: Object.fromEntries([...document.querySelectorAll('[data-live-bar]')].map(e => [e.dataset.liveBar, e.getAttribute('width')]))};
  });
}

function assess(tag, g, controls) {
  const ids = controls.map(c => c.id).sort();
  for (const [k, arr] of [['labels', g.labels], ['shapes', g.shapes], ['leaders', g.leaders], ['heads', g.heads]])
    check(`${tag}.count-23-${k}`, arr.length === 23 && JSON.stringify(arr.map(x => x.id).sort()) === JSON.stringify(ids), arr.length);
  check(`${tag}.stream-live-with-overlays-drawn`, g.live === 'live' && Number(g.bars.r2) > 40 && Number(g.bars.l2) > 60 && g.dots.left_stick[0] !== '280' && g.dots.right_stick[0] !== '900', {live: g.live, dots: g.dots, bars: g.bars});
  const overlaps = [];
  g.labels.forEach((a, i) => g.labels.slice(i + 1).forEach(b => { if (boxesOverlap(a.box, b.box)) overlaps.push([a.id, b.id]); }));
  check(`${tag}.label-overlaps-zero`, overlaps.length === 0, overlaps);
  const segs = g.leaders.flatMap(l => l.points.slice(1).map((p, i) => ({id: l.id, a: l.points[i], b: p})));
  const crossings = [];
  segs.forEach((s, i) => segs.slice(i + 1).forEach(t => { if (s.id !== t.id && !(same(s.a, t.a) || same(s.a, t.b) || same(s.b, t.a) || same(s.b, t.b)) && segsCross(s.a, s.b, t.a, t.b)) crossings.push([s.id, t.id]); }));
  check(`${tag}.leader-crossings-zero`, crossings.length === 0, crossings);
  const badEnds = [];
  for (const l of g.leaders) {
    const shape = g.shapes.find(s => s.id === l.id), end = l.points.at(-1);
    const d = shape ? distToBoxEdge(end, shape.box) : Infinity;
    const others = g.shapes.filter(s => s.id !== l.id && inBox(end, s.box)).map(s => s.id);
    if (!(d <= 3) || others.length) badEnds.push({id: l.id, d, others});
  }
  check(`${tag}.endpoints-on-own-shape-edge`, badEnds.length === 0, badEnds);
  const glyphHits = [];
  for (const l of g.leaders) for (const gl of g.glyphs) {
    const head = g.heads.find(h => h.id === l.id);
    if (l.points.slice(1).some((p, i) => segHitsBox(l.points[i], p, gl.box)) || (head && polyHitsBox(head.points, gl.box))) glyphHits.push({leader: l.id, glyph: gl.text});
  }
  check(`${tag}.no-glyph-covered-by-leader-or-head`, glyphHits.length === 0, glyphHits);
  const overlayHits = [];
  for (const o of g.overlays) {
    for (const gl of g.glyphs.filter(x => !x.live)) if (boxesOverlap(o.box, gl.box)) overlayHits.push({overlay: o.what, glyph: gl.text});
    for (const lb of g.labels) if (boxesOverlap(o.box, lb.box)) overlayHits.push({overlay: o.what, label: lb.id});
    if (g.card && boxesOverlap(o.box, g.card)) overlayHits.push({overlay: o.what, card: true});
  }
  for (const gl of g.glyphs.filter(x => x.live)) for (const lb of g.labels) if (boxesOverlap(gl.box, lb.box)) overlayHits.push({liveText: gl.text, label: lb.id});
  check(`${tag}.live-overlays-cover-no-glyph-label-or-card`, overlayHits.length === 0, overlayHits);
  const overlayLeader = [];
  for (const o of g.overlays) for (const l of g.leaders) if (l.points.slice(1).some((p, i) => segHitsBox(l.points[i], p, o.box))) overlayLeader.push({overlay: o.what, leader: l.id});
  results.push({name: `${tag}.info.overlay-leader-contacts`, pass: true, detail: overlayLeader});
  const covered = g.labels.filter(l => !l.topmost).map(l => ({id: l.id, hit: l.hit}));
  check(`${tag}.labels-topmost-hit-test`, covered.length === 0, covered);
  const outside = g.labels.concat(g.shapes).filter(x => !inBox({x: x.box.x, y: x.box.y}, g.pane) || !inBox({x: x.box.r, y: x.box.b}, g.pane)).map(x => x.id);
  check(`${tag}.labels-and-shapes-inside-pane`, outside.length === 0, outside);
  if (g.card) {
    check(`${tag}.card-inside-pane`, inBox({x: g.card.x, y: g.card.y}, g.pane) && inBox({x: g.card.r, y: g.card.b}, g.pane), g.card);
    const underCard = g.labels.filter(l => boxesOverlap(l.box, g.card)).map(l => l.id);
    check(`${tag}.no-label-under-card`, underCard.length === 0, underCard);
  }
  check(`${tag}.no-page-or-pane-scroll`, g.scroll.every(s => s.sw <= s.cw + 1 && s.sh <= s.ch + 1 && s.st === 0 && s.sl === 0), g.scroll);
}

(async () => {
  const browser = await chromium.launch({executablePath, headless: true});
  const sock = dgram.createSocket('udp4');
  const settings = await (await fetch(url + '/api/settings')).json();
  const [host, port] = settings.listen.split(':');
  if (host !== '127.0.0.1' || Number(port) === 45123) throw Error('unsafe listen');
  let seq = 0;
  const send = o => new Promise((res, rej) => { const b = {...o, seq: ++seq}; sock.send(Buffer.from(JSON.stringify(Object.fromEntries(Object.keys(b).sort().map(k => [k, b[k]])))), Number(port), host, e => e ? rej(e) : res()); });
  const hb = setInterval(() => send({kind: 'heartbeat'}).catch(() => {}), 100);
  const samples = [];
  try {
    const controls = (await (await fetch(url + '/api/controller-map')).json()).controls;
    for (const [w, h] of [[1440, 900], [1024, 768]]) {
      const context = await browser.newContext({viewport: {width: w, height: h}});
      const page = await context.newPage();
      page.on('pageerror', e => check(`${w}x${h}.page-error`, false, e.message));
      await page.goto(url, {waitUntil: 'domcontentloaded'});
      await page.waitForFunction(() => document.querySelectorAll('.controller-label').length === 23 && document.getElementById('controllerLiveStatus').textContent === 'live', null, {timeout: 10000});
      const drive = async () => {
        await send({kind: 'axis', action: 'L_STICK_X_AXIS', value: 23085}); await send({kind: 'axis', action: 'L_STICK_Y_AXIS', value: 22863});
        await send({kind: 'axis', action: 'R_STICK_X_AXIS', value: 32487}); await send({kind: 'axis', action: 'R_STICK_Y_AXIS', value: -32432});
        await send({kind: 'axis', action: 'L_TRIGGER_PRESSURE', value: 65535}); await send({kind: 'axis', action: 'R_TRIGGER_PRESSURE', value: 45875});
        await send({kind: 'axis', action: 'GYRO_PITCH', value: 32767}); await send({kind: 'axis', action: 'GYRO_YAW', value: -32767});
      };
      await drive();
      const settle = async () => { await page.waitForFunction(() => Number(document.querySelector('[data-live-bar="r2"]').getAttribute('width')) > 40, null, {timeout: 3000}); await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))); };
      await settle();
      const clients = (await (await fetch(url + '/api/live/snapshot', {cache: 'no-store'})).json()).clients;
      check(`${w}x${h}.bridge-snapshot-one-live-client`, clients === 1, {clients});
      const states = [['closed', null], ['open-btn_a', 'btn_a'], ['open-left_stick', 'left_stick'], ['open-r2', 'r2']];
      for (const [name, id] of states) {
        if (id) { await page.click(`.controller-label[data-control="${id}"]`); await page.waitForFunction(() => !document.getElementById('controllerCard').hidden); }
        await drive(); await settle();
        if (mutation === 'overlay-on-label' && name === 'closed') await page.evaluate(() => {
          const lab = document.querySelector('.controller-label[data-control="btn_a"]').getBoundingClientRect(), dot = document.querySelector('[data-live-dot="right_stick"]');
          const m = dot.getScreenCTM().inverse(), p = new DOMPoint((lab.left + lab.right) / 2, (lab.top + lab.bottom) / 2).matrixTransform(m);
          dot.setAttribute('cx', p.x); dot.setAttribute('cy', p.y);
        });
        if (mutation === 'label-overlap' && name === 'closed') await page.evaluate(() => {
          const a = document.querySelector('.controller-label[data-control="btn_a"]'), b = document.querySelector('.controller-label[data-control="btn_b"]');
          b.style.left = a.style.left; b.style.top = a.style.top;
        });
        const g = await measure(page);
        samples.push({tag: `${w}x${h}.${name}`, ...g});
        assess(`${w}x${h}.${name}`, g, controls);
        await page.screenshot({path: path.join(out, `geom-${w}x${h}-${name}.png`)});
        if (mutation) break;
      }
      await context.close();
      if (mutation) break;
    }
  } catch (e) { check('script-error', false, String(e.stack || e)); }
  finally {
    clearInterval(hb); sock.close(); await browser.close();
    fs.writeFileSync(path.join(out, 'geom-live.json'), JSON.stringify({results, samples}, null, 1));
    const failed = results.filter(r => !r.pass).length;
    console.log(`SUMMARY ${results.length - failed}/${results.length} PASS`);
    process.exitCode = failed || !results.length ? 1 : 0;
  }
})();
