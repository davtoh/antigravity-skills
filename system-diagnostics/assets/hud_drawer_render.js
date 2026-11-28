/* Frontier debug HUD drawer renderer helper. ES5, no dependencies. */
H.drawerUi = {
  elementsFor: function (it) {
    if (it && Array.isArray(it.elements) && it.elements.length) return it.elements;
    if (it && it.selector) return [{ selector: it.selector, rect: it.rect || null, attrs: it.attrs || {} }];
    return [];
  },
  mergeElements: function (existing, incoming) {
    var out = [], seen = {}, i, item;
    function add(raw) {
      var clean = H.normalizePick ? H.normalizePick(raw) : (raw && raw.selector ? { selector: raw.selector, rect: raw.rect || null, attrs: raw.attrs || {} } : null);
      if (!clean || seen[clean.selector] || out.length >= (H.MAX_ELEMENTS || 20)) return;
      seen[clean.selector] = 1;
      out.push(clean);
    }
    for (i = 0; i < (existing || []).length; i++) add(existing[i]);
    for (i = 0; i < (incoming || []).length; i++) add(incoming[i]);
    return out;
  },
  updateCounts: function (n) {
    if (!H.panelEl) return;
    var txt = typeof n === 'number' ? '(' + n + ')' : '';
    var c1 = H.panelEl.querySelector('[data-a=count]'), c2 = H.panelEl.querySelector('[data-a=qcount]');
    if (c1) c1.textContent = txt;
    if (c2) c2.textContent = txt;
  },
  obsNum: function (id) {
    var m = String(id || '').match(/(\d+)$/);
    return m ? parseInt(m[1], 10) : 0;
  },
  sortLabel: function (mode) {
    if (mode === 'id_asc') return 'Sort: ID ↑';
    if (mode === 'recent') return 'Sort: Recent';
    return 'Sort: ID ↓';
  },
  visibleItems: function (state) {
    var items = Array.isArray(state.items) ? state.items.slice() : [];
    var q = String(state.query || '').replace(/^\s+|\s+$/g, '').toLowerCase();
    if (q) {
      items = items.filter(function (it) {
        var els = H.drawerUi.elementsFor(it), i;
        if (String(it.id || '').toLowerCase().indexOf(q) >= 0) return true;
        if (String(it.message || '').toLowerCase().indexOf(q) >= 0) return true;
        if (String(it.selector || '').toLowerCase().indexOf(q) >= 0) return true;
        if (String(it.page_path || '').toLowerCase().indexOf(q) >= 0) return true;
        for (i = 0; i < els.length; i++) {
          if (String(els[i].selector || '').toLowerCase().indexOf(q) >= 0) return true;
        }
        return false;
      });
    }
    var mode = state.sort || 'id_desc';
    items.sort(function (a, b) {
      if (mode === 'id_asc') return H.drawerUi.obsNum(a.id) - H.drawerUi.obsNum(b.id);
      if (mode === 'recent') {
        var cmp = String(b.last_seen || '').localeCompare(String(a.last_seen || ''));
        return cmp !== 0 ? cmp : (H.drawerUi.obsNum(b.id) - H.drawerUi.obsNum(a.id));
      }
      return H.drawerUi.obsNum(b.id) - H.drawerUi.obsNum(a.id);
    });
    return items;
  },
  renderElements: function (it, open) {
    var els = H.drawerUi.elementsFor(it), i, h = '';
    if (!els.length) return '<div class="fh-muted">Target: No element</div>';
    h += '<div class="fh-chips">';
    for (i = 0; i < els.length; i++) {
      h += '<span class="fh-chip" title="' + H.htmlEsc(els[i].selector) + '"><span class="fh-chip-label">' + H.htmlEsc(els[i].selector) + '</span>';
      if (open) h += '<button type="button" class="fh-btn" style="padding:0 4px;flex-shrink:0" data-da="remove-el" data-id="' + H.htmlEsc(it.id) + '" data-idx="' + i + '">x</button>';
      h += '</span>';
    }
    return h + '</div>';
  },
  renderTrace: function (it) {
    var rid = it && it.recording_id, w = it && it.window;
    var tl = (it && Array.isArray(it.timeline)) ? it.timeline : [];
    var cnt = (it && typeof it.trace_count === 'number') ? it.trace_count : tl.length;
    if (!rid && !w && !cnt) return '';
    var label = rid || 'trace';
    return '<div class="fh-chips"><span class="fh-chip" data-da="trace-chip" title="' +
      H.htmlEsc(label + ' (' + cnt + ' events)') + '"><span class="fh-chip-label">Trace: ' + H.htmlEsc(label) + ' (' + cnt + ')</span></span></div>';
  },
  renderRelated: function (it, open, allItems) {
    var rels = (it && Array.isArray(it.related_ids)) ? it.related_ids : [], i, h = '';
    if (rels.length) {
      h += '<div class="fh-chips">';
      for (i = 0; i < rels.length; i++) {
        h += '<span class="fh-chip fh-chip-link" data-da="jump-rel" data-id="' + H.htmlEsc(rels[i]) + '">' + H.htmlEsc(rels[i]);
        if (open) h += ' <button type="button" class="fh-btn" style="padding:0 4px;flex-shrink:0" data-da="unlink-rel" data-id="' + H.htmlEsc(it.id) + '" data-rel="' + H.htmlEsc(rels[i]) + '">x</button>';
        h += '</span>';
      }
      h += '</div>';
    }
    if (open) {
      var listId = 'fh-rel-list-' + String(it.id || '').replace(/[^a-zA-Z0-9_-]/g, '');
      var seen = {}, opts = [], cands = Array.isArray(allItems) ? allItems.slice() : [];
      seen[String(it.id || '').toUpperCase()] = 1;
      for (i = 0; i < rels.length; i++) seen[String(rels[i] || '').toUpperCase()] = 1;
      cands.sort(function (a, b) { return H.drawerUi.obsNum(b.id) - H.drawerUi.obsNum(a.id); });
      for (i = 0; i < cands.length && opts.length < 25; i++) {
        var cid = String((cands[i] && cands[i].id) || '').toUpperCase();
        if (!cid || seen[cid]) continue;
        seen[cid] = 1;
        var sum = String((cands[i] && cands[i].message) || '').replace(/\s+/g, ' ').slice(0, 60);
        opts.push('<option value="' + H.htmlEsc(cid) + '">' + H.htmlEsc(cid + (sum ? ': ' + sum : '')) + '</option>');
      }
      h += '<div class="fh-row"><input type="text" class="fh-input" data-da="rel-input" list="' + H.htmlEsc(listId) + '" placeholder="Link OBS-NNN..." style="min-height:0;width:auto;flex:1;padding:4px 6px">' +
        '<datalist id="' + H.htmlEsc(listId) + '" data-da="rel-datalist">' + opts.join('') + '</datalist>' +
        '<button type="button" class="fh-btn" data-da="link-rel" data-id="' + H.htmlEsc(it.id) + '">Link</button></div>';
    }
    return h;
  },
  renderResolution: function (it) {
    if (!it || (it.status !== 'resolved' && it.status !== 'confirmed')) return '';
    var idEsc = H.htmlEsc(it.id), h = '', badges = [];
    if (it.resolution) h += '<div class="fh-muted" data-da="resolution-note">Resolution: ' + H.htmlEsc(it.resolution) + '</div>';
    if (it.confirmed_note) h += '<div class="fh-muted" data-da="confirmed-note">Confirmed: ' + H.htmlEsc(it.confirmed_note) + '</div>';
    var plan = it.resolved_plan || it.linked_plan;
    if (plan) badges.push('<span class="fh-chip" data-da="prov-plan">plan: ' + H.htmlEsc(plan) + '</span>');
    if (it.resolved_milestone) badges.push('<span class="fh-chip" data-da="prov-milestone">milestone: ' + H.htmlEsc(it.resolved_milestone) + '</span>');
    if (it.linked_commit) badges.push('<span class="fh-chip" data-da="prov-commit">commit: ' + H.htmlEsc(it.linked_commit) + '</span>');
    else if (it.base_commit) badges.push('<span class="fh-chip" data-da="prov-base-commit">base: ' + H.htmlEsc(it.base_commit) + '</span>');
    if (badges.length) h += '<div class="fh-chips" data-da="provenance">' + badges.join('') + '</div>';
    if (it.status === 'resolved') {
      h += '<div class="fh-row" data-da="resolve-actions">' +
        '<button type="button" class="fh-btn active" data-da="confirm" data-id="' + idEsc + '">Confirm</button>' +
        '<button type="button" class="fh-btn" data-da="reopen" data-id="' + idEsc + '">Reopen</button></div>';
    }
    return h;
  },
  renderCard: function (it, state) {
    var open = state.selectedId === it.id, idEsc = H.htmlEsc(it.id);
    var draft = state.drafts[it.id], curKind = draft ? draft.kind : it.kind, curMsg = draft ? draft.message : it.message;
    var dirty = !!(draft && (draft.kind !== it.kind || draft.message !== it.message));
    var closed = it.status === 'dismissed' || it.status === 'resolved' || it.status === 'confirmed';
    var h = '<div class="fh-item" data-obs-id="' + idEsc + '"' + (dirty ? ' data-dirty="true"' : '') + '>';
    h += '<div class="fh-item-head" data-da="select" data-id="' + idEsc + '">';
    h += '<span><strong>' + idEsc + '</strong> [' + H.htmlEsc(it.kind) + ']' + (closed ? ' (' + H.htmlEsc(it.status) + ')' : '') + (dirty ? ' <span class="fh-dirty" data-da="dirty-badge" title="Unsaved draft changes">* Unsaved</span>' : '') + ' <span class="fh-muted">' + H.htmlEsc(it.page_path || '/') + '</span></span>';
    h += '<span class="fh-muted">' + (open ? '▲' : '▼') + '</span></div>';
    h += '<div>' + H.htmlEsc(it.message) + '</div>';
    h += H.drawerUi.renderResolution(it);
    h += H.drawerUi.renderElements(it, open);
    h += H.drawerUi.renderTrace(it);
    h += H.drawerUi.renderRelated(it, open, state.items);
    if (open) {
      h += '<select class="fh-select" data-da="kind">';
      ['note', 'element', 'idea', 'error', 'network'].forEach(function (k) {
        h += '<option value="' + k + '"' + (curKind === k ? ' selected' : '') + '>' + k + '</option>';
      });
      h += '</select>';
      h += '<textarea class="fh-input" data-da="msg" style="min-height:54px">' + H.htmlEsc(curMsg) + '</textarea>';
      h += '<div class="fh-row">';
      h += '<button type="button" class="fh-btn' + (dirty ? ' active' : '') + '" data-da="save" data-id="' + idEsc + '">' + (dirty ? 'Save *' : 'Save') + '</button>';
      h += '<button type="button" class="fh-btn" data-da="open" data-id="' + idEsc + '">Open</button>';
      h += '<button type="button" class="fh-btn" data-da="attach-pick" data-id="' + idEsc + '">' + (H.activePicks().length ? 'Attach Pick' : 'Pick & Attach') + '</button>';
      h += '<button type="button" class="fh-btn" data-da="attach-trace" data-id="' + idEsc + '">Attach Trace</button>';
      h += closed
        ? '<button type="button" class="fh-btn" data-da="reopen" data-id="' + idEsc + '">Reopen</button>'
        : '<button type="button" class="fh-btn" data-da="dismiss" data-id="' + idEsc + '">Dismiss</button>';
      if (state.confirmDeleteId === it.id) {
        h += '<button type="button" class="fh-btn danger" data-da="delete-confirm" data-id="' + idEsc + '">Confirm Delete</button>';
        h += '<button type="button" class="fh-btn" data-da="delete-cancel" data-id="' + idEsc + '">Cancel</button>';
      } else {
        h += '<button type="button" class="fh-btn danger" data-da="delete" data-id="' + idEsc + '">Delete</button>';
      }
      h += '</div>';
    }
    return h + '</div>';
  },
  renderList: function (drawer, state) {
    var list = drawer.querySelector('[data-a=list]'), st = drawer.querySelector('[data-a=dstatus]');
    var sortBtn = drawer.querySelector('[data-da=sort]');
    if (sortBtn) sortBtn.textContent = H.drawerUi.sortLabel(state.sort);
    if (!list) return;
    var shown = H.drawerUi.visibleItems(state);
    if (!shown.length) {
      list.innerHTML = '<div class="fh-muted">' + (state.query ? 'No matching observations.' : 'No observations in this view.') + '</div>';
      if (st && state.query) st.textContent = '0/' + state.items.length + ' matching';
      return;
    }
    list.innerHTML = shown.map(function (it) { return H.drawerUi.renderCard(it, state); }).join('');
    if (st && state.query) st.textContent = shown.length + '/' + state.items.length + ' matching';
    else if (st && !st.textContent) st.textContent = shown.length + ' loaded';
  }
};
