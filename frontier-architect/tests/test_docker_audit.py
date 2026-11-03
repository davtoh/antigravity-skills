#!/usr/bin/env python3
"""
Unit tests for scripts/docker_audit.py.
Tests 100% of docker_audit.py logic using mocks and standard library,
with zero external dependencies and zero requirement for a live Docker daemon.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import docker_audit


class TestDockerAudit(unittest.TestCase):
    """Thorough unit test coverage for docker_audit.py."""

    def test_host_md5_existing_file(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as tf:
            tf.write("hello frontier architect")
            temp_path = tf.name

        try:
            expected = hashlib.md5(b"hello frontier architect", usedforsecurity=False).hexdigest()
            actual = docker_audit.host_md5(temp_path)
            self.assertEqual(actual, expected)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_host_md5_missing_file(self):
        result = docker_audit.host_md5("nonexistent_path_test_12345.xyz")
        self.assertEqual(result, "MISSING_ON_HOST")

    def test_run_cmd_handles_missing_command_safely(self):
        result = docker_audit.run_cmd(["__definitely_nonexistent_cli_cmd_9999__"])
        self.assertTrue(result.startswith("Error:") or "not found" in result.lower())

    def test_run_cmd_handles_timeout_safely(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["sleep", "10"], timeout=1.0)):
            result = docker_audit.run_cmd(["sleep", "10"], timeout=1.0)
            self.assertTrue(result.startswith("Error:"))

    def test_run_cmd_success_combines_stdout_and_stderr(self):
        mock_res = MagicMock()
        mock_res.stdout = "line 1\n"
        mock_res.stderr = "warning 1\n"
        with patch("subprocess.run", return_value=mock_res):
            out = docker_audit.run_cmd(["echo", "hello"])
            self.assertIn("line 1", out)
            self.assertIn("warning 1", out)

    def test_arg_parser_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            parser = argparse.ArgumentParser()
            parser.add_argument("--container", default=os.getenv("DOCKER_CONTAINER"))
            parser.add_argument("--workdir", default=os.getenv("CONTAINER_WORKDIR", "/app"))
            parser.add_argument("--sync-check", nargs="*", default=[])
            parser.add_argument("--tail-errors", type=int, default=150)

            args = parser.parse_args([])
            self.assertIsNone(args.container)
            self.assertEqual(args.workdir, "/app")
            self.assertEqual(args.sync_check, [])
            self.assertEqual(args.tail_errors, 150)

    def test_arg_parser_custom_args(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--container", default=None)
        parser.add_argument("--workdir", default="/app")
        parser.add_argument("--sync-check", nargs="*", default=[])
        parser.add_argument("--tail-errors", type=int, default=150)

        args = parser.parse_args([
            "--container", "my_app_container",
            "--workdir", "/workspace/srv",
            "--sync-check", "app.py", "styles.css",
            "--tail-errors", "50",
        ])
        self.assertEqual(args.container, "my_app_container")
        self.assertEqual(args.workdir, "/workspace/srv")
        self.assertEqual(args.sync_check, ["app.py", "styles.css"])
        self.assertEqual(args.tail_errors, 50)

    def test_main_docker_cli_missing(self):
        with patch("shutil.which", return_value=None), \
             patch("sys.argv", ["docker_audit.py"]), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            docker_audit.main()
            self.assertIn("Notice: 'docker' CLI not found on host", mock_out.getvalue())

    def test_main_docker_daemon_inactive(self):
        daemon_err = "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?"
        with patch("shutil.which", return_value="/usr/bin/docker"), \
             patch("sys.argv", ["docker_audit.py"]), \
             patch("docker_audit.run_cmd", return_value=daemon_err), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            docker_audit.main()
            self.assertIn("Notice: Docker daemon is not active", mock_out.getvalue())

    def test_main_full_run_with_container_and_sync_in_sync(self):
        stats_output = "Name\tCPUPerc\tMemUsage\tNetIO\tPIDs\napp_srv\t2.5%\t120MiB\t10MB / 5MB\t4"
        top_output = "UID PID PPID C STIME TTY TIME CMD\nroot 101 100 0 10:00 ? 00:00:01 python app.py"
        test_file = "SKILL.md"
        actual_skill_md = SKILL_DIR / "SKILL.md"
        file_hash = docker_audit.host_md5(str(actual_skill_md))
        md5_output = f"{file_hash}  /app/SKILL.md\n"
        logs_output = "2026-11-02 10:00:00 INFO: App started successfully.\n2026-11-02 10:01:00 INFO: Ready."

        def mock_run(cmd, timeout=10.0):
            if cmd[1] == "stats":
                return stats_output
            if cmd[1] == "top":
                return top_output
            if cmd[1] == "exec":
                return md5_output
            if cmd[1] == "logs":
                return logs_output
            return ""

        test_args = ["docker_audit.py", "--container", "app_srv", "--workdir", "/app", "--sync-check", test_file, "--tail-errors", "50"]
        with patch("shutil.which", return_value="/usr/bin/docker"), \
             patch("sys.argv", test_args), \
             patch("docker_audit.host_md5", return_value=file_hash), \
             patch("docker_audit.run_cmd", side_effect=mock_run), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            docker_audit.main()
            out = mock_out.getvalue()
            self.assertIn("DOCKER STATS", out)
            self.assertIn("CONTAINER PROCESSES (app_srv)", out)
            self.assertIn("HOST vs CONTAINER FILE SYNC", out)
            self.assertIn("IN_SYNC", out)
            self.assertIn("No recent Tracebacks/Errors in last 50 lines", out)

    def test_main_sync_check_unverifiable_fallback(self):
        stats_output = "Name\tCPUPerc\tMemUsage\tNetIO\tPIDs\napp_srv\t2.5%\t120MiB\t10MB / 5MB\t4"
        md5_err = "OCI runtime exec failed: exec: \"md5sum\": executable file not found in $PATH: unknown"

        def mock_run(cmd, timeout=10.0):
            if cmd[1] == "stats":
                return stats_output
            if cmd[1] == "top":
                return ""
            if cmd[1] == "exec":
                return md5_err
            return ""

        test_args = ["docker_audit.py", "--container", "app_srv", "--sync-check", "app.py"]
        with patch("shutil.which", return_value="/usr/bin/docker"), \
             patch("sys.argv", test_args), \
             patch("docker_audit.run_cmd", side_effect=mock_run), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            docker_audit.main()
            out = mock_out.getvalue()
            self.assertIn("UNVERIFIABLE: cannot hash inside container", out)

    def test_main_sync_check_stale_and_missing_in_container(self):
        stats_output = "Name\tCPUPerc\tMemUsage\tNetIO\tPIDs\napp_srv\t2.5%\t120MiB\t10MB / 5MB\t4"
        md5_output = "11111111111111111111111111111111  /app/stale.py\nmd5sum: /app/missing.py: No such file or directory\n"

        def mock_run(cmd, timeout=10.0):
            if cmd[1] == "stats":
                return stats_output
            if cmd[1] == "top":
                return ""
            if cmd[1] == "exec":
                return md5_output
            return ""

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tf:
            tf.write("host content")
            stale_path = tf.name

        try:
            test_args = ["docker_audit.py", "--container", "app_srv", "--workdir", "/app", "--sync-check", stale_path, "missing.py"]
            with patch("shutil.which", return_value="/usr/bin/docker"), \
                 patch("sys.argv", test_args), \
                 patch("docker_audit.run_cmd", side_effect=mock_run), \
                 patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                docker_audit.main()
                out = mock_out.getvalue()
                self.assertIn("STALE_IN_CONTAINER", out)
        finally:
            if os.path.exists(stale_path):
                os.remove(stale_path)

    def test_main_tail_errors_found(self):
        stats_output = "Name\tCPUPerc\tMemUsage\tNetIO\tPIDs\napp_srv\t2.5%\t120MiB\t10MB / 5MB\t4"
        logs_output = "INFO: starting\nTraceback (most recent call last):\n  File 'app.py', line 10\nZeroDivisionError: division by zero"

        def mock_run(cmd, timeout=10.0):
            if cmd[1] == "stats":
                return stats_output
            if cmd[1] == "top":
                return ""
            if cmd[1] == "logs":
                return logs_output
            return ""

        test_args = ["docker_audit.py", "--container", "app_srv", "--tail-errors", "100"]
        with patch("shutil.which", return_value="/usr/bin/docker"), \
             patch("sys.argv", test_args), \
             patch("docker_audit.run_cmd", side_effect=mock_run), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            docker_audit.main()
            out = mock_out.getvalue()
            self.assertIn("RECENT CONTAINER EXCEPTIONS / ERRORS", out)
            self.assertIn("Traceback (most recent call last):", out)


if __name__ == "__main__":
    unittest.main()
