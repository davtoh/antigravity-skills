/* Frontier debug HUD, part 1 of 4: core helpers & dark-slate/amber composer. ES5, no dependencies. */
var doc = win.document;
H.endpoint = win.__FRONTIER_OBS_ENDPOINT__ || '/api/diagnostics/observation';
H.baseEndpoint = H.endpoint.replace(/\/observation$/, '');
H.roots = [doc];
H.recordingId = null;
H.finished = null;
H.timeline = [];
H.t0 = 0;
H.lastPick = null;
H.panelOpen = false;
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
H.esc = function (s) {
  return (win.CSS && win.CSS.escape) ? win.CSS.escape(s) : String(s).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
};
H.htmlEsc = function (s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
};
H.isUnique = function (root, sel) {
  try { return root.querySelectorAll(sel).length === 1; } catch (e) { return false; }
};
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
H.isSecret = function (el) {
  return el.tagName === 'INPUT' && String(el.getAttribute('type') || '').toLowerCase() === 'password';
};
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
H.pagePath = function () {
  var p = (win.location && win.location.pathname) || '/', h = (win.location && win.location.hash) || '';
  return p + (h ? h : '');
};
H.buildRecord = function (kind, message) {
  var p = H.lastPick || {}, rec = {
    schema: 1, ts: new Date().toISOString(), kind: kind, page_path: H.pagePath(),
    message: String(message || '').slice(0, 500)
  };
  if (p.selector) { rec.selector = p.selector; rec.rect = p.rect; rec.attrs = p.attrs; }
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
H.listObservations = function (status, limit) {
  var st = status || 'active', lim = limit || 50;
  return H.req(H.baseEndpoint + '/observations?status=' + encodeURIComponent(st) + '&limit=' + lim, 'GET');
};
H.getObservation = function (id) { return H.req(H.baseEndpoint + '/observations/' + encodeURIComponent(id), 'GET'); };
H.patchObservation = function (id, data) { return H.req(H.baseEndpoint + '/observations/' + encodeURIComponent(id), 'PATCH', data); };
H.deleteObservation = function (id) { return H.req(H.baseEndpoint + '/observations/' + encodeURIComponent(id), 'DELETE'); };
H.logObservation = function (kind, message) {
  if (H.isRecording && H.isRecording() && H.stop) H.stop();
  var text = String(message || '').replace(/^\s+|\s+$/g, ''), resolvedKind = kind || (H.lastPick ? 'element' : 'note');
  if (!text) {
    if (!H.lastPick && !H.finished) {
      if (H.updateUi) H.updateUi('Enter a message, Pick an element, or Record a trace first', true);
      return Promise.resolve({ http: 0, error: 'empty', message: 'Nothing to log yet' });
    }
    if (H.lastPick && H.finished) text = '[element+trace] ' + H.lastPick.selector;
    else if (H.lastPick) text = '[element] ' + H.lastPick.selector;
    else text = '[trace] ' + H.finished.id + ' (' + H.finished.timeline.length + ' events)';
  }
  var rec = H.buildRecord(resolvedKind, text);
  return H.post(rec).then(function (res) {
    if (res && res.http >= 200 && res.http < 300) {
      H.finished = null;
      H.lastPick = null;
      if (H.onSaved) H.onSaved(res);
      if (H.updateUi) H.updateUi((res.deduplicated ? 'Updated ' : 'Saved ') + (res.id || 'observation'));
    } else if (H.updateUi) {
      H.updateUi('Save failed (' + ((res && res.http) || '?') + '): ' + ((res && res.message) || 'error'), true);
    }
    return res;
  }, function (err) {
    if (H.updateUi) H.updateUi('Save error: ' + String((err && err.message) || err || 'network'), true);
    throw err;
  });
};
H.sameOrigin = function (url) {
  try { return new win.URL(String(url), win.location.href).origin === win.location.origin; } catch (e) { return false; }
};
H.addRoot = function (root) { if (H.roots.indexOf(root) < 0) H.roots.push(root); };
H.attachFrames = function () {
  var frames = doc.querySelectorAll('iframe'), i, d;
  for (i = 0; i < frames.length; i++) {
    try { d = frames[i].contentDocument; } catch (e) { d = null; }
    if (d) { H.addRoot(d); if (H.onRoot) H.onRoot(d); }
  }
};
H.buildPanel = function () {
  var p = doc.createElement('div'), css = '';
  p.id = '__frontier_hud__';
  css += '#__frontier_hud__{position:fixed;right:16px;bottom:16px;z-index:2147483647;font-family:Inter,system-ui,sans-serif;display:flex;flex-direction:column;align-items:flex-end;gap:8px;color:#f3f4f6;}';
  css += '#__frontier_hud__ *{box-sizing:border-box;}';
  css += '.fh-pill{background:#b45309;color:#fff;border:1px solid #f59e0b;border-radius:999px;padding:7px 13px;font-size:12px;font-weight:600;cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,.35);display:inline-flex;align-items:center;gap:6px;}';
  css += '.fh-btn{background:#1f2937;color:#f3f4f6;border:1px solid #374151;border-radius:6px;padding:5px 9px;font-size:11px;font-weight:600;cursor:pointer;}';
  css += '.fh-btn:hover{border-color:#f59e0b;}.fh-btn.active{background:#b45309;border-color:#f59e0b;color:#fff;}.fh-btn.danger{border-color:#ef4444;color:#fca5a5;}';
  css += '.fh-card{width:320px;background:#111827;border:1px solid #f59e0b;border-radius:10px;padding:12px;display:flex;flex-direction:column;gap:8px;box-shadow:0 8px 24px rgba(0,0,0,.5);}';
  css += '.fh-card[hidden],.fh-drawer[hidden]{display:none;}.fh-row{display:flex;justify-content:space-between;align-items:center;gap:6px;flex-wrap:wrap;}';
  css += '.fh-input,.fh-select{width:100%;background:#1f2937;color:#f9fafb;border:1px solid #374151;border-radius:6px;padding:7px;font-size:12px;}';
  css += '.fh-input{min-height:68px;resize:vertical;}.fh-chips{display:flex;flex-wrap:wrap;gap:4px;}.fh-chip{background:#1f2937;border:1px solid #f59e0b;color:#fde68a;border-radius:999px;padding:2px 8px;font-size:10px;display:inline-flex;align-items:center;gap:4px;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}';
  css += '.fh-status{font-size:11px;color:#fcd34d;min-height:14px;}.fh-status.err{color:#fca5a5;}.fh-bar{display:flex;align-items:center;gap:6px;}';
  css += '.fh-drawer{position:fixed;top:0;right:0;bottom:0;width:360px;max-width:95vw;background:#111827;border-left:1px solid #f59e0b;padding:12px;display:flex;flex-direction:column;gap:8px;box-shadow:-8px 0 28px rgba(0,0,0,.55);z-index:2147483647;}';
  css += '.fh-list{flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:8px;}.fh-item{background:#1f2937;border:1px solid #374151;border-radius:8px;padding:8px;display:flex;flex-direction:column;gap:6px;font-size:11px;}';
  css += '.fh-item-head{display:flex;justify-content:space-between;align-items:center;gap:6px;cursor:pointer;}.fh-muted{color:#9ca3af;font-size:10px;word-break:break-word;}.fh-dot{width:8px;height:8px;border-radius:999px;background:#ef4444;display:inline-block;}';
  var html = '<style>' + css + '</style>';
  html += '<div class="fh-card" data-a="card" hidden>';
  html += '<div class="fh-row"><strong style="font-size:12px;color:#fbbf24">Debug Observation</strong><select class="fh-select" data-a="kind" style="width:auto;padding:3px 6px"><option value="note">note</option><option value="element">element</option><option value="idea">idea</option><option value="error">error</option><option value="network">network</option></select></div>';
  html += '<div class="fh-row"><button type="button" class="fh-btn" data-a="pick">Pick</button><button type="button" class="fh-btn" data-a="rec">Record</button><button type="button" class="fh-btn" data-a="stop">Stop</button><button type="button" class="fh-btn" data-a="drawer">History <span data-a="count"></span></button></div>';
  html += '<div class="fh-chips" data-a="chips"></div>';
  html += '<textarea class="fh-input" data-a="msg" placeholder="Describe bug or idea (or attach Pick/Trace)..."></textarea>';
  html += '<div class="fh-row"><span class="fh-status" data-a="status">Ready</span><button type="button" class="fh-pill" data-a="log">Log</button></div></div>';
  html += '<div class="fh-bar"><button type="button" class="fh-btn" data-a="drawer-quick">Observations <span data-a="qcount"></span></button><button type="button" class="fh-pill" data-a="toggle">Log Observation</button></div>';
  p.innerHTML = html;
  H.panelEl = p;
  H.updateUi = function (statusText, isErr) {
    var st = p.querySelector('[data-a=status]'), chips = p.querySelector('[data-a=chips]'), recBtn = p.querySelector('[data-a=rec]'), pickBtn = p.querySelector('[data-a=pick]'), kindEl = p.querySelector('[data-a=kind]');
    if (st && statusText !== undefined) { st.textContent = statusText; st.className = isErr ? 'fh-status err' : 'fh-status'; }
    if (pickBtn) pickBtn.className = (H.isPicking && H.isPicking()) ? 'fh-btn active' : 'fh-btn';
    if (recBtn) { recBtn.className = (H.isRecording && H.isRecording()) ? 'fh-btn active' : 'fh-btn'; recBtn.textContent = (H.isRecording && H.isRecording()) ? ('Recording (' + H.timeline.length + ')') : 'Record'; }
    if (kindEl && H.lastPick && kindEl.value === 'note') kindEl.value = 'element';
    if (chips) {
      var chtml = '';
      if (H.lastPick) chtml += '<span class="fh-chip" title="' + H.htmlEsc(H.lastPick.selector) + '">Target: ' + H.htmlEsc(H.lastPick.selector) + ' <button type="button" class="fh-btn" style="padding:0 4px" data-a="clear-pick">x</button></span>';
      if (H.recordingId) chtml += '<span class="fh-chip"><span class="fh-dot"></span> ' + H.htmlEsc(H.recordingId) + ' (' + H.timeline.length + ')</span>';
      else if (H.finished) chtml += '<span class="fh-chip">Trace: ' + H.htmlEsc(H.finished.id) + ' (' + H.finished.timeline.length + ') <button type="button" class="fh-btn" style="padding:0 4px" data-a="clear-trace">x</button></span>';
      chips.innerHTML = chtml;
    }
  };
  p.addEventListener('click', function (e) {
    var target = e.target, btn = target && target.closest ? target.closest('[data-a]') : target;
    var a = btn && btn.getAttribute ? btn.getAttribute('data-a') : null;
    if (!a) return;
    var msg = p.querySelector('[data-a=msg]'), card = p.querySelector('[data-a=card]'), kindEl = p.querySelector('[data-a=kind]');
    if (a === 'toggle') { H.panelOpen = !H.panelOpen; if (card) card.hidden = !H.panelOpen; if (H.panelOpen && msg && msg.focus) msg.focus(); }
    else if (a === 'pick') H.pick();
    else if (a === 'rec') H.record();
    else if (a === 'stop') H.stop();
    else if (a === 'clear-pick') { H.lastPick = null; H.updateUi('Cleared picked element'); }
    else if (a === 'clear-trace') { H.finished = null; H.updateUi('Cleared recorded trace'); }
    else if (a === 'drawer' || a === 'drawer-quick') { if (H.toggleDrawer) H.toggleDrawer(); }
    else if (a === 'log') {
      H.logObservation(kindEl ? kindEl.value : 'note', msg ? msg.value : '').then(function (res) {
        if (res && res.http >= 200 && res.http < 300 && msg) msg.value = '';
      }, function () { /* keep text for retry */ });
    }
  });
  (doc.body || doc.documentElement).appendChild(p);
  return p;
};
