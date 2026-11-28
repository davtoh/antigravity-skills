# Triage Edge Cases & Multi-Skill Co-Invocation Protocols

> *Antigravity vocabulary below; Claude Code users translate it with [`claude-adapter.md`](./claude-adapter.md).*

Consult this reference when handling **Improvement Intent**, **Multi-Skill Co-Invocation**, or **Mixed Requests** in **Phase 0**.

---

## 1. Improvement Intent (`improve`, `enhance`, `refine`, `review`, `elevate`)

1. **Deepen and Detail; Never Simplify**: Make the architecture more detailed, rigorous, and well-thought-out—never flatten or strip technical nuances.
2. **Preserve Contracts**: Keep all concrete parameters, types, contracts, and sub-bullet specifications intact.
3. **Enrich Before Updating**: Add deeper failure recovery, edge cases, lifecycle states, precise method signatures, and modularity invariants before updating the artifact.

---

## 2. Multi-Skill Co-Invocation Protocol

### With `/app-debugger`
1. **Orchestrator of Intent**: `frontier-architect` owns modularity boundaries, API contracts, 3-tier proposals, and the Implementation Plan Artifact.
2. **Tool-Call Ceiling (`<= 3–5` calls)**: Initial clarification/diagnostic gate must execute within 3–5 tool calls—never run a 50–100 tool exploration marathon before engaging the user.
3. **Empirical Handoff**: `app-debugger` runs Phase 1B (diagnostics + Symptom Matrix) under its `<= 5` tool ceiling, then yields to `frontier-architect` for Phase 5 + atomic vertical slicing.

### With `/refactor-monolith`
1. **Single Plan SSOT**: `frontier-architect` designs domain clusters, class boundaries, and 1-phase vertical slices directly in `<workspace>/.refactor/plan.md` and aligns `.refactor/state.json`.
2. **In-Flight Tool Elevation**: Fix skill script bugs/limitations in `<skill_dir>/scripts/` and verify against `<skill_dir>/tests/` before resuming project edits.

---

## 3. Mixed Requests
Split cleanly:
1. Establish the failing empirical baseline and root cause via `app-debugger` / `diagnose.py`.
2. Transition to `frontier-architect` (Phase 2 & Phase 5) for the new architectural component, API contract, and plan artifact before editing production code.

---

## 4. Execution Intent & Handoff Gates (`implement`, `continue`, `execute`, `run`)

1. **Zero-Plan-Re-Read Gate**: On `/frontier-architect continue`, run `plan_engine.py status [slug] --root .` and `next [slug] --root .` (omit `[slug]` to auto-resolve `.frontier/state.json`), AND read [`cli-cheatsheet.md`](./cli-cheatsheet.md) **before** dispatching any `plan_engine.py` shell command (never run `python .frontier/plan_engine.py` in parallel on turn 1) or reading the full plan or source files. Prepend workspace root to repo-relative `read_file` (`Read`) paths; never manually patch checkboxes with `edit_file` (`Edit`), never call `enter_plan_mode`/`exit_plan_mode` (`EnterPlanMode`/`ExitPlanMode`), never issue parallel `edit_file` (`Edit`) calls on one file, and do not emit a duplicate `RequestFeedback: true` (`.TODO/*.md`) artifact.
2. **Plan-Then-Switch-Model Gate (Planning Mode / Handoff Turns)**: When starting in IDE Plan Mode (or on a planning-tier model) or when the user asks to create a plan and pause/switch to an execution model before coding, **STOP immediately after `plan_engine.py init`** with `RequestFeedback: true` (Claude: `.TODO/<slug>.md` + `ExitPlanMode`). Because Antigravity Plan Mode blocks all `write_file` calls via pre-tool hook until `exit_plan_mode`, finish read-only discovery first, embed the **complete verified plan markdown** inside `exit_plan_mode` **once** (never call `write_file` before `exit_plan_mode` and never re-enter Plan Mode), have the execution turn write `.TODO/<slug>.md` + `<appDataDir>/brain/<cid>/<slug>.md` (`RequestFeedback: true`) and run `init` ONLY (zero source-code edits, zero full-suite runs, zero re-reads of subagent-swept files), and after a `> 5`-question `/grill-me` Master Roadmap audit, defer child step plans (`step_1_...`) to a fresh `/frontier-architect continue <master_slug>` turn unless Step 1 touches `<= 15` files.
3. **Master Step Pre-Plan Gate (`MASTER STEP PRE-PLAN GATE`)**: If `next` emits this gate without a `Tactical Master Step` bypass, **DO NOT** implement in one turn. Read `AGENTS.md` + `docs/architecture/`, run `diagnose.py arch-map --path .`, sweep imports via `research` subagent, create `.TODO/step_<N>_<slug>.md` + `RequestFeedback: true` artifact, register with `--parent <master_slug> --milestone <N>`, and include live wiring (`PipelineEngine` / `CameraPool` / entrypoints).
4. **Active Milestone Discovery Hygiene**: Jump to **Phase 6** for the active milestone only; delegate `> 3–4` unfamiliar file sweeps (or any milestone spanning `>= 3` apps/packages) to `research` (`Model: 'flash'`) upfront so main-thread `read_file` stays `< 15` and steps stay `<= 60`. Run full test suites only when targeted tests are missing or at milestone completion.
5. **Context Hygiene & Subagent Isolation**:
   - Never pair `invoke_subagent` with a fast background command and start manual `read_file` sweeps on its early wakeup—wait for the subagent's `SYSTEM_MESSAGE`.
   - Never read a subagent's `transcript.jsonl`, and never poll `manage_subagents list`, `manage_task status`, or `schedule` timers; let reactive wakeup resume execution.
   - Strict **1-Milestone-Per-Turn & Scope Lock**: never implement multiple milestones in one turn, never expand beyond a milestone's planned files without amending the child plan first, and scope follow-up prompts to Milestone 1 only.
