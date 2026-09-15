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
  function resetDrafts() { editors.clear(); advanced.clear(); conflicting.clear(); }
  function markConflicts(conflicts) {
    conflicting = new Set(conflicts.flatMap(conflict => conflict.actions));
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
