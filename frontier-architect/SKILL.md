---
name: frontier-architect
description: >-
  Architecture, design and plan-first engineering. Make sure to use this skill whenever the user wants to design or architect a feature or system, compare architecture options (CRDT vs op-log, REST vs GraphQL), brainstorm novel ideas, prototype a risky idea as a SPIKE, write a multi-milestone plan to execute across sessions, continue a plan (/frontier-architect continue, plan_engine status/next), or reproduce and fix a multi-symptom UI/Docker/runtime regression, even if they never say "architecture". Not for small single-file edits, code review, or splitting large files. Works with Claude Sonnet/Opus/Ultra and Gemini.
compatibility: >-
  Python 3.10+ standard library. Under Claude Code read references/claude-adapter.md first. Delegates shared diagnostics (cdp_inspect.py, docker_audit.py) to system-diagnostics/scripts/ SSOT in monorepo; run diagnose.py package-skill for standalone .skill distribution.
---

# Frontier Architect: SOTA Product, Context & Verification Engine

Combines **divergent SOTA innovation** with **disciplined execution** via the model-neutral **Reasoning Harness** ([`references/reasoning-harness.md`](./references/reasoning-harness.md)).

> **Running under Claude Code?** Read [`references/claude-adapter.md`](./references/claude-adapter.md) first. Gate names and tool names below use Antigravity vocabulary (`ask_question`, `research`, `RequestFeedback`, `run_command`); the adapter maps each to Claude equivalents (`AskUserQuestion`, `Explore` agent, `.TODO/*.md`, `Bash`). `<skill_dir>` is the folder containing this file; never assume the repo is at `./skills/`. Commands: [`references/cli-cheatsheet.md`](./references/cli-cheatsheet.md).

## Core Operational Axioms

1. **Adaptive Depth**: Execute simple deterministic tasks without ceremony; for complex/novel tasks, research SOTA patterns, offer 3-tier options, de-risk with SPIKEs, and enforce plan-first atomic slicing.
2. **Intent Clarity Before Action**: If the goal is ambiguous, **stop and ask** concise structured questions before designing.
3. **Externalized Reasoning**: Before production edits, write the **Architectural Pre-Flight** (invariants, flow, edge cases, verifier) and slice vertically ([`references/reasoning-harness.md`](./references/reasoning-harness.md)).
4. **Context Hygiene & Subagent Isolation**: Delegate discovery of `> 3–4` files to a read-only research subagent (Claude: `Explore`; Antigravity: `research`, `Model: 'flash'`), do not re-read files a `research` subagent already swept, wait for its result (`SYSTEM_MESSAGE`) (avoids the wakeup race) instead of starting manual `read_file` sweeps on an early wakeup, and checkpoint summaries in `AGENTS.md`/`CLAUDE.md`. Never load `.TODO/` plans by default; use `plan_engine.py status`/`next`.
5. **Plan-First & Atomic Slicing**: Present an implementation plan (`RequestFeedback: true` / Claude: `.TODO/<slug>.md` + `ExitPlanMode`) before sprawling edits; slice `Contracts/Types → Core Logic → State/Service → UI Layout → Styling & Polish`.
6. **Closed-Loop Empirical Verification**: Pair every slice with tests, typecheck/lint, background suites (`WaitMsBeforeAsync` / Claude: `Bash` `run_in_background`) or browser inspection.
7. **Capability Expansion & Demystification**: Suggest high-leverage MCPs/APIs/SDKs (`search_marketplace` / `ToolSearch`) and explain trade-offs with concrete analogies.
8. **Non-Destructive & Reversible**: Ask explicit consent before hard-to-undo actions (`git reset --hard`, `git checkout --`, `git clean`, force-push, deleting unowned files, dropping DBs, `docker system prune`).
9. **Honest Verification Reporting (Axiom 9)**: Only claim `"verified"` when you ran the check and saw it pass; end every code handoff or design/architecture answer with an evidence-based split of `Verified`, `Not verified` (`UNVERIFIED` / assumed), and known risks.
10. **Respect Explicit User Overrides (Axiom 10)**: On `"just do it"` / `"skip the plan"` / `"no questions"`, skip planning ceremony for reversible work, state working assumptions in 1–2 lines, and keep Axioms 8–9 intact.

---

## Workflow Router

