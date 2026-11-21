#!/usr/bin/env python3
"""Automated unit test suite for Unified System Diagnostics CLI (diagnose.py).

Zero external dependencies; standard library Python 3.10+ only.
Tests all subcommands: ui, container, surface, tests, all.
"""

import argparse
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure system-diagnostics/scripts is in sys.path
SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import diagnose

class TestAutoDiscovery(unittest.TestCase):
    """Test environment and service auto-discovery helpers."""

    def test_probe_local_port_found(self):
        with patch("socket.create_connection") as mock_conn:
            mock_conn.return_value.__enter__.return_value = MagicMock()
            url = diagnose.probe_local_port([8000])
            self.assertEqual(url, "http://localhost:8000")

    def test_probe_local_port_none_open(self):
        with patch("socket.create_connection", side_effect=ConnectionRefusedError):
            url = diagnose.probe_local_port([8000, 3000])
            self.assertIsNone(url)

    def test_probe_docker_container_no_cli(self):
        with patch("shutil.which", return_value=None):
            container = diagnose.probe_docker_container()
            self.assertIsNone(container)

    def test_probe_docker_container_success(self):
        with patch("shutil.which", return_value="/usr/bin/docker"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="redis_cache\napp_dashboard\npostgres_db\n"
            )
            container = diagnose.probe_docker_container()
            self.assertEqual(container, "app_dashboard")

    def test_find_virtualenv_python_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            py = diagnose.find_virtualenv_python(Path(tmpdir))
            self.assertEqual(py, sys.executable)

    def test_find_virtualenv_python_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            venv_bin = root / ".venv" / ("Scripts" if os.name == "nt" else "bin")
            venv_bin.mkdir(parents=True)
            mock_py = venv_bin / ("python.exe" if os.name == "nt" else "python")
            mock_py.write_text("#!/bin/sh\n")

            found = diagnose.find_virtualenv_python(root)
            self.assertEqual(found, str(mock_py))

class TestParser(unittest.TestCase):
    """Test CLI argument parsing for all subcommands."""

    def setUp(self):
        self.parser = diagnose.build_parser()

    def test_parse_ui_subcommand(self):
        args = self.parser.parse_args(["ui", "--url", "http://localhost:8000", "--audit-layout", "--live", "--wait", "2.5", "--strict"])
        self.assertEqual(args.subcommand, "ui")
        self.assertEqual(args.url, "http://localhost:8000")
        self.assertTrue(args.audit_layout)
        self.assertTrue(args.live)
        self.assertEqual(args.wait, 2.5)
        self.assertTrue(args.strict)

    def test_parse_ui_defaults(self):
        args = self.parser.parse_args(["ui"])
        self.assertEqual(args.wait, 1.5)
        self.assertFalse(args.strict)

    def test_parse_container_subcommand(self):
        args = self.parser.parse_args(["container", "--container", "my-app", "--workdir", "/srv", "--lines", "100"])
        self.assertEqual(args.subcommand, "container")
        self.assertEqual(args.container, "my-app")
        self.assertEqual(args.workdir, "/srv")
        self.assertEqual(args.lines, 100)

    def test_parse_surface_subcommand(self):
        args = self.parser.parse_args(["surface", "--path", "src", "--show-ids", "--json"])
        self.assertEqual(args.subcommand, "surface")
        self.assertEqual(args.path, "src")
        self.assertTrue(args.show_ids)
        self.assertTrue(args.json)

    def test_parse_tests_subcommand(self):
        args = self.parser.parse_args(["tests", "--path", ".", "tests.test_unit"])
        self.assertEqual(args.subcommand, "tests")
        self.assertEqual(args.args, ["tests.test_unit"])

    def test_parse_all_subcommand(self):
        args = self.parser.parse_args(["all", "--url", "http://localhost:3000", "--wait", "3.0", "--strict"])
        self.assertEqual(args.subcommand, "all")
        self.assertEqual(args.url, "http://localhost:3000")
        self.assertEqual(args.wait, 3.0)
        self.assertTrue(args.strict)

    def test_parse_scan_subcommand(self):
        args = self.parser.parse_args(["scan", "--path", "src", "tests", "--deep", "--json", "--strict"])
        self.assertEqual(args.subcommand, "scan")
        self.assertEqual(args.path, ["src", "tests"])
        self.assertTrue(args.deep)
        self.assertTrue(args.json)
        self.assertTrue(args.strict)

    def test_parse_scaffold_defect_subcommand(self):
        args = self.parser.parse_args(["scaffold-defect", "--id", "DEFECT-001", "--branch", "--elevate"])
        self.assertEqual(args.subcommand, "scaffold-defect")
        self.assertEqual(args.id, "DEFECT-001")
        self.assertTrue(args.branch)
        self.assertTrue(args.elevate)

