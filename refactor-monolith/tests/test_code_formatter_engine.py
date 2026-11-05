#!/usr/bin/env python3
"""Unit tests for code_formatter_engine and opportunistic slice formatting."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure skill root is in sys.path
_SKILL_ROOT = Path(__file__).resolve().parent.parent
import sys
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from scripts.code_formatter_engine import (
    format_slice_files,
    group_files_by_language,
    resolve_formatter_command,
)

class TestCodeFormatterEngine(unittest.TestCase):
    """Test opportunistic slice formatting logic and error handling."""

    def test_group_files_by_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            f_py = base / "app.py"
            f_js = base / "main.js"
            f_css = base / "style.css"
            f_go = base / "server.go"
            f_txt = base / "readme.txt"
            for f in (f_py, f_js, f_css, f_go, f_txt):
                f.write_text("content", encoding="utf-8")

            groups = group_files_by_language([f_py, f_js, f_css, f_go, f_txt])
            self.assertEqual(groups["python"], [f_py])
            self.assertEqual(set(groups["javascript"]), {f_js, f_css})
            self.assertEqual(groups["go"], [f_go])
            self.assertNotIn("readme.txt", groups)

    def test_format_slice_files_gracefully_bypasses_when_no_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual(format_slice_files(Path(tmpdir), []), 0)
            self.assertEqual(format_slice_files(Path(tmpdir), [Path(tmpdir) / "non_existent.py"]), 0)

    @patch("scripts.code_formatter_engine.resolve_formatter_command", return_value=None)
    def test_format_slice_files_bypasses_silently_when_no_tool_installed(self, mock_resolve) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.py"
            f.write_text("x = 1\n", encoding="utf-8")
            # When formatter is absent, returns 0 (graceful bypass)
            ret = format_slice_files(Path(tmpdir), [f])
            self.assertEqual(ret, 0)

    @patch("scripts.code_formatter_engine.resolve_formatter_command", return_value=["ruff", "format"])
    @patch("subprocess.run")
    def test_format_slice_files_runs_tool_on_success(self, mock_run, mock_resolve) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.py"
            f.write_text("x = 1\n", encoding="utf-8")
            ret = format_slice_files(Path(tmpdir), [f])
            self.assertEqual(ret, 0)
            mock_run.assert_called_once()
            called_cmd = mock_run.call_args[0][0]
            self.assertIn("ruff", called_cmd[0])
            self.assertIn(str(f), called_cmd)

    @patch("scripts.code_formatter_engine.resolve_formatter_command", return_value=["ruff", "format"])
    @patch("subprocess.run")
    def test_format_slice_files_hard_fails_on_syntax_error(self, mock_run, mock_resolve) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stderr = "SyntaxError: invalid syntax at line 1"
        mock_run.return_value = mock_proc

        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "broken.py"
            f.write_text("broken py\n", encoding="utf-8")
            ret = format_slice_files(Path(tmpdir), [f])
            self.assertEqual(ret, 1)

if __name__ == "__main__":
    unittest.main()
