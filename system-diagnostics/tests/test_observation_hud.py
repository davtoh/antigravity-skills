"""HUD logic tests: run the bundle in a Node VM against a tiny fake DOM (skips without node)."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import observation_assets  # noqa: E402

DRIVER = r"""
const vm = require('vm'), fs = require('fs');
const bundle = fs.readFileSync(process.argv[2], 'utf8'), mode = process.argv[3];
const touched = [];
function stubEl(tag, attrs) {
  const a = attrs || {};
  return { tagName: tag.toUpperCase(), children: [], style: {}, nodeType: 1, value: a.value, parentNode: null,
    getAttribute: k => (k in a ? a[k] : null), setAttribute() {}, addEventListener() {}, removeEventListener() {},
    appendChild(c) { this.children.push(c); c.parentNode = this; return c; }, querySelector() { return null; },
    querySelectorAll() { return []; }, getRootNode() { return fakeDoc; }, getBoundingClientRect: () => ({x: 1, y: 2, width: 3, height: 4}) };
}
const fakeDoc = { documentElement: stubEl('html'), body: stubEl('body'), createElement: t => stubEl(t),
  querySelector() { return null; }, querySelectorAll() { return []; }, addEventListener() {}, removeEventListener() {}, defaultView: null };
let calls = [];
class FakeHeaders { constructor(i) { this.m = Object.assign({}, i || {}); } set(k, v) { this.m[k] = v; } }
const win = { document: fakeDoc, location: { pathname: '/dash', href: 'http://x.test/dash', origin: 'http://x.test' }, console: { error() {} },
  history: { pushState() {}, replaceState() {} }, Headers: FakeHeaders, URL, CSS: { escape: s => s },
  addEventListener() {}, removeEventListener() {}, crypto: require('crypto').webcrypto, requestAnimationFrame: cb => 1,
  fetch: (u, o) => { calls.push([String(u), o]); return Promise.resolve({ status: 200, json: () => Promise.resolve({}) }); } };
