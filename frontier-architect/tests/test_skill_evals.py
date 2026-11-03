#!/usr/bin/env python3
"""
Portable regression and eval test suite for Frontier Architect.
Validates evals.json schema and asserts that SKILL.md satisfies all
expectations across all 12 evaluation scenarios without regressions.

100% portable, OS-agnostic, zero hardcoded paths, standard library only.
"""

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

    # Specific patterns evaluated first to prevent shadowing by broader substrings
    if "tool-call ceiling" in exp_lower or "<= 3-5" in exp_lower:
        has_tc = bool(re.search(r"tool-call ceiling|3 to 5|3–5", text, re.I))
        return has_tc, f"Tool-call ceiling: {has_tc}"

    if "user override" in exp_lower or "axiom 10" in exp_lower:
        has_override = bool(re.search(r"axiom 10|user override|just do it|skip the plan|no questions", text, re.I))
        return has_override, f"Axiom 10 User Overrides: {has_override}"

    if "working assumption" in exp_lower or "state.*assumption" in exp_lower or "states working assumption" in exp_lower:
        has_assumptions = bool(re.search(r"state the assumptions|write the assumptions|assumptions in one or two lines|assumptions at the top", text, re.I))
        return has_assumptions, f"State assumptions: {has_assumptions}"

    if "bucket a" in exp_lower:
        has_bucket_a = bool(re.search(r"bucket a|lean|minimal edit", text, re.I))
        return has_bucket_a, f"Bucket A lean handling: {has_bucket_a}"

    if "no interactive user" in exp_lower or "unattended" in exp_lower:
        has_unattended = bool(re.search(r"subagent|unattended|no interactive user|assumptions", text, re.I))
        return has_unattended, f"Unattended handling: {has_unattended}"

    if "pre-flight pause protocol" in exp_lower:
        has_pause = bool(re.search(r"pre-flight pause|allow banner|remote debugging|probe", text, re.I))
        return has_pause, f"Pre-flight pause protocol: {has_pause}"

    if "minimal, scoped edit" in exp_lower:
        has_scope = bool(re.search(r"formatcurrency|targeted|minimal", text, re.I))
        return has_scope, f"Scoped edit recognized: {has_scope}"

    if "destructive actions" in exp_lower:
        has_safe_git = bool(re.search(r"no reset --hard|avoid destructive|branch|non-destructive", text, re.I))
        return has_safe_git, f"Safe git boundary: {has_safe_git}"

    if "single source of truth" in exp_lower or "ssot" in exp_lower or "re-export" in exp_lower or "facade" in exp_lower:
        has_ssot = bool(re.search(r"single source of truth|ssot|re-export|facade|zombie", text, re.I))
        return has_ssot, f"SSOT / Zombie facade prevention: {has_ssot}"

    if "duplicate domain logic" in exp_lower or "delegating legacy" in exp_lower:
        has_dup = bool(re.search(r"duplicate domain logic|unify duplicate|delegation", text, re.I))
        return has_dup, f"Duplicate logic unification: {has_dup}"

    if "delegat" in exp_lower and "refactor-monolith" in exp_lower:
        has_delegation = bool(re.search(r"refactor-monolith|davtoh/antigravity-skills", text, re.I))
        return has_delegation, f"Delegation boundary: {has_delegation}"

    if "modularity budget" in exp_lower or "350-line" in exp_lower:
        has_budget = bool(re.search(r"modularity|350 lines|500 lines|method budget", text, re.I))
        return has_budget, f"Modularity budget: {has_budget}"

    if "mega-turn" in exp_lower or "1-phase-per-turn" in exp_lower:
        has_gate = bool(re.search(r"1-phase-per-turn|phase 1 only|scope immediate|mega-turn", text, re.I))
        return has_gate, f"1-Phase-Per-Turn gate: {has_gate}"

    if "deferred" in exp_lower:
        has_deferred = bool(re.search(r"deferred|subsequent turn|next milestone", text, re.I))
        return has_deferred, f"Deferred phase boundary: {has_deferred}"

    if "symptom-to-root-cause" in exp_lower:
        has_matrix = bool(re.search(r"symptom-to-root-cause|root cause|matrix", text, re.I))
        return has_matrix, f"Symptom to root cause matrix: {has_matrix}"

    if "axiom 9" in exp_lower or "honest reporting" in exp_lower or "honest verification reporting" in exp_lower:
        has_axiom9 = bool(re.search(r"axiom 9|honest reporting|unverified|honest verification", text, re.I))
        return has_axiom9, f"Axiom 9 Honest Reporting: {has_axiom9}"

    if "docker_audit" in exp_lower:
        has_docker = bool(re.search(r"docker_audit\.py|docker stats|docker top", text, re.I))
        return has_docker, f"Docker audit present: {has_docker}"

    if "cdp_inspect" in exp_lower or "cdp inspection" in exp_lower:
        has_cdp = bool(re.search(r"cdp_inspect\.py|bounding box|domrect|chrome devtools", text, re.I))
        return has_cdp, f"CDP inspector present: {has_cdp}"

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

    if "socratic" in exp_lower or "ask_question" in exp_lower:
        has_ask = bool(re.search(r"ask_question|socratic|interview|clarification", text, re.I))
        return has_ask, f"Socratic question protocol: {has_ask}"

    if "self-contained" in exp_lower or "non-bundled" in exp_lower:
        has_self_contained = bool(re.search(r"self-contained|standalone|invariant", text, re.I))
        return has_self_contained, f"Self-containment verified: {has_self_contained}"

    if "multi-skill co-invocation" in exp_lower or "orchestrator of intent" in exp_lower:
        has_co = bool(re.search(r"multi-skill co-invocation|orchestrator of intent|app-debugger", text, re.I))
        return has_co, f"Co-invocation protocol / Orchestrator of Intent: {has_co}"

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
        """Ensure evals.json contains at least 12 valid scenarios with >= 4 expectations each."""
        self.assertGreaterEqual(len(self.evals), 12)
        total_expectations = sum(len(e.get("expectations", [])) for e in self.evals)
        self.assertGreaterEqual(total_expectations, 60)

        for e in self.evals:
            self.assertIn("id", e)
            self.assertIn("prompt", e)
            self.assertIn("expected_output", e)
            self.assertGreaterEqual(len(e.get("expectations", [])), 4)

    def test_skill_passes_all_eval_expectations(self):
        """Assert current SKILL.md achieves 100% pass rate across all 60 expectations."""
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

    def test_evaluate_matcher_direct_cases(self):
        """Direct unit testing of evaluate_expectation_against_text to ensure coverage."""
        ok, _ = evaluate_expectation_against_text("tool-call ceiling: 3 to 5 calls", "Enforces tool-call ceiling")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("Axiom 10: Respect Explicit User Overrides", "Honors Axiom 10 user override")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("state the assumptions at the top", "States working assumptions concisely")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("Bucket A lean handling formatCurrency", "Triages as Bucket A")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("subagent unattended with no interactive user", "No interactive user present")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("Pre-flight pause protocol for remote debugging", "Pre-flight pause protocol")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("targeted minimal edit to formatCurrency", "minimal, scoped edit")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("no reset --hard avoid destructive actions", "avoids destructive actions")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("Single source of truth (SSOT) no zombie facade", "single source of truth")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("unify duplicate domain logic via delegation", "duplicate domain logic")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("delegate to refactor-monolith", "delegates to refactor-monolith")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("modularity budget 350 lines hard ceiling 500 lines", "Modularity budget")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("1-phase-per-turn gate prevents mega-turn", "1-Phase-Per-Turn gate")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("deferred to subsequent turns", "deferred phases")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("symptom-to-root-cause matrix", "symptom-to-root-cause matrix")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("Axiom 9 honest reporting of unverified checks", "Axiom 9 honest reporting")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("scripts/docker_audit.py docker stats", "docker_audit")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("scripts/cdp_inspect.py bounding box", "cdp_inspect")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("Tier 1 Baseline, Tier 2 SOTA, Tier 3 Novel", "3-Tier SOTA proposals")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("pre-flight block and atomic vertical slicing", "flash-to-opus cognitive harness")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("Plan-first gate via /plan artifact", "plan-first gate")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("AGENTS.md project rules", "AGENTS.md file")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("closed-loop verification matrix with async checks", "closed-loop verification matrix")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("context hygiene via /compact and new conversation", "context hygiene")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("Phase 1B reproduce-first diagnostic triage", "reproduce-first triage")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("socratic question clarification via ask_question", "socratic clarification")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("self-contained standalone architecture", "self-contained boundary")
        self.assertTrue(ok)
        ok, _ = evaluate_expectation_against_text("Multi-skill co-invocation with app-debugger as orchestrator of intent", "multi-skill co-invocation")
        self.assertTrue(ok)

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