class TestSubcommandsExecution(unittest.TestCase):
    """Test execution dispatch of subcommands."""

    def test_cmd_surface_isolated_workspace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "index.html").write_text('<div id="main-view"><select id="model-select"></select></div>', encoding="utf-8")
            (root / "app.js").write_text('window.AppEngine = {}; document.getElementById("main-view");', encoding="utf-8")
            (root / "routes.py").write_text('@app.get("/api/v1/health")\ndef health(): return {"ok": True}\n', encoding="utf-8")
            (root / "style.css").write_text('.card { color: red !important; }', encoding="utf-8")

            args = argparse.Namespace(
                path=str(root),
                show_ids=True,
                show_globals=True,
                show_routes=True,
                json=False,
            )
            code = diagnose.cmd_surface(args)
            self.assertEqual(code, 0)

    def test_cmd_ui_missing_url_returns_error(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch("diagnose.probe_local_port", return_value=None):
            args = argparse.Namespace(
                url=None, list_tabs=False, audit_layout=False, selectors=None,
                screenshot=None, eval=None, click=None, navigate=False,
                window_size=None, headless=True, live=False
            )
            code = diagnose.cmd_ui(args)
            self.assertEqual(code, 2)

    def test_cmd_ui_invokes_cdp_inspect(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            args = argparse.Namespace(
                url="http://localhost:8000", list_tabs=False, audit_layout=True,
                selectors="#app", screenshot=None, eval=None, click=None,
                navigate=True, window_size="1920x1080", headless=True, live=False,
                wait=2.0, strict=True
            )
            code = diagnose.cmd_ui(args)
            self.assertEqual(code, 0)
            mock_run.assert_called_once()
            called_cmd = mock_run.call_args[0][0]
            self.assertIn("cdp_inspect.py", called_cmd[1])
            self.assertIn("--audit-layout", called_cmd)
            self.assertIn("--navigate", called_cmd)
            self.assertIn("--wait", called_cmd)
            self.assertIn("2.0", called_cmd)
            self.assertIn("--strict", called_cmd)

    def test_cmd_ui_live_omits_headless_and_forwards_eval_file(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            parser = diagnose.build_parser()
            args = parser.parse_args([
                "ui", "--url", "http://localhost:8000", "--live",
                "--eval-file", "probe.js", "--port", "9222", "--no-fallback-headless",
            ])
            code = diagnose.cmd_ui(args)
            self.assertEqual(code, 0)
            called_cmd = mock_run.call_args[0][0]
            self.assertNotIn("--headless", called_cmd)
            self.assertIn("--eval-file", called_cmd)
            self.assertIn("probe.js", called_cmd)
            self.assertIn("--port", called_cmd)
            self.assertIn("9222", called_cmd)
            self.assertIn("--no-fallback-headless", called_cmd)
            self.assertIn("--capture-runtime", called_cmd)

            args_no_rt = parser.parse_args([
                "ui", "--url", "http://localhost:8000", "--eval-file", "probe.js", "--no-capture-runtime",
            ])
            cmd_no_rt = diagnose.diagnose_cli.build_ui_command(diagnose.SCRIPTS_DIR, "http://localhost:8000", args_no_rt)
            self.assertNotIn("--capture-runtime", cmd_no_rt)
            self.assertIn("--no-capture-runtime", cmd_no_rt)

            args_eval_file = parser.parse_args(["ui", "--url", "http://localhost:8000", "--eval-file", "probe.js"])
            cmd_eval_file = diagnose.diagnose_cli.build_ui_command(diagnose.SCRIPTS_DIR, "http://localhost:8000", args_eval_file)
            self.assertIn("--capture-runtime", cmd_eval_file)

            args_plain = parser.parse_args(["ui", "--url", "http://localhost:8000", "--audit-layout"])
            cmd_plain = diagnose.diagnose_cli.build_ui_command(diagnose.SCRIPTS_DIR, "http://localhost:8000", args_plain)
            self.assertNotIn("--capture-runtime", cmd_plain)
            self.assertNotIn("--no-capture-runtime", cmd_plain)

    def test_stage_standalone_skill_materializes_ssot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_root = diagnose.SCRIPTS_DIR.parent.parent
            fa_dir = skills_root / "frontier-architect"
            staged = diagnose.skill_packager.stage_standalone_skill(fa_dir, Path(tmpdir))
            self.assertFalse((staged / "tests").exists())
            self.assertFalse((staged / "evals").exists())
            self.assertFalse((staged / "scripts" / ".mypy_cache").exists())
            self.assertFalse((staged / "scripts" / ".ruff_cache").exists())
            self.assertTrue((staged / "scripts" / "cdp_transport.py").is_file())
            self.assertTrue((staged / "scripts" / "audit_layout.js").is_file())
            cdp_lines = (staged / "scripts" / "cdp_inspect.py").read_text(encoding="utf-8").splitlines()
            self.assertGreater(len(cdp_lines), 100)

            rm_dir = skills_root / "refactor-monolith"
            rm_staged = diagnose.skill_packager.stage_standalone_skill(rm_dir, Path(tmpdir))
            proc = subprocess.run(
                [sys.executable, "-c", "import scripts.css_inspector; import scripts.surface_scanners"],
                cwd=str(rm_staged),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.assertEqual(proc.returncode, 0, f"Standalone import failed: {proc.stderr}")

    def test_cmd_container_invokes_docker_audit(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            args = argparse.Namespace(
                container="test-container", workdir="/app",
                sync_check=["app.py"], lines=100
            )
            code = diagnose.cmd_container(args)
            self.assertEqual(code, 0)
            mock_run.assert_called_once()
            called_cmd = mock_run.call_args[0][0]
            self.assertIn("docker_audit.py", called_cmd[1])
            self.assertIn("--container", called_cmd)

    def test_cmd_tests_executes_test_runner(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                args = argparse.Namespace(path=tmpdir, args=["discover"])
                code = diagnose.cmd_tests(args)
                self.assertEqual(code, 0)
                mock_run.assert_called_once()
                called_cmd = mock_run.call_args[0][0]
                self.assertIn("-m", called_cmd)
                self.assertIn("unittest", called_cmd)

    def test_cmd_tests_auto_discovers_tests_subdir_or_dot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            tests_dir = root / "tests"
            tests_dir.mkdir()
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                self.assertEqual(diagnose.cmd_tests(argparse.Namespace(path=str(root), args=[])), 0)
                cmd_root = mock_run.call_args[0][0]
                self.assertEqual(cmd_root[-4:], ["-s", "tests", "-p", "test_*.py"])

                self.assertEqual(diagnose.cmd_tests(argparse.Namespace(path=str(tests_dir), args=[])), 0)
                cmd_sub = mock_run.call_args[0][0]
                self.assertEqual(cmd_sub[-4:], ["-s", ".", "-p", "test_*.py"])

    def test_cmd_scan_and_scaffold_execution(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            code_file = root / "service.py"
            code_file.write_text("def process(items=[]):\n    pass\n", encoding="utf-8")

            # 1. Test cmd_scan
            args_scan = argparse.Namespace(path=str(root), deep=False, json=True, strict=False)
            code = diagnose.cmd_scan(args_scan)
            self.assertEqual(code, 0)
            cat_file = root / ".diagnostics" / "defect_catalog.json"
            self.assertTrue(cat_file.is_file())

            # 2. Test cmd_scaffold_defect
            args_scaf = argparse.Namespace(
                path=str(root), id="DEFECT-001", branch=False, elevate=False, fix=True, json=True
            )
            code_scaf = diagnose.cmd_scaffold_defect(args_scaf)
            self.assertEqual(code_scaf, 0)
            self.assertTrue((root / "tests" / "quarantine" / "test_defect_001.py").is_file())

    def test_cmd_scan_multiple_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pkg_a").mkdir()
            (root / "pkg_b").mkdir()
            (root / "pkg_a" / "a.py").write_text("def f(x=[]):\n    pass\n", encoding="utf-8")
            (root / "pkg_b" / "b.js").write_text("eval('1');\n", encoding="utf-8")
            old_cwd = os.getcwd()
            try:
                os.chdir(root)
                args_scan = argparse.Namespace(path=["pkg_a", "pkg_b"], deep=False, json=True, strict=False)
                code = diagnose.cmd_scan(args_scan)
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            cat_file = root / ".diagnostics" / "defect_catalog.json"
            self.assertTrue(cat_file.is_file())
            self.assertIn("DEFECT-002", cat_file.read_text(encoding="utf-8"))

    def test_scan_and_save_single_file_uses_parent_workspace(self):
        import shadow_prober
        with tempfile.TemporaryDirectory() as tmpdir:
            sub = Path(tmpdir) / "nested"
            sub.mkdir()
            f = sub / "a.py"
            f.write_text("def f(x=[]):\n    pass\n", encoding="utf-8")
            _, json_path, _ = shadow_prober.scan_and_save(f)
            self.assertEqual(json_path.parent.parent, sub.resolve())

class TestMainDispatcher(unittest.TestCase):
    """Test top-level main() entrypoint."""

    def test_main_no_args_prints_help(self):
        with patch.object(sys, "argv", ["diagnose.py"]):
            code = diagnose.main()
            self.assertEqual(code, 0)

    def test_main_with_surface_args(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(sys, "argv", ["diagnose.py", "surface", "--path", tmpdir]):
                code = diagnose.main()
                self.assertEqual(code, 0)

    def test_debug_retro_writes_to_diagnostics_or_frontier(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with patch.object(sys, "argv", ["diagnose.py", "debug-retro", "--path", str(root), "--symptom", "Black screen", "--cause", "Stub cam_01", "--learn", "Avoid stub"]):
                self.assertEqual(diagnose.main(), 0)
            self.assertTrue((root / ".diagnostics" / "DEBUG_RETRO.md").is_file())
            (root / ".frontier").mkdir()
            with patch.object(sys, "argv", ["diagnose.py", "debug-retro", "--path", str(root), "--symptom", "Overlay missing", "--cause", "Stale tab"]):
                self.assertEqual(diagnose.main(), 0)
            retro_text = (root / ".frontier" / "DEBUG_RETRO.md").read_text(encoding="utf-8")
            self.assertIn("Overlay missing", retro_text)


if __name__ == "__main__":
    unittest.main()
