#!/usr/bin/env python3
"""Comprehensive branch-complete unit tests for Frontier Architect plan engine.

Tests markdown parser, checklist in-place patcher, state ledger transitions,
cross-platform path resolution, and CLI subcommands with zero external dependencies.
"""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import plan_engine
from plan_parser import (
    _extract_verifiers, _is_section_boundary, discover_plans,
    parse_plan_markdown, patch_milestone_checkboxes, slugify,
)
from plan_state import (
    _calc_active_milestone, bootstrap_plan, get_frontier_dir, get_git_sha,
    get_repo_root, load_json, record_milestone_advance, resolve_plan_path, save_json,
)


class TestPlanParser(unittest.TestCase):
    """Unit tests for plan_parser.py markdown parsing and discovery."""

    def test_slugify(self):
        self.assertEqual(slugify("Milestone 1: Plan Engine"), "milestone_1_plan_engine")
        self.assertEqual(slugify("  ***Special   Chars---!!!  "), "special_chars")
        self.assertEqual(slugify(""), "unnamed_plan")

    def test_discover_plans(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for d in (".plans", ".TODO", "node_modules"):
                (root / d).mkdir()
            p1, p2 = root / ".plans" / "plan_a.md", root / ".TODO" / "plan_b.md"
            ign = root / "node_modules" / "plan_c.md"
            for p in (p1, p2, ign):
                p.write_text("# Plan", encoding="utf-8")
            found = [p.name for p in discover_plans(root)]
            self.assertIn("plan_a.md", found)
            self.assertIn("plan_b.md", found)
            self.assertNotIn("plan_c.md", found)

    def test_parse_plan_markdown_full_and_variations(self):
        md = (
            "# Main Architecture Plan\n\n### Milestone 1: Core Setup\n"
            "- [x] 1.1 First task\n- [ ] 1.2 Second task\n\n"
            "### **Milestone 2**: Advanced Features\n* [ ] 2.1 Third task\n"
            "  - [ ] Nested subtask\n\n## Scenario Matrix\n| Col 1 | Col 2 |\n\n"
            "### 4.1 Non-Milestone Section\n- Non-task bullet\n\n"
            "```bash\npython -m unittest discover tests\n# comment\npytest tests/\n```\n"
        )
        parsed = parse_plan_markdown(md)
        self.assertEqual(parsed["title"], "Main Architecture Plan")
        self.assertEqual(len(parsed["milestones"]), 2)
        m1, m2 = parsed["milestones"][0], parsed["milestones"][1]
        self.assertEqual(m1["index"], 1)
        self.assertFalse(m1["is_complete"])
        self.assertEqual(m2["index"], 2)
        self.assertEqual(len(m2["tasks"]), 2)
        self.assertIn("python -m unittest discover tests", parsed["verification_commands"])
        self.assertIn("pytest tests/", parsed["verification_commands"])

    def test_parse_plan_markdown_plain_bullets(self):
        md = (
            "# Plain Bullets Plan\n\n### Phase 1: Core Worker\n"
            "- **`intelligent_tracker/batch.py`**: Add progress callback\n"
            "- **`video_transcoder.py`**: Add async transcode\n\n"
            "### Milestone 2: Service Layer\n"
            "- **`video_jobs.py`**: Add job manager\n"
        )
        parsed = parse_plan_markdown(md)
        self.assertEqual(len(parsed["milestones"]), 2)
        m1 = parsed["milestones"][0]
        self.assertEqual(m1["index"], 1)
        self.assertEqual(len(m1["tasks"]), 2)
        self.assertFalse(m1["tasks"][0]["checked"])
        self.assertIn("batch.py", m1["tasks"][0]["text"])

    def test_section_boundary_and_verifiers(self):
        self.assertTrue(_is_section_boundary("## 2. Requirements"))
        self.assertTrue(_is_section_boundary("### 4.1 Sign-Off"))
        self.assertFalse(_is_section_boundary("### Milestone 1: Init"))
        self.assertFalse(_is_section_boundary("## Scenario Matrix"))
        self.assertFalse(_is_section_boundary("- [ ] Task item"))
        self.assertEqual(_extract_verifiers("No code blocks"), [])
        self.assertEqual(_extract_verifiers("```python\n# only comments\n```"), [])
        table_md = (
            "| Scenario | Verification Check |\n| :--- | :--- |\n"
            "| SC-01 | `python -m unittest tests/test_video_jobs.py` |\n"
            "| SC-02 | `python` prose and `python scripts/plan_engine.py init <plan>` |\n"
        )
        self.assertEqual(_extract_verifiers(table_md), ["python -m unittest tests/test_video_jobs.py"])


class TestChecklistPatching(unittest.TestCase):
    """Unit tests for in-place markdown checkbox modification."""

    def test_patch_milestone_checkboxes(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "plan.md"
            p.write_text(
                "### Milestone 1: First\n- [ ] Task 1.1\n- [ ] Task 1.2\n\n"
                "### Milestone 2: Second\n- [ ] Task 2.1\n",
                encoding="utf-8",
            )
            count = patch_milestone_checkboxes(p, 1)
            self.assertEqual(count, 2)
            content = p.read_text(encoding="utf-8")
            self.assertIn("- [x] Task 1.1", content)
            self.assertIn("- [x] Task 1.2", content)
            self.assertIn("- [ ] Task 2.1", content)

    def test_patch_plain_bullet_tasks(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "plan.md"
            p.write_text(
                "### Phase 1: First\n- Bullet task 1\n- Bullet task 2\n\n"
                "### Phase 2: Second\n- Bullet task 3\n",
                encoding="utf-8",
            )
            count = patch_milestone_checkboxes(p, 1)
            self.assertEqual(count, 2)
            content = p.read_text(encoding="utf-8")
            self.assertIn("- [x] Bullet task 1", content)
            self.assertIn("- [x] Bullet task 2", content)
            self.assertIn("- Bullet task 3", content)

    def test_patch_preserves_crlf_and_non_targets(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "plan.md"
            p.write_bytes(b"### Milestone 1: A\r\n- [ ] Task\r\n### Notes\r\n- [ ] Note\r\n")
            count = patch_milestone_checkboxes(p, 1)
            self.assertEqual(count, 1)
            raw = p.read_bytes()
            self.assertIn(b"\r\n", raw)
            self.assertIn(b"- [x] Task\r\n", raw)
            self.assertIn(b"- [ ] Note\r\n", raw)
            self.assertEqual(patch_milestone_checkboxes(p, 99), 0)


class TestPlanState(unittest.TestCase):
    """Unit tests for plan_state.py state ledgers and workspace persistence."""

    def test_repo_root_and_frontier_dir(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            sub = root / "src" / "deep"
            sub.mkdir(parents=True)
            self.assertEqual(get_repo_root(sub), root)
            fdir = get_frontier_dir(root)
            self.assertTrue((fdir / ".gitignore").exists())
            self.assertIn("*", (fdir / ".gitignore").read_text(encoding="utf-8"))

    def test_load_and_atomic_save_json(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "sub" / "data.json"
            self.assertEqual(load_json(p, {"default": 1}), {"default": 1})
            save_json(p, {"saved": True})
            self.assertEqual(load_json(p), {"saved": True})
            p.write_text("{bad json", encoding="utf-8")
            self.assertEqual(load_json(p, "fallback"), "fallback")

    def test_resolve_plan_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".plans").mkdir()
            p = root / ".plans" / "my_cool_feature_plan.md"
            p.write_text("# Feature Plan\n### Milestone 1: Go\n- [ ] Task", encoding="utf-8")
            self.assertEqual(resolve_plan_path(root, str(p)), p)
            self.assertEqual(resolve_plan_path(root, "my_cool_feature_plan"), p)
            self.assertEqual(resolve_plan_path(root, "cool_feature"), p)
            self.assertIsNone(resolve_plan_path(root, "nonexistent_slug"))
            self.assertEqual(resolve_plan_path(root, None), p)

    def test_bootstrap_and_record_advance(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = root / "feature_plan.md"
            p.write_text(
                "# Feature\n### Milestone 1: Init\n- [x] T1\n### Milestone 2: Finish\n- [ ] T2\n",
                encoding="utf-8",
            )
            _ws, ps = bootstrap_plan(root, p)
            self.assertEqual(ps["active_milestone_index"], 2)
            self.assertEqual(ps["status"], "in_progress")
            fdir = get_frontier_dir(root)
            ps = record_milestone_advance(fdir, ps, 2, "abc1234", "2026-11-08T00:00:00Z")
            self.assertEqual(ps["status"], "completed")
            self.assertEqual(ps["milestones"][1]["commit_sha"], "abc1234")
            ws_reloaded = load_json(fdir / "state.json")
            self.assertEqual(ws_reloaded["active_plan"]["status"], "completed")

    def test_calc_active_milestone_and_git_sha(self):
        ms = [{"index": 1, "is_complete": True}, {"index": 2, "is_complete": False}]
        self.assertEqual(_calc_active_milestone(ms), 2)
        self.assertEqual(_calc_active_milestone([{"index": 1, "is_complete": True}]), 1)
        self.assertEqual(_calc_active_milestone([]), 1)
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(get_git_sha(Path(td)), "")


class TestPlanEngineCLI(unittest.TestCase):
    """Unit tests for plan_engine.py CLI commands and subparser orchestration."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.plan_path = self.root / ".TODO" / "sample_plan.md"
        self.plan_path.parent.mkdir(parents=True)
        self.plan_path.write_text(
            "# Sample Plan\n\n### Milestone 1: Initial Slice\n- [ ] Task 1.1\n\n"
            "### Milestone 2: Second Slice\n- [ ] Task 2.1\n\n"
            "```bash\npython -m unittest discover tests\n```\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.td.cleanup()

    def _run_cli(self, args_list: list[str]) -> tuple[int, str]:
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = plan_engine.main(args_list, root=self.root)
        return code, buf.getvalue()

    def test_parse_tri_helper(self):
        self.assertEqual(plan_engine._parse_tri(None), {})
        self.assertEqual(plan_engine._parse_tri("5"), {"overall": 5})
        self.assertEqual(plan_engine._parse_tri("cdp=5, plan=4, bad=xyz"), {"cdp": 5, "plan": 4})

    def test_cli_discover_and_init(self):
        code, out = self._run_cli(["discover"])
        self.assertEqual(code, 0)
        self.assertIn("sample_plan.md", out)

        code, out = self._run_cli(["init", "sample_plan"])
        self.assertEqual(code, 0)
        self.assertIn("Initialized plan: Sample Plan", out)

        code, _ = self._run_cli(["init", "nonexistent_target_xyz"])
        self.assertEqual(code, 1)

    def test_cli_discover_empty(self):
        with tempfile.TemporaryDirectory() as td:
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                code = plan_engine.main(["discover"], root=Path(td))
            self.assertEqual(code, 0)
            self.assertIn("No architectural plans found", buf.getvalue())

    def test_cli_unresolvable_plan_errors(self):
        for cmd in ["status", "next", "advance", "retrospective"]:
            code, _ = self._run_cli([cmd, "nonexistent_slug_999"])
            self.assertEqual(code, 1)

    def test_cli_status_and_next(self):
        self._run_cli(["init", "sample_plan"])
        code, out = self._run_cli(["status", "sample_plan"])
        self.assertEqual(code, 0)
        self.assertIn("Milestone 1 of 2", out)

        code, out_json = self._run_cli(["status", "sample_plan", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out_json)["plan"]["slug"], "sample_plan")

        code, out = self._run_cli(["next", "sample_plan"])
        self.assertEqual(code, 0)
        self.assertIn("Task 1.1", out)
        self.assertIn("python -m unittest discover tests", out)

        code, out_cont = self._run_cli(["continue", "sample_plan"])
        self.assertEqual(code, 0)
        self.assertEqual(out, out_cont)

        code, out_json = self._run_cli(["next", "sample_plan", "--json"])
        self.assertEqual(code, 0)
        self.assertIn("verifiers", json.loads(out_json))

    def test_cli_advance_and_completion(self):
        self._run_cli(["init", "sample_plan"])
        code, out = self._run_cli(["advance", "sample_plan", "--commit", "feedbeef"])
        self.assertEqual(code, 0)
        self.assertIn("checked 1 tasks", out)
        self.assertIn("Suggested Commit: git commit -m", out)

        code, out = self._run_cli(["advance", "sample_plan", "--milestone", "2"])
        self.assertEqual(code, 0)
        self.assertIn("All milestones COMPLETED", out)

        code, out = self._run_cli(["next", "sample_plan"])
        self.assertEqual(code, 0)
        self.assertIn("All milestones in 'Sample Plan' are completed", out)

        code, out_json = self._run_cli(["next", "sample_plan", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out_json)["status"], "completed")

    def test_cli_retrospective_and_lookup(self):
        self._run_cli(["init", "sample_plan"])
        code, out = self._run_cli([
            "retrospective", "sample_plan", "--grade", "A", "--tri", "cdp=5,plan=4",
            "--hypotheses", "2", "--learn", "Use zero-dependency parsers",
            "--escalate", "Uncaught DOM overflow",
        ])
        self.assertEqual(code, 0)
        self.assertIn("Token Grade: A", out)

        code, out = self._run_cli(["lookup", "sample"])
        self.assertEqual(code, 0)
        self.assertIn("[PLAN]", out)

        code, out = self._run_cli(["lookup", "zero-dependency"])
        self.assertEqual(code, 0)
        self.assertIn("[RETRO]", out)

        code, out = self._run_cli(["lookup", "unmatched_term_xyz"])
        self.assertEqual(code, 0)
        self.assertIn("No historical decisions", out)

    @patch("subprocess.run")
    def test_cli_verify(self, mock_subproc):
        self._run_cli(["init", "sample_plan"])
        mock_subproc.return_value = MagicMock(returncode=0, stdout="Ran 8 tests in 0.05s\n\nOK\n", stderr="")

        code, out = self._run_cli(["verify", "sample_plan"])
        self.assertEqual(code, 0)
        self.assertIn("Running verifier: python -m unittest", out)

        ws = load_json(get_frontier_dir(self.root) / "state.json")
        self.assertEqual(ws["verification_baseline"]["passed_tests"], 8)
        self.assertEqual(ws["verification_baseline"]["failed_tests"], 0)

        # Test failure parsing
        mock_subproc.return_value = MagicMock(returncode=1, stdout="FAILED (failures=2, errors=1)\n", stderr="")
        code, _ = self._run_cli(["verify", "sample_plan"])
        self.assertEqual(code, 1)
        ws = load_json(get_frontier_dir(self.root) / "state.json")
        self.assertEqual(ws["verification_baseline"]["failed_tests"], 3)

        # Test --cmd alias and baseline fallback on a plan without explicit verifiers
        no_ver_plan = self.root / ".TODO" / "no_ver_plan.md"
        no_ver_plan.write_text("# Bare Plan\n### Milestone 1: Do\n- [ ] Task\n", encoding="utf-8")
        mock_subproc.return_value = MagicMock(returncode=0, stdout="Ran 3 tests\n\nOK\n", stderr="")
        code, out = self._run_cli(["verify", "no_ver_plan", "--cmd", "pytest tests/custom.py"])
        self.assertEqual(code, 0)
        self.assertIn("Running verifier: pytest tests/custom.py", out)
        # Subsequent verify without --cmd should reuse stored baseline command
        code, out = self._run_cli(["verify", "no_ver_plan"])
        self.assertEqual(code, 0)
        self.assertIn("Running verifier: pytest tests/custom.py", out)

    def test_cross_platform_path_handling(self):
        rel_posix = self.plan_path.relative_to(self.root).as_posix()
        self.assertNotIn("\\", rel_posix)
        self.assertTrue(rel_posix.startswith(".TODO/"))


if __name__ == "__main__":
    unittest.main()
