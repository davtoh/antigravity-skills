/* Node VM test driver for HUD v1.1 UX fixes (U1-U7). */
const vm = require('vm'), fs = require('fs');
const bundle = fs.readFileSync(process.argv[2], 'utf8');

function makeEl(tag, attrs) {
  const el = {
    tagName: tag.toUpperCase(), attrs: Object.assign({}, attrs || {}), children: [], style: {},
    nodeType: 1, value: (attrs && attrs.value) || '', parentNode: null, hidden: false,
    textContent: '', innerHTML: '', className: '', listeners: {},
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    addEventListener(n, f) { (this.listeners[n] = this.listeners[n] || []).push(f); },
    removeEventListener(n, f) { this.listeners[n] = (this.listeners[n] || []).filter(x => x !== f); },
    appendChild(c) { this.children.push(c); c.parentNode = this; return c; },
    getRootNode() { return fakeDoc; },
    getBoundingClientRect: () => ({ x: 10, y: 20, width: 30, height: 40 }),
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
  return el;
}

const panelNodes = {
  card: makeEl('div', { 'data-a': 'card' }),
  title: makeEl('strong', { 'data-a': 'title' }),
  kind: makeEl('select', { 'data-a': 'kind', value: 'note' }),
  msg: makeEl('textarea', { 'data-a': 'msg', value: '' }),
  status: makeEl('span', { 'data-a': 'status' }),
  chips: makeEl('div', { 'data-a': 'chips' }),
  log: makeEl('button', { 'data-a': 'log' }),
  'cancel-edit': makeEl('button', { 'data-a': 'cancel-edit' }),
  count: makeEl('span', { 'data-a': 'count' }),
  qcount: makeEl('span', { 'data-a': 'qcount' }),
  pick: makeEl('button', { 'data-a': 'pick' }),
  rec: makeEl('button', { 'data-a': 'rec' }),
};
panelNodes.card.hidden = true;
panelNodes['cancel-edit'].hidden = true;

const drawerNodes = {
  dstatus: makeEl('div', { 'data-a': 'dstatus', 'data-da': 'dstatus' }),
  list: makeEl('div', { 'data-a': 'list' }),
  filter: makeEl('select', { 'data-da': 'filter', value: 'active' }),
};
const cardNodes = {};
function ensureCard(id, kind, msg, relVal) {
  const card = makeEl('div', { 'data-obs-id': id });
  const kEl = makeEl('select', { 'data-da': 'kind', value: kind });
  const mEl = makeEl('textarea', { 'data-da': 'msg', value: msg });
  const sBtn = makeEl('button', { 'data-da': 'save', 'data-id': id });
  const rInp = makeEl('input', { 'data-da': 'rel-input', value: relVal || '' });
  [kEl, mEl, sBtn, rInp].forEach(c => card.appendChild(c));
  card._q = sel => ({ '[data-da=kind]': kEl, '[data-da=msg]': mEl, '[data-da=save]': sBtn, '[data-da=rel-input]': rInp }[sel] || null);
  cardNodes[id] = { card, kEl, mEl, sBtn, rInp };
  return cardNodes[id];
}

const docListeners = {};
const fakeDoc = {
  documentElement: makeEl('html'), body: makeEl('body'),
  createElement(tag) {
    const el = makeEl(tag);
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
  querySelector() { return null; }, querySelectorAll(sel) { return String(sel).startsWith('#') ? [1] : []; },
  addEventListener(n, f) { docListeners[n] = f; }, removeEventListener() {}, defaultView: null,
};

let store = [
  { id: 'OBS-001', kind: 'note', status: 'open', page_path: '/a', message: 'first note', selector: '#a1', elements: [{ selector: '#a1', rect: null, attrs: {} }], related_ids: [] },
  { id: 'OBS-002', kind: 'idea', status: 'dismissed', page_path: '/b', message: 'old idea', selector: '', elements: [], related_ids: [] },
];
const calls = [];
class FakeHeaders { constructor(i) { this.m = Object.assign({}, i || {}); } set(k, v) { this.m[k] = v; } }
function fakeFetch(url, opts) {
  const method = (opts && opts.method) || 'GET';
  const body = opts && opts.body ? JSON.parse(opts.body) : null;
  calls.push({ url: String(url), method, body });
  if (method === 'GET' && url.includes('/observations?')) {
    const st = new URL(url, 'http://x.test').searchParams.get('status') || 'active';
    const items = st === 'all' ? store.slice() : store.filter(o => st === 'active' ? o.status === 'open' : o.status === st);
    return Promise.resolve({ status: 200, json: () => Promise.resolve({ count: items.length, observations: items }) });
  }
  if (method === 'POST' && url.endsWith('/observation')) {
    const next = Object.assign({ id: 'OBS-003', status: 'open', elements: [], related_ids: [] }, body);
    store.push(next);
    return Promise.resolve({ status: 201, json: () => Promise.resolve({ id: next.id, status: 'open', deduplicated: false }) });
  }
  const m = String(url).match(/\/observations\/(OBS-\d+)$/);
  if (m && method === 'PATCH') {
    const it = store.find(o => o.id === m[1]);
    Object.assign(it, body);
    return Promise.resolve({ status: 200, json: () => Promise.resolve(Object.assign({}, it)) });
  }
  if (m && method === 'DELETE') {
    store = store.filter(o => o.id !== m[1]);
    return Promise.resolve({ status: 200, json: () => Promise.resolve({ deleted: true, id: m[1] }) });
  }
  return Promise.resolve({ status: 404, json: () => Promise.resolve({}) });
}

const win = {
  __FRONTIER_DEBUG__: true, document: fakeDoc,
  location: { pathname: '/dash', href: 'http://x.test/dash', origin: 'http://x.test' },
  console: { error() {} }, history: { pushState() {}, replaceState() {} }, Headers: FakeHeaders, URL,
  CSS: { escape: s => s }, addEventListener() {}, removeEventListener() {},
  crypto: require('crypto').webcrypto, requestAnimationFrame: () => 1, cancelAnimationFrame() {},
  fetch: fakeFetch,
};

vm.runInNewContext(bundle, { window: win });
const H = win.__FRONTIER_HUD__;
const flush = () => new Promise(r => setTimeout(r, 15));
const clickEl = (container, target) => (container.listeners.click || []).forEach(fn => fn({ target }));

(async () => {
  await flush();
  const out = {};
  // U6: initial active count populated before drawer opens
  out.u6InitCount = [panelNodes.count.textContent, panelNodes.qcount.textContent];

  // U3: multi-element composer pick preserves kind='note'
  const b1 = makeEl('button', { id: 'btn-1' }), b2 = makeEl('button', { id: 'btn-2' });
  const ev = t => ({ target: t, preventDefault() {}, stopPropagation() {} });
  H.pick(); docListeners.click(ev(b1));
  H.pick(); docListeners.click(ev(b2));
  out.u3KindAfterPick = panelNodes.kind.value;
  out.u3PickCount = H.picks.length;
  await H.logObservation('note', 'multi el note');
  await flush();
  const postCall = calls.find(c => c.method === 'POST');
  out.u3PostKind = postCall.body.kind;
  out.u3PostElements = postCall.body.elements.map(e => e.selector);
  out.u6CountAfterPost = panelNodes.qcount.textContent;

  // Open drawer & select OBS-001
  H.toggleDrawer(true);
  await flush();
  clickEl(H.drawerEl, makeEl('div', { 'data-da': 'select', 'data-id': 'OBS-001' }));

  // U2: draft preservation & Save *
  const c1 = ensureCard('OBS-001', 'note', 'draft text', 'obs-002');
  (H.drawerEl.listeners.input || []).forEach(fn => fn({ target: c1.mEl }));
  out.u2DirtyBtn = c1.sBtn.textContent;
  await H.refreshDrawer();
  out.u2PreservedHtml = drawerNodes.list.innerHTML.includes('draft text') && drawerNodes.list.innerHTML.includes('Save *');

  // U3 drawer attach-pick without overwriting kind
  H.addPick({ selector: '#a2', rect: { x: 1, y: 1, w: 2, h: 2 }, attrs: { tag: 'div' } });
  clickEl(H.drawerEl, makeEl('button', { 'data-da': 'attach-pick', 'data-id': 'OBS-001' }));
  await flush();
  const attachPatch = calls.filter(c => c.method === 'PATCH').pop();
  out.u3DrawerAttachHasKind = 'kind' in attachPatch.body;
  out.u3DrawerAttachEls = attachPatch.body.elements.map(e => e.selector);

  // U4: link, self-link reject, jump, unlink
  clickEl(H.drawerEl, makeEl('button', { 'data-da': 'link-rel', 'data-id': 'OBS-001' }));
  await flush();
  out.u4Linked = store.find(o => o.id === 'OBS-001').related_ids.slice();
  c1.rInp.value = 'OBS-001';
  const patchCountBeforeSelf = calls.filter(c => c.method === 'PATCH').length;
  clickEl(H.drawerEl, makeEl('button', { 'data-da': 'link-rel', 'data-id': 'OBS-001' }));
  out.u4SelfRejected = calls.filter(c => c.method === 'PATCH').length === patchCountBeforeSelf;
  clickEl(H.drawerEl, makeEl('span', { 'data-da': 'jump-rel', 'data-id': 'OBS-002' }));
  await flush();
  out.u4JumpFilterAndSel = [H.drawerState.filter, H.drawerState.selectedId];
  clickEl(H.drawerEl, makeEl('button', { 'data-da': 'unlink-rel', 'data-id': 'OBS-001', 'data-rel': 'OBS-002' }));
  await flush();
  out.u4Unlinked = store.find(o => o.id === 'OBS-001').related_ids.slice();

  // U1: Open in composer -> edit -> Save PATCH
  clickEl(H.drawerEl, makeEl('button', { 'data-da': 'open', 'data-id': 'OBS-001' }));
  out.u1EditState = { id: H.editingId, open: H.panelOpen, drawerOpen: H.drawerState.open, btn: panelNodes.log.textContent, cancelHidden: panelNodes['cancel-edit'].hidden, msg: panelNodes.msg.value };
  await H.logObservation('idea', 'edited via composer');
  await flush();
  const editPatch = calls.filter(c => c.method === 'PATCH').pop();
  out.u1Patch = { url: editPatch.url, kind: editPatch.body.kind, msg: editPatch.body.message, editingAfter: H.editingId };

  // U5: Dismissed filter + Dismiss + inline Undo + Reopen
  out.u5HasDismissedFilter = H.drawerEl.innerHTML.includes('value="dismissed"');
  H.toggleDrawer(true);
  await flush();
  clickEl(H.drawerEl, makeEl('button', { 'data-da': 'dismiss', 'data-id': 'OBS-001' }));
  await flush();
  out.u5UndoRendered = drawerNodes.dstatus.innerHTML.includes('data-da="undo"');
  clickEl(H.drawerEl, makeEl('button', { 'data-da': 'undo' }));
  await flush();
  out.u5AfterUndo = store.find(o => o.id === 'OBS-001').status;
  clickEl(H.drawerEl, makeEl('button', { 'data-da': 'reopen', 'data-id': 'OBS-002' }));
  await flush();
  out.u5AfterReopen = store.find(o => o.id === 'OBS-002').status;

  // U7: 2-step inline delete confirmation
  clickEl(H.drawerEl, makeEl('div', { 'data-da': 'select', 'data-id': 'OBS-003' }));
  const delBefore = calls.filter(c => c.method === 'DELETE').length;
  clickEl(H.drawerEl, makeEl('button', { 'data-da': 'delete', 'data-id': 'OBS-003' }));
  out.u7FirstClickDeletes = calls.filter(c => c.method === 'DELETE').length - delBefore;
  out.u7ConfirmVisible = drawerNodes.list.innerHTML.includes('delete-confirm');
  clickEl(H.drawerEl, makeEl('button', { 'data-da': 'delete-cancel', 'data-id': 'OBS-003' }));
  out.u7CancelCleared = H.drawerState.confirmDeleteId === null;
  clickEl(H.drawerEl, makeEl('button', { 'data-da': 'delete', 'data-id': 'OBS-003' }));
  clickEl(H.drawerEl, makeEl('button', { 'data-da': 'delete-confirm', 'data-id': 'OBS-003' }));
  await flush();
  out.u7ConfirmedDeletes = calls.filter(c => c.method === 'DELETE').length - delBefore;

  // U8: Confirmed/Resolved filters, provenance badges, one-click Confirm & Reopen
  out.u8HasFilters = H.drawerEl.innerHTML.includes('value="resolved"') && H.drawerEl.innerHTML.includes('value="confirmed"');
  store.push(
    { id: 'OBS-004', kind: 'element', status: 'resolved', page_path: '/grid', message: 'grid misaligned', elements: [], related_ids: [],
      resolution: 'Fixed CSS grid', resolved_plan: 'ui_plan', resolved_milestone: 'M1', base_commit: 'pending:abc1234' },
    { id: 'OBS-005', kind: 'network', status: 'confirmed', page_path: '/api', message: '500 on save', elements: [], related_ids: [],
      resolution: 'Fixed API', confirmed_note: 'Verified in Chrome', resolved_plan: 'api_plan', resolved_milestone: 'M2', linked_commit: 'def5678' }
  );
  H.drawerState.filter = 'resolved';
  await H.refreshDrawer();
  out.u8ResolvedHtml = drawerNodes.list.innerHTML;
  clickEl(H.drawerEl, makeEl('button', { 'data-da': 'confirm', 'data-id': 'OBS-004' }));
  await flush();
  out.u8AfterConfirm = store.find(o => o.id === 'OBS-004').status;
  H.drawerState.filter = 'confirmed';
  await H.refreshDrawer();
  out.u8ConfirmedHtml = drawerNodes.list.innerHTML;
  clickEl(H.drawerEl, makeEl('button', { 'data-da': 'reopen', 'data-id': 'OBS-005' }));
  await flush();
  out.u8AfterReopen = store.find(o => o.id === 'OBS-005').status;

  console.log(JSON.stringify(out));
})();
