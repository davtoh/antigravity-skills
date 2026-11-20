#!/usr/bin/env python3
"""Skill evaluation and regression test suite for system-diagnostics.

Validates that SKILL.md adheres to /skill-creator standards and satisfies
all evaluation scenario expectations without regressions.
Zero external dependencies; standard library Python 3.10+ only.
"""

import json
import re
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
EVALS_FILE = SKILL_DIR / "evals" / "evals.json"
SKILL_MD = SKILL_DIR / "SKILL.md"

# Ordered (trigger_terms_any, required_regexes_all, label)
_RULES: list[tuple[tuple[str, ...], tuple[str, ...], str]] = [
    (("3-tier", "diagnose.py all"), (r"diagnose\.py\s+all|3-tier",), "Unified 3-tier / diagnose.py all"),
    (("axiom 9", "honest verification"), (r"axiom\s*9|honest verification|verified|unverified|skipped",), "Axiom 9 reporting"),
    (("auto-probe", "auto-detect"), (r"auto-probe|auto-detect|ports?|8000|3000",), "Auto-probing"),
    (("strict",), (r"--strict",), "--strict option"),
    (("diagnose.py ui", "cdp"), (r"diagnose\.py\s+ui|cdp",), "diagnose.py ui / CDP"),
    (("--live", "devtoolsactiveport"), (r"--live|devtoolsactiveport|visible",), "--live flag"),
    (("audit-layout", "bounding box", "overflow"), (r"--audit-layout|bounding box|overflow|domrect",), "--audit-layout"),
    (("headless",), (r"--headless",), "--headless"),
    (("diagnose.py container", "docker stats"), (r"diagnose\.py\s+container|docker stats|docker top",), "Container audit"),
    (("sync-check", "md5"), (r"--sync-check|md5",), "Sync check"),
    (("traceback", "--lines", "exception"), (r"--lines|traceback|exception",), "Traceback scan"),
    (("diagnose.py surface", "html element id"), (r"diagnose\.py\s+surface|html element ids?",), "Surface scanning"),
    (("--verify", "cross-verify"), (r"--verify", r"--strict"), "Surface cross-contract --verify"),
    (("window.*", "global"), (r"window\.\*|global",), "Window globals"),
    (("!important",), (r"!important",), "!important count"),
    (("diagnose.py tests", "virtualenv", ".venv"), (r"diagnose\.py\s+tests|virtualenv|\.venv",), "Virtualenv test runner"),
    (("diagnose.py audit", "code smell audit"), (r"diagnose\.py\s+audit|static quality",), "Static quality audit"),
    (("import ladder", "--smells"), (r"import ladder|--smells|try\.\.\.except\s+importerror",), "Import ladder smells"),
    (("callable smoke", "--callable-smoke"), (r"--callable-smoke|callable smoke",), "Callable smoke tests"),
    (("top 5", "token budget"), (r"top\s*5|token-budget",), "Token budgeting / top 5"),
    (("transcript-audit",), (r"transcript-audit", r"--latest|--cids"), "transcript-audit command"),
    (("parallel same-file", "duplicate subagent"), (r"--json", r"parallel same-file|subagent duplicate"), "transcript-audit JSON metrics"),
    (("grade cap", "--brain-dir", "agy_brain_dir"), (r"grade cap", r"--brain-dir|AGY_BRAIN_DIR"), "transcript-audit grade caps & brain-dir"),
    (("--path src/", "multiple files or directories"), (r"diagnose\.py\s+scan", r"--path\s+<paths\.\.\.>|one or more files/directories"), "Multi-path scan --path"),
    (("--deep", "extended rules"), (r"--deep", r"--all"), "scan --deep / --all"),
    (("--prune",), (r"--prune", r"vanished|resolved"), "scan --prune"),
    (("diagnose.py scan",), (r"diagnose\.py\s+scan",), "Polyglot scan"),
    (("dual-key",), (r"dual-key|defect-xxx",), "Dual-key IDs"),
    (("single source of truth", "ssot"), (r"single source of truth|ssot|defect_catalog\.json",), "SSOT catalog"),
    (("scaffold-defect",), (r"scaffold-defect",), "Scaffold defect"),
    (("dual-track", "/app-debugger"), (r"dual-track|/app-debugger|frontier-architect",), "Dual-track remediation"),
    (("probe list",), (r"diagnose\.py\s+probe\s+list",), "probe list"),
    (("probe run camera_hardware",), (r"diagnose\.py\s+probe\s+run\s+camera_hardware",), "probe run camera_hardware"),
    (("probe new",), (r"diagnose\.py\s+probe\s+new",), "probe new"),
    (("probe save",), (r"diagnose\.py\s+probe\s+save",), "probe save"),
    (("changelog add",), (r"diagnose\.py\s+changelog\s+add", r"--title"), "changelog add"),
    (("150 lines", ".changelogs/"), (r"150", r"\.changelogs/"), "changelog 150-line cap & sharding"),
    (("changelog migrate",), (r"diagnose\.py\s+changelog\s+migrate",), "changelog migrate"),
    (("changelog show", "changelog status"), (r"changelog\s+show\s+--recent\s+3", r"changelog\s+status"), "changelog show/status"),
    (("resolve-defect",), (r"diagnose\.py\s+resolve-defect\s+--id", r"--note"), "resolve-defect"),
    (("dismiss-defect",), (r"diagnose\.py\s+dismiss-defect\s+--id", r"--reason"), "dismiss-defect"),
    (("--elevate",), (r"scaffold-defect\s+--id.*--elevate",), "scaffold-defect --elevate"),
    (("package-skill",), (r"diagnose\.py\s+package-skill",), "package-skill"),
    (("temp-stages", "ssot shims"), (r"temp-stage", r"ssot shims"), "temp-stage SSOT shims"),
    (("package_skill.py",), (r"package_skill\.py", r"tests/"), "package_skill.py strip tests"),
    (("--eval-file",), (r"--eval-file", r"quote-stripping"), "ui --eval-file"),
    (("--click", "--screenshot"), (r"--click", r"--screenshot"), "ui --click & --screenshot"),
    (("--no-fallback-headless",), (r"--no-fallback-headless",), "ui --no-fallback-headless"),
    (("--navigate", "--window-size"), (r"--navigate", r"--window-size"), "ui --navigate & --window-size"),
    (("arch-map",), (r"diagnose\.py\s+arch-map",), "arch-map"),
    (("--include-tests",), (r"--json", r"--full", r"--include-tests", r"--out"), "arch-map options"),
    (("diagnose.py run",), (r"diagnose\.py\s+run", r"zero-code runner"), "diagnose.py run"),
    (("diagnose.py traces", "--scaffold"), (r"diagnose\.py\s+traces",), "diagnose.py traces"),
    (("cmd /c npx",), (r"cmd\s+/c\s+npx\s+-y",), "cmd /c npx -y"),
    (("git grep",), (r"git grep -n",), "git grep -n"),
    (("crlf/lf",), (r"crlf/lf",), "CRLF/LF preservation"),
    (("--no-capture-runtime",), (r"--no-capture-runtime", r"--eval-file"), "ui --no-capture-runtime opt-out"),
    (("- redirect", "workflow/model"), (r"- REDIRECT", r"transcript-audit"), "transcript-audit - REDIRECT"),
    (("schedule-while-subagent",), (r"schedule-while-subagent", r"transcript-audit"), "transcript-audit schedule-while-subagent"),
    (("suggested_grade_cap",), (r"grade cap", r"transcript-audit"), "transcript-audit failure-based grade cap"),
    (("has_debug_retro",), (r"transcript-audit", r"debug-retro|unescalated thrash"), "transcript-audit has_debug_retro tracking"),
]


