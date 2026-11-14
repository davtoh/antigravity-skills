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

Before diving in, protect the context window, pick up the highest-leverage tools automatically, and classify the task:

1. **Plan Ledger Check & Goal-to-Tool Auto-Dispatch**:
   - **Check Prior Plans First**: On any existing repository, run `python "<config_dir>/skills/frontier-architect/scripts/plan_engine.py" discover --root .` and `status` before broad exploration so recent completed slices are inherited rather than rediscovered.
   - **Auto-Pickup High-Leverage Tools by Goal Signal**:
     - *Architecture / coupling / multi-file change* $\rightarrow$ `diagnose.py arch-map --path .` + `research` subagent (`Model: 'flash'`) for `> 3–4` files.
     - *Web UI / DOM / routes / CSS / layout* $\rightarrow$ `diagnose.py surface --show-ids --show-routes --show-globals` + `diagnose.py ui` (or `/browser` / `chrome_devtools` MCP).
     - *Modularity / latent defects / tests* $\rightarrow$ `diagnose.py audit --path <targets>`, `diagnose.py scan --path <targets>`, `diagnose.py tests`.
     - *Hardware / cameras / DB / external services* $\rightarrow$ `diagnose.py probe list` (or `search_marketplace` for missing MCPs/SDKs).
     - *Post-task introspection* $\rightarrow$ `plan_engine.py digest <slug> --backfill --write-scaffold`, `diagnose.py transcript-audit --latest 1`.
   - **Subagent Map-Reduce**: If inspecting more than 3–4 unfamiliar files, spawn a `research` subagent (`Model: 'flash'`) to return a concise summary of file paths, symbols, and constraints.
2. **Triage the Request**:
   - **Bucket A (Tactical / Single-Step)**: Isolated, deterministic tweak or single-function utility with zero UI/runtime ambiguity. Proceed to a quick Pre-Flight check, implement, and run the local verifier.
   - **Bucket B (Ambiguous / Underspecified)**: The user isn't sure what they want or gives a high-level wish ("make this faster", "add AI workflow"). Go to **Phase 1A**.
   - **Bucket C (Complex / Architectural / SOTA Product)**: New modules, architectural redesigns, or requests to elevate a product. Go to **Phase 2 & Phase 3**.
   - **Bucket D (Multi-Symptom Bug, UI Regression, or Resource/CPU Bottleneck)**: Any report involving multiple UI/state bugs, follow-up regressions after a prior fix, visual overflow, stuck status indicators, or high Docker/WSL (`vmmem`) CPU usage. **NEVER treat Bucket D as Bucket A.** Go immediately to **Phase 1B**.
   - **Bucket E (Plan Implementation Handoff)**: The user provides an existing plan file with execution intent (`implement @[plan.md]`, `/frontier-architect continue [plan]`). Jump directly to **Phase 6 (Plan Execution & Closed-Loop Verification)** to execute Milestone 1 without re-running planning or emitting another plan artifact.
