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
  renderElements: function (it, open) {
    var els = H.drawerUi.elementsFor(it), i, h = '';
    if (!els.length) return '<div class="fh-muted">Target: No element</div>';
    h += '<div class="fh-chips">';
    for (i = 0; i < els.length; i++) {
      h += '<span class="fh-chip" title="' + H.htmlEsc(els[i].selector) + '">' + H.htmlEsc(els[i].selector);
      if (open) h += ' <button type="button" class="fh-btn" style="padding:0 4px" data-da="remove-el" data-id="' + H.htmlEsc(it.id) + '" data-idx="' + i + '">x</button>';
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
      H.htmlEsc(label + ' (' + cnt + ' events)') + '">Trace: ' + H.htmlEsc(label) + ' (' + cnt + ')</span></div>';
  },
  renderRelated: function (it, open) {
    var rels = (it && Array.isArray(it.related_ids)) ? it.related_ids : [], i, h = '';
    if (rels.length) {
      h += '<div class="fh-chips">';
      for (i = 0; i < rels.length; i++) {
        h += '<span class="fh-chip fh-chip-link" data-da="jump-rel" data-id="' + H.htmlEsc(rels[i]) + '">' + H.htmlEsc(rels[i]);
        if (open) h += ' <button type="button" class="fh-btn" style="padding:0 4px" data-da="unlink-rel" data-id="' + H.htmlEsc(it.id) + '" data-rel="' + H.htmlEsc(rels[i]) + '">x</button>';
        h += '</span>';
      }
      h += '</div>';
    }
    if (open) {
      h += '<div class="fh-row"><input type="text" class="fh-input" data-da="rel-input" placeholder="Link OBS-NNN..." style="min-height:0;width:auto;flex:1;padding:4px 6px">' +
        '<button type="button" class="fh-btn" data-da="link-rel" data-id="' + H.htmlEsc(it.id) + '">Link</button></div>';
    }
    return h;
  },
  renderCard: function (it, state) {
    var open = state.selectedId === it.id, idEsc = H.htmlEsc(it.id);
    var draft = state.drafts[it.id], curKind = draft ? draft.kind : it.kind, curMsg = draft ? draft.message : it.message;
    var dirty = !!(draft && (draft.kind !== it.kind || draft.message !== it.message));
    var closed = it.status === 'dismissed' || it.status === 'resolved';
    var h = '<div class="fh-item" data-obs-id="' + idEsc + '"' + (dirty ? ' data-dirty="true"' : '') + '>';
    h += '<div class="fh-item-head" data-da="select" data-id="' + idEsc + '">';
    h += '<span><strong>' + idEsc + '</strong> [' + H.htmlEsc(it.kind) + ']' + (closed ? ' (' + H.htmlEsc(it.status) + ')' : '') + (dirty ? ' <span class="fh-dirty" data-da="dirty-badge" title="Unsaved draft changes">* Unsaved</span>' : '') + ' <span class="fh-muted">' + H.htmlEsc(it.page_path || '/') + '</span></span>';
    h += '<span class="fh-muted">' + (open ? '▲' : '▼') + '</span></div>';
    h += '<div>' + H.htmlEsc(it.message) + '</div>';
    h += H.drawerUi.renderElements(it, open);
    h += H.drawerUi.renderTrace(it);
    h += H.drawerUi.renderRelated(it, open);
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
    if (!list) return;
    if (!state.items.length) {
      list.innerHTML = '<div class="fh-muted">No observations in this view.</div>';
      return;
    }
    list.innerHTML = state.items.map(function (it) { return H.drawerUi.renderCard(it, state); }).join('');
    if (st && !st.textContent) st.textContent = state.items.length + ' loaded';
  }
};
