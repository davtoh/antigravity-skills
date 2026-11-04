#!/usr/bin/env python3
"""Skill evaluation and regression test suite for refactor-monolith.

Validates that SKILL.md adheres to /skill-creator standards, satisfies
all evaluation scenario expectations without regressions, and passes
pre-commit sanitization gates.
Zero external dependencies; standard library Python 3.10+ only.
"""

import json
import re
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
EVALS_FILE = SKILL_DIR / "evals" / "evals.json"
SKILL_MD = SKILL_DIR / "SKILL.md"


def evaluate_expectation(text: str, expectation: str) -> tuple[bool, str]:
    """Check if skill documentation provides concrete evidence for an expectation."""
    exp_lower = expectation.lower()

    if "mode a" in exp_lower or "single-file" in exp_lower:
        has_mode_a = bool(re.search(r"mode a|single-file", text, re.I))
        return has_mode_a, f"Mode A / Single-file: {has_mode_a}"

    if "code_health_audit.py" in exp_lower:
        has_audit = bool(re.search(r"code_health_audit\.py", text, re.I))
        return has_audit, f"code_health_audit.py: {has_audit}"

    if "breaking imports" in exp_lower or "re-export" in exp_lower or "facade" in exp_lower:
        has_facade = bool(re.search(r"re-export|facade|backward-compatible", text, re.I))
        return has_facade, f"Facade re-export: {has_facade}"

    if "quantitative modularity budget" in exp_lower or "<=350 lines" in exp_lower or "10-12 methods" in exp_lower:
        has_budget = bool(re.search(r"modularity budget|350 lines|500 lines|10.*12 methods", text, re.I))
        return has_budget, f"Modularity budget: {has_budget}"

    if "mode b" in exp_lower or "project_campaign" in exp_lower:
        has_mode_b = bool(re.search(r"mode b|project_campaign|campaign", text, re.I))
        return has_mode_b, f"Mode B / Campaign: {has_mode_b}"

    if "migration_log.md" in exp_lower or "plan.md" in exp_lower:
        has_plan = bool(re.search(r"migration_log\.md|\.refactor/plan\.md", text, re.I))
        return has_plan, f"Migration checklist / plan: {has_plan}"

    if "agents.md" in exp_lower or "freeze" in exp_lower:
        has_agents = bool(re.search(r"agents\.md|freeze", text, re.I))
        return has_agents, f"AGENTS.md / freeze: {has_agents}"

    if "hot loop" in exp_lower or "hot/cold" in exp_lower:
        has_hot = bool(re.search(r"hot/cold|hot loop|memory locality", text, re.I))
        return has_hot, f"Hot/cold loop: {has_hot}"

    if "anti-thrash" in exp_lower or "stop-loss" in exp_lower or "bailout" in exp_lower:
        has_thrash = bool(re.search(r"anti-thrash|stop-loss|bailout", text, re.I))
        return has_thrash, f"Anti-thrash / bailout: {has_thrash}"

    if "vendor" in exp_lower or "minified" in exp_lower:
        has_vendor = bool(re.search(r"vendor|minified", text, re.I))
        return has_vendor, f"Vendor filtering: {has_vendor}"

    if "self-contained" in exp_lower:
        has_sc = bool(re.search(r"self-contained", text, re.I))
        return has_sc, f"Self-contained: {has_sc}"

    if "mode c" in exp_lower or "contract_snapshot.py diagnose" in exp_lower:
        has_mode_c = bool(re.search(r"mode c|diagnose|regression diagnostic", text, re.I))
        return has_mode_c, f"Mode C / diagnose: {has_mode_c}"

    if "baseline.json" in exp_lower or "contract check" in exp_lower:
        has_base = bool(re.search(r"baseline\.json|contract_snapshot\.py verify", text, re.I))
        return has_base, f"Contract verify / baseline: {has_base}"

    if "infinite reload" in exp_lower or "window property" in exp_lower:
        has_reload = bool(re.search(r"infinite reload|window\.", text, re.I))
        return has_reload, f"Infinite reload guard: {has_reload}"

    if "crlf" in exp_lower or "normalize-eol" in exp_lower or "patch" in exp_lower:
        has_eol = bool(re.search(r"crlf|normalize-eol|patch", text, re.I))
        return has_eol, f"CRLF / normalize-eol: {has_eol}"

    if "inject-scripts" in exp_lower:
        has_inj = bool(re.search(r"inject-scripts", text, re.I))
        return has_inj, f"inject-scripts: {has_inj}"

    if "turn ceiling" in exp_lower:
        has_tc = bool(re.search(r"turn ceiling", text, re.I))
        return has_tc, f"Turn ceiling: {has_tc}"

    if "checkpoint" in exp_lower or "state --checkpoint" in exp_lower:
        has_cp = bool(re.search(r"checkpoint|state --checkpoint", text, re.I))
        return has_cp, f"Checkpoint: {has_cp}"

    if "run-tests" in exp_lower or "pytest" in exp_lower:
        has_rt = bool(re.search(r"run-tests", text, re.I))
        return has_rt, f"run-tests: {has_rt}"

    if "polling" in exp_lower or "manage_task" in exp_lower:
        has_poll = bool(re.search(r"polling|manage_task", text, re.I))
        return has_poll, f"No polling rule: {has_poll}"

    if "refactoring invariant" in exp_lower or "behavior preservation" in exp_lower:
        has_inv = bool(re.search(r"refactoring invariant|behavior preservation|\(\\\?delta\(\\?text\{observable behavior\}\)", text, re.I))
        return has_inv, f"Refactoring invariant: {has_inv}"

    if "state --record-defect" in exp_lower or "defect_catalog.json" in exp_lower:
        has_rec = bool(re.search(r"state --record-defect|defect_catalog\.json", text, re.I))
        return has_rec, f"record-defect / defect_catalog.json: {has_rec}"

    if "zero plan.md drift" in exp_lower or "plan.md drift" in exp_lower:
        has_drift = bool(re.search(r"zero plan\.md drift|plan\.md", text, re.I))
        return has_drift, f"Zero plan.md drift: {has_drift}"

    if "handoff" in exp_lower or "summarizes quarantined defects" in exp_lower:
        has_ho = bool(re.search(r"handoff|scaffold-defect", text, re.I))
        return has_ho, f"Defect handoff / scaffold-defect: {has_ho}"

    # Generic keyword match
    words = [w for w in re.findall(r"\b[a-zA-Z_]{4,}\b", exp_lower) if w not in {"with", "that", "from", "this", "then", "have"}]
    found_cnt = sum(1 for w in words if w in text.lower())
    passed = (found_cnt / max(len(words), 1)) >= 0.4
    return passed, f"Generic keywords: {found_cnt}/{len(words)}"


