"""Chrome-gated HUD SPIKE + end-to-end test (skips without Chrome). Six fixtures, one local server."""
import json
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import cdp_inspect  # noqa: E402
import observation_assets  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "hud"
CDP = str(ROOT / "scripts" / "cdp_inspect.py")
TARGETS = {
    "plain": "document.querySelector('[data-testid=save]')",
    "spa": "document.querySelector('.go')",
    "iframe": "document.getElementById('f').contentDocument.getElementById('inner')",
    "shadow": "document.getElementById('card').shadowRoot.querySelector('.inside')",
    "csp": "document.getElementById('csp-btn')",
    "media": "document.getElementById('media-btn')",
}
SELECTORS = {"plain": '[data-testid="save"]', "iframe": "#f >>> #inner", "csp": "#csp-btn", "media": "#media-btn"}  # #id, then data-testid
EVAL = """(async () => { const H = window.__FRONTIER_HUD__; if (!H) return {error: 'no hud'};
 const el = %s; H.record(); H.pick();
 el.dispatchEvent(new MouseEvent('click', {bubbles: true, composed: true, cancelable: true}));
 const sel = H.lastPick && H.lastPick.selector; el.click();
 await new Promise(r => setTimeout(r, 400)); H.stop();
 return {sel, strict: (() => { try { return document.querySelector(sel) === el; } catch (e) { return false; } })(), ext: H.resolve(sel) === el,
         timeline: H.timeline, rid: H.recordingId, attrs: H.lastPick.attrs}; })()"""


def _chrome_available():
    try:
        return Path(cdp_inspect.find_chrome_executable()).exists()
    except Exception:
        return False


class _Handler(BaseHTTPRequestHandler):
    pings = []
    posts = []

    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/diagnostics/hud.js":
            return self._send(200, observation_assets.hud_bundle().encode(), "application/javascript")
        if path == "/api/ping":
            type(self).pings.append(self.headers.get("X-Debug-Recording-Id"))
            return self._send(200, b"{}", "application/json")
        f = FIXTURES / path.lstrip("/")
        if not f.is_file():
            return self._send(404, b"", "text/plain")
        ctype = "application/javascript" if f.suffix == ".js" else "text/html"
        self._send(200, f.read_bytes(), ctype)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        type(self).posts.append(json.loads(body))
        self._send(201, b'{"id":"OBS-001"}', "application/json")


@unittest.skipUnless(_chrome_available(), "Chrome/Chromium not available")
class HudSpikeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def run_fixture(self, name):
        return self._run(name, EVAL % TARGETS[name])

    def _run(self, name, script):
        _Handler.pings.clear()
        p = subprocess.run(
            [sys.executable, CDP, "--headless", "--url", f"http://127.0.0.1:{self.port}/{name}.html", "--eval", script],
            capture_output=True, text=True, encoding="utf-8", timeout=90)
        text = p.stdout
        if "{" not in text:
            self.fail(
                f"cdp_inspect produced no JSON for '{name}' (rc={p.returncode}).\n"
                f"STDOUT: {p.stdout!r}\nSTDERR: {p.stderr!r}"
            )
        start = text.index("{")
        return json.JSONDecoder().raw_decode(text[start:])[0]

    def test_spike_fixtures(self):
        table, passed = {}, 0
        for name in TARGETS:
            res = self.run_fixture(name)
            ok_sel = bool(res.get("strict") or res.get("ext"))
            self.assertEqual(res.get("sel"), SELECTORS.get(name, res.get("sel")), name)
            fetches = [e for e in res.get("timeline", []) if e["type"] == "fetch"]
            if fetches:
                self.assertEqual((fetches[0]["status"], fetches[0]["ms"] >= 0), (200, True))
            if name in ("plain", "spa"):
                self.assertIn("click", [e["type"] for e in res["timeline"]], name)
            ok_rec = bool(res.get("timeline")) and any(p and p.startswith("rec-") for p in _Handler.pings)
            table[name] = {"strict": res.get("strict"), "extended": res.get("ext"), "record": ok_rec}
            passed += int(ok_sel and ok_rec)
        print("\nHUD SPIKE", json.dumps(table), f"passed={passed}/6")
        self.assertGreaterEqual(passed, 5, table)

    def test_password_pick_records_nothing_and_value_never_sent(self):
        TARGETS["pw"] = "document.getElementById('pw')"
        self.addCleanup(TARGETS.pop, "pw")
        script = EVAL.replace("attrs: H.lastPick.attrs", "attrs: H.lastPick && H.lastPick.attrs")
        out = self._run("plain", script % TARGETS["pw"])
        self.assertIsNone(out["sel"])  # password pick is discarded
        self.assertEqual([e for e in out["timeline"] if e["type"] == "click"], [])
        self.assertNotIn("hunter2", json.dumps(out))
        text = self.run_fixture("plain")
        self.assertNotIn("secret text", json.dumps(text))


if __name__ == "__main__":
    unittest.main()
