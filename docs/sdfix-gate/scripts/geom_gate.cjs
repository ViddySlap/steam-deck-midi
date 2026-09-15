// sdfix gate: INDEPENDENT real-Chromium geometry of the controller view.
// Shares no code with tests/ui_controller_geometry.cjs. Written from the product DOM only.
// Usage: node geom_gate.cjs URL OUT_DIR VIEWPORTS(e.g. 1440x900,1024x768) [--extra-open id@WxH,...] [--png] [--label TAG]
// Page coordinates: SVG user points -> page via the scene <svg> getBoundingClientRect and its viewBox
// (preserveAspectRatio xMidYMid meet computed by hand; NOT getScreenCTM).
// Endpoint rule: distance from the leader's LAST point to the boundary of the SHAPE's own
// getBoundingClientRect (element with data-control=<id> inside svg.controller-art), never the label box.
const { chromium } = require('/Users/viddyslap/Documents/project-workspaces/life-os-showday/web-ui-server/node_modules/playwright-core');
const fs = require('fs');
const path = require('path');
const CHROMIUM = '/Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell';

const args = process.argv.slice(2);
const [URL, OUT, VPS] = args;
const flag = n => args.includes(n);
const opt = n => { const i = args.indexOf(n); return i > 0 ? args[i + 1] : null; };
const extraOpen = (opt('--extra-open') || '').split(',').filter(Boolean).map(s => { const [id, vp] = s.split('@'); return { id, vp }; });
const TAG = opt('--label') || 'after';
fs.mkdirSync(OUT, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));