3. **Triage Edge Cases**:
   - **Existing Plan Handoff: Execution vs. Improvement Intent**:
     - **Execution Intent (`implement`, `continue`, `execute`, `run`)**:
       1. **Mandatory Continuation Reflex (Zero-Plan-Re-Read Gate)**: On `/frontier-architect continue`, immediately run `plan_engine.py status <slug>` and `plan_engine.py next <slug>` AND read [`references/cli-cheatsheet.md`](./references/cli-cheatsheet.md) BEFORE reading the full markdown plan or codebase files (`next` outputs the exact active slice; `cli-cheatsheet.md` eliminates `--help` and `scripts/` listing round-trips). When reading files listed in the plan, always prepend the workspace root to repo-relative paths (`read_file` requires absolute paths). Never manually patch plan checkboxes with `edit_file`—let `plan_engine.py advance` maintain the ledger and checkboxes. Do not emit a duplicate plan artifact with `RequestFeedback: true` (which prematurely halts the turn).
       2. **Master Plan Step Detection (`MASTER STEP PRE-PLAN GATE`)**: If `plan_engine.py next` emits `MASTER STEP PRE-PLAN GATE` (master step without a child plan), **DO NOT** implement it in one turn. Run Pre-Plan -> Child Plan: read `AGENTS.md` and `docs/architecture/` blueprints, run `python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" arch-map --path .`, sweep imports via a `research` subagent, create `.TODO/step_<N>_<slug>.md` + `RequestFeedback: true` artifact, and register with `--parent <master_slug> --milestone <N>`. Include a live-wiring task into `PipelineEngine` / `CameraPool` / app entrypoints for any new runtime coordinator or mapper.
       3. **Execute Active Milestone Immediately (With Discovery Hygiene)**: Jump directly to **Phase 6 (Atomic Vertical Slicing)** to implement only the active milestone (consult [`references/cli-cheatsheet.md`](./references/cli-cheatsheet.md) for exact CLI flags). On **every** milestone (Milestone 1, 2, ...), if inspecting `> 3–4` unfamiliar files, delegate the discovery sweep to a `research` subagent (`Model: 'flash'`) instead of reading 20–30+ files directly in the main thread (keep main-thread `read_file` calls for exact edit targets).
       4. Do not run the full workspace test suite unless targeted unit tests are missing or a milestone is completing.
     - **Improvement Intent (`improve`, `enhance`, `refine`, `review`, `elevate`)**:
       1. **Deepen and Detail; Never Simplify**: When explicitly asked to improve or enhance an existing plan, the mandate is to make the architecture **more detailed, rigorous, and well-thought-out**, not to flatten or strip technical nuances.
       2. Preserve all concrete parameters, types, contracts, and sub-bullet specifications.
       3. Enrich the plan with deeper failure recovery, edge cases, lifecycle states, precise method signatures, and modularity invariants before updating the artifact.
   - **Multi-Skill Co-Invocation Protocol (Co-working with `/app-debugger` or `/refactor-monolith`)**:
     When the user invokes `/frontier-architect` alongside `/app-debugger`:
     1. **Orchestrator of Intent**: `frontier-architect` acts as the overall system architect, establishing modularity boundaries, API contracts, 3-tier proposals, and the formal Implementation Plan Artifact.
     2. **Tool-Call Ceiling for Triage ($\le 3-5$ calls)**: The initial clarification or diagnostic gate MUST execute within **3 to 5 tool calls**. Never run a 50–100 tool exploration marathon before engaging the user.
     3. **Empirical Handoff**: `app-debugger` executes Phase 1B (diagnostics and Symptom Matrix) under its $\le 5$ tool ceiling, then yields to `frontier-architect`.
     4. **Plan-First Synthesis**: `frontier-architect` incorporates the Symptom Matrix into Phase 5, defines quantitative modularity limits, and leads atomic vertical slicing.

     When the user invokes `/frontier-architect` alongside `/refactor-monolith`:
     1. **Architectural Roadmap & Single Plan Source of Truth**: `frontier-architect` designs the domain clusters, class boundaries, and 1-phase vertical slices. It writes directly to `<workspace>/.refactor/plan.md` and aligns `.refactor/state.json` so resuming agents execute without plan drift.
     2. **In-Flight Tool Elevation Protocol**: When an executing agent discovers a limitation or bug in an invoked skill tool, the agent enhances the reusable tool script in `<skill_dir>/scripts/` and verifies it against `<skill_dir>/tests/` before resuming project code edits, avoiding disposable scratch scripts and preventing regression thrash.
   - **Mixed requests** (e.g., "fix this bug and also redesign the page", or a bug report asking to build a new class/component): split them cleanly. Maintain strict separation of concerns:
     1. Establish the failing empirical baseline and root-cause analysis via `app-debugger` / `diagnose.py`.
     2. For the new architectural component, class, or subsystem, transition to `frontier-architect` (Phase 2 & Phase 5) to draft the API contract, trade-offs, and implementation plan artifact before touching production code.
   - **Bucket A that grows**: If a "simple" fix touches more than 2–3 files, changes a public interface, or fails its first verification, it wasn't Bucket A. Stop, re-triage, and tell the user the scope changed instead of expanding the diff quietly.
   - **No interactive user** (you're running as a subagent, under `/goal`, or `ask_question` isn't available): you can't use the clarification gates. Pick the most conservative, reversible interpretation, write the assumptions at the top of your output (or in the plan artifact), and don't take any Axiom 8 destructive action—leave those as recommendations for the user.
   - **Read-only or review requests** ("check this", "audit this", "is this right?"): report findings and proposed fixes. Only edit if the user asked for changes, and when you do, keep them minimal and non-destructive.

