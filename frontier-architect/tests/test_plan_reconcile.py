"""Tests for plan_reconcile, DEBUG_RETRO digestion, and telemetry floor enforcement."""

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
import plan_reconcile as pr  # noqa: E402
import plan_scaffold as ps  # noqa: E402


class TestPlanReconcileAndScaffold(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / ".TODO").mkdir()

    def test_reconcile_flags_duplicate_milestones_and_applies_stale_fix(self) -> None:
        dup_plan = "# Dup\n\n## Milestone 1: A\n- [x] a\n\n## Milestone 1: A\n- [ ] a\n"
        stale_plan = "# Stale\n\n## Milestone 1: Done\n- [x] ok\n"
        (self.root / ".TODO" / "dup.md").write_bytes(dup_plan.encode("utf-8"))
        (self.root / ".TODO" / "stale.md").write_bytes(stale_plan.encode("utf-8"))
        plan_engine.main(["init", ".TODO/stale.md"], root=self.root)
        st_path = self.root / ".frontier" / "plans" / "stale" / "state.json"
        st = json.loads(st_path.read_text(encoding="utf-8"))
        st["status"] = "in_progress"
        st_path.write_bytes(json.dumps(st).encode("utf-8"))

        rows = {r["slug"]: r for r in pr.inspect_workspace_plans(self.root)}
        self.assertIn("duplicate_milestones:1", rows["dup"]["issues"])
        self.assertIn("stale_in_progress_zero_unchecked", rows["stale"]["issues"])

        self.assertEqual(plan_engine.main(["reconcile", "--apply"], root=self.root), 0)
        st_after = json.loads(st_path.read_text(encoding="utf-8"))
        self.assertEqual(st_after["status"], "completed")

    def test_debug_retro_and_triage_symbol_dedup_and_telemetry_floor(self) -> None:
        (self.root / "AGENTS.md").write_bytes("Always call `LivePlayer.detachGridStreams()` before teardown.\n".encode("utf-8"))
        (self.root / ".frontier").mkdir(parents=True, exist_ok=True)
        (self.root / ".frontier" / "DEBUG_RETRO.md").write_bytes((
            "# Debug Retrospectives\n\n"
            "## [2026-11-18] [UNCONFIRMED] StreamWorker crash\n"
            "- **Root Cause**: missing try/except\n"
            "- **Project `/learn`**: Wrap StreamWorker.run() loop in try/except\n"
            "- **Skill `/learn`**: Run debug-retro on RCA sessions\n"
        ).encode("utf-8"))
        (self.root / ".TODO" / "demo.md").write_bytes("# Demo\n\n## Milestone 1: A\n- [x] ok\n".encode("utf-8"))
        plan_engine.main(["init", ".TODO/demo.md"], root=self.root)
        plan_engine.main([
            "retrospective", "demo", "--milestone", "1", "--grade", "A", "--retries", "3", "--steps", "40",
            "--tri", "5,5,5,5", "--hypotheses", "1",
            "--learn", "Always call LivePlayer.detachGridStreams() before innerHTML teardown",
            "--skill-learn", "Transcript audit: repeated file reads (>=3x): app.py (3x)",
        ], root=self.root)
        retros = json.loads((self.root / ".frontier" / "plans" / "demo" / "retrospectives.json").read_text(encoding="utf-8"))
        self.assertEqual(retros[0]["hypotheses_tested"], 4)
        self.assertEqual(retros[0]["tool_reliability_scores"]["tool_reliability"], 4)

        wd = pd.build_workspace_digest(self.root)
        self.assertNotIn("Always call LivePlayer.detachGridStreams() before innerHTML teardown", wd["learn_candidates"])
        self.assertIn("Wrap StreamWorker.run() loop in try/except", wd["learn_candidates"])
        self.assertIn("Run debug-retro on RCA sessions", wd["skill_learn_candidates"])
        self.assertFalse(any(x.startswith("Transcript audit: repeated file reads") for x in wd["skill_learn_candidates"]))
        self.assertIn("Debug retro (unconfirmed): StreamWorker crash", wd["escalations"])

    def test_reconcile_missing_legacy_uncheckboxed_and_json(self) -> None:
        (self.root / ".TODO" / "missing.md").write_bytes("# Missing\n\n## Milestone 1: A\n- [ ] a\n".encode("utf-8"))
        plan_engine.main(["init", ".TODO/missing.md"], root=self.root)
        (self.root / ".TODO" / "missing.md").unlink()

        (self.root / ".TODO" / "legacy.md").write_bytes("# Legacy\n\nJust prose, no milestones.\n".encode("utf-8"))
        plan_engine.main(["init", ".TODO/legacy.md"], root=self.root)
        leg_st = self.root / ".frontier" / "plans" / "legacy" / "state.json"
        st = json.loads(leg_st.read_text(encoding="utf-8"))
        st["status"] = "in_progress"
        leg_st.write_bytes(json.dumps(st).encode("utf-8"))

        (self.root / ".TODO" / "plain.md").write_bytes("# Plain\n\n## Milestone 1: A\n- first item\n- second item\n".encode("utf-8"))
        plan_engine.main(["init", ".TODO/plain.md"], root=self.root)
        plain_st = self.root / ".frontier" / "plans" / "plain" / "state.json"

        rows = {r["slug"]: r for r in pr.inspect_workspace_plans(self.root)}
        self.assertIn("stale_missing_plan", rows["missing"]["issues"])
        self.assertIn("legacy_no_milestones", rows["legacy"]["issues"])
        self.assertIn("uncheckboxed_bullets:2", rows["plain"]["issues"])

        self.assertEqual(plan_engine.main(["reconcile", "--apply", "--json"], root=self.root), 0)
        self.assertEqual(json.loads((self.root / ".frontier" / "plans" / "missing" / "state.json").read_text(encoding="utf-8"))["status"], "completed")
        self.assertEqual(json.loads(leg_st.read_text(encoding="utf-8"))["status"], "completed")
        self.assertEqual(json.loads(plain_st.read_text(encoding="utf-8"))["status"], "in_progress")

    def test_init_warns_on_duplicate_milestones(self) -> None:
        import io
        from contextlib import redirect_stdout
        (self.root / ".TODO" / "dupinit.md").write_bytes("# Dup\n\n## Milestone 1: A\n- [ ] a\n\n## Milestone 1: B\n- [ ] b\n".encode("utf-8"))
        buf = io.StringIO()
        with redirect_stdout(buf):
            plan_engine.main(["init", ".TODO/dupinit.md"], root=self.root)
        self.assertIn("DUPLICATE MILESTONE WARNING", buf.getvalue())

    def test_debug_retro_diagnostics_dir_and_cross_line_triage(self) -> None:
        (self.root / "AGENTS.md").write_bytes("Always call `LivePlayer` here.\nAnd call `detachGridStreams()` separately.\n".encode("utf-8"))
        (self.root / ".diagnostics").mkdir(parents=True, exist_ok=True)
        (self.root / ".diagnostics" / "DEBUG_RETRO.md").write_bytes((
            "# Debug Retro\n\n"
            "## [2026-11-18] [VERIFIED] Fixed leak\n"
            "- **Project `/learn`**: Verified project lesson\n\n"
            "## [2026-11-18] [ESCALATED] Unresolved race\n"
            "- **Skill `/learn`**: Escalated skill lesson\n"
        ).encode("utf-8"))
        (self.root / ".TODO" / "triage.md").write_bytes("# Triage\n\n## Milestone 1: A\n- [x] ok\n".encode("utf-8"))
        plan_engine.main(["init", ".TODO/triage.md"], root=self.root)
        plan_engine.main([
            "retrospective", "triage", "--milestone", "1", "--grade", "A", "--retries", "0", "--steps", "10",
            "--tri", "5,5,5,5", "--hypotheses", "1",
            "--learn", "Always call LivePlayer.detachGridStreams() before teardown",
        ], root=self.root)
        retros = json.loads((self.root / ".frontier" / "plans" / "triage" / "retrospectives.json").read_text(encoding="utf-8"))
        self.assertEqual(retros[0]["hypotheses_tested"], 1)
        self.assertEqual(retros[0]["tool_reliability_scores"]["tool_reliability"], 5)

        wd = pd.build_workspace_digest(self.root)
        self.assertIn("Always call LivePlayer.detachGridStreams() before teardown", wd["learn_candidates"])
        self.assertIn("Verified project lesson", wd["learn_candidates"])
        self.assertIn("Escalated skill lesson", wd["skill_learn_candidates"])
        self.assertIn("Debug retro (escalated): Unresolved race", wd["escalations"])
        self.assertFalse(any("Fixed leak" in e for e in wd["escalations"]))

    def test_telemetry_retry_floor_preserves_explicit_hypotheses(self) -> None:
        (self.root / ".TODO" / "hyp.md").write_bytes("# Hyp\n\n## Milestone 1: A\n- [x] ok\n".encode("utf-8"))
        plan_engine.main(["init", ".TODO/hyp.md"], root=self.root)
        plan_engine.main([
            "retrospective", "hyp", "--milestone", "1", "--grade", "A", "--retries", "2", "--steps", "20",
            "--tri", "5,5,5,5", "--hypotheses", "3",
        ], root=self.root)
        retros = json.loads((self.root / ".frontier" / "plans" / "hyp" / "retrospectives.json").read_text(encoding="utf-8"))
        self.assertEqual(retros[0]["hypotheses_tested"], 3)
        self.assertEqual(retros[0]["tool_reliability_scores"]["tool_reliability"], 4)

    def test_per_plan_digest_filters_unrelated_debug_retro_cids(self) -> None:
        (self.root / ".frontier").mkdir(parents=True, exist_ok=True)
        (self.root / ".frontier" / "DEBUG_RETRO.md").write_bytes((
            "# Debug Retrospectives\n\n"
            "## [2026-11-20] [UNCONFIRMED] Unrelated stream bug\n"
            "- **Telemetry**: cid=bbbb2222 steps=50 fails=1 cap=A cdp_fallbacks=0\n"
            "- **Project `/learn`**: Unrelated lesson\n\n"
            "## [2026-11-20] [UNCONFIRMED] Related plan bug\n"
            "- **Telemetry**: cid=aaaa1111 steps=30 fails=0 cap=A cdp_fallbacks=0\n"
            "- **Project `/learn`**: Related lesson\n"
        ).encode("utf-8"))
        (self.root / ".TODO" / "scoped.md").write_bytes("# Scoped\n\n## Milestone 1: A\n- [x] ok\n".encode("utf-8"))
        plan_engine.main(["init", ".TODO/scoped.md"], root=self.root)
        plan_engine.main([
            "retrospective", "scoped", "--milestone", "1", "--grade", "A", "--retries", "0", "--steps", "30",
            "--tri", "5,5,5,5", "--cid", "aaaa1111-0000-0000-0000-000000000000",
        ], root=self.root)
        d = pd.build_digest(self.root, "scoped")
        self.assertIn("Debug retro (unconfirmed): Related plan bug", d["escalations"])
        self.assertFalse(any("Unrelated stream bug" in e for e in d["escalations"]))
        self.assertIn("Related lesson", d["learn_candidates"])
        self.assertNotIn("Unrelated lesson", d["learn_candidates"])
        wd = pd.build_workspace_digest(self.root)
        self.assertIn("Debug retro (unconfirmed): Unrelated stream bug", wd["escalations"])


if __name__ == "__main__":
    unittest.main()
