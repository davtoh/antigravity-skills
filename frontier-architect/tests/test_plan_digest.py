"""Tests for plan_digest (isolated temp workspaces only)."""

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import plan_digest as pd  # noqa: E402
import plan_engine  # noqa: E402

PLAN = "# Demo Plan\n\n## Milestone 1: Core\n- [ ] **a.py**: add\n\n## Milestone 2: UI\n- [ ] **b.py**: add\n"


class _PlanDigestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / ".TODO").mkdir()
        (self.root / ".TODO" / "demo.md").write_bytes(PLAN.encode("utf-8"))

    def _write_retros(self, entries: list[dict]) -> None:
        plan_engine.main(["init", ".TODO/demo.md"], root=self.root)
        path = self.root / ".frontier" / "plans" / "demo" / "retrospectives.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(json.dumps(entries).encode("utf-8"))


class TestPlanDigestCore(_PlanDigestBase):
    def test_grade_cap_thresholds(self) -> None:
        self.assertEqual(pd._grade_cap(None, None), "A")
        self.assertEqual(pd._grade_cap(61, 0), "B")
        self.assertEqual(pd._grade_cap(10, 2), "B")
        self.assertEqual(pd._grade_cap(101, 0), "C")
        self.assertEqual(pd._grade_cap(10, 4), "C")

    def test_integrity_flags_missing_steps_inflation_and_empty_tri(self) -> None:
        issues = pd.check_retro_integrity([
            {"milestone_index": 1, "token_efficiency_grade": "A", "steps": 120, "retries": 0, "tool_reliability_scores": {"x": 5}},
            {"milestone_index": 2, "token_efficiency_grade": "A", "tool_reliability_scores": {}},
        ])
        joined = "\n".join(issues)
        self.assertIn("M1: grade A exceeds rubric cap C", joined)
        self.assertIn("M2: --steps missing", joined)
        self.assertIn("M2: empty tool_reliability_scores", joined)

    def test_honest_entry_has_no_issues(self) -> None:
        ok = {"milestone_index": 1, "token_efficiency_grade": "B", "steps": 70, "retries": 1, "tool_reliability_scores": {"x": 5}}
        self.assertEqual(pd.check_retro_integrity([ok]), [])

    def test_unresolved_dedupes_and_ignores_none(self) -> None:
        learns, esc = pd._unresolved([
            {"learn_candidates": ["a", "a"], "root_causes_escalated": ["none", "None"]},
            {"learn_candidates": ["b"], "root_causes_escalated": ["real bug"]},
        ])
        self.assertEqual((learns, esc), (["a", "b"], ["real bug"]))

    def test_build_digest_end_to_end_and_unresolved_plan(self) -> None:
        self._write_retros([{"milestone_index": 1, "token_efficiency_grade": "A", "learn_candidates": ["x"], "root_causes_escalated": []}])
        digest = pd.build_digest(self.root, "demo")
        self.assertEqual(digest["slug"], "demo")
        self.assertEqual(digest["retro_entries"], 1)
        self.assertEqual(digest["learn_candidates"], ["x"])
        self.assertIn("## Retrospective integrity", pd.format_digest(digest))
        self.assertIsNone(pd.build_digest(self.root, "does-not-exist"))

    def test_cli_digest_json_and_missing_transcripts(self) -> None:
        self._write_retros([])
        ns = argparse.Namespace(plan="demo", cids=["zzz"], brain_dir=self._tmp.name, json=True)
        self.assertEqual(pd.cmd_digest(self.root, ns), 0)
        digest = pd.build_digest(self.root, "demo", ["zzz"], self._tmp.name)
        self.assertTrue(digest["transcripts"][0]["missing"] or digest["transcripts_unavailable"])
        self.assertEqual(pd.cmd_digest(self.root, argparse.Namespace(plan="nope", cids=None, brain_dir=None, json=False)), 1)

    def test_build_digest_includes_child_plan_retros(self) -> None:
        (self.root / ".TODO" / "child.md").write_bytes("# Child\n\n## Milestone 1: Sub\n- [ ] **c.py**: add\n".encode("utf-8"))
        plan_engine.main(["init", ".TODO/demo.md"], root=self.root)
        plan_engine.main(["init", ".TODO/child.md", "--parent", "demo"], root=self.root)
        child_retros = self.root / ".frontier" / "plans" / "child" / "retrospectives.json"
        child_retros.parent.mkdir(parents=True, exist_ok=True)
        child_retros.write_bytes(json.dumps([
            {"milestone_index": 1, "token_efficiency_grade": "A", "steps": 120, "retries": 0, "tool_reliability_scores": {"x": 5}, "learn_candidates": ["child rule"]},
        ]).encode("utf-8"))
        digest = pd.build_digest(self.root, "demo")
        self.assertEqual(digest["children"], ["child"])
        self.assertEqual(digest["retro_entries"], 1)
        self.assertEqual(digest["learn_candidates"], ["child rule"])
        self.assertIn("child:M1: grade A exceeds rubric cap C", "\n".join(digest["integrity_issues"]))


