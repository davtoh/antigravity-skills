#!/usr/bin/env python3
"""`observations pull` against loopback stub servers: scenarios from the parent matrix."""

import argparse
import contextlib
import io
import json
import shutil
import socket
import tempfile
import unittest
from pathlib import Path

import _obs_stub as stub
import observation_cli as cli
import observation_pull as pull
import observation_store as store


def run_cli(*argv):
    parser = argparse.ArgumentParser()
    cli.register_parser(parser.add_subparsers(dest="command"))
    args = parser.parse_args(["observations", *argv])
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.cmd_observations(args)
    return code, out.getvalue()


class PullBase(unittest.TestCase):
    def setUp(self):
        self.remote_ws = Path(tempfile.mkdtemp(prefix="obs_remote_")).resolve()
        self.local_ws = Path(tempfile.mkdtemp(prefix="obs_local_")).resolve()
        for i in range(3):
            store.add_observation(self.remote_ws, {"kind": "idea", "message": f"idea {i}", "ts": f"2026-11-0{i + 1}T00:00:00+00:00"})

    def tearDown(self):
        for ws in (self.remote_ws, self.local_ws):
            shutil.rmtree(ws, ignore_errors=True)

    def catalog_path(self):
        return self.local_ws / ".diagnostics" / store.CATALOG_NAME


class TestPull(PullBase):
    def test_pull_new_then_unchanged(self):
        with stub.StubServer(self.remote_ws) as srv:
            code, out = run_cli("pull", "--url", srv.url, "--path", str(self.local_ws))
            self.assertEqual((code, out.strip()), (0, "pulled 3 (new 3, updated 0, unchanged 0)"))
            code, out = run_cli("pull", "--url", srv.url, "--path", str(self.local_ws))
            self.assertEqual(out.strip(), "pulled 3 (new 0, updated 0, unchanged 3)")
        entries = store.load_catalog(self.local_ws)["observations"]
        self.assertEqual(len(entries), 3)
        self.assertTrue(all(e["source_url"].startswith("http://127.0.0.1:") for e in entries))

    def test_local_triage_kept_and_remote_status_wins_when_newer(self):
        with stub.StubServer(self.remote_ws) as srv:
            run_cli("pull", "--url", srv.url, "--path", str(self.local_ws))
            first = store.list_observations(self.local_ws, status="all", limit=0)[0]
            store.update_status(self.local_ws, first["id"], "triaged", note="n", root_cause="local cause")
            remote_entry = store.list_observations(self.remote_ws, status="all", limit=0)[0]
            store.update_status(self.remote_ws, remote_entry["id"], "resolved", note="fixed", resolution="r")
            cat = store.load_catalog(self.remote_ws)
            for e in cat["observations"]:
                e["last_seen"] = "2026-12-01T00:00:00+00:00"
            store.save_catalog(self.remote_ws, cat)
            code, out = run_cli("pull", "--url", srv.url, "--path", str(self.local_ws), "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["updated"], 3)
        merged = store.get_observation(self.local_ws, first["fingerprint"])
        self.assertEqual((merged["status"], merged["root_cause"]), ("resolved", "local cause"))

    def test_kind_filter(self):
        store.add_observation(self.remote_ws, {"kind": "note", "message": "a note"})
        with stub.StubServer(self.remote_ws) as srv:
            _, out = run_cli("pull", "--url", srv.url, "--path", str(self.local_ws), "--kind", "note")
        self.assertIn("pulled 1 ", out)

    def test_wrong_contract_version_writes_nothing(self):
        def override(method, rel, query, hdrs, body, default):
            if rel == "/health":
                s, h, _ = default()
                return s, h, json.dumps({"enabled": True, "contract_version": 2}).encode()
        with stub.StubServer(self.remote_ws, override) as srv:
            code, out = run_cli("pull", "--url", srv.url, "--path", str(self.local_ws))
        self.assertEqual(code, 1)
        self.assertIn("contract mismatch", out)
        self.assertFalse(self.catalog_path().exists())

    def test_failure_midway_is_atomic(self):
        def override(method, rel, query, hdrs, body, default):
            if rel.startswith("/observations/"):
                return 500, {"Content-Type": "application/json"}, b"{}"
        with stub.StubServer(self.remote_ws, override) as srv:
            code, out = run_cli("pull", "--url", srv.url, "--path", str(self.local_ws))
        self.assertEqual(code, 1)
        self.assertIn("nothing written", out)
        self.assertFalse(self.catalog_path().exists())

    def test_unreachable_exit_1(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        code, out = run_cli("pull", "--url", f"http://127.0.0.1:{port}", "--path", str(self.local_ws), "--timeout", "2")
        self.assertEqual(code, 1)
        self.assertIn("cannot reach", out)
        self.assertFalse(self.catalog_path().exists())

    def test_disabled_app_exit_1(self):
        def override(method, rel, query, hdrs, body, default):
            return 404, {"X-Diagnostics-Contract": "1"}, b'{"error":"not_found","message":"off"}'
        with stub.StubServer(self.remote_ws, override) as srv:
            code, _ = run_cli("pull", "--url", srv.url, "--path", str(self.local_ws))
        self.assertEqual(code, 1)

    def test_redirect_is_not_followed(self):
        def override(method, rel, query, hdrs, body, default):
            return 302, {"Location": "http://10.255.255.1/"}, b""
        with stub.StubServer(self.remote_ws, override) as srv:
            code, out = run_cli("pull", "--url", srv.url, "--path", str(self.local_ws))
        self.assertEqual(code, 1)
        self.assertIn("HTTP 302", out)

    def test_malformed_observations_list_exits_1(self):
        def override(method, rel, query, hdrs, body, default):
            if rel.startswith("/observations"):
                return 200, {"X-Diagnostics-Contract": "1"}, b'{"observations": "not-a-list"}'
            return default()
        with stub.StubServer(self.remote_ws, override) as srv:
            code, out = run_cli("pull", "--url", srv.url, "--path", str(self.local_ws))
        self.assertEqual(code, 1)
        self.assertIn("non-list", out)


class TestPullRefusals(PullBase):
    def test_remote_host_refused_without_flag(self):
        code, out = run_cli("pull", "--url", "http://10.0.0.5:8000", "--path", str(self.local_ws))
        self.assertEqual(code, 2)
        self.assertIn("--allow-remote", out)

    def test_allow_remote_warns_then_fails_to_connect(self):
        code, out = run_cli("pull", "--url", "http://203.0.113.1:1", "--path", str(self.local_ws),
                            "--allow-remote", "--timeout", "1")
        self.assertIn("WARNING", out)
        self.assertEqual(code, 1)

    def test_missing_url_and_bad_scheme_exit_2(self):
        self.assertEqual(run_cli("pull", "--path", str(self.local_ws))[0], 2)
        self.assertEqual(run_cli("pull", "--url", "file:///etc/passwd", "--path", str(self.local_ws))[0], 2)

    def test_api_base_not_doubled(self):
        self.assertEqual(pull.api_base("http://127.0.0.1:1/api/diagnostics/"), "http://127.0.0.1:1/api/diagnostics")
        self.assertEqual(pull.api_base("http://127.0.0.1:1"), "http://127.0.0.1:1/api/diagnostics")


if __name__ == "__main__":
    unittest.main()
