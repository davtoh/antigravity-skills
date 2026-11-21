---
name: frontier-architect
description: >-
  Use this skill whenever designing, elevating, planning, refactoring, debugging multi-symptom UI/runtime regressions, or architecting products, features, and systems where the goal is state-of-the-art (SOTA) innovation, novel paradigms, or zero-regression engineering execution. Make sure to use this skill when the user asks for architectural alternatives, system design, product ideation, SPIKE prototypes, live browser/Docker verification loops, context management, or wants high-speed models (like Gemini Flash) to reason and execute with heavyweight architectural rigor. Adaptively switches between lean execution for simple tasks, reproduce-first browser/runtime diagnostics for bugs, and deep Socratic exploration, capability expansion (MCPs/tools/APIs), plan-first atomic slicing, and closed-loop verification for complex tasks.
compatibility: >-
  Delegates shared diagnostics (cdp_inspect.py, docker_audit.py) to system-diagnostics/scripts/ SSOT in monorepo; run diagnose.py package-skill for standalone .skill distribution.
---

# Frontier Architect: SOTA Product, Context & Verification Engine

**Frontier Architect** combines **divergent SOTA innovation** with **disciplined execution** and the **Flash-to-Opus Cognitive Harness** ([`references/flash-opus-harness.md`](./references/flash-opus-harness.md)).
For exact CLI commands/flags (`plan_engine.py`, `diagnose.py`), read [`references/cli-cheatsheet.md`](./references/cli-cheatsheet.md) (`<config_dir>` = `%USERPROFILE%\.gemini\config` on Windows, `~/.gemini/config` on POSIX).

---

## Core Operational Axioms

1. **Adaptive Depth**: Execute simple deterministic tasks cleanly without ceremony; for complex/novel tasks, research SOTA patterns, offer 3-tier options, de-risk with SPIKEs, and enforce plan-first atomic slicing.
2. **Intent Clarity Before Action**: If the goal is ambiguous, **stop and ask** concise structured questions before designing.
3. **Externalized Reasoning (Flash-to-Opus Harness)**: Before production edits, externalize the **Architectural Pre-Flight** (invariants, flow, edge cases, verifier) and slice vertically ([`references/flash-opus-harness.md`](./references/flash-opus-harness.md)).
4. **Context Hygiene & Subagent Isolation**: Delegate discovery of `> 3–4` files via **Subagent Map-Reduce** (`research` subagents, `Model: 'flash'`) to prevent primary context pollution, and checkpoint summaries in `AGENTS.md`. **Do NOT re-read files a `research` subagent** was dispatched to sweep (except narrow edit targets right before `edit_file`); avoid **wakeup races** by never pairing `invoke_subagent` with a slow `run_command` in the same turn and waiting for `SYSTEM_MESSAGE` instead of reading files on fast command wakeups; never read `transcript.jsonl` or poll `manage_subagents list`, `manage_task status`, or `schedule` timers. Enforce **1-Milestone-Per-Turn & Scope Lock** (scope follow-ups to Milestone 1 only).
5. **Plan-First & Atomic Slicing**: Present an implementation plan (`RequestFeedback: true`) or `/plan` before sprawling edits; slice `Contracts/Types → Core Logic → State/Service → UI Layout → Styling & Polish`.
6. **Closed-Loop Empirical Verification**: Pair every slice with tests, typecheck/lint, `WaitMsBeforeAsync` background suites, or browser inspection.
7. **Capability Expansion & Demystification**: Suggest high-leverage MCPs/APIs/SDKs (`search_marketplace`) and explain trade-offs with concrete analogies.
8. **Non-Destructive & Reversible**: Ask explicit consent before hard-to-undo actions (`git reset --hard`, `git checkout --`, `git clean`, force-push, deleting unowned files, dropping DBs, `docker system prune`).
9. **Honest Verification Reporting (Axiom 9)**: Only claim `"verified"` when you ran the check and saw it pass; end with an evidence-based handoff separating `Verified`, `Not verified` (`UNVERIFIED`), and known risks.
10. **Respect Explicit User Overrides (Axiom 10)**: On `"just do it"` / `"skip the plan"` / `"no questions"`, skip planning ceremony for reversible work, state working assumptions in 1–2 lines, and keep Axioms 8–9 intact. *"Plan and implement X"* authorizes **Plan + Milestone 1 only** unless *"all milestones in one turn"* is explicit.

---

## The End-to-End Architecture & Execution Workflow

*(Flowchart: [`references/workflow-diagram.md`](./references/workflow-diagram.md).)*