*(Flowchart: [`references/workflow-diagram.md`](./references/workflow-diagram.md). Full Phase 0, 5, 6 text: [`references/phase-protocols.md`](./references/phase-protocols.md); edge-case gates: [`references/triage-protocols.md`](./references/triage-protocols.md).)*

### Phase 0: Context Hygiene, Tool Auto-Pickup & Complexity Triage

Run `python "<skill_dir>/scripts/plan_engine.py" discover --root .` then `status` first. Triage into buckets:
**A (Tactical)** isolated fix → Pre-Flight, edit, verify, and if it grows (`> 2–3` files, API change, failed check) stop and re-triage · **B (Ambiguous)** → 1A · **C (Complex/SOTA)** → 2 & 3 · **D (Multi-symptom bug / UI regression / CPU)** → 1B, never A · **E (`continue`/plan handoff)** → 6.
Execution intent (`implement`, `continue`, `execute`) hits the **Zero-Plan-Re-Read Gate**: `plan_engine.py status`/`next` before opening any plan; never manually edit checkboxes. Improvement intent (`improve`, `enhance`) means **deepen and detail**, preserving contracts. Co-invocation with `/app-debugger` or `/refactor-monolith`: act as **Orchestrator of Intent** under a 3 to 5 tool-call ceiling. Unattended/no interactive user → state assumptions in 1–2 lines, destructive actions stay proposals; read-only or review requests → report without editing. Full gates: `phase-protocols.md`, `triage-protocols.md`.

### Phase 1A: Socratic Clarification Gate (New Features / Vague Intent)

Ask 2–4 targeted questions (`ask_question` / `AskUserQuestion`) on **Core Friction**, **Hard Constraints**, **10x Outcome**.
- **Zero-Dangling-Question Invariant**: Never end a turn with an interview question without invoking the question tool in the **same turn**; skip only in non-interactive or subagent mode.

### Phase 1B: Reproduce-First & Browser/Runtime Diagnostic Gate (Bugs & Regressions)

For **Bucket D**, never write ad-hoc CDP/Docker scripts; prefer `diagnose.py` or bundled `<skill_dir>/scripts/` (`docker_audit.py`, `cdp_inspect.py`). *(Modes & flags: [`references/diagnostics-and-tiers.md`](./references/diagnostics-and-tiers.md).)*
1. **Container & Sync**: `docker_audit.py` / `diagnose.py container` (`docker stats`, `docker top`, `--sync-check`).
2. **Browser CDP**: `cdp_inspect.py --url $APP_URL --audit-layout`; apply the **Pre-Flight Pause Protocol** (ask before attaching to a live browser, or mark *"Live Browser: UNVERIFIED"* per Axiom 9).
3. **Symptom Interview & Matrix**: build a **Symptom-to-Root-Cause Matrix** (`Symptom → Root Cause → File/Line → Live Check`).

### Phase 2: Capability, Tooling & Model Tier Scan

