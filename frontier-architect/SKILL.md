---
name: frontier-architect
description: >-
  Use this skill whenever designing, elevating, planning, refactoring, debugging multi-symptom UI/runtime regressions, or architecting products, features, and systems where the goal is state-of-the-art (SOTA) innovation, novel paradigms, or zero-regression engineering execution. Make sure to use this skill when the user asks for architectural alternatives, system design, product ideation, SPIKE prototypes, live browser/Docker verification loops, context management, or wants high-speed models (like Gemini Flash) to reason and execute with heavyweight architectural rigor. Adaptively switches between lean execution for simple tasks, reproduce-first browser/runtime diagnostics for bugs, and deep Socratic exploration, capability expansion (MCPs/tools/APIs), plan-first atomic slicing, and closed-loop verification for complex tasks.
compatibility: >-
  Delegates shared diagnostics (cdp_inspect.py, docker_audit.py) to system-diagnostics/scripts/ SSOT in monorepo; run diagnose.py package-skill for standalone .skill distribution.
---

# Frontier Architect: SOTA Product, Context & Verification Engine

**Frontier Architect** combines **divergent SOTA innovation** with **disciplined execution** (context hygiene, plan-first gates, atomic vertical slicing, and closed-loop verification) plus the **Flash-to-Opus Cognitive Harness** ([`references/flash-opus-harness.md`](./references/flash-opus-harness.md)).
For exact CLI commands/flags (`plan_engine.py`, `diagnose.py`), consult [`references/cli-cheatsheet.md`](./references/cli-cheatsheet.md) (`<config_dir>` = `%USERPROFILE%\.gemini\config` on Windows, `~/.gemini/config` on POSIX).

---

## Core Operational Axioms

1. **Adaptive Depth (The Complexity Dial)**:
   - **Simple / Deterministic Tasks**: Execute cleanly and directly without unnecessary ceremony.
   - **Complex / Novel Tasks**: Research SOTA patterns, propose 3-tier alternatives, run isolated SPIKEs, and enforce plan-first atomic execution.
2. **Intent Clarity Before Action (Zero Guessing)**:
   - If the goal is ambiguous or underspecified, **stop and ask** concise, structured questions before proposing architectures.
3. **Externalized Reasoning (The Flash-to-Opus Harness)**:
   - Before editing production code, externalize the **Architectural Pre-Flight** (invariants, data flow, edge cases, verifier command) and execute in small, verified vertical slices. *(See [`references/flash-opus-harness.md`](./references/flash-opus-harness.md)).*
