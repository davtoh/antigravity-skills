#!/usr/bin/env python3
"""Every Wire Contract row, exercised through the generated bridges without any framework installed."""

import asyncio
import importlib.util
import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import connector_scaffolder
import observation_routes as R

ENV_ON = {"FRONTIER_DEBUG_OBSERVATIONS": "1"}
JSON_H = {"Content-Type": "application/json"}
LOCAL = "127.0.0.1"


def load_bridge(root: Path, fw: str):
    path = connector_scaffolder.scaffold_connector(root, fw, "services", with_observations=True)
    spec = importlib.util.spec_from_file_location(f"bridge_{fw}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestWireContract(unittest.TestCase):
    def setUp(self):
        self.ws = Path(tempfile.mkdtemp(prefix="sysdiag_wire_")).resolve()

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def call(self, method, path, query="", headers=None, host=LOCAL, body=b"", env=ENV_ON):
        return R.handle(method, path, query, headers or {}, host, body, self.ws, env)

    def post(self, rec, query="", **kw):
        return self.call("POST", "/observation", query, JSON_H, body=json.dumps(rec).encode(), **kw)

    def test_every_response_has_contract_header(self):
        for res in (self.call("GET", "/health"), self.call("GET", "/nope"), self.call("GET", "/health", env={}),
                    self.call("GET", "/health", host="10.0.0.5")):
            self.assertEqual(res[1]["X-Diagnostics-Contract"], "1")

    def test_disabled_is_404_and_remote_is_403(self):
        self.assertEqual(self.call("GET", "/health", env={})[0], 404)
        self.assertEqual(self.call("GET", "/health", host="10.0.0.5")[0], 403)
        self.assertEqual(self.call("GET", "/health", host="::1")[0], 200)

    def test_remote_403_on_every_route_and_gating_404_wins(self):
        for method, path in (("GET", "/health"), ("POST", "/observation"), ("GET", "/observations"),
                             ("GET", "/observations/OBS-001"), ("GET", "/hud.js")):
            self.assertEqual(self.call(method, path, host="8.8.8.8")[0], 403, path)
            self.assertEqual(self.call(method, path, host="8.8.8.8", env={})[0], 404, path)

    def test_health(self):
        status, _, body = self.call("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"schema": 1, "enabled": True, "contract_version": 1, "store": "ok"})

    def test_post_new_then_dedup(self):
        rec = {"kind": "element", "page_path": "/a", "selector": "b", "message": "x"}
        s1, _, b1 = self.post(rec)
        s2, _, b2 = self.post(rec)
        self.assertEqual((s1, s2), (201, 200))
        self.assertFalse(json.loads(b1)["deduplicated"])
        self.assertTrue(json.loads(b2)["deduplicated"])
        self.assertTrue(json.loads(b1)["fingerprint"].startswith("OBS-ELEMENT-"))

    def test_dry_run_stores_nothing(self):
        status, _, body = self.post({"kind": "note", "message": "hi"}, "dry_run=1")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["dry_run"])
        self.assertEqual(json.loads(self.call("GET", "/observations")[2])["count"], 0)

    def test_post_errors(self):
        self.assertEqual(self.call("POST", "/observation", "", {"Content-Type": "text/plain"}, body=b"{}")[0], 415)
        self.assertEqual(self.call("POST", "/observation", "", JSON_H, body=b"{nope")[0], 400)
        s, _, b = self.post({"kind": "bogus"})
        self.assertEqual((s, json.loads(b)["error"]), (400, "invalid_record"))
        self.assertEqual(self.call("POST", "/observation", "", JSON_H, body=b" " * 70000)[0], 413)
        self.assertEqual(self.post({"kind": "note"}, host="8.8.8.8")[0], 403)

    def test_redaction_and_caps(self):
        self.post({"kind": "note", "message": "m" * 900, "attrs": {"password": "s3", "id": "a"}, "value": "v"})
        entry = json.loads(self.call("GET", "/observations/OBS-001")[2])
        self.assertEqual(len(entry["message"]), 500)
        self.assertNotIn("password", entry["attrs"])

    def test_list_filters_and_limit(self):
        for i in range(3):
            self.post({"kind": "idea", "message": f"idea {i}"})
        self.post({"kind": "note", "message": "n"})
        body = json.loads(self.call("GET", "/observations", "kind=idea&limit=2")[2])
        self.assertEqual((body["count"], body["truncated"]), (2, True))
        self.assertEqual(self.call("GET", "/observations", "limit=abc")[0], 400)
        self.assertEqual(self.call("GET", "/observations", "status=weird")[0], 400)
        self.assertEqual(self.call("GET", "/observations", host="8.8.8.8")[0], 403)

    def test_get_one_by_id_and_fingerprint(self):
        fp = json.loads(self.post({"kind": "note", "message": "z"})[2])["fingerprint"]
        self.assertEqual(self.call("GET", f"/observations/{fp}")[0], 200)
        self.assertEqual(self.call("GET", "/observations/OBS-999")[0], 404)

    def test_hud_js(self):
        status, headers, body = self.call("GET", "/hud.js")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/javascript")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn(b"__FRONTIER_DEBUG__", body)
        self.assertEqual(self.call("GET", "/hud.js", host="8.8.8.8")[0], 403)


class TestGeneratedBridges(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="sysdiag_bridge_")).resolve()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_import_and_handle_without_frameworks(self):
        for fw in ("fastapi", "flask", "generic"):
            mod = load_bridge(self.root, fw)
            with mock.patch.dict("os.environ", ENV_ON):
                s, h, _ = mod.handle_diagnostics_request("GET", "/health", "", {}, LOCAL, b"", self.root)
            self.assertEqual((s, h["X-Diagnostics-Contract"]), (200, "1"))

    def test_register_is_noop_when_disabled(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("FRONTIER_DEBUG_OBSERVATIONS", None)
            self.assertFalse(load_bridge(self.root, "flask").register_observation_routes(object()))

    def test_fastapi_adapter_with_fake_framework(self):
        routes = {}

        class App:
            def api_route(self, path, **kw):
                def deco(fn):
                    routes[path] = (fn, kw)
                    return fn
                return deco

        fake = types.ModuleType("fastapi")
        fake.Request = object
        resp = types.ModuleType("fastapi.responses")
        resp.Response = lambda content, status_code, headers: (status_code, headers, content)
        mod = load_bridge(self.root, "fastapi")
        req = types.SimpleNamespace(method="GET", url=types.SimpleNamespace(query=""), headers={},
                                    client=types.SimpleNamespace(host=LOCAL))

        async def stream():
            yield b""
        req.stream = stream
        with mock.patch.dict("os.environ", ENV_ON), mock.patch.dict(sys.modules, {"fastapi": fake, "fastapi.responses": resp}):
            self.assertTrue(mod.register_observation_routes(App(), self.root))
            fn, kw = routes["/api/diagnostics/{rest:path}"]
            self.assertEqual(kw["methods"], ["GET", "POST"])
            status, headers, _ = asyncio.run(fn("health", req))
        self.assertEqual((status, headers["X-Diagnostics-Contract"]), (200, "1"))

    def test_fastapi_adapter_caps_body_and_skips_remote(self):
        mod = load_bridge(self.root, "fastapi")
        routes = {}
        app = types.SimpleNamespace(api_route=lambda path, **kw: (lambda fn: routes.setdefault("f", fn)))
        fake = types.ModuleType("fastapi")
        fake.Request = object
        resp = types.ModuleType("fastapi.responses")
        resp.Response = lambda content, status_code, headers: (status_code, headers, content)
        pulled = []

        def make(host):
            async def stream():
                for _ in range(100):
                    pulled.append(1)
                    yield b"x" * 10000
            return types.SimpleNamespace(method="POST", url=types.SimpleNamespace(query=""),
                                         headers={"content-type": "application/json"},
                                         client=types.SimpleNamespace(host=host), stream=stream)
        with mock.patch.dict("os.environ", ENV_ON), mock.patch.dict(sys.modules, {"fastapi": fake, "fastapi.responses": resp}):
            mod.register_observation_routes(app, self.root)
            self.assertEqual(asyncio.run(routes["f"]("observation", make(LOCAL)))[0], 413)
            self.assertLess(len(pulled), 10)
            pulled.clear()
            self.assertEqual(asyncio.run(routes["f"]("observation", make("8.8.8.8")))[0], 403)
            self.assertEqual(pulled, [])

    def test_flask_adapter_with_fake_framework(self):
        rules = []
        fake = types.ModuleType("flask")
        fake.request = types.SimpleNamespace(method="GET", query_string=b"", headers={}, remote_addr=LOCAL,
                                             stream=types.SimpleNamespace(read=lambda n: b""))
        fake.Response = lambda payload, status, headers: (status, headers, payload)

        class App:
            def add_url_rule(self, rule, endpoint, view, methods):
                rules.append((rule, view, methods))
        mod = load_bridge(self.root, "flask")
        with mock.patch.dict("os.environ", ENV_ON), mock.patch.dict(sys.modules, {"flask": fake}):
            self.assertTrue(mod.register_observation_routes(App(), self.root))
            rule, view, methods = rules[0]
            status, headers, _ = view("health")
        self.assertEqual((rule, methods, status), ("/api/diagnostics/<path:rest>", ["GET", "POST"], 200))


if __name__ == "__main__":
    unittest.main()
