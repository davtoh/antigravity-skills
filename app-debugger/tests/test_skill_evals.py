#!/usr/bin/env python3
"""Skill evaluation and regression test suite for app-debugger.

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

    # 1. Specific multi-token gating / routing checks
    if "skip" in exp_lower and "ask_question" in exp_lower:
        has_skip = bool(re.search(r"skip.*ask_question|specified.*skip", text, re.I))
        return has_skip, f"Skip ask_question when specified: {has_skip}"

    if "yield" in exp_lower and ("frontier-architect" in exp_lower or "floor" in exp_lower):
        has_yd = bool(re.search(r"yield.*frontier-architect|yield the floor", text, re.I))
        return has_yd, f"Yield floor to frontier-architect: {has_yd}"

    if "tool-call ceiling" in exp_lower or "<= 3-5" in exp_lower:
        has_tc = bool(re.search(r"tool-call ceiling|3 to 5|3–5", text, re.I))
        return has_tc, f"Tool-call ceiling: {has_tc}"

    if "co-invocation" in exp_lower or "multi-skill" in exp_lower:
        has_ci = bool(re.search(r"co-invocation|separation of concerns|frontier-architect", text, re.I))
        return has_ci, f"Co-invocation protocol: {has_ci}"

    # 2. Specific diagnostic flags and parameters
    if "--sync-check" in exp_lower or "md5" in exp_lower or "code drift" in exp_lower:
        has_sync = bool(re.search(r"--sync-check|md5", text, re.I)) and bool(re.search(r"reproduce first|empirical", text, re.I))
        return has_sync, f"Container sync check / drift diagnosis: {has_sync}"

    if "surface" in exp_lower or "--show-ids" in exp_lower:
        has_surf = bool(re.search(r"surface|--show-ids", text, re.I))
        return has_surf, f"Surface scanning: {has_surf}"

    if "--wait" in exp_lower or "resting offset" in exp_lower or "scroll-snap" in exp_lower or "resting gap" in exp_lower:
        has_ro = bool(re.search(r"--wait|resting offset|scroll-snap", text, re.I))
        return has_ro, f"--wait / resting offset / scroll-snap: {has_ro}"

    if "--live" in exp_lower or "--audit-layout" in exp_lower or "cdp" in exp_lower:
        has_live = bool(re.search(r"--live|--audit-layout|cdp", text, re.I))
        return has_live, f"--live / --audit-layout: {has_live}"

    if "traceback" in exp_lower or "--lines" in exp_lower:
        has_trace = bool(re.search(r"--lines|traceback|exception", text, re.I))
        return has_trace, f"Traceback scan: {has_trace}"

    if "skips exploratory ux interviews" in exp_lower:
        ok = bool(re.search(r"skip ux interviews", text, re.I)) and bool(re.search(r"red", text, re.I))
        return ok, f"Skip UX interviews on quarantined defect: {ok}"

    if "suggested_fix" in exp_lower:
        ok = bool(re.search(r"suggested_fix", text)) and bool(re.search(r"surgical", text, re.I))
        return ok, f"Surgical fix guided by suggested_fix: {ok}"

    if "followup_cids" in exp_lower and "before transcript-audit" in exp_lower:
        ok = bool(re.search(r"followup_cids", text)) and bool(re.search(r"never run `transcript-audit`.*before.*`debug-retro`", text, re.I))
        return ok, f"Exact order debug-retro --plan before transcript-audit: {ok}"

    if "probe" in exp_lower or "scaffold" in exp_lower:
        has_probe = bool(re.search(r"probe (?:run|list|new|save)|domain probe|scaffold-defect", text, re.I))
        return has_probe, f"Dynamic domain probe / scaffold: {has_probe}"

    if "run_diagnose.py tests" in exp_lower and "180s" in exp_lower:
        ok = bool(re.search(r"run_diagnose\.py\s+tests\s+tests\.test_mod1", text)) and bool(re.search(r"180s\s+--timeout", text))
        return ok, f"Targeted module runs with 180s --timeout: {ok}"

    if "tests" in exp_lower or "unit test" in exp_lower:
        has_test = bool(re.search(r"tests|unit test|regressions", text, re.I))
        return has_test, f"Test suite execution: {has_test}"

    # 3. Hardware & Environment Routing
    if "hardware & device diagnostic routing" in exp_lower or ("hardware" in exp_lower and "routing" in exp_lower):
        has_hr = bool(re.search(r"hardware.*diagnostic routing|directshow.*lock|camera_hardware", text, re.I))
        return has_hr, f"Hardware diagnostic routing: {has_hr}"

    if "virtualenv auto-detection" in exp_lower or ("virtualenv" in exp_lower and "auto-detect" in exp_lower):
        has_va = bool(re.search(r"virtualenv auto-detection|\.venv", text, re.I))
        return has_va, f"Virtualenv auto-detection: {has_va}"

    # 4. Dev Server and Workflow Safety
    if "file watcher" in exp_lower or "auto-reloader" in exp_lower or "dev server" in exp_lower:
        has_fw = bool(re.search(r"dev server|file watcher|auto-reloader|statreload", text, re.I))
        return has_fw, f"File watcher / dev server safety: {has_fw}"

    if "single-pass" in exp_lower or "batch" in exp_lower:
        has_sp = bool(re.search(r"single-pass|atomic|batch", text, re.I))
        return has_sp, f"Single-pass atomic edits: {has_sp}"

    if "headless sandbox" in exp_lower or ("headless" in exp_lower and "permission" in exp_lower):
        has_hl = bool(re.search(r"headless|permission", text, re.I))
        return has_hl, f"Headless sandbox / permission: {has_hl}"

    if "reactive task discipline" in exp_lower or "manage_task" in exp_lower or "polling" in exp_lower:
        has_rt = bool(re.search(r"reactive task discipline|manage_task|polling", text, re.I))
        return has_rt, f"Reactive task discipline: {has_rt}"

    if "line ending" in exp_lower or "crlf" in exp_lower:
        has_le = bool(re.search(r"line ending|crlf|autocrlf", text, re.I))
        return has_le, f"Line ending discipline: {has_le}"

    if "disposable scratch" in exp_lower:
        has_ds = bool(re.search(r"disposable.*scratch|scratch/.*mismatch", text, re.I))
        return has_ds, f"Avoid disposable scratch scripts: {has_ds}"

    # 5. Core Workflow Steps & Output Patterns
    if "introspective options" in exp_lower:
        has_io = (
            bool(re.search(r"introspective options", text, re.I))
            and bool(re.search(r"transcript-audit", text, re.I))
            and bool(re.search(r"digest", text, re.I))
            and bool(re.search(r"/learn", text, re.I))
        )
        return has_io, f"Introspective Options hint: {has_io}"

    if "dual output" in exp_lower or "markdown artifact" in exp_lower or "inline" in exp_lower or "artifact creation overhead" in exp_lower:
        has_dual = bool(re.search(r"dual output|inline markdown|no artifact overhead", text, re.I))
        return has_dual, f"Dual output rules: {has_dual}"

    if "4-step workflow" in exp_lower or "5-step" in exp_lower or "workflow" in exp_lower:
        has_wf = bool(re.search(r"(?:4|5)-step.*workflow|step 1.*step 2.*step 3.*step 4", text, re.I | re.DOTALL))
        return has_wf, f"Workflow step structure: {has_wf}"

    if "symptom-to-root-cause matrix" in exp_lower or "symptom matrix" in exp_lower:
        has_mat = bool(re.search(r"symptom-to-root-cause matrix|symptom.*root cause", text, re.I))
        return has_mat, f"Symptom Matrix: {has_mat}"

    if "pre-flight gate" in exp_lower or "ask_question" in exp_lower:
        has_pf = bool(re.search(r"pre-flight.*gate|ask_question", text, re.I))
        return has_pf, f"Pre-Flight gate / ask_question: {has_pf}"

    if ".frontier/plans/<slug>/" in exp_lower or "mid-plan escalation" in exp_lower:
        ok = bool(re.search(r"\.frontier/plans/<slug>/", text)) and bool(re.search(r"--plan <slug>", text))
        return ok, f"Mid-Plan Escalation Bridge: {ok}"

    if "single clock-domain parity" in exp_lower or "now=100.0" in exp_lower:
        ok = bool(re.search(r"single clock-domain parity", text, re.I)) and bool(re.search(r"now=100\.0", text))
        return ok, f"Single clock-domain parity without synthetic stubs: {ok}"

    if "pending user-verification gate" in exp_lower or "changelog add" in exp_lower:
        ok = bool(re.search(r"pending user-verification gate", text, re.I)) and bool(re.search(r"diagnose\.py changelog add", text))
        return ok, f"Pending User-Verification Gate before changelog add: {ok}"

    if "reproduce first" in exp_lower or "empirical proof" in exp_lower or "run_diagnose.py" in exp_lower:
        has_rep = bool(re.search(r"reproduce first|empirical", text, re.I)) and bool(re.search(r"run_diagnose\.py", text, re.I))
        return has_rep, f"Reproduce first / empirical: {has_rep}"

    if "defensive" in exp_lower or "min-width: 0" in exp_lower or "overflow containment" in exp_lower:
        has_def = bool(re.search(r"defensive.*layout|min-width:\s*0|containment", text, re.I))
        return has_def, f"Defensive layout CSS: {has_def}"

    if "closed-loop" in exp_lower or "hasoverflow: false" in exp_lower:
        has_loop = bool(re.search(r"closed-loop|hasoverflow:\s*false", text, re.I))
        return has_loop, f"Closed-loop verification: {has_loop}"

    if "axiom 9" in exp_lower or "honest verification" in exp_lower:
        has_a9 = bool(re.search(r"axiom\s*9|honest verification|verified|unverified|skipped", text, re.I))
        return has_a9, f"Axiom 9 reporting: {has_a9}"

    if "mismatch" in exp_lower or "event listener" in exp_lower:
        has_mis = bool(re.search(r"event listener", text, re.I)) and bool(re.search(r"selector", text, re.I))
        return has_mis, f"Selector / ID mismatch: {has_mis}"

    if "modularity" in exp_lower or "surgical" in exp_lower:
        has_mod = bool(re.search(r"modularity|surgical|budget", text, re.I))
        return has_mod, f"Modularity / surgical edits: {has_mod}"

    if "debug-retro" in exp_lower and "20 steps" in exp_lower:
        ok = bool(re.search(r">=\s*20`?\s*steps", text, re.I)) and bool(re.search(r"debug-retro", text, re.I))
        return ok, f"debug-retro >= 20 steps threshold: {ok}"

    if "debug_retro.md" in exp_lower and "learn_queue.md" in exp_lower:
        ok = (
            bool(re.search(r"DEBUG_RETRO\.md", text))
            and bool(re.search(r"LEARNING_SCAFFOLD\.md", text))
            and bool(re.search(r"LEARN_QUEUE\.md", text))
        )
        return ok, f"DEBUG_RETRO.md folded into LEARNING_SCAFFOLD.md & LEARN_QUEUE.md: {ok}"

    if "test_*_e2e*.py" in exp_lower or "probe save" in exp_lower:
        ok = bool(re.search(r"test_\*_e2e\*\.py", text)) and bool(re.search(r"probe save", text, re.I))
        return ok, f"Promote CDP script to e2e test or probe save: {ok}"

    if "test-path" in exp_lower and "read_fail" in exp_lower:
        ok = bool(re.search(r"Test-Path\s+\.frontier/DEBUG_RETRO\.md", text)) and bool(re.search(r"read_fail", text))
        return ok, f"Check Test-Path before read_file on DEBUG_RETRO.md: {ok}"

    # Generic keyword match
    words = [w for w in re.findall(r"\b[a-zA-Z_]{4,}\b", exp_lower) if w not in {"with", "that", "from", "this", "then", "have"}]
    found_cnt = sum(1 for w in words if w in text.lower())
    passed = (found_cnt / max(len(words), 1)) >= 0.4
    return passed, f"Generic keywords: {found_cnt}/{len(words)}"

class TestAppDebuggerEvals(unittest.TestCase):
    """Test suite ensuring SKILL.md meets all evaluation and compliance requirements."""

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

    def test_evaluate_expectation_unit_positive_and_negative(self):
        """Verify evaluate_expectation correctly identifies matches and missing patterns."""
        mock_doc = "step 1 step 2 step 3 step 4. Skip ask_question. Yield floor to frontier-architect."
        passed_skip, _ = evaluate_expectation(mock_doc, "Skips ask_question when requested")
        self.assertTrue(passed_skip)

        passed_yield, _ = evaluate_expectation(mock_doc, "Yields floor to frontier-architect")
        self.assertTrue(passed_yield)

        failed_sync, _ = evaluate_expectation(mock_doc, "Executes run_diagnose.py container with --sync-check")
        self.assertFalse(failed_sync)

        failed_generic, _ = evaluate_expectation(mock_doc, "Unrelated obscure terminology missing completely")
        self.assertFalse(failed_generic)

    def test_eval_failure_recording(self):
        """Verify expectation failure collection format when regression occurs."""
        failures = []
        passed, reason = evaluate_expectation("minimal text", "Executes run_diagnose.py container with --sync-check")
        if not passed:
            failures.append(f"Eval 99: 'missing check' failed ({reason})")
        self.assertEqual(len(failures), 1)
        self.assertIn("Eval 99", failures[0])

    def test_zero_unmapped_generic_fallback_expectations(self):
        """Assert 100% of expectations in evals.json hit explicit discriminating rules rather than generic keyword ratio."""
        generic_hits = []
        for e in self.evals:
            for exp in e.get("expectations", []):
                _, reason = evaluate_expectation(self.skill_text, exp)
                if reason.startswith("Generic keywords:"):
                    generic_hits.append(f"Eval {e['id']}: '{exp}' ({reason})")
        self.assertEqual(generic_hits, [], "Unmapped expectations falling back to generic keywords:\n" + "\n".join(generic_hits))

    def test_reference_links_resolve(self):
        """Verify all relative reference links in SKILL.md resolve to existing files."""
        refs = re.findall(r"\(\./(references/[^)#\s]+)", self.skill_text)
        self.assertGreaterEqual(len(refs), 2)
        for rel in refs:
            self.assertTrue((SKILL_DIR / rel).is_file(), f"Broken reference link in SKILL.md: {rel}")

    def test_line_count_modularity_budget(self):
        """Assert SKILL.md is under the 350-line target (500 hard ceiling)."""
        lines = len(self.skill_text.splitlines())
        self.assertLessEqual(lines, 350, f"SKILL.md exceeds 350-line soft ceiling: {lines} lines")

    def test_sanitization_gate(self):
        """Verify committable SKILL.md has zero file-scheme URLs or OS user paths."""
        self.assertNotIn("file:" + "///", self.skill_text, "Forbidden file URI in SKILL.md")
        self.assertNotIn("C:\\" + "Users\\", self.skill_text, "Forbidden local absolute path in SKILL.md")
        self.assertNotIn("/" + "home/", self.skill_text, "Forbidden local absolute path in SKILL.md")

if __name__ == "__main__":
    unittest.main()
