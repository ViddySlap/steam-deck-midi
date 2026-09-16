#!/usr/bin/env node
// sdpolish gate: INDEPENDENT controller-view geometry detector.
//
// Written for the gate. It shares no code with tests/ui_controller_geometry.cjs:
// the DOM extraction, the geometry maths, the criteria and the output format are
// all implemented here from the app's own source (controller_map.json,
// controller_view.js, controller_live.js, protocol/messages.py).
//
// Usage:
//   node gate_geometry.cjs URL CHROMIUM LISTEN_HOST:PORT --out DIR [--single-process]
//        [--only-viewport WxH] [--closed-only]
//
// Exit 0 when every assertion passes, 1 when any fails, 2 on a harness error
// (browser launch, lost live stream, missing elements). A harness error is never
// geometry credit.

'use strict';

const fs = require('node:fs');
const path = require('node:path');
const dgram = require('node:dgram');

const PW = process.env.PLAYWRIGHT_CORE
  || '/Users/viddyslap/Documents/project-workspaces/life-os-showday/web-ui-server/node_modules/playwright-core';
const {chromium} = require(PW);

const CLEARANCE_FLOOR = 6.0;   // criterion c
const OWN_EDGE_TOL = 3.0;      // sdfix: endpoint at its own shape edge
const TOUCH_EPS = 1e-9;        // criterion b: "intersects or touches (distance 0)"
const VIEWPORTS = [[1024, 768], [1366, 768], [1440, 900], [1920, 1080]];

// ---------------------------------------------------------------- geometry --
// All maths below is this file's own. Boxes are {x, y, right, bottom}.

function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }

function pointSegDistance(p, a, b) {
  const vx = b.x - a.x, vy = b.y - a.y;
  const len2 = vx * vx + vy * vy;
  if (len2 === 0) return Math.hypot(p.x - a.x, p.y - a.y);
  const t = clamp(((p.x - a.x) * vx + (p.y - a.y) * vy) / len2, 0, 1);
  return Math.hypot(p.x - (a.x + t * vx), p.y - (a.y + t * vy));
}

function orient(a, b, c) {
  return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
}

function onSeg(a, b, p) {
  return Math.min(a.x, b.x) - TOUCH_EPS <= p.x && p.x <= Math.max(a.x, b.x) + TOUCH_EPS
      && Math.min(a.y, b.y) - TOUCH_EPS <= p.y && p.y <= Math.max(a.y, b.y) + TOUCH_EPS;
}

function segsIntersect(a, b, c, d) {
  const o1 = orient(a, b, c), o2 = orient(a, b, d);
  const o3 = orient(c, d, a), o4 = orient(c, d, b);
  if (((o1 > 0) !== (o2 > 0)) && ((o3 > 0) !== (o4 > 0))) return true;
  if (Math.abs(o1) <= TOUCH_EPS && onSeg(a, b, c)) return true;
  if (Math.abs(o2) <= TOUCH_EPS && onSeg(a, b, d)) return true;
  if (Math.abs(o3) <= TOUCH_EPS && onSeg(c, d, a)) return true;
  if (Math.abs(o4) <= TOUCH_EPS && onSeg(c, d, b)) return true;
  return false;
}

// Exact minimum distance between two closed segments. 0 when they cross or touch.
function segSegDistance(a, b, c, d) {
  if (segsIntersect(a, b, c, d)) return 0;
  return Math.min(
    pointSegDistance(a, c, d), pointSegDistance(b, c, d),
    pointSegDistance(c, a, b), pointSegDistance(d, a, b),
  );
}

function boxEdges(box) {
  const tl = {x: box.x, y: box.y}, tr = {x: box.right, y: box.y};
  const br = {x: box.right, y: box.bottom}, bl = {x: box.x, y: box.bottom};
  return [[tl, tr], [tr, br], [br, bl], [bl, tl]];
}

function pointInBox(p, box) {
  return p.x >= box.x - TOUCH_EPS && p.x <= box.right + TOUCH_EPS
      && p.y >= box.y - TOUCH_EPS && p.y <= box.bottom + TOUCH_EPS;
}

