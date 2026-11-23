#!/usr/bin/env python3
"""Skill evaluation and regression test suite for refactor-monolith.

Validates that SKILL.md adheres to /skill-creator standards, satisfies
all evaluation scenario expectations without regressions, resolves all
reference links and anchors, and passes pre-commit sanitization gates.
Zero external dependencies; standard library Python 3.10+ only.
"""

import json
import re
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
EVALS_FILE = SKILL_DIR / "evals" / "evals.json"
SKILL_MD = SKILL_DIR / "SKILL.md"

_RULES: list[tuple[tuple[str, ...], tuple[str, ...], str]] = [
    (("mode a", "single-file"), (r"mode a", r"single[-_]file"), "Mode A / Single-file"),
    (("targeted slicing", "normalize-eol --path <active_slice>"), (r"verify --path <target_slice> --strict", r"normalize-eol --path <active_slice> --to lf"), "Targeted Slicing verify & normalize-eol"),
    (("opportunistic slice formatting", "verify --format"), (r"contract_snapshot\.py\"?\s+format --files", r"--format"), "Opportunistic slice formatting"),
    (("safe deprecated script facades", "lazy __getattr__"), (r"safe deprecated script facades", r"try\.\.\.except importerror", r"__getattr__"), "Safe Deprecated Script Facades"),
    (("in-flight tool elevation protocol", "changelog add"), (r"diagnose\.py changelog add", r"in-flight tool elevation protocol"), "Changelog add & In-Flight Tool Elevation"),
    (("persists a 4-phase", "initializes .refactor/state.json"), (r"\.refactor/plan\.md", r"\.refactor/state\.json"), "Persist .refactor/plan.md & state.json"),
    (("reads .refactor/state.json", "next pending"), (r"\.refactor/state\.json", r"\.refactor/plan\.md", r"next pending `\[ \]` milestone"), "Auto-resume from .refactor/state.json & plan.md"),
    (("checkpoints and advances campaign state",), (r"code_health_audit\.py", r"checkpoint/advance state"), "Verify and checkpoint/advance state"),
    (("designs a layered target directory structure",), (r"level 0 models/utils -> level 1 repositories -> level 2 services -> level 3 routers/ui -> level 4 facade",), "Layered target DAG directory structure"),
    (("updates agents.md with a monolith freeze",), (r"agents\.md", r"monolith freeze"), "AGENTS.md Monolith Freeze"),
    (("honors the user-specified planner",), (r"user-specified planner \(`/plan`",), "Honor user-specified planner"),
    (("hot/cold split", "tight per-frame"), (r"hot/cold split", r"memory locality"), "Hot/Cold split performance guard"),
    (("anti-thrash", "stop-loss"), (r"anti-thrash stop-loss", r"/plan` or `/grill-me"), "Anti-thrash stop-loss & escalation"),
    (("vendor/minified", "static/scss/theme/"), (r"vendor/minified", r"static/scss/theme/"), "Exclude vendor & check upstream SCSS"),
    (("100% self-contained",), (r"100% self-contained", r"agents\.md"), "Self-contained & AGENTS.md"),
    (("multi-language structural modes", "language-playbooks.md"), (r"ast, brace, stylesheet, fallback", r"references/language-playbooks\.md", r"itcss"), "Multi-language structural modes & playbooks"),
    (("best working version", "unknown language"), (r"best working version", r"parser: fallback"), "Unknown language & Best Working Version bailout"),
    (("mode c", "contract_snapshot.py diagnose"), (r"mode c", r"contract_snapshot\.py\"?\s+diagnose"), "Mode C / contract_snapshot.py diagnose"),
    (("tier 1 ast and dom contracts against baseline.json",), (r"\.refactor/baseline\.json", r"ast/dom contracts"), "Tier 1 AST/DOM contract check vs baseline.json"),
    (("tier 2 container sync and tier 3 headless cdp",), (r"audit-container", r"verify-ui"), "Tier 2 container sync & Tier 3 CDP layout"),
    (("infinite reload traps",), (r"infinite reload traps", r"window\.\*"), "Infinite reload guard"),
    (("axiom 9",), (r"axiom 9", r"tier 1: verified"), "Axiom 9 3-tier verification reporting"),
    (("windows crlf", "normalize-eol or patch"), (r"crlf", r"normalize-eol", r"patch"), "Windows CRLF normalize-eol / patch"),
    (("inject-scripts",), (r"inject-scripts",), "inject-scripts"),
    (("turn ceiling gate",), (r"turn ceiling gate", r"20[–-]25"), "Turn Ceiling Gate"),
    (("state --checkpoint",), (r"state --checkpoint",), "Campaign state --checkpoint"),
    (("fresh session with /refactor-monolith continue",), (r"/refactor-monolith continue` in a fresh chat",), "Advise /refactor-monolith continue in fresh chat"),
    (("run-tests", "--runner pytest"), (r"run-tests", r"--runner pytest"), "contract_snapshot.py run-tests pytest"),
    (("passes test runner flags (-k, -v, -p)",), (r"forwards -k, -v, -p cleanly",), "Transparently forwards -k, -v, -p flags"),
    (("polling manage_task status", "time.sleep"), (r"manage_task\(action='status'\)", r"time\.sleep", r"start-sleep"), "Reactive turn-yield no polling/sleep"),
    (("git status --short",), (r"git status --short", r"pathspec errors"), "Defensive git status --short"),
    (("refactoring invariant", "behavior preservation"), (r"refactoring invariant", r"behavior preservation"), "Refactoring Invariant behavior preservation"),
    (("state --record-defect", "defect_catalog.json"), (r"state --record-defect", r"\.diagnostics/defect_catalog\.json"), "Quarantine via state --record-defect"),
    (("zero plan.md drift", "defect_catalog.md"), (r"\.diagnostics/defect_catalog\.md", r"zero `plan\.md` table drift"), "Zero plan.md drift single link"),
    (("summarizes quarantined defects", "scaffold-defect"), (r"diagnose\.py scaffold-defect", r"/app-debugger", r"/frontier-architect"), "Quarantined defect handoff commands"),
    (("selects mode b", "project_campaign"), (r"mode b1 \(`project_campaign`", r"code_health_audit\.py"), "Mode B PROJECT_CAMPAIGN selection"),
    (("5-step zero-regression decomposition",), (r"5-step zero-regression decomposition workflow",), "5-Step Zero-Regression Decomposition Workflow"),
    (("code_health_audit.py",), (r"code_health_audit\.py",), "code_health_audit.py usage"),
    (("zero breaking imports", "backward-compatible imports"), (r"re-export", r"facade"), "Backward-compatible facade re-exports"),
    (("quantitative modularity budget",), (r"350 sloc", r"500 sloc", r"10 methods", r"12 methods"), "Quantitative modularity budgets"),
    (("preserves existing docstrings",), (r"preserve docstrings, rationale comments, and mathematical algorithms verbatim",), "Preserve docstrings and comments"),
]


