#!/usr/bin/env python3
"""
Portable regression and eval test suite for Frontier Architect.
Validates evals.json schema and asserts that SKILL.md satisfies all
expectations across all evaluation scenarios without regressions.

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

# Ordered (trigger_terms_any, required_regexes_all, label)
_RULES: list[tuple[tuple[str, ...], tuple[str, ...], str]] = [
    (("scripts/py.sh", "scripts/py.cmd"), (r"scripts/py\.sh", r"py\.cmd", r"3\.10\+"), "Cross-OS Python 3.10+ launcher"),
    (("checks $virtual_env first", "preserves script exit codes"), (r"VIRTUAL_ENV", r"preserves exit codes"), "Launcher VIRTUAL_ENV & exit code preservation"),
    (("retrospective-recipe.md precedence",), (r"retrospective-recipe\.md", r"RETROSPECTIVE_RECIPE", r"CLAUDECODE=1"), "Retrospective recipe router precedence"),
    (("learning_proposal*.md", "before editing skills"), (r"learning_proposal", r"no edits to skills"), "Retrospective proposal-only before decision"),
    (("tool-call ceiling", "<= 3-5"), (r"tool-call ceiling|3 to 5|3–5",), "Tool-call ceiling"),
    (("user override", "axiom 10"), (r"axiom 10|user override|just do it|skip the plan|no questions",), "Axiom 10 User Overrides"),
    (("working assumption", "states working assumption"), (r"state the assumptions|write the assumptions|assumptions in one or two lines|assumptions at the top|working assumptions",), "State assumptions"),
    (("bucket a fix grows",), (r"bucket a that grows", r"re-triage"), "Bucket A growth re-triage"),
    (("bucket a",), (r"bucket a|lean|minimal edit",), "Bucket A lean handling"),
    (("no interactive user", "unattended"), (r"subagent|unattended|no interactive user|assumptions",), "Unattended handling"),
    (("pre-flight pause protocol",), (r"pre-flight pause|allow banner|remote debugging|probe",), "Pre-flight pause protocol"),
    (("minimal, scoped edit",), (r"formatcurrency|targeted|minimal",), "Scoped edit recognized"),
    (("destructive actions",), (r"no reset --hard|avoid destructive|branch|non-destructive",), "Safe git boundary"),
    (("single source of truth", "ssot", "re-export", "facade"), (r"single source of truth|ssot|re-export|facade|zombie",), "SSOT / Zombie facade prevention"),
    (("duplicate domain logic", "delegating legacy"), (r"duplicate domain logic|unify duplicate|delegation",), "Duplicate logic unification"),
    (("modularity budget", "350-line"), (r"modularity|350 lines|500 lines|method budget",), "Modularity budget"),
    (("mega-turn", "1-phase-per-turn"), (r"1-phase-per-turn|phase 1 only|scope immediate|mega-turn",), "1-Phase-Per-Turn gate"),
    (("deferred",), (r"deferred|subsequent turn|next milestone",), "Deferred phase boundary"),
    (("symptom-to-root-cause",), (r"symptom-to-root-cause|root cause|matrix",), "Symptom to root cause matrix"),
    (("axiom 9", "honest reporting", "honest verification reporting"), (r"axiom 9|honest reporting|unverified|honest verification",), "Axiom 9 Honest Reporting"),
    (("docker_audit",), (r"docker_audit\.py|docker stats|docker top",), "Docker audit present"),
    (("cdp_inspect", "cdp inspection"), (r"cdp_inspect\.py|bounding box|domrect|chrome devtools",), "CDP inspector present"),
    (("plan-first", "/plan"), (r"plan-first|implementation plan|requestfeedback|/plan",), "Plan-first indicators"),
    (("agents.md",), (r"agents\.md|\.agents/rules",), "AGENTS.md presence"),
    (("closed-loop", "verification matrix"), (r"verification|closed-loop|matrix|async|waitmsbeforeasync",), "Closed-loop matrix"),
    (("reproduce-first", "phase 1b", "triag"), (r"phase 1b|reproduce-first|diagnostic|triage",), "Reproduce-first triage"),
    (("socratic", "ask_question"), (r"ask_question|socratic|interview|clarification",), "Socratic question protocol"),
    (("self-contained", "non-bundled"), (r"self-contained|standalone|invariant",), "Self-containment verified"),
    (("multi-skill co-invocation", "orchestrator of intent"), (r"multi-skill co-invocation|orchestrator of intent|app-debugger",), "Co-invocation protocol"),
    (("dual-track", ".frontier/state.json"), (r"dual-track|\.frontier/state\.json|zero.*token.*plan_engine",), "Dual-track state synchronization"),
    (("plan_engine.py advance", "checklist patching"), (r"plan_engine\.py advance|patch checkboxes|advance milestone",), "Milestone advance and checklist patch"),
    (("status and lookup", "progress bar"), (r"status|lookup|progress bar",), "Status and lookup commands"),
    (("pre-flight critic gate", "critic gate"), (r"pre-flight critic gate|critic gate|public surface invariants",), "Pre-Flight Critic Gate"),
    (("anti-thrash stop-loss", "stop-loss"), (r"anti-thrash stop-loss|stop-loss|two fix attempts|2 attempts",), "Anti-Thrash Stop-Loss"),
    (("4-dimensional retrospective", "retrospective telemetry"), (r"4-dimensional retrospective|token efficiency grade|tri|retrospective",), "4-Dimensional Retrospective"),
    (("introspective options",), (r"introspective options", r"transcript-audit", r"digest", r"/learn"), "Introspective Options block"),
    (("--skill-learn", "--tool-gap"), (r"--skill-learn", r"--tool-gap"), "--skill-learn / --tool-gap flags"),
    (("transcript-audit",), (r"transcript-audit", r"--steps|--retries"), "transcript-audit deterministic telemetry"),
    (("master roadmap", "--parent <master_slug>"), (r"master roadmap", r"--parent\s+<master_slug>\s+--milestone\s+1"), "Master Roadmap & Step 1 child plan"),
    (("master step pre-plan gate",), (r"master step pre-plan gate", r"arch-map"), "MASTER STEP PRE-PLAN GATE"),
    (("runtime wiring mandate",), (r"runtime wiring mandate", r"PipelineEngine|CameraPool"), "Master-Step Runtime Wiring Mandate"),
    (("improvement intent",), (r"improvement intent", r"deepen and detail"), "Improvement Intent deepen & detail"),
    (("zero-plan-re-read gate",), (r"zero-plan-re-read gate", r"cli-cheatsheet\.md"), "Zero-Plan-Re-Read Gate"),
    (("enter_plan_mode",), (r"enter_plan_mode", r"requestfeedback:\s*true"), "No enter_plan_mode on continue"),
    (("wakeup race", "system_message"), (r"wakeup race", r"SYSTEM_MESSAGE"), "Wakeup race prevention"),
    (("transcript.jsonl", "manage_subagents"), (r"transcript\.jsonl", r"manage_subagents list"), "No transcript scraping or polling"),
    (("export-ready portable plan",), (r"export-ready portable plan contract", r"repo-relative"), "Export-Ready Portable Plan Contract"),
    (("scenario combinations matrix",), (r"scenario combinations matrix", r"os-agnostic"), "OS-agnostic & Scenario Combinations Matrix"),
    (("changelog task formulation", "migration_log.md"), (r"changelog task formulation invariant", r"MIGRATION_LOG\.md"), "Changelog Task Formulation Invariant"),
    (("--max-lines",), (r"plan budget calibration rule", r"--max-lines"), "Plan Budget Calibration Rule"),
    (("zero audit evasion",), (r"zero audit evasion", r"diagnose\.py.*audit"), "Zero Audit Evasion"),
    (("second-check verification gate",), (r"second-check verification gate", r"threading\.Timer"), "Second-Check Verification Gate"),
    (("lightweight test fixtures",), (r"lightweight test fixtures", r"synthetic mini-fixtures"), "Lightweight Test Fixtures"),
    (("turn-end daemon", "manage_task kill"), (r"mandatory turn-end daemon & task teardown", r"manage_task kill"), "Mandatory Turn-End Daemon & Task Teardown"),
    (("persistent state invariant",), (r"persistent state invariant", r"local storage"), "Persistent State Invariant"),
    (("smart commit hint gate",), (r"smart commit hint gate",), "Smart Commit Hint Gate"),
    (("in-flight tool elevation",), (r"in-flight tool elevation protocol", r"system-diagnostics/scripts/"), "In-Flight Tool Elevation Protocol"),
    (("read-only or review",), (r"read-only or review requests",), "Read-only review handling"),
    (("zero-dangling-question",), (r"zero-dangling-question invariant",), "Zero-Dangling-Question Invariant"),
    (("non-mocked", "unconfigured/empty/fallback"), (r"non-mocked branch gate", r"diagnose\.py scan --path \."), "Non-Mocked Branch Gate & scan"),
    (("git diff main...plan/",), (r"git diff main\.\.\.plan/<slug>", r"changelog add"), "Final sign-off diff & changelog"),
    (("/learn", "continuous learning"), (r"/learn|continuous learning",), "Continuous learning feed to /learn"),
    (("2-3 cohesive milestones", "40-70 steps"), (r"2[–-]3 cohesive milestones", r"40[–-]70 steps"), "Consolidated child plan sizing"),
    (("--no-sync-parent", "auto-advances linked parent"), (r"auto-advance any completed child plan", r"--no-sync-parent"), "Auto-sync parent milestone"),
    ((">60-step", "duplicate-read churn"), (r">60`-step", r"transcript-audit --latest 1"), ">60-step transcript-audit check"),
    (("single-agent hydrogen", "split mode"), (r"already-approved `\.TODO/` plans directly in single-agent `Hydrogen`", r"Plan/Execution split mode"), "Single-agent Hydrogen execution"),
    (("advance <master_slug>", "before next <master_slug>"), (r"plan_engine\.py advance <master_slug> --milestone <N>", r"next <master_slug>"), "Master advance before next"),
    (("near-limit files", "before editing"), (r"diagnose\.py audit --path <target_files>", r"near-limit files/classes"), "Pre-edit audit on near-limit files"),
    (("test_*_e2e*.py", "cdp e2e probes"), (r"tests/test_\*_e2e\*\.py", r"ephemeral `port=0`"), "Promote CDP E2E probe to permanent test"),
    (("before dispatching any plan_engine.py",), (r"cli-cheatsheet\.md.*before.*dispatching any `plan_engine\.py`",), "Zero-Plan-Re-Read Gate cli-cheatsheet before commands"),
    (("calls exit_plan_mode once",), (r"exit_plan_mode.*once.*never re-enter Plan Mode", r"Step 1 `\.TODO/` plan-file creation \+ `init` ONLY"), "IDE Plan Mode single exit_plan_mode handoff"),
    (("pending:<base_sha>",), (r"pending:<base_sha>", r"plan_engine\.py advance"), "Pending base SHA tracking on advance"),
    (("escalates to /app-debugger", "debug-retro --plan"), (r"diagnose\.py debug-retro --plan <slug>", r"--escalate \"<root_cause>\""), "Anti-thrash escalation to debug-retro"),
    (("single clock-domain parity",), (r"single clock-domain parity", r"time\.monotonic\(\).*time\.time\(\)"), "Single clock-domain parity check"),
    (("diagnose.py tests <modules...>", "180s --timeout"), (r"diagnose\.py\s+tests\s+<modules\.\.\.>", r"180s\s+`?--timeout`?"), "Targeted unittest routed via diagnose.py tests"),
    (("followup_cids", "transcript-audit --latest 1 last"), (r"followup_cids", r"transcript-audit --latest 1`?\s+last"), "debug-retro auto-records followup_cids and transcript-audit runs last"),
    (("subagent map-reduce", "30 components"), (r"subagent map-reduce", r"research"), "Subagent Map-Reduce discovery"),
    (("atomic vertical slices",), (r"contracts/types\s*→\s*core logic\s*→\s*state/service\s*→\s*ui layout\s*→\s*styling & polish",), "Atomic Vertical Slices sequence"),
    (("browser/visual ui verification", "web ui layer"), (r"browser inspection|cdp_inspect\.py|/browser",), "Browser/Visual UI verification"),
    (("model tier escalation", "useg1credits"), (r"model tiers", r"useG1Credits"), "Model Tier Escalation & Quota Strategy"),
    (("single riskiest assumption", "timeboxed spike"), (r"single riskiest assumption \(sra\)", r"scratch/"), "SPIKE De-risking SRA"),
    (("package-lock.json", "evidence-based handoff"), (r"verified", r"not verified", r"known risks"), "Evidence-based handoff & conflict safety"),
    (("new conversation (+)", "/compact"), (r"new conversation \(\+\)", r"/compact"), "New Conversation (+) or /compact hygiene"),
    (("public interface compatibility", "dual-maintenance"), (r"unify duplicate domain logic via delegation while preserving public interface compatibility",), "Preserve public interface compatibility"),
    (("plan_engine.py verify and plan_engine.py advance",), (r"plan_engine\.py verify", r"plan_engine\.py advance"), "Run plan_engine.py verify and advance"),
    (("plan_engine.py verify --timeout", "exit code 124"), (r"plan_engine\.py verify", r"--timeout 180", r"124"), "plan_engine.py verify --timeout 180 / exit 124"),
    (("streams live output during verify",), (r"plan_engine\.py verify`?\s+streams live",), "plan_engine.py verify live output streaming"),
    (("--timeout 600", "--timeout 0"), (r"--timeout 600", r"active progress"), "Re-run slow suites with --timeout 600 or 0"),
    (("deadlocks or blocking i/o",), (r"deadlocks/blocking i/o",), "Debug deadlocks or blocking I/O on no-progress timeout"),
    (("mixed requests",), (r"split empirical baseline \(`app-debugger`\)", r"phase 2/5"), "Mixed requests split cleanly"),
    (("surface baseline inventory", "public routes"), (r"document public routes/schemas/selectors upfront",), "Surface Baseline Inventory"),
    (("thousands separators", "unit test"), (r"pair every slice with tests", r"tactical"), "Unit test pairing for Bucket A"),
    (("targeted test command", "observed result honestly"), (r"only claim `\"verified\"` when you ran the check",), "Honest targeted test verification"),
    (("separate branch or leaves changes uncommitted",), (r"non-destructive & reversible", r"consent before hard-to-undo"), "Leave changes safe/uncommitted in unattended mode"),
    (("evidence-based handoff separating verified",), (r"evidence-based handoff separating `verified`, `not verified` \(`unverified`\), and known risks",), "Evidence-based handoff"),
    (("persistent checkpoint in agents.md",), (r"checkpoint summaries in `agents\.md`",), "Persistent checkpoint in AGENTS.md"),
    (("merging external cids", "--cids <all_cids>"), (r"plan_engine\.py digest <slug> --cids <all_cids> --backfill --write-scaffold",), "Merge external CIDs with digest --cids"),
    (("live browser: unverified", "cannot attach"), (r"live browser: unverified", r"axiom 9"), "Explicit Live Browser: UNVERIFIED status"),
    (("synthesizes the empirical symptom matrix",), (r"symptom-to-root-cause matrix", r"implementation plan"), "Synthesize Symptom Matrix into Implementation Plan"),
    (("extracted signal/helper adapter", "getattr stubs"), (r"frozen-monolith signal adapters", r"getattr"), "Frozen-Monolith Signal Adapters"),
    (("advance --note", "milestone completion summary note"), (r"plan_engine\.py\"?\s+advance", r"--note"), "plan_engine.py advance --note summary"),
    (("learn_queue.md", "updates .frontier/learn_queue.md"), (r"plan_engine\.py\s+digest\s+<slug>\s+--backfill\s+--write-scaffold", r"LEARN_QUEUE\.md"), "digest updates LEARN_QUEUE.md"),
    (("changelog pr-description",), (r"diagnose\.py\"?\s+changelog\s+pr-description", r"--base\s+main", r"--plan\s+<slug>"), "diagnose.py changelog pr-description"),
]


def _check_special_rules(text: str, exp_lower: str) -> tuple[bool, str] | None:
    """Handle multi-condition expectation rules that need custom combinators."""
    if "delegat" in exp_lower and "refactor-monolith" in exp_lower:
        ok = bool(re.search(r"refactor-monolith|davtoh/antigravity-skills", text, re.I))
        return ok, f"Delegation boundary: {ok}"
    if "3-tier sota" in exp_lower:
        t1, t2, t3 = (bool(re.search(rf"tier\s*{i}", text, re.I)) for i in (1, 2, 3))
        sota = bool(re.search(r"sota|baseline|frontier", text, re.I))
        return (t1 and t2 and t3) or (sota and (t1 or t2)), f"Tiers: T1={t1}, T2={t2}, T3={t3}"
    if "flash-to-opus" in exp_lower or "cognitive harness" in exp_lower:
        pf = bool(re.search(r"pre-flight|preflight|invariants", text, re.I))
        mr = bool(re.search(r"map-reduce|subagent|isolation", text, re.I))
        sl = bool(re.search(r"vertical slic|atomic slic", text, re.I))
        return (pf or mr or sl), f"Harness: PF={pf}, MR={mr}, SL={sl}"
    if "context" in exp_lower and "hygiene" in exp_lower:
        ok = bool(re.search(r"new conversation|/compact|context hygiene", text, re.I))
        return ok, f"Context hygiene: {ok}"
    if "continue" in exp_lower and ("markdown plan" in exp_lower or "resume" in exp_lower):
        ok = bool(re.search(r"frontier-architect continue|resumes execution|plan_engine\.py next", text, re.I))
        return ok, f"Continue engine resume: {ok}"
    if "digest" in exp_lower and "--backfill" in exp_lower:
        ok = bool(re.search(r"digest\s+<slug>\s+--backfill\s+--write-scaffold", text, re.I))
        return ok, f"plan_engine.py digest --backfill --write-scaffold: {ok}"
    if "frozen" in exp_lower and "signal" in exp_lower:
        ok = bool(re.search(r"frozen-monolith signal adapters", text, re.I)) and bool(re.search(r"getattr", text))
        return ok, f"Frozen-Monolith Signal Adapters: {ok}"
    if "failure recovery" in exp_lower and "lifecycle states" in exp_lower:
        ok = bool(re.search(r"failure recovery", text, re.I)) and bool(re.search(r"lifecycle states", text, re.I))
        return ok, f"Failure recovery & lifecycle states: {ok}"
    if "research subagent" in exp_lower and "never re-reads" in exp_lower:
        ok = bool(re.search(r"do not re-read files a `research` subagent", text, re.I))
        return ok, f"Zero Subagent Duplication: {ok}"
    return _check_audit_rules(text, exp_lower)


def _check_audit_rules(text: str, exp_lower: str):
    """Audit-mode expectations (observations connector)."""
    if "diagnose.py brief" in exp_lower:
        ok = bool(re.search(r"brief --run-probes", text)) and bool(re.search(r"UNAVAILABLE.*UNVERIFIED", text, re.S))
        return ok, f"Audit baseline via brief, UNAVAILABLE is UNVERIFIED: {ok}"
    if "active observations" in exp_lower:
        ok = bool(re.search(r"observations list --json", text)) and bool(re.search(r"observations list --kind idea", text))
        return ok, f"Findings and ideas from observations: {ok}"
    if "--missed-by" in exp_lower:
        ok = bool(re.search(r"triage --id <ID> --root-cause .* --missed-by .* --guard", text))
        return ok, f"Record why tools missed it: {ok}"
    return None


def evaluate_expectation_against_text(text: str, expectation: str) -> tuple[bool, str]:
    """Check if a skill text contains concrete evidence for an expectation."""
    exp_lower = expectation.lower()
    if (special := _check_special_rules(text, exp_lower)) is not None:
        return special
    for triggers, patterns, label in _RULES:
        if any(t in exp_lower for t in triggers):
            ok = all(bool(re.search(p, text, re.I)) for p in patterns)
            return ok, f"{label}: {ok}"
    keywords = [w for w in re.findall(r"\b[a-zA-Z_]{4,}\b", exp_lower) if w not in {"with", "that", "from", "this", "then", "have"}]
    found_kw = sum(1 for kw in keywords if kw in text.lower())
    return (found_kw / max(len(keywords), 1)) >= 0.35, f"Generic keywords: {found_kw}/{len(keywords)}"


class TestSkillEvals(unittest.TestCase):
    """Test suite ensuring SKILL.md satisfies all evals in evals/evals.json."""

    @classmethod
    def setUpClass(cls):
        cls.assertTrue(EVALS_FILE.exists(), f"evals.json missing at {EVALS_FILE}")
        cls.assertTrue(SKILL_MD.exists(), f"SKILL.md missing at {SKILL_MD}")
        with open(EVALS_FILE, "r", encoding="utf-8") as f:
            cls.evals = json.load(f).get("evals", [])
        # Progressive disclosure: SKILL.md is a router; detailed gates live in references/.
        cls.router_text = SKILL_MD.read_text(encoding="utf-8")
        refs = sorted((SKILL_DIR / "references").glob("*.md"))
        cls.skill_text = "\n".join([cls.router_text] + [r.read_text(encoding="utf-8") for r in refs])

    def test_evals_json_structure(self):
        """Ensure evals.json contains at least 12 valid scenarios with >= 4 expectations each."""
        self.assertGreaterEqual(len(self.evals), 12)
        total_expectations = sum(len(e.get("expectations", [])) for e in self.evals)
        self.assertGreaterEqual(total_expectations, 60)
        for e in self.evals:
            for key in ("id", "prompt", "expected_output"):
                self.assertIn(key, e)
            self.assertGreaterEqual(len(e.get("expectations", [])), 4)

    def test_trigger_evals_json_structure(self):
        """Verify trigger_eval.json exists and has balanced positive/negative queries."""
        tf = SKILL_DIR / "evals" / "trigger_eval.json"
        self.assertTrue(tf.is_file(), f"Missing trigger_eval.json at {tf}")
        items = json.loads(tf.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(items), 16)
        pos = [x for x in items if x.get("should_trigger") is True]
        neg = [x for x in items if x.get("should_trigger") is False]
        self.assertGreaterEqual(len(pos), 8)
        self.assertGreaterEqual(len(neg), 8)
        self.assertTrue(all(isinstance(x.get("query"), str) and x["query"].strip() for x in items))

    def test_skill_passes_all_eval_expectations(self):
        """Assert current SKILL.md achieves 100% pass rate across all expectations."""
        failed = [
            f"Eval {e['id']}: '{exp}' failed ({reason})"
            for e in self.evals
            for exp in e.get("expectations", [])
            for ok, reason in (evaluate_expectation_against_text(self.skill_text, exp),)
            if not ok
        ]
        self.assertEqual(len(failed), 0, "Regressions found in SKILL.md:\n" + "\n".join(failed))

    def test_evaluate_matcher_direct_cases(self):
        """Direct unit testing of evaluate_expectation_against_text to ensure coverage."""
        cases = [
            ("tool-call ceiling: 3 to 5 calls", "Enforces tool-call ceiling"),
            ("Axiom 10: Respect Explicit User Overrides", "Honors Axiom 10 user override"),
            ("state the assumptions at the top", "States working assumptions concisely"),
            ("Bucket A lean handling formatCurrency", "Triages as Bucket A"),
            ("subagent unattended with no interactive user", "No interactive user present"),
            ("Pre-flight pause protocol for remote debugging", "Pre-flight pause protocol"),
            ("targeted minimal edit to formatCurrency", "minimal, scoped edit"),
            ("no reset --hard avoid destructive actions", "avoids destructive actions"),
            ("Single source of truth (SSOT) no zombie facade", "single source of truth"),
            ("delegate to refactor-monolith", "delegates to refactor-monolith"),
            ("Tier 1 Baseline, Tier 2 SOTA, Tier 3 Novel", "3-Tier SOTA proposals"),
            ("pre-flight block and atomic vertical slicing", "flash-to-opus cognitive harness"),
            ("context hygiene via /compact and new conversation", "context hygiene"),
            ("Multi-skill co-invocation with app-debugger as orchestrator of intent", "multi-skill co-invocation"),
        ]
        for text, exp in cases:
            self.assertTrue(evaluate_expectation_against_text(text, exp)[0], f"Failed direct case: {exp}")

    def test_baseline_comparison_performance(self):
        """If historical baseline snapshot is available, verify no regressions against it."""
        if not BASELINE_SKILL_MD.exists():
            self.skipTest(f"Baseline snapshot not found at {BASELINE_SKILL_MD}; skipping diff.")
        baseline_text = BASELINE_SKILL_MD.read_text(encoding="utf-8")
        all_exps = [exp for e in self.evals for exp in e.get("expectations", [])]
        curr_rate = sum(1 for exp in all_exps if evaluate_expectation_against_text(self.skill_text, exp)[0]) / len(all_exps)
        base_rate = sum(1 for exp in all_exps if evaluate_expectation_against_text(baseline_text, exp)[0]) / len(all_exps)
        self.assertGreaterEqual(curr_rate, base_rate)
        self.assertGreaterEqual(curr_rate, 0.95)

    def test_skill_reference_links_and_tool_effectivity_invariants(self):
        """Pre-refactor invariant: all reference links resolve and core CLI/gate anchors remain in SKILL.md."""
        refs = re.findall(r"\(\./(references/[^)#\s]+)", self.skill_text)
        self.assertGreaterEqual(len(refs), 5)
        for rel in refs:
            self.assertTrue((SKILL_DIR / rel).is_file(), f"Broken reference link in SKILL.md: {rel}")

        required_anchors = [
            "## Core Operational Axioms",
            "### Phase 0:", "### Phase 1A:", "### Phase 1B:",
            "### Phase 2:", "### Phase 3:", "### Phase 4:", "### Phase 5:", "### Phase 6:",
            "plan_engine.py", "discover", "init", "status", "next", "verify", "advance",
            "retrospective", "digest", "lookup", "--no-sync-parent", "--cid", "--backfill --write-scaffold",
            "diagnose.py", "arch-map", "surface", "audit", "scan", "changelog add", "transcript-audit",
            "docker_audit.py", "cdp_inspect.py",
            "MASTER STEP PRE-PLAN GATE", "Smart Commit Hint Gate", "Second-Check Verification Gate",
            "In-Flight Tool Elevation Protocol", "Zero-Dangling-Question Invariant",
            "Anti-Thrash Stop-Loss", "Non-Mocked Branch Gate",
        ]
        missing = [a for a in required_anchors if a not in self.skill_text]
        router_missing = [a for a in required_anchors if a.startswith(("##", "###")) and a not in self.router_text]
        self.assertEqual(router_missing, [], "Phase headings must stay in SKILL.md router")
        self.assertEqual(missing, [], f"Missing critical tool/gate anchors in SKILL.md: {missing}")

    def test_zero_unmapped_generic_fallback_expectations(self):
        """Assert 100% of expectations in evals.json match explicit rules rather than generic keyword fallback."""
        generic_hits = [
            f"Eval {e['id']}: '{exp}' ({reason})"
            for e in self.evals
            for exp in e.get("expectations", [])
            for _, reason in (evaluate_expectation_against_text(self.skill_text, exp),)
            if reason.startswith("Generic keywords:")
        ]
        self.assertEqual(generic_hits, [], "Unmapped expectations falling back to generic keywords:\n" + "\n".join(generic_hits))

    def test_router_stays_lean(self):
        """SKILL.md is a router: cap size so context cost does not creep back."""
        self.assertLess(len(self.router_text.encode("utf-8")), 12_000)
        desc = re.search(r"description: >-\n((?:  .*\n)+)", self.router_text).group(1)
        self.assertLess(len(" ".join(desc.split())), 700)

    def test_claude_adapter_covers_antigravity_tools(self):
        adapter = (SKILL_DIR / "references" / "claude-adapter.md").read_text(encoding="utf-8")
        for term in ("ask_question", "AskUserQuestion", "run_command", "Explore", "RequestFeedback", ".TODO", "appDataDir", "view_file"):
            self.assertIn(term, adapter)

    def test_sanitization_gate(self):
        """Verify committable SKILL.md has zero file-scheme URLs or OS user paths."""
        self.assertIsNone(re.search(r"file:///[A-Za-z0-9_/]", self.skill_text), "Forbidden file URI in SKILL.md")
        self.assertNotIn("C:\\" + "Users\\", self.skill_text, "Forbidden local absolute path in SKILL.md")
        self.assertNotIn("/" + "home/", self.skill_text, "Forbidden local absolute path in SKILL.md")


if __name__ == "__main__":
    unittest.main()
