"""Unit tests for Frontier Architect plan_engine fixes (concurrency, tactical master gate, commit hint)."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import unittest

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from plan_cli_helpers import assess_plan_scope, print_master_gate, print_retrospective_summary, resolve_commit_hint
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
            {"text": "`dashboard/stream_manager.py`: Event wakeup."},
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

    def test_tactical_master_gate_counts_all_paths_per_line(self):
        import io
        from contextlib import redirect_stdout

        ps = {"slug": "demo_master_roadmap", "title": "Demo Master", "child_plans": {}}
        tasks = [
            {"text": "`pkg/a.py`, `pkg/b.py`, `pkg/c.py`"},
            {"text": "`pkg/d.py`, `pkg/e.py`, `pkg/f.py`"},
        ]
        buf = io.StringIO()
        with redirect_stdout(buf):
            print_master_gate(ps, 2, declared_child=None, tasks=tasks)
        out = buf.getvalue()
        self.assertNotIn("Tactical Master Step", out)
        self.assertIn("MANDATORY: DO NOT implement this entire master step in one turn.", out)

    def test_assess_plan_scope_warns_on_overloaded_single_milestone_child(self):
        ps = {"slug": "step_2_demo", "title": "Step 2", "child_plans": {}, "parent_plan": {"slug": "demo_master", "milestone": 2}}
        one_m = {"milestones": [{"index": 1, "tasks": [{"text": f"**pkg/f{i}.py**: edit"} for i in range(7)]}]}
        warn = assess_plan_scope(one_m, ps, parent_arg="demo_master")
        self.assertIsNotNone(warn)
        self.assertIn("GRANULARITY WARNING (SINGLE-MILESTONE CHILD)", warn)

        two_m = {"milestones": [{"index": 1, "tasks": [{"text": "**pkg/f1.py**: a"}]}, {"index": 2, "tasks": [{"text": "**pkg/f2.py**: b"}]}]}
        self.assertIsNone(assess_plan_scope(two_m, ps, parent_arg="demo_master"))

    def test_advance_warns_on_unresolved_observations_in_milestone_and_plan(self):
        import io
        import json
        from contextlib import redirect_stdout
        import plan_engine

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_p = root / ".TODO" / "obs_gate_plan.md"
            plan_p.parent.mkdir(parents=True, exist_ok=True)
            plan_p.write_text(
                "# Obs Gate\n\n## Milestone 1: Fix OBS-001\n- [ ] **a.py**: fix OBS-001 and verify OBS-003\n\n"
                "## Milestone 2: Fix OBS-002\n- [ ] **b.py**: fix OBS-002\n",
                encoding="utf-8",
            )
            cat_p = root / ".diagnostics" / "observation_catalog.json"
            cat_p.parent.mkdir(parents=True, exist_ok=True)
            cat_p.write_text(
                json.dumps({
                    "observations": [
                        {"id": "OBS-001", "status": "open"},
                        {"id": "OBS-002", "status": "triaged"},
                        {"id": "OBS-003", "status": "resolved"},
                    ]
                }),
                encoding="utf-8",
            )
            parser = plan_engine.build_parser()
            self.assertEqual(plan_engine.cmd_init(root, parser.parse_args(["init", str(plan_p)])), 0)
            buf1 = io.StringIO()
            with redirect_stdout(buf1):
                rc1 = plan_engine.cmd_advance(root, parser.parse_args(["advance", "obs_gate_plan", "--milestone", "1"]))
            self.assertEqual(rc1, 0)
            out1 = buf1.getvalue()
            self.assertIn("OBSERVATION WARNING", out1)
            self.assertIn("OBS-001", out1)
            self.assertIn("diagnose.py observations resolve --id OBS-001", out1)
            self.assertNotIn("OBS-002", out1)
            self.assertNotIn("OBS-003", out1)

            # Resolve OBS-001, then advance Milestone 2 -> only OBS-002 warned
            cat_p.write_text(
                json.dumps({
                    "observations": [
                        {"id": "OBS-001", "status": "resolved"},
                        {"id": "OBS-002", "status": "in_progress"},
                        {"id": "OBS-003", "status": "confirmed"},
                    ]
                }),
                encoding="utf-8",
            )
            buf2 = io.StringIO()
            with redirect_stdout(buf2):
                rc2 = plan_engine.cmd_advance(root, parser.parse_args(["advance", "obs_gate_plan", "--milestone", "2"]))
            self.assertEqual(rc2, 0)
            out2 = buf2.getvalue()
            self.assertIn("OBSERVATION WARNING", out2)
            self.assertIn("OBS-002", out2)
            self.assertNotIn("OBS-001", out2)

    def test_advance_no_observation_warning_when_closed_or_no_catalog(self):
        import io
        from contextlib import redirect_stdout
        import plan_engine

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_p = root / ".TODO" / "clean_obs_plan.md"
            plan_p.parent.mkdir(parents=True, exist_ok=True)
            plan_p.write_text("# Clean\n\n## Milestone 1: Fix OBS-009\n- [ ] **a.py**: task\n", encoding="utf-8")
            parser = plan_engine.build_parser()
            self.assertEqual(plan_engine.cmd_init(root, parser.parse_args(["init", str(plan_p)])), 0)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = plan_engine.cmd_advance(root, parser.parse_args(["advance", "clean_obs_plan", "--milestone", "1"]))
            self.assertEqual(rc, 0)
            self.assertNotIn("OBSERVATION WARNING", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
