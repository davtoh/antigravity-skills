"""Automated unit and regression tests for contract_snapshot and surface_scanners.

Verifies detection of DOM ID parity, lost global exports, broken inline handlers,
route changes, script order, and optional tool discovery.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.contract_snapshot import (
    CodebaseContract,
    cmd_generate_smoke_test,
    cmd_inspect,
    cmd_state,
    diff_contracts,
    discover_optional_tools,
    get_refactor_dir,
    _format_phase_icon,
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

        # Check first route
        r0 = surf.routes[0]
        self.assertEqual(r0["method"], "GET")
        self.assertEqual(r0["path"], "/api/cameras/{cam_id}")
        self.assertEqual(r0["handler"], "get_cam")
        self.assertEqual(r0["file"], "dashboard/routers/cameras.py")
        self.assertIsInstance(r0["line"], int)

        # Check multi-method route
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


class TestContractDiffEngine(unittest.TestCase):
    def test_diff_detects_missing_dom_ids(self):
        before = CodebaseContract(html_ids=["cam-select", "btn-save"])
        after = CodebaseContract(html_ids=["cam-select"], js_queried_ids=["cam-select", "btn-save", "ghost-element"])
        issues = diff_contracts(before, after)
        self.assertTrue(any("ghost-element" in iss for iss in issues))

    def test_diff_ignores_preexisting_unmapped_dom_ids(self):
        """Pre-existing unmapped JS queries present in baseline must not trigger false positive regression."""
        before = CodebaseContract(html_ids=["cam-1"], js_queried_ids=["cam-1", "legacy-dead-id"])
        after = CodebaseContract(html_ids=["cam-1"], js_queried_ids=["cam-1", "legacy-dead-id"])
        issues = diff_contracts(before, after)
        self.assertEqual(issues, [])

    def test_diff_detects_removed_html_id_when_queried_by_js(self):
        """If an HTML ID is deleted during refactoring while JS queries it, must trigger CRITICAL DOM."""
        before = CodebaseContract(html_ids=["cam-1", "player-box"], js_queried_ids=["player-box"])
        after = CodebaseContract(html_ids=["cam-1"], js_queried_ids=["player-box"])
        issues = diff_contracts(before, after)
        self.assertTrue(any("player-box" in iss for iss in issues))

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


class TestCampaignAndTools(unittest.TestCase):
    def test_state_management_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / ".git").mkdir()
            target = base / "dashboard"
            target.mkdir()

            # 1. Init state
            code = cmd_state(target, action="init", plan=".refactor/plan.md", phases=3, phase_title="Domain Decoupling")
            self.assertEqual(code, 0)
            state_file = base / ".refactor" / "state.json"
            self.assertTrue(state_file.exists())
            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual(state["active_phase"], 1)
            self.assertEqual(state["total_phases"], 3)
            self.assertEqual(state["phases"]["1"]["title"], "Domain Decoupling")

            # 2. Advance phase
            code = cmd_state(target, action="advance", sha="abcdef1")
            self.assertEqual(code, 0)
            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual(state["active_phase"], 2)
            self.assertEqual(state["phases"]["1"]["status"], "completed")
            self.assertEqual(state["phases"]["1"]["sha"], "abcdef1")

    def test_generate_smoke_test_scopes_root_and_excludes_ignored_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / ".git").mkdir()
            dashboard = base / "dashboard"
            dashboard.mkdir()
            (dashboard / "index.html").write_text('<select id="cam-sel"></select><div id="player"></div>', encoding="utf-8")
            (dashboard / "styles.css").write_text('.c { color: red !important; }', encoding="utf-8")

            out_test = base / "tests" / "test_refactor_contract.py"
            code = cmd_generate_smoke_test(dashboard, out_file=str(out_test))
            self.assertEqual(code, 0)
            self.assertTrue(out_test.exists())

            test_content = out_test.read_text(encoding="utf-8")
            self.assertIn("cam-sel", test_content)
            self.assertIn("dashboard", test_content)
            self.assertIn('".refactor"', test_content)
            self.assertIn('".venv"', test_content)

    def test_optional_tool_discovery_does_not_crash(self):
        tools = discover_optional_tools()
        self.assertIsInstance(tools, dict)

    def test_refactor_dir_creates_subdirectories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            rdir = get_refactor_dir(base)
            self.assertTrue((rdir / "scripts").is_dir())
            self.assertTrue((rdir / "artifacts").is_dir())
            gitignore = rdir / ".gitignore"
            self.assertTrue(gitignore.is_file())
            content = gitignore.read_text(encoding="utf-8")
            self.assertIn("*", content)
            self.assertIn("!.gitignore", content)

    def test_inspect_show_routes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / ".git").mkdir()
            sub = base / "api"
            sub.mkdir()
            (sub / "routes.py").write_text(
                'from fastapi import APIRouter\n'
                'router = APIRouter()\n'
                '@router.get("/status")\n'
                'def get_status():\n'
                '    return {"ok": True}\n',
                encoding="utf-8",
            )
            # Test default inspect
            code = cmd_inspect(sub, show_routes=False)
            self.assertEqual(code, 0)

            # Test inspect with show_routes
            code_all = cmd_inspect(sub, show_routes=True)
            self.assertEqual(code_all, 0)

    def test_format_phase_icon_fallback(self):
        # Normal UTF-8 check
        icon_done = _format_phase_icon(is_completed=True, is_active=False)
        self.assertIn(icon_done, ["✅", "[x]"])

        icon_act = _format_phase_icon(is_completed=False, is_active=True)
        self.assertIn(icon_act, ["▶️", "[>]"])

        icon_pend = _format_phase_icon(is_completed=False, is_active=False)
        self.assertIn(icon_pend, ["⏳", "[ ]"])

    def test_discover_virtualenv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / ".git").mkdir()
            venv = base / ".venv"
            venv.mkdir()
            bin_dir = venv / ("Scripts" if sys.platform == "win32" else "bin")
            bin_dir.mkdir(parents=True)
            py_exe = bin_dir / ("python.exe" if sys.platform == "win32" else "python")
            py_exe.write_text("", encoding="utf-8")

            tools = discover_optional_tools(base)
            self.assertIn("virtualenv_python", tools)
            self.assertEqual(tools["virtualenv_python"], str(py_exe))


if __name__ == "__main__":
    unittest.main()