---

### Phase 1A: Socratic Clarification Gate (For New Features / Vague Intent)

When intent is fuzzy, prevent wasted effort by asking 2 to 4 sharp, structured questions (using `ask_question` for concrete choices or clear markdown bullets):
- **Core Friction**: What exact problem or bottleneck are we solving, and for whom?
- **Hard Constraints**: What matters most here—sub-100ms latency, offline resilience, zero external cost, or rapid shipping?
- **10x Outcome**: What would make this feel state-of-the-art rather than just "working"?
- **Zero-Dangling-Question Invariant**: Never end a turn with a `Question X` heading or interview transition without calling `ask_question` in the **same turn**. If the user asks a clarifying question mid-interview, answer it concisely and immediately invoke `ask_question` for the next decision in the same turn (skip `ask_question` only in non-interactive `/goal` or subagent mode).

---

### Phase 1B: Reproduce-First & Browser/Runtime Diagnostic Gate (For Bugs & Regressions)

Bug fixes fail or burn tokens when agents guess from static source without live DOM/container evidence, or when chrome_devtools//browser is unavailable (e.g. 
px missing) and they hand-write repetitive CDP scripts.

When handling **Bucket D**, **NEVER write ad-hoc CDP or Docker inspection scripts from scratch**.
- **Centralized Diagnostic Suite (Recommended)**: If `system-diagnostics` is available (or when using `/app-debugger` for dedicated bug hunting), invoke the unified CLI via its configuration path:
  ```bash
  python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" all
  # Or target specific subsystems:
  python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" ui --live --audit-layout
  python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" container --container <name> --sync-check <files...>
  # For domain-specific inspections (hardware, databases, network), use the dynamic probe registry:
  python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" probe run camera_hardware
  ```
  *(Where `<config_dir>` is `%USERPROFILE%\.gemini\config` on Windows or `~/.gemini/config` on Linux/macOS).*
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

Before modifying production files on any multi-step task:

