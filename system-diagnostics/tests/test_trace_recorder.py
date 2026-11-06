#!/usr/bin/env python3
"""Unit tests for Universal Runtime Diagnostic Trace Recorder & Catalog (trace_recorder.py)."""

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import trace_recorder


class TestTraceRecorder(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="sysdiag_trace_test_"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_fingerprint_normalization_and_deduplication(self):
        # Two messages with different memory addresses or PIDs must yield the exact same fingerprint
        fp1 = trace_recorder.generate_trace_fingerprint(
            "ValueError", "services/worker.py", "process", "Failed on item at 0x0000021A87536660 (PID 1234)"
        )
        fp2 = trace_recorder.generate_trace_fingerprint(
            "ValueError", "services/worker.py", "process", "Failed on item at 0x0000021B98647771 (PID 5678)"
        )
        self.assertEqual(fp1, fp2)
        self.assertTrue(fp1.startswith("TRC-VALUEERR-"))

    def test_extract_trace_event(self):
        try:
            raise KeyError("test_key_missing")
        except KeyError as exc:
            event = trace_recorder.extract_trace_event(
                type(exc), exc, exc.__traceback__, context={"camera_id": "cam_01"}, workspace_root=self.temp_dir
            )

        self.assertEqual(event["exception_type"], "KeyError")
        self.assertIn("test_key_missing", event["message"])
        self.assertEqual(event["context"], {"camera_id": "cam_01"})
        self.assertTrue(len(event["traceback"]) >= 1)
        self.assertTrue(event["fingerprint"].startswith("TRC-KEYERROR-"))

    def test_catalog_enrichment_without_duplicates(self):
        mgr = trace_recorder.TraceCatalogManager(self.temp_dir)

        # Record first occurrence
        event1 = {
            "fingerprint": "TRC-IOERROR-ABC123",
            "timestamp": "2026-11-06T12:00:00Z",
            "severity": "ERROR",
            "exception_type": "IOError",
            "message": "Connection refused on port 8000",
            "culprit_file": "client.py",
            "culprit_line": 42,
            "culprit_func": "connect",
            "traceback": ["line 42"],
            "environment": {"platform": "win32"},
            "context": {"port": 8000},
        }
        issue1 = mgr.record_trace(event1)
        self.assertEqual(issue1["id"], "TRC-001")
        self.assertEqual(issue1["occurrence_count"], 1)

        # Record second occurrence of the same issue
        event2 = dict(event1)
        event2["timestamp"] = "2026-11-06T12:05:00Z"
        event2["context"] = {"port": 8001}
        issue2 = mgr.record_trace(event2)

        self.assertEqual(issue2["id"], "TRC-001")
        self.assertEqual(issue2["occurrence_count"], 2)
        self.assertEqual(issue2["last_seen"], "2026-11-06T12:05:00Z")

        # Verify catalog summary and single enriched issue
        cat = mgr.load_catalog()
        self.assertEqual(cat["summary"]["total_events"], 2)
        self.assertEqual(cat["summary"]["unique_issues"], 1)
        self.assertEqual(len(cat["issues"]), 1)
        self.assertEqual(len(cat["issues"][0]["sample_contexts"]), 2)

        # Verify daily JSONL log wrote 2 raw lines
        daily_logs = list(mgr.traces_dir.glob("trace_*.jsonl"))
        self.assertEqual(len(daily_logs), 1)
        lines = daily_logs[0].read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)

    def test_cmd_traces_cli(self):
        mgr = trace_recorder.TraceCatalogManager(self.temp_dir)
        mgr.record_trace({
            "fingerprint": "TRC-RUNTIME-112233",
            "timestamp": "2026-11-06T12:00:00Z",
            "severity": "ERROR",
            "exception_type": "RuntimeError",
            "message": "Buffer overflow",
            "culprit_file": "buf.py",
            "culprit_line": 10,
            "culprit_func": "push",
            "traceback": [],
            "environment": {},
            "context": {},
        })

        class Args:
            path = str(self.temp_dir)
            recent = 5
            json = True
            clear = False

        res = trace_recorder.cmd_traces(Args())
        self.assertEqual(res, 0)

        # Test clear
        Args.json = False
        Args.clear = True
        res_clear = trace_recorder.cmd_traces(Args())
        self.assertEqual(res_clear, 0)
        self.assertFalse(mgr.catalog_path.exists())

    def test_scaffold_connector(self):
        class Args:
            path = str(self.temp_dir)
            recent = 5
            json = False
            clear = False
            scaffold = "fastapi"
            dest = "services"

        res = trace_recorder.cmd_traces(Args())
        self.assertEqual(res, 0)
        bridge_file = self.temp_dir / "services" / "diagnostic_bridge.py"
        self.assertTrue(bridge_file.exists())
        self.assertIn("DiagnosticTraceMiddleware", bridge_file.read_text(encoding="utf-8"))

    def test_asgi_middleware(self):
        import asyncio
        from trace_middleware import DiagnosticTraceMiddleware

        async def faulty_app(scope, receive, send):
            raise KeyError("missing_param_in_request")

        middleware = DiagnosticTraceMiddleware(faulty_app, workspace_root=self.temp_dir)
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/infer",
            "client": ("127.0.0.1", 54321),
        }

        with self.assertRaises(KeyError):
            asyncio.run(middleware(scope, None, None))

        mgr = trace_recorder.TraceCatalogManager(self.temp_dir)
        cat = mgr.load_catalog()
        self.assertEqual(cat["summary"]["total_events"], 1)
        issue = cat["issues"][0]
        self.assertEqual(issue["exception_type"], "KeyError")
        self.assertEqual(issue["sample_contexts"][0]["http_path"], "/api/v1/infer")
        self.assertEqual(issue["sample_contexts"][0]["http_method"], "POST")


if __name__ == "__main__":
    unittest.main()

