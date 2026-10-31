#!/usr/bin/env python3
"""Automated unit test suite for Unified System Diagnostics CLI (diagnose.py).

Zero external dependencies; standard library Python 3.10+ only.
Tests all subcommands: ui, container, surface, tests, all.
"""

from __future__ import annotations

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
        args = self.parser.parse_args(["ui", "--url", "http://localhost:8000", "--audit-layout", "--live"])
        self.assertEqual(args.subcommand, "ui")
        self.assertEqual(args.url, "http://localhost:8000")
        self.assertTrue(args.audit_layout)
        self.assertTrue(args.live)

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
        args = self.parser.parse_args(["all", "--url", "http://localhost:3000", "--strict"])
        self.assertEqual(args.subcommand, "all")
        self.assertEqual(args.url, "http://localhost:3000")
        self.assertTrue(args.strict)


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
                navigate=True, window_size="1920x1080", headless=True, live=False
            )
            code = diagnose.cmd_ui(args)
            self.assertEqual(code, 0)
            mock_run.assert_called_once()
            called_cmd = mock_run.call_args[0][0]
            self.assertIn("cdp_inspect.py", called_cmd[1])
            self.assertIn("--audit-layout", called_cmd)
            self.assertIn("--navigate", called_cmd)

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


if __name__ == "__main__":
    unittest.main()
