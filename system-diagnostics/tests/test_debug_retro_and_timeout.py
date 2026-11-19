"""Tests for standalone debug-retro learning scaffolds and bounded test timeouts."""

import argparse
import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import diagnose  # noqa: E402


class TestDebugRetroScaffoldAndTimeout(unittest.TestCase):
    def test_debug_retro_writes_standalone_scaffold_and_turn_end_echo(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            buf = io.StringIO()
            argv = [
                "diagnose.py", "debug-retro", "--path", str(root),
                "--symptom", "Worker hangs on missing file",
                "--cause", "Un-signaled _ready_event",
                "--learn", "Always set _ready_event in finally",
                "--skill-learn", "Enforce test timeout",
            ]
            with patch.object(sys, "argv", argv), contextlib.redirect_stdout(buf):
                rc = diagnose.main()
            self.assertEqual(rc, 0)
            scaf = root / ".diagnostics" / "LEARNING_SCAFFOLD.md"
            self.assertTrue(scaf.is_file())
            scaf_txt = scaf.read_text(encoding="utf-8")
            self.assertIn("Always set _ready_event in finally", scaf_txt)
            self.assertIn("Enforce test timeout", scaf_txt)
            out = buf.getvalue()
            self.assertIn("--- Turn-End Echo (Copy-Paste Into Final Response) ---", out)
            self.assertIn("### Continuous Learning & Introspective Options", out)

    def test_cmd_tests_returns_124_on_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            args = argparse.Namespace(path=tmpdir, args=[], timeout=5.0)
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="unittest", timeout=5.0)):
                rc = diagnose.cmd_tests(args)
            self.assertEqual(rc, 124)


if __name__ == "__main__":
    unittest.main()
