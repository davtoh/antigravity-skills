/* Node VM test driver for HUD v1.2 UX fixes (OBS-037, OBS-042, OBS-044, OBS-045, OBS-046). */
const vm = require('vm'), fs = require('fs');
const bundle = fs.readFileSync(process.argv[2], 'utf8');

function makeEl(tag, attrs) {
  const el = {
    tagName: tag.toUpperCase(), attrs: Object.assign({}, attrs || {}), children: [], style: {},
    nodeType: 1, value: (attrs && attrs.value) || '', parentNode: null, hidden: false,
    textContent: '', innerHTML: '', className: '', listeners: {}, captured: [], released: [],
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    addEventListener(n, f) { (this.listeners[n] = this.listeners[n] || []).push(f); },
    removeEventListener(n, f) { this.listeners[n] = (this.listeners[n] || []).filter(x => x !== f); },
    appendChild(c) { this.children.push(c); c.parentNode = this; return c; },
    setPointerCapture(id) { this.captured.push(id); },
    releasePointerCapture(id) { this.released.push(id); },
    getRootNode() { return fakeDoc; },
    getBoundingClientRect: () => ({ left: 800, top: 450, x: 800, y: 450, width: 320, height: 200 }),
    closest(sel) {
      let cur = this;
      const parts = sel.split(',').map(s => s.trim());
      while (cur) {
        for (const part of parts) {
          const m = part.match(/^\[([a-z-]+)(?:="([^"]*)")?\]$/);
          if (m && cur.getAttribute && (m[2] !== undefined ? cur.getAttribute(m[1]) === m[2] : cur.getAttribute(m[1]) !== null)) return cur;
        }
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
const drawerNodes = {
  dstatus: makeEl('div', { 'data-a': 'dstatus', 'data-da': 'dstatus' }),
  list: makeEl('div', { 'data-a': 'list' }),
  filter: makeEl('select', { 'data-da': 'filter', value: 'active' }),
  sort: makeEl('button', { 'data-da': 'sort' }),
  search: makeEl('input', { 'data-da': 'search', value: '' }),
};

const fakeDoc = {
  documentElement: Object.assign(makeEl('html'), { clientWidth: 1200, clientHeight: 700 }),
  body: makeEl('body'),
  createElement(tag) {
    const el = makeEl(tag);
    el._q = sel => {
      const mA = sel.match(/^\[data-a=([a-z-]+)\]$/);
      if (mA) return (el.className === 'fh-drawer' ? drawerNodes[mA[1]] : panelNodes[mA[1]]) || null;
      const mD = sel.match(/^\[data-da=([a-z-]+)\]$/);
      if (mD) return drawerNodes[mD[1]] || null;
      return null;
    };
    return el;
  },
  querySelector() { return null; }, querySelectorAll() { return []; },
  addEventListener() {}, removeEventListener() {}, defaultView: null,
};

const longSel = 'main.workspace > ' + 'div.nested-panel > '.repeat(9) + 'button#deep-action-btn';
const store = [
  { id: 'OBS-001', kind: 'element', status: 'open', page_path: '/a', message: 'Long selector overflow issue with extra details for truncation check in datalist',
    selector: longSel, elements: [{ selector: longSel, rect: null, attrs: {} }], related_ids: [], last_seen: '2026-01-01T00:00:00Z' },
  { id: 'OBS-002', kind: 'network', status: 'triaged', page_path: '/b', message: 'API timeout on save',
    selector: '#sidebar-btn', elements: [{ selector: '#sidebar-btn', rect: null, attrs: {} }], related_ids: ['OBS-003'], last_seen: '2026-01-03T00:00:00Z' },
  { id: 'OBS-003', kind: 'idea', status: 'in_progress', page_path: '/c', message: 'Add keyboard shortcut',
    selector: '#toolbar', elements: [{ selector: '#toolbar', rect: null, attrs: {} }], related_ids: [], last_seen: '2026-01-02T00:00:00Z' },
];

class FakeHeaders { constructor(i) { this.m = Object.assign({}, i || {}); } set(k, v) { this.m[k] = v; } }
const winListeners = {};
const win = {
  __FRONTIER_DEBUG__: true, document: fakeDoc, innerWidth: 1200, innerHeight: 700,
  location: { pathname: '/dash', href: 'http://x.test/dash', origin: 'http://x.test' },
  console: { error() {} }, history: { pushState() {}, replaceState() {} }, Headers: FakeHeaders, URL,
  CSS: { escape: s => s },
  addEventListener(n, f) { (winListeners[n] = winListeners[n] || []).push(f); },
  removeEventListener() {},
  crypto: require('crypto').webcrypto, requestAnimationFrame: () => 1, cancelAnimationFrame() {},
  fetch: (url, opts) => {
    const method = (opts && opts.method) || 'GET';
    if (method === 'GET' && url.includes('/observations?')) {
      return Promise.resolve({ status: 200, json: () => Promise.resolve({ count: store.length, observations: store.slice() }) });
    }
    return Promise.resolve({ status: 200, json: () => Promise.resolve({}) });
  },
};

vm.runInNewContext(bundle, { window: win });
const H = win.__FRONTIER_HUD__;
const flush = () => new Promise(r => setTimeout(r, 15));
const emit = (el, name, ev) => (el.listeners[name] || []).forEach(fn => fn(ev));
const cardIds = html => [...html.matchAll(/data-obs-id="(OBS-\d+)"/g)].map(m => m[1]);

(async () => {
  await flush();
  const out = {};

  // OBS-044: 180+ char selector chip label ellipsis + flex-shrink:0 remove button
  H.addPick({ selector: longSel, rect: null, attrs: {} });
  H.updateUi();
  out.longSelLen = longSel.length;
  out.panelCssHasChipLabel = H.panelEl.innerHTML.includes('.fh-chip-label{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1 1 auto;}')
    && H.panelEl.innerHTML.includes('.fh-chip .fh-btn{flex-shrink:0;}');
  out.composerChipHtml = panelNodes.chips.innerHTML;

  // OBS-037: filter options include active, open, triaged, in_progress, resolved, confirmed, dismissed, all
  out.filterOptions = ['active', 'open', 'triaged', 'in_progress', 'resolved', 'confirmed', 'dismissed', 'all']
    .every(v => H.drawerEl.innerHTML.includes('value="' + v + '"'));

  // OBS-045: stable ID sort + sort toggle + text search
  H.toggleDrawer(true);
  await flush();
  out.orderDefaultIdDesc = cardIds(drawerNodes.list.innerHTML);
  out.sortLabelInit = drawerNodes.sort.textContent;
  emit(H.drawerEl, 'click', { target: drawerNodes.sort });
  out.orderIdAsc = cardIds(drawerNodes.list.innerHTML);
  out.sortLabelAsc = drawerNodes.sort.textContent;
  emit(H.drawerEl, 'click', { target: drawerNodes.sort });
  out.orderRecent = cardIds(drawerNodes.list.innerHTML);
  out.sortLabelRecent = drawerNodes.sort.textContent;
  emit(H.drawerEl, 'click', { target: drawerNodes.sort });
  out.orderBackIdDesc = cardIds(drawerNodes.list.innerHTML);

  // Search by ID, selector, message, then clear
  drawerNodes.search.value = 'OBS-002';
  emit(H.drawerEl, 'input', { target: drawerNodes.search });
  out.searchById = cardIds(drawerNodes.list.innerHTML);
  drawerNodes.search.value = 'sidebar-btn';
  emit(H.drawerEl, 'input', { target: drawerNodes.search });
  out.searchBySelector = cardIds(drawerNodes.list.innerHTML);
  drawerNodes.search.value = 'shortcut';
  emit(H.drawerEl, 'input', { target: drawerNodes.search });
  out.searchByMessage = cardIds(drawerNodes.list.innerHTML);
  drawerNodes.search.value = '';
  emit(H.drawerEl, 'input', { target: drawerNodes.search });
  out.searchCleared = cardIds(drawerNodes.list.innerHTML);

  // OBS-044 in drawer + OBS-046 rel-input datalist (expand OBS-002 which links OBS-003)
  emit(H.drawerEl, 'click', { target: makeEl('div', { 'data-da': 'select', 'data-id': 'OBS-002' }) });
  out.drawerExpandedHtml = drawerNodes.list.innerHTML;
  emit(H.drawerEl, 'click', { target: makeEl('div', { 'data-da': 'select', 'data-id': 'OBS-001' }) });
  out.drawerChipHtml = drawerNodes.list.innerHTML;

  // OBS-042: draggable card with pointer capture + viewport clamping
  const titleEl = panelNodes.title;
  emit(H.panelEl, 'pointerdown', { target: titleEl, pointerId: 7, button: 0, clientX: 900, clientY: 500, preventDefault() {} });
  emit(H.panelEl, 'pointermove', { pointerId: 7, clientX: 700, clientY: 350 });
  out.dragMoved = { left: H.panelEl.style.left, top: H.panelEl.style.top, right: H.panelEl.style.right, bottom: H.panelEl.style.bottom };
  emit(H.panelEl, 'pointermove', { pointerId: 7, clientX: -500, clientY: -500 });
  out.dragClampMin = { left: H.panelEl.style.left, top: H.panelEl.style.top };
  emit(H.panelEl, 'pointermove', { pointerId: 7, clientX: 2500, clientY: 2500 });
  out.dragClampMax = { left: H.panelEl.style.left, top: H.panelEl.style.top };
  emit(H.panelEl, 'pointerup', { pointerId: 7 });
  emit(H.panelEl, 'pointermove', { pointerId: 7, clientX: 100, clientY: 100 });
  out.dragAfterUp = { left: H.panelEl.style.left, top: H.panelEl.style.top };
  out.dragCapture = { captured: titleEl.captured, released: titleEl.released };

  console.log(JSON.stringify(out));
})();
