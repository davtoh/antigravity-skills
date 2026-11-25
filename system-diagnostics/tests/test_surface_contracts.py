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

    def test_es6_shorthand_fetch_response_helpers_forms_and_scoped_dupes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text(
                '<nav class="nav-tabs"><button class="nav-tab" id="tab-a">Live</button></nav>'
                '<div class="drawer-nav"><button class="drawer-tab" id="drw-a">Live</button></div>'
                '<div class="modal" id="m1"><form id="f1"><button id="sub1" type="submit">Go</button></form><button id="c1">&times;</button></div>'
                '<div class="modal" id="m2"><button id="c2">&times;</button></div>',
                encoding="utf-8",
            )
            (root / "app.js").write_text(
                'const openModal = () => {}; window.Batch = { openModal };\n'
                'window.Batch.openModal();\n'
                'document.querySelectorAll(".nav-tab, .drawer-tab");\n'
                'document.getElementById("f1"); el("c1"); bindOnce("c2", "click", () => {});\n'
                'fetch("/api/status").then(res => { if (!res.ok) return; return res.json(); });\n',
                encoding="utf-8",
            )
            (root / "api.py").write_text(
                'from fastapi import APIRouter\nrouter = APIRouter()\n'
                '@router.get("/api/status")\ndef status(): return {"healthy": True}\n',
                encoding="utf-8",
            )
            files = walk_source_files(root)
            res = verify_surface_contracts(root, files, scan_html_surface, scan_js_surface, scan_python_surface)
            self.assertEqual(res["summary"]["total_mismatches"], 0, f"Unexpected: {res}")

    def test_fallback_id_or_pair_table_bindings_and_param_fetch_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text(
                '<img id="live-stream-img" />'
                '<button id="drawer-btn-enroll">Enroll</button>'
                '<div class="modal" id="modal-enroll"></div>',
                encoding="utf-8",
            )
            (root / "app.js").write_text(
                'const liveVideo = el("live-stream-img") || el("video-stream");\n'
                'window.addEventListener("tab-changed", () => {});\n'
                '[["drawer-btn-enroll", "modal-enroll"]].forEach(([b, m]) => document.getElementById(b)?.addEventListener("click", () => m));\n'
                'fetch(`/api/cameras/${encodeURIComponent(id)}/${action}`, { method: "POST" });\n',
                encoding="utf-8",
            )
            (root / "api.py").write_text(
                'from fastapi import APIRouter\nrouter = APIRouter()\n'
                '@router.post("/api/cameras/{camera_id}/release")\ndef rel(): return {"ok": True}\n',
                encoding="utf-8",
            )
            files = walk_source_files(root)
            res = verify_surface_contracts(root, files, scan_html_surface, scan_js_surface, scan_python_surface)
            self.assertEqual(res["summary"]["total_mismatches"], 0, f"Unexpected: {res}")

    def test_transcript_checks_bg_audit_truncated_exit_and_priority_snippet(self):
        import transcript_checks as tc
        pad = "INFO line\n" * 160
        bg_audit = f"<SYSTEM_MESSAGE>\nCommand exited with code 1.\n{pad}Audit Result: DEFECTS_FOUND\n</SYSTEM_MESSAGE>"
        self.assertEqual(tc.classify_result(bg_audit, "DONE", "echo ok"), "audit_catch")
        mypy_audit = f"<SYSTEM_MESSAGE>\nCommand exited with code 1.\ncam.py:1: error: Argument \"classes\"\n{pad}Audit Result: DEFECTS_FOUND\n</SYSTEM_MESSAGE>"
        self.assertEqual(tc.classify_result(mypy_audit, "DONE", "diagnose.py audit"), "audit_catch")
        trunc_fail = f"The tool's output was truncated.\n{'x' * 420}\nCommand exited with code 1.\nFAIL: test_box\n"
        self.assertEqual(tc.classify_result(trunc_fail, "DONE", "pytest"), "cmd_fail")
        self.assertEqual(tc.failure_snippet("FAIL: test_one\n[mov,mp4] moov atom not found"), "FAIL: test_one")
        notes: list[str] = []
        tc.append_row_notes({"cid": "8c26213a", "failures": {"cmd_fail": 4}, "total_failures": 4, "tooling_cli_fails": 1, "failure_samples": ["s1 pytest: FAIL"], "parallel_same_file_edits": [], "subagents": []}, "8c26213a", notes)
        self.assertFalse(any("unescalated thrash" in n for n in notes))

    def test_script_wrap_order_and_query_param_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text(
                '<script src="/static/nav_tabs_manager.js"></script><script src="/static/app.js"></script>',
                encoding="utf-8",
            )
            (root / "app.js").write_text("window.switchTab = function(t) { return t; };", encoding="utf-8")
            (root / "nav_tabs_manager.js").write_text(
                "const orig = window.switchTab; window.switchTab = (t) => orig(t);\n"
                "fetch('/analytics/heatmap?camera_id=cam_1&bogus_param=2');\n",
                encoding="utf-8",
            )
            (root / "api.py").write_text(
                'from fastapi import APIRouter\nrouter = APIRouter()\n'
                '@router.get("/analytics/heatmap")\ndef hm(camera_id: str = ""): return {}\n',
                encoding="utf-8",
            )
            files = walk_source_files(root)
            res = verify_surface_contracts(root, files, scan_html_surface, scan_js_surface, scan_python_surface)
            self.assertEqual([w["symbol"] for w in res["script_order_warnings"]], ["switchTab"])
            self.assertEqual([(w["path"], w["param"]) for w in res["query_param_warnings"]], [("/analytics/heatmap", "bogus_param")])

    def test_undefined_layout_class_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text(
                '<div class="modal-wide split-pane custom-tag"></div>',
                encoding="utf-8",
            )
            (root / "styles.css").write_text(".modal-wide { width: 80vw; }\n", encoding="utf-8")
            files = walk_source_files(root)
            res = verify_surface_contracts(root, files, scan_html_surface, scan_js_surface, scan_python_surface)
            self.assertEqual([u["class"] for u in res["undefined_layout_classes"]], ["split-pane"])
            self.assertEqual(res["summary"]["undefined_layout_classes"], 1)

    def test_fetch_default_get_method_parity_and_app_navigate_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text(
                '<div id="tab-live"></div><button id="btn-jump" onclick="App.navigate(\'tab-missing\')">Jump</button>',
                encoding="utf-8",
            )
            (root / "app.js").write_text(
                'document.getElementById("btn-jump");\n'
                'fetch("/api/post-only", {});\n'
                'App.navigate("tab-live");\n',
                encoding="utf-8",
            )
            (root / "api.py").write_text(
                'from fastapi import APIRouter\nrouter = APIRouter()\n'
                '@router.post("/api/post-only")\ndef do_post(): return {"ok": True}\n',
                encoding="utf-8",
            )
            files = walk_source_files(root)
            res = verify_surface_contracts(root, files, scan_html_surface, scan_js_surface, scan_python_surface)
            self.assertEqual([(u["method"], u["path"]) for u in res["unmatched_fetches"]], [("GET", "/api/post-only")])
            self.assertEqual([n["target"] for n in res["invalid_nav_targets"]], ["tab-missing"])
