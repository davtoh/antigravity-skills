# The Flash-to-Opus Cognitive Harness & Context Architecture

This reference details how to orchestrate high-speed models (such as Gemini Flash) to achieve or surpass heavyweight reasoning quality (such as Claude Opus or Gemini Pro) while maintaining superior speed, token efficiency, and empirical reliability.

---

## Table of Contents
1. [Why Fast Models Underperform Without a Harness](#1-why-fast-models-underperform-without-a-harness)
2. [The 5 Mechanisms of the Flash-to-Opus Harness](#2-the-5-mechanisms-of-the-flash-to-opus-harness)
3. [Context Hygiene & Subagent Map-Reduce](#3-context-hygiene--subagent-map-reduce)
4. [Closed-Loop Verification Matrix](#4-closed-loop-verification-matrix)
5. [Tier Escalation: When to Stay on Flash vs. Scale Up](#5-tier-escalation-when-to-stay-on-flash-vs-scale-up)
6. [AGENTS.md Blueprint for Persistent Project Memory](#6-agentsmd-blueprint-for-persistent-project-memory)

---

## 1. Why Fast Models Underperform Without a Harness

Heavyweight models allocate massive internal compute per token to hold implicit multi-file dependency graphs in working memory. High-speed models (like Gemini Flash running at ~250–300+ tokens/sec) optimize for low-latency emission. Without structural guardrails, a fast model may:
- Jump straight into writing code before mapping edge cases or state invariants ("premature implementation").
- Lose track of earlier constraints when the conversation history becomes bloated with raw file dumps and terminal logs ("attention dilution").
- Generate large, monolithic diffs across 10 files at once instead of verifying incremental slices.

**The Insight:** When you force a high-speed model to **externalize its working memory into structured artifacts**, **isolate noisy research in subagents**, and **verify small slices against a real compiler/test runner**, its effective engineering accuracy matches or exceeds a slow monolithic model—in a fraction of the wall-clock time.

---

## 2. The 5 Mechanisms of the Flash-to-Opus Harness

### A. Externalized Pre-Computation (Think-on-Paper First)
Before modifying any production file on a non-trivial task, write an explicit **Architectural Pre-Flight Block** (either in the plan artifact or concisely in chat):
- **Invariants & Global Rules**: What must remain true before and after this change? Verify compliance with global rules (12-Factor zero hardcoded credentials/URLs, the 10 Core Coding Principles, OS-agnostic verification commands, and comment preservation).
- **Modularity & SRP Budget Check**: What is the current line count and class method count of each target file? Enforce the **350-line soft / 500-line hard ceiling per file**, **$\le$ 10–12 methods per class**, and **$\le$ 40 lines per function**. If a target file is already $\ge$ 350 lines, apply the **Split-Before-You-Grow** rule and place new logic in a dedicated submodule.
- **Portable Plan Hygiene (Strict Precedence)**: While generic chat guidelines allow `file:///` links, committable files and implementation plans **must never contain `file:///` links, absolute drive paths, or OS user paths**. Use clean POSIX repo-relative paths (`src/module/file.py#L10-L20`).
- **Data & State Flow**: Source of truth → transformation → sink.
- **Failure Modes**: Network drop, null/empty input, concurrency race, quota limit.
- **OS-Agnostic Verification Command**: The exact cross-platform command (`python -m unittest discover tests`, `pytest`) or browser check that proves it works. Never embed OS-locked virtualenv paths or hidden user customization directories.

*Why it works:* Once these constraints are written into the prompt/artifact context, the model attends to them explicitly while generating code, simulating deep internal reasoning at near-zero latency cost.

### B. Strict Atomic Vertical Slicing
Never build an entire module in one giant pass. Decompose execution into ordered, independently testable micro-slices:
1. **Slice 1 — Contracts & Types**: Interfaces, data schemas, types, and validation rules. *(Verify: Typechecker / Linter)*
2. **Slice 2 — Core Domain Logic**: Pure functions or state machines with zero UI coupling. *(Verify: Fast unit test)*
3. **Slice 3 — Integration / Service Layer**: Storage, API wiring, MCP/tool bindings. *(Verify: Integration smoke test)*
4. **Slice 4 — UI Layout & Structural Wiring**: Component hierarchy and semantic HTML/widgets. *(Verify: Build + DOM/Widget inspection)*
5. **Slice 5 — Styling, Motion & Edge Polish**: Responsive states, loading skeletons, error boundaries. *(Verify: Browser visual check)*

### C. Test-and-Compiler-in-the-Loop (Empirical Grounding)
Never code blind. Treat the local toolchain (`tsc`, `pytest`, `cargo check`, `dart analyze`, `vitest`) as an external reasoning oracle.
- Write a 50-line slice → run the check in 1 second → self-correct immediately if needed.
- Three rapid verified loops on Flash are far more reliable than one unverified single-shot pass on any model.

### D. Subagent Map-Reduce (Protecting Primary Context)
Every raw file read or 500-line stack trace injected into the main thread permanently degrades attention over the rest of the conversation.
- **Delegate Exploration**: When surveying more than 3–4 files or searching external docs, invoke the `research` subagent.
- **Distilled Return**: Instruct the subagent to return *only* exact file paths, line ranges, symbol signatures, and a 10-line architectural synthesis.

### E. Self-Critique & Live Runtime Audit Before User Handoff
Before declaring a task complete, perform a strict adversarial audit of both the diff and the live runtime:
- **Per-Symptom Checklist**: Did I verify *every single* symptom reported by the user against the live running application (not just unit tests)?
- **Container & Asset Sync**: If Docker is running, did I confirm the container is serving the new JS/CSS/Python files (`docker cp` or restart) rather than an old image layer?
- **DOM Bounding-Box & State Proof**: For layout or button-state bugs, did I inspect the live browser via `chrome-devtools` MCP (`evaluate_script` / `take_screenshot`) after a hard reload?
- **Resource & Process Hygiene (`vmmem` / Docker CPU)**: Did I check `docker top` / `docker stats --no-stream` to ensure no orphaned `ffmpeg` jobs, unthrottled video loops, or inactive tab streams are burning CPU in the background?
- **Export & Staging Sanitization**: If saving a plan or updating documentation in the repository, did I audit the files to ensure zero `file:///` URLs, zero machine-local paths, zero OS-locked virtualenv binaries, and zero hardcoded local host/port URLs?
- **Modularity & Line Budget Audit**: Did I verify that all newly created or modified files stay within the 350-line soft / 500-line hard budget, classes stay $\le$ 10–12 methods, and functions stay $\le$ 40 lines?
- **Documentation & Test Preservation**: Did I preserve all existing docstrings/comments and run the unit test suite after my *very last* edit?

---

## 3. Context Hygiene & Subagent Map-Reduce

### Signs of Context Degradation
Watch for these symptoms in long conversations:
- Repeating a mistake that was corrected 10 turns ago.
- Slower time-to-first-token due to massive transcript history.
- Mixing up requirements from an earlier feature with the current feature.

### Active Hygiene Protocol
1. **One Milestone Per Conversation**: When a logical milestone is finished and verified, write the updated state into `AGENTS.md` or the project's milestone log, provide a clean git commit summary, and explicitly advise the user:
   > *"Milestone X is verified and documented. To keep response speed at peak performance and avoid context bloat, I recommend clicking **New Conversation (+)** (or running `/compact`) before starting Milestone Y."*
2. **Artifact Offloading**: Store extensive tables, architecture blueprints, and task checklists in Artifacts (`<appDataDir>\brain\<conversation-id>/`) rather than repeating them in chat responses.

---

## 4. Closed-Loop Verification Matrix

Always match the change type to the right verification mechanism:

| Change Category | Primary Verification (Fast / Sync) | Secondary Verification (Async / Visual) |
| :--- | :--- | :--- |
| **Data Models / Types** | `tsc --noEmit`, `mypy`, `dart analyze`, `cargo check` | Schema unit tests |
| **Business Logic / Algorithms** | Targeted unit test (`pytest path/to/test.py`, `npm test -- filter`) | Property-based or edge-case script in `scratch/` |
| **API / Backend Routes** | Local smoke script or `curl`/`Invoke-RestMethod` check | Background integration suite (`WaitMsBeforeAsync: 500`) |
| **Frontend UI / Web** | Build/bundle check (`npm run build`) | Chrome DevTools MCP (`take_snapshot`, `take_screenshot`, `list_console_messages`) or `/browser` |
| **Flutter / Mobile UI** | `analyze_files` MCP + Widget test | `widget_inspector`, `get_runtime_errors`, `hot_reload` |

> [!IMPORTANT]
> **Asynchronous Heavy Suites**: When an integration test suite, Docker build, or E2E run takes more than 5–10 seconds, launch it as a background task (`WaitMsBeforeAsync: 500` or daemon) so you and the user never block workspace momentum.

---

## 5. Tier Escalation: When to Stay on Flash vs. Scale Up

| Task Profile | Recommended Tier | Rationale |
| :--- | :--- | :--- |
| **Codebase discovery, doc search, file mapping** | **Flash** (via `research` subagent) | High throughput (~300 tok/s); summarizes large repos rapidly. |
| **Iterative vertical slices (UI, CRUD, state, tests)** | **Flash + Cognitive Harness** | Fast edit-test-fix loops outperform slow monolithic generation. |
| **Technical SPIKEs & rapid prototyping** | **Flash** | Quickly tests hypotheses and measures real runtime behavior. |
| **3-Tier SOTA Architecture & Cross-System Synthesis** | **Flash (High Thinking) or Pro / Heavy Model** | Benefits from deeper deliberation when weighing subtle distributed trade-offs. |
| **Subtle multi-threaded race conditions or deep cryptographic/compiler bugs** | **Pro / Heavy Reasoning Tier + `/boost`** | When empirical tests fail after 2–3 structured hypotheses, advise scaling up the model tier or invoking `/boost`. |

---

## 6. `AGENTS.md` Blueprint for Persistent Project Memory

To make every fresh conversation start with instant project mastery, maintain a concise `AGENTS.md` (or `.agents/rules/architecture.md`) at the workspace root:

```markdown
# Project Architecture & Agent Rules

## 1. System Overview & Tech Stack
- **Core Paradigm**: [e.g., Local-first React + SQLite WASM / FastAPI Backend]
- **State Boundaries**: [Where state lives and how it flows]

## 2. Directory Structure & Ownership
- `src/domain/`: Pure business logic & types (zero UI imports allowed)
- `src/services/`: External APIs, storage, MCP adapters
- `src/ui/`: Components, views, styling

## 3. Modularity Budgets & Split-Before-You-Grow
- **File Size Budget**: Soft warning at 350 lines; hard ceiling at 500 lines.
- **Class & Function Budget**: Max 10–12 methods per class; max 40 lines per function; max 15–25 lines per route handler.
- **Monolith Freeze**: Never append new features directly to files $\ge$ 350 lines; extract a domain submodule instead.

## 4. Mandatory OS-Agnostic Verification Commands
- **Typecheck & Lint**: `<exact command>`
- **Fast Unit Tests**: `<exact command>`
- **Full Smoke Test**: `<exact command>`

## 5. Architectural Invariants
- Never bypass the service layer from UI components.
- All state mutations must be optimistic and idempotent.
```
