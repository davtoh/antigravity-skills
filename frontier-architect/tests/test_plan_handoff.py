"""Tests for plan_handoff: completion hand-off lines for a finished child plan."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import plan_handoff as ph  # noqa: E402


class TestParentHandoff(unittest.TestCase):
    def _root(self, state: dict) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        path = root / ".frontier" / "plans" / "master" / "state.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(state), encoding="utf-8")
        return root

    def _lines(self, state: dict) -> list[str]:
        return ph.parent_handoff(self._root(state), {"slug": "master", "milestone": 1})

    def test_master_step_not_advanced_keeps_advance_instruction(self) -> None:
        out = self._lines({"milestones": [{"index": 1, "status": "in_progress"}], "active_milestone_index": 1, "total_milestones": 3})
        self.assertEqual(len(out), 1)
        self.assertIn("advance master --milestone 1", out[0])

    def test_master_step_already_advanced_points_to_continue_and_drops_advance(self) -> None:
        out = "\n".join(self._lines({"milestones": [{"index": 1, "status": "completed"}], "active_milestone_index": 2, "total_milestones": 3}))
        self.assertIn("already advanced", out)
        self.assertIn("/frontier-architect continue master", out)
        self.assertNotIn("Run 'plan_engine.py advance", out)

    def test_last_master_step_says_final_signoff(self) -> None:
        out = "\n".join(self._lines({"milestones": [{"index": 1, "status": "completed"}], "active_milestone_index": 4, "total_milestones": 3, "status": "completed"}))
        self.assertIn("final sign-off", out)
        self.assertNotIn("continue master", out)

    def test_missing_parent_state_falls_back_to_advance_instruction(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = ph.parent_handoff(Path(tmp.name).resolve(), {"slug": "gone", "milestone": 2})
        self.assertIn("advance gone --milestone 2", out[0])


if __name__ == "__main__":
    unittest.main()
