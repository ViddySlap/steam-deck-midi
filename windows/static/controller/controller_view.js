/* The owned map supplies all control/action relations and drawing anchors.
 * Rows use page state, not persisted API rows: pending List edits stay visible.
 * V3 can mount scoped forms inside each .controller-row using data-action.
 */
const ControllerView = (() => {
  'use strict';
  const GROUP_ORDER = [['tap', 'TAP'], ['long_press', 'LONG PRESS'], ['layer_2', 'LAYER 2'], ['analog', 'ANALOG']];
  const STORAGE_KEY = 'steamdeck.mappingView';
  let map = null;
  let activeControl = null;
  let view = 'controller';
  let tab = 'editor';
  const labels = new Map();
  const arrows = new Map();
  const shapes = new Map();
  const el = id => document.getElementById(id);
  const svgElement = (tag, attrs = {}) => {
    const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, value);
    return node;
  };

  function setView(next, remember = true) {
    view = next === 'list' ? 'list' : 'controller';
    if (remember) {
      try { localStorage.setItem(STORAGE_KEY, view); } catch (_) { /* Storage may be disabled. */ }
    }
    el('controllerView').hidden = view !== 'controller';
    el('editorContent').hidden = view !== 'list';
    el('mappingSidebar').hidden = tab === 'editor' && view !== 'list';
    el('viewController').setAttribute('aria-pressed', String(view === 'controller'));
    el('viewList').setAttribute('aria-pressed', String(view === 'list'));
  }

  function tabChanged(name) { tab = name; setView(view, false); }

  function openControl(id) {
    if (!map?.controls.some(control => control.id === id)) return;
    activeControl = id;
    refresh();
    el('controllerTitle').focus();
  }

  function closeControl() {
    const previous = activeControl;
    activeControl = null;
    refresh();
    labels.get(previous)?.focus();
  }

  function openInList(action) {
    setView('list');
    selectAction(action);
  }

  function renderCard() {
    const control = map.controls.find(item => item.id === activeControl);
    el('controllerCard').hidden = !control;
    el('controllerRows').replaceChildren();
    if (!control) return;
    el('controllerTitle').textContent = control.label;
    for (const [key, title] of GROUP_ORDER) {
      if (!control.groups[key]) continue;
      const group = document.createElement('section');
      group.className = 'controller-group';
      group.dataset.group = key;
      const heading = document.createElement('h3');
      heading.textContent = title;
      group.appendChild(heading);
      for (const action of control.groups[key]) {
        const spec = state[action];
        const row = document.createElement('div');
        row.className = 'controller-row';
        row.dataset.action = action;
        const head = document.createElement('div');
        head.className = 'controller-row-head';
        const id = document.createElement('span');
        id.className = 'controller-action';
        id.textContent = action;
        head.appendChild(id);
        const badge = document.createElement('span');
        badge.className = `chip-badge ${mappingBadgeClass(spec)}`;
        badge.textContent = mappingBadge(spec) || 'unmapped';
        head.appendChild(badge);
        row.appendChild(head);
        const desc = document.createElement('p');
        desc.className = 'controller-description';
        desc.textContent = mappingDesc(spec);
        desc.title = desc.textContent;
        row.appendChild(desc);
        const link = document.createElement('button');
        link.className = 'btn btn-ghost btn-sm controller-open-list';
        link.textContent = 'Open in list';
        link.setAttribute('aria-label', `Open ${action} in list`);
        link.addEventListener('click', () => openInList(action));
        row.appendChild(link);
        group.appendChild(row);
      }
      el('controllerRows').appendChild(group);
    }
  }

  function refresh() {
    if (!map) return;
    for (const control of map.controls) {
      const ids = Object.values(control.groups).flat();
      const mapped = ids.filter(id => Boolean(state[id])).length;
      const label = labels.get(control.id);
      label.querySelector('small').textContent = `${mapped}/${ids.length}`;
      label.setAttribute('aria-label', `${control.label}: ${mapped} of ${ids.length} mapped`);
      label.setAttribute('aria-expanded', String(activeControl === control.id));
      for (const node of [label, arrows.get(control.id), shapes.get(control.id)]) {
        node.classList.toggle('control-unmapped', mapped === 0);
        node.classList.toggle('control-selected', activeControl === control.id);
      }
    }
    renderCard();
  }

  function draw(art) {
    const picture = el('controllerPicture');
    picture.replaceChildren();
    const [x, y, width, height] = map.scene_view_box;
    picture.style.aspectRatio = `${width} / ${height}`;
    const scene = svgElement('svg', {viewBox: map.scene_view_box.join(' '), class: 'controller-scene'});
    const defs = svgElement('defs');
    const marker = svgElement('marker', {id: 'controllerArrowHead', viewBox: '0 0 10 10', refX: 9, refY: 5,
      markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse'});
    marker.appendChild(svgElement('path', {d: 'M0 0 L10 5 L0 10 Z', fill: 'var(--text-mid)'}));
    defs.appendChild(marker);
    scene.appendChild(defs);
    art.setAttribute('x', map.view_box[0]);
    art.setAttribute('y', map.view_box[1]);
    art.setAttribute('width', map.view_box[2]);
    art.setAttribute('height', map.view_box[3]);
    art.setAttribute('class', 'controller-art');
    scene.appendChild(art);
    picture.appendChild(scene);
    for (const control of map.controls) {
      const shape = art.querySelector(`[data-control="${control.id}"]`);
      shape.addEventListener('click', () => openControl(control.id));
      shapes.set(control.id, shape);
      const {x: lx, y: ly} = control.label_anchor;
      const {x: ax, y: ay} = control.anchor;
      // The broad invisible stroke is a pointer target for the single visible arrow.
      const coords = {x1: lx, y1: ly, x2: ax, y2: ay};
      const arrow = svgElement('line', {...coords, class: 'controller-arrow', 'data-control-arrow': control.id,
        'marker-end': 'url(#controllerArrowHead)', 'pointer-events': 'none'});
      const hit = svgElement('line', {...coords, class: 'controller-arrow-hit', 'data-control': control.id});
      hit.addEventListener('click', () => openControl(control.id));
      scene.appendChild(arrow);
      scene.appendChild(hit);
      arrows.set(control.id, arrow);
      const label = document.createElement('button');
      label.className = 'controller-label';
      label.dataset.control = control.id;
      label.style.left = `${(lx - x) / width * 100}%`;
      label.style.top = `${(ly - y) / height * 100}%`;
      label.setAttribute('aria-controls', 'controllerCard');
      const name = document.createElement('span');
      name.textContent = control.label;
      label.appendChild(name);
      label.appendChild(document.createElement('small'));
      label.addEventListener('click', () => openControl(control.id));
      // Native buttons provide Enter/Space activation without a duplicate key handler.
      picture.appendChild(label);
      labels.set(control.id, label);
    }
    refresh();
  }

  async function init() {
    try { view = localStorage.getItem(STORAGE_KEY) === 'list' ? 'list' : 'controller'; } catch (_) { view = 'controller'; }
    setView(view, false);
    el('viewController').addEventListener('click', () => setView('controller'));
    el('viewList').addEventListener('click', () => setView('list'));
    el('controllerClose').addEventListener('click', closeControl);
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && activeControl && tab === 'editor' && view === 'controller') {
        event.preventDefault();
        closeControl();
      }
    });
    try {
      const [relation, response] = await Promise.all([
        apiFetch('/api/controller-map'), fetch('/static/controller/steam_deck.svg'),
      ]);
      if (!response.ok) throw new Error(`Artwork HTTP ${response.status}`);
      const doc = new DOMParser().parseFromString(await response.text(), 'image/svg+xml');
      if (doc.querySelector('parsererror') || doc.documentElement.localName !== 'svg') throw new Error('Invalid controller artwork');
      map = relation;
      draw(document.importNode(doc.documentElement, true));
    } catch (error) {
      map = null;
      el('controllerPicture').replaceChildren();
      const message = document.createElement('p');
      message.setAttribute('role', 'status');
      message.textContent = `Controller could not load: ${error.message}. Use List to edit mappings.`;
      el('controllerPicture').appendChild(message);
    }
  }
  return {init, refresh, tabChanged};
})();