1. **Generate an Implementation Plan Artifact (`RequestFeedback: true`)**:
   - Map exact file changes, state boundaries, invariants, and verification commands using Markdown checkboxes:
     `- [ ] **<file_path>**: <action description>` (`plan_engine.py` parses/patches checkboxes; never use plain bullets).
   - **The 1-Phase-Per-Turn Execution Gate (Context Hygiene)**:
     - **Complete Multi-Phase Roadmap Invariant**: Always outline the complete roadmap (Phase 1..N) with explicit Definitions of Done (tests, persistent DB/disk state, zero console errors/orphan processes) and interactive User Checkpoints.
     - **Scoping Immediate Execution**: Mark Phase 1 as *Active Execution Target* and Phases 2..N as *Deferred to Next Turn / Milestone* (`Proceed` authorizes only the active phase). Record milestones via `python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" changelog add` and pause.
   - **Workspace Plan Engine Registration (Dual-Write & Master Plan Hierarchy Contract)**:
     - Dual-write every plan: (1) `<appDataDir>/brain/<conversation-id>/<slug>.md` with `ArtifactMetadata` (`RequestFeedback: true`), and (2) exact same content to `<workspace>/.TODO/<slug>.md` (or `.plans/<slug>.md`) without `ArtifactMetadata`, registered via `python "<skill_dir>/scripts/plan_engine.py" init .TODO/<slug>.md`.
     - **Master Plans of Plans (Automatic Scope Threshold)**: Automatically create a Master Roadmap (`<slug>_master_roadmap.md`) + Step 1 child plan (`--parent <master_slug> --milestone 1`) whenever a roadmap has **`>= 4` milestones**, spans **`>= 3` distinct subsystems/directories** with **`>= 10` tasks**, or requires cross-layer refactoring—never default to a flat plan unless the user explicitly asks for a single-tier plan (`plan_engine.py init` emits `SCOPE RECOMMENDATION (MASTER PLAN)` when this threshold is crossed). Distill subagent file/line findings into `docs/architecture/`.
     - **Master-Step Runtime Wiring Mandate & Frozen-Monolith Signal Adapters**: Any step introducing a new coordinator, mapper, or service MUST pair unit-tested component modules with explicit live runtime constructor/pool/lifecycle wiring (e.g., `PipelineEngine`, `CameraPool`, app startup) in the same step—never leave tested modules disconnected from production entrypoints. When freezing an oversized `WARN`/`HARD` file (e.g., `gallery.py`), explicitly schedule a small extracted signal/helper adapter so upstream producers populate newly introduced downstream attributes rather than leaving duck-typed `getattr(..., 0.0)` stubs that only fire in synthetic unit tests.
     - **Vertical Slice Parity**: Pair implementation updates directly with a targeted unit test covering every milestone's changes rather than deferring testing to a final empty shell.
     - **Changelog Task Formulation Invariant**: NEVER declare milestone tasks targeting raw log files (`MIGRATION_LOG.md`). Always use:
       `- [ ] **CHANGELOG.md**: Record milestone completion via 'python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" changelog add'` (note bare `diagnose.py` is not on PATH; always include its explicit path).
   - **Architectural Invariant & Surface Baseline Inventory**:
     - Identify and document public API routes/payload schemas, exported symbols/types, state machine transitions, and critical UI selectors (`#main-canvas`, `.control-bar`) before editing.
     - **Skill Delegation Boundary for Monolith Decomposition**: For decomposing oversized files/classes with deep AST/DOM contract snapshotting, recommend or delegate to `/refactor-monolith` (available at `https://github.com/davtoh/antigravity-skills` if not installed); otherwise isolate public interfaces, add regression tests first, and split incrementally.
   - **Enforce the Modularity & SRP Budget Gate ("Split-Before-You-Grow")**:
     - Check line/method counts via `python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" audit --path <targets>` before planning edits.
     - **File Budget**: Soft warning at **350 lines**, hard split ceiling at **500 lines**; **Class/Function**: $\le 10–12$ methods (200–300 L), $\le 40$ lines/function, $\le 15–25$ lines/route handler.
     - **Split-Before-You-Grow**: Never plan appending endpoints, DB ops, or UI logic into files $\ge 350$ lines—plan dedicated submodules (`routers/`, `services/`, `repositories/`, `components/`).
     - **Plan Budget Calibration Rule**: If the project's `AGENTS.md` or master plan defines a tighter line ceiling (e.g., `< 300 lines`), calibrate `diagnose.py audit --max-lines <N>` to that threshold—or adopt the project's actual enforced rule instead of emitting unreachable `< 250L` budgets that force premature file splits.
   - **Enforce the Export-Ready Portable Plan Contract**:
     - **Repo-Relative Paths Only**: Use POSIX repo-relative paths (`src/module/component.js#L94-L105`), never machine-local absolute paths or `file:///` URIs inside plans/docs.
     - **OS-Agnostic Verification & 12-Factor Rules**: Use portable commands (`python -m unittest discover tests`, `pytest tests/`, `$APP_URL`), zero OS-locked virtualenv paths or hardcoded hosts/ports, and an executable **Scenario Combinations Matrix**.
   - **Single Source of Truth (SSOT) vs. Zombie Facade Debt**:
     - **Zero Dead Re-Export Shims**: Never create empty unreferenced re-export facades just to satisfy a checklist item.
     - **Unify Duplicate Domain Logic**: Repoint all callers to the authoritative SSOT and delete or 1-line delegate legacy helpers.
     - **Filesystem Verification Before Plan Formulation**: Verify file vs. package-directory paths (`os.path.isfile` / `Test-Path`) and root documentation filenames (`README.md` vs. `README.rst`, `pyproject.toml` `readme` field) before writing plan targets.
     - **Zero Abandoned Plan Tools**: Implement and verify every CLI subcommand/tool promised in the plan or explicitly amend the plan before sign-off.
   - Let the user review and approve (or recommend `/plan`) before coding.
