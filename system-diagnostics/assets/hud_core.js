/* Frontier debug HUD, part 1 of 4: core helpers & dark-slate/amber composer. ES5, no dependencies. */
var doc = win.document;
H.endpoint = win.__FRONTIER_OBS_ENDPOINT__ || '/api/diagnostics/observation';
H.baseEndpoint = H.endpoint.replace(/\/observation$/, '');
H.roots = [doc]; H.recordingId = null; H.finished = null; H.traceCleared = false; H.timeline = []; H.t0 = 0;
H.lastPick = null; H.picks = []; H.editingId = null; H.panelOpen = false; H.MAX_ELEMENTS = 20;
var FORBIDDEN = { value: 1, password: 1, authorization: 1, cookie: 1 };

H.isHud = function (el) {
  while (el) { if (el.id === '__frontier_hud__') return true; el = el.parentNode || el.host; }
  return false;
};
H.hex = function (n) {
  var s = '', i, a = null;
  try { a = win.crypto.getRandomValues(new Uint8Array(n)); } catch (e) { a = null; }
  for (i = 0; i < n; i++) s += ('0' + ((a ? a[i] : Math.floor(Math.random() * 256)) & 255).toString(16)).slice(-2);
  return s;
};
H.esc = function (s) { return (win.CSS && win.CSS.escape) ? win.CSS.escape(s) : String(s).replace(/[^a-zA-Z0-9_-]/g, '\\$&'); };
H.htmlEsc = function (s) { return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); };
H.isUnique = function (root, sel) { try { return root.querySelectorAll(sel).length === 1; } catch (e) { return false; } };
H.partFor = function (el) {
  var tag = el.tagName.toLowerCase(), cls = (el.getAttribute('class') || '').split(/\s+/).filter(Boolean).slice(0, 2);
  var part = tag + cls.map(function (c) { return '.' + H.esc(c); }).join('');
  var p = el.parentNode, same = 0, idx = 0, k;
  if (p && p.children) {
    for (k = 0; k < p.children.length; k++) {
      if (p.children[k].tagName === el.tagName) { same++; if (p.children[k] === el) idx = same; }
    }
    if (same > 1) part += ':nth-of-type(' + idx + ')';
  }
  return part;
};
H.scopedSelector = function (el, root) {
  var id = el.getAttribute('id'), tid = el.getAttribute('data-testid'), sel, path = [], cur = el, cand;
  if (id && H.isUnique(root, '#' + H.esc(id))) return '#' + H.esc(id);
  if (tid) { sel = '[data-testid="' + String(tid).replace(/"/g, '\\"') + '"]'; if (H.isUnique(root, sel)) return sel; }
  while (cur && cur.nodeType === 1 && cur !== root.documentElement) {
    path.unshift(H.partFor(cur));
    cand = path.join(' > ');
    if (H.isUnique(root, cand)) return cand;
    cur = cur.parentNode;
    if (cur && cur.nodeType !== 1) break;
  }
  return path.join(' > ');
};
H.selectorFor = function (el) {
  var parts = [], cur = el, root, host;
  while (cur) {
    root = cur.getRootNode ? cur.getRootNode() : doc;
    parts.unshift(H.scopedSelector(cur, root));
    if (root.host) { cur = root.host; continue; }
    host = root.defaultView && root.defaultView.frameElement;
    if (host) { cur = host; continue; }
    break;
  }
  return parts.join(' >>> ');
};
H.resolve = function (sel) {
  var parts = String(sel).split(' >>> '), ctx = doc, el = null, i;
  for (i = 0; i < parts.length; i++) {
    try { el = ctx.querySelector(parts[i]); } catch (e) { return null; }
    if (!el) return null;
    ctx = el.shadowRoot || (el.contentDocument || el);
  }
  return el;
};
H.attrsFor = function (el) {
  var tag = el.tagName.toLowerCase(), a = { tag: tag }, names = ['id', 'class', 'data-testid', 'role', 'aria-label', 'type', 'name'], i, v;
  for (i = 0; i < names.length; i++) { v = el.getAttribute(names[i]); if (v) a[names[i]] = String(v).slice(0, 200); }
  if (tag === 'input' || tag === 'textarea') { try { a.value_length = String(el.value).length; } catch (e) { /* ignore */ } }
  return a;
};
H.isSecret = function (el) { return el.tagName === 'INPUT' && String(el.getAttribute('type') || '').toLowerCase() === 'password'; };
H.urlTarget = function (url) {
  var u, keys = [], k;
  try { u = new win.URL(String(url), win.location.href); } catch (e) { return ''; }
  for (k of u.searchParams.keys()) keys.push(k);
  return u.pathname + (keys.length ? '?' + keys.join('&') : '');
};
H.log = function (type, target, extra) {
  var ev = { t: Date.now() - (H.t0 || Date.now()), type: type, target: String(target || '').slice(0, 200) }, k;
  for (k in (extra || {})) ev[k] = extra[k];
  if (H.recordingId) {
    H.timeline.push(ev);
    if (H.timeline.length > 50) H.timeline.shift();
    if (H.updateUi) H.updateUi();
  }
};
H.scrub = function (obj) {
  var k;
  if (Array.isArray(obj)) { obj.forEach(H.scrub); return obj; }
  if (obj && typeof obj === 'object') { for (k in obj) { if (FORBIDDEN[k.toLowerCase()]) delete obj[k]; else H.scrub(obj[k]); } }
  return obj;
};
H.pagePath = function () { return ((win.location && win.location.pathname) || '/') + ((win.location && win.location.hash) || ''); };
H.normalizePick = function (p) { return (p && p.selector) ? { selector: String(p.selector), rect: p.rect || null, attrs: p.attrs || {} } : null; };
H.activePicks = function () {
  if (H.picks && H.picks.length) return H.picks.slice(0, H.MAX_ELEMENTS);
  var single = H.normalizePick(H.lastPick);
  return single ? [single] : [];
};
H.addPick = function (pick) {
  var clean = H.normalizePick(pick), i;
  if (!clean) return false;
  H.lastPick = pick;
  for (i = 0; i < H.picks.length; i++) if (H.picks[i].selector === clean.selector) { H.picks[i] = clean; return true; }
  if (H.picks.length < H.MAX_ELEMENTS) H.picks.push(clean);
  return true;
};
H.removePick = function (idx) { if (idx >= 0 && idx < H.picks.length) H.picks.splice(idx, 1); H.lastPick = H.picks.length ? H.picks[H.picks.length - 1] : null; };
H.clearPicks = function () { H.picks = []; H.lastPick = null; };
H.buildRecord = function (kind, message) {
  var picks = H.activePicks(), rec = {
    schema: 1, ts: new Date().toISOString(), kind: kind, page_path: H.pagePath(),
    message: String(message || '').slice(0, 500)
  };
  if (picks.length) {
    rec.elements = picks;
    rec.selector = picks[0].selector; rec.rect = picks[0].rect; rec.attrs = picks[0].attrs;
  }
  var run = H.recordingId ? { id: H.recordingId, window: H.window, timeline: H.timeline } : H.finished;
  if (run) { rec.recording_id = run.id; rec.window = run.window || {}; rec.timeline = run.timeline.slice(-50); }
  return H.scrub(rec);
};
H.req = function (url, method, body) {
  var send = H.rawFetch || win.fetch, opts = { method: method || 'GET', headers: {} };
  if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(H.scrub(body)); }
  return send.call(win, url, opts).then(function (r) {
    return r.json().catch(function () { return {}; }).then(function (j) {
      if (!j || typeof j !== 'object') j = {};
      j.http = r.status;
      return j;
    });
  });
};
H.post = function (rec) { return H.req(H.endpoint, 'POST', rec); };
H.listObservations = function (status, limit) { return H.req(H.baseEndpoint + '/observations?status=' + encodeURIComponent(status || 'active') + '&limit=' + (limit || 50), 'GET'); };
H.getObservation = function (id) { return H.req(H.baseEndpoint + '/observations/' + encodeURIComponent(id), 'GET'); };
H.patchObservation = function (id, data) { return H.req(H.baseEndpoint + '/observations/' + encodeURIComponent(id), 'PATCH', data); };
H.deleteObservation = function (id) { return H.req(H.baseEndpoint + '/observations/' + encodeURIComponent(id), 'DELETE'); };
H.openInComposer = function (entry) {
  if (!entry || !entry.id) return;
  var p = H.panelEl, card = p && p.querySelector('[data-a=card]'), kindEl = p && p.querySelector('[data-a=kind]'), msg = p && p.querySelector('[data-a=msg]');
  var els = Array.isArray(entry.elements) && entry.elements.length ? entry.elements : (entry.selector ? [{ selector: entry.selector, rect: entry.rect || null, attrs: entry.attrs || {} }] : []);
  H.editingId = entry.id;
  H.picks = els.map(H.normalizePick).filter(Boolean).slice(0, H.MAX_ELEMENTS);
  H.lastPick = H.picks.length ? H.picks[0] : null;
  var tl = Array.isArray(entry.timeline) ? entry.timeline.slice() : [], tc = typeof entry.trace_count === 'number' ? entry.trace_count : tl.length;
  H.finished = (entry.recording_id || entry.window || tl.length || tc > 0) ? { id: entry.recording_id || 'trace', window: entry.window || {}, timeline: tl, count: tc, restored: true } : null; H.traceCleared = false;
  H.panelOpen = true;
  if (card) card.hidden = false;
  if (kindEl) kindEl.value = entry.kind || 'note';
  if (msg) { msg.value = entry.message || ''; if (msg.focus) msg.focus(); }
  if (H.toggleDrawer) H.toggleDrawer(false);
  if (H.updateUi) H.updateUi('Editing ' + entry.id);
};
H.cancelEdit = function () {
  var p = H.panelEl, msg = p && p.querySelector('[data-a=msg]'), kindEl = p && p.querySelector('[data-a=kind]');
  H.editingId = null; H.clearPicks(); H.finished = null; H.traceCleared = false;
  if (msg) msg.value = ''; if (kindEl) kindEl.value = 'note';
  if (H.updateUi) H.updateUi('Edit cancelled');
};
H.logObservation = function (kind, message) {
  if (H.isRecording && H.isRecording() && H.stop) H.stop();
  var picks = H.activePicks(), text = String(message || '').replace(/^\s+|\s+$/g, '');
  var resolvedKind = kind || (picks.length ? 'element' : 'note');
  if (H.editingId) {
    var editId = H.editingId, patch = { kind: resolvedKind, message: text.slice(0, 500), elements: picks };
    if (H.finished && !H.finished.restored) { patch.recording_id = H.finished.id; patch.window = H.finished.window || {}; patch.timeline = H.finished.timeline.slice(-50); }
    else if (!H.finished && H.traceCleared) { patch.recording_id = null; patch.window = null; patch.timeline = []; }
    return H.patchObservation(editId, patch).then(function (res) {
      if (res && res.http >= 200 && res.http < 300) {
        H.editingId = null; H.finished = null; H.traceCleared = false; H.clearPicks();
        if (H.onSaved) H.onSaved(res);
        if (H.updateUi) H.updateUi('Saved ' + editId);
      } else if (H.updateUi) H.updateUi('Save failed (' + ((res && res.http) || '?') + '): ' + ((res && res.message) || 'error'), true);
      return res;
    });
  }
  if (!text) {
    if (!picks.length && !H.finished) {
      if (H.updateUi) H.updateUi('Enter a message, Pick an element, or Record a trace first', true);
      return Promise.resolve({ http: 0, error: 'empty', message: 'Nothing to log yet' });
    }
    if (picks.length && H.finished) text = '[element+trace] ' + picks[0].selector;
    else if (picks.length) text = '[element] ' + picks[0].selector;
    else text = '[trace] ' + H.finished.id + ' (' + H.finished.timeline.length + ' events)';
  }
  return H.post(H.buildRecord(resolvedKind, text)).then(function (res) {
    if (res && res.http >= 200 && res.http < 300) {
      H.finished = null; H.clearPicks();
      if (H.onSaved) H.onSaved(res);
      if (H.updateUi) H.updateUi((res.deduplicated ? 'Updated ' : 'Saved ') + (res.id || 'observation'));
    } else if (H.updateUi) H.updateUi('Save failed (' + ((res && res.http) || '?') + '): ' + ((res && res.message) || 'error'), true);
    return res;
  }, function (err) {
    if (H.updateUi) H.updateUi('Save error: ' + String((err && err.message) || err || 'network'), true);
    throw err;
  });
};
H.sameOrigin = function (url) { try { return new win.URL(String(url), win.location.href).origin === win.location.origin; } catch (e) { return false; } };
H.addRoot = function (root) { if (H.roots.indexOf(root) < 0) H.roots.push(root); };
H.attachFrames = function () {
  var frames = doc.querySelectorAll('iframe'), i, d;
  for (i = 0; i < frames.length; i++) {
    try { d = frames[i].contentDocument; } catch (e) { d = null; }
    if (d) { H.addRoot(d); if (H.onRoot) H.onRoot(d); }
  }
};
H.attachDrag = function (p) {
  var drag = null;
  function onMove(e) {
    if (!drag || (drag.id !== undefined && e.pointerId !== undefined && e.pointerId !== drag.id)) return;
    var vw = win.innerWidth || (doc.documentElement && doc.documentElement.clientWidth) || 1280;
    var vh = win.innerHeight || (doc.documentElement && doc.documentElement.clientHeight) || 720;
    var nx = Math.min(Math.max(0, vw - Math.min(drag.w, vw)), Math.max(0, drag.ox + ((e.clientX || 0) - drag.sx)));
    var ny = Math.min(Math.max(0, vh - Math.min(drag.h, vh)), Math.max(0, drag.oy + ((e.clientY || 0) - drag.sy)));
    p.style.left = Math.round(nx) + 'px'; p.style.top = Math.round(ny) + 'px'; p.style.right = 'auto'; p.style.bottom = 'auto';
  }
  function onUp(e) {
    if (!drag || (drag.id !== undefined && e && e.pointerId !== undefined && e.pointerId !== drag.id)) return;
    if (drag.cap && drag.cap.releasePointerCapture && drag.id !== undefined) { try { drag.cap.releasePointerCapture(drag.id); } catch (err) { /* ignore */ } }
    drag = null;
  }
  p.addEventListener('pointerdown', function (e) {
    var t = e.target, h = t && t.closest ? t.closest('[data-a="title"],[data-a="card-head"]') : null;
    if (!h || (t && t.tagName && /^(SELECT|OPTION|BUTTON|INPUT|TEXTAREA)$/i.test(t.tagName)) || (e.button !== undefined && e.button !== 0)) return;
    var r = p.getBoundingClientRect ? p.getBoundingClientRect() : { left: 0, top: 0, width: 320, height: 180 };
    drag = { id: e.pointerId, sx: e.clientX || 0, sy: e.clientY || 0, ox: typeof r.left === 'number' ? r.left : (r.x || 0), oy: typeof r.top === 'number' ? r.top : (r.y || 0), w: r.width || 320, h: r.height || 180, cap: h };
    if (h.setPointerCapture && e.pointerId !== undefined) { try { h.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ } }
    if (e.preventDefault) e.preventDefault();
  });
  p.addEventListener('pointermove', onMove); p.addEventListener('pointerup', onUp); p.addEventListener('pointercancel', onUp);
  if (win.addEventListener) { win.addEventListener('pointermove', onMove); win.addEventListener('pointerup', onUp); win.addEventListener('pointercancel', onUp); }
};
H.buildPanel = function () {
  var p = doc.createElement('div'), css = '';
  p.id = '__frontier_hud__';
  css += '#__frontier_hud__{position:fixed;right:16px;bottom:16px;z-index:2147483647;font-family:Inter,system-ui,sans-serif;display:flex;flex-direction:column;align-items:flex-end;gap:8px;color:#f3f4f6;}';
  css += '#__frontier_hud__ *{box-sizing:border-box;}.fh-pill{background:#b45309;color:#fff;border:1px solid #f59e0b;border-radius:999px;padding:7px 13px;font-size:12px;font-weight:600;cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,.35);display:inline-flex;align-items:center;gap:6px;}';
  css += '.fh-btn{background:#1f2937;color:#f3f4f6;border:1px solid #374151;border-radius:6px;padding:5px 9px;font-size:11px;font-weight:600;cursor:pointer;}.fh-btn:hover{border-color:#f59e0b;}.fh-btn.active{background:#b45309;border-color:#f59e0b;color:#fff;}.fh-btn.danger{border-color:#ef4444;color:#fca5a5;}';
  css += '.fh-card{width:320px;background:#111827;border:1px solid #f59e0b;border-radius:10px;padding:12px;display:flex;flex-direction:column;gap:8px;box-shadow:0 8px 24px rgba(0,0,0,.5);}.fh-card[hidden],.fh-drawer[hidden]{display:none;}';
  css += '.fh-row{display:flex;justify-content:space-between;align-items:center;gap:6px;flex-wrap:wrap;}.fh-drag{cursor:grab;user-select:none;}.fh-drag:active{cursor:grabbing;}.fh-input,.fh-select{width:100%;background:#1f2937;color:#f9fafb;border:1px solid #374151;border-radius:6px;padding:7px;font-size:12px;}.fh-input{min-height:68px;resize:vertical;}';
  css += '.fh-chips{display:flex;flex-wrap:wrap;gap:4px;}.fh-chip{background:#1f2937;border:1px solid #f59e0b;color:#fde68a;border-radius:999px;padding:2px 8px;font-size:10px;display:inline-flex;align-items:center;gap:4px;max-width:100%;min-width:0;overflow:hidden;}.fh-chip-label{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1 1 auto;}.fh-chip .fh-btn{flex-shrink:0;}';
  css += '.fh-chip-link{border-color:#60a5fa;color:#bfdbfe;cursor:pointer;}.fh-status{font-size:11px;color:#fcd34d;min-height:14px;}.fh-status.err{color:#fca5a5;}.fh-bar{display:flex;align-items:center;gap:6px;}';
  css += '.fh-drawer{position:fixed;top:0;right:0;bottom:0;width:360px;max-width:95vw;background:#111827;border-left:1px solid #f59e0b;padding:12px;display:flex;flex-direction:column;gap:8px;box-shadow:-8px 0 28px rgba(0,0,0,.55);z-index:2147483647;}';
  css += '.fh-list{flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:8px;}.fh-item{background:#1f2937;border:1px solid #374151;border-radius:8px;padding:8px;display:flex;flex-direction:column;gap:6px;font-size:11px;}';
  css += '.fh-item-head{display:flex;justify-content:space-between;align-items:center;gap:6px;cursor:pointer;}.fh-muted{color:#9ca3af;font-size:10px;word-break:break-word;}.fh-dot{width:8px;height:8px;border-radius:999px;background:#ef4444;display:inline-block;}.fh-dirty{background:#78350f;border:1px solid #f59e0b;color:#fde68a;border-radius:999px;padding:1px 6px;font-size:10px;font-weight:600;}';
  var html = '<style>' + css + '</style><div class="fh-card" data-a="card" hidden>';
  html += '<div class="fh-row fh-drag" data-a="card-head"><strong class="fh-drag" style="font-size:12px;color:#fbbf24" data-a="title">Debug Observation</strong><select class="fh-select" data-a="kind" style="width:auto;padding:3px 6px"><option value="note">note</option><option value="element">element</option><option value="idea">idea</option><option value="error">error</option><option value="network">network</option></select></div>';
  html += '<div class="fh-row"><button type="button" class="fh-btn" data-a="pick">Pick</button><button type="button" class="fh-btn" data-a="rec">Record</button><button type="button" class="fh-btn" data-a="stop">Stop</button><button type="button" class="fh-btn" data-a="drawer">History <span data-a="count"></span></button></div>';
  html += '<div class="fh-chips" data-a="chips"></div><textarea class="fh-input" data-a="msg" placeholder="Describe bug or idea (or attach Pick/Trace)..."></textarea>';
  html += '<div class="fh-row"><span class="fh-status" data-a="status">Ready</span><div class="fh-bar"><button type="button" class="fh-btn" data-a="cancel-edit" hidden>Cancel</button><button type="button" class="fh-pill" data-a="log">Log</button></div></div></div>';
  html += '<div class="fh-bar"><button type="button" class="fh-btn" data-a="drawer-quick">Observations <span data-a="qcount"></span></button><button type="button" class="fh-pill" data-a="toggle">Log Observation</button></div>';
  p.innerHTML = html;
  H.panelEl = p;
  H.updateUi = function (statusText, isErr) {
    var st = p.querySelector('[data-a=status]'), chips = p.querySelector('[data-a=chips]'), recBtn = p.querySelector('[data-a=rec]'), pickBtn = p.querySelector('[data-a=pick]');
    var titleEl = p.querySelector('[data-a=title]'), logBtn = p.querySelector('[data-a=log]'), cancelBtn = p.querySelector('[data-a=cancel-edit]');
    if (st && statusText !== undefined) { st.textContent = statusText; st.className = isErr ? 'fh-status err' : 'fh-status'; }
    if (pickBtn) pickBtn.className = (H.isPicking && H.isPicking()) ? 'fh-btn active' : 'fh-btn';
    if (recBtn) { recBtn.className = (H.isRecording && H.isRecording()) ? 'fh-btn active' : 'fh-btn'; recBtn.textContent = (H.isRecording && H.isRecording()) ? ('Recording (' + H.timeline.length + ')') : 'Record'; }
    if (titleEl) titleEl.textContent = H.editingId ? ('Editing ' + H.editingId) : 'Debug Observation';
    if (logBtn) logBtn.textContent = H.editingId ? 'Save' : 'Log';
    if (cancelBtn) cancelBtn.hidden = !H.editingId;
    if (chips) {
      var chtml = '', picks = H.activePicks(), i;
      for (i = 0; i < picks.length; i++) {
        chtml += '<span class="fh-chip" title="' + H.htmlEsc(picks[i].selector) + '"><span class="fh-chip-label">Target: ' + H.htmlEsc(picks[i].selector) + '</span><button type="button" class="fh-btn" style="padding:0 4px;flex-shrink:0" data-a="remove-pick" data-idx="' + i + '">x</button></span>';
      }
      if (H.recordingId) chtml += '<span class="fh-chip"><span class="fh-dot"></span> <span class="fh-chip-label">' + H.htmlEsc(H.recordingId) + ' (' + H.timeline.length + ')</span></span>';
      else if (H.finished) chtml += '<span class="fh-chip"><span class="fh-chip-label">Trace: ' + H.htmlEsc(H.finished.id) + ' (' + (typeof H.finished.count === 'number' ? H.finished.count : H.finished.timeline.length) + ')</span><button type="button" class="fh-btn" style="padding:0 4px;flex-shrink:0" data-a="clear-trace">x</button></span>';
      chips.innerHTML = chtml;
    }
  };
  p.addEventListener('click', function (e) {
    var target = e.target, btn = target && target.closest ? target.closest('[data-a]') : target, a = btn && btn.getAttribute ? btn.getAttribute('data-a') : null;
    if (!a) return;
    var msg = p.querySelector('[data-a=msg]'), card = p.querySelector('[data-a=card]'), kindEl = p.querySelector('[data-a=kind]');
    if (a === 'toggle') { H.panelOpen = !H.panelOpen; if (card) card.hidden = !H.panelOpen; if (H.panelOpen && msg && msg.focus) msg.focus(); }
    else if (a === 'pick') H.pick();
    else if (a === 'rec') H.record();
    else if (a === 'stop') H.stop();
    else if (a === 'cancel-edit') H.cancelEdit();
    else if (a === 'remove-pick') { H.removePick(parseInt(btn.getAttribute('data-idx'), 10)); H.updateUi('Removed picked element'); }
    else if (a === 'clear-pick') { H.clearPicks(); H.updateUi('Cleared picked elements'); }
    else if (a === 'clear-trace') { H.finished = null; if (H.editingId) H.traceCleared = true; H.updateUi('Cleared recorded trace'); }
    else if (a === 'drawer' || a === 'drawer-quick') { if (H.toggleDrawer) H.toggleDrawer(); }
    else if (a === 'log') {
      H.logObservation(kindEl ? kindEl.value : 'note', msg ? msg.value : '').then(function (res) {
        if (res && res.http >= 200 && res.http < 300 && msg) msg.value = '';
      }, function () { /* keep text for retry */ });
    }
  });
  H.attachDrag(p);
  (doc.body || doc.documentElement).appendChild(p);
  return p;
};