const origFetch = win.fetch;
if (mode === 'pick') {
  win.__FRONTIER_DEBUG__ = true;
  const hs = {}; fakeDoc.addEventListener = (n, f) => { hs[n] = f; };
  win.cancelAnimationFrame = () => {};
  vm.runInNewContext(bundle, { window: win });
  const H = win.__FRONTIER_HUD__, out = {};
  const ev = t => ({ target: t, called: [], preventDefault() { this.called.push('pd'); }, stopPropagation() { this.called.push('sp'); } });
  const btn = stubEl('button', { id: 'save' });
  H.pick(); let e = ev(btn); hs.click(e);
  out.suppressed = e.called; out.rect = H.lastPick.rect; out.attrs = H.lastPick.attrs; out.pickingAfter = H.isPicking();
  H.pick(); e = ev(stubEl('input', { type: 'password' })); hs.click(e);
  out.lastPickAfterPassword = H.lastPick;
  H.pick(); const id = win.requestAnimationFrame(() => {}); win.cancelAnimationFrame(id); H.exitPick();
  out.rafId = id;
  console.log(JSON.stringify(out));
} else if (mode === 'extra') {
  win.__FRONTIER_DEBUG__ = true; win.__FRONTIER_OBS_ENDPOINT__ = '/custom/obs'; win.location.origin = 'http://x.test';
  const handlers = {}; win.addEventListener = (n, f) => { handlers[n] = f; };
  const xhrs = []; function FakeXhr() { this.h = {}; this.l = {}; }
  FakeXhr.prototype.open = function () {}; FakeXhr.prototype.setRequestHeader = function (k, v) { this.h[k] = v; };
  FakeXhr.prototype.addEventListener = function (n, f) { this.l[n] = f; }; FakeXhr.prototype.send = function () { xhrs.push(this); };
  win.XMLHttpRequest = FakeXhr;
  const errs = []; win.console.error = function () { errs.push(1); };
  vm.runInNewContext(bundle, { window: win });
  const H = win.__FRONTIER_HUD__, out = { endpoint: H.endpoint };
  H.record();
  const a = new win.XMLHttpRequest(); a.open('GET', '/api/a?x=1'); a.send();
  const b = new win.XMLHttpRequest(); b.open('GET', 'https://other.test/api'); b.send();
  out.xhrSame = a.h['X-Debug-Recording-Id'] === H.recordingId; out.xhrCross = 'X-Debug-Recording-Id' in b.h;
  a.status = 204; a.l.loadend();
  win.console.error('boom', 1); handlers.error({ message: 'oops' }); win.history.pushState({}, '', '/n'); handlers.popstate();
  out.types = H.timeline.map(e => e.type);
  win.fetch('https://other.test/x').then(() => {
    out.crossFetchHeaders = calls[calls.length - 1][1] && calls[calls.length - 1][1].headers ? Object.keys(calls[calls.length - 1][1].headers.m || {}) : [];
    const pw = stubEl('input', { type: 'password', id: 'pw' });
    out.lenBeforeStop = H.timeline.length;
    H.stop(); a.l.loadend();
    out.afterStopLen = H.timeline.length; out.recAfterStop = H.buildRecord('note', 'x').recording_id;
    return H.logObservation('note', 'first');
  }).then(() => {
    out.first = JSON.parse(calls[calls.length - 1][1].body).recording_id || null;
    return H.logObservation('note', 'second');
  }).then(() => {
    out.second = JSON.parse(calls[calls.length - 1][1].body).recording_id || null;
    out.postUrl = calls[calls.length - 1][0];
    console.log(JSON.stringify(out));
  });
} else if (mode === 'pause') {
  win.__FRONTIER_DEBUG__ = true;
  const log = [], video = { paused: false, pause() { this.paused = true; log.push('pause'); }, play() { this.paused = false; log.push('play'); } };
  fakeDoc.querySelectorAll = sel => (sel === 'video,audio' ? [video] : []);
  vm.runInNewContext(bundle, { window: win });
  const ran = [], raf = cb => { cb(); return 1; };
  win.requestAnimationFrame = raf;
  const H = win.__FRONTIER_HUD__;
  H.pick();
  const during = { picking: H.isPicking(), paused: video.paused, rafSwapped: win.requestAnimationFrame !== raf };
  win.requestAnimationFrame(() => ran.push(1));
  H.exitPick();
  const ranAfter = ran.length;
  console.log(JSON.stringify({ ranAfter, during, after: { picking: H.isPicking(), played: !video.paused, rafRestored: win.requestAnimationFrame === raf }, log }));
} else if (mode === 'disabled') {
  const guarded = new Proxy({ __FRONTIER_DEBUG__: undefined }, { get(t, k) { touched.push(String(k)); return t[k]; }, set(t, k, v) { touched.push('set:' + String(k)); t[k] = v; return true; } });
  vm.runInNewContext(bundle, { window: guarded });
  console.log(JSON.stringify({ touched }));
} else {
  win.__FRONTIER_DEBUG__ = true;
  vm.runInNewContext(bundle, { window: win, Date, Math, Uint8Array, Array, Object, String, JSON });
  const H = win.__FRONTIER_HUD__;
  const out = { installed: !!H, panel: fakeDoc.body.children.length };
  vm.runInNewContext(bundle, { window: win });
  out.panelAfterReinstall = fakeDoc.body.children.length;
  out.urlTarget = H.urlTarget('/api/x?token=SECRET&a=1');
  out.scrub = H.scrub({ a: 1, Value: 'x', nested: [{ password: 'p', ok: 2 }], authorization: 'z' });
  const pw = stubEl('input', { type: 'password', value: 'hunter2' });
  const txt = stubEl('input', { type: 'text', name: 'q', value: 'secret text', class: 'c' });
  out.isSecret = [H.isSecret(pw), H.isSecret(txt)];
  out.attrs = H.attrsFor(txt);
  const rid = H.record();
  out.rid = rid; out.recording = H.isRecording();
  for (let i = 0; i < 60; i++) H.log('click', '#b' + i);
  out.tlLen = H.timeline.length; out.tlFirst = H.timeline[0].target;
  H.lastPick = { selector: '#b', rect: {x: 0, y: 0, w: 1, h: 1}, attrs: { tag: 'button' } };
  const rec = H.buildRecord('element', 'm'.repeat(900));
  out.rec = { kind: rec.kind, msgLen: rec.message.length, rid: rec.recording_id, tl: rec.timeline.length, page: rec.page_path, schema: rec.schema };
  win.fetch('/api/x?k=v', { headers: { A: 'b' } }).then(() => {
    const tagged = calls[calls.length - 1][1].headers.m;
    out.fetchHeader = tagged['X-Debug-Recording-Id']; out.keptHeader = tagged.A;
    H.stop();
    out.restored = win.fetch === origFetch; out.recordingAfter = H.isRecording();
    return H.logObservation('note', 'hello');
  }).then(() => {
    const last = calls[calls.length - 1];
    out.postUrl = last[0]; out.postBody = JSON.parse(last[1].body);
    console.log(JSON.stringify(out));
  });
}
"""


AUTOSTOP_DRIVER = r"""
const vm = require('vm'), fs = require('fs');
const bundle = fs.readFileSync(process.argv[2], 'utf8');
function stubEl(tag) {
  return { tagName: tag.toUpperCase(), children: [], style: {}, nodeType: 1, value: '', parentNode: null,
    getAttribute: () => null, setAttribute() {}, addEventListener() {}, removeEventListener() {},
    appendChild(c) { this.children.push(c); c.parentNode = this; return c; }, querySelector() { return null; },
    querySelectorAll() { return []; }, getRootNode() { return fakeDoc; }, getBoundingClientRect: () => ({x: 0, y: 0, width: 10, height: 10}) };
}
const fakeDoc = { documentElement: stubEl('html'), body: stubEl('body'), createElement: t => stubEl(t),
  querySelector() { return null; }, querySelectorAll() { return []; }, addEventListener() {}, removeEventListener() {}, defaultView: null };
