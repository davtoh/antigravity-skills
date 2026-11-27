/* Node VM test driver for HUD trace chips, export/import, and collapsed dirty badge. */
const vm = require('vm'), fs = require('fs');
const bundle = fs.readFileSync(process.argv[2], 'utf8');

function makeEl(tag, attrs) {
  return {
    tagName: tag.toUpperCase(), attrs: Object.assign({}, attrs || {}), children: [], style: {},
    nodeType: 1, value: (attrs && attrs.value) || '', parentNode: null, hidden: false,
    textContent: '', innerHTML: '', className: '', listeners: {}, files: [], clicked: 0,
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    addEventListener(n, f) { (this.listeners[n] = this.listeners[n] || []).push(f); },
    removeEventListener(n, f) { this.listeners[n] = (this.listeners[n] || []).filter(x => x !== f); },
    appendChild(c) { this.children.push(c); c.parentNode = this; return c; },
    removeChild(c) { this.children = this.children.filter(x => x !== c); c.parentNode = null; return c; },
    click() { this.clicked++; },
    getRootNode() { return fakeDoc; },
    getBoundingClientRect: () => ({ x: 1, y: 2, width: 3, height: 4 }),
    closest(sel) {
      let cur = this;
      while (cur) {
        const m = sel.match(/^\[([a-z-]+)(?:="([^"]*)")?\]$/);
        if (m && cur.getAttribute && (m[2] !== undefined ? cur.getAttribute(m[1]) === m[2] : cur.getAttribute(m[1]) !== null)) return cur;
        cur = cur.parentNode;
      }
      return null;
    },
    querySelector(sel) { return this._q ? this._q(sel) : null; },
    querySelectorAll() { return []; },
  };
}

const panelNodes = {
  card: makeEl('div', { 'data-a': 'card' }), title: makeEl('strong', { 'data-a': 'title' }),
  kind: makeEl('select', { 'data-a': 'kind', value: 'note' }), msg: makeEl('textarea', { 'data-a': 'msg', value: '' }),
  status: makeEl('span', { 'data-a': 'status' }), chips: makeEl('div', { 'data-a': 'chips' }),
  log: makeEl('button', { 'data-a': 'log' }), 'cancel-edit': makeEl('button', { 'data-a': 'cancel-edit' }),
  count: makeEl('span', { 'data-a': 'count' }), qcount: makeEl('span', { 'data-a': 'qcount' }),
};
const drawerNodes = {
  dstatus: makeEl('div', { 'data-a': 'dstatus', 'data-da': 'dstatus' }),
  list: makeEl('div', { 'data-a': 'list' }),
  filter: makeEl('select', { 'data-da': 'filter', value: 'active' }),
  'import-file': makeEl('input', { 'data-da': 'import-file', type: 'file' }),
};
const cardNodes = {};
function ensureCard(id, kind, msg) {
  const card = makeEl('div', { 'data-obs-id': id });
  const kEl = makeEl('select', { 'data-da': 'kind', value: kind });
  const mEl = makeEl('textarea', { 'data-da': 'msg', value: msg });
  const sBtn = makeEl('button', { 'data-da': 'save', 'data-id': id });
  [kEl, mEl, sBtn].forEach(c => card.appendChild(c));
  card._q = sel => ({ '[data-da=kind]': kEl, '[data-da=msg]': mEl, '[data-da=save]': sBtn }[sel] || null);
  cardNodes[id] = { card, kEl, mEl, sBtn };
  return cardNodes[id];
}

const anchors = [];
const fakeDoc = {
  documentElement: makeEl('html'), body: makeEl('body'),
  createElement(tag) {
    const el = makeEl(tag);
    if (tag === 'a') anchors.push(el);
    el._q = sel => {
      const mA = sel.match(/^\[data-a=([a-z-]+)\]$/);
      if (mA) return (el.className === 'fh-drawer' ? drawerNodes[mA[1]] : panelNodes[mA[1]]) || null;
      const mD = sel.match(/^\[data-da=([a-z-]+)\]$/);
      if (mD) return drawerNodes[mD[1]] || null;
      const mO = sel.match(/^\[data-obs-id="([^"]+)"\]$/);
      if (mO && cardNodes[mO[1]]) return cardNodes[mO[1]].card;
      return null;
    };
    return el;
  },
  querySelector() { return null; }, querySelectorAll() { return []; },
  addEventListener() {}, removeEventListener() {}, defaultView: null,
};

let store = [
  {
    id: 'OBS-001', kind: 'idea', status: 'open', page_path: '/#live', message: 'traced obs',
    selector: '#live-stream-img', elements: [{ selector: '#live-stream-img', rect: null, attrs: {} }],
    related_ids: [], recording_id: 'rec-abc123',
    window: { started_at: '2026-11-27T00:00:00Z', stopped_at: '2026-11-27T00:00:03Z' },
    timeline: [{ t: 10, type: 'click', target: '#a' }], trace_count: 12,
  },
  { id: 'OBS-002', kind: 'note', status: 'open', page_path: '/#review', message: 'plain obs', selector: '', elements: [], related_ids: [] },
];
const calls = [], blobs = [];
class FakeBlob { constructor(parts, opts) { this.text = parts.join(''); this.type = opts && opts.type; blobs.push(this); } }
class FakeHeaders { constructor(i) { this.m = Object.assign({}, i || {}); } set(k, v) { this.m[k] = v; } }
function fakeFetch(url, opts) {
  const method = (opts && opts.method) || 'GET';
  const body = opts && opts.body ? JSON.parse(opts.body) : null;
  calls.push({ url: String(url), method, body });
  if (method === 'GET' && url.includes('/observations/export')) {
    return Promise.resolve({ status: 200, json: () => Promise.resolve({ schema: 1, count: store.length, observations: store.slice() }) });
  }
  if (method === 'POST' && url.endsWith('/observations/import')) {
    const incoming = (body && body.observations) || [];
    store.push({ id: 'OBS-003', kind: incoming[0].kind || 'note', status: 'open', page_path: '/', message: incoming[0].message || '', selector: '', elements: [], related_ids: [] });
    return Promise.resolve({ status: 200, json: () => Promise.resolve({ schema: 1, imported: 1, updated: 0, skipped: 1, total: store.length }) });
  }
  if (method === 'GET' && url.includes('/observations?')) {
    return Promise.resolve({ status: 200, json: () => Promise.resolve({ count: store.length, observations: store.slice() }) });
  }
  const m = String(url).match(/\/observations\/(OBS-\d+)$/);
  if (m && method === 'PATCH') {
    const it = store.find(o => o.id === m[1]);
    Object.assign(it, body);
    return Promise.resolve({ status: 200, json: () => Promise.resolve(Object.assign({}, it)) });
  }
  return Promise.resolve({ status: 404, json: () => Promise.resolve({}) });
}

const revoked = [];
const win = {
  __FRONTIER_DEBUG__: true, document: fakeDoc,
  location: { pathname: '/dash', href: 'http://x.test/dash', origin: 'http://x.test' },
  console: { error() {} }, history: { pushState() {}, replaceState() {} }, Headers: FakeHeaders,
  URL: Object.assign(function (u, b) { return new URL(u, b); }, { createObjectURL: () => 'blob:mock-1', revokeObjectURL: u => revoked.push(u) }),
  Blob: FakeBlob, CSS: { escape: s => s }, addEventListener() {}, removeEventListener() {},
  crypto: require('crypto').webcrypto, requestAnimationFrame: () => 1, cancelAnimationFrame() {}, fetch: fakeFetch,
};

vm.runInNewContext(bundle, { window: win });
const H = win.__FRONTIER_HUD__;
const flush = () => new Promise(r => setTimeout(r, 15));
const clickEl = (c, t) => (c.listeners.click || []).forEach(fn => fn({ target: t }));

(async () => {
  await flush();
  const out = {};
  H.toggleDrawer(true);
  await flush();
  const listHtml = drawerNodes.list.innerHTML;
  out.cardHasTraceChip = listHtml.includes('data-da="trace-chip"') && listHtml.includes('Trace: rec-abc123 (12)');
  out.plainCardCount = (listHtml.match(/data-da="trace-chip"/g) || []).length;

  // OBS-022: edit draft while expanded, then collapse card -> collapsed header displays * Unsaved
  clickEl(H.drawerEl, makeEl('div', { 'data-da': 'select', 'data-id': 'OBS-002' }));
  const c2 = ensureCard('OBS-002', 'note', 'unsaved edit');
  (H.drawerEl.listeners.input || []).forEach(fn => fn({ target: c2.mEl }));
  clickEl(H.drawerEl, makeEl('div', { 'data-da': 'select', 'data-id': 'OBS-002' }));
  const collapsedHtml = drawerNodes.list.innerHTML;
  out.collapsedSelectedNull = H.drawerState.selectedId === null;
  out.collapsedDirtyBadge = collapsedHtml.includes('data-dirty="true"') && collapsedHtml.includes('data-da="dirty-badge"') && collapsedHtml.includes('* Unsaved');
  clickEl(H.drawerEl, makeEl('div', { 'data-da': 'select', 'data-id': 'OBS-002' }));
  clickEl(H.drawerEl, makeEl('button', { 'data-da': 'save', 'data-id': 'OBS-002' }));
  await flush();
  out.dirtyClearedAfterSave = !drawerNodes.list.innerHTML.includes('data-da="dirty-badge"');

  // OBS-020: open traced observation in composer -> trace restored without overwriting timeline on message edit
  clickEl(H.drawerEl, makeEl('button', { 'data-da': 'open', 'data-id': 'OBS-001' }));
  out.restoredFinished = H.finished ? { id: H.finished.id, count: H.finished.count, restored: H.finished.restored } : null;
  out.composerHasTraceChip = panelNodes.chips.innerHTML.includes('Trace: rec-abc123 (12)');
  await H.logObservation('idea', 'updated without clobbering timeline');
  await flush();
  const patchKeep = calls.filter(c => c.method === 'PATCH').pop();
  out.patchKeepHasTimeline = 'timeline' in patchKeep.body || 'recording_id' in patchKeep.body;

  // Clear restored trace in composer and save -> clears recording_id/window/timeline
  H.toggleDrawer(true);
  await flush();
  clickEl(H.drawerEl, makeEl('button', { 'data-da': 'open', 'data-id': 'OBS-001' }));
  clickEl(H.panelEl, makeEl('button', { 'data-a': 'clear-trace' }));
  await H.logObservation('idea', 'cleared trace');
  await flush();
  const patchCleared = calls.filter(c => c.method === 'PATCH').pop();
  out.patchClearedTrace = { rid: patchCleared.body.recording_id, win: patchCleared.body.window, tl: patchCleared.body.timeline };

  // OBS-021: Export & Import via drawer controls
  H.toggleDrawer(true);
  await flush();
  out.hasExportImportBtns = H.drawerEl.innerHTML.includes('data-da="export"') && H.drawerEl.innerHTML.includes('data-da="import"');
  clickEl(H.drawerEl, makeEl('button', { 'data-da': 'export' }));
  await flush();
  const exportedJson = blobs.length ? JSON.parse(blobs[0].text) : {};
  out.exportOk = !('http' in exportedJson) && exportedJson.count === 2 && anchors.length > 0 && anchors[0].download === 'observations-export.json' && anchors[0].clicked === 1 && revoked.length === 1;
  out.exportStatus = drawerNodes.dstatus.textContent;

  drawerNodes['import-file'].files = [{ text: () => Promise.resolve('{bad json') }];
  (H.drawerEl.listeners.change || []).forEach(fn => fn({ target: drawerNodes['import-file'] }));
  await flush();
  out.badImportStatus = drawerNodes.dstatus.textContent;
  out.postCallsAfterBad = calls.filter(c => c.method === 'POST').length;

  drawerNodes['import-file'].files = [{ text: () => Promise.resolve(JSON.stringify({ observations: [{ kind: 'note', message: 'imported item' }] })) }];
  (H.drawerEl.listeners.change || []).forEach(fn => fn({ target: drawerNodes['import-file'] }));
  await flush();
  out.importStatus = drawerNodes.dstatus.textContent;
  out.postCallsAfterGood = calls.filter(c => c.method === 'POST').length;
  out.drawerCountAfterImport = store.length;
  console.log(JSON.stringify(out));
})();