// Minimum distance from a segment to a filled box. 0 when it enters or touches it.
function segBoxDistance(a, b, box) {
  if (pointInBox(a, box) || pointInBox(b, box)) return 0;
  let best = Infinity;
  for (const [p, q] of boxEdges(box)) best = Math.min(best, segSegDistance(a, b, p, q));
  return best;
}

function boxesOverlap(u, v) {
  return u.x < v.right - TOUCH_EPS && v.x < u.right - TOUCH_EPS
      && u.y < v.bottom - TOUCH_EPS && v.y < u.bottom - TOUCH_EPS;
}

function boxInside(inner, outer, tol) {
  const t = tol || 0;
  return inner.x >= outer.x - t && inner.right <= outer.right + t
      && inner.y >= outer.y - t && inner.bottom <= outer.bottom + t;
}

// A polyline's ordered segments. Bends are the shared endpoints, so a segment
// list covers "segment, bend" for both criterion b and criterion c.
function polySegments(points) {
  const out = [];
  for (let i = 0; i + 1 < points.length; i += 1) out.push([points[i], points[i + 1]]);
  return out;
}

// A polygon arrowhead: its closed edges.
function polyClosedSegments(points) {
  const out = polySegments(points);
  if (points.length > 2) out.push([points[points.length - 1], points[0]]);
  return out;
}

// ------------------------------------------------------------- UDP driving --
// protocol/messages.py: one JSON object per datagram, no framing.

function makeDriver(host, port) {
  const sock = dgram.createSocket('udp4');
  let seq = 0;
  const send = (obj) => {
    seq += 1;
    const buf = Buffer.from(JSON.stringify(Object.assign({seq}, obj)), 'utf8');
    sock.send(buf, port, host);
  };
  const axis = (action, value) => send({kind: 'axis', action, value});
  // Values chosen so every overlay is visibly off its rest position:
  // sticks pushed, both triggers well past zero, pads touched, gyro off centre.
  const frame = () => {
    axis('L_STICK_X_AXIS', 22000); axis('L_STICK_Y_AXIS', -18000);
    axis('R_STICK_X_AXIS', -21000); axis('R_STICK_Y_AXIS', 19000);
    axis('L_TRIGGER_PRESSURE', 45000); axis('R_TRIGGER_PRESSURE', 61000);
    axis('L_PAD_X_POS', 16000); axis('L_PAD_Y_POS', -14000);
    axis('R_PAD_X_POS', -17000); axis('R_PAD_Y_POS', 15000);
    axis('GYRO_PITCH', 20000); axis('GYRO_YAW', -22000); axis('GYRO_ROLL', 24000);
    send({kind: 'heartbeat'});
  };
  frame();
  const timer = setInterval(frame, 120);
  return {stop: () => { clearInterval(timer); sock.close(); }, frame};
}

// ------------------------------------------------------- in-page extraction --
// Returns raw numbers only. No criterion is decided in the page.

