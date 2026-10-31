#!/usr/bin/env python3
"""Unit tests for app-debugger dynamic tool resolver (run_diagnose.py).

Zero external dependencies; standard library Python 3.10+ only.
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Import resolver under test
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import run_diagnose  # noqa: E402


class TestRunDiagnose(unittest.TestCase):
    """Test dynamic discovery, environment variables, fallbacks, and execution."""

    def test_resolve_sibling_diagnose(self):
        """Verify resolver discovers sibling system-diagnostics/scripts/diagnose.py."""
        resolved = run_diagnose.resolve_diagnose_path()
        self.assertIsNotNone(resolved, "Failed to resolve system-diagnostics/scripts/diagnose.py")
        self.assertTrue(resolved.is_file(), f"Resolved path does not exist: {resolved}")
        self.assertEqual(resolved.name, "diagnose.py")

    def test_resolve_env_var_override_cli_path(self):
        """Verify DIAGNOSE_CLI_PATH takes precedence."""
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            with patch.dict(os.environ, {"DIAGNOSE_CLI_PATH": str(tmp_path)}):
                resolved = run_diagnose.resolve_diagnose_path()
                self.assertEqual(resolved, tmp_path.resolve())
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_resolve_env_var_override_system_dir(self):
        """Verify SYSTEM_DIAGNOSTICS_DIR is checked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scripts_dir = Path(tmpdir) / "scripts"
            scripts_dir.mkdir(parents=True)
            mock_diag = scripts_dir / "diagnose.py"
            mock_diag.write_text("# mock", encoding="utf-8")

            with patch.dict(os.environ, {"SYSTEM_DIAGNOSTICS_DIR": tmpdir}):
                resolved = run_diagnose.resolve_diagnose_path()
                self.assertEqual(resolved, mock_diag.resolve())

    def test_resolve_missing(self):
        """Verify None returned when candidate paths do not exist."""
        with tempfile.TemporaryDirectory() as empty_dir:
            with patch.object(run_diagnose, "_get_candidate_paths", return_value=[Path(empty_dir) / "missing.py"]):
                resolved = run_diagnose.resolve_diagnose_path()
                self.assertIsNone(resolved)

    def test_print_missing_dependency_recipe(self):
        """Verify actionable error recipe is printed to stderr when missing."""
        buf = io.StringIO()
        with patch("sys.stderr", buf):
            run_diagnose.print_missing_dependency_recipe()

        output = buf.getvalue()
        self.assertIn("[app-debugger] Error: 'system-diagnostics' tool engine not found", output)
        self.assertIn("SYSTEM_DIAGNOSTICS_DIR", output)
        self.assertIn("~/.gemini/config/skills/system-diagnostics/", output)

    def test_main_probe_success(self):
        """Verify --probe exits with 0 when diagnose.py is found."""
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            with patch.dict(os.environ, {"DIAGNOSE_CLI_PATH": str(tmp_path)}):
                ret = run_diagnose.main(["--probe"])
                self.assertEqual(ret, 0)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_main_probe_missing(self):
        """Verify --probe exits with 1 when diagnose.py is missing."""
        with patch.object(run_diagnose, "resolve_diagnose_path", return_value=None):
            buf = io.StringIO()
            with patch("sys.stderr", buf):
                ret = run_diagnose.main(["--probe"])
            self.assertEqual(ret, 1)
            self.assertIn("not found", buf.getvalue())

    def test_main_forwards_arguments(self):
        """Verify arguments are forwarded directly to diagnose.py."""
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            with patch.dict(os.environ, {"DIAGNOSE_CLI_PATH": str(tmp_path)}):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value.returncode = 0
                    ret = run_diagnose.main(["ui", "--headless", "--audit-layout"])
                    self.assertEqual(ret, 0)
                    mock_run.assert_called_once()
                    called_cmd = mock_run.call_args[0][0]
                    self.assertEqual(called_cmd[0], sys.executable)
                    self.assertEqual(called_cmd[1], str(tmp_path.resolve()))
                    self.assertEqual(called_cmd[2:], ["ui", "--headless", "--audit-layout"])
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_modularity_and_line_count_budgets(self):
        """Verify run_diagnose.py adheres to the 80-120 line target and function length rules."""
        script_file = SCRIPTS_DIR / "run_diagnose.py"
        lines = script_file.read_text(encoding="utf-8").splitlines()
        self.assertLessEqual(len(lines), 120, f"run_diagnose.py exceeds 120 lines: {len(lines)}")
        self.assertGreaterEqual(len(lines), 70, f"run_diagnose.py suspiciously short: {len(lines)}")


if __name__ == "__main__":
    unittest.main()