2. **Codify Persistent Rules (`AGENTS.md` / `.agents/rules/`)**:
   - Propose creating/updating `AGENTS.md` (ownership, modularity budgets, test commands) by merging rather than overwriting existing project rules (project rules win on conflict).

---

### Phase 6: Plan Execution, Continuation Engine & Closed-Loop Verification

Execute approved plans in tight, verifiable increments rather than monolithic dumps *(see [references/flash-opus-harness.md](./references/flash-opus-harness.md))*:

1. **The Plan Continuation Engine (`/frontier-architect continue [plan_or_slug]`)**:
   - **Slash Commands**:
     - `/frontier-architect continue [plan_or_slug]`: Resumes execution of any active or discovered markdown plan (`.plans/`, `.TODO/`, `docs/plans/`). **MANDATORY**: Run `python "<skill_dir>/scripts/plan_engine.py" status` and `next` as the first action—never bypass the engine or manually inspect/edit `.frontier/state.json`.
     - `/frontier-architect status [plan_or_slug]`: Displays visual progress bar, active milestone, and baseline via `scripts/plan_engine.py status`.
     - `/frontier-architect lookup <query_or_sha>`: Surfaces past architectural decisions, milestones, commit SHAs, and retrospectives via `scripts/plan_engine.py lookup`.
2. **Mandatory Pre-Flight Critic Gate (The Cognitive Checkpoint)**:
   - Before writing or editing production code in any vertical slice, explicitly audit 4 vectors:
     - **Public Surface Invariants & Runtime Types**: Explicitly document schemas, API contracts, exported types, and DOM selector IDs. In Python, never apply runtime union syntax (`| None`) to factory functions like `threading.RLock` (`TypeError`); use `Optional[Any]` or `from __future__ import annotations`.
     - **Defensive Edge Cases**: Address boundary states, timeouts, missing inputs, network drops, and resource cleanup.
     - **Modularity Line Budgets**: Enforce soft trigger at **350 lines**, hard split ceiling at **500 lines**, $\le 10–12$ methods/class, and $\le 40$ lines/function.
     - **Scenario Verifiers**: Commit to exact runnable command from the plan's Scenario Combinations Matrix.
3. **Execution Sequence & In-Flight Tool Elevation**:
   - **Sequence Slices Cleanly**: Types/Contracts $\rightarrow$ Core Logic $\rightarrow$ State/Service $\rightarrow$ UI Layout $\rightarrow$ Styling & Polish.
   - **In-Flight Tool Elevation Protocol (SSOT)**: When encountering a limitation, false positive (e.g., `static_auditor.py` failing on `Protocol`), or bug in an invoked skill tool, fix it at its authoritative source rather than ignoring it or lowering TRI: for `plan_engine.py`/`plan_parser.py`/`plan_state.py`, update `frontier-architect/scripts/` and run `frontier-architect/tests/`; for shared diagnostic scripts (`cdp_inspect.py`, `cdp_transport.py`, `audit_layout.js`, `docker_audit.py`, `static_auditor.py`, `arch_mapper.py`), update the SSOT in `system-diagnostics/scripts/` and run `system-diagnostics/tests/` before resuming application code.
   - **Tooling Hygiene**: Use `<appDataDir>/brain/<conversation-id>/scratch/` strictly for throwaway Phase 4 SPIKEs or `--eval-file` inputs—never leave `scratch/` in project repositories or vendor skill scripts into `<workspace>/scripts/`.
   - **Serial Same-File Edits**: Never issue multiple parallel `edit_file` calls on one file in a single turn (later `Target`s go stale); merge adjacent edits into one call or apply them sequentially.
   - **Run Heavy Tests Asynchronously**: Kick off slow integration suites or builds as background tasks (`WaitMsBeforeAsync: 500`).
   - **Lightweight Test Fixtures (Zero Compute/Resource Starvation)**: Always use synthetic mini-fixtures, mocks, or sampled data slices instead of full-dataset inferences or multi-gigabyte media conversions during automated verification.
   - **Mandatory Turn-End Daemon & Task Teardown**: Any background daemon, dev server, or support process launched via `run_command` (`IsDaemon: true`) or `manage_task` solely for verification MUST be terminated (`manage_task kill`) before concluding the turn.
   - **Persistent State Invariant vs. In-Memory Shims**: When preserving user state, progress, or job reports across tabs, page reloads, or file navigation, state MUST be backed by persistent storage (database, local storage, or server-side cache), not volatile in-memory JS structures (`Map`, `Object`).
