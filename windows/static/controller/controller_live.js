/* Lossy, browser-only observation. Event handlers update bounded latest state;
 * a single animation frame paints it. No editor or bridge writes live here.
 */
const ControllerLive = (() => {
  'use strict';
  const FOLLOW_KEY = 'steamdeck.controllerFollow';
  const FLASH_MS = 150, PAD_MS = 300;
  const RETRY_MIN = 250, RETRY_MAX = 8000;
  const TAGS = {tap: 'tap', long_press: 'hold', layer_2: 'L2', touch: 'touch', analog: 'analog'};
  const el = id => document.getElementById(id);
  const svg = (tag, attrs) => {
    const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    return node;
  };

  function create(map, art, labels, card) {
    const actions = new Map(), visuals = new Map();
    const pressed = new Set(), axes = new Map(), padSeen = new Map(), flashes = new Map();
    let visible = false, pageHidden = false, online = false, follow = false;
    let source = null, fetcher = null, retry = null, frame = null, expiry = null;
    let epoch = 0, seq = 0, retryDelay = RETRY_MIN, pendingFollow = null, painting = false;
    const enabled = () => visible && !document.hidden && !pageHidden;
    try { follow = localStorage.getItem(FOLLOW_KEY) === 'true'; } catch (_) { /* Optional preference. */ }

    for (const control of map.controls) {
      for (const [group, ids] of Object.entries(control.groups)) {
        for (const action of ids) actions.set(action, {control, group});
      }
      const tag = document.createElement('span');
      tag.className = 'controller-live-tag'; tag.hidden = true;
      labels.get(control.id).appendChild(tag);
      const group = svg('g', {class: 'controller-live-overlay', 'pointer-events': 'none', 'aria-hidden': 'true'});
      art.appendChild(group);
      const {x, y} = control.anchor;
      const visual = {tag, shape: art.querySelector(`[data-control="${control.id}"]`)};
      if (['stick', 'trackpad'].includes(control.kind)) {
        visual.dot = svg('circle', {'data-live-dot': control.id, cx: x, cy: y, r: 7, class: 'controller-live-dot'});
        visual.dot.style.opacity = control.kind === 'trackpad' ? '0' : '1';
        group.appendChild(visual.dot);
      } else if (control.kind === 'trigger') {
        group.appendChild(svg('rect', {x: x - 32, y: y + 4, width: 64, height: 8, rx: 3, class: 'controller-live-track'}));
        visual.bar = svg('rect', {'data-live-bar': control.id, x: x - 32, y: y + 4, width: 0, height: 8, rx: 3, class: 'controller-live-fill'});
        group.appendChild(visual.bar);
      } else if (control.kind === 'gyro') {
        visual.gyro = control.groups.analog.map((action, i) => {
          const cy = y - 25 + i * 24;
          const text = svg('text', {x: x - 48, y: cy + 4, class: 'controller-live-axis-label'});
          text.textContent = action.slice('GYRO_'.length).toLowerCase();
          group.appendChild(text);
          group.appendChild(svg('line', {x1: x + 1, y1: cy, x2: x + 43, y2: cy, class: 'controller-live-track'}));
          const dot = svg('circle', {'data-live-axis': action, cx: x + 22, cy, r: 3, class: 'controller-live-dot'});
          group.appendChild(dot);
          return dot;
        });
      }
      visuals.set(control.id, visual);
    }
    // The tile now carries the three named indicators instead of its old caption.
    for (const text of art.querySelectorAll('text')) if (text.textContent === 'GYRO') text.style.display = 'none';

    function normalized(action) {
      // Ranges arrive from the bridge already reflecting the live mapping, so
      // full travel here means full travel in Resolume, deadzone included.
      const range = map.axis_ranges[action];
      const value = Math.max(range.min, Math.min(range.max, axes.get(action) ?? range.rest)) - range.rest;
      const dead = range.deadzone || 0;
      const span = (value < 0 ? range.rest - range.min : range.max - range.rest) - dead;
      if (span <= 0) return 0;
      if (Math.abs(value) <= dead) return 0;
      return Math.sign(value) * (Math.abs(value) - dead) / span;
    }
    function paintSoon() {
      if (enabled() && frame === null && !painting) frame = requestAnimationFrame(paint);
    }
    function paint() {
      frame = null;
      if (!enabled()) return;
      painting = true;
      const now = performance.now();
      clearTimeout(expiry); expiry = null;
      if (pendingFollow && follow) {
        if (!card.hasUnsavedEdit() && card.currentControl() !== pendingFollow) card.openControl(pendingFollow);
      }
      pendingFollow = null;
      el('controllerFollow').textContent = follow ? 'Follow: on' : 'Follow: off';
      el('controllerFollow').setAttribute('aria-pressed', String(follow));
      el('controllerFollowNote').hidden = !(follow && card.hasUnsavedEdit());
      el('controllerLiveStatus').textContent = online ? 'live' : 'offline';
      el('controllerLiveStatus').classList.toggle('is-live', online);
      let nextExpiry = Infinity;
      for (const control of map.controls) {
        const visual = visuals.get(control.id);
        const groups = Object.keys(TAGS).filter(name => control.groups[name]?.some(id => pressed.has(id)));
        const down = groups.length > 0;
        visual.shape.classList.toggle('control-down', down);
        labels.get(control.id).classList.toggle('control-down', down);
        visual.tag.textContent = groups.map(name => TAGS[name]).join(' ');
        visual.tag.hidden = !down;
        const analog = control.groups.analog;
        if (visual.dot) {
          visual.dot.setAttribute('cx', control.anchor.x + normalized(analog[0]) * 30);
          visual.dot.setAttribute('cy', control.anchor.y - normalized(analog[1]) * 30);
          if (control.kind === 'trackpad') {
            const until = (padSeen.get(control.id) ?? -Infinity) + PAD_MS;
            visual.dot.style.opacity = now < until ? '1' : '0';
            if (now < until) nextExpiry = Math.min(nextExpiry, until);
          }
        }
        if (visual.bar) visual.bar.setAttribute('width', normalized(analog[0]) * 64);
        if (visual.gyro) visual.gyro.forEach((dot, i) => dot.setAttribute('cx', control.anchor.x + 22 + normalized(analog[i]) * 21));
      }
      for (const [action, until] of flashes) {
        if (until <= now) flashes.delete(action);
        else nextExpiry = Math.min(nextExpiry, until);
      }
      for (const row of el('controllerRows').querySelectorAll('[data-action]')) {
        row.classList.toggle('controller-midi-flash', flashes.has(row.dataset.action));
      }
      if (Number.isFinite(nextExpiry)) expiry = setTimeout(paintSoon, Math.max(1, nextExpiry - now));
      painting = false;
    }
    function clearState() {
      pressed.clear(); axes.clear(); padSeen.clear(); flashes.clear(); pendingFollow = null;
      online = false;
    }
    function disconnect() {
      epoch++;
      source?.close(); source = null;
      fetcher?.abort(); fetcher = null;
    }
    function recover(immediate = false) {
      disconnect(); clearState(); paintSoon();
      if (!enabled()) return;
      clearTimeout(retry);
      retry = setTimeout(() => { retry = null; connect(); }, immediate ? 0 : retryDelay);
      if (!immediate) retryDelay = Math.min(RETRY_MAX, retryDelay * 2);
    }
    function receive(kind, event) {
      let data;
      try { data = JSON.parse(event.data); } catch (_) { recover(); return; }
      if (kind === 'dropped') { recover(true); return; }
      if (!Number.isSafeInteger(data.seq) || data.seq <= seq) return;
      seq = data.seq;
      const owner = actions.get(data.action);
      if (!owner) return; // Null/unattributed MIDI never flashes anything.
      if (kind === 'input') {
        if (data.state === 'down') {
          pressed.add(data.action);
          if (follow) pendingFollow = owner.control.id;
        } else if (data.state === 'up') pressed.delete(data.action);
      } else if (kind === 'axis' && map.axis_ranges[data.action] && Number.isFinite(data.value)) {
        axes.set(data.action, data.value);
        if (owner.control.kind === 'trackpad') padSeen.set(owner.control.id, performance.now());
      } else if (kind === 'midi' && (card.currentControl() === owner.control.id ||
          (follow && pendingFollow === owner.control.id && !card.hasUnsavedEdit()))) {
        flashes.set(data.action, performance.now() + FLASH_MS);
      }
      paintSoon();
    }
    async function connect() {
      if (!enabled()) return;
      const ticket = ++epoch;
      const abort = new AbortController(); fetcher = abort;
      try {
        const response = await fetch('/api/live/snapshot', {cache: 'no-store', signal: abort.signal});
        if (!response.ok) throw new Error('Snapshot unavailable');
        const snapshot = await response.json();
        if (ticket !== epoch || !enabled()) return;
        if (!Number.isSafeInteger(snapshot.seq) || !Array.isArray(snapshot.pressed) || !snapshot.axes) throw new Error('Invalid snapshot');
        clearState(); seq = snapshot.seq;
        for (const action of snapshot.pressed) if (actions.has(action)) pressed.add(action);
        for (const [action, value] of Object.entries(snapshot.axes)) {
          if (map.axis_ranges[action] && Number.isFinite(value)) axes.set(action, value);
        }
        // Snapshots have no axis ages. Never imply that an old pad position is a touch.
        paintSoon();
        const stream = new EventSource('/api/live/events?since=' + seq); source = stream;
        const current = () => ticket === epoch && enabled() && source === stream;
        stream.onopen = () => { if (current()) { online = true; retryDelay = RETRY_MIN; paintSoon(); } };
        stream.onerror = () => { if (current()) recover(); }; // Close native auto-retry; own one backoff timer.
        for (const kind of ['input', 'axis', 'midi', 'dropped']) {
          stream.addEventListener(kind, event => { if (current()) receive(kind, event); });
        }
      } catch (_) { if (ticket === epoch && enabled()) recover(); }
      finally { if (fetcher === abort) fetcher = null; }
    }
    function sync() {
      if (enabled()) {
        if (!source && !fetcher && retry === null) connect();
        paintSoon();
      } else {
        disconnect();
        clearTimeout(retry); retry = null;
        clearTimeout(expiry); expiry = null;
        if (frame !== null) cancelAnimationFrame(frame);
        frame = null;
        clearState();
        el('controllerLiveStatus').textContent = 'offline';
        el('controllerLiveStatus').classList.remove('is-live');
      }
    }
    el('controllerFollow').addEventListener('click', () => {
      follow = !follow; pendingFollow = null;
      try { localStorage.setItem(FOLLOW_KEY, String(follow)); } catch (_) { /* Optional preference. */ }
      paintSoon();
    });
    // Draft changes need only a preference-note repaint, never a card rebuild.
    for (const event of ['input', 'change']) el('controllerCard').addEventListener(event, paintSoon);
    document.addEventListener('visibilitychange', sync);
    window.addEventListener('pagehide', () => { pageHidden = true; sync(); });
    window.addEventListener('pageshow', () => { pageHidden = false; sync(); });
    return {setVisible(next) { visible = next; sync(); }, refresh: paintSoon};
  }
  return {create};
})();
