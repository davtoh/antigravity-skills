"""Claude Code portability: skill works when installed outside the monorepo layout."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SKILLS_ROOT = SKILL_DIR.parent


class TestClaudeInstallLayout(unittest.TestCase):
    def test_shims_resolve_from_dot_claude_skills(self):
        """Copy both skills into <tmp>/.claude/skills/ and run a shim from a different cwd."""
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td).resolve() / ".claude" / "skills"
            for name in ("frontier-architect", "system-diagnostics"):
                shutil.copytree(SKILLS_ROOT / name, dest / name,
                                ignore=shutil.ignore_patterns("__pycache__", "tests", "evals"))
            out = subprocess.run(
                [sys.executable, "-I", str(dest / "frontier-architect" / "scripts" / "docker_audit.py"), "--help"],
                cwd=td, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(out.returncode, 0, out.stderr)

    def test_plan_engine_status_runs_from_any_cwd(self):
        with tempfile.TemporaryDirectory() as td:
            out = subprocess.run(
                [sys.executable, "-I", str(SKILL_DIR / "scripts" / "plan_engine.py"), "discover", "--root", td],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(out.returncode, 0, out.stderr)

    def test_skill_md_has_no_repo_relative_script_paths(self):
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("python skills/", text)
        self.assertNotIn("~/.gemini/config", text)


class TestTriggerEvalShape(unittest.TestCase):
    def test_trigger_eval_balanced_and_realistic(self):
        data = json.loads((SKILL_DIR / "evals" / "trigger_eval.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data), 20)
        pos = sum(1 for d in data if d["should_trigger"])
        self.assertTrue(8 <= pos <= len(data) - 8)
        self.assertTrue(all(len(d["query"]) > 30 for d in data))


if __name__ == "__main__":
    unittest.main()