4. **Closed-Loop Verification Ladder & Second-Check Gate**:
   - **Tier 1 (Static & Type Contract Parity)**: Before running `unittest`, run `python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" audit --path <modified_files>` (add `--max-lines <N>` for tighter plan budgets) to catch file, `>40L` function, and `>12` method overruns in one shot. **Zero Audit Evasion**: never drop a modified file from `diagnose.py audit` or advance/sign off a milestone when `diagnose.py audit` exits non-zero—extract a helper immediately. When pruning `arch-map` unused imports, preserve `try/except ImportError` availability probes, and keep Sphinx `.. automodule::` directives in one canonical `.rst` file for `-W` builds. Run targeted unit tests (`-p "test_<module>.py"`) before full-suite discovery, then native verifiers (`pytest`, `npm test`, `tsc --noEmit`, `mypy`, `cargo test`). Use `subprocess.run([sys.executable, ...])` or AST parsing for `sys.modules` / import-boundary tests.
   - **Tier 2 (Container Deployment Check)**: If the app runs in Docker, verify with `scripts/docker_audit.py --container <name> --sync-check ...` that host and container MD5s match (`IN_SYNC`) and zero orphan processes spike CPU.
   - **Tier 3 (Live Browser & Bounding-Box Check)**:
     - **Pre-Flight Pause Protocol**: Check if `$APP_URL` is responding and if Chrome remote debugging requires user approval ("Allow" banner). If not ready, pause and prompt the user via `ask_question` rather than failing blind.
     - Execute `scripts/cdp_inspect.py --url $APP_URL --audit-layout --selectors "<selectors>"` (or `--eval-file <js_path>` for multi-statement DOM probes) to assert DOM bounding boxes, overflow flags, media/button states, and zero console errors.
     - **Axiom 9 Honest Reporting**: If live browser inspection cannot run, state plainly: *"Static Contract: VERIFIED | Live Browser: UNVERIFIED (Server offline or unattached)."* Never report static string assertions as live browser verification.
   - **Second-Check Verification Gate**: Verify interruptibility with active asynchronous cancellation (`threading.Timer`), grep upstream call-sites for shadowing defaults, and audit that blocking waits/joins occur strictly outside lock blocks.
5. **Anti-Thrash Stop-Loss ($\le 2$ Attempts)**:
   - If the same symptom survives two fix attempts, stop editing. Revert or isolate speculative changes, go back to Phase 1B evidence (live DOM, logs, container state), document the failed hypothesis, and escalate to `/app-debugger` or higher model tier (`/boost`).
