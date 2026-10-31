#!/usr/bin/env python3
"""Skill evaluation and regression test suite for system-diagnostics.

Validates that SKILL.md adheres to /skill-creator standards and satisfies
all evaluation scenario expectations without regressions.
Zero external dependencies; standard library Python 3.10+ only.
"""

from __future__ import annotations

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

    if "3-tier" in exp_lower or "diagnose.py all" in exp_lower:
        has_all = bool(re.search(r"diagnose\.py\s+all|3-tier", text, re.I))
        return has_all, f"Unified 3-tier / diagnose.py all: {has_all}"

    if "axiom 9" in exp_lower or "honest verification" in exp_lower:
        has_a9 = bool(re.search(r"axiom\s*9|honest verification|verified|unverified|skipped", text, re.I))
        return has_a9, f"Axiom 9 reporting: {has_a9}"

    if "auto-probe" in exp_lower or "auto-detect" in exp_lower:
        has_probe = bool(re.search(r"auto-probe|auto-detect|ports?|8000|3000", text, re.I))
        return has_probe, f"Auto-probing: {has_probe}"

    if "strict" in exp_lower:
        has_strict = bool(re.search(r"--strict", text, re.I))
        return has_strict, f"--strict option: {has_strict}"

    if "diagnose.py ui" in exp_lower or "cdp" in exp_lower:
        has_ui = bool(re.search(r"diagnose\.py\s+ui|cdp", text, re.I))
        return has_ui, f"diagnose.py ui / CDP: {has_ui}"

    if "--live" in exp_lower or "devtoolsactiveport" in exp_lower:
        has_live = bool(re.search(r"--live|devtoolsactiveport|visible", text, re.I))
        return has_live, f"--live flag: {has_live}"

    if "audit-layout" in exp_lower or "bounding box" in exp_lower or "overflow" in exp_lower:
        has_audit = bool(re.search(r"--audit-layout|bounding box|overflow|domrect", text, re.I))
        return has_audit, f"--audit-layout: {has_audit}"

    if "headless" in exp_lower:
        has_headless = bool(re.search(r"--headless", text, re.I))
        return has_headless, f"--headless: {has_headless}"

    if "diagnose.py container" in exp_lower or "docker stats" in exp_lower:
        has_cnt = bool(re.search(r"diagnose\.py\s+container|docker stats|docker top", text, re.I))
        return has_cnt, f"Container audit: {has_cnt}"

    if "sync-check" in exp_lower or "md5" in exp_lower:
        has_sync = bool(re.search(r"--sync-check|md5", text, re.I))
        return has_sync, f"Sync check: {has_sync}"

    if "traceback" in exp_lower or "--lines" in exp_lower or "exception" in exp_lower:
        has_trace = bool(re.search(r"--lines|traceback|exception", text, re.I))
        return has_trace, f"Traceback scan: {has_trace}"

    if "diagnose.py surface" in exp_lower or "html element id" in exp_lower:
        has_surf = bool(re.search(r"diagnose\.py\s+surface|html element ids?", text, re.I))
        return has_surf, f"Surface scanning: {has_surf}"

    if "window.*" in exp_lower or "global" in exp_lower:
        has_glob = bool(re.search(r"window\.\*|global", text, re.I))
        return has_glob, f"Window globals: {has_glob}"

    if "backend" in exp_lower and "route" in exp_lower:
        has_routes = bool(re.search(r"routes?|@app\.", text, re.I))
        return has_routes, f"Backend routes: {has_routes}"

    if "!important" in exp_lower:
        has_imp = bool(re.search(r"!important", text, re.I))
        return has_imp, f"!important count: {has_imp}"

    if "diagnose.py tests" in exp_lower or "virtualenv" in exp_lower or ".venv" in exp_lower:
        has_test = bool(re.search(r"diagnose\.py\s+tests|virtualenv|\.venv", text, re.I))
        return has_test, f"Virtualenv test runner: {has_test}"

    # Generic keyword match
    words = [w for w in re.findall(r"\b[a-zA-Z_]{4,}\b", exp_lower) if w not in {"with", "that", "from", "this", "then", "have"}]
    found_cnt = sum(1 for w in words if w in text.lower())
    passed = (found_cnt / max(len(words), 1)) >= 0.4
    return passed, f"Generic keywords: {found_cnt}/{len(words)}"


class TestSystemDiagnosticsEvals(unittest.TestCase):
    """Test suite ensuring SKILL.md meets all evaluation requirements."""

    @classmethod
    def setUpClass(cls):
        cls.assertTrue(EVALS_FILE.exists(), f"Missing evals file at {EVALS_FILE}")
        cls.assertTrue(SKILL_MD.exists(), f"Missing SKILL.md at {SKILL_MD}")

        with open(EVALS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            cls.evals = data.get("evals", [])

        cls.skill_text = SKILL_MD.read_text(encoding="utf-8")

    def test_evals_json_structure(self):
        """Verify evals.json contains valid evaluation scenarios."""
        self.assertGreaterEqual(len(self.evals), 5)
        for e in self.evals:
            self.assertIn("id", e)
            self.assertIn("prompt", e)
            self.assertIn("expected_output", e)
            self.assertGreaterEqual(len(e.get("expectations", [])), 3)

    def test_skill_satisfies_all_eval_expectations(self):
        """Assert current SKILL.md satisfies 100% of expectations across all scenarios."""
        failures = []
        for e in self.evals:
            eid = e["id"]
            for exp in e.get("expectations", []):
                passed, reason = evaluate_expectation(self.skill_text, exp)
                if not passed:
                    failures.append(f"Eval {eid}: '{exp}' failed ({reason})")

        self.assertEqual(len(failures), 0, "Regressions found in SKILL.md:\n" + "\n".join(failures))

    def test_line_count_modularity_budget(self):
        """Assert SKILL.md is under the 350-line target (500 hard ceiling)."""
        lines = len(self.skill_text.splitlines())
        self.assertLessEqual(lines, 350, f"SKILL.md exceeds 350-line soft ceiling: {lines} lines")


if __name__ == "__main__":
    unittest.main()
