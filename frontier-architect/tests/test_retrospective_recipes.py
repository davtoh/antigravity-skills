"""Retrospective recipes (Retro M4): files exist, D3 precedence documented, no-edit rule, evals present."""

import re
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
REFS = SKILL_DIR / "references"
EVALS = SKILL_DIR / "evals"
ROUTER = REFS / "retrospective-recipe.md"
GEMINI = REFS / "retrospective-gemini.md"
CLAUDE = REFS / "retrospective-claude.md"
SKILL_MD_LIMIT = 12000


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


class TestRecipeFiles(unittest.TestCase):
    def test_all_recipe_files_exist(self):
        for p in (ROUTER, GEMINI, CLAUDE):
            self.assertTrue(p.is_file(), f"missing {p.name}")

    def test_router_precedence_table_matches_d3(self):
        """explicit --recipe > env RETROSPECTIVE_RECIPE > runtime (CLAUDECODE=1 -> claude) > gemini."""
        rows = re.findall(r"^\|\s*(\d)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|$", _read(ROUTER), re.M)
        ordered = [r[1] for r in sorted(rows)]
        self.assertEqual(len(ordered), 4)
        self.assertIn("--recipe", ordered[0])
        self.assertIn("RETROSPECTIVE_RECIPE", ordered[1])
        self.assertIn("CLAUDECODE=1", ordered[2])
        results = {r[0]: r[2] for r in rows}
        self.assertIn("claude", results["3"])
        self.assertIn("gemini", results["4"])

    def test_both_recipes_have_five_parts(self):
        for p in (GEMINI, CLAUDE):
            text = _read(p)
            for n in range(1, 6):
                self.assertRegex(text, rf"## Part {n}\.", f"{p.name} missing Part {n}")

    def test_gemini_recipe_keeps_antigravity_vocabulary(self):
        text = _read(GEMINI)
        for token in ("ask_question", "learning_proposal.md", "LEARNING_SCAFFOLD.md", "LEARN_QUEUE.md", "AGENTS.md"):
            self.assertIn(token, text)

    def test_claude_recipe_uses_claude_vocabulary(self):
        text = _read(CLAUDE)
        for token in ("AskUserQuestion", "Explore", ".TODO/learning_proposal", "CLAUDE_CODE_SESSION_ID", "D8"):
            self.assertIn(token, text)
        self.assertNotIn("ask_question", text)
        self.assertIn("Never `Read` a session `.jsonl`", text.replace("**", ""))

    def test_no_edits_before_decision_rule_in_all(self):
        for p in (ROUTER, GEMINI, CLAUDE):
            self.assertRegex(_read(p).lower(), r"no edits to skills|do not edit skills", p.name)

    def test_never_overwrite_existing_proposal(self):
        self.assertRegex(_read(CLAUDE), r"never overwrite")
        self.assertRegex(_read(ROUTER), r"Never overwrite")


class TestRouting(unittest.TestCase):
    def test_skill_md_points_to_router_and_stays_small(self):
        skill = SKILL_DIR / "SKILL.md"
        self.assertIn("retrospective-recipe.md", _read(skill))
        self.assertLess(len(skill.read_bytes()), SKILL_MD_LIMIT)

    def test_phase_protocols_points_to_router(self):
        self.assertIn("retrospective-recipe.md", _read(REFS / "phase-protocols.md"))

    def test_eval_cases_exist_with_graders(self):
        for case in ("retrospective-claude-fixture", "retrospective-antigravity-fixture"):
            d = EVALS / case
            for rel in ("case.yaml", "prompt.md"):
                self.assertTrue((d / rel).is_file(), f"{case}/{rel}")
            self.assertGreaterEqual(len(list((d / "graders").glob("*.md"))), 3, case)

    def test_claude_fixture_has_two_sessions(self):
        files = list((EVALS / "retrospective-claude-fixture" / "files").glob("*.jsonl"))
        self.assertEqual(len(files), 2)


if __name__ == "__main__":
    unittest.main()
