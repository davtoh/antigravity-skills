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

    def test_walk_source_files_skips_vendor_and_minified_assets(self) -> None:
        import surface_scanners
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "static" / "js" / "vendor").mkdir(parents=True)
            (root / "static" / "js" / "vendor" / "htmx.min.js").write_text("eval('x')", encoding="utf-8")
            (root / "static" / "js" / "app.min.js").write_text("eval('y')", encoding="utf-8")
            (root / "static" / "js" / "app.js").write_text("console.log(1);", encoding="utf-8")
            found = surface_scanners.walk_source_files(root)
            self.assertEqual([p.name for p in found["js"]], ["app.js"])

    def test_debug_retro_with_plan_records_followup_cid_and_backfills(self) -> None:
        fa_scripts = Path(__file__).resolve().parents[2] / "frontier-architect" / "scripts"
        if str(fa_scripts) not in sys.path:
            sys.path.insert(0, str(fa_scripts))
        import plan_engine
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".TODO").mkdir()
            (root / ".TODO" / "demo.md").write_bytes("# Demo\n\n## Milestone 1: M1\n- [ ] **a.py**: add\n".encode("utf-8"))
            plan_engine.main(["init", ".TODO/demo.md"], root=root)
            plan_engine.main(["advance", "demo", "--milestone", "1"], root=root)
            plan_engine.main(["retrospective", "demo", "--milestone", "1", "--grade", "A", "--cid", "aaaaaaaa"], root=root)
            brain = root / "brain"
            for cid in ("aaaaaaaa", "bbbbbbbb"):
                lp = brain / cid / ".system_generated" / "logs"
                lp.mkdir(parents=True)
                (lp / "transcript.jsonl").write_text('{"step_index":0,"type":"USER_INPUT","content":"hi"}\n', encoding="utf-8")
            argv = [
                "diagnose.py", "debug-retro", "--path", str(root), "--plan", "demo",
                "--cid", "bbbbbbbb", "--brain-dir", str(brain),
                "--symptom", "clock skew", "--cause", "time.time used", "--learn", "Use monotonic",
            ]
            with patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
                rc = diagnose.main()
            self.assertEqual(rc, 0)
            scaf = (root / ".frontier" / "plans" / "demo" / "LEARNING_SCAFFOLD.md").read_text(encoding="utf-8")
            self.assertIn("bbbbbbbb", scaf)
            self.assertIn("Use monotonic", scaf)

    def test_debug_retro_with_completed_plan_preserves_followup_cid(self) -> None:
        fa_scripts = Path(__file__).resolve().parents[2] / "frontier-architect" / "scripts"
        if str(fa_scripts) not in sys.path:
            sys.path.insert(0, str(fa_scripts))
        import plan_engine
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".TODO").mkdir()
            (root / ".TODO" / "demo.md").write_bytes("# Demo\n\n## Milestone 1: M1\n- [ ] **a.py**: add\n".encode("utf-8"))
            plan_engine.main(["init", ".TODO/demo.md"], root=root)
            plan_engine.main(["advance", "demo", "--milestone", "1"], root=root)
            plan_engine.main(["retrospective", "demo", "--milestone", "1", "--grade", "A", "--cid", "aaaaaaaa"], root=root)
            brain = root / "brain"
            for cid in ("aaaaaaaa", "cccccccc"):
                lp = brain / cid / ".system_generated" / "logs"
                lp.mkdir(parents=True)
                (lp / "transcript.jsonl").write_text('{"step_index":0,"type":"USER_INPUT","content":"hi"}\n', encoding="utf-8")
            argv = [
                "diagnose.py", "debug-retro", "--path", str(root), "--plan", "demo",
                "--cid", "cccccccc", "--brain-dir", str(brain),
                "--symptom", "late regression", "--cause", "missing guard",
            ]
            with patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
                rc = diagnose.main()
            self.assertEqual(rc, 0)
            scaf = (root / ".frontier" / "plans" / "demo" / "LEARNING_SCAFFOLD.md").read_text(encoding="utf-8")
            self.assertIn("cccccccc", scaf)


if __name__ == "__main__":
    unittest.main()