const EXTRACT = () => {
  const scene = document.querySelector('svg.controller-scene');
  const m = scene.getScreenCTM();
  const toScreen = (x, y) => ({x: m.a * x + m.c * y + m.e, y: m.b * x + m.d * y + m.f});
  const parsePoints = (el) => {
    const raw = (el.getAttribute('points') || '').trim();
    if (!raw) return [];
    const nums = raw.split(/[\s,]+/).map(Number);
    const pts = [];
    for (let i = 0; i + 1 < nums.length; i += 2) pts.push(toScreen(nums[i], nums[i + 1]));
    return pts;
  };
  const rect = (el) => {
    const r = el.getBoundingClientRect();
    return {x: r.x, y: r.y, right: r.right, bottom: r.bottom};
  };

  const labels = [...document.querySelectorAll('button.controller-label')].map((el) => ({
    id: el.dataset.control, box: rect(el), text: el.textContent.trim(),
  }));

  const shapes = {};
  for (const el of document.querySelectorAll('.controller-art [data-control]')) {
    if (el.classList.contains('controller-arrow-hit')) continue;
    shapes[el.dataset.control] = rect(el);
  }

  const leaders = {};
  for (const el of document.querySelectorAll('polyline.controller-arrow')) {
    leaders[el.dataset.controlArrow] = parsePoints(el);
  }
  const heads = {};
  for (const el of document.querySelectorAll('polygon.controller-arrow-head')) {
    heads[el.dataset.controlHead] = parsePoints(el);
  }

  // Live overlays, attributed by the group each element was appended to
  // (controller_live.js builds one <g class="controller-live-overlay"> per control).
  const live = [];
  for (const g of document.querySelectorAll('g.controller-live-overlay')) {
    const dot = g.querySelector('[data-live-dot]');
    const bar = g.querySelector('[data-live-bar]');
    const ax = g.querySelector('[data-live-axis]');
    let owner = null;
    if (dot) owner = dot.dataset.liveDot;
    else if (bar) owner = bar.dataset.liveBar;
    else if (ax) owner = 'gyro';
    if (!owner) continue;
    const parts = [];
    for (const el of g.children) {
      const cls = el.getAttribute('class') || '';
      let kind = null;
      if (el.hasAttribute('data-live-dot')) kind = 'dot';
      else if (el.hasAttribute('data-live-bar')) kind = 'bar';
      else if (el.hasAttribute('data-live-axis')) kind = 'axisdot';
      else if (cls.includes('controller-live-track')) kind = 'track';
      else if (cls.includes('controller-live-axis-label')) kind = 'axislabel';
      if (!kind) continue;
      const opacity = Number(getComputedStyle(el).opacity);
      parts.push({
        kind, box: rect(el), opacity,
        cx: el.hasAttribute('cx') ? Number(el.getAttribute('cx')) : null,
        width: el.hasAttribute('width') ? Number(el.getAttribute('width')) : null,
      });
    }
    live.push({owner, parts});
  }

  const cardEl = document.getElementById('controllerCard');
  const cardOpen = !!cardEl && !cardEl.hidden;
  let card = null;
  if (cardOpen) {
    const titleEl = cardEl.querySelector('h2');
    const tabsEl = cardEl.querySelector('.controller-tabs');
    const rowEls = [...cardEl.querySelectorAll('#controllerRows .controller-row')];
    const r = cardEl.getBoundingClientRect();
    card = {
      box: rect(cardEl),
      // The visible area: the border box less the scrollbar-free content the
      // user can actually see without scrolling the card itself.
      view: {x: r.x, y: r.y, right: r.x + cardEl.clientWidth + (r.width - cardEl.clientWidth), bottom: r.y + cardEl.clientHeight},
      scrollTop: cardEl.scrollTop,
      scrollHeight: cardEl.scrollHeight,
      clientHeight: cardEl.clientHeight,
      title: titleEl ? rect(titleEl) : null,
      titleText: titleEl ? titleEl.textContent.trim() : null,
      tabs: tabsEl ? rect(tabsEl) : null,
      rowCount: rowEls.length,
      rows: rowEls.slice(0, 2).map((el) => ({
        box: rect(el), text: el.textContent.trim().slice(0, 60),
      })),
    };
  }

  const pane = rect(document.getElementById('controllerView'));
  const status = document.getElementById('controllerLiveStatus');

  return {
    labels, shapes, leaders, heads, live, card, cardOpen, pane,
    liveText: status ? status.textContent.trim() : null,
    liveClass: status ? status.className : null,
    pageScroll: {
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
      scrollHeight: document.documentElement.scrollHeight,
      clientHeight: document.documentElement.clientHeight,
    },
  };
};

// ---------------------------------------------------------------- criteria --

