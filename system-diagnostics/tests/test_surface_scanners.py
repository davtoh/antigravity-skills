#!/usr/bin/env python3
"""Automated unit test suite for surface_scanners.py in system-diagnostics.

Zero external dependencies; standard library Python 3.10+ only.
Tests extraction of HTML elements, JS globals/queries, Python routes, and CSS properties.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Ensure system-diagnostics/scripts is in sys.path
SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from surface_scanners import (
    scan_css_surface,
    scan_html_surface,
    scan_js_surface,
    scan_python_surface,
)


class TestSurfaceScanners(unittest.TestCase):
    """Test suite for static AST/DOM surface scanners."""

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

    def test_scan_js_surface_ignores_equality_comparisons_and_builtins(self):
        js = """
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        if (window.location.protocol == 'http:') {}
        if (window.activeUser !== null) {}
        window.location.href = '/login';
        window.document.title = 'Dashboard';
        window.localStorage.token = 'abc';
        window.App = { init: () => {} };
        window.VideoScrubber.onTabEnter = () => {};
        """
        surf = scan_js_surface(js)
        self.assertIn("App", surf.global_exports)
        self.assertIn("VideoScrubber.onTabEnter", surf.global_exports)
        self.assertNotIn("location.protocol", surf.global_exports)
        self.assertNotIn("location.href", surf.global_exports)
        self.assertNotIn("document.title", surf.global_exports)
        self.assertNotIn("localStorage.token", surf.global_exports)
        self.assertNotIn("activeUser", surf.global_exports)

    def test_scan_python_surface(self):
        py = """
        from fastapi import APIRouter
        router = APIRouter()
        active_stream_manager = None

        @router.get("/api/cameras/{cam_id}")
        async def get_cam(cam_id: str):
            pass

        @router.route("/api/items", methods=["GET", "POST"])
        def handle_items():
            return []

        class CameraPool:
            def add_camera(self): pass
        """
        surf = scan_python_surface(py, rel_path="dashboard/routers/cameras.py")
        self.assertIn("CameraPool", surf.classes)
        self.assertIn("get_cam", surf.functions)
        self.assertIn("handle_items", surf.functions)
        self.assertIn("active_stream_manager", surf.mutable_globals)
        self.assertEqual(len(surf.routes), 3)

        r0 = surf.routes[0]
        self.assertEqual(r0["method"], "GET")
        self.assertEqual(r0["path"], "/api/cameras/{cam_id}")
        self.assertEqual(r0["handler"], "get_cam")
        self.assertEqual(r0["file"], "dashboard/routers/cameras.py")
        self.assertIsInstance(r0["line"], int)

        methods = [r["method"] for r in surf.routes[1:]]
        self.assertIn("GET", methods)
        self.assertIn("POST", methods)
        self.assertEqual(surf.routes[1]["path"], "/api/items")
        self.assertEqual(surf.routes[1]["handler"], "handle_items")

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


if __name__ == "__main__":
    unittest.main()

