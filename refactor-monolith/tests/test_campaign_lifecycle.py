"""Automated tests for refactor-monolith campaign lifecycle and directory management.

Verifies .refactor/state.json initialization, phase advancement, checkpointing,
and directory structure provisioning.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure skill root is in sys.path
_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from scripts.campaign_manager import (
    cmd_state,
    get_refactor_dir,
    _format_phase_icon,
    record_campaign_defect,
)

class TestCampaignLifecycle(unittest.TestCase):
    def test_state_management_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / ".git").mkdir()
            target = base / "dashboard"
            target.mkdir()

            # 1. Init state
            code = cmd_state(target, action="init", plan=".refactor/plan.md", phases=3, phase_title="Domain Decoupling")
            self.assertEqual(code, 0)
            state_file = base / ".refactor" / "state.json"
            self.assertTrue(state_file.exists())
            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual(state["active_phase"], 1)
            self.assertEqual(state["total_phases"], 3)
            self.assertEqual(state["phases"]["1"]["title"], "Domain Decoupling")

            # 2. Advance phase
            code = cmd_state(target, action="advance", sha="abcdef1")
            self.assertEqual(code, 0)
            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual(state["active_phase"], 2)
            self.assertEqual(state["phases"]["1"]["status"], "completed")
            self.assertEqual(state["phases"]["1"]["sha"], "abcdef1")

    def test_refactor_dir_creates_subdirectories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            rdir = get_refactor_dir(base)
            self.assertTrue((rdir / "scripts").is_dir())
            self.assertTrue((rdir / "artifacts").is_dir())
            gitignore = rdir / ".gitignore"
            self.assertTrue(gitignore.is_file())
            content = gitignore.read_text(encoding="utf-8")
            self.assertIn("*", content)
            self.assertNotIn("!.gitignore", content)

    def test_format_phase_icon_fallback(self):
        self.assertIn(_format_phase_icon(is_completed=True, is_active=False), ["✅", "[x]"])
        self.assertIn(_format_phase_icon(is_completed=False, is_active=True), ["▶️", "[>]"])
        self.assertIn(_format_phase_icon(is_completed=False, is_active=False), ["⏳", "[ ]"])

    def test_campaign_state_checkpoint_action(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            rdir = base / ".refactor"
            rdir.mkdir()
            state_file = rdir / "state.json"
            # Init state
            cmd_state(base, action="init", plan=str(rdir / "plan.md"), phases=3, phase_title="Phase 1")

            # Save checkpoint
            code = cmd_state(base, action="checkpoint", note="Slice 1.2 completed")
            self.assertEqual(code, 0)
            data = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertIn("last_checkpoint", data)
            self.assertEqual(data["last_checkpoint"]["note"], "Slice 1.2 completed")

    def test_cmd_state_missing_state_graceful_query(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            # Inspection without existing state.json exits cleanly with code 0
            code_show = cmd_state(base, action="show")
            self.assertEqual(code_show, 0)
            code_status = cmd_state(base, action="status")
            self.assertEqual(code_status, 0)
            # Mutation actions without state.json return code 1
            code_adv = cmd_state(base, action="advance")
            self.assertEqual(code_adv, 1)
            code_cp = cmd_state(base, action="checkpoint", note="test")
            self.assertEqual(code_cp, 1)

    def test_record_campaign_defect_zero_plan_drift(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / ".git").mkdir()
            rdir = base / ".refactor"
            rdir.mkdir()
            plan_file = rdir / "plan.md"
            plan_file.write_text("# SOTA Plan\nOriginal plan content.\n", encoding="utf-8")

            # 1. Record defect directly
            json_path, entry = record_campaign_defect(
                base,
                defect_data={
                    "rule_id": "MUTABLE_DEFAULT_ARG",
                    "file": "src/worker.py",
                    "line": 42,
                    "symbol": "Worker.process",
                    "message": "Mutable default list detected.",
                    "suggested_fix": "Use items=None.",
                    "track": "tactical",
                }
            )
            self.assertTrue(json_path.is_file())
            cat_data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(cat_data["summary"]["total"], 1)
            self.assertEqual(cat_data["defects"][0]["id"], "DEFECT-001")
            self.assertEqual(cat_data["defects"][0]["track"], "tactical")

            # 2. Assert zero modification to plan.md (Refactoring Invariant)
            self.assertEqual(plan_file.read_text(encoding="utf-8"), "# SOTA Plan\nOriginal plan content.\n")

            # 3. Record defect via cmd_state --record-defect CLI hook
            cmd_state(base, action="init", plan=str(plan_file), phases=1, phase_title="Phase 1")
            code = cmd_state(base, action="", record_defect="UNHANDLED_ASYNC_COROUTINE:src/events.py:10:Async coroutine not awaited")
            self.assertEqual(code, 0)
            cat_data_after = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(cat_data_after["summary"]["total"], 2)

            # 4. Advance campaign to completion and verify handoff summary
            import unittest.mock
            with unittest.mock.patch("builtins.print") as mock_print:
                cmd_state(base, action="advance")
                printed = [call_args[0][0] for call_args in mock_print.call_args_list if call_args[0]]
                self.assertTrue(any("Latent Defect Handoff" in str(p) for p in printed))

if __name__ == "__main__":
    unittest.main()
