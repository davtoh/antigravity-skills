#!/usr/bin/env python3
"""Unit tests for extended surface_contracts and surface_verifier checks."""

import argparse
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from surface_scanners import cmd_surface, scan_html_surface, scan_js_surface, scan_python_surface, walk_source_files
from surface_verifier import verify_surface_contracts


class TestSurfaceContracts(unittest.TestCase):
    """Focused tests for HTTP methods, non-fetch URLs, dead buttons, and response keys."""

    def test_http_method_mismatch_and_non_fetch_urls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text('<img src="/api/missing_img">', encoding="utf-8")
            (root / "app.js").write_text(
                'fetch("/api/items", { method: "DELETE" });\n'
                'const ws = new WebSocket("/ws/missing");\n',
                encoding="utf-8",
            )
            (root / "api.py").write_text(
                'from fastapi import APIRouter\nrouter = APIRouter()\n'
                '@router.get("/api/items")\ndef list_items(): return []\n',
                encoding="utf-8",
            )
            files = walk_source_files(root)
            res = verify_surface_contracts(root, files, scan_html_surface, scan_js_surface, scan_python_surface)
            paths = {(x["method"], x["path"]) for x in res["unmatched_fetches"]}
            self.assertIn(("DELETE", "/api/items"), paths)
            self.assertIn(("WEBSOCKET", "/ws/missing"), paths)
            self.assertIn(("GET", "/api/missing_img"), paths)

    def test_dead_buttons_dupes_inline_handlers_and_window_methods(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text(
                '<button id="btn-dead">Save</button>'
                '<button id="btn-live" onclick="missingHandler()">Save</button>',
                encoding="utf-8",
            )
            (root / "app.js").write_text(
                'window.Studio = { init() {} };\nwindow.Studio.missingFn();\n',
                encoding="utf-8",
            )
            files = walk_source_files(root)
            res = verify_surface_contracts(root, files, scan_html_surface, scan_js_surface, scan_python_surface)
            self.assertEqual([b["id"] for b in res["dead_buttons"]], ["btn-dead"])
            self.assertEqual([d["label"] for d in res["duplicate_button_labels"]], ["Save"])
            self.assertEqual([h["target"] for h in res["missing_inline_handlers"]], ["missingHandler"])
            self.assertEqual([w["symbol"] for w in res["dead_window_reads"]], ["Studio.missingFn"])

    def test_response_key_contract_and_verify_excludes_tests_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests").mkdir()
            (root / "tests" / "test_ui.js").write_text('fetch("/api/test-only");', encoding="utf-8")
            (root / "app.js").write_text(
                'fetch("/api/status").then(r => r.json()).then(data => data.missing_key);\n',
                encoding="utf-8",
            )
            (root / "api.py").write_text(
                'from fastapi import APIRouter\nrouter = APIRouter()\n'
                '@router.get("/api/status")\ndef status(): return {"ok": True}\n',
                encoding="utf-8",
            )
            args = argparse.Namespace(path=str(root), verify=True, strict=True, json=True, include_tests=False)
            rc = cmd_surface(args)
            self.assertEqual(rc, 1)
            files = walk_source_files(root, include_tests=False)
            res = verify_surface_contracts(root, files, scan_html_surface, scan_js_surface, scan_python_surface)
            self.assertEqual([m["key"] for m in res["response_key_mismatches"]], ["missing_key"])
            self.assertEqual(res["unmatched_fetches"], [])
