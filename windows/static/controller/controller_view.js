/* The owned map supplies all control/action relations and drawing anchors.
 * Rows use page state, not persisted API rows: pending List edits stay visible.
 * Scoped editors share the List field renderer, reader and commit path.
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
  const heads = new Map();
  const hits = new Map();
  let layoutObserver = null;
  let live = null;
  const el = id => document.getElementById(id);
  const svgElement = (tag, attrs = {}) => {
    const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, value);
    return node;
  };

  // Detached editors survive card navigation and sibling commits. Accepted loads
  // explicitly reset these caches; a version poll never resets a dirty draft.
  const editors = new Map();
  const advanced = new Map();
  let cardTab = 'mappings';
  let conflicting = new Set();
  let conflictGroups = [];
  const button = (text, className, onClick) => {
    const node = document.createElement('button');
    node.className = 'btn btn-sm ' + className;
    node.textContent = text;
    node.addEventListener('click', onClick);
    return node;
  };
  const errorText = (node, message = '') => {
    node.textContent = message;
    node.classList.toggle('show', Boolean(message));
  };
  function trackDraft(node, draft) {
    for (const event of ['input', 'change']) node.addEventListener(event, () => {
      draft.dirty = true;
      formDirty = true;
      editRevision++;
    });
  }
  function hasDrafts() { return [...editors.values(), ...advanced.values()].some(draft => draft.dirty); }
  function resetDrafts() { editors.clear(); advanced.clear(); conflicting.clear(); conflictGroups = []; }
  function markConflicts(conflicts) {
    conflictGroups = conflicts;
    conflicting = new Set(conflictGroups.flatMap(conflict => conflict.actions));
    refresh();
  }
  function setCardTab(next) {
    cardTab = next;
    el('controllerRows').hidden = next !== 'mappings';
    el('controllerAdvanced').hidden = next !== 'advanced';
    el('controllerMappingsTab').setAttribute('aria-selected', String(next === 'mappings'));
    el('controllerAdvancedTab').setAttribute('aria-selected', String(next === 'advanced'));
  }
  function rowEditor(action) {
    if (editors.has(action)) return editors.get(action);
    const prefix = 'controller_' + action + '_';
    const node = document.createElement('div');
    node.className = 'controller-inline-editor';
    node.id = prefix + 'editor';
    node.hidden = true;
    const draft = {node, dirty:false};
    const label = document.createElement('label');
    label.textContent = 'Mapping type';
    label.setAttribute('for', prefix + 'type');
    const type = document.createElement('select');
    type.className = 'controller-type'; type.id = prefix + 'type';
    for (const [value, title] of Object.entries(TYPE_LABELS)) {
      const option = document.createElement('option');
      option.value = value; option.textContent = title; type.appendChild(option);
    }
    type.value = state[action]?.type || '';
    const fields = document.createElement('div'); fields.className = 'controller-fields';
    const applyRow = document.createElement('div'); applyRow.className = 'action-row';
    const error = document.createElement('div'); error.className = 'json-err'; error.setAttribute('role', 'alert');
    const render = spec => renderFields(type.value, spec, fields, prefix, applyRow);
    type.addEventListener('change', () => { render(type.value ? {...DEFAULTS[type.value]} : null); errorText(error); });
    applyRow.appendChild(button('Apply fields', 'btn-primary controller-apply', () => {
      // Use the form's existing bounds. Optional overrides may stay blank.
      for (const input of fields.querySelectorAll('input')) {
        if (input.type !== 'number') continue;
        const value = String(input.value).trim();
        if (!value && input.placeholder) continue;
        const number = Number(value);
        if (!value || !Number.isFinite(number) || number < Number(input.min) || number > Number(input.max) ||
            (Number(input.step) === 1 && !Number.isInteger(number))) {
          errorText(error, 'Invalid value for ' + input.id.slice(prefix.length) + '. Check the field range.');
          return;
        }
      }
      const spec = readFields(type.value, fields, prefix);
      if (!spec) return;
      commit(action, spec);
      renderMacroLibrary();
      toast(`${action} updated`);
    }));
    node.appendChild(label); node.appendChild(type); node.appendChild(fields);
    node.appendChild(error); node.appendChild(applyRow);
    node.appendChild(button('Clear mapping', 'btn-danger-outline controller-clear', () => {
      commit(action, null); toast(`${action} cleared`);
    }));
    render(state[action]);
    trackDraft(node, draft);
    editors.set(action, draft);
    return draft;
  }
  function macroPicker(action) {
    const select = document.createElement('select'); select.className = 'controller-macro';
    select.setAttribute('aria-label', `Apply macro to ${action}`);
    const placeholder = document.createElement('option');
    placeholder.value = ''; placeholder.textContent = 'Apply macro...'; select.appendChild(placeholder);
    for (const macro of macroLibrary) {
      const option = document.createElement('option'); option.value = macro.id;
      option.disabled = !macroCompatible(macro, action);
      option.textContent = macro.name + (option.disabled ? ' (incompatible)' : '');
      select.appendChild(option);
    }
    select.value = '';
    select.addEventListener('change', () => {
      const macro = macroLibrary.find(item => item.id === select.value);
      if (macro && macroCompatible(macro, action)) {
        applyMacroToAction(macro, action);
        renderMacroLibrary();
        toast(`Applied "${macro.name}" to ${action}`);
      }
      select.value = '';
    });
    return select;
  }
  function advancedEditor(control) {
    const ids = Object.values(control.groups).flat();
    const currentJson = () => JSON.stringify(Object.fromEntries(ids.map(id => [id, state[id] || null])), null, 2);
    if (advanced.has(control.id)) {
      const draft = advanced.get(control.id);
      if (!draft.dirty) draft.input.value = currentJson();
      return draft.node;
    }
    const node = document.createElement('div'); node.className = 'controller-json-editor';
    const label = document.createElement('label'); label.textContent = 'Mappings JSON for ' + control.label;
    const input = document.createElement('textarea'); input.className = 'json-textarea controller-json';
    input.id = 'controller_' + control.id + '_json'; input.spellcheck = false; input.value = currentJson();
    label.setAttribute('for', input.id);
    const error = document.createElement('div'); error.className = 'json-err'; error.setAttribute('role', 'alert');
    const draft = {node, input, dirty:false};
    const actions = document.createElement('div'); actions.className = 'action-row';
    actions.appendChild(button('Apply JSON', 'controller-json-apply', () => {
      let parsed;
      try {
        parsed = JSON.parse(input.value);
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('Expected an object keyed by Action ID.');
        for (const [id, spec] of Object.entries(parsed)) {
          if (!ids.includes(id)) throw new Error(id + ' does not belong to this control.');
          if (spec !== null && (!spec || typeof spec !== 'object' || Array.isArray(spec) || !Object.hasOwn(DEFAULTS, spec.type))) {
            throw new Error(id + ': expected a mapping object with a supported type, or null.');
          }
          if (spec) {
            // A malformed field (for example a string refresh_actions) must
            // not throw halfway through committing the control's other IDs.
            mappingDesc(spec);
            renderFields(spec.type, spec, document.createElement('div'), 'controller_check_', document.createElement('div'));
          }
        }
      } catch (e) { errorText(error, 'JSON error: ' + e.message); return; }
      // Validate the entire object before any per-id commit, as in List applyJson.
      for (const id of ids) commit(id, Object.hasOwn(parsed, id) ? parsed[id] : null);
      draft.dirty = false;
      errorText(error);
      refresh();
      renderMacroLibrary();
      toast(`${control.label} updated from JSON`);
    }));
    actions.appendChild(button('Copy', 'controller-json-copy', async () => {
      try { await navigator.clipboard.writeText(input.value.trim()); toast('Copied'); }
      catch (e) { errorText(error, 'Copy failed: ' + e.message); }
    }));
    input.addEventListener('input', () => errorText(error));
    node.appendChild(label); node.appendChild(input); node.appendChild(error); node.appendChild(actions);
    trackDraft(node, draft);
    advanced.set(control.id, draft);
    return node;
  }

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
    el('controllerLiveTools').hidden = view !== 'controller';
    live?.setVisible(tab === 'editor' && view === 'controller');
  }

  function tabChanged(name) { tab = name; setView(view, false); }

  function openControl(id, focus = true) {
    if (!map?.controls.some(control => control.id === id)) return;
    activeControl = id;
    refresh();
    if (focus) el('controllerTitle').focus();
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
    el('controllerAdvanced').replaceChildren();
    if (!control) return;
    el('controllerTitle').textContent = control.label;
    el('controllerAdvanced').appendChild(advancedEditor(control));
    setCardTab(cardTab);
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
        row.classList.toggle('controller-conflict', conflicting.has(action));
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
        const draft = rowEditor(action);
        const edit = button('Edit', 'controller-edit', () => {
          draft.node.hidden = !draft.node.hidden;
          edit.setAttribute('aria-expanded', String(!draft.node.hidden));
        });
        edit.setAttribute('aria-controls', draft.node.id);
        edit.setAttribute('aria-expanded', String(!draft.node.hidden));
        const actions = document.createElement('div'); actions.className = 'action-row';
        actions.appendChild(edit); actions.appendChild(link);
        row.appendChild(actions);
        row.appendChild(macroPicker(action));
        if (conflicting.has(action)) {
          const warning = document.createElement('p'); warning.className = 'controller-conflict-message';
          warning.textContent = 'MIDI CC conflict'; row.appendChild(warning);
        }
        row.appendChild(draft.node);
        group.appendChild(row);
      }
      el('controllerRows').appendChild(group);
    }
  }

  function refresh(action = null) {
    if (!map) return;
    if (action && conflicting.has(action)) {
      // Only retire a reported warning after its channel/CC collision is resolved.
      // This is presentation state; Save still uses the server's conflict guard.
      conflictGroups = conflictGroups.filter(group => !group.actions.includes(action) || group.actions.filter(id => {
        const spec = state[id];
        return spec && (spec.channel || 0) === group.channel &&
          (spec.type === 'axis_split_cc' ? [spec.cc_positive, spec.cc_negative] : [spec.cc]).includes(group.cc);
      }).length > 1);
      conflicting = new Set(conflictGroups.flatMap(group => group.actions));
    }
    if (action && action === selected && view === 'controller') renderEditor(action);
    if (action && editors.has(action)) {
      const wasOpen = !editors.get(action).node.hidden;
      editors.delete(action);
      rowEditor(action).node.hidden = !wasOpen;
    }
    for (const control of map.controls) {
      const ids = Object.values(control.groups).flat();
      const mapped = ids.filter(id => Boolean(state[id])).length;
      const label = labels.get(control.id);
      label.querySelector('small').textContent = `${mapped}/${ids.length}`;
      label.setAttribute('aria-label', `${control.label}: ${mapped} of ${ids.length} mapped`);
      label.setAttribute('aria-expanded', String(activeControl === control.id));
      for (const node of [label, arrows.get(control.id), shapes.get(control.id), heads.get(control.id)]) {
        node.classList.toggle('control-unmapped', mapped === 0);
        node.classList.toggle('control-selected', activeControl === control.id);
      }
    }
    renderCard();
    live?.refresh();
  }

  function draw(art) {
    const picture = el('controllerPicture');
    picture.replaceChildren();
    const [x, y, width, height] = map.scene_view_box;

    const scene = svgElement('svg', {viewBox: map.scene_view_box.join(' '), class: 'controller-scene'});
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
      const arrow = svgElement('polyline', {...coords, class: 'controller-arrow', 'data-control-arrow': control.id,
        'pointer-events': 'none'});
      const hit = svgElement('polyline', {...coords, class: 'controller-arrow-hit', 'data-control': control.id});
      hit.addEventListener('click', () => openControl(control.id));
      const head = svgElement('polygon', {class: 'controller-arrow-head', 'data-control-head': control.id});
      heads.set(control.id, head);
      hits.set(control.id, hit);
      scene.appendChild(head);
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
    live = ControllerLive.create(map, art, labels, {
      currentControl: () => activeControl,
      openControl: id => openControl(id, false),
      hasUnsavedEdit: () => {
        const control = map.controls.find(c => c.id === activeControl);
        if (!control) return false;
        return advanced.get(control.id)?.dirty || Object.values(control.groups).flat().some(action =>
          editors.get(action)?.dirty || (dirty && JSON.stringify(state[action] || null) !==
            JSON.stringify(sectionDocument.mappings?.[action] || sharedMappings[action] || null)));
      },
    });
    refresh();
    live.setVisible(tab === 'editor' && view === 'controller');
    // Layout requires the real SVG geometry API. The VM behavior check deliberately
    // has no layout engine; its initial anchor attributes still describe the map.
    if (typeof ResizeObserver !== 'undefined') {
      layoutObserver?.disconnect();
      layoutObserver = new ResizeObserver(() => layout(picture, scene, art));
      layoutObserver.observe(picture);
    }
  }

  // All label placement and routing is here. Bank/order and optional bend anchors
  // come from the owned map; the art and its control coordinates never move apart.
  function layout(picture, scene, art) {
    const width = picture.clientWidth, height = picture.clientHeight;
    if (!width || !height) return;
    scene.setAttribute('viewBox', `0 0 ${width} ${height}`);
    const labelWidth = Math.min(146, width / 6 - 10);
    const scale = Math.min((width - 2 * (labelWidth + 18)) / map.view_box[2], (height - 100) / map.view_box[3]);
    const ox = (width - map.view_box[2] * scale) / 2;
    const oy = (height - map.view_box[3] * scale) / 2;
    art.setAttribute('x', ox); art.setAttribute('y', oy);
    art.setAttribute('width', map.view_box[2] * scale); art.setAttribute('height', map.view_box[3] * scale);
    const project = (x, y) => ({x: ox + x * scale, y: oy + y * scale});
    const banks = {top: [], bottom: [], left: [], right: []};
    for (const c of map.controls) {
      const p = c.label_anchor;
      banks[p.y < 0 ? 'top' : p.y > map.view_box[3] - 50 ? 'bottom' : p.x < 0 ? 'left' : 'right'].push(c);
    }
    for (const [bank, controls] of Object.entries(banks)) {
      const horizontal = bank === 'top' || bank === 'bottom';
      controls.sort((a, b) => horizontal ? a.label_anchor.x - b.label_anchor.x : a.label_anchor.y - b.label_anchor.y);
      const span = horizontal ? 0 : Math.max((controls.at(-1).label_anchor.y - controls[0].label_anchor.y) * scale, (controls.length - 1) * 34);
      const middle = horizontal ? 0 : oy + (controls[0].label_anchor.y + controls.at(-1).label_anchor.y) / 2 * scale;
      const first = Math.max(66, Math.min(height - 66 - span, middle - span / 2));
      controls.forEach((c, i) => {
        const center = horizontal ? {x: width * (i + .5) / controls.length, y: bank === 'top' ? 18 : height - 18} :
          {x: bank === 'left' ? labelWidth / 2 + 3 : width - labelWidth / 2 - 3, y: first + i * span / (controls.length - 1)};
        const label = labels.get(c.id);
        label.style.width = `${labelWidth}px`;
        label.style.left = `${center.x}px`; label.style.top = `${center.y}px`;
        const target = project(c.anchor.x, c.anchor.y);
        const bends = (c.leader_via || []).map(([x, y]) => project(x, y));
        const toward = bends[0] || target;
        // Intersect a ray from an interior anchor with a rectangle's boundary.
        const edge = (from, to, box) => {
          const dx = to.x - from.x, dy = to.y - from.y;
          const t = Math.min(dx > 0 ? (box.x + box.width - from.x) / dx : dx < 0 ? (box.x - from.x) / dx : Infinity,
            dy > 0 ? (box.y + box.height - from.y) / dy : dy < 0 ? (box.y - from.y) / dy : Infinity);
          return {x: from.x + dx * t, y: from.y + dy * t};
        };
        const start = edge(center, toward, {x: center.x - labelWidth / 2, y: center.y - 15, width: labelWidth, height: 30});
        const b = shapes.get(c.id).getBBox();
        const box = {x: ox + b.x * scale, y: oy + b.y * scale, width: b.width * scale, height: b.height * scale};
        const end = edge(target, bends.at(-1) || start, box);
        const points = [start, ...bends, end];
        const encoded = points.map(p => `${p.x},${p.y}`).join(' ');
        const arrow = arrows.get(c.id);
        arrow.setAttribute('points', encoded); hits.get(c.id).setAttribute('points', encoded);
        arrow.setAttribute('x2', end.x); arrow.setAttribute('y2', end.y);
        const last = points.at(-2), length = Math.hypot(end.x - last.x, end.y - last.y);
        const ux = (end.x - last.x) / length, uy = (end.y - last.y) / length;
        heads.get(c.id).setAttribute('points', `${end.x},${end.y} ${end.x - ux * 6 - uy * 3},${end.y - uy * 6 + ux * 3} ${end.x - ux * 6 + uy * 3},${end.y - uy * 6 - ux * 3}`);
      });
    }
  }

  async function init() {
    try { view = localStorage.getItem(STORAGE_KEY) === 'list' ? 'list' : 'controller'; } catch (_) { view = 'controller'; }
    setView(view, false);
    el('viewController').addEventListener('click', () => setView('controller'));
    el('viewList').addEventListener('click', () => setView('list'));
    el('controllerClose').addEventListener('click', closeControl);
    el('controllerMappingsTab').addEventListener('click', () => setCardTab('mappings'));
    el('controllerAdvancedTab').addEventListener('click', () => setCardTab('advanced'));
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
  return {init, refresh, tabChanged, resetDrafts, hasDrafts, markConflicts};
})();