// ---------- pure geometry ----------
const EPS = 1e-6;
const orient = (a, b, c) => (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
const onSeg = (a, b, c) => Math.min(a.x, b.x) - EPS <= c.x && c.x <= Math.max(a.x, b.x) + EPS && Math.min(a.y, b.y) - EPS <= c.y && c.y <= Math.max(a.y, b.y) + EPS;
function segsIntersect(p1, p2, p3, p4) {
  const d1 = orient(p3, p4, p1), d2 = orient(p3, p4, p2), d3 = orient(p1, p2, p3), d4 = orient(p1, p2, p4);
  if (((d1 > EPS && d2 < -EPS) || (d1 < -EPS && d2 > EPS)) && ((d3 > EPS && d4 < -EPS) || (d3 < -EPS && d4 > EPS))) return true;
  if (Math.abs(d1) <= EPS && onSeg(p3, p4, p1)) return true;
  if (Math.abs(d2) <= EPS && onSeg(p3, p4, p2)) return true;
  if (Math.abs(d3) <= EPS && onSeg(p1, p2, p3)) return true;
  if (Math.abs(d4) <= EPS && onSeg(p1, p2, p4)) return true;
  return false;
}
const same = (a, b) => Math.abs(a.x - b.x) < 1e-6 && Math.abs(a.y - b.y) < 1e-6;
const inRect = (p, r, inset = 0) => p.x > r.left + inset && p.x < r.right - inset && p.y > r.top + inset && p.y < r.bottom - inset;
function distToBoundary(p, r) {
  const dx = Math.max(r.left - p.x, 0, p.x - r.right), dy = Math.max(r.top - p.y, 0, p.y - r.bottom);
  if (dx > 0 || dy > 0) return Math.hypot(dx, dy);
  return Math.min(p.x - r.left, r.right - p.x, p.y - r.top, r.bottom - p.y);
}
function segHitsRect(a, b, r) {
  if (inRect(a, r) || inRect(b, r)) return true;
  const c = [{ x: r.left, y: r.top }, { x: r.right, y: r.top }, { x: r.right, y: r.bottom }, { x: r.left, y: r.bottom }];
  for (let i = 0; i < 4; i++) if (segsIntersect(a, b, c[i], c[(i + 1) % 4])) return true;
  return false;
}
function triHitsRect(t, r) {
  for (let i = 0; i < 3; i++) if (segHitsRect(t[i], t[(i + 1) % 3], r)) return true;
  const c = [{ x: r.left, y: r.top }, { x: r.right, y: r.top }, { x: r.right, y: r.bottom }, { x: r.left, y: r.bottom }];
  const inside = q => { const s1 = orient(t[0], t[1], q), s2 = orient(t[1], t[2], q), s3 = orient(t[2], t[0], q); return (s1 >= 0 && s2 >= 0 && s3 >= 0) || (s1 <= 0 && s2 <= 0 && s3 <= 0); };
  return c.some(inside);
}
const rectsOverlap = (a, b) => Math.min(a.right, b.right) - Math.max(a.left, b.left) > 0 && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 0;

// ---------- page sampling ----------
async function sample(page) {
  return page.evaluate(() => {
    const R = r => ({ left: r.left, top: r.top, right: r.right, bottom: r.bottom, width: r.width, height: r.height });
    const scene = document.querySelector('#controllerPicture svg.controller-scene');
    const art = scene.querySelector('svg.controller-art');
    const sr = scene.getBoundingClientRect();
    const vb = scene.viewBox.baseVal;
    const s = Math.min(sr.width / vb.width, sr.height / vb.height);
    const offX = sr.left + (sr.width - vb.width * s) / 2, offY = sr.top + (sr.height - vb.height * s) / 2;
    const toPage = str => str.trim().split(/\s+/).map(pair => { const [x, y] = pair.split(',').map(Number); return { x: offX + (x - vb.x) * s, y: offY + (y - vb.y) * s }; });
    const labels = [...document.querySelectorAll('#controllerPicture .controller-label')].map(l => {
      const r = l.getBoundingClientRect(); const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      const hit = document.elementFromPoint(cx, cy);
      return { id: l.dataset.control, text: l.querySelector('span')?.textContent, rect: R(r), centerHit: hit ? (hit === l || l.contains(hit)) : false,
        hitWhat: hit ? (hit.id || hit.className?.baseVal || hit.className || hit.tagName) : null };
    });
    // polyline leaders (HEAD) or <line> leaders (BASE of lap, marker-end heads)
    const arrows = [...scene.querySelectorAll('.controller-arrow')].map(a => {
      const pts = a.localName === 'line' ? ['x1', 'y1', 'x2', 'y2'].map(k => a.getAttribute(k)).reduce((s, v, i) => s + (i % 2 ? ',' : ' ') + v, '').trim() : (a.getAttribute('points') || '');
      return { id: a.getAttribute('data-control-arrow'), kind: a.localName, raw: pts, points: toPage(pts) };
    });
    const heads = [...scene.querySelectorAll('polygon.controller-arrow-head')].map(h => ({ id: h.getAttribute('data-control-head'), points: toPage(h.getAttribute('points') || '') }));
    const artRect = art.getBoundingClientRect();
    const shapes = [...art.querySelectorAll('[data-control]')].map(e => { const b = e.getBBox(); return { id: e.getAttribute('data-control'), rect: R(e.getBoundingClientRect()), bbox: { x: b.x, y: b.y, width: b.width, height: b.height } }; });
    const glyphs = [...art.querySelectorAll('text')].map(t => ({ text: t.textContent, rect: R(t.getBoundingClientRect()) }));
    const pane = document.getElementById('tab-editor');
    const card = document.getElementById('controllerCard');
    const status = document.querySelector('.statusbar');
    const se = document.scrollingElement;
    return { labels, arrows, heads, shapes, glyphs, artRect: R(artRect), paneRect: R(pane.getBoundingClientRect()), statusRect: R(status.getBoundingClientRect()),
      cardHidden: card.hidden, cardRect: R(card.getBoundingClientRect()), cardTitle: document.getElementById('controllerTitle').textContent,
      viewport: { w: innerWidth, h: innerHeight },
      scroll: { pageOverflow: se.scrollHeight - se.clientHeight, pageOverflowX: se.scrollWidth - se.clientWidth, paneOverflow: pane.scrollHeight - pane.clientHeight, winY: scrollY, paneTop: pane.scrollTop } };
  });
}

function analyse(g) {
  const labelOverlaps = [];
  for (let i = 0; i < g.labels.length; i++) for (let j = i + 1; j < g.labels.length; j++)
    if (rectsOverlap(g.labels[i].rect, g.labels[j].rect)) labelOverlaps.push([g.labels[i].id, g.labels[j].id]);
  const segs = g.arrows.flatMap(a => a.points.slice(1).map((p, k) => ({ id: a.id, a: a.points[k], b: p })));
  const crossings = [];
  for (let i = 0; i < segs.length; i++) for (let j = i + 1; j < segs.length; j++) {
    const s = segs[i], t = segs[j];
    if (s.id === t.id) continue;
    if (!segsIntersect(s.a, s.b, t.a, t.b)) continue;
    if (same(s.a, t.a) || same(s.a, t.b) || same(s.b, t.a) || same(s.b, t.b)) continue; // shared endpoint
    crossings.push([s.id, t.id]);
  }
  const shapeById = Object.fromEntries(g.shapes.map(s => [s.id, s]));
  const endpoints = g.arrows.map(a => {
    const end = a.points.at(-1); const own = shapeById[a.id];
    const d = own ? distToBoundary(end, own.rect) : Infinity;
    const insideOther = g.shapes.filter(s => s.id !== a.id && inRect(end, s.rect, 0.5)).map(s => s.id);
    return { id: a.id, end, dist: d, insideOther, pass: d <= 3 && insideOther.length === 0 };
  });
  const glyphHits = [];
  for (const a of g.arrows) {
    for (let k = 1; k < a.points.length; k++) for (const gl of g.glyphs) if (segHitsRect(a.points[k - 1], a.points[k], gl.rect)) glyphHits.push({ id: a.id, part: 'line', glyph: gl.text });
  }
  for (const h of g.heads) for (const gl of g.glyphs) if (h.points.length === 3 && triHitsRect(h.points, gl.rect)) glyphHits.push({ id: h.id, part: 'head', glyph: gl.text });
  const vp = { left: 0, top: 0, right: g.viewport.w, bottom: g.viewport.h };
  const within = (r, box) => r.left >= box.left - 0.5 && r.top >= box.top - 0.5 && r.right <= box.right + 0.5 && r.bottom <= box.bottom + 0.5;
  const hidden = [];
  for (const l of g.labels) {
    if (!within(l.rect, g.paneRect) || !within(l.rect, vp)) hidden.push({ id: l.id, why: 'outside pane/viewport' });
    if (!l.centerHit) hidden.push({ id: l.id, why: 'centre hit ' + l.hitWhat });
    if (rectsOverlap(l.rect, g.statusRect)) hidden.push({ id: l.id, why: 'overlaps status bar' });
  }
  for (const s of g.shapes) if (!within(s.rect, g.paneRect) || !within(s.rect, vp)) hidden.push({ id: s.id, why: 'shape outside pane/viewport' });
  const scrolled = g.scroll.pageOverflow > 0 || g.scroll.paneOverflow > 0 || g.scroll.winY !== 0 || g.scroll.paneTop !== 0 || g.scroll.pageOverflowX > 0;
  const ids = new Set(g.labels.map(l => l.id));
  return { labelCount: g.labels.length, uniqueLabelIds: ids.size, arrowCount: g.arrows.length, headCount: g.heads.length, shapeCount: g.shapes.length,
    labelOverlaps, crossings, endpointsPass: endpoints.filter(e => e.pass).length, endpointFails: endpoints.filter(e => !e.pass), maxEndpointDist: Math.max(...endpoints.map(e => e.dist)),
    glyphHits, hidden, scrolled, scroll: g.scroll, endpoints };
}

async function settle(page) {
  let prev = null;
  for (let i = 0; i < 40; i++) {
    await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
    const cur = await page.evaluate(() => [...document.querySelectorAll('.controller-arrow')].map(a => a.getAttribute('points') || a.getAttribute('x1') + a.getAttribute('x2')).join('|') + JSON.stringify([...document.querySelectorAll('.controller-label')].map(l => [l.style.left, l.style.top])));
    if (cur === prev && cur.length > 50) return;
    prev = cur; await sleep(80);
  }
}

(async () => {
  const launchOpts = { headless: true, executablePath: CHROMIUM };
  if (flag('--single-process')) launchOpts.args = ['--single-process'];
  const browser = await chromium.launch(launchOpts);
  const results = [];
  try {
    for (const vpStr of VPS.split(',')) {
      const [w, h] = vpStr.split('x').map(Number);
      const context = await browser.newContext({ viewport: { width: w, height: h } });
      const page = await context.newPage();
      page.on('dialog', d => d.dismiss());
      await page.goto(URL, { waitUntil: 'load' });
      await page.waitForFunction(() => document.querySelectorAll('#controllerPicture .controller-label').length > 0 && [...document.querySelectorAll('.controller-arrow')].every(a => a.localName === 'line' || a.getAttribute('points')), null, { timeout: 15000 });
      await settle(page);
      const record = async (state, png) => {
        await settle(page);
        const g = await sample(page);
        const an = analyse(g);
        results.push({ viewport: vpStr, state, cardTitle: g.cardHidden ? null : g.cardTitle, analysis: an, raw: g });
        if (png) await page.screenshot({ path: path.join(OUT, png) });
        const row = `${vpStr} ${state} labels=${an.labelCount} overlaps=${an.labelOverlaps.length} crossings=${an.crossings.length} endpoints=${an.endpointsPass}/${an.arrowCount} (max ${an.maxEndpointDist.toFixed(3)}px) glyphHits=${an.glyphHits.length} hidden=${an.hidden.length} scrolled=${an.scrolled}`;
        console.log(row);
        if (an.labelOverlaps.length) console.log('  overlaps', JSON.stringify(an.labelOverlaps));
        if (an.crossings.length) console.log('  crossings', JSON.stringify(an.crossings));
        if (an.endpointFails.length) console.log('  endpointFails', JSON.stringify(an.endpointFails.map(e => ({ id: e.id, dist: e.dist, insideOther: e.insideOther }))));
        if (an.glyphHits.length) console.log('  glyphHits', JSON.stringify(an.glyphHits));
        if (an.hidden.length) console.log('  hidden', JSON.stringify(an.hidden));
        if (an.scrolled) console.log('  scroll', JSON.stringify(an.scroll));
        return g;
      };
      const open = async id => {
        await page.click(`#controllerPicture .controller-label[data-control="${id}"]`);
        await page.waitForFunction(() => !document.getElementById('controllerCard').hidden, null, { timeout: 5000 });
        await settle(page);
      };
      await record('closed', flag('--png') ? `${TAG}-${vpStr}-card-closed.png` : null);
      if (flag('--closed-only')) { await context.close(); continue; }
      await open('btn_a');
      const g = await record('open-btn_a', flag('--png') ? `${TAG}-${vpStr}-card-open.png` : null);
      // nearest label to the card by rectangle gap; ties -> listed, first in DOM order opened
      const gap = (a, b) => Math.hypot(Math.max(b.left - a.right, a.left - b.right, 0), Math.max(b.top - a.bottom, a.top - b.bottom, 0));
      const dists = g.labels.map(l => ({ id: l.id, d: gap(l.rect, g.cardRect) }));
      const min = Math.min(...dists.map(x => x.d));
      const ties = dists.filter(x => Math.abs(x.d - min) < 0.5).map(x => x.id);
      const nearest = ties.find(id => id !== 'btn_a') || ties[0];
      console.log(`  nearest-to-card gap=${min.toFixed(2)} ties=${JSON.stringify(ties)} opening ${nearest}`);
      await open(nearest);
      await record(`open-nearest-${nearest}`, null);
      for (const e of extraOpen.filter(e => e.vp === vpStr && e.id !== nearest)) { await open(e.id); await record(`open-${e.id}`, null); }
      await context.close();
    }
  } finally {
    await browser.close();
  }
  fs.writeFileSync(path.join(OUT, `geometry-${TAG}.json`), JSON.stringify(results, null, 1));
  const bad = results.filter(r => { const a = r.analysis; return a.labelCount !== 23 || a.uniqueLabelIds !== 23 || a.labelOverlaps.length || a.crossings.length || a.endpointsPass !== 23 || a.glyphHits.length || a.hidden.length; });
  console.log(`GATE-GEOMETRY states=${results.length} bad=${bad.length}`);
  process.exit(bad.length ? 1 : 0);
})().catch(e => { console.error('RIG ERROR', e); process.exit(2); });
