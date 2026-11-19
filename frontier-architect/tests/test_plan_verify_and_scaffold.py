"""Tests for plan_scaffold workflow/plan-mode promotion and plan_verify timeout handling."""

import argparse
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import plan_engine  # noqa: E402
import plan_scaffold as ps  # noqa: E402
import plan_verify as pv  # noqa: E402


class TestPlanVerifyAndScaffold(unittest.TestCase):
    def test_promote_transcript_findings_captures_redirects_and_plan_mode(self) -> None:
        skill_learns: list[str] = []
        escalations: list[str] = []
        rows = [{
            "cid": "07c31c62-9392-4593-815b-9c80d0fdaedf",
            "plan_mode_calls": 2,
            "workflow_redirects": ["step 94: why did you not pause for model switch"],
        }]
        ps.promote_transcript_findings(rows, skill_learns, escalations)
        self.assertIn("Transcript audit: 07c31c62 called enter/exit_plan_mode (2x)", skill_learns)
        self.assertIn("Workflow redirect (07c31c62): step 94: why did you not pause for model switch", escalations)

    def test_format_digest_includes_ready_learn_prompt_when_candidates_exist(self) -> None:
        digest = {
            "title": "Demo", "slug": "demo", "status": "completed",
            "milestones": [{"index": 1, "title": "M1", "status": "completed", "sha": "abc"}],
            "retro_entries": 1, "integrity_issues": [], "went_well": ["ok"],
            "learn_candidates": ["Rule 1"], "skill_learn_candidates": [], "tool_gaps": [],
            "escalations": [], "transcripts_unavailable": False, "transcripts": [],
            "cids": [], "next_step": "Invoke /learn",
        }
        rendered = ps.format_digest(digest)
        self.assertIn("/learn Review .frontier/plans/demo/LEARNING_SCAFFOLD.md", rendered)

    def test_cmd_verify_returns_124_on_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".TODO").mkdir()
            (root / ".TODO" / "demo.md").write_bytes("# Demo\n\n## Milestone 1: M1\n- [ ] **a.py**: add\n".encode("utf-8"))
            plan_engine.main(["init", ".TODO/demo.md"], root=root)
            cmd = f'"{sys.executable}" -c "import time; print(\'1 passed\'); time.sleep(5)"'
            args = argparse.Namespace(plan="demo", command=cmd, timeout=0.3)
            rc = pv.cmd_verify(root, args)
            self.assertEqual(rc, 124)
            ws = pv.load_json(pv.get_frontier_dir(root) / "state.json", {})
            self.assertEqual(ws["verification_baseline"]["last_exit_code"], 124)
            self.assertEqual(ws["verification_baseline"]["passed_tests"], 1)

    def test_cmd_verify_timeout_zero_disables_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".TODO").mkdir()
            (root / ".TODO" / "demo.md").write_bytes("# Demo\n\n## Milestone 1: M1\n- [ ] **a.py**: add\n".encode("utf-8"))
            plan_engine.main(["init", ".TODO/demo.md"], root=root)
            args = argparse.Namespace(plan="demo", command="pytest", timeout=0)
            with patch("subprocess.Popen") as mock_popen:
                proc = mock_popen.return_value
                proc.stdout = None
                proc.wait.return_value = 0
                rc = pv.cmd_verify(root, args)
            self.assertEqual(rc, 0)
            proc.wait.assert_called_once_with(timeout=None)


if __name__ == "__main__":
    unittest.main()
