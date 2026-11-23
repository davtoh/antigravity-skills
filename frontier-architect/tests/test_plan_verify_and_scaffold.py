"""Tests for plan_scaffold workflow/plan-mode promotion and plan_verify timeout handling."""

import argparse
import json
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
        self.assertIn("## Learning Scaffold Highlights", rendered)
        self.assertIn("- Top Project Lesson: Rule 1", rendered)

    def test_promote_transcript_findings_flags_unescalated_thrash(self) -> None:
        skill_learns, escalations = [], []
        rows = [
            {"cid": "aaaa1111-0000", "total_failures": 4, "has_debug_retro": False},
            {"cid": "bbbb2222-0000", "total_failures": 5, "has_debug_retro": True},
        ]
        ps.promote_transcript_findings(rows, skill_learns, escalations)
        self.assertEqual(len(escalations), 1)
        self.assertIn("Unescalated thrash (aaaa1111): 4 failures without /app-debugger or debug-retro", escalations[0])

    def test_future_turn_tag_stripped_and_pending_sha_synced(self) -> None:
        import plan_rollup as pr
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Tester"], cwd=root, check=True, capture_output=True)
            (root / "app.py").write_bytes(b"v = 1\n")
            subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
            base_sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
            (root / ".TODO").mkdir()
            (root / ".TODO" / "demo.md").write_bytes("# Demo\n\n### Milestone 1: Core *(Deferred to Future Turn)*\n- [ ] **app.py**: update\n".encode("utf-8"))
            plan_engine.main(["init", ".TODO/demo.md"], root=root)
            (root / "app.py").write_bytes(b"v = 2\n")
            self.assertEqual(plan_engine.main(["advance", "demo", "--milestone", "1"], root=root), 0)
            patched = (root / ".TODO" / "demo.md").read_text(encoding="utf-8")
            self.assertNotIn("Deferred to Future Turn", patched)
            st = json.loads((root / ".frontier" / "plans" / "demo" / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(st["milestones"][0]["commit_sha"], f"pending:{base_sha}")
            subprocess.run(["git", "add", "app.py"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "feat: m1"], cwd=root, check=True, capture_output=True)
            m1_sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
            self.assertTrue(pr.sync_pending_commit_shas(root, st))
            st2 = json.loads((root / ".frontier" / "plans" / "demo" / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(st2["milestones"][0]["commit_sha"], m1_sha)

    def test_sync_pending_commit_shas_edge_cases(self) -> None:
        import plan_rollup as pr
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self.assertFalse(pr.sync_pending_commit_shas(root, {"slug": "x", "milestones": [{"status": "completed", "commit_sha": "pending:abc"}]}))
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Tester"], cwd=root, check=True, capture_output=True)
            (root / "app.py").write_bytes(b"v = 1\n")
            subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
            base_sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
            (root / ".TODO").mkdir()
            (root / ".TODO" / "demo.md").write_bytes("# Demo\n\n## Milestone 1: M1\n- [ ] a\n\n## Milestone 2: M2\n- [ ] b\n".encode("utf-8"))
            plan_engine.main(["init", ".TODO/demo.md"], root=root)
            self.assertEqual(plan_engine.main(["advance", "demo", "--milestone", "1"], root=root), 0)
            st_clean = json.loads((root / ".frontier" / "plans" / "demo" / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(st_clean["milestones"][0]["commit_sha"], base_sha)
            st_pending = {"slug": "demo", "milestones": [
                {"status": "completed", "commit_sha": f"pending:{base_sha}"},
                {"status": "completed", "commit_sha": f"pending:{base_sha}"},
            ]}
            self.assertFalse(pr.sync_pending_commit_shas(root, st_pending))
            (root / "app.py").write_bytes(b"v = 2\n")
            subprocess.run(["git", "add", "app.py"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "c1"], cwd=root, check=True, capture_output=True)
            c1 = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
            (root / "app.py").write_bytes(b"v = 3\n")
            subprocess.run(["git", "add", "app.py"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "c2"], cwd=root, check=True, capture_output=True)
            c2 = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
            self.assertTrue(pr.sync_pending_commit_shas(root, st_pending))
            self.assertEqual([m["commit_sha"] for m in st_pending["milestones"]], [c1, c2])

    def test_workspace_digest_sorts_completed_by_latest_retro_at(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".TODO").mkdir()
            for idx in range(7):
                slug = f"p{idx}"
                (root / ".TODO" / f"{slug}.md").write_text(f"# {slug}\n", encoding="utf-8")
                d = root / ".frontier" / "plans" / slug
                d.mkdir(parents=True)
                (d / "state.json").write_text(json.dumps({"slug": slug, "plan_path": f".TODO/{slug}.md", "status": "completed", "milestones": [{"status": "completed"}], "updated_at": f"2026-11-0{idx+1}T00:00:00Z"}), encoding="utf-8")
            def fake_digest(_root, plan_path, *_args):
                slug = Path(plan_path).stem
                idx = int(slug[1:])
                return {
                    "slug": slug, "title": slug, "status": "completed",
                    "milestones": [{"status": "completed"}], "retro_entries": 1, "integrity_issues": [],
                    "learn_candidates": [f"lesson-{idx}"], "skill_learn_candidates": [], "tool_gaps": [],
                    "escalations": [], "went_well": [], "latest_retro_at": f"2026-11-0{idx+1}T12:00:00Z",
                    "transcripts": [],
                }
            res = ps._build_workspace_digest_core(root, None, False, fake_digest)
            self.assertEqual(res["learn_candidates"], ["lesson-6", "lesson-5", "lesson-4", "lesson-3", "lesson-2"])

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

    def test_triage_plan_candidates_and_record_followup_cid(self) -> None:
        import plan_digest as pd
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "AGENTS.md").write_text("- Always preserve has_target_custom=False when injecting built-in rules in resolve_target_filters.\n", encoding="utf-8")
            (root / ".TODO").mkdir()
            (root / ".TODO" / "demo.md").write_bytes("# Demo\n\n## Milestone 1: M1\n- [ ] **a.py**: add\n".encode("utf-8"))
            plan_engine.main(["init", ".TODO/demo.md"], root=root)
            plan_engine.main(["advance", "demo", "--milestone", "1"], root=root)
            plan_engine.main(["retrospective", "demo", "--milestone", "1", "--grade", "A", "--steps", "20", "--retries", "0", "--cid", "11111111", "--learn", "Preserve has_target_custom=False in resolve_target_filters when injecting built-in rules", "--skill-learn", "Transcript audit: repeated file reads (>=3x): a.py (3x)"], root=root)
            self.assertTrue(ps.record_followup_cid(root, "demo", "22222222"))
            brain = root / "brain"
            for cid in ("11111111", "22222222"):
                lp = brain / cid / ".system_generated" / "logs"
                lp.mkdir(parents=True)
                (lp / "transcript.jsonl").write_text('{"step_index":0,"type":"USER_INPUT","content":"hi"}\n', encoding="utf-8")
            d = pd.build_digest(root, "demo", brain_dir=str(brain), backfill=False)
            self.assertEqual(d["learn_candidates"], [])
            self.assertEqual(d["skill_learn_candidates"], [])
            self.assertEqual({r["cid"] for r in d["transcripts"]}, {"11111111", "22222222"})

    def test_followup_cids_preserved_on_reinit_and_completed_plan(self) -> None:
        import plan_digest as pd
        import plan_state as pst
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".TODO").mkdir()
            (root / ".TODO" / "demo.md").write_bytes("# Demo\n\n## Milestone 1: M1\n- [ ] **a.py**: add\n".encode("utf-8"))
            plan_engine.main(["init", ".TODO/demo.md"], root=root)
            plan_engine.main(["advance", "demo", "--milestone", "1"], root=root)
            plan_engine.main(["retrospective", "demo", "--milestone", "1", "--grade", "A", "--cid", "11111111"], root=root)
            self.assertTrue(ps.record_followup_cid(root, "demo", "22222222"))
            # Re-running init must preserve followup_cids in state.json
            plan_engine.main(["init", ".TODO/demo.md"], root=root)
            state_data = pst.load_json(root / ".frontier" / "plans" / "demo" / "state.json", {})
            self.assertEqual(state_data.get("followup_cids"), ["22222222"])
            brain = root / "brain"
            for cid in ("11111111", "22222222"):
                lp = brain / cid / ".system_generated" / "logs"
                lp.mkdir(parents=True)
                (lp / "transcript.jsonl").write_text('{"step_index":0,"type":"USER_INPUT","content":"hi"}\n', encoding="utf-8")
            d = pd.build_digest(root, "demo", brain_dir=str(brain), backfill=False)
            self.assertEqual(d["status"], "completed")
            self.assertEqual({r["cid"] for r in d["transcripts"]}, {"11111111", "22222222"})

    def test_triage_candidates_keeps_distinct_rules_and_dedupes(self) -> None:
        import plan_scaffold as psc
        with tempfile.TemporaryDirectory() as tmpdir:
            doc = Path(tmpdir) / "AGENTS.md"
            doc.write_text("- Always use monotonic clocks in cache schedulers.\n", encoding="utf-8")
            items = [
                "Use monotonic clocks in cache schedulers",
                "Use monotonic clocks in cache schedulers!",
                "Validate archive symlinks uniformly across zip and tar extractors",
            ]
            kept = psc._triage_candidates(items, [doc])
            self.assertEqual(kept, ["Validate archive symlinks uniformly across zip and tar extractors"])


if __name__ == "__main__":
    unittest.main()
