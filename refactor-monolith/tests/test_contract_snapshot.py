"""Automated unit and regression tests for contract_snapshot and surface_scanners.

Verifies detection of DOM ID parity, lost global exports, broken inline handlers,
route changes, script order, and optional tool discovery.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.contract_snapshot import (
    CodebaseContract,
    diff_contracts,
    discover_optional_tools,
)
from scripts.surface_scanners import (
    scan_css_surface,
    scan_html_surface,
    scan_js_surface,
    scan_python_surface,
)


class TestSurfaceScanners(unittest.TestCase):
    def test_scan_html_surface(self):
        html = """
        <!DOCTYPE html>
        <html>
        <head>
          <link rel="stylesheet" href="/static/css/tokens.css">
          <link rel="stylesheet" href="/static/css/layout.css">
        </head>
        <body>
          <select id="cam-select" onchange="window.App.switchCamera(this.value)">
            <option value="1">Cam 1</option>
          </select>
          <button id="btn-save" onclick="saveData()">Save</button>
          <div class="modal" id="modal-edit"></div>
          <script src="/static/js/utils.js"></script>
          <script src="/static/js/app.js"></script>
        </body>
        </html>
        """
        surf = scan_html_surface(html)
        self.assertIn("cam-select", surf.ids)
        self.assertIn("cam-select", surf.selects)
        self.assertIn("btn-save", surf.buttons)
        self.assertIn("modal-edit", surf.modals)
        self.assertEqual(len(surf.inline_handlers), 2)
        self.assertEqual(surf.inline_handlers[0]["target"], "window.App.switchCamera")
        self.assertEqual(surf.script_srcs, ["/static/js/utils.js", "/static/js/app.js"])
        self.assertEqual(surf.stylesheet_hrefs, ["/static/css/tokens.css", "/static/css/layout.css"])

    def test_scan_js_surface(self):
        js = """
        const sel = document.getElementById('cam-select');
        const card = document.querySelector('#preview-card');
        window.App = { switchCamera: (id) => {} };
        window.showToast = (msg) => {};
        document.addEventListener('DOMContentLoaded', () => {});
        export function initModule() {}
        """
        surf = scan_js_surface(js)
        self.assertIn("cam-select", surf.queried_ids)
        self.assertIn("preview-card", surf.queried_ids)
        self.assertIn("App", surf.global_exports)
        self.assertIn("showToast", surf.global_exports)
        self.assertIn("DOMContentLoaded", surf.event_listeners)
        self.assertIn("initModule", surf.es_exports)

    def test_scan_python_surface(self):
        py = """
        from fastapi import APIRouter
        router = APIRouter()
        active_stream_manager = None

        @router.get("/api/cameras/{cam_id}")
        async def get_cam(cam_id: str):
            pass

        class CameraPool:
            def add_camera(self): pass
        """
        surf = scan_python_surface(py)
        self.assertIn("CameraPool", surf.classes)
        self.assertIn("get_cam", surf.functions)
        self.assertIn("active_stream_manager", surf.mutable_globals)
        self.assertEqual(len(surf.routes), 1)
        self.assertEqual(surf.routes[0], {"method": "GET", "path": "/api/cameras/{cam_id}"})

    def test_scan_css_surface(self):
        css = """
        :root { --primary: #00ffcc; --radius: 8px; }
        .btn { color: red !important; }
        .card:fullscreen { background: black; }
        @keyframes pulse { 0% { opacity: 0; } }
        """
        surf = scan_css_surface(css)
        self.assertIn("--primary", surf.custom_properties)
        self.assertEqual(surf.important_count, 1)
        self.assertIn("pulse", surf.keyframes)
        self.assertEqual(len(surf.fullscreen_rules), 1)


class TestContractDiffEngine(unittest.TestCase):
    def test_diff_detects_missing_dom_ids(self):
        before = CodebaseContract(html_ids=["cam-select", "btn-save"])
        after = CodebaseContract(html_ids=["cam-select"], js_queried_ids=["cam-select", "btn-save", "ghost-element"])
        issues = diff_contracts(before, after)
        self.assertTrue(any("ghost-element" in iss for iss in issues))

    def test_diff_detects_lost_globals_and_selects(self):
        before = CodebaseContract(
            select_ids=["cam-select", "studio-cam-select"],
            js_global_exports=["App", "Studio", "showToast"]
        )
        after = CodebaseContract(
            select_ids=["cam-select"],
            js_global_exports=["Studio", "showToast"]
        )
        issues = diff_contracts(before, after)
        self.assertTrue(any("studio-cam-select" in iss for iss in issues))
        self.assertTrue(any("window.App" in iss for iss in issues))

    def test_diff_detects_lost_routes(self):
        before = CodebaseContract(python_routes=[{"method": "GET", "path": "/api/cameras"}])
        after = CodebaseContract(python_routes=[])
        issues = diff_contracts(before, after)
        self.assertTrue(any("/api/cameras" in iss for iss in issues))

    def test_diff_detects_css_important_creep(self):
        before = CodebaseContract(css_important_count=0)
        after = CodebaseContract(css_important_count=5)
        issues = diff_contracts(before, after)
        self.assertTrue(any("!important count increased" in iss for iss in issues))

    def test_optional_tool_discovery_does_not_crash(self):
        tools = discover_optional_tools()
        self.assertIsInstance(tools, dict)


if __name__ == "__main__":
    unittest.main()
