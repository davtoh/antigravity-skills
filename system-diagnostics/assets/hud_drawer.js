/* Frontier debug HUD, part 4 of 4: Right-side observation drawer + install. */
var drawerState = { open: false, filter: 'active', selectedId: null, items: [], pendingPickObsId: null };

function updateCounts(n) {
  if (!H.panelEl) return;
  var txt = typeof n === 'number' ? '(' + n + ')' : '';
  var c1 = H.panelEl.querySelector('[data-a=count]'), c2 = H.panelEl.querySelector('[data-a=qcount]');
  if (c1) c1.textContent = txt;
  if (c2) c2.textContent = txt;
}
function renderDrawerItems(drawer) {
  var list = drawer.querySelector('[data-a=list]'), st = drawer.querySelector('[data-a=dstatus]');
  if (!list) return;
  if (!drawerState.items.length) {
    list.innerHTML = '<div class="fh-muted">No observations in this view.</div>';
    return;
  }
  list.innerHTML = drawerState.items.map(function (it) {
    var open = drawerState.selectedId === it.id, sel = it.selector || 'No element';
    var h = '<div class="fh-item" data-obs-id="' + H.htmlEsc(it.id) + '">';
    h += '<div class="fh-item-head" data-da="select" data-id="' + H.htmlEsc(it.id) + '">';
    h += '<span><strong>' + H.htmlEsc(it.id) + '</strong> [' + H.htmlEsc(it.kind) + '] <span class="fh-muted">' + H.htmlEsc(it.page_path || '/') + '</span></span>';
    h += '<span class="fh-muted">' + (open ? '▲' : '▼') + '</span></div>';
    h += '<div>' + H.htmlEsc(it.message) + '</div>';
    h += '<div class="fh-muted">Target: ' + H.htmlEsc(sel) + '</div>';
    if (open) {
      h += '<select class="fh-select" data-da="kind">';
      ['note', 'element', 'idea', 'error', 'network'].forEach(function (k) {
        h += '<option value="' + k + '"' + (it.kind === k ? ' selected' : '') + '>' + k + '</option>';
      });
      h += '</select>';
      h += '<textarea class="fh-input" data-da="msg" style="min-height:54px">' + H.htmlEsc(it.message) + '</textarea>';
      h += '<div class="fh-row">';
      h += '<button type="button" class="fh-btn" data-da="save" data-id="' + H.htmlEsc(it.id) + '">Save</button>';
      h += '<button type="button" class="fh-btn" data-da="attach-pick" data-id="' + H.htmlEsc(it.id) + '">' + (H.lastPick ? 'Attach Pick' : 'Pick & Attach') + '</button>';
      h += '<button type="button" class="fh-btn" data-da="attach-trace" data-id="' + H.htmlEsc(it.id) + '">Attach Trace</button>';
      h += '<button type="button" class="fh-btn" data-da="dismiss" data-id="' + H.htmlEsc(it.id) + '">Dismiss</button>';
      h += '<button type="button" class="fh-btn danger" data-da="delete" data-id="' + H.htmlEsc(it.id) + '">Delete</button>';
      h += '</div>';
    }
    return h + '</div>';
  }).join('');
  if (st && !st.textContent) st.textContent = drawerState.items.length + ' loaded';
}
H.refreshDrawer = function () {
  var drawer = H.drawerEl;
  if (!drawer) return Promise.resolve([]);
  var st = drawer.querySelector('[data-a=dstatus]');
  return H.listObservations(drawerState.filter, 50).then(function (res) {
    drawerState.items = (res && Array.isArray(res.observations)) ? res.observations : [];
    if (drawerState.filter === 'active') updateCounts(drawerState.items.length);
    if (st) st.textContent = drawerState.items.length + ' ' + drawerState.filter;
    renderDrawerItems(drawer);
    return drawerState.items;
  }, function () {
    if (st) st.textContent = 'Failed to load observations';
    return [];
  });
};
H.toggleDrawer = function (forceOpen) {
  if (!H.drawerEl) return;
  drawerState.open = typeof forceOpen === 'boolean' ? forceOpen : !drawerState.open;
  H.drawerEl.hidden = !drawerState.open;
  if (drawerState.open) H.refreshDrawer();
};
H.onSaved = function () {
  if (drawerState.open) H.refreshDrawer();
};
H.onPicked = function (pick) {
  if (!drawerState.pendingPickObsId || !pick) return;
  var obsId = drawerState.pendingPickObsId;
  drawerState.pendingPickObsId = null;
  H.patchObservation(obsId, { selector: pick.selector, rect: pick.rect, attrs: pick.attrs, kind: 'element' }).then(function () {
    H.lastPick = null;
    if (H.updateUi) H.updateUi('Attached element to ' + obsId);
    H.toggleDrawer(true);
  });
};
H.buildDrawer = function () {
  if (!H.panelEl) return null;
  var d = doc.createElement('div');
  d.className = 'fh-drawer';
  d.hidden = true;
  d.innerHTML = '<div class="fh-row"><strong style="color:#fbbf24;font-size:13px">Registered Observations</strong>' +
    '<div class="fh-bar"><select class="fh-select" data-da="filter" style="width:auto;padding:3px 6px"><option value="active">Active</option><option value="all">All</option></select>' +
    '<button type="button" class="fh-btn" data-da="refresh">Refresh</button>' +
    '<button type="button" class="fh-btn" data-da="close">Close</button></div></div>' +
    '<div class="fh-status" data-da="dstatus" data-a="dstatus"></div><div class="fh-list" data-a="list"></div>';
  d.addEventListener('change', function (e) {
    if (e.target && e.target.getAttribute && e.target.getAttribute('data-da') === 'filter') {
      drawerState.filter = e.target.value;
      H.refreshDrawer();
    }
  });
  d.addEventListener('click', function (e) {
    var btn = e.target && e.target.closest ? e.target.closest('[data-da]') : e.target;
    var act = btn && btn.getAttribute ? btn.getAttribute('data-da') : null;
    var id = btn && btn.getAttribute ? btn.getAttribute('data-id') : null;
    var st = d.querySelector('[data-a=dstatus]');
    if (!act) return;
    if (act === 'close') { H.toggleDrawer(false); return; }
    if (act === 'refresh') { H.refreshDrawer(); return; }
    if (act === 'select' && id) { drawerState.selectedId = drawerState.selectedId === id ? null : id; renderDrawerItems(d); return; }
    if (!id) return;
    var card = d.querySelector('[data-obs-id="' + id + '"]');
    if (act === 'save' && card) {
      var kEl = card.querySelector('[data-da=kind]'), mEl = card.querySelector('[data-da=msg]');
      H.patchObservation(id, { kind: kEl ? kEl.value : 'note', message: mEl ? mEl.value : '' }).then(function () {
        if (st) st.textContent = 'Updated ' + id;
        H.refreshDrawer();
      });
    } else if (act === 'attach-pick') {
      if (H.lastPick) {
        H.patchObservation(id, { selector: H.lastPick.selector, rect: H.lastPick.rect, attrs: H.lastPick.attrs, kind: 'element' }).then(function () {
          H.lastPick = null;
          if (st) st.textContent = 'Attached picked element to ' + id;
          if (H.updateUi) H.updateUi();
          H.refreshDrawer();
        });
      } else {
        drawerState.pendingPickObsId = id;
        H.toggleDrawer(false);
        H.pick();
      }
    } else if (act === 'attach-trace') {
      if (H.isRecording && H.isRecording() && H.stop) H.stop();
      if (!H.finished) { if (st) st.textContent = 'Record a trace first, then click Attach Trace'; return; }
      H.patchObservation(id, { recording_id: H.finished.id, window: H.finished.window, timeline: H.finished.timeline }).then(function () {
        H.finished = null;
        if (st) st.textContent = 'Attached trace to ' + id;
        if (H.updateUi) H.updateUi();
        H.refreshDrawer();
      });
    } else if (act === 'dismiss') {
      H.patchObservation(id, { status: 'dismissed' }).then(function () {
        if (st) st.textContent = 'Dismissed ' + id;
        H.refreshDrawer();
      });
    } else if (act === 'delete') {
      H.deleteObservation(id).then(function () {
        if (drawerState.selectedId === id) drawerState.selectedId = null;
        if (st) st.textContent = 'Deleted ' + id;
        H.refreshDrawer();
      });
    }
  });
  H.panelEl.appendChild(d);
  H.drawerEl = d;
  return d;
};

H.buildPanel();
H.buildDrawer();
win.__FRONTIER_HUD__ = H;