6. **Milestone Advance & 3-Tier Continuous Learning Loop** *(see [`references/cli-cheatsheet.md`](./references/cli-cheatsheet.md) for exact flags)*:
   - **Verification Baseline**: Run `python "<skill_dir>/scripts/plan_engine.py" verify` (auto-extracts verifiers or pass `--command "<cmd>"`) to record test pass counts.
   - **Advance Milestone & Commit Suggestion**: Run `python "<skill_dir>/scripts/plan_engine.py" advance` to patch checkboxes (`- [ ]` $\rightarrow$ `- [x]`), record the current commit SHA, and emit a copy-pasteable `git commit` suggestion. Never execute `git add` or `git commit` without explicit user consent.
      - **Smart Commit Hint Gate**: If `plan_engine.py advance` reports `(None - Milestone was verification/audit only; no application code changes)`, do not present a commit command in your turn-end message; explain that milestone verification succeeded without requiring code commits.
   - **4-Dimensional Retrospective (MANDATORY on every advance)**: Log telemetry via `python "<skill_dir>/scripts/plan_engine.py" retrospective --grade <A-F> --retries <n> --steps <step_count> --tri "5,5,5,5" --hypotheses <n> --learn "<project_candidate>" --skill-learn "<skill_or_tool_candidate>" --tool-gap "<gap_or_none>" --escalate "<bug>"` (or named `key=score` pairs). Never inflate grades (`plan_engine.py` enforces rubric caps when `--retries >= 2` or `--steps > 60` / `> 100`).
     - Dimensions (positional `5,5,5,5`): *Token Efficiency (1–5)*, *Hypothesis Accuracy (1–5)* ($\le 2$ attempts), *Tool Reliability Index (TRI 1–5)*, and *Architectural Defense (1–5)* (SSOT & modularity adherence).
     - Grading rubric (honest self-assessment): `A` (0–1 retries, $\le 60$ steps), `B` (2–3 retries or 61–100 steps), `C` (>3 retries or >100 steps), `D/F` (repeated thrash or unverified).
   - **Deterministic Telemetry**: Take `--steps`/`--retries` from `python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" transcript-audit --cids <id>` (or pass `--cid <id>` directly to `retrospective`); at plan close run `plan_engine.py digest <slug> --backfill --write-scaffold` instead of a manual post-mortem.
   - **Continuous Learning Feed & User-Selectable Introspectives**: Propose discovered project/skill candidates to `/learn`, and at the end of any completed task or milestone always present a concise **Introspective Options** block telling the user what they can choose to run (e.g., `plan_engine.py digest <slug> --backfill --write-scaffold`, `diagnose.py transcript-audit --latest 1`, or `/learn`) so they decide without surprise token burn.
   - **Turn-Termination Gate & Interactive User Checkpoint (MANDATORY)**: After advancing an intermediate milestone and logging retrospective telemetry, **STOP calling tools immediately**:
     > *"Milestone [N] is verified and complete. Ready to proceed with Milestone [N+1] ([Milestone Title])? Reply to continue or invoke `/frontier-architect continue`."*
7. **Final Plan Completion Sign-Off & Pre-Merge Gate (Axiom 8 Safety)**:
   - **Post-Step Integration & Non-Mocked Branch Gate**: Before ticking a Master Step `[x]`, run `diagnose.py scan --path .` (including `tests/`, not just one subfolder) and exercise unconfigured/empty/fallback branches (`api_key=""`, `None` deps, missing config) without mocks that hide them; then run `plan_engine.py digest <slug> [--cids <ids>] --backfill --write-scaffold` and resolve or log every integrity issue, project/skill `/learn` candidate, and escalation it lists.
   - When all milestones reach 100% (`- [x]`), run the full regression suite, verify zero `file:///` links or secrets and full 350/500-line budget compliance, record the changelog via `python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" changelog add`, provide `git diff main...plan/<slug>`, include the **Introspective Options** summary for the user, and advise clicking **New Conversation (+)** or `/compact`.

---

## Built-In Cross-Platform Helper Scripts & Reference Library

### Scripts (`scripts/`) & References (`references/`)
- `plan_engine.py` (+ `plan_parser.py`, `plan_state.py`, `plan_telemetry.py`, `plan_digest.py`): `continue`, `status`, `next`, `advance`, `retrospective`, `lookup`, `verify`, `digest`.
- `cdp_inspect.py` / `docker_audit.py`: thin SSOT shims to `system-diagnostics/scripts/` (`package-skill` materializes a standalone `.skill`).
- `references/`: [`cli-cheatsheet.md`](./references/cli-cheatsheet.md) (exact commands), [`flash-opus-harness.md`](./references/flash-opus-harness.md), [`sota-patterns.md`](./references/sota-patterns.md), [`spike-protocol.md`](./references/spike-protocol.md), [`workflow-diagram.md`](./references/workflow-diagram.md).

### Skill Self-Testing & Benchmark Suite (`tests/`)
- **[`tests/README.md`](./tests/README.md)**: Run `python -m unittest discover -s skills/frontier-architect/tests -p "test_*.py"` or `python skills/frontier-architect/tests/run_benchmark.py`. For generative multi-agent benchmarking, invoke `/skill-creator`.
