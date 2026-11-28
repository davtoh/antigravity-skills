#!/usr/bin/env python3
"""`observations verify-connector`: compliant, non-compliant and generated-bridge servers."""

import argparse
import contextlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _obs_stub as stub
import connector_scaffolder
import observation_cli as cli
import observation_store as store
import observation_verify as verify


def by_name(results):
    return {r["check"]: r for r in results}


def run_cli(*argv):
    parser = argparse.ArgumentParser()
    cli.register_parser(parser.add_subparsers(dest="command"))
    args = parser.parse_args(["observations", *argv])
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.cmd_observations(args)
    return code, out.getvalue()


class VerifyBase(unittest.TestCase):
    def setUp(self):
        self.ws = Path(tempfile.mkdtemp(prefix="obs_verify_")).resolve()

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)


class TestVerify(VerifyBase):
    def test_compliant_app_passes_and_stores_nothing(self):
        with stub.StubServer(self.ws) as srv:
            results = verify.run(srv.url)
            code, out = run_cli("verify-connector", "--url", srv.url)
        self.assertEqual(code, 0)
        self.assertTrue(verify.passed(results))
        self.assertEqual([r["result"] for r in results if r["result"] == "FAIL"], [])
        skips = [r["check"] for r in results if r["result"] == "SKIP"]
        self.assertIn("non-loopback -> 403", skips)
        self.assertIn("CONFORMANT", out)
        self.assertEqual(store.load_catalog(self.ws)["observations"], [])
        self.assertEqual(results[1]["check"], "X-Diagnostics-Contract on every response")

    def test_oversize_accepted_is_a_fail_with_expected_vs_actual(self):
        def override(method, rel, query, hdrs, body, default):
            if method == "POST" and len(body) > store.MAX_RECORD_BYTES:
                return 200, {"Content-Type": "application/json", "X-Diagnostics-Contract": "1"}, b'{"dry_run":true}'
        with stub.StubServer(self.ws, override) as srv:
            code, out = run_cli("verify-connector", "--url", srv.url)
            results = by_name(verify.run(srv.url))
        self.assertEqual(code, 1)
        fail = results["oversize -> 413"]
        self.assertEqual(fail["result"], "FAIL")
        self.assertIn("expected 413 payload_too_large", fail["detail"])
        self.assertIn("NOT CONFORMANT", out)

    def test_missing_contract_header_fails(self):
        def override(method, rel, query, hdrs, body, default):
            if rel == "/hud.js":
                s, h, b = default()
                h.pop("X-Diagnostics-Contract")
                return s, h, b
        with stub.StubServer(self.ws, override) as srv:
            results = by_name(verify.run(srv.url))
        self.assertEqual(results["X-Diagnostics-Contract on every response"]["result"], "FAIL")

    def test_wrong_contract_version_fails_health(self):
        def override(method, rel, query, hdrs, body, default):
            if rel == "/health":
                return 200, {"Content-Type": "application/json", "X-Diagnostics-Contract": "1"}, \
                    b'{"schema":1,"enabled":true,"contract_version":2,"store":"ok"}'
        with stub.StubServer(self.ws, override) as srv:
            self.assertEqual(by_name(verify.run(srv.url))["health shape and contract_version"]["result"], "FAIL")

    def test_leaky_redaction_preview_fails(self):
        def override(method, rel, query, hdrs, body, default):
            if method == "POST" and b'"password"' in body and b'"kind": "note"' in body and b"pad" not in body:
                return 200, {"Content-Type": "application/json", "X-Diagnostics-Contract": "1"}, \
                    json.dumps({"dry_run": True, "accepted": json.loads(body)}).encode()
        with stub.StubServer(self.ws, override) as srv:
            results = by_name(verify.run(srv.url))
        self.assertEqual(results["redaction of value/password"]["result"], "FAIL")

    def test_unreachable_exit_1_json_mode(self):
        code, out = run_cli("verify-connector", "--url", "http://127.0.0.1:1", "--timeout", "2")
        self.assertEqual(code, 1)
        self.assertIn("cannot reach", out)

    def test_json_output_and_missing_url(self):
        with stub.StubServer(self.ws) as srv:
            code, out = run_cli("verify-connector", "--url", srv.url, "--json")
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["ok"])
        self.assertEqual(run_cli("verify-connector")[0], 2)


class TestGeneratedBridgePasses(VerifyBase):
    def test_generic_bridge_is_conformant(self):
        path = connector_scaffolder.scaffold_connector(self.ws, "generic", "services", with_observations=True)
        spec = importlib.util.spec_from_file_location("bridge_generic_verify", path)
        bridge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bridge)

        def handler(method, rel, query, headers, host, body, workspace, env):
            return bridge.handle_diagnostics_request(method, rel, query, headers, host, body, self.ws)

        with mock.patch.dict(os.environ, {"FRONTIER_DEBUG_OBSERVATIONS": "1"}):
            with stub.StubServer(self.ws, handler=handler) as srv:
                results = verify.run(srv.url)
        failed = [r for r in results if r["result"] == "FAIL"]
        self.assertEqual(failed, [])


if __name__ == "__main__":
    unittest.main()