def evaluate_expectation(text: str, expectation: str) -> tuple[bool, str]:
    """Check if skill documentation provides concrete evidence for an expectation."""
    exp_lower = expectation.lower()
    for triggers, patterns, label in _RULES:
        if any(t in exp_lower for t in triggers):
            ok = all(bool(re.search(p, text, re.I)) for p in patterns)
            return ok, f"{label}: {ok}"

    words = [w for w in re.findall(r"\b[a-zA-Z_]{4,}\b", exp_lower) if w not in {"with", "that", "from", "this", "then", "have"}]
    found_cnt = sum(1 for w in words if w in text.lower())
    passed = (found_cnt / max(len(words), 1)) >= 0.4
    return passed, f"Generic keywords: {found_cnt}/{len(words)}"


def _heading_to_anchor(heading: str) -> str:
    """Convert a GitHub Markdown heading line to its #anchor slug."""
    raw = re.sub(r"^#+\s*", "", heading.strip()).lower()
    cleaned = re.sub(r"[^\w\s\-]", "", raw)
    return re.sub(r"[ ]", "-", cleaned)


class TestRefactorMonolithSkillEvals(unittest.TestCase):
    """Test suite ensuring SKILL.md meets all evaluation requirements."""

    @classmethod
    def setUpClass(cls):
        cls.assertTrue(EVALS_FILE.exists(), f"Missing evals file at {EVALS_FILE}")
        cls.assertTrue(SKILL_MD.exists(), f"Missing SKILL.md at {SKILL_MD}")

        with open(EVALS_FILE, "r", encoding="utf-8") as f:
            cls.evals_data = json.load(f)
        cls.evals = cls.evals_data.get("evals", [])
        cls.skill_text = SKILL_MD.read_text(encoding="utf-8")

    def test_evals_json_structure(self):
        """Verify evals.json contains valid evaluation scenarios."""
        self.assertGreaterEqual(len(self.evals), 10)
        for e in self.evals:
            self.assertIn("id", e)
            self.assertIn("prompt", e)
            self.assertIn("expected_output", e)
            self.assertGreaterEqual(len(e.get("expectations", [])), 4)

    def test_all_evaluation_expectations(self):
        """Iterate over all evaluation scenarios and assert SKILL.md satisfies each expectation."""
        failures = []
        for eval_case in self.evals:
            eid = eval_case.get("id")
            for exp in eval_case.get("expectations", []):
                passed, reason = evaluate_expectation(self.skill_text, exp)
                if not passed:
                    failures.append(f"Eval {eid}: '{exp}' failed ({reason})")

        self.assertEqual(len(failures), 0, "Regressions found in SKILL.md:\n" + "\n".join(failures))

    def test_zero_unmapped_generic_fallback_expectations(self):
        """Assert 100% of expectations in evals.json match explicit rules rather than generic keyword fallback."""
        generic_hits = [
            f"Eval {e['id']}: '{exp}' ({reason})"
            for e in self.evals
            for exp in e.get("expectations", [])
            for _, reason in (evaluate_expectation(self.skill_text, exp),)
            if reason.startswith("Generic keywords:")
        ]
        self.assertEqual(generic_hits, [], "Unmapped expectations falling back to generic keywords:\n" + "\n".join(generic_hits))

    def test_reference_links_and_toc_anchors(self):
        """Verify all relative reference links in SKILL.md and internal TOC anchors in references/*.md resolve."""
        refs = re.findall(r"\(\./(references/[^)#\s]+)", self.skill_text)
        self.assertGreaterEqual(len(refs), 3)
        for rel in refs:
            ref_path = SKILL_DIR / rel
            self.assertTrue(ref_path.is_file(), f"Broken reference link in SKILL.md: {rel}")
            ref_text = ref_path.read_text(encoding="utf-8")
            headings = {_heading_to_anchor(line) for line in ref_text.splitlines() if line.startswith("#")}
            for anchor in re.findall(r"\]\(#([^)]+)\)", ref_text):
                self.assertIn(anchor, headings, f"Broken TOC anchor #{anchor} in {rel}")

    def test_evaluate_expectation_unit_positive_and_negative(self):
        """Verify evaluate_expectation correctly identifies matches and missing patterns."""
        mock_doc = "Mode A SINGLE_FILE. code_health_audit.py. re-export facade."
        self.assertTrue(evaluate_expectation(mock_doc, "Routes to Mode A (Single-File Fast-Track)")[0])
        self.assertFalse(evaluate_expectation(mock_doc, "Enforces the Turn Ceiling Gate")[0])

    def test_line_count_ceiling(self):
        """Assert SKILL.md is under the 350-line soft ceiling (500 hard ceiling)."""
        lines = len(self.skill_text.splitlines())
        self.assertLessEqual(lines, 350, f"SKILL.md exceeds 350-line soft ceiling: {lines} lines")

    def test_sanitization_gate(self):
        """Verify committable SKILL.md has zero file-scheme URLs or OS user paths."""
        self.assertNotIn("file:" + "///", self.skill_text, "Forbidden file URI in SKILL.md")
        self.assertNotIn("C:\\" + "Users\\", self.skill_text, "Forbidden local absolute path in SKILL.md")
        self.assertNotIn("/" + "home/", self.skill_text, "Forbidden local absolute path in SKILL.md")


if __name__ == "__main__":
    unittest.main()