class TestPlanDigestBackfillAndScaffold(_PlanDigestBase):
    def test_digest_backfill_persists_steps_retries_and_caps_inflated_grade(self) -> None:
        brain = Path(self._tmp.name) / "brain"
        log_dir = brain / "conv-123" / ".system_generated" / "logs"
        log_dir.mkdir(parents=True)
        steps = [
            {"type": "USER_INPUT", "created_at": "2026-11-14T00:00:00Z", "content": "hi"},
            {"type": "PLANNER_RESPONSE", "created_at": "2026-11-14T00:01:00Z", "tool_calls": [
                {"name": "run_command", "args": {"CommandLine": "plan_engine.py retrospective demo --learn \"Unique backfill lesson\""}},
            ]},
        ] + [{"type": "GENERIC", "created_at": "2026-11-14T00:02:00Z", "content": "Command exited with code 1\n", "status": "DONE"} for _ in range(4)] + [
            {"type": "GENERIC", "created_at": "2026-11-14T00:03:00Z", "content": "ok"} for _ in range(100)
        ]
        (log_dir / "transcript.jsonl").write_bytes(("\n".join(json.dumps(s) for s in steps) + "\n").encode("utf-8"))
        self._write_retros([
            {"milestone_index": 1, "timestamp": "2026-11-14T00:02:30+00:00", "token_efficiency_grade": "A",
             "tool_reliability_scores": {}, "learn_candidates": ["Unique backfill lesson"], "root_causes_escalated": []},
        ])

        digest = pd.build_digest(self.root, "demo", brain_dir=str(brain), backfill=True)
        self.assertEqual(digest["backfilled_entries"], 1)
        self.assertEqual(digest["integrity_issues"], [])
        saved = json.loads((self.root / ".frontier" / "plans" / "demo" / "retrospectives.json").read_text(encoding="utf-8"))
        self.assertEqual(saved[0]["cid"], "conv-123")
        self.assertEqual(saved[0]["steps"], 106)
        self.assertEqual(saved[0]["retries"], 4)
        self.assertEqual(saved[0]["token_efficiency_grade"], "C")
        self.assertIn("overall", saved[0]["tool_reliability_scores"])

    def test_digest_dual_axis_and_write_scaffold(self) -> None:
        self._write_retros([
            {
                "milestone_index": 1, "token_efficiency_grade": "A", "steps": 25, "retries": 0,
                "tool_reliability_scores": {"overall": 5},
                "learn_candidates": ["Project rule"], "skill_learn_candidates": ["Skill rule"],
                "tool_gaps": ["CLI flag missing"], "root_causes_escalated": [],
            },
        ])
        ns = argparse.Namespace(plan="demo", cids=None, brain_dir=None, backfill=False, write_scaffold=True, json=False)
        self.assertEqual(pd.cmd_digest(self.root, ns), 0)
        scaffold = self.root / ".frontier" / "plans" / "demo" / "LEARNING_SCAFFOLD.md"
        self.assertTrue(scaffold.is_file())
        text = scaffold.read_text(encoding="utf-8")
        self.assertIn("## Skill & Tooling /learn candidates", text)
        self.assertIn("Skill rule", text)
        self.assertIn("CLI flag missing", text)
        self.assertIn("## Introspective Commands (User Choice)", text)

    def test_digest_write_scaffold_with_json_outputs_valid_json(self) -> None:
        import io
        from contextlib import redirect_stdout
        self._write_retros([
            {"milestone_index": 1, "token_efficiency_grade": "A", "steps": 10, "retries": 0, "tool_reliability_scores": {"overall": 5}},
        ])
        ns = argparse.Namespace(plan="demo", cids=None, brain_dir=None, backfill=False, write_scaffold=True, json=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = pd.cmd_digest(self.root, ns)
        self.assertEqual(rc, 0)
        parsed = json.loads(buf.getvalue())
        self.assertEqual(parsed["slug"], "demo")
        self.assertTrue((self.root / ".frontier" / "plans" / "demo" / "LEARNING_SCAFFOLD.md").is_file())

    def test_digest_includes_recorded_cids_in_introspective_command(self) -> None:
        self._write_retros([
            {"milestone_index": 1, "token_efficiency_grade": "A", "steps": 20, "retries": 0,
             "tool_reliability_scores": {"overall": 5}, "cid": "20aa8189-94b2-4ab5"},
        ])
        digest = pd.build_digest(self.root, "demo")
        self.assertEqual(digest["cids"], ["20aa8189-94b2-4ab5"])
        self.assertIn("transcript-audit --cids 20aa8189-94b2-4ab5", pd.format_digest(digest))

    def test_unresolved_filters_none_and_renders_went_well(self) -> None:
        self._write_retros([
            {
                "milestone_index": 1, "token_efficiency_grade": "A", "steps": 20, "retries": 0,
                "tool_reliability_scores": {"overall": 5},
                "learn_candidates": ["none", "Real project rule"],
                "skill_learn_candidates": ["none", "N/A", "Real skill rule"],
                "went_well": ["Fast isolated tests", "none"],
            },
        ])
        digest = pd.build_digest(self.root, "demo")
        self.assertEqual(digest["learn_candidates"], ["Real project rule"])
        self.assertEqual(digest["skill_learn_candidates"], ["Real skill rule"])
        self.assertEqual(digest["went_well"], ["Fast isolated tests"])
        md = pd.format_digest(digest)
        self.assertIn("## What Went Well", md)
        self.assertIn("- Fast isolated tests", md)

    def test_backfill_resolves_short_cid_and_dedupes_incomplete_duplicate_rows(self) -> None:
        brain = Path(self._tmp.name) / "brain"
        log_dir = brain / "dbc7d48f-f0ba-4569-b8a5-cf91d55ffddc" / ".system_generated" / "logs"
        log_dir.mkdir(parents=True)
        steps = [{"type": "GENERIC", "content": "ok"} for _ in range(65)]
        (log_dir / "transcript.jsonl").write_bytes(("\n".join(json.dumps(s) for s in steps) + "\n").encode("utf-8"))
        self._write_retros([
            {"milestone_index": 1, "cid": "dbc7d48f", "token_efficiency_grade": "A", "tool_reliability_scores": {}},
            {"milestone_index": 1, "cid": "dbc7d48f-f0ba-4569-b8a5-cf91d55ffddc", "steps": 65, "retries": 0,
             "token_efficiency_grade": "B", "tool_reliability_scores": {"overall": 5}},
        ])
        digest = pd.build_digest(self.root, "demo", brain_dir=str(brain), backfill=True)
        self.assertEqual(digest["integrity_issues"], [])
        self.assertEqual(digest["retro_entries"], 1)
        saved = json.loads((self.root / ".frontier" / "plans" / "demo" / "retrospectives.json").read_text(encoding="utf-8"))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["cid"], "dbc7d48f-f0ba-4569-b8a5-cf91d55ffddc")

    def test_enrich_entry_from_audit_and_master_rollup(self) -> None:
        import plan_telemetry as pt
        brain = Path(self._tmp.name) / "brain_flags"
        log_dir = brain / "abc12345-0000-0000-0000-000000000001" / ".system_generated" / "logs"
        log_dir.mkdir(parents=True)
        steps = [
            {"type": "PLANNER_RESPONSE", "tool_calls": [
                {"name": "edit_file", "args": {"Path": "foo.py"}},
                {"name": "edit_file", "args": {"Path": "foo.py"}},
            ]},
            {"type": "PLANNER_RESPONSE", "tool_calls": [{"name": "read_file", "args": {"Path": "bar.py"}}]},
            {"type": "PLANNER_RESPONSE", "tool_calls": [{"name": "read_file", "args": {"Path": "bar.py"}}]},
            {"type": "PLANNER_RESPONSE", "tool_calls": [{"name": "read_file", "args": {"Path": "bar.py"}}]},
        ]
        (log_dir / "transcript.jsonl").write_bytes(("\n".join(json.dumps(s) for s in steps) + "\n").encode("utf-8"))
        entry = {"skill_learn_candidates": []}
        pt._enrich_entry_from_audit(entry, "abc12345-0000-0000-0000-000000000001", str(brain))
        joined = " | ".join(entry["skill_learn_candidates"])
        self.assertIn("parallel edits", joined)
        self.assertIn("bar.py (3x)", joined)

        self._write_retros([{"milestone_index": 1, "token_efficiency_grade": "B", "steps": 50, "retries": 2, "learn_candidates": ["L1"]}])
        master_ps = {"slug": "master", "child_plans": {"1": {"slug": "demo"}}}
        self.assertTrue(pt.rollup_child_retrospective(self.root, master_ps, 1))
        rolled = json.loads((self.root / ".frontier" / "plans" / "master" / "retrospectives.json").read_text(encoding="utf-8"))
        self.assertEqual(rolled[0]["token_efficiency_grade"], "B")
        self.assertEqual(rolled[0]["learn_candidates"], ["L1"])


if __name__ == "__main__":
    unittest.main()