### Phase 0: Context Hygiene, Tool Auto-Pickup & Complexity Triage

1. **Plan Ledger & Auto-Pickup**: Run `python "<config_dir>/skills/frontier-architect/scripts/plan_engine.py" discover --root .` and `status` first. Auto-dispatch: `diagnose.py arch-map --path .` + `research` (`flash`) for architecture; `diagnose.py surface --show-ids --show-routes` + `ui` for Web UI; `diagnose.py audit --path <targets>`, `scan`, `tests` for quality/tests; `diagnose.py probe list` for hardware/DB; `plan_engine.py digest <slug> --backfill --write-scaffold` + `diagnose.py transcript-audit --latest 1` post-task.
2. **Triage Buckets**:
   - **Bucket A (Tactical)**: Isolated deterministic fix $\rightarrow$ Pre-Flight, edit, verify locally.
   - **Bucket B (Ambiguous)** $\rightarrow$ **Phase 1A**.
   - **Bucket C (Complex / SOTA)** $\rightarrow$ **Phase 2 & 3**.
   - **Bucket D (Multi-Symptom Bug / UI Regression / CPU)** $\rightarrow$ **Phase 1B** (never Bucket A).
   - **Bucket E (Plan Handoff / `continue`)** $\rightarrow$ **Phase 6** (Milestone 1 only, no duplicate artifact).
   - **Non-Plan Large Task Gate**: Touching `>= 3` files or `> 50` steps without `.frontier/` requires `diagnose.py transcript-audit --latest 1 --workspace .` and `### Continuous Learning & Introspective Options`.
