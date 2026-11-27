"""Unit tests for Frontier Architect plan_engine fixes (concurrency, tactical master gate, commit hint)."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import unittest

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from plan_cli_helpers import print_master_gate, print_retrospective_summary, resolve_commit_hint
from plan_scaffold import _triage_candidates
from plan_state import load_json, save_json


class TestPlanEngineFixes(unittest.TestCase):
    """Verify concurrent save_json, tactical master gate, and commit hint edge cases."""

    def test_concurrent_save_json_no_tmp_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "state.json"

            def _write(idx: int) -> None:
                save_json(target, {"worker": idx, "ok": True})

            with ThreadPoolExecutor(max_workers=6) as pool:
                list(pool.map(_write, range(24)))

            data = load_json(target)
            self.assertIsInstance(data, dict)
            self.assertTrue(data.get("ok"))
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])

    def test_tactical_master_gate_vs_full_gate(self):
        import io
        from contextlib import redirect_stdout

        ps = {"slug": "demo_master_roadmap", "title": "Demo Master", "child_plans": {}}
        buf_small = io.StringIO()
        with redirect_stdout(buf_small):
            print_master_gate(ps, 1, declared_child=None, tasks=[{"text": "one"}, {"text": "two"}])
        self.assertIn("MASTER STEP PRE-PLAN GATE (Step 1)", buf_small.getvalue())
        self.assertIn("Tactical Master Step", buf_small.getvalue())

        buf_large = io.StringIO()
        with redirect_stdout(buf_large):
            print_master_gate(ps, 2, declared_child=None, tasks=[{"text": str(i)} for i in range(4)])
        self.assertIn("MASTER STEP PRE-PLAN GATE (Step 2)", buf_large.getvalue())
        self.assertNotIn("Tactical Master Step", buf_large.getvalue())

    def test_resolve_commit_hint_precommitted_vs_audit_only(self):
        ps = {"slug": "step_4", "milestones": [{"index": 2, "title": "Verification"}]}
        hint_committed, has_diff = resolve_commit_hint(ps, 2, [], True, "b76f7a5")
        self.assertEqual(hint_committed, "(Already committed as b76f7a5)")
        self.assertTrue(has_diff)

        hint_audit, has_diff_audit = resolve_commit_hint(ps, 2, [], True, None)
        self.assertIn("verification/audit only", hint_audit)
        self.assertFalse(has_diff_audit)

    def test_tactical_master_gate_allows_concrete_4_file_slice(self):
        import io
        from contextlib import redirect_stdout

        ps = {"slug": "perf_master_roadmap", "title": "Perf Master", "child_plans": {}}
        tasks = [
            {"text": "**Files**:"},
            {"text": "`dashboard/services/async_inference_worker.py`: Add worker."},
            {"text": "`dashboard/services/stream_worker.py`: Wire async step."},
            {"text": "`dashboard/stream_manager.py` & `dashboard/routers/streaming.py`: Event wakeup."},
            {"text": "`tests/test_async_inference_worker.py`: Add unit tests."},
            {"text": "**Verification**:"},
            {"text": "`python -m unittest tests/test_async_inference_worker.py`"},
        ]
        buf = io.StringIO()
        with redirect_stdout(buf):
            print_master_gate(ps, 2, declared_child=None, tasks=tasks)
        self.assertIn("Tactical Master Step", buf.getvalue())

    def test_retrospective_summary_includes_commit_reminder(self):
        import io
        from contextlib import redirect_stdout

        entry = {
            "milestone_index": 1,
            "token_efficiency_grade": "A",
            "tool_reliability_scores": {"overall": 5},
            "went_well": ["Clean vertical slice"],
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            print_retrospective_summary(entry, "demo_plan", ".frontier/plans/demo_plan/LEARNING_SCAFFOLD.md")
        self.assertIn("Commit Reminder", buf.getvalue())
        self.assertIn("Suggested Commit", buf.getvalue())

    def test_triage_candidates_dedupes_and_filters_codified(self):
        with tempfile.TemporaryDirectory() as tmp:
            agents_md = Path(tmp) / "AGENTS.md"
            agents_md.write_text(
                "Use `ProcessingModeService` and `should_hibernate_camera` for focus_only.\n",
                encoding="utf-8",
            )
            items = [
                "Update `ProcessingModeService` `should_hibernate_camera()` for focus_only.",
                "Always scale `warmup_timeout` proportionally with `read_timeout`.",
                "Always scale warmup_timeout proportionally with read_timeout!",
            ]
            triaged = _triage_candidates(items, [agents_md])
            self.assertEqual(triaged, ["Always scale `warmup_timeout` proportionally with `read_timeout`."])

    def test_verify_cmd_and_retrospective_summary_cli_aliases(self):
        import plan_engine

        parser = plan_engine.build_parser()
        v_args = parser.parse_args(["verify", "demo_plan", "--verify-cmd", "python -m unittest"])
        self.assertEqual(v_args.command, "python -m unittest")
        r_args = parser.parse_args(["retrospective", "demo_plan", "--summary", "Clean milestone"])
        self.assertEqual(r_args.went_well, "Clean milestone")
        a_args = parser.parse_args(["advance", "demo_plan", "--milestone", "2", "--note", "Milestone 2 summary"])
        self.assertEqual(a_args.note, "Milestone 2 summary")

    def test_advance_single_milestone_reminds_when_retrospective_missing(self):
        import io
        from contextlib import redirect_stdout
        import plan_engine

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_p = root / ".TODO" / "single_m_plan.md"
            plan_p.parent.mkdir(parents=True, exist_ok=True)
            plan_p.write_text("# Single\n\n## Milestone 1: Do work\n- [ ] **a.py**: task\n", encoding="utf-8")
            parser = plan_engine.build_parser()
            self.assertEqual(plan_engine.cmd_init(root, parser.parse_args(["init", str(plan_p)])), 0)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = plan_engine.cmd_advance(root, parser.parse_args(["advance", "single_m_plan", "--milestone", "1"]))
            self.assertEqual(rc, 0)
            self.assertIn("Reminder: run `plan_engine.py retrospective single_m_plan --milestone 1", buf.getvalue())

    def test_retrospective_warns_when_tri_steps_or_retries_missing(self):
        import io
        from contextlib import redirect_stdout
        import plan_engine
        import plan_telemetry

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_p = root / ".TODO" / "retro_warn_plan.md"
            plan_p.parent.mkdir(parents=True, exist_ok=True)
            plan_p.write_text("# Warn\n\n## Milestone 1: Do work\n- [x] **a.py**: task\n", encoding="utf-8")
            parser = plan_engine.build_parser()
            self.assertEqual(plan_engine.cmd_init(root, parser.parse_args(["init", str(plan_p)])), 0)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = plan_telemetry.cmd_retrospective(
                    root,
                    parser.parse_args(["retrospective", "retro_warn_plan", "--milestone", "1", "--grade", "A"]),
                )
            self.assertEqual(rc, 0)
            out = buf.getvalue()
            self.assertIn("Warning: --tri omitted", out)
            self.assertIn("Warning: --steps/--retries unresolved", out)


if __name__ == "__main__":
    unittest.main()
