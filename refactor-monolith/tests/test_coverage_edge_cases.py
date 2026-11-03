"""Targeted unit tests for edge cases to achieve near-100% test coverage.

Covers error handling, environment fallback paths, subprocess failures,
and boundary conditions across all scripts in refactor-monolith.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

_SKILL_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _SKILL_ROOT / "scripts"
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from scripts.auxiliary_tool_bridge import auto_detect_app_url, auto_detect_container, cmd_audit_container, cmd_diagnose, cmd_run_tests, cmd_verify_ui, discover_optional_tools, _diagnose_contracts, _diagnose_container, _diagnose_ui
from scripts.file_patcher import (
    cmd_normalize_eol,
    inject_html_scripts,
    normalize_file_eol,
    patch_file_content,
)
from scripts.css_inspector import cmd_inspect_css, _inspect_single_css_file
from scripts.smoke_test_generator import cmd_generate_smoke_test
from scripts.surface_scanners import scan_html_surface, scan_js_surface, scan_python_surface
from scripts.campaign_manager import cmd_state, get_git_sha
from scripts.contract_diff_engine import diff_contracts, CodebaseContract

class TestAuxiliaryBridgeEdgeCases(unittest.TestCase):
    def test_run_tests_failure_and_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            # Subprocess non-zero return
            with mock.patch("subprocess.run") as mock_sub:
                mock_sub.return_value = mock.Mock(returncode=1)
                code = cmd_run_tests(p, ["discover", "tests"])
                self.assertEqual(code, 1)

            # Subprocess raises OSError
            with mock.patch("subprocess.run", side_effect=OSError("spawn failed")):
                code = cmd_run_tests(p, ["discover", "tests"])
                self.assertEqual(code, 1)

    def test_auto_detect_container_env_and_docker_ps(self):
        with mock.patch.dict(os.environ, {"DOCKER_CONTAINER": "custom_container"}):
            self.assertEqual(auto_detect_container(), "custom_container")

        with mock.patch.dict(os.environ, {}, clear=True):
            # docker ps succeeds with matching name
            with mock.patch("subprocess.run") as mock_sub:
                mock_sub.return_value = mock.Mock(returncode=0, stdout="my_dashboard_1\nother_box\n")
                self.assertEqual(auto_detect_container(), "my_dashboard_1")

            # docker ps succeeds with generic first name
            with mock.patch("subprocess.run") as mock_sub:
                mock_sub.return_value = mock.Mock(returncode=0, stdout="random_service\n")
                self.assertEqual(auto_detect_container(), "random_service")

            # docker ps fails or throws
            with mock.patch("subprocess.run", side_effect=Exception("no docker")):
                self.assertEqual(auto_detect_container(), "")

    def test_auto_detect_app_url_env_and_ports(self):
        with mock.patch.dict(os.environ, {"APP_URL": "http://example.com:9000"}):
            self.assertEqual(auto_detect_app_url(), "http://example.com:9000")

        with mock.patch.dict(os.environ, {}, clear=True):
            # Mock successful response
            with mock.patch("urllib.request.urlopen") as mock_open:
                mock_resp = mock.MagicMock()
                mock_resp.status = 200
                mock_open.return_value.__enter__.return_value = mock_resp
                self.assertEqual(auto_detect_app_url(), "http://127.0.0.1:8000")

            # Mock HTTPError 404 (still an active server!)
            with mock.patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("url", 404, "Not Found", {}, None)):
                self.assertEqual(auto_detect_app_url(), "http://127.0.0.1:8000")

            # Mock connection refused
            with mock.patch("urllib.request.urlopen", side_effect=OSError("Connection refused")):
                self.assertEqual(auto_detect_app_url(), "")

    def test_verify_ui_execution_and_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            # When cdp_inspect script missing and strict=True
            with mock.patch("scripts.auxiliary_tool_bridge.discover_optional_tools", return_value={}):
                code = cmd_verify_ui(p, url="http://127.0.0.1:8000", strict=True)
                self.assertEqual(code, 1)

            # When cdp_inspect script present but no url
            mock_tools = {"cdp_inspect": "cdp_inspect.py"}
            with mock.patch("scripts.auxiliary_tool_bridge.discover_optional_tools", return_value=mock_tools):
                with mock.patch("scripts.auxiliary_tool_bridge.auto_detect_app_url", return_value=""):
                    code = cmd_verify_ui(p, url="", strict=False)
                    self.assertEqual(code, 0)

            # When execution returns non-zero code
            with mock.patch("scripts.auxiliary_tool_bridge.discover_optional_tools", return_value=mock_tools):
                with mock.patch("subprocess.run") as mock_sub:
                    mock_sub.return_value = mock.Mock(returncode=2, stdout="", stderr="Error connecting to Chrome")
                    code = cmd_verify_ui(p, url="http://127.0.0.1:8000", selectors="div.nav", headless=True)
                    self.assertEqual(code, 1)

            # When execution throws exception
            with mock.patch("scripts.auxiliary_tool_bridge.discover_optional_tools", return_value=mock_tools):
                with mock.patch("subprocess.run", side_effect=Exception("Process error")):
                    code = cmd_verify_ui(p, url="http://127.0.0.1:8000", strict=True)
                    self.assertEqual(code, 1)

    def test_audit_container_execution_and_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            mock_tools = {"docker_audit": "docker_audit.py"}
            with mock.patch("scripts.auxiliary_tool_bridge.discover_optional_tools", return_value=mock_tools):
                # Successful run with container and sync-check
                with mock.patch("subprocess.run") as mock_sub:
                    mock_sub.return_value = mock.Mock(returncode=0)
                    code = cmd_audit_container(p, container="my_app", sync_check=["app.py"])
                    self.assertEqual(code, 0)

                # Execution throws exception
                with mock.patch("subprocess.run", side_effect=Exception("Docker failed")):
                    code = cmd_audit_container(p, container="my_app")
                    self.assertEqual(code, 1)

    def test_diagnose_contracts_and_tiers(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "index.html").write_text('<div id="foo"></div>', encoding="utf-8")

            # 1. No baseline or git ref: captures current contract
            issues = _diagnose_contracts(p, before_file="", git_ref="")
            self.assertEqual(issues, [])

            # 2. With real baseline file showing missing select
            before_file = p / "baseline.json"
            before_file.write_text(json.dumps({"select_ids": ["old_sel"], "html_ids": [], "python_routes": []}), encoding="utf-8")
            issues = _diagnose_contracts(p, before_file=str(before_file), git_ref="")
            self.assertTrue(len(issues) > 0)
            self.assertTrue(any("old_sel" in iss for iss in issues))

            # 3. Diagnose container and UI branches
            with mock.patch("scripts.auxiliary_tool_bridge.auto_detect_container", return_value="c1"):
                with mock.patch("scripts.auxiliary_tool_bridge.cmd_audit_container", return_value=0):
                    code, st = _diagnose_container(p, "")
                    self.assertEqual(code, 0)
                    self.assertIn("VERIFIED", st)

            with mock.patch("scripts.auxiliary_tool_bridge.auto_detect_app_url", return_value="http://127.0.0.1:8000"):
                with mock.patch("scripts.auxiliary_tool_bridge.cmd_verify_ui", return_value=0):
                    code, st = _diagnose_ui(p, "", strict=False)
                    self.assertEqual(code, 0)
                    self.assertIn("VERIFIED", st)

            # 4. cmd_diagnose with failures in strict mode
            with mock.patch("scripts.auxiliary_tool_bridge._diagnose_contracts", return_value=["ID dropped"]):
                with mock.patch("scripts.auxiliary_tool_bridge._diagnose_container", return_value=(0, "SKIPPED")):
                    with mock.patch("scripts.auxiliary_tool_bridge._diagnose_ui", return_value=(0, "SKIPPED")):
                        code = cmd_diagnose(p, strict=True)
                        self.assertEqual(code, 1)

class TestFilePatcherEdgeCases(unittest.TestCase):
    def test_normalize_file_eol_edge_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            # Binary file should be skipped
            bin_file = p / "test.png"
            bin_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")
            ok, msg = normalize_file_eol(bin_file, "\n")
            self.assertFalse(ok)
            self.assertIn("Skipped binary file", msg)

            # Text file already normalized should be skipped
            txt_file = p / "test.txt"
            txt_file.write_bytes(b"line1\nline2\n")
            ok, msg = normalize_file_eol(txt_file, "\n")
            self.assertFalse(ok)
            self.assertIn("Already using LF", msg)

            # Non-existent file results in 0 converted
            code = cmd_normalize_eol(p / "nonexistent.txt", "lf")
            self.assertEqual(code, 0)

    def test_patch_file_content_edge_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            txt = p / "test.txt"
            txt.write_bytes(b"Hello World\n")

            # Missing target
            ok, msg = patch_file_content(txt, "TargetNotFound", "Replacement")
            self.assertFalse(ok)
            self.assertIn("Target content not found", msg)

            # Whitespace-only target not found triggers "Target text is empty"
            ok, msg = patch_file_content(txt, "   \n  \n   ", "Replacement")
            self.assertFalse(ok)
            self.assertIn("Target text is empty", msg)

            # Non-existent file
            ok, msg = patch_file_content(p / "missing.txt", "A", "B")
            self.assertFalse(ok)

    def test_inject_html_scripts_edge_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            html = p / "index.html"
            html.write_text('<html><body><script src="/static/a.js"></script></body></html>', encoding="utf-8")

            # Script already exists
            ok, msg = inject_html_scripts(html, ["/static/a.js"])
            self.assertTrue(ok)
            self.assertIn("already present", msg)

            # Before script not found fallback
            ok, msg = inject_html_scripts(html, ["/static/b.js"], before_script="nonexistent.js")
            self.assertTrue(ok)
            self.assertIn("Injected 1 script", msg)
            content = html.read_text(encoding="utf-8")
            self.assertIn("/static/b.js", content)

            # Missing HTML file
            ok, msg = inject_html_scripts(p / "missing.html", ["/static/b.js"])
            self.assertFalse(ok)

class TestCssAndSmokeEdgeCases(unittest.TestCase):
    def test_css_inspector_edge_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            # Non-existent path
            code = cmd_inspect_css(p / "missing.css")
            self.assertEqual(code, 2)

            # Binary file
            bin_css = p / "blob.css"
            bin_css.write_bytes(b"\x00\x01\x02\x03\xff")
            code, data = _inspect_single_css_file(bin_css)
            self.assertEqual(code, 0)

            # > 15 section banners
            many_banners = p / "many.css"
            content = "\n".join(f"/* === Section {i} === */\n.c{i} {{ color: blue; }}" for i in range(20))
            many_banners.write_text(content, encoding="utf-8")
            code = cmd_inspect_css(many_banners, show_all=False)
            self.assertEqual(code, 0)

    def test_smoke_test_generator_edge_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            # Write error to unwritable path
            bad_path = p / "readonly" / "sub" / "test.py"
            # Target dir has no baseline or git ref
            code = cmd_generate_smoke_test(p, out_file=str(p / "smoke.py"))
            self.assertEqual(code, 0)
            self.assertTrue((p / "smoke.py").exists())

class TestSurfaceScannersAndCampaignEdgeCases(unittest.TestCase):
    def test_surface_scanners_syntax_error_and_edge_cases(self):
        # Python syntax error
        broken_py = "def foo(\n   bad syntax = = ="
        data = scan_python_surface(broken_py)
        self.assertEqual(data.routes, [])

        # HTML scanner
        sample_html = "<div><select id='my-sel'></select><button id='my-btn'></button></div>"
        data_html = scan_html_surface(sample_html)
        self.assertIn("my-sel", data_html.selects)
        self.assertIn("my-btn", data_html.buttons)
        self.assertIn("my-sel", data_html.ids)

        # JS window properties
        js = "window.MyService = {}; window.AnotherModule = 123;"
        data_js = scan_js_surface(js)
        self.assertIn("MyService", data_js.global_exports)
        self.assertIn("AnotherModule", data_js.global_exports)

    def test_campaign_manager_edge_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            # get_git_sha non-git directory returns empty string
            sha = get_git_sha(p)
            self.assertEqual(sha, "")

            # cmd_state unknown action
            code = cmd_state(p, action="invalid_action")
            self.assertEqual(code, 1)

            # Advance when already completed
            cmd_state(p, action="init", plan="plan.md", phases=1)
            cmd_state(p, action="advance")
            code = cmd_state(p, action="advance")
            self.assertEqual(code, 0)

    def test_contract_diff_route_changes(self):
        before = CodebaseContract(python_routes=[{"method": "POST", "path": "/api/users"}])
        after = CodebaseContract(python_routes=[{"method": "GET", "path": "/api/users"}])
        issues = diff_contracts(before, after)
        self.assertTrue(any("API route POST /api/users" in iss for iss in issues))

if __name__ == "__main__":
    unittest.main()
