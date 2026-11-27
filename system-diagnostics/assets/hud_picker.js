/* Frontier debug HUD, part 2 of 4: Pick Element + Soft Pause. Uses `H`, `win`, `doc` from hud_core.js. */
var pickState = { active: false, box: null, paused: [], held: [], origRaf: null, prev: null };

function pickTarget(e) {
  var path = e.composedPath ? e.composedPath() : [], el = path.length ? path[0] : e.target;
  return (el && el.nodeType === 1) ? el : e.target;
}
function ensureBox() {
  if (pickState.box) return pickState.box;
  var b = doc.createElement('div');
  b.id = '__frontier_hud_box__';
  b.setAttribute('style', 'position:fixed;pointer-events:none;z-index:2147483646;outline:2px solid #f59e0b;background:rgba(245,158,11,.15);display:none');
  (doc.body || doc.documentElement).appendChild(b);
  pickState.box = b;
  return b;
}
function onMove(e) {
  var el = pickTarget(e), r, b;
  if (!el || H.isHud(el)) return;
  r = el.getBoundingClientRect();
  b = ensureBox();
  b.style.cssText += ';display:block;left:' + r.left + 'px;top:' + r.top + 'px;width:' + r.width + 'px;height:' + r.height + 'px';
}
function onPickKey(e) {
  if (e && (e.key === 'Escape' || e.keyCode === 27)) {
    e.preventDefault(); e.stopPropagation();
    H.exitPick();
    if (H.updateUi) H.updateUi('Pick cancelled');
  }
}
function onPickClick(e) {
  var el = pickTarget(e), r;
  if (H.isHud(el)) return;
  e.preventDefault(); e.stopPropagation(); if (e.stopImmediatePropagation) e.stopImmediatePropagation();
  if (H.isSecret(el)) {
    H.lastPick = null;
    H.exitPick();
    if (H.updateUi) H.updateUi('Pick cancelled (secret input)', true);
    return;
  }
  r = el.getBoundingClientRect();
  H.lastPick = { selector: H.selectorFor(el), rect: { x: r.x, y: r.y, w: r.width, h: r.height }, attrs: H.attrsFor(el), element: el };
  H.exitPick();
  if (H.onPicked) H.onPicked(H.lastPick);
  if (H.updateUi) H.updateUi('Picked: ' + H.lastPick.selector);
}
function softPause() {
  var media = doc.querySelectorAll('video,audio'), i;
  for (i = 0; i < media.length; i++) { if (!media[i].paused) { pickState.paused.push(media[i]); media[i].pause(); } }
  pickState.origRaf = win.requestAnimationFrame;
  pickState.origCancel = win.cancelAnimationFrame;
  win.requestAnimationFrame = function (cb) { pickState.held.push(cb); return -pickState.held.length; };
  win.cancelAnimationFrame = function (id) { if (id < 0) pickState.held[-id - 1] = null; else if (pickState.origCancel) pickState.origCancel.call(win, id); };
}
function softResume() {
  var i, held = pickState.held;
  for (i = 0; i < pickState.paused.length; i++) { try { var pr = pickState.paused[i].play(); if (pr && pr.catch) pr.catch(function () {}); } catch (e) { /* ignore */ } }
  if (pickState.origRaf) win.requestAnimationFrame = pickState.origRaf;
  if (pickState.origCancel) win.cancelAnimationFrame = pickState.origCancel;
  pickState.paused = []; pickState.held = []; pickState.origRaf = null; pickState.origCancel = null;
  for (i = 0; i < held.length; i++) if (held[i]) win.requestAnimationFrame(held[i]);
}
function toggle(root, on) {
  var f = on ? 'addEventListener' : 'removeEventListener';
  root[f]('mousemove', onMove, true);
  root[f]('click', onPickClick, true);
  root[f]('mousedown', swallow, true);
  root[f]('mouseup', swallow, true);
  ['pointerdown', 'pointerup', 'touchstart', 'touchend'].forEach(function (n) { root[f](n, swallow, true); });
}
function swallow(e) { if (!H.isHud(pickTarget(e))) { e.preventDefault(); e.stopPropagation(); } }

H.pick = function () {
  if (pickState.active) return;
  pickState.active = true;
  H.attachFrames();
  H.roots.forEach(function (r) { toggle(r, true); });
  if (win.addEventListener) win.addEventListener('keydown', onPickKey, true);
  softPause();
  if (H.updateUi) H.updateUi('Click any element to pick (Esc to cancel)');
};
H.exitPick = function () {
  if (!pickState.active) return;
  pickState.active = false;
  H.roots.forEach(function (r) { toggle(r, false); });
  if (win.removeEventListener) win.removeEventListener('keydown', onPickKey, true);
  if (pickState.box && pickState.box.parentNode) pickState.box.parentNode.removeChild(pickState.box);
  pickState.box = null;
  softResume();
  if (H.updateUi) H.updateUi();
};
H.isPicking = function () { return pickState.active; };
H.onRoot = function (r) { if (pickState.active) toggle(r, true); if (H.onRecordRoot) H.onRecordRoot(r); };