function evaluate(tag, g, viewportName, results) {
  const pass = (name, detail) => results.push({tag, name, ok: true, detail});
  const fail = (name, detail) => results.push({tag, name, ok: false, detail});
  const ids = g.labels.map((l) => l.id);

  // Live-stream credit. Without it every obstacle criterion below is vacuous.
  const dotsMoved = g.live.filter((L) => L.parts.some((p) => p.kind === 'dot' && p.cx !== null
    && Math.abs(p.cx) > 0)).length;
  const barsNonZero = g.live.filter((L) => L.parts.some((p) => p.kind === 'bar' && p.width > 0)).length;
  const axisDots = g.live.filter((L) => L.parts.some((p) => p.kind === 'axisdot')).length;
  if (g.liveText === 'live' && barsNonZero >= 2 && dotsMoved >= 2 && axisDots >= 1) {
    pass('stream-live-with-overlays-drawn', {liveText: g.liveText, barsNonZero, dotsMoved, axisDots});
  } else {
    fail('stream-live-with-overlays-drawn', {liveText: g.liveText, barsNonZero, dotsMoved, axisDots});
  }

  // sdfix: 23 labels, each with a shape, a leader and an arrowhead.
  if (ids.length === 23) pass('labels-23', {count: 23});
  else fail('labels-23', {count: ids.length});
  const missing = ids.filter((id) => !g.shapes[id] || !g.leaders[id] || !g.heads[id]);
  if (missing.length === 0) pass('every-label-has-shape-leader-head', {});
  else fail('every-label-has-shape-leader-head', {missing});

  // sdfix: no two label boxes overlap.
  const labelHits = [];
  for (let i = 0; i < g.labels.length; i += 1) {
    for (let j = i + 1; j < g.labels.length; j += 1) {
      if (boxesOverlap(g.labels[i].box, g.labels[j].box)) labelHits.push([g.labels[i].id, g.labels[j].id]);
    }
  }
  if (labelHits.length === 0) pass('label-overlaps', []); else fail('label-overlaps', labelHits);

  // sdfix: each leader's far endpoint sits on its OWN shape's boundary.
  const edgeBad = [];
  for (const id of ids) {
    const pts = g.leaders[id]; const shape = g.shapes[id];
    if (!pts || pts.length < 2 || !shape) continue;
    const end = pts[pts.length - 1];
    let d = Infinity;
    for (const [p, q] of boxEdges(shape)) d = Math.min(d, pointSegDistance(end, p, q));
    if (d > OWN_EDGE_TOL) edgeBad.push({id, distance: d});
  }
  if (edgeBad.length === 0) pass('own-edge-3px', {}); else fail('own-edge-3px', edgeBad);

  // sdfix: no two leaders' segments intersect.
  const crossings = [];
  for (let i = 0; i < ids.length; i += 1) {
    for (let j = i + 1; j < ids.length; j += 1) {
      const A = polySegments(g.leaders[ids[i]] || []);
      const B = polySegments(g.leaders[ids[j]] || []);
      let hit = false;
      for (const [a, b] of A) for (const [c, d] of B) if (segsIntersect(a, b, c, d)) hit = true;
      if (hit) crossings.push([ids[i], ids[j]]);
    }
  }
  if (crossings.length === 0) pass('leader-intersections', []); else fail('leader-intersections', crossings);

  // CRITERION b: no leader part through or touching ANOTHER control's shape,
  // live trigger track or live bar.
  const obstacles = [];
  for (const id of ids) if (g.shapes[id]) obstacles.push({owner: id, what: 'shape', box: g.shapes[id]});
  for (const L of g.live) {
    for (const p of L.parts) {
      if (p.kind === 'track') obstacles.push({owner: L.owner, what: 'track', box: p.box});
      if (p.kind === 'bar' && p.width > 0) obstacles.push({owner: L.owner, what: 'bar', box: p.box});
    }
  }
  const bHits = [];
  for (const id of ids) {
    const parts = polySegments(g.leaders[id] || []).map((s) => ['segment', s])
      .concat(polyClosedSegments(g.heads[id] || []).map((s) => ['arrowhead', s]));
    for (const [part, [a, b]] of parts) {
      for (const ob of obstacles) {
        if (ob.owner === id) continue;
        if (segBoxDistance(a, b, ob.box) <= TOUCH_EPS) {
          bHits.push({leader: id, part, hits: `${ob.owner}.${ob.what}`});
        }
      }
    }
  }
  if (bHits.length === 0) pass('b.no-leader-through-other-control', []);
  else fail('b.no-leader-through-other-control', bHits.slice(0, 12));

  // CRITERION b2: with a card open, no live overlay over the card or any label.
  if (g.cardOpen && g.card) {
    const b2 = [];
    const targets = [{what: 'card', box: g.card.box}]
      .concat(g.labels.map((l) => ({what: `label.${l.id}`, box: l.box})));
    for (const L of g.live) {
      for (const p of L.parts) {
        if (p.opacity === 0) continue;                 // a hidden pad dot draws nothing
        if (p.kind === 'bar' && p.width === 0) continue;
        for (const t of targets) {
          if (boxesOverlap(p.box, t.box)) b2.push({overlay: `${L.owner}.${p.kind}`, over: t.what});
        }
      }
    }
    if (b2.length === 0) pass('b2.no-live-overlay-over-card-or-label', []);
    else fail('b2.no-live-overlay-over-card-or-label', b2.slice(0, 12));
  }

  // CRITERION c: >= 6 px between any two DIFFERENT leaders' segments/bends/heads.
  let minD = Infinity, minPair = null;
  for (let i = 0; i < ids.length; i += 1) {
    const A = polySegments(g.leaders[ids[i]] || []).map((s) => ['segment', s])
      .concat(polyClosedSegments(g.heads[ids[i]] || []).map((s) => ['arrowhead', s]));
    for (let j = i + 1; j < ids.length; j += 1) {
      const B = polySegments(g.leaders[ids[j]] || []).map((s) => ['segment', s])
        .concat(polyClosedSegments(g.heads[ids[j]] || []).map((s) => ['arrowhead', s]));
      for (const [pa, [a, b]] of A) for (const [pb, [c, d]] of B) {
        const dist = segSegDistance(a, b, c, d);
        if (dist < minD) { minD = dist; minPair = [`${ids[i]}.${pa}`, `${ids[j]}.${pb}`]; }
      }
    }
  }
  const cDetail = {distance: minD, pair: minPair};
  if (minD >= CLEARANCE_FLOOR) pass('c.leader-clearance-6px', cDetail);
  else fail('c.leader-clearance-6px', cDetail);

  // CRITERION d: 1024x768 only, card open. Title, tabs and the first two action
  // rows (all rows if fewer) fully visible, with the card's own scrollTop at 0.
  if (viewportName === '1024x768' && g.cardOpen && g.card) {
    const c = g.card;
    const want = [['title', c.title], ['tabs', c.tabs]]
      .concat(c.rows.map((r, i) => [`row${i + 1}`, r.box]));
    const clipped = [];
    for (const [what, box] of want) {
      if (!box) { clipped.push({part: what, missing: true}); continue; }
      if (!boxInside(box, c.view, 0.5)) {
        clipped.push({
          part: what,
          overflowBottomPx: box.bottom - c.view.bottom,
          overflowRightPx: box.right - c.view.right,
          box,
        });
      }
    }
    const detail = {clipped, scrollTop: c.scrollTop, view: c.view, rows: c.rowCount};
    if (clipped.length === 0 && c.scrollTop === 0) pass('d.drawer-rows-visible', detail);
    else fail('d.drawer-rows-visible', detail);
  }

  // sdfix: the card stays inside the pane, and the page itself does not scroll.
  if (g.cardOpen && g.card) {
    if (boxInside(g.card.box, g.pane, 1.0)) pass('card-inside-pane', {});
    else fail('card-inside-pane', {card: g.card.box, pane: g.pane});
  }
  const ps = g.pageScroll;
  if (ps.scrollWidth <= ps.clientWidth + 1 && ps.scrollHeight <= ps.clientHeight + 1) {
    pass('no-page-scroll', ps);
  } else fail('no-page-scroll', ps);
}

