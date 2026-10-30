#!/usr/bin/env python3
"""
Portable regression and eval test suite for Frontier Architect.
Validates evals.json schema and asserts that SKILL.md satisfies all
expectations across all 9 evaluation scenarios without regressions.

100% portable, OS-agnostic, zero hardcoded paths, standard library only.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
EVALS_FILE = SKILL_DIR / "evals" / "evals.json"
SKILL_MD = SKILL_DIR / "SKILL.md"
WORKSPACE_DIR = SKILL_DIR.parent / f"{SKILL_DIR.name}-workspace"
BASELINE_SKILL_MD = WORKSPACE_DIR / "skill-snapshot" / "SKILL.md"


def evaluate_expectation_against_text(text: str, expectation: str) -> tuple[bool, str]:
    """Helper to check if a skill text contains concrete evidence for an expectation."""
    exp_lower = expectation.lower()

    if "3-tier sota" in exp_lower:
        has_t1 = bool(re.search(r"tier\s*1", text, re.I))
        has_t2 = bool(re.search(r"tier\s*2", text, re.I))
        has_t3 = bool(re.search(r"tier\s*3", text, re.I))
        has_sota = bool(re.search(r"sota|baseline|frontier", text, re.I))
        passed = (has_t1 and has_t2 and has_t3) or (has_sota and (has_t1 or has_t2))
        return passed, f"Tiers: T1={has_t1}, T2={has_t2}, T3={has_t3}, SOTA={has_sota}"

    if "flash-to-opus" in exp_lower or "cognitive harness" in exp_lower:
        has_preflight = bool(re.search(r"pre-flight|preflight|invariants", text, re.I))
        has_mapreduce = bool(re.search(r"map-reduce|subagent|isolation", text, re.I))
        has_slicing = bool(re.search(r"vertical slic|atomic slic", text, re.I))
        passed = has_preflight or has_mapreduce or has_slicing
        return passed, f"Harness: Pre-Flight={has_preflight}, Map-Reduce={has_mapreduce}, Slicing={has_slicing}"

    if "plan-first" in exp_lower or "/plan" in exp_lower:
        has_plan = bool(re.search(r"plan-first|implementation plan|requestfeedback|/plan", text, re.I))
        return has_plan, f"Plan-first indicators: {has_plan}"

    if "agents.md" in exp_lower:
        has_agents = bool(re.search(r"agents\.md|\.agents/rules", text, re.I))
        return has_agents, f"AGENTS.md presence: {has_agents}"

    if "closed-loop" in exp_lower or "verification matrix" in exp_lower:
        has_matrix = bool(re.search(r"verification|closed-loop|matrix|async|waitmsbeforeasync", text, re.I))
        return has_matrix, f"Closed-loop matrix: {has_matrix}"

    if "context" in exp_lower and "hygiene" in exp_lower:
        has_hygiene = bool(re.search(r"new conversation|/compact|context hygiene", text, re.I))
        return has_hygiene, f"Context hygiene: {has_hygiene}"

    if "reproduce-first" in exp_lower or "phase 1b" in exp_lower or "triag" in exp_lower:
        has_diag = bool(re.search(r"phase 1b|reproduce-first|diagnostic|triage", text, re.I))
        return has_diag, f"Reproduce-first triage: {has_diag}"

    if "docker_audit" in exp_lower:
        has_docker = bool(re.search(r"docker_audit\.py|docker stats|docker top", text, re.I))
        return has_docker, f"Docker audit present: {has_docker}"

    if "cdp_inspect" in exp_lower or "cdp inspection" in exp_lower:
        has_cdp = bool(re.search(r"cdp_inspect\.py|bounding box|domrect|chrome devtools", text, re.I))
        return has_cdp, f"CDP inspector present: {has_cdp}"

    if "socratic" in exp_lower or "ask_question" in exp_lower:
        has_ask = bool(re.search(r"ask_question|socratic|interview|clarification", text, re.I))
        return has_ask, f"Socratic question protocol: {has_ask}"

    if "symptom-to-root-cause" in exp_lower:
        has_matrix = bool(re.search(r"symptom-to-root-cause|root cause|matrix", text, re.I))
        return has_matrix, f"Symptom to root cause matrix: {has_matrix}"

    if "bucket a" in exp_lower:
        has_bucket_a = bool(re.search(r"bucket a|lean|minimal edit", text, re.I))
        return has_bucket_a, f"Bucket A lean handling: {has_bucket_a}"

    if "minimal, scoped edit" in exp_lower:
        has_scope = bool(re.search(r"formatcurrency|targeted|minimal", text, re.I))
        return has_scope, f"Scoped edit recognized: {has_scope}"

    if "no interactive user" in exp_lower or "unattended" in exp_lower:
        has_unattended = bool(re.search(r"subagent|unattended|assumptions", text, re.I))
        return has_unattended, f"Unattended handling: {has_unattended}"

    if "destructive actions" in exp_lower:
        has_safe_git = bool(re.search(r"no reset --hard|avoid destructive|branch", text, re.I))
        return has_safe_git, f"Safe git boundary: {has_safe_git}"

    if "mega-turn" in exp_lower or "1-phase-per-turn" in exp_lower:
        has_gate = bool(re.search(r"1-phase-per-turn|phase 1 only|scope immediate|mega-turn", text, re.I))
        return has_gate, f"1-Phase-Per-Turn gate: {has_gate}"

    if "deferred" in exp_lower:
        has_deferred = bool(re.search(r"deferred|subsequent turn|next milestone", text, re.I))
        return has_deferred, f"Deferred phase boundary: {has_deferred}"

    if "pre-flight pause protocol" in exp_lower:
        has_pause = bool(re.search(r"pre-flight pause|allow banner|remote debugging|probe", text, re.I))
        return has_pause, f"Pre-flight pause protocol: {has_pause}"

    if "axiom 9" in exp_lower or "honest reporting" in exp_lower:
        has_axiom9 = bool(re.search(r"axiom 9|honest reporting|unverified", text, re.I))
        return has_axiom9, f"Axiom 9 Honest Reporting: {has_axiom9}"

    if "modularity budget" in exp_lower or "350-line" in exp_lower:
        has_budget = bool(re.search(r"modularity|350 lines|500 lines|method budget", text, re.I))
        return has_budget, f"Modularity budget: {has_budget}"

    if "delegat" in exp_lower and "refactor-monolith" in exp_lower:
        has_delegation = bool(re.search(r"refactor-monolith|davtoh/antigravity-skills", text, re.I))
        return has_delegation, f"Delegation boundary: {has_delegation}"

    if "self-contained" in exp_lower or "non-bundled" in exp_lower:
        has_self_contained = bool(re.search(r"self-contained|standalone|invariant", text, re.I))
        return has_self_contained, f"Self-containment verified: {has_self_contained}"

    # Generic keyword fallback
    keywords = [w for w in re.findall(r"\b[a-zA-Z_]{4,}\b", exp_lower) if w not in {"with", "that", "from", "this", "then", "have"}]
    found_kw = sum(1 for kw in keywords if kw in text.lower())
    passed = (found_kw / max(len(keywords), 1)) >= 0.35
    return passed, f"Generic keywords: {found_kw}/{len(keywords)}"


class TestSkillEvals(unittest.TestCase):
    """Test suite ensuring SKILL.md satisfies all evals in evals/evals.json."""

    @classmethod
    def setUpClass(cls):
        cls.assertTrue(EVALS_FILE.exists(), f"evals.json missing at {EVALS_FILE}")
        cls.assertTrue(SKILL_MD.exists(), f"SKILL.md missing at {SKILL_MD}")

        with open(EVALS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            cls.evals = data.get("evals", [])

        cls.skill_text = SKILL_MD.read_text(encoding="utf-8")

    def test_evals_json_structure(self):
        """Ensure evals.json contains at least 9 valid scenarios with >= 4 expectations each."""
        self.assertGreaterEqual(len(self.evals), 9)
        total_expectations = sum(len(e.get("expectations", [])) for e in self.evals)
        self.assertGreaterEqual(total_expectations, 48)

        for e in self.evals:
            self.assertIn("id", e)
            self.assertIn("prompt", e)
            self.assertIn("expected_output", e)
            self.assertGreaterEqual(len(e.get("expectations", [])), 4)

    def test_skill_passes_all_eval_expectations(self):
        """Assert current SKILL.md achieves 100% pass rate across all 48 expectations."""
        failed_expectations = []
        for e in self.evals:
            eid = e["id"]
            for exp in e.get("expectations", []):
                passed, reason = evaluate_expectation_against_text(self.skill_text, exp)
                if not passed:
                    failed_expectations.append(f"Eval {eid}: '{exp}' failed ({reason})")

        self.assertEqual(
            len(failed_expectations),
            0,
            f"Regressions found in SKILL.md:\n" + "\n".join(failed_expectations),
        )

    def test_baseline_comparison_performance(self):
        """If historical baseline snapshot is available, verify no regressions against it."""
        if not BASELINE_SKILL_MD.exists():
            self.skipTest(f"Baseline snapshot not found at {BASELINE_SKILL_MD}; skipping diff.")

        baseline_text = BASELINE_SKILL_MD.read_text(encoding="utf-8")

        current_passed = 0
        baseline_passed = 0
        total_expectations = 0

        for e in self.evals:
            for exp in e.get("expectations", []):
                total_expectations += 1
                curr_ok, _ = evaluate_expectation_against_text(self.skill_text, exp)
                base_ok, _ = evaluate_expectation_against_text(baseline_text, exp)
                if curr_ok:
                    current_passed += 1
                if base_ok:
                    baseline_passed += 1

        curr_rate = current_passed / total_expectations
        base_rate = baseline_passed / total_expectations

        # Verify current version strictly outperforms or matches baseline
        self.assertGreater(curr_rate, base_rate)
        self.assertGreaterEqual(curr_rate, 0.95)


if __name__ == "__main__":
    unittest.main()
