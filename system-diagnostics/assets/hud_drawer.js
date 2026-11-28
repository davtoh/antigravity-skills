/* Frontier debug HUD, part 4 of 4: Right-side observation drawer + install. */
var drawerState = { open: false, filter: 'active', sort: 'id_desc', query: '', selectedId: null, items: [], pendingPickObsId: null, drafts: {}, confirmDeleteId: null, lastUndo: null };
H.drawerState = drawerState;

function findItem(id) {
  var i;
  for (i = 0; i < drawerState.items.length; i++) if (drawerState.items[i].id === id) return drawerState.items[i];
  return null;
}
function setStatus(drawer, text, html) {
  var st = drawer && drawer.querySelector('[data-a=dstatus]');
  if (!st) return;
  if (html !== undefined) st.innerHTML = html;
  else st.textContent = text;
}
function syncDraft(drawer, card) {
  var id = card && card.getAttribute ? card.getAttribute('data-obs-id') : null, orig = id && findItem(id);
  if (!id || !orig) return;
  var kEl = card.querySelector('[data-da=kind]'), mEl = card.querySelector('[data-da=msg]'), sBtn = card.querySelector('[data-da=save]');
  var k = kEl ? kEl.value : orig.kind, m = mEl ? mEl.value : orig.message;
  var dirty = k !== orig.kind || m !== orig.message;
  if (dirty) drawerState.drafts[id] = { kind: k, message: m };
  else delete drawerState.drafts[id];
  if (sBtn) { sBtn.textContent = dirty ? 'Save *' : 'Save'; sBtn.className = dirty ? 'fh-btn active' : 'fh-btn'; }
}
H.refreshCounts = function () {
  if (!H.panelEl || (!H.panelEl.querySelector('[data-a=count]') && !H.panelEl.querySelector('[data-a=qcount]'))) {
    return Promise.resolve(null);
  }
  return H.listObservations('active', 200).then(function (res) {
    if (res && res.http >= 200 && res.http < 300) {
      var n = typeof res.count === 'number' ? res.count : (Array.isArray(res.observations) ? res.observations.length : 0);
      H.drawerUi.updateCounts(n);
      return n;
    }
    return null;
  }, function () { return null; });
};
H.refreshDrawer = function (keepStatus) {
  var drawer = H.drawerEl;
  if (!drawer) return Promise.resolve([]);
  return H.listObservations(drawerState.filter, 50).then(function (res) {
    drawerState.items = (res && Array.isArray(res.observations)) ? res.observations : [];
    if (drawerState.filter === 'active') H.drawerUi.updateCounts(drawerState.items.length);
    else H.refreshCounts();
    if (!keepStatus) setStatus(drawer, drawerState.items.length + ' ' + drawerState.filter);
    H.drawerUi.renderList(drawer, drawerState);
    return drawerState.items;
  }, function () {
    setStatus(drawer, 'Failed to load observations');
    return [];
  });
};
H.toggleDrawer = function (forceOpen) {
  if (!H.drawerEl) return;
  drawerState.open = typeof forceOpen === 'boolean' ? forceOpen : !drawerState.open;
  H.drawerEl.hidden = !drawerState.open;
  if (drawerState.open) H.refreshDrawer();
};
H.onSaved = function (res) {
  if (res && res.id) delete drawerState.drafts[res.id];
  if (drawerState.open) H.refreshDrawer();
  else H.refreshCounts();
};
H.onPicked = function (pick) {
  if (!drawerState.pendingPickObsId || !pick) return false;
  var obsId = drawerState.pendingPickObsId, item = findItem(obsId);
  drawerState.pendingPickObsId = null;
  var merged = H.drawerUi.mergeElements(H.drawerUi.elementsFor(item), [pick]);
  H.patchObservation(obsId, { elements: merged }).then(function () {
    if (H.updateUi) H.updateUi('Attached element to ' + obsId);
    H.toggleDrawer(true);
  });
  return true;
};
function triggerDownload(filename, text) {
  if (!win.Blob || !win.URL || !win.URL.createObjectURL) return false;
  var blob = new win.Blob([text], { type: 'application/json' }), url = win.URL.createObjectURL(blob), a = doc.createElement('a');
  a.href = url; a.download = filename; a.style.display = 'none';
  if (doc.body && doc.body.appendChild) doc.body.appendChild(a);
  if (a.click) a.click();
  if (doc.body && doc.body.removeChild && a.parentNode === doc.body) doc.body.removeChild(a);
  if (win.URL.revokeObjectURL) win.URL.revokeObjectURL(url);
  return true;
}
function exportObservations(d) {
  return H.req(H.baseEndpoint + '/observations/export?status=all', 'GET').then(function (res) {
    if (!res || res.http < 200 || res.http >= 300) { setStatus(d, 'Export failed: ' + ((res && res.message) || 'error')); return res; }
    var copy = {}, k;
    for (k in res) { if (Object.prototype.hasOwnProperty.call(res, k) && k !== 'http') copy[k] = res[k]; }
    triggerDownload('observations-export.json', JSON.stringify(copy, null, 2));
    setStatus(d, 'Exported ' + (copy.count || (Array.isArray(copy.observations) ? copy.observations.length : 0)) + ' observations');
    return copy;
  }, function () { setStatus(d, 'Export failed: network error'); return null; });
}
function importPayload(d, payload) {
  return H.req(H.baseEndpoint + '/observations/import', 'POST', payload).then(function (res) {
    if (!res || res.http < 200 || res.http >= 300) { setStatus(d, 'Import failed: ' + ((res && res.message) || 'error')); return res; }
    setStatus(d, 'Imported ' + (res.imported || 0) + ', updated ' + (res.updated || 0) + ', skipped ' + (res.skipped || 0));
    return H.refreshDrawer(true).then(function () { return res; });
  }, function () { setStatus(d, 'Import failed: network error'); return null; });
}
function handleImportFile(d, inp) {
  var file = inp && inp.files && inp.files[0];
  if (!file) return Promise.resolve(null);
  function parseAndSend(text) {
    var parsed;
    try { parsed = JSON.parse(String(text || '')); } catch (err) { setStatus(d, 'Import failed: invalid JSON'); return Promise.resolve(null); }
    return importPayload(d, parsed);
  }
  if (typeof file.text === 'function') return file.text().then(parseAndSend);
  if (win.FileReader) {
    return new Promise(function (resolve) {
      var fr = new win.FileReader();
      fr.onload = function () { parseAndSend(fr.result).then(resolve); };
      fr.onerror = function () { setStatus(d, 'Import failed: read error'); resolve(null); };
      fr.readAsText(file);
    });
  }
  setStatus(d, 'Import failed: unsupported file reader');
  return Promise.resolve(null);
}
H.exportObservations = function () { return exportObservations(H.drawerEl); };
H.importObservations = function (payload) { return importPayload(H.drawerEl, payload); };
function handleDrawerAction(d, act, id, btn) {
  if (act === 'close') { H.toggleDrawer(false); return; }
  if (act === 'refresh') { H.refreshDrawer(); return; }
  if (act === 'sort') {
    var order = ['id_desc', 'id_asc', 'recent'];
    drawerState.sort = order[(order.indexOf(drawerState.sort) + 1) % order.length];
    if (btn) btn.textContent = H.drawerUi.sortLabel(drawerState.sort);
    H.drawerUi.renderList(d, drawerState);
    return;
  }
  if (act === 'export') { exportObservations(d); return; }
  if (act === 'import') {
    var fi = d.querySelector('[data-da=import-file]');
    if (fi) { fi.value = ''; if (fi.click) fi.click(); }
    return;
  }
  if (act === 'undo' && drawerState.lastUndo) {
    var u = drawerState.lastUndo;
    drawerState.lastUndo = null;
    H.patchObservation(u.id, { status: u.prevStatus || 'open' }).then(function () {
      setStatus(d, 'Reopened ' + u.id);
      H.refreshDrawer(true);
    });
    return;
  }
  if (act === 'jump-rel' && id) {
    drawerState.selectedId = id;
    if (findItem(id)) { H.drawerUi.renderList(d, drawerState); return; }
    drawerState.filter = 'all';
    var fEl = d.querySelector('[data-da=filter]');
    if (fEl) fEl.value = 'all';
    H.refreshDrawer();
    return;
  }
  if (act === 'select' && id) {
    drawerState.selectedId = drawerState.selectedId === id ? null : id;
    drawerState.confirmDeleteId = null;
    H.drawerUi.renderList(d, drawerState);
    return;
  }
  if (!id) return;
  var card = d.querySelector('[data-obs-id="' + id + '"]'), item = findItem(id);
  if (act === 'save' && card) {
    var kEl = card.querySelector('[data-da=kind]'), mEl = card.querySelector('[data-da=msg]');
    H.patchObservation(id, { kind: kEl ? kEl.value : 'note', message: mEl ? mEl.value : '' }).then(function () {
      delete drawerState.drafts[id];
      setStatus(d, 'Updated ' + id);
      H.refreshDrawer(true);
    });
  } else if (act === 'open' && item) {
    var dr = drawerState.drafts[id];
    H.openInComposer({
      id: item.id, kind: dr ? dr.kind : item.kind, message: dr ? dr.message : item.message,
      elements: H.drawerUi.elementsFor(item), selector: item.selector, rect: item.rect, attrs: item.attrs,
      recording_id: item.recording_id, window: item.window, timeline: item.timeline, trace_count: item.trace_count
    });
  } else if (act === 'attach-pick') {
    var picks = H.activePicks();
    if (picks.length) {
      var nextEls = H.drawerUi.mergeElements(H.drawerUi.elementsFor(item), picks);
      H.patchObservation(id, { elements: nextEls }).then(function () {
        H.clearPicks();
        setStatus(d, 'Attached element to ' + id);
        if (H.updateUi) H.updateUi();
        H.refreshDrawer(true);
      });
    } else {
      drawerState.pendingPickObsId = id;
      H.toggleDrawer(false);
      H.pick();
    }
  } else if (act === 'remove-el' && item) {
    var idx = parseInt(btn.getAttribute('data-idx'), 10), curEls = H.drawerUi.elementsFor(item).slice();
    if (idx >= 0 && idx < curEls.length) curEls.splice(idx, 1);
    H.patchObservation(id, { elements: curEls }).then(function () {
      setStatus(d, 'Removed element from ' + id);
      H.refreshDrawer(true);
    });
  } else if (act === 'link-rel' && card && item) {
    var inp = card.querySelector('[data-da=rel-input]'), val = String((inp && inp.value) || '').replace(/^\s+|\s+$/g, '').toUpperCase();
    if (!/^OBS-\d+$/.test(val) || val === id.toUpperCase()) { setStatus(d, val === id.toUpperCase() ? 'Cannot link observation to itself' : 'Enter a valid ID like OBS-001'); return; }
    var nextRels = (Array.isArray(item.related_ids) ? item.related_ids.slice() : []);
    if (nextRels.indexOf(val) < 0) nextRels.push(val);
    H.patchObservation(id, { related_ids: nextRels }).then(function () {
      setStatus(d, 'Linked ' + val + ' to ' + id);
      H.refreshDrawer(true);
    });
  } else if (act === 'unlink-rel' && item) {
    var rel = btn.getAttribute('data-rel'), kept = (item.related_ids || []).filter(function (r) { return r !== rel; });
    H.patchObservation(id, { related_ids: kept }).then(function () {
      setStatus(d, 'Unlinked ' + rel);
      H.refreshDrawer(true);
    });
  } else if (act === 'attach-trace') {
    if (H.isRecording && H.isRecording() && H.stop) H.stop();
    if (!H.finished) { setStatus(d, 'Record a trace first, then click Attach Trace'); return; }
    H.patchObservation(id, { recording_id: H.finished.id, window: H.finished.window, timeline: H.finished.timeline }).then(function () {
      H.finished = null;
      setStatus(d, 'Attached trace to ' + id);
      if (H.updateUi) H.updateUi();
      H.refreshDrawer(true);
    });
  } else if (act === 'dismiss') {
    drawerState.lastUndo = { id: id, prevStatus: (item && item.status) || 'open' };
    H.patchObservation(id, { status: 'dismissed' }).then(function () {
      setStatus(d, '', 'Dismissed ' + H.htmlEsc(id) + ' <button type="button" class="fh-btn" style="padding:1px 6px;margin-left:6px" data-da="undo">Undo</button>');
      H.refreshDrawer(true);
    });
  } else if (act === 'confirm') {
    drawerState.lastUndo = null;
    H.patchObservation(id, { status: 'confirmed' }).then(function () {
      setStatus(d, 'Confirmed ' + id);
      H.refreshDrawer(true);
    });
  } else if (act === 'reopen') {
    drawerState.lastUndo = null;
    H.patchObservation(id, { status: 'open' }).then(function () {
      setStatus(d, 'Reopened ' + id);
      H.refreshDrawer(true);
    });
  } else if (act === 'delete') {
    drawerState.confirmDeleteId = id;
    H.drawerUi.renderList(d, drawerState);
  } else if (act === 'delete-cancel') {
    drawerState.confirmDeleteId = null;
    H.drawerUi.renderList(d, drawerState);
  } else if (act === 'delete-confirm') {
    drawerState.confirmDeleteId = null;
    H.deleteObservation(id).then(function () {
      delete drawerState.drafts[id];
      if (drawerState.selectedId === id) drawerState.selectedId = null;
      setStatus(d, 'Deleted ' + id);
      H.refreshDrawer(true);
    });
  }
}
H.buildDrawer = function () {
  if (!H.panelEl) return null;
  var d = doc.createElement('div');
  d.className = 'fh-drawer';
  d.hidden = true;
  d.innerHTML = '<div class="fh-row"><strong style="color:#fbbf24;font-size:13px">Registered Observations</strong>' +
    '<div class="fh-bar"><select class="fh-select" data-da="filter" style="width:auto;padding:3px 6px"><option value="active">Active</option><option value="open">Open</option><option value="triaged">Triaged</option><option value="in_progress">In Progress</option><option value="resolved">Resolved</option><option value="confirmed">Confirmed</option><option value="dismissed">Dismissed</option><option value="all">All</option></select>' +
    '<button type="button" class="fh-btn" data-da="export">Export</button><button type="button" class="fh-btn" data-da="import">Import</button>' +
    '<input type="file" data-da="import-file" accept="application/json,.json" hidden>' +
    '<button type="button" class="fh-btn" data-da="refresh">Refresh</button><button type="button" class="fh-btn" data-da="close">Close</button></div></div>' +
    '<div class="fh-row"><input type="search" class="fh-input" data-da="search" placeholder="Search ID, message, selector..." style="min-height:0;width:auto;flex:1;padding:4px 6px"><button type="button" class="fh-btn" data-da="sort" title="Toggle sort order">Sort: ID ↓</button></div>' +
    '<div class="fh-status" data-da="dstatus" data-a="dstatus"></div><div class="fh-list" data-a="list"></div>';
  d.addEventListener('change', function (e) {
    var da = e.target && e.target.getAttribute ? e.target.getAttribute('data-da') : null;
    if (da === 'filter') { drawerState.filter = e.target.value; H.refreshDrawer(); }
    else if (da === 'kind') syncDraft(d, e.target.closest ? e.target.closest('[data-obs-id]') : null);
    else if (da === 'import-file') handleImportFile(d, e.target);
  });
  d.addEventListener('input', function (e) {
    var da = e.target && e.target.getAttribute ? e.target.getAttribute('data-da') : null;
    if (da === 'msg') syncDraft(d, e.target.closest ? e.target.closest('[data-obs-id]') : null);
    else if (da === 'search') { drawerState.query = String(e.target.value || ''); H.drawerUi.renderList(d, drawerState); }
  });
  d.addEventListener('click', function (e) {
    var btn = e.target && e.target.closest ? e.target.closest('[data-da]') : e.target;
    var act = btn && btn.getAttribute ? btn.getAttribute('data-da') : null;
    var id = btn && btn.getAttribute ? btn.getAttribute('data-id') : null;
    if (act) handleDrawerAction(d, act, id, btn);
  });
  H.panelEl.appendChild(d);
  H.drawerEl = d;
  return d;
};

H.buildPanel();
H.buildDrawer();
H.refreshCounts();
win.__FRONTIER_HUD__ = H;
