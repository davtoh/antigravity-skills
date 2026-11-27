/* Frontier debug HUD, part 3 of 4: Record / Stop, request tagging, timeline. */
var rec = { on: false, origFetch: null, origOpen: null, origSend: null, origErr: null, origPush: null, origReplace: null };

function clickLog(e) {
  var el = (e.composedPath && e.composedPath()[0]) || e.target;
  if (el && el.nodeType === 1 && !H.isHud(el) && !H.isPicking() && !H.isSecret(el)) H.log('click', H.selectorFor(el));
}
function navLog() { H.log('nav', H.pagePath ? H.pagePath() : win.location.pathname); }
function errLog(e) { H.log('error', (e && e.message) || 'error'); }
function wrapFetch() {
  rec.origFetch = win.fetch;
  H.rawFetch = rec.origFetch;
  win.fetch = function (input, init) {
    var url = (input && input.url) || input, started = Date.now(), headers, opts = init || {};
    if (String(url).indexOf(H.endpoint) !== 0 && String(url).indexOf(H.baseEndpoint + '/observations') !== 0 && H.recordingId && H.sameOrigin(url)) {
      headers = new win.Headers(opts.headers || (input && input.headers) || undefined);
      headers.set('X-Debug-Recording-Id', H.recordingId);
      opts = Object.assign({}, opts, { headers: headers });
    }
    return rec.origFetch.call(win, input, opts).then(function (r) {
      H.log('fetch', H.urlTarget(url), { status: r.status, ms: Date.now() - started }); return r;
    }, function (err) { H.log('fetch', H.urlTarget(url), { status: 0, ms: Date.now() - started }); throw err; });
  };
}
function wrapXhr() {
  var proto = win.XMLHttpRequest && win.XMLHttpRequest.prototype;
  if (!proto) return;
  rec.origOpen = proto.open; rec.origSend = proto.send;
  proto.open = function () { this.__fhud_url = arguments[1]; return rec.origOpen.apply(this, arguments); };
  proto.send = function () {
    var x = this, started = Date.now();
    if (x.__fhud_url && H.sameOrigin(x.__fhud_url)) { try { x.setRequestHeader('X-Debug-Recording-Id', H.recordingId); } catch (e) { /* ignore */ } }
    if (x.__fhud_url) x.addEventListener('loadend', function () { H.log('fetch', H.urlTarget(x.__fhud_url), { status: x.status, ms: Date.now() - started }); });
    return rec.origSend.apply(this, arguments);
  };
}
function wrapConsole() {
  rec.origErr = win.console.error;
  win.console.error = function () { H.log('console', Array.prototype.slice.call(arguments).join(' ').slice(0, 200)); return rec.origErr.apply(win.console, arguments); };
}
function wrapHistory() {
  var h = win.history;
  rec.origPush = h.pushState; rec.origReplace = h.replaceState;
  h.pushState = function () { var r = rec.origPush.apply(h, arguments); navLog(); return r; };
  h.replaceState = function () { var r = rec.origReplace.apply(h, arguments); navLog(); return r; };
}
H.onRecordRoot = function (r) { if (rec.on) r.addEventListener('click', clickLog, true); };

H.record = function () {
  if (rec.on) return H.recordingId;
  rec.on = true;
  H.recordingId = 'rec-' + H.hex(3);
  H.timeline = []; H.t0 = Date.now(); H.finished = null;
  H.window = { started_at: new Date().toISOString() };
  H.attachFrames();
  H.roots.forEach(function (r) { r.addEventListener('click', clickLog, true); });
  win.addEventListener('error', errLog); win.addEventListener('popstate', navLog); win.addEventListener('hashchange', navLog);
  wrapFetch(); wrapXhr(); wrapConsole(); wrapHistory();
  if (H.updateUi) H.updateUi('Recording ' + H.recordingId + '...');
  return H.recordingId;
};
H.stop = function () {
  if (!rec.on) return null;
  rec.on = false;
  H.window.stopped_at = new Date().toISOString();
  H.finished = { id: H.recordingId, window: H.window, timeline: H.timeline };
  H.roots.forEach(function (r) { r.removeEventListener('click', clickLog, true); });
  win.removeEventListener('error', errLog); win.removeEventListener('popstate', navLog); win.removeEventListener('hashchange', navLog);
  win.fetch = rec.origFetch; win.console.error = rec.origErr;
  win.history.pushState = rec.origPush; win.history.replaceState = rec.origReplace;
  if (win.XMLHttpRequest) { win.XMLHttpRequest.prototype.open = rec.origOpen; win.XMLHttpRequest.prototype.send = rec.origSend; }
  var id = H.recordingId;
  H.recordingId = null;
  if (H.updateUi) H.updateUi('Stopped ' + id + ' (' + H.finished.timeline.length + ' events)');
  return id;
};
H.isRecording = function () { return rec.on; };