// -------------------------------------------------------------------- main --

async function main() {
  const argv = process.argv.slice(2);
  const [url, chromiumPath, listen] = argv;
  const outDir = argv[argv.indexOf('--out') + 1];
  const singleProcess = argv.includes('--single-process');
  const closedOnly = argv.includes('--closed-only');
  const onlyViewport = argv.includes('--only-viewport') ? argv[argv.indexOf('--only-viewport') + 1] : null;
  if (!url || !chromiumPath || !listen || !outDir) {
    console.error('usage: gate_geometry.cjs URL CHROMIUM HOST:PORT --out DIR [--single-process] [--only-viewport WxH] [--closed-only]');
    process.exit(2);
  }
  fs.mkdirSync(outDir, {recursive: true});
  const [host, portStr] = listen.split(':');
  const driver = makeDriver(host, Number(portStr));

  const args = ['--no-sandbox', '--disable-gpu'];
  if (singleProcess) args.push('--single-process');

  const results = [];
  let harnessError = null;
  // One browser PER VIEWPORT: --single-process cannot serve a second page.
  for (const [w, h] of VIEWPORTS) {
    const vp = `${w}x${h}`;
    if (onlyViewport && onlyViewport !== vp) continue;
    if (harnessError) break;
    let browser;
    try {
      browser = await chromium.launch({executablePath: chromiumPath, args});
    } catch (err) {
      driver.stop();
      console.error(`HARNESS launch failed: ${err.message}`);
      process.exit(2);
    }
    try {
      const page = await browser.newPage({viewport: {width: w, height: h}});
      await page.goto(url, {waitUntil: 'domcontentloaded'});   // NEVER networkidle
      await page.waitForSelector('button.controller-label', {timeout: 30000});
      await page.waitForFunction(
        () => document.querySelectorAll('button.controller-label').length === 23,
        {timeout: 30000});
      await page.waitForFunction(
        () => (document.getElementById('controllerLiveStatus') || {}).textContent === 'live',
        {timeout: 30000});
      // Wait until the overlays have actually been painted off their rest values.
      await page.waitForFunction(() => {
        const bars = [...document.querySelectorAll('[data-live-bar]')];
        return bars.length >= 2 && bars.filter((b) => Number(b.getAttribute('width')) > 0).length >= 2;
      }, {timeout: 30000});

      const states = ['closed'];
      if (!closedOnly) {
        const ids = await page.$$eval('button.controller-label', (els) => els.map((e) => e.dataset.control));
        for (const id of ids) states.push(id);
      }
      for (const state of states) {
        if (state === 'closed') {
          await page.evaluate(() => {
            const c = document.getElementById('controllerCard');
            if (c && !c.hidden) document.querySelector('button.controller-label').click();
          });
          await page.evaluate(() => {
            const c = document.getElementById('controllerCard');
            if (c && !c.hidden) c.hidden = true;
          });
        } else {
          await page.click(`button.controller-label[data-control="${state}"]`);
          await page.waitForFunction(
            () => { const c = document.getElementById('controllerCard'); return c && !c.hidden; },
            {timeout: 10000});
        }
        driver.frame();
        await page.waitForTimeout(160);   // let one live paint land after the layout change
        const g = await page.evaluate(EXTRACT);
        const tag = `${vp}.${state === 'closed' ? 'closed' : `open-${state}`}`;
        evaluate(tag, g, vp, results);
      }
      await page.close();
    } catch (err) {
      harnessError = err.message;
    } finally {
      await browser.close();
    }
  }
  driver.stop();

  const failures = results.filter((r) => !r.ok);
  for (const r of results) {
    console.log(`${r.ok ? 'PASS' : 'FAIL'} ${r.tag}.${r.name} ${JSON.stringify(r.detail)}`);
  }
  fs.writeFileSync(path.join(outDir, 'results.json'),
    JSON.stringify({results, failures: failures.length, total: results.length, harnessError}, null, 1));
  if (harnessError) {
    console.error(`HARNESS error: ${harnessError}`);
    console.log(`SUMMARY ${results.length - failures.length}/${results.length} (INCOMPLETE)`);
    process.exit(2);
  }
  console.log(`SUMMARY ${results.length - failures.length}/${results.length} PASS failures=${failures.length}`);
  process.exit(failures.length === 0 ? 0 : 1);
}

main();
