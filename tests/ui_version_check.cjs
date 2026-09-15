// F4 header width cascade and the status-bar version label, DOM-free.
// Run: node tests/ui_version_check.cjs [path/to/index.html]
// Part 1 resolves the CSS `width` cascade over the shipped stylesheets for
// elements located in the shipped markup. Part 2 executes the shipped editor
// script's loadVersion() against a stubbed apiFetch. Real layout (one header
// row at 1440x900) is measured in a real browser by the gate.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const htmlPath = process.argv[2] || 'windows/static/index.html';
const staticDir = path.dirname(htmlPath);
const html = fs.readFileSync(htmlPath, 'utf8');
const results = [];
const check = (name, pass, detail = '') => {
  results.push({name, pass: Boolean(pass)});
  console.log(`${pass ? 'PASS' : 'FAIL'} ${name} ${JSON.stringify(detail)}`);
};

// ---- markup: element ancestry from the real HTML ----
const VOID = new Set(['area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr']);
function parseAttrs(text) {
  const attrs = {};
  for (const m of text.matchAll(/([a-zA-Z_:][-\w:.]*)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s>]+))?/g)) {
    attrs[m[1].toLowerCase()] = m[2] === undefined ? '' : m[2].replace(/^["']|["']$/g, '');
  }
  return attrs;
}
function parseMarkup(source) {
  const root = {tag: '#root', attrs: {}, parent: null};
  const byId = new Map();
  const links = [];
  const styles = [];
  let cur = root;
  const re = /<!--[\s\S]*?-->|<(\/?)([a-zA-Z][\w-]*)((?:[^>"']|"[^"]*"|'[^']*')*)>/g;
  let m;
  while ((m = re.exec(source))) {
    if (!m[2]) continue;
    const tag = m[2].toLowerCase();
    if (m[1]) {
      let n = cur;
      while (n && n.tag !== tag) n = n.parent;
      if (n && n.parent) cur = n.parent;
      continue;
    }
    const attrs = parseAttrs(m[3]);
    const el = {tag, attrs, parent: cur};
    if (attrs.id) byId.set(attrs.id, el);
    if (tag === 'link' && (attrs.rel || '').toLowerCase() === 'stylesheet') links.push(attrs.href);
    if (tag === 'script' || tag === 'style') {
      const end = source.indexOf(`</${tag}>`, re.lastIndex);
      if (tag === 'style') styles.push({order: m.index, text: source.slice(re.lastIndex, end)});
      re.lastIndex = end + tag.length + 3;
      continue;
    }
    if (!VOID.has(tag) && !m[3].trim().endsWith('/')) cur = el;
  }
  return {byId, links, styles};
}

// ---- stylesheets: rules with media conditions ----
function parseRules(css, sheet) {
  css = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const rules = [];
  function walk(text, media) {
    let i = 0;
    while (i < text.length) {
      const open = text.indexOf('{', i);
      if (open < 0) break;
      const prelude = text.slice(i, open).trim();
      let depth = 1, j = open + 1;
      while (j < text.length && depth) { if (text[j] === '{') depth++; else if (text[j] === '}') depth--; j++; }
      const body = text.slice(open + 1, j - 1);
      if (prelude.startsWith('@media')) walk(body, [...media, prelude.slice(6).trim()]);
      else if (!prelude.startsWith('@')) rules.push({sheet, selector: prelude, body, media});
      i = j;
    }
  }
  walk(css, []);
  return rules;
}
function mediaMatches(conditions, viewport) {
  return conditions.every(cond => cond.split(/\s+and\s+/).every(part => {
    const m = part.match(/\(\s*(max|min)-width\s*:\s*(\d+)px\s*\)/);
    if (!m) throw new Error(`unsupported media condition: ${part}`);
    return m[1] === 'max' ? viewport.width <= +m[2] : viewport.width >= +m[2];
  }));
}
function declarations(body, property) {
  const out = [];
  for (const decl of body.split(';')) {
    const idx = decl.indexOf(':');
    if (idx < 0) continue;
    if (decl.slice(0, idx).trim().toLowerCase() !== property) continue;
    const raw = decl.slice(idx + 1).trim();
    out.push({value: raw.replace(/\s*!important$/i, ''), important: /!important$/i.test(raw)});
  }
  return out;
}

// ---- selectors: type, #id, .class, [attr], [attr="v"], descendant and child ----
const DYNAMIC = /^:(hover|focus|focus-visible|focus-within|active|disabled|checked|visited)$|^::/;
function splitList(selector) {
  const parts = []; let depth = 0, start = 0;
  for (let i = 0; i < selector.length; i++) {
    if (selector[i] === '(') depth++; else if (selector[i] === ')') depth--;
    else if (selector[i] === ',' && !depth) { parts.push(selector.slice(start, i).trim()); start = i + 1; }
  }
  parts.push(selector.slice(start).trim());
  return parts;
}
function parseComplex(selector) {
  const tokens = selector.replace(/\s*([>+~])\s*/g, ' $1 ').trim().split(/\s+/);
  const steps = []; let combinator = ' ';
  for (const t of tokens) {
    if (t === '>' || t === '+' || t === '~') { combinator = t; continue; }
    const c = {tag: null, ids: [], classes: [], attrs: [], pseudo: [], unsupported: false, combinator};
    const re = /^(\*|[a-zA-Z][\w-]*)|#([\w-]+)|\.([\w-]+)|\[\s*([\w-]+)\s*(?:=\s*("[^"]*"|'[^']*'|[^\]\s]+))?\s*\]|(::?[\w-]+(?:\([^)]*\))?)/g;
    let consumed = 0, m;
    while ((m = re.exec(t)) && m.index === consumed) {
      consumed += m[0].length;
      if (m[1]) c.tag = m[1] === '*' ? null : m[1].toLowerCase();
      else if (m[2]) c.ids.push(m[2]);
      else if (m[3]) c.classes.push(m[3]);
      else if (m[4]) c.attrs.push([m[4].toLowerCase(), m[5] === undefined ? null : m[5].replace(/^["']|["']$/g, '')]);
      else c.pseudo.push(m[6]);
    }
    if (consumed !== t.length || combinator === '+' || combinator === '~') c.unsupported = true;
    if (c.pseudo.some(p => !DYNAMIC.test(p.replace(/\(.*$/, '')))) c.unsupported = true;
    steps.push(c); combinator = ' ';
  }
  return steps;
}
function compoundMatches(c, el) {
  if (!el || el.tag === '#root') return false;
  if (c.pseudo.length) return false; // a static, unfocused element in its resting state
  if (c.tag && c.tag !== el.tag) return false;
  if (c.ids.some(id => el.attrs.id !== id)) return false;
  const classes = (el.attrs.class || '').split(/\s+/);
  if (c.classes.some(k => !classes.includes(k))) return false;
  return c.attrs.every(([k, v]) => k in el.attrs && (v === null || el.attrs[k] === v));
}
function complexMatches(steps, el) {
  function from(i, node) {
    if (!compoundMatches(steps[i], node)) return false;
    if (i === 0) return true;
    if (steps[i].combinator === '>') return from(i - 1, node.parent);
    for (let p = node.parent; p && p.tag !== '#root'; p = p.parent) if (from(i - 1, p)) return true;
    return false;
  }
  return from(steps.length - 1, el);
}
function specificity(steps) {
  let a = 0, b = 0, c = 0;
  for (const s of steps) { a += s.ids.length; b += s.classes.length + s.attrs.length + s.pseudo.length; c += s.tag ? 1 : 0; }
  return [a, b, c];
}
function resolveWidth(el, rules, viewport, unsupported) {
  const candidates = [];
  rules.forEach((rule, order) => {
    if (!mediaMatches(rule.media, viewport)) return;
    const decls = declarations(rule.body, 'width');
    if (!decls.length) return;
    for (const selector of splitList(rule.selector)) {
      const steps = parseComplex(selector);
      const subject = steps[steps.length - 1];
      if (steps.some(s => s.unsupported)) {
        if (!subject.tag || subject.tag === el.tag) unsupported.add(`${rule.sheet}: ${selector}`);
        continue;
      }
      if (!complexMatches(steps, el)) continue;
      for (const d of decls) candidates.push({...d, spec: specificity(steps), order, selector, sheet: rule.sheet});
    }
  });
  for (const d of declarations(el.attrs.style || '', 'width')) candidates.push({...d, spec: [1e6, 0, 0], order: 1e9, selector: '[style]', sheet: 'inline'});
  candidates.sort((x, y) => (x.important - y.important) || (x.spec[0] - y.spec[0]) || (x.spec[1] - y.spec[1]) || (x.spec[2] - y.spec[2]) || (x.order - y.order));
  return candidates.length ? candidates[candidates.length - 1] : null;
}

const markup = parseMarkup(html);
const rules = [];
for (const style of markup.styles) rules.push(...parseRules(style.text, 'index.html <style>'));
for (const href of markup.links) {
  const file = path.join(staticDir, href.replace(/^\/static\//, ''));
  check(`stylesheet readable ${href}`, fs.existsSync(file), file);
  if (fs.existsSync(file)) rules.push(...parseRules(fs.readFileSync(file, 'utf8'), href));
}
check('rules observed', rules.length > 50, rules.length);

const expectations = [
  // [element id, expected width, why]
  ['sectionSelect', 'auto', 'F4: header section select sizes to content'],
  ['saveAsInput', '100%', 'save-as dialog text input keeps full width'],
  ['macroEditorType', '100%', 'macro editor select keeps full width'],
  ['searchInput', '100%', 'sidebar text input keeps full width'],
];
for (const viewport of [{width: 1440, height: 900}, {width: 1024, height: 768}]) {
  for (const [id, expected, why] of expectations) {
    const el = markup.byId.get(id);
    const tag = `${viewport.width}x${viewport.height}.${id}`;
    if (!el) { check(`${tag} element present`, false, why); continue; }
    const unsupported = new Set();
    const win = resolveWidth(el, rules, viewport, unsupported);
    check(`${tag} no unevaluable width selector could target <${el.tag}>`, unsupported.size === 0, [...unsupported]);
    check(`${tag} width ${expected} (${why})`, win && win.value === expected,
          win ? {value: win.value, selector: win.selector, sheet: win.sheet} : 'no width rule matched');
  }
}
const header = markup.byId.get('sectionSelect');
let inHeader = false;
for (let p = header && header.parent; p; p = p.parent) if (p.tag === 'header') inHeader = true;
check('sectionSelect is inside <header>', inHeader);

// ---- version label: the shipped loadVersion() ----
const source = html.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/\nloadAll\(\);\s*$/, '');
const elements = new Map();
const element = () => ({textContent: '', innerHTML: '', value: '', title: '', hidden: true, children: [], listeners: {},
  classList: {toggle() {}, add() {}, remove() {}}, addEventListener(n, h) { this.listeners[n] = h; },
  replaceChildren() { this.children = []; }, appendChild(c) { this.children.push(c); }, querySelectorAll() { return []; }});
const document = {getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
  createElement: element, querySelectorAll() { return []; }, addEventListener() {}};
const bootFetches = [];
const fetch = async p => {
  bootFetches.push(p);
  const body = p === '/api/version' ? {version: '0.0.0', git_commit: 'boot', build_time_utc: 'boot', frozen: false} : {};
  return {ok: p === '/api/version', status: p === '/api/version' ? 200 : 404, json: async () => body};
};
const context = vm.createContext({document, fetch, window: {confirm: () => false}, setInterval() {}, setTimeout() {}});
vm.runInContext(source, context);
(async () => {
  for (let i = 0; i < 10; i++) await new Promise(resolve => setImmediate(resolve));
  check('boot fetches /api/version', bootFetches.includes('/api/version'), bootFetches);
  check('boot renders the version label', document.getElementById('appVersion').textContent === 'v0.0.0 (source)',
        document.getElementById('appVersion').textContent);
  const cases = [
    [{version: '0.5.0', git_commit: 'source', build_time_utc: 'source', frozen: false}, 'v0.5.0 (source)', 'commit source, built source'],
    [{version: '0.5.0', git_commit: 'abc123', build_time_utc: '2026-09-15T00:00:00Z', frozen: true}, 'v0.5.0', 'commit abc123, built 2026-09-15T00:00:00Z'],
    [{fail: 'HTTP 404'}, '', null],
  ];
  const label = () => document.getElementById('appVersion');
  for (const [reply, text, title] of cases) {
    const calls = [];
    context.__reply = reply; context.__calls = calls;
    vm.runInContext(`apiFetch = async (p) => { __calls.push(p); if (__reply.fail) throw new Error(__reply.fail); return __reply; };`, context);
    label().textContent = 'stale'; label().title = '';
    await vm.runInContext('loadVersion()', context);
    const tag = reply.fail ? 'error' : `frozen=${reply.frozen}`;
    check(`version label ${tag} fetches /api/version`, JSON.stringify(calls) === JSON.stringify(['/api/version']), calls);
    check(`version label ${tag} text`, label().textContent === text, label().textContent);
    if (title !== null) check(`version label ${tag} title`, label().title === title, label().title);
  }
  const failed = results.filter(r => !r.pass);
  console.log(`SUMMARY ${results.length - failed.length}/${results.length} PASS`);
  process.exit(failed.length || !results.length ? 1 : 0);
})().catch(err => { console.log(`FAIL uncaught ${err.stack}`); process.exit(1); });