const calls = [];
class FakeHeaders { constructor(i) { this.m = Object.assign({}, i || {}); } set(k, v) { this.m[k] = v; } }
const win = { __FRONTIER_DEBUG__: true, document: fakeDoc,
  location: { pathname: '/', hash: '#tab-studio', href: 'http://x.test/#tab-studio', origin: 'http://x.test' },
  console: { error() {} }, history: { pushState() {}, replaceState() {} }, Headers: FakeHeaders, URL, CSS: { escape: s => s },
  addEventListener() {}, removeEventListener() {}, crypto: require('crypto').webcrypto, requestAnimationFrame: () => 1,
  fetch: (u, o) => { calls.push([String(u), o]); return Promise.resolve({ status: 201, json: () => Promise.resolve({ id: 'OBS-010' }) }); } };
vm.runInNewContext(bundle, { window: win });
const H = win.__FRONTIER_HUD__;
(async () => {
  const emptyRes = await H.logObservation('note', '   ');
  H.record();
  H.log('click', '#btn-a');
  const traceOnly = await H.logObservation('note', '');
  const recordingAfterLog = H.isRecording();
  const tracePost = JSON.parse(calls[calls.length - 1][1].body);
  H.lastPick = { selector: '#studio-drawing-canvas', rect: {x: 1, y: 2, w: 3, h: 4}, attrs: { tag: 'canvas' } };
  await H.logObservation('element', '');
  const pickPost = JSON.parse(calls[calls.length - 1][1].body);
  await H.patchObservation('OBS-010', { message: 'edited' });
  await H.deleteObservation('OBS-010');
  const methods = calls.map(c => c[0] + ':' + ((c[1] && c[1].method) || 'GET'));
  console.log(JSON.stringify({ emptyErr: emptyRes.error, recordingAfterLog, tracePage: tracePost.page_path,
    traceMsg: tracePost.message, traceRid: tracePost.recording_id, pickMsg: pickPost.message,
    lastPickCleared: H.lastPick === null, methods }));
})();
"""
UX_DRIVER = ROOT / "tests" / "fixtures" / "hud" / "ux_driver.js"


@unittest.skipUnless(shutil.which("node"), "Node.js required")
class HudLogicTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.tmp = Path(td.name).resolve()
        (self.tmp / "driver.js").write_text(DRIVER, encoding="utf-8")
        (self.tmp / "bundle.js").write_text(observation_assets.hud_bundle(), encoding="utf-8")

    def run_mode(self, mode):
        p = subprocess.run(["node", str(self.tmp / "driver.js"), str(self.tmp / "bundle.js"), mode],
                           capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_disabled_is_strict_noop(self):
        # Only the gate flag and the install marker may be read; nothing may be written.
        touched = self.run_mode("disabled")["touched"]
        self.assertEqual(sorted(set(touched)), ["__FRONTIER_DEBUG__"], touched)

    def test_enabled_contract(self):
        o = self.run_mode("enabled")
        self.assertTrue(o["installed"])
        self.assertEqual(o["panel"], 1)
        self.assertEqual(o["panelAfterReinstall"], 1)  # double install is a no-op
        self.assertEqual(o["urlTarget"], "/api/x?token&a")  # path + query keys, never values
        self.assertEqual(o["scrub"], {"a": 1, "nested": [{"ok": 2}]})
        self.assertEqual(o["isSecret"], [True, False])
        self.assertEqual(o["attrs"], {"tag": "input", "class": "c", "type": "text", "name": "q", "value_length": 11})
        self.assertRegex(o["rid"], r"^rec-[0-9a-f]{6}$")
        self.assertEqual((o["tlLen"], o["tlFirst"]), (50, "#b10"))
        self.assertEqual(o["rec"], {"kind": "element", "msgLen": 500, "rid": o["rid"], "tl": 50, "page": "/dash", "schema": 1})

    def test_fetch_tagging_restore_and_post(self):
        o = self.run_mode("enabled")
        self.assertEqual(o["fetchHeader"], o["rid"])
        self.assertEqual(o["keptHeader"], "b")
        self.assertTrue(o["restored"])
        self.assertFalse(o["recordingAfter"])
        self.assertEqual(o["postUrl"], "/api/diagnostics/observation")
        self.assertEqual(o["postBody"]["message"], "hello")
        self.assertIn("stopped_at", o["postBody"]["window"])

    def test_soft_pause_pauses_media_and_restores(self):
        o = self.run_mode("pause")
        self.assertEqual(o["during"], {"picking": True, "paused": True, "rafSwapped": True})
        self.assertEqual(o["after"], {"picking": False, "played": True, "rafRestored": True})
        self.assertEqual(o["log"], ["pause", "play"])
        self.assertEqual(o["ranAfter"], 1)  # held animation frame ran once, only after exit

    def test_pick_suppresses_clicks_and_password_clears_lastpick(self):
        o = self.run_mode("pick")
        self.assertEqual(o["suppressed"], ["pd", "sp"])
        self.assertEqual(o["rect"], {"x": 1, "y": 2, "w": 3, "h": 4})
        self.assertEqual(o["attrs"], {"tag": "button", "id": "save"})
        self.assertFalse(o["pickingAfter"])
        self.assertIsNone(o["lastPickAfterPassword"])
        self.assertLess(o["rafId"], 0)

    def test_extra_contract_rows(self):
        o = self.run_mode("extra")
        self.assertEqual(o["endpoint"], "/custom/obs")
        self.assertEqual((o["xhrSame"], o["xhrCross"]), (True, False))  # same-origin only
        for t in ("fetch", "console", "error", "nav"):
            self.assertIn(t, o["types"])
        self.assertNotIn("X-Debug-Recording-Id", o["crossFetchHeaders"])
        self.assertEqual(o["afterStopLen"], o["lenBeforeStop"])  # late XHR loadend after Stop is ignored
        self.assertIsNotNone(o["first"])  # finished recording attaches to the next Log
        self.assertIsNone(o["second"])    # and only that one
        self.assertEqual(o["postUrl"], "/custom/obs")

    def test_log_autostops_recording_allows_pick_or_trace_only_and_clears_pick(self):
        (self.tmp / "extra_driver.js").write_text(AUTOSTOP_DRIVER, encoding="utf-8")
        p = subprocess.run(
            ["node", str(self.tmp / "extra_driver.js"), str(self.tmp / "bundle.js")],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        o = json.loads(p.stdout)
        self.assertEqual(o["emptyErr"], "empty")
        self.assertFalse(o["recordingAfterLog"])
        self.assertEqual(o["tracePage"], "/#tab-studio")
        self.assertTrue(o["traceMsg"].startswith("[trace] rec-"))
        self.assertRegex(o["traceRid"], r"^rec-[0-9a-f]{6}$")
        self.assertEqual(o["pickMsg"], "[element] #studio-drawing-canvas")
        self.assertTrue(o["lastPickCleared"])
        self.assertIn("/api/diagnostics/observations/OBS-010:PATCH", o["methods"])
        self.assertIn("/api/diagnostics/observations/OBS-010:DELETE", o["methods"])

    def test_hud_v1_1_ux_u1_to_u7(self):
        p = subprocess.run(
            ["node", str(UX_DRIVER), str(self.tmp / "bundle.js")],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        o = json.loads(p.stdout)
        self.assertEqual(o["u6InitCount"], ["(1)", "(1)"])
        self.assertEqual(o["u3KindAfterPick"], "note")
        self.assertEqual(o["u3PickCount"], 2)
        self.assertEqual((o["u3PostKind"], o["u3PostElements"]), ("note", ["#btn-1", "#btn-2"]))
        self.assertEqual(o["u6CountAfterPost"], "(2)")
        self.assertEqual(o["u2DirtyBtn"], "Save *")
        self.assertTrue(o["u2PreservedHtml"])
        self.assertFalse(o["u3DrawerAttachHasKind"])
        self.assertEqual(o["u3DrawerAttachEls"], ["#a1", "#a2"])
        self.assertEqual(o["u4Linked"], ["OBS-002"])
        self.assertTrue(o["u4SelfRejected"])
        self.assertEqual(o["u4JumpFilterAndSel"], ["all", "OBS-002"])
        self.assertEqual(o["u4Unlinked"], [])
        self.assertEqual(o["u1EditState"], {"id": "OBS-001", "open": True, "drawerOpen": False, "btn": "Save", "cancelHidden": False, "msg": "draft text"})
        self.assertEqual(o["u1Patch"], {"url": "/api/diagnostics/observations/OBS-001", "kind": "idea", "msg": "edited via composer", "editingAfter": None})
        self.assertTrue(o["u5HasDismissedFilter"])
        self.assertTrue(o["u5UndoRendered"])
        self.assertEqual((o["u5AfterUndo"], o["u5AfterReopen"]), ("open", "open"))
        self.assertEqual((o["u7FirstClickDeletes"], o["u7ConfirmVisible"], o["u7CancelCleared"], o["u7ConfirmedDeletes"]), (0, True, True, 1))

    def test_bundle_order_and_size(self):
        text = observation_assets.hud_bundle()
        self.assertLess(text.index("part 1 of 4"), text.index("part 2 of 4"))
        self.assertLess(text.index("part 2 of 4"), text.index("part 3 of 4"))
        self.assertLess(text.index("part 3 of 4"), text.index("part 4 of 4"))
        for name in observation_assets.HUD_FILES:
            lines = (observation_assets.ASSETS_DIR / name).read_text(encoding="utf-8").count("\n")
            self.assertLessEqual(lines, 300, name)


if __name__ == "__main__":
    unittest.main()