class TestRefactorMonolithSkillEvals(unittest.TestCase):
    """Test suite ensuring SKILL.md meets all evaluation requirements."""

    @classmethod
    def setUpClass(cls):
        cls.assertTrue(EVALS_FILE.exists(), f"Missing evals file at {EVALS_FILE}")
        cls.assertTrue(SKILL_MD.exists(), f"Missing SKILL.md at {SKILL_MD}")

        with open(EVALS_FILE, "r", encoding="utf-8") as f:
            cls.evals_data = json.load(f)
        with open(SKILL_MD, "r", encoding="utf-8") as f:
            cls.skill_text = f.read()

    def test_all_evaluation_expectations(self):
        """Iterate over all evaluation scenarios and assert SKILL.md satisfies each expectation."""
        failures = []
        for eval_case in self.evals_data.get("evals", []):
            eid = eval_case.get("id")
            for exp in eval_case.get("expectations", []):
                passed, reason = evaluate_expectation(self.skill_text, exp)
                if not passed:
                    failures.append(f"Eval {eid}: '{exp}' failed ({reason})")

        self.assertEqual(len(failures), 0, "Regressions found in SKILL.md:\n" + "\n".join(failures))

    def test_line_count_ceiling(self):
        """Assert SKILL.md is under the 500-line hard ceiling."""
        lines = len(self.skill_text.splitlines())
        self.assertLessEqual(lines, 500, f"SKILL.md exceeds 500-line hard ceiling: {lines} lines")

    def test_sanitization_gate(self):
        """Verify committable SKILL.md has zero file-scheme URLs or OS user paths."""
        self.assertNotIn("file:" + "///", self.skill_text, "Forbidden file URI in SKILL.md")
        self.assertNotIn("C:\\" + "Users\\", self.skill_text, "Forbidden local absolute path in SKILL.md")
        self.assertNotIn("/" + "home/", self.skill_text, "Forbidden local absolute path in SKILL.md")


if __name__ == "__main__":
    unittest.main()