*(Detail: [`references/diagnostics-and-tiers.md`](./references/diagnostics-and-tiers.md#2-phase-2-capability-expansion-and-model-tier-strategy).)*
Check for MCPs/SDKs replacing custom boilerplate. **Model tiers** ([`reasoning-harness.md` §5](./references/reasoning-harness.md#5-tier-escalation-which-model-tier-does-what)): **Executor** (e.g., Sonnet / fast tier) executes the sliced, verified loop; **Planner/Reviewer** (e.g., Opus / Pro) plans and reviews; **Strategist** (e.g., Ultra / heavy) owns long-horizon master roadmaps. Execute an already-approved plan at the Executor tier (Antigravity quota overflow: `useG1Credits`).

### Phase 3: The 3-Tier SOTA Proposition Engine

Present **3 tiers** with plain-language analogies *(detail: [`references/sota-patterns.md`](./references/sota-patterns.md))*: **Tier 1 Pragmatic Baseline**, **Tier 2 Frontier SOTA (Recommended)**, **Tier 3 Novel Moonshot** (de-risk via SPIKE). Before locking a direction, invite questions on trade-offs.

### Phase 4: The SPIKE De-risking Protocol

Before scaffolding unproven Tier 2/3 assumptions, isolate the **Single Riskiest Assumption**, prototype in `.frontier/scratch/<slug>/` (Antigravity: `<appDataDir>/brain/<conversation-id>/scratch/`; [`references/spike-protocol.md`](./references/spike-protocol.md)), measure, then pivot or advance. Any SPIKE named in a plan or proposal needs a **SPIKE Spec** (assumption, metric, pass/fail thresholds, decision rule; spike-protocol.md §5).

### Phase 5: Plan-First Gate, Modularity Budgets & Persistent Memory (`AGENTS.md`)

*(Full contracts & templates: [`references/plan-contracts.md`](./references/plan-contracts.md); detail: `phase-protocols.md`.)*
- Plan as `- [ ] **<file_path>**: <action>` checkboxes, **1-Phase-Per-Turn** (later phases *Deferred to Next Turn / Milestone*); write `.TODO/<slug>.md` and register with `plan_engine.py init .TODO/<slug>.md`.
- `>= 4` milestones or `>= 3` subsystems → **Master Roadmap** (`--parent <master_slug> --milestone 1`; **only Milestone 1 active**, mark `M2..N` *Deferred to Next Turn / Milestone*—never generate all child plans upfront; each milestone names its own OS-agnostic verifier; **Master Roadmap Mode** in `plan-contracts.md` §4 enforces a mandatory **Review Gate** where a fresh reviewer separate from the author checks diff + verify output before advancing). **MASTER STEP PRE-PLAN GATE** and **Master-Step Runtime Wiring Mandate** apply.
- Budgets via `diagnose.py audit --path <targets>`: **350 lines** soft / **500** hard, `<= 10–12` methods/class, `<= 40` lines/function. **Export-Ready Portable Plan Contract**: POSIX repo-relative paths, no `file:///`, OS-agnostic test commands, **Scenario Combinations Matrix**. Use `diagnose.py changelog add`, never `MIGRATION_LOG.md`. Ask before creating any new UI component.

### Phase 6: Plan Execution, Continuation Engine & Closed-Loop Verification

*(Harness: [`reasoning-harness.md`](./references/reasoning-harness.md); CLI: [`cli-cheatsheet.md`](./references/cli-cheatsheet.md); sign-off: [`plan-contracts.md`](./references/plan-contracts.md); full text: `phase-protocols.md`.)*
Loop per milestone: `plan_engine.py status`/`next` → **Pre-Flight Critic Gate** → sliced edits (never guess paths; one `edit_file` / `Edit` per file at a time; **In-Flight Tool Elevation Protocol**: fix shared tool bugs in `system-diagnostics/scripts/` + tests) → `diagnose.py audit` (**Zero Audit Evasion**) → `plan_engine.py verify` → **Second-Check Verification Gate** → `advance` → `diagnose.py scan` → `retrospective` (**Smart Commit Hint Gate**; echo `Suggested Commit`, never commit without consent). **Anti-Thrash Stop-Loss**: after 2 failed attempts, revert and escalate (`/app-debugger`, or the Planner/Reviewer tier, e.g., Opus). Final sign-off adds the **Non-Mocked Branch Gate**, `digest --backfill --write-scaffold`, full regression, and `### Continuous Learning & Introspective Options` once at verified completion.

---

## Scripts, References & Self-Tests

- **Scripts (`scripts/`)**: `plan_engine.py` (status/next/advance/verify/reconcile), `cdp_inspect.py`, `docker_audit.py` (SSOT shims to `system-diagnostics`).
- **References (`references/`)**: [`claude-adapter.md`](./references/claude-adapter.md), [`phase-protocols.md`](./references/phase-protocols.md), [`cli-cheatsheet.md`](./references/cli-cheatsheet.md), [`plan-contracts.md`](./references/plan-contracts.md), [`triage-protocols.md`](./references/triage-protocols.md), [`diagnostics-and-tiers.md`](./references/diagnostics-and-tiers.md), [`reasoning-harness.md`](./references/reasoning-harness.md), [`sota-patterns.md`](./references/sota-patterns.md), [`spike-protocol.md`](./references/spike-protocol.md), [`workflow-diagram.md`](./references/workflow-diagram.md).
- **Tests**: `python -m unittest discover -s <skill_dir>/tests -p "test_*.py"`.
- **Pre-commit self-audit (on monorepo edits)**: run the `system-diagnostics`, `app-debugger` and `frontier-architect` suites plus `diagnose.py audit --path <modified_skill_files>`.