4. **Context Hygiene & Subagent Isolation**:
   - Delegate broad codebase/doc sweeps (`> 3–4` files) to `research` subagents (`Model: 'flash'`) so only distilled summaries enter the main thread. Checkpoint state into `AGENTS.md` or artifacts for clean fresh threads.
   - **Zero Subagent Duplication, Wakeup Race & Transcript Scraping**: Do NOT re-read files a `research` subagent was dispatched to sweep (unless reading a narrow edit target right before `edit_file`), never pair `invoke_subagent` with a fast background command and start manual `read_file` sweeps on its early wakeup (wait for the subagent's `SYSTEM_MESSAGE`), never read its `transcript.jsonl`, and never poll `manage_subagents list`, `manage_task status`, or `schedule` timers—let reactive wakeup resume execution.
   - **Strict 1-Milestone-Per-Turn & Scope Lock**: Never implement multiple milestones in one turn, and never expand beyond a milestone's planned files without amending the child plan first. When drafting follow-up prompts for the user, always scope execution to **Milestone 1 only** (`advance` + `retrospective` + stop).
5. **Plan-First & Atomic Slicing**:
   - Present an implementation plan artifact (`RequestFeedback: true`) or `/plan` before sprawling edits. Sequence slices: `Contracts/Types → Core Logic → State/Service → UI Layout → Styling & Polish`.
6. **Closed-Loop Empirical Verification (Never Code Blind)**:
   - Pair every slice with an empirical check (unit test, typechecker, linter, background integration task, or browser/UI inspection).
7. **Capability Expansion & Demystification**:
   - Recommend MCP servers, frontier APIs, or modern libraries when they unlock a 10x leap; explain concepts with concrete analogies before locking in decisions.
8. **Non-Destructive & Reversible by Default**:
   - Before hard-to-undo actions (`git reset --hard`, `git checkout -- <file>`, `git clean`, force-push, deleting/overwriting unowned files, dropping DB tables, `docker system prune`, global installs), stop and get explicit consent. Prefer additive edits and never discard unowned changes.
9. **Honest Verification Reporting (Evidence, Not Optimism)**:
   - Only report something as "verified" if you ran the check and saw it pass. State plainly what is unverified (blocked browser/Docker/dependency) and report regressions prominently.
10. **Respect Explicit User Overrides**:
    - If the user says "just do it", "skip the plan", or "no questions", follow that for reversible parts, state working assumptions in 1–2 lines, and keep Axioms 8 and 9 intact.
    - *"Plan and implement X"* authorizes **Plan + Milestone 1 only** unless the user explicitly writes *"all milestones in one turn"*.

---

## The End-to-End Architecture & Execution Workflow

*(Workflow flowchart: [`references/workflow-diagram.md`](./references/workflow-diagram.md).)*

---

### Phase 0: Context Hygiene, Tool Auto-Pickup & Complexity Triage

Protect the context window, auto-dispatch high-leverage tools, and classify the task:

1. **Plan Ledger Check & Goal-to-Tool Auto-Dispatch**:
   - **Check Prior Plans First**: Run `python "<config_dir>/skills/frontier-architect/scripts/plan_engine.py" discover --root .` and `status` before broad exploration.
   - **Auto-Pickup Tools by Goal**:
     - *Architecture / multi-file*: `diagnose.py arch-map --path .` + `research` subagent (`Model: 'flash'`) for `> 3–4` files.
     - *Web UI / DOM / CSS*: `diagnose.py surface --show-ids --show-routes --show-globals` + `diagnose.py ui` (or `/browser` / `chrome_devtools`).
     - *Modularity / defects / tests*: `diagnose.py audit --path <targets>`, `diagnose.py scan --path <targets>`, `diagnose.py tests`.
     - *Hardware / DB / external*: `diagnose.py probe list` (or `search_marketplace` for missing MCPs/SDKs).
     - *Post-task introspection*: `plan_engine.py digest <slug> --backfill --write-scaffold`, `diagnose.py transcript-audit --latest 1`.
2. **Triage the Request**:
   - **Bucket A (Tactical / Single-Step)**: Isolated, deterministic tweak or single-function utility with zero UI/runtime ambiguity. Run Pre-Flight, edit, and verify locally.
   - **Bucket B (Ambiguous / Underspecified)**: High-level or unclear goal $\rightarrow$ **Phase 1A**.
   - **Bucket C (Complex / Architectural / SOTA)**: New modules, redesigns, or product elevation $\rightarrow$ **Phase 2 & Phase 3**.
   - **Bucket D (Multi-Symptom Bug / UI Regression / CPU Bottleneck)**: Multiple UI/state bugs, post-fix regressions, overflow, stuck indicators, or high Docker/WSL (`vmmem`) CPU. **Never treat as Bucket A** $\rightarrow$ **Phase 1B**.
   - **Bucket E (Plan Handoff)**: Existing plan with execution intent (`implement @[plan.md]`, `/frontier-architect continue [plan]`) $\rightarrow$ **Phase 6** (Milestone 1 only, no duplicate plan artifact).
   - **Non-Plan Large Task Gate**: Even without an active `.frontier` plan, any Bucket A/C/D task touching `>= 3` files or exceeding `> 50` steps **MUST** run `diagnose.py transcript-audit --latest 1 --workspace .` before final sign-off and append the Turn-End `### Continuous Learning & Introspective Options` block (offering `/learn` if lessons surfaced).
3. **Triage Edge Cases** *(full protocols: [`references/triage-protocols.md`](./references/triage-protocols.md))*:
   - **Execution Intent (`implement`, `continue`, `execute`, `run`)**:
     1. **Zero-Plan-Re-Read Gate**: On `/frontier-architect continue`, run `plan_engine.py status [slug] --root .` and `next [slug] --root .` (omit `[slug]` to auto-resolve `.frontier/state.json`), AND read [`references/cli-cheatsheet.md`](./references/cli-cheatsheet.md) before reading the full plan or source files. Prepend workspace root to repo-relative `read_file` paths; never manually patch checkboxes with `edit_file`, never call `enter_plan_mode`/`exit_plan_mode`, never issue parallel `edit_file` calls on one file, and do not emit a duplicate `RequestFeedback: true` artifact.
     2. **Master Step Pre-Plan Gate (`MASTER STEP PRE-PLAN GATE`)**: If `next` emits this gate without a `Tactical Master Step` bypass, **DO NOT** implement in one turn. Read `AGENTS.md` + `docs/architecture/`, run `diagnose.py arch-map --path .`, sweep imports via `research` subagent, create `.TODO/step_<N>_<slug>.md` + `RequestFeedback: true` artifact, register with `--parent <master_slug> --milestone <N>`, and include live wiring (`PipelineEngine` / `CameraPool` / entrypoints). If `next` emits `Tactical Master Step`, execute directly in this turn unless exploration reveals `>= 3` subsystems or `>= 4` files.
     3. **Active Milestone Discovery Hygiene**: Jump to **Phase 6** for the active milestone only; delegate `> 3–4` unfamiliar file sweeps (or any milestone spanning `>= 3` apps/packages) to `research` (`Model: 'flash'`) upfront so main-thread `read_file` stays `< 15` and steps stay `<= 60`. Run full test suites only when targeted tests are missing or at milestone completion.
   - **Improvement Intent (`improve`, `enhance`, `refine`, `review`, `elevate`)**: **Deepen and detail; never simplify**—preserve all parameters/contracts and enrich failure recovery, edge cases, lifecycle states, and modularity invariants ([`triage-protocols.md`](./references/triage-protocols.md#1-improvement-intent-improve-enhance-refine-review-elevate)).
   - **Multi-Skill Co-Invocation (`/app-debugger` or `/refactor-monolith`)**: Act as **Orchestrator of Intent** with a **3 to 5 tool-call ceiling** for initial triage; with `/refactor-monolith`, write to `<workspace>/.refactor/plan.md` + `.refactor/state.json` and enforce the **In-Flight Tool Elevation Protocol** ([`triage-protocols.md`](./references/triage-protocols.md#2-multi-skill-co-invocation-protocol)).
   - **Mixed Requests**: Split empirical baseline (`app-debugger` / `diagnose.py`) from new architectural design (`frontier-architect` Phase 2 & 5).
   - **Bucket A That Grows**: If a Bucket A fix touches `> 2–3` files, changes a public interface, or fails first verification, stop, re-triage, and inform the user.
   - **No Interactive User** (subagent / `/goal` / no `ask_question`): Pick the most conservative reversible path, state working assumptions in 1–2 lines, and leave Axiom 8 destructive actions as recommendations.
   - **Read-only or review requests** ("check this", "audit this"): Report findings without editing unless asked.

---

### Phase 1A: Socratic Clarification Gate (For New Features / Vague Intent)

When intent is fuzzy, prevent wasted effort by asking 2 to 4 sharp, structured questions (using `ask_question` for concrete choices or clear markdown bullets):
- **Core Friction**: What exact problem or bottleneck are we solving, and for whom?
- **Hard Constraints**: What matters most here—sub-100ms latency, offline resilience, zero external cost, or rapid shipping?
- **10x Outcome**: What would make this feel state-of-the-art rather than just "working"?
- **Zero-Dangling-Question Invariant**: Never end a turn with a `Question X` heading or interview transition without calling `ask_question` in the **same turn**. If the user asks a clarifying question mid-interview, answer it concisely and immediately invoke `ask_question` for the next decision in the same turn (skip `ask_question` only in non-interactive `/goal` or subagent mode).

---

### Phase 1B: Reproduce-First & Browser/Runtime Diagnostic Gate (For Bugs & Regressions)

Bug fixes fail or burn tokens when agents guess from static source without live DOM/container evidence, or when `chrome_devtools` / `/browser` is unavailable (e.g. `npx` missing) and they hand-write repetitive CDP scripts.

When handling **Bucket D**, **NEVER write ad-hoc CDP or Docker inspection scripts from scratch**.
- **Centralized Diagnostic Suite (Recommended)**: If `system-diagnostics` is available (or via `/app-debugger`), run `"<config_dir>/skills/system-diagnostics/scripts/diagnose.py"` (`all`, `ui --live --audit-layout`, `container --sync-check`, `probe run <name>`); see [`references/cli-cheatsheet.md`](./references/cli-cheatsheet.md) for full flags.
- **Self-Contained Bundled Fallback**: When running standalone without sibling skills, execute the built-in cross-platform helpers in `<skill_dir>/scripts/` (`docker_audit.py`, `cdp_inspect.py`) as detailed below.

Execute these 3 steps *before* editing production code:
1. **Runtime, Sync & CPU Audit (`scripts/docker_audit.py` or `diagnose.py container`)**: Check `docker stats --no-stream`, `docker top`, host-vs-container MD5 sync (`--sync-check`), and recent tracebacks in one shot across Windows, macOS, and Linux.
2. **Browser Diagnostic Mode Selection**:
   - **Mode A: Python CDP Inspector (`scripts/cdp_inspect.py`, ~500–1,000 tokens — Default for Layout & Math)**: Deterministic Python `asyncio` audit returning `DOMRect` boxes, styles, and overflow flags (`--url $APP_URL --audit-layout --selectors "<css>"`, plus `--headless`, `--navigate`, `--click`, `--eval-file`, `--screenshot`). Exits non-zero on `{"jsException": ...}`.
   - **Mode B: Interactive `/browser` Agent (`chrome_devtools` MCP, ~5k–20k+ tokens)**: Propose when qualitative visual aesthetics or multi-step UX flows are needed. Pre-Flight if `npx` is missing: check Node.js install, advise IDE/CLI restart or `winget`/`brew` install, and enable Chrome remote debugging + "Allow" prompt.
   - **Pre-Flight Pause / Unverified Rule**: If helpers cannot run or `docker_audit.py` returns `UNVERIFIABLE`, do not fake verification—tell the user what is blocked and mark it "unverified" in the Symptom Matrix (Axiom 9).
3. **Socratic Symptom & Lifecycle Interview (`ask_question`)**: Lock in ambiguous UX/resource policies (e.g., background stream hibernation, auto-resume) *before* coding, then build a **Symptom-to-Root-Cause Matrix** (Symptom → Root Cause → File/Line → Live Check) for **Phase 5**.

---

### Phase 2: Capability, Tooling & Model Tier Scan

Assess whether current capabilities and model tiers are optimal for the goal:
- **MCP & Tool Expansion**: Would an MCP server (e.g., Chrome DevTools, database, Flutter inspector) or a frontier SDK (e.g., Gemini Live bidirectional streaming, local WASM vector search) eliminate custom boilerplate? Search the marketplace (`search_marketplace`) if a missing integration would replace a fragile workaround.
- **Model Tier Strategy**:
  - Use **Gemini Flash + Cognitive Harness** for rapid exploration, subagent research, technical SPIKEs, and iterative vertical slices.
  - If the task hits a deep theoretical bottleneck (e.g., complex distributed consensus proof or subtle multi-threaded deadlock) that resists 2–3 empirical loops, advise scaling up the model tier (or using `/boost`) for that specific bottleneck, while keeping `useG1Credits` enabled in CLI settings if seamless quota overflow is desired.

---

### Phase 3: The 3-Tier SOTA Proposition Engine

For architectural or product decisions, never offer a single default. Present **3 distinct tiers** so the user sees the full landscape of possibilities *(consult [references/sota-patterns.md](./references/sota-patterns.md) for frontier primitives)*:

1. **Tier 1 Pragmatic Baseline**: conventional, fast, familiar; no moat.
2. **Tier 2 Frontier SOTA (Recommended Default)**: current best practice (optimistic UI, streaming, type-safe boundaries); needs discipline.
3. **Tier 3 Novel Moonshot**: paradigm-inverting (local-first CRDT, speculative agents); must be de-risked via a SPIKE.
*(Full tier descriptions & trade-offs: [`references/sota-patterns.md`](./references/sota-patterns.md#3-tier-detail).)*

#### The Pedagogical Inquiry Rule
- Explain advanced concepts in plain, accessible language using concrete analogies.
- **Pause before locking in**: Explicitly invite the user to ask questions about any tier or trade-off before committing to a path:
  > *"Before we lock in our direction, would you like me to unpack how any of these options work under the hood or compare their long-term maintenance?"*

---

### Phase 4: The SPIKE De-risking Protocol

When Tier 2 or Tier 3 introduces an unproven technical assumption, **do not build production scaffolding yet**.
1. Isolate the **Single Riskiest Assumption (SRA)** (e.g., *"Can we stream structured chunks in under 150ms?"*).
2. Write a minimal, self-contained prototype in `<appDataDir>\brain\<conversation-id>/scratch/` *(see [references/spike-protocol.md](./references/spike-protocol.md))*.
3. Run it, measure empirical metrics (latency, memory, accuracy), and report the verdict. Pivot early if it fails; advance to Phase 5 if it passes.

---

### Phase 5: Plan-First Gate, Modularity Budgets & Persistent Project Memory (`AGENTS.md`)

Before modifying production files on any multi-step task *(full contracts & templates: [`references/plan-contracts.md`](./references/plan-contracts.md))*:

1. **Generate an Implementation Plan Artifact (`RequestFeedback: true`)**:
   - Use Markdown checkboxes (`- [ ] **<file_path>**: <action>`) so `plan_engine.py` can parse/patch them.
   - **The 1-Phase-Per-Turn Execution Gate**: Outline the full roadmap (Phase 1..N) with Definitions of Done and User Checkpoints; mark Phase 1 as *Active Execution Target* and Phases 2..N as *Deferred to Next Turn / Milestone*. Record milestones via `python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" changelog add` and pause.
   - **Workspace Plan Engine Registration (Dual-Write & Master Hierarchy)**:
     - Dual-write to `<appDataDir>/brain/<conversation-id>/<slug>.md` (`RequestFeedback: true`) and `<workspace>/.TODO/<slug>.md` (no `ArtifactMetadata`, never call `enter_plan_mode`/`exit_plan_mode`), registered via `python "<skill_dir>/scripts/plan_engine.py" init .TODO/<slug>.md`.
     - **Master Plans of Plans**: Auto-create a Master Roadmap (`<slug>_master_roadmap.md`) + Step 1 child plan (`--parent <master_slug> --milestone 1`) when a roadmap has **`>= 4` milestones**, spans **`>= 3` subsystems** with **`>= 10` tasks**, or requires cross-layer refactoring. Consolidate child plans into **2–3 cohesive milestones** (`~40–70 steps` each; avoid splitting small vertical slices into `>= 4` micro-milestones) and distill subagent findings into `docs/architecture/`.
     - **Master-Step Runtime Wiring Mandate & Frozen-Monolith Signal Adapters**: Pair new coordinators/mappers/services with live runtime wiring (`PipelineEngine`, `CameraPool`, app entrypoints) in the same step; when freezing oversized files, schedule an extracted signal/helper adapter instead of leaving `getattr(..., 0.0)` stubs.
     - **Vertical Slice Parity**: Pair implementation updates with targeted unit tests covering every milestone.
     - **Changelog Task Formulation Invariant**: Never target `MIGRATION_LOG.md`; always use `python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" changelog add`.
   - **Surface Baseline & Delegation Boundary**: Document public routes, schemas, exported symbols, and UI selectors before editing. For deep AST/DOM monolith decomposition, delegate to `/refactor-monolith` (`https://github.com/davtoh/antigravity-skills` if not installed).
   - **Modularity & SRP Budget Gate ("Split-Before-You-Grow")**: Run `diagnose.py audit --path <targets>` before planning. Enforce **350 lines** soft warning / **500 lines** hard ceiling, $\le 10–12$ methods/class, $\le 40$ lines/function, $\le 15–25$ lines/route; calibrate via **Plan Budget Calibration Rule** (`--max-lines <N>`) if `AGENTS.md` is tighter. Never append into files $\ge 350$ lines.
   - **Export-Ready Portable Plan Contract**: Use POSIX repo-relative paths (`src/module/component.js#L94-L105`), zero `file:///` URIs or machine-local paths, OS-agnostic test commands, and an executable **Scenario Combinations Matrix**.
   - **SSOT vs. Zombie Facade Debt**: Zero dead re-export shims; unify duplicate domain logic; verify file vs. directory paths (`os.path.isfile` / `Test-Path`) and root docs (`README.md` vs. `README.rst`, `pyproject.toml`); implement or amend every promised CLI tool before sign-off.
   - Let the user review and approve (or recommend `/plan`) before coding.
2. **Codify Persistent Rules (`AGENTS.md` / `.agents/rules/`)**: Merge ownership, modularity budgets, and test commands into `AGENTS.md` (project rules win on conflict).

---

### Phase 6: Plan Execution, Continuation Engine & Closed-Loop Verification

Execute approved plans in tight, verifiable increments *(harness: [`references/flash-opus-harness.md`](./references/flash-opus-harness.md); sign-off & rubric details: [`references/plan-contracts.md`](./references/plan-contracts.md))*:

1. **Plan Continuation Engine (`/frontier-architect continue [plan_or_slug]`)**:
   - `continue`: Run `python "<config_dir>/skills/frontier-architect/scripts/plan_engine.py" status` and `next` first (never `.frontier/plan_engine.py`, and never manually inspect/edit `.frontier/state.json`).
   - `status` / `lookup`: Surface progress bar, active milestone, baseline, past decisions, and SHAs via `plan_engine.py status` / `lookup`.
2. **Pre-Flight Critic Gate**: Before editing code, audit (1) **Public Surface Invariants & Runtime Types** (schemas, routes, selectors; avoid `| None` on factory functions like `threading.RLock`—use `Optional[Any]` or `from __future__ import annotations`), (2) **Defensive Edge Cases**, (3) **Signature-First Test Rule** (read/`git grep` `__init__` and target methods before writing tests), (4) **Modularity Line Budgets** (350L/500L, $\le 10–12$ methods, $\le 40$L/fn — run `diagnose.py audit --path <target_files>` *before* editing near-limit files/classes so helper extraction is planned upfront rather than discovered via post-edit audit retry loops), and (5) **Scenario Verifiers**.
3. **Execution Sequence & In-Flight Tool Elevation**:
   - **Slice Order**: `Types/Contracts -> Core Logic -> State/Service -> UI Layout -> Styling & Polish`.
   - **In-Flight Tool Elevation Protocol (SSOT)**: Fix skill tool bugs/false positives at their SSOT (`frontier-architect/scripts/` + `tests/` or `system-diagnostics/scripts/` + `tests/`) before resuming app code.
   - **Hygiene & Safety**: Use `<appDataDir>/brain/<conversation-id>/scratch/` only for throwaway SPIKEs/`--eval-file`; never issue parallel `edit_file` calls on one file; run heavy suites async (`WaitMsBeforeAsync: 500`); use **Lightweight Test Fixtures** (synthetic mini-fixtures/mocks); enforce **Mandatory Turn-End Daemon & Task Teardown** (`manage_task kill`); enforce **Persistent State Invariant** (DB/local storage/server cache, never volatile JS `Map`/`Object`).
4. **Closed-Loop Verification Ladder & Second-Check Gate**:
   - **Tier 1 (Static & Tests)**: Run `python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" audit --path <modified_files>` before `unittest` (**Zero Audit Evasion**: never drop a modified file or advance on non-zero exit). Run targeted unit tests before full discovery, then native verifiers (`pytest`, `npm test`, `tsc --noEmit`, `mypy`, `cargo test`). *(Import-probe & Sphinx `-W` rules: [`plan-contracts.md`](./references/plan-contracts.md#3-retrospective-rubric-tier-1-nuances--final-sign-off-phase-6).)*
   - **Tier 2 (Container)**: Verify with `scripts/docker_audit.py --container <name> --sync-check ...` (`IN_SYNC`, zero CPU-spiking orphans).
   - **Tier 3 (Browser)**: Apply **Pre-Flight Pause Protocol** if `$APP_URL` or Chrome debugging ("Allow" banner) isn't ready; run `scripts/cdp_inspect.py --url $APP_URL --audit-layout --selectors "<selectors>"` (or `--eval-file`). Apply **Axiom 9** (*"Live Browser: UNVERIFIED"* if offline).
   - **Second-Check Verification Gate**: Verify interruptibility with `threading.Timer`, grep upstream call-sites for shadowing defaults, and ensure waits/joins occur strictly outside lock blocks.
5. **Anti-Thrash Stop-Loss ($\le 2$ Attempts)**: If a symptom survives two fix attempts, stop editing, revert speculative changes, return to Phase 1B evidence, and escalate to `/app-debugger` or `/boost`.
6. **Milestone Advance & 3-Tier Continuous Learning Loop** *(CLI templates: [`references/cli-cheatsheet.md`](./references/cli-cheatsheet.md))*:
   - **Verify & Advance**: Run `plan_engine.py verify`, then `plan_engine.py advance` to patch `[ ]` $\rightarrow$ `[x]`, record commit SHA, auto-advance any completed child plan's linked parent master milestone (`--no-sync-parent` to opt out), and emit a `git commit` suggestion (obey **Smart Commit Hint Gate**: omit commit command on verification-only milestones). Always echo the `Suggested Commit` block; never run `git add`/`git commit` before `advance` or without consent.
   - **4-Dimensional Retrospective (MANDATORY)**: Run `diagnose.py scan --path <modified_paths>` (on completion) *before* running `plan_engine.py retrospective` sequentially (not in parallel with `advance`) once with `--cid <current_cid>`, `--grade A`, `--retries <n>`, `--steps <n>`, `--tri "5,5,5,5"`, `--hypotheses 1`, `--went-well`, `--learn`, `--skill-learn`, `--tool-gap`, `--escalate` (auto-refreshes `.frontier/plans/<slug>/LEARNING_SCAFFOLD.md`; rubric caps enforced; see [`plan-contracts.md`](./references/plan-contracts.md#3-retrospective-rubric-tier-1-nuances--final-sign-off-phase-6)). For `>60`-step or subagent-heavy runs, run `diagnose.py transcript-audit --latest 1`.
   - **Introspectives & Turn-Termination Gate (MANDATORY)**: Copy-paste the `--- Turn-End Echo ---` (`### Continuous Learning & Introspective Options`) block into your turn-end summary so the user chooses whether to review `LEARNING_SCAFFOLD.md`, run `/learn` (default at Child Plan completion), or run `transcript-audit`. **STOP calling tools immediately** after an intermediate milestone:
     > *"Milestone [N] is verified and complete. Ready to proceed with Milestone [N+1] ([Milestone Title])? Reply to continue or invoke `/frontier-architect continue <slug>`."*
7. **Final Plan Completion Sign-Off (Axiom 8 Safety)**:
   - **Post-Step Integration & Non-Mocked Branch Gate**: Before ticking a Master Step `[x]`, run `diagnose.py scan --path .` (including `tests/`), exercise unconfigured/empty/fallback branches without mocks hiding them, and run `plan_engine.py digest <slug> [--cids <ids>] --backfill --write-scaffold` (and `plan_engine.py digest --all --backfill --write-scaffold` when consolidating multi-plan queues into `.frontier/LEARN_QUEUE.md`; resolve/log all integrity issues, `/learn` candidates, and escalations; check `git log -n 3` / `test_step*_budgets.py`). Never run `diagnose.py scan` *after* `retrospective`/`digest`, or stale defects invalidate telemetry.
   - At 100% completion: run full regression suite, verify zero `file:///` links/secrets and 350/500L compliance, run `diagnose.py changelog add`, echo the `Suggested Commit` block from `advance`/`changelog add` (respecting the Smart Commit Hint Gate), provide `git diff main...plan/<slug>`, surface `LEARNING_SCAFFOLD.md` + Introspective Options, and advise **New Conversation (+)** or `/compact` (or `/frontier-architect continue <parent_slug>`). *(Full checklist: [`plan-contracts.md`](./references/plan-contracts.md#3-retrospective-rubric-tier-1-nuances--final-sign-off-phase-6).)*

---

## Built-In Cross-Platform Helper Scripts & Reference Library

### Scripts (`scripts/`) & References (`references/`)
- `plan_engine.py`: `discover`, `init`, `continue`, `status`, `next`, `advance`, `retrospective`, `lookup`, `verify`, `digest`.
- `cdp_inspect.py` / `docker_audit.py`: thin SSOT shims to `system-diagnostics/scripts/` (`package-skill` materializes standalone `.skill`).
- `references/`: [`cli-cheatsheet.md`](./references/cli-cheatsheet.md), [`plan-contracts.md`](./references/plan-contracts.md), [`triage-protocols.md`](./references/triage-protocols.md), [`flash-opus-harness.md`](./references/flash-opus-harness.md), [`sota-patterns.md`](./references/sota-patterns.md), [`spike-protocol.md`](./references/spike-protocol.md), [`workflow-diagram.md`](./references/workflow-diagram.md).

### Skill Self-Testing & Benchmark Suite (`tests/`)
- **[`tests/README.md`](./tests/README.md)**: Run `python -m unittest discover -s skills/frontier-architect/tests -p "test_*.py"` or `python skills/frontier-architect/tests/run_benchmark.py`. For generative multi-agent benchmarking, invoke `/skill-creator`.