def evaluate_expectation(text: str, expectation: str) -> tuple[bool, str]:
    """Check if skill documentation provides concrete evidence for an expectation."""
    exp_lower = expectation.lower()
    if "backend" in exp_lower and "route" in exp_lower:
        ok = bool(re.search(r"routes?|@app\.", text, re.I))
        return ok, f"Backend routes: {ok}"
    for triggers, patterns, label in _RULES:
        if any(t in exp_lower for t in triggers):
            ok = all(bool(re.search(p, text, re.I)) for p in patterns)
            return ok, f"{label}: {ok}"
    words = [w for w in re.findall(r"\b[a-zA-Z_]{4,}\b", exp_lower) if w not in {"with", "that", "from", "this", "then", "have"}]
    found = sum(1 for w in words if w in text.lower())
    return (found / max(len(words), 1)) >= 0.4, f"Generic keywords: {found}/{len(words)}"


class TestSystemDiagnosticsEvals(unittest.TestCase):
    """Test suite ensuring SKILL.md meets all evaluation requirements."""

    @classmethod
    def setUpClass(cls):
        cls.assertTrue(EVALS_FILE.exists(), f"Missing evals file at {EVALS_FILE}")
        cls.assertTrue(SKILL_MD.exists(), f"Missing SKILL.md at {SKILL_MD}")
        with open(EVALS_FILE, "r", encoding="utf-8") as f:
            cls.evals = json.load(f).get("evals", [])
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
        failures = [
            f"Eval {e['id']}: '{exp}' failed ({reason})"
            for e in self.evals
            for exp in e.get("expectations", [])
            for ok, reason in (evaluate_expectation(self.skill_text, exp),)
            if not ok
        ]
        self.assertEqual(len(failures), 0, "Regressions found in SKILL.md:\n" + "\n".join(failures))

    def test_line_count_modularity_budget(self):
        """Assert SKILL.md is under the 350-line target (500 hard ceiling)."""
        lines = len(self.skill_text.splitlines())
        self.assertLessEqual(lines, 350, f"SKILL.md exceeds 350-line soft ceiling: {lines} lines")


if __name__ == "__main__":
    unittest.main()