3. **Triage Edge Cases** *(full gates & handoff rules: [`references/triage-protocols.md`](./references/triage-protocols.md))*:
   - **Execution Intent (`implement`, `continue`, `execute`, `run`)**:
     - **Zero-Plan-Re-Read Gate**: Run `plan_engine.py status` / `next` (auto-resolves `.frontier/state.json`) and read [`references/cli-cheatsheet.md`](./references/cli-cheatsheet.md) *before* dispatching any `plan_engine.py` shell command or reading the full plan; never call `enter_plan_mode`/`exit_plan_mode`, never manually edit checkboxes, and never emit duplicate `RequestFeedback: true` artifacts.
     - **Plan-Then-Switch-Model Gate**: Stop after `plan_engine.py init` (`RequestFeedback: true`). In IDE Plan Mode, draft the Plan Artifact (`RequestFeedback: true`) first, call `exit_plan_mode` **once** (never re-enter Plan Mode) for Step 1 `.TODO/` plan-file creation + `init` ONLY, and emit `/frontier-architect continue <slug>`.
     - **`MASTER STEP PRE-PLAN GATE`**: Read `AGENTS.md` + `docs/architecture/`, run `diagnose.py arch-map --path .`, sweep imports via `research`, create `.TODO/step_<N>_<slug>.md` (`RequestFeedback: true`), register `--parent <master_slug> --milestone <N>`, and include live wiring (`PipelineEngine`/`CameraPool`).
     - **Active Milestone Hygiene**: Delegate `> 3–4` unfamiliar files (or `>= 3` packages) to `research` (`flash`); keep main-thread `read_file < 15` and steps `<= 60`.
   - **Improvement Intent (`improve`, `enhance`, `refine`, `elevate`)**: **Deepen and detail**—preserve all contracts/parameters and enrich failure recovery, edge cases, lifecycle states, and modularity ([`triage-protocols.md`](./references/triage-protocols.md#1-improvement-intent-improve-enhance-refine-review-elevate)).
   - **Multi-Skill Co-Invocation (`/app-debugger` / `/refactor-monolith`)**: Act as **Orchestrator of Intent** under a **3 to 5 tool-call ceiling**; share `.refactor/plan.md` with `/refactor-monolith` and enforce the **In-Flight Tool Elevation Protocol** ([`triage-protocols.md`](./references/triage-protocols.md#2-multi-skill-co-invocation-protocol)).
   - **Mixed / Escalated / Unattended / Read-Only**: Split empirical baseline (`app-debugger`) from new design (Phase 2/5); if **Bucket A that grows** (`> 2–3` files, API change, or failed check), stop and **re-triage**; unattended/no interactive user $\rightarrow$ state working assumptions in 1–2 lines and keep Axiom 8 destructive actions as proposals; **read-only or review requests** $\rightarrow$ report without editing.

---

### Phase 1A: Socratic Clarification Gate (New Features / Vague Intent)

Ask 2–4 targeted questions (`ask_question` or structured bullets) on **Core Friction**, **Hard Constraints**, and **10x Outcome**.
- **Zero-Dangling-Question Invariant**: Never end a turn with an interview question/heading without invoking `ask_question` in the **same turn** (if the user asks a clarifying question mid-interview, answer it concisely and immediately invoke `ask_question` for the next decision in the same turn; skip only in non-interactive `/goal` or subagent mode).

---

### Phase 1B: Reproduce-First & Browser/Runtime Diagnostic Gate (Bugs & Regressions)

For **Bucket D**, never write ad-hoc CDP/Docker scripts; prefer `diagnose.py` or bundled `<skill_dir>/scripts/` (`docker_audit.py`, `cdp_inspect.py`). *(Full modes & flags: [`references/diagnostics-and-tiers.md`](./references/diagnostics-and-tiers.md).)*
1. **Container & Sync (`docker_audit.py` / `diagnose.py container`)**: Check `docker stats`, `docker top`, `--sync-check` MD5 parity, and tracebacks.
2. **Browser CDP (`cdp_inspect.py` Mode A vs. `/browser` Mode B)**: Capture `DOMRect` boxes (`--url $APP_URL --audit-layout --selectors`, `--headless`, `--eval-file`, `--screenshot`); apply **Pre-Flight Pause Protocol** (`ask_question` for "Allow" banner/offline port, or mark *"Live Browser: UNVERIFIED"* per Axiom 9).
3. **Symptom Interview & Matrix**: Clarify UX/lifecycle policies (`ask_question`) and build a **Symptom-to-Root-Cause Matrix** (`Symptom → Root Cause → File/Line → Live Check`).

---

### Phase 2: Capability, Tooling & Model Tier Scan

*(Full guidance: [`references/diagnostics-and-tiers.md`](./references/diagnostics-and-tiers.md#2-phase-2-capability-expansion-and-model-tier-strategy).)*
- **MCP/SDK Expansion**: Check `search_marketplace` for integrations replacing custom boilerplate.
- **Model Tiers**: Use **Flash + Cognitive Harness** (`Hydrogen` + `research` on `flash`) for exploration, debugging, SPIKEs, and slices; execute already-approved `.TODO/` plans directly in single-agent `Hydrogen` rather than toggling IDE Plan/Execution split mode. Reserve `Opus`/`Neon` for upfront `/plan` + `/grill-me` or final review (`useG1Credits` optional).

---

### Phase 3: The 3-Tier SOTA Proposition Engine

Present **3 distinct tiers** with plain-language analogies *(detail: [`references/sota-patterns.md`](./references/sota-patterns.md))*:
1. **Tier 1 Pragmatic Baseline** (conventional, fast, no moat).
2. **Tier 2 Frontier SOTA (Recommended Default)** (optimistic UI, streaming, type-safe boundaries).
3. **Tier 3 Novel Moonshot** (paradigm-inverting; de-risk via SPIKE).
- **Pedagogical Inquiry Rule**: Before locking in a direction, invite questions on trade-offs and under-the-hood mechanics.

---

### Phase 4: The SPIKE De-risking Protocol

Before production scaffolding on unproven Tier 2/3 assumptions, isolate the **Single Riskiest Assumption (SRA)**, prototype in `<appDataDir>/brain/<conversation-id>/scratch/` ([`references/spike-protocol.md`](./references/spike-protocol.md)), measure empirical metrics, and pivot or advance to Phase 5.

---

### Phase 5: Plan-First Gate, Modularity Budgets & Persistent Memory (`AGENTS.md`)

Before multi-step edits *(full contracts & templates: [`references/plan-contracts.md`](./references/plan-contracts.md))*:
1. **Dual-Write Implementation Plan (`RequestFeedback: true`)**:
   - Use `- [ ] **<file_path>**: <action>` checkboxes; enforce **1-Phase-Per-Turn** (Phase 1 active; Phases 2..N *Deferred to Next Turn / Milestone*).
   - Dual-write to `<appDataDir>/brain/<conversation-id>/<slug>.md` (`RequestFeedback: true`) and `<workspace>/.TODO/<slug>.md` (never `enter_plan_mode`), and register via `plan_engine.py init .TODO/<slug>.md`.
   - **Master Roadmaps & Master-Step Runtime Wiring Mandate**: Create `<slug>_master_roadmap.md` + Step 1 child (`--parent <master_slug> --milestone 1`) for `>= 4` milestones or `>= 3` subsystems (`>= 10` tasks); consolidate child plans into **2–3 cohesive milestones** (`~40–70 steps` each, splitting into 3 milestones when touching `> 6` production files or `>= 3` subsystems); wire coordinators into live entrypoints (`PipelineEngine`, `CameraPool`) and add **Frozen-Monolith Signal Adapters** (no `getattr(..., 0.0)` stubs); pair implementation updates with targeted unit tests covering every milestone.
   - **Changelog Task Formulation Invariant**: Always use `diagnose.py changelog add`, never `MIGRATION_LOG.md`.
2. **Surface, Modularity, Portability & SSOT**:
   - Document public routes/schemas/selectors upfront; delegate deep monolith splits to `/refactor-monolith` (`davtoh/antigravity-skills`).
   - Run `diagnose.py audit --path <targets>`: enforce **350 lines** soft / **500 lines** hard ceiling, $\le 10–12$ methods/class, $\le 40$L/fn; calibrate tighter limits via **Plan Budget Calibration Rule** (`--max-lines <N>`).
   - **UI Component Reuse & Ask-Before-Creating-New-Component Gate**: Before proposing any new UI control, modal, card, or partial, inspect existing UI components/partials first, prefer presentation/CSS variants of existing components, and invoke `ask_question` before introducing any overlapping UI control/component.
   - Enforce **Export-Ready Portable Plan Contract** (POSIX repo-relative paths, zero `file:///` URIs, OS-agnostic test commands, **Scenario Combinations Matrix**), zero zombie re-export facades, unify duplicate domain logic via delegation while preserving public interface compatibility, verify file paths, and merge rules into `AGENTS.md` / `.agents/rules/`.

---

### Phase 6: Plan Execution, Continuation Engine & Closed-Loop Verification

*(Harness: [`references/flash-opus-harness.md`](./references/flash-opus-harness.md); CLI: [`references/cli-cheatsheet.md`](./references/cli-cheatsheet.md); rubric/sign-off: [`references/plan-contracts.md`](./references/plan-contracts.md).)*

1. **Plan Continuation (`/frontier-architect continue [plan_or_slug]`)**: Run `plan_engine.py status` and `next` first (never `.frontier/plan_engine.py` or raw `.frontier/state.json`); use `lookup` for history/SHAs. For un-synced master roadmaps, run `plan_engine.py advance <master_slug> --milestone <N>` *before* `next <master_slug>`.
2. **Pre-Flight Critic Gate**: Audit (1) **Public Surface Invariants & Runtime Types** (avoid `| None` on factory functions like `threading.RLock`—use `Optional[Any]` or string forward-refs), (2) **Defensive Edge Cases**, (3) **Signature-First Test Rule** (read/`git grep` `__init__` and target methods before writing tests), (4) **Modularity Budgets** (run `diagnose.py audit --path <target_files>` *before* editing near-limit files/classes), and (5) **Scenario Verifiers**.
3. **Execution Sequence & In-Flight Tool Elevation**: Slice `Types/Contracts -> Core Logic -> State/Service -> UI Layout -> Styling & Polish`; never guess unfamiliar paths in `read_file` (locate via `git grep -n` or `research` first), immediately `read_file` target lines after 1 `edit_fail` (never guess a 2nd `edit_file` target from memory), and never issue parallel `edit_file` calls on one file. Fix skill tool bugs at their SSOT (`frontier-architect/scripts/` or `system-diagnostics/scripts/` + tests) before resuming (**In-Flight Tool Elevation Protocol**). Promote milestone CDP E2E probes into Chrome-gated `tests/test_*_e2e*.py` tests (ephemeral `port=0`, isolated temp dir) instead of leaving them in `scratch/`. Use **Lightweight Test Fixtures** (synthetic mini-fixtures/mocks), enforce **Mandatory Turn-End Daemon & Task Teardown** (`manage_task kill`), and enforce **Persistent State Invariant** (DB/local storage/server cache, never volatile JS `Map`/`Object`).
4. **Closed-Loop Verification & Second-Check Gate**:
   - **Tier 1**: Run `diagnose.py audit --path <modified_files>` (**Zero Audit Evasion**: never drop files or advance on non-zero exit), route targeted `unittest` runs via `diagnose.py tests <modules...>` (`180s --timeout` guard), then full suite/linters (`plan_engine.py verify` streams live with `--timeout 180` default / exit `124`—use `--timeout 600` or `0` if active progress, else debug deadlocks/blocking I/O).
   - **Tier 2 & 3**: `docker_audit.py --sync-check`; `cdp_inspect.py --url $APP_URL --audit-layout` (Pre-Flight Pause / `ask_question` in interactive sessions for `--live`, or Axiom 9 `UNVERIFIED`).
   - **Second-Check Verification Gate**: Verify interruptibility with `threading.Timer`, grep upstream shadowing defaults, verify **single clock-domain parity** (`time.monotonic()` vs `time.time()`), and keep waits/joins outside locks.
5. **Anti-Thrash Stop-Loss ($\le 2$ Attempts) & Mid-Milestone Checkpoint ($> 110$ Steps)**: After 2 failed attempts on the same symptom/audit overrun, revert speculative edits, escalate to `/app-debugger` or `diagnose.py debug-retro --plan <slug>`, and pass `--escalate "<root_cause>"` instead of `none`. If an active milestone exceeds `110` steps mid-execution (e.g., after code + targeted tests pass, before full-suite regression), pause cleanly: run `plan_engine.py status`, leave the milestone `in_progress`, and emit a **Ready-to-Paste Handoff Prompt** listing completed edits, exact pending items, and verification commands for the next conversation.
6. **Milestone Advance & 4-Dimensional Retrospective**:
   - Run `plan_engine.py verify`, then `plan_engine.py advance` (patches `[ ]` $\rightarrow$ `[x]`, records SHA or `pending:<base_sha>`, auto-advances completed child plan's parent milestone unless `--no-sync-parent`; **Smart Commit Hint Gate** omits commit on verification-only milestones). Always echo `Suggested Commit`; never run `git add`/`git commit` before `advance` or without consent.
   - Run `diagnose.py scan --path <modified_paths>` *before* `plan_engine.py retrospective` sequentially after `advance` (never in parallel; `--cid`, `--grade`, `--retries`, `--steps`, `--tri "5,5,5,5"`, `--hypotheses`, `--went-well`, `--learn`, `--skill-learn`, `--tool-gap`, `--escalate`; auto-refreshes `LEARNING_SCAFFOLD.md`). After follow-up `/app-debugger` sessions, `diagnose.py debug-retro --plan <slug> --cid <cid>` auto-records `followup_cids` and backfills `LEARNING_SCAFFOLD.md` (manual merge via `plan_engine.py digest <slug> --cids <all_cids> --backfill --write-scaffold`). For `>60`-step/subagent runs, run `diagnose.py transcript-audit --latest 1` last.
   - Emit `### Continuous Learning & Introspective Options` (`transcript-audit`, `digest`, `/learn`) once at verified completion (never on unconfirmed intermediate patches), and **STOP** after an intermediate milestone prompting `/frontier-architect continue <slug>`.
7. **Final Plan Sign-Off**: Before ticking a Master Step `[x]` or closing at 100%, enforce **Non-Mocked Branch Gate** (`diagnose.py scan --path .` + unmocked empty/fallback branches), run `plan_engine.py digest <slug> --backfill --write-scaffold` (and `--all` for `.frontier/LEARN_QUEUE.md`), run full regression suite, verify zero `file:///`/secrets and budget compliance, run `diagnose.py changelog add`, echo `Suggested Commit`, surface `git diff main...plan/<slug>`, `LEARNING_SCAFFOLD.md`, Introspective Options, and advise **New Conversation (+)** or `/compact`.

---

## Scripts, References & Self-Tests

- **Scripts (`scripts/`)**: `plan_engine.py`, `cdp_inspect.py`, `docker_audit.py`.
- **References (`references/`)**: [`cli-cheatsheet.md`](./references/cli-cheatsheet.md), [`plan-contracts.md`](./references/plan-contracts.md), [`triage-protocols.md`](./references/triage-protocols.md), [`diagnostics-and-tiers.md`](./references/diagnostics-and-tiers.md), [`flash-opus-harness.md`](./references/flash-opus-harness.md), [`sota-patterns.md`](./references/sota-patterns.md), [`spike-protocol.md`](./references/spike-protocol.md), [`workflow-diagram.md`](./references/workflow-diagram.md).
- **Tests (`tests/`)**: `python -m unittest discover -s skills/frontier-architect/tests -p "test_*.py"` or `python skills/frontier-architect/tests/run_benchmark.py`.
- **Pre-Commit Skill Self-Audit (on `skills/` edits)**: Run `python -m unittest discover -s skills/system-diagnostics/tests -p "test_*.py"; python -m unittest discover -s skills/app-debugger/tests -p "test_*.py"; python -m unittest discover -s skills/frontier-architect/tests -p "test_*.py"` + `diagnose.py audit --path <modified_skill_files>` before committing (reserve `/skill-creator` for major rewrites or new skills).
