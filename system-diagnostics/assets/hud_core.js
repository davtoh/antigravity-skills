/* Frontier debug HUD, part 1 of 3: core helpers. Concatenated by observation_assets.hud_bundle()
 * inside a gate wrapper that defines `H` (shared namespace) and `win`. Plain ES5, no dependencies. */
var doc = win.document;
H.endpoint = win.__FRONTIER_OBS_ENDPOINT__ || '/api/diagnostics/observation';
H.roots = [doc];
H.recordingId = null;
H.finished = null;
H.timeline = [];
H.t0 = 0;
H.lastPick = null;
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
/* Unique selector inside one tree scope (document or shadow root): #id, [data-testid], else short path. */
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
/* Selector with ` >>> ` crossing open shadow roots and same-origin iframes. */
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
  if (H.recordingId) { H.timeline.push(ev); if (H.timeline.length > 50) H.timeline.shift(); }
};
H.scrub = function (obj) {
  var k;
  if (Array.isArray(obj)) { obj.forEach(H.scrub); return obj; }
  if (obj && typeof obj === 'object') { for (k in obj) { if (FORBIDDEN[k.toLowerCase()]) delete obj[k]; else H.scrub(obj[k]); } }
  return obj;
};
H.buildRecord = function (kind, message) {
  var p = H.lastPick || {}, rec = {
    schema: 1, ts: new Date().toISOString(), kind: kind, page_path: win.location.pathname,
    message: String(message || '').slice(0, 500)
  };
  if (p.selector) { rec.selector = p.selector; rec.rect = p.rect; rec.attrs = p.attrs; }
  var run = H.recordingId ? { id: H.recordingId, window: H.window, timeline: H.timeline } : H.finished;
  if (run) { rec.recording_id = run.id; rec.window = run.window || {}; rec.timeline = run.timeline.slice(-50); }
  return H.scrub(rec);
};
H.post = function (rec) {
  var send = H.rawFetch || win.fetch;
  return send.call(win, H.endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(rec) })
    .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { j.http = r.status; return j; }); });
};
H.logObservation = function (kind, message) {
  var rec = H.buildRecord(kind || 'note', message);
  return H.post(rec).then(function (res) {
    if (res && res.http >= 200 && res.http < 300) H.finished = null; /* attaches to one successful Log only */
    return res;
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
  var p = doc.createElement('div'), html = '';
  p.id = '__frontier_hud__';
  p.setAttribute('style', 'position:fixed;right:8px;bottom:8px;z-index:2147483647;background:#111;color:#eee;font:12px sans-serif;padding:6px;border-radius:6px;display:flex;gap:4px');
  html += '<button data-a="pick">Pick</button><button data-a="rec">Record</button><button data-a="stop">Stop</button>';
  html += '<input data-a="msg" placeholder="message" size="16"><button data-a="log">Log</button>';
  p.innerHTML = html;
  p.addEventListener('click', function (e) {
    var a = e.target.getAttribute && e.target.getAttribute('data-a'), msg = p.querySelector('[data-a=msg]');
    if (a === 'pick') H.pick(); else if (a === 'rec') H.record(); else if (a === 'stop') H.stop();
    else if (a === 'log') H.logObservation(H.lastPick ? 'element' : 'note', msg.value).then(function () { msg.value = ''; }, function () { /* keep text for retry */ });
  });
  (doc.body || doc.documentElement).appendChild(p);
  return p;
};
