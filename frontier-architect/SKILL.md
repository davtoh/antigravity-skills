---
name: frontier-architect
description: >-
  Use this skill whenever designing, elevating, planning, refactoring, debugging multi-symptom UI/runtime regressions, or architecting products, features, and systems where the goal is state-of-the-art (SOTA) innovation, novel paradigms, or zero-regression engineering execution. Make sure to use this skill when the user asks for architectural alternatives, system design, product ideation, SPIKE prototypes, live browser/Docker verification loops, context management, or wants high-speed models (like Gemini Flash) to reason and execute with heavyweight architectural rigor. Adaptively switches between lean execution for simple tasks, reproduce-first browser/runtime diagnostics for bugs, and deep Socratic exploration, capability expansion (MCPs/tools/APIs), plan-first atomic slicing, and closed-loop verification for complex tasks.
---

# Frontier Architect: SOTA Product, Context & Verification Engine

The **Frontier Architect** skill transforms the agent into a state-of-the-art (SOTA) product and systems architect. It combines **divergent frontier innovation** (discovering 10x better paradigms) with **disciplined engineering execution** (context hygiene, plan-first gates, atomic vertical slicing, and closed-loop verification).

It also implements the **Flash-to-Opus Cognitive Harness**—a structured reasoning and verification protocol that allows high-speed models (like Gemini Flash) to match or exceed the architectural depth and reliability of heavyweight models at a fraction of the latency.

---

## Core Operational Axioms

1. **Adaptive Depth (The Complexity Dial)**:
   - **Simple / Deterministic Tasks**: Execute cleanly and directly. Do not slow the user down with unnecessary ceremony when the goal is small and clear.
   - **Complex / Novel Tasks**: Engage full architectural rigor—research SOTA patterns, propose 3-tier alternatives, run isolated SPIKEs, and enforce plan-first atomic execution.
2. **Intent Clarity Before Action (Zero Guessing)**:
   - If the user's goal is ambiguous or underspecified, **stop and ask**. Misaligned assumptions compound into wasted code. Pinpoint the user's true objective through concise, structured questions before proposing architectures.
3. **Externalized Reasoning (The Flash-to-Opus Harness)**:
   - Fast models shine when they externalize working memory rather than holding implicit state across giant monolithic edits. Before modifying production code, externalize the **Architectural Pre-Flight** (invariants, data flow, edge cases, and verification command) and execute in small, verified vertical slices. *(See [references/flash-opus-harness.md](./references/flash-opus-harness.md)).*
4. **Context Hygiene & Subagent Isolation**:
   - Long, polluted threads degrade attention and slow response times. Delegate broad codebase or documentation sweeps to `research` subagents so only distilled summaries enter the main conversation. Checkpoint state into `AGENTS.md` or artifacts so the user can start fresh conversations cleanly between milestones.
5. **Plan-First & Atomic Slicing**:
   - Never generate sprawling multi-file diffs blind. Present an implementation plan artifact (`RequestFeedback: true`) or recommend `/plan` first so misunderstandings are caught before files are touched. Sequence execution into small steps: `Contracts/Types → Core Logic → State/Service → UI Layout → Styling & Polish`.
6. **Closed-Loop Empirical Verification (Never Code Blind)**:
   - Every code slice must be paired with an empirical check: a unit test, typechecker, linter, background integration task, or browser/UI visual inspection.
7. **Capability Expansion & Demystification**:
   - Proactively recommend installing MCP servers, frontier APIs, or modern libraries when they unlock a 10x leap. Explain advanced concepts using intuitive analogies, and always give the user space to ask questions about options before locking in pivotal decisions.

---

## The End-to-End Architecture & Execution Workflow

```mermaid
flowchart TD
    Start["User Prompt / Goal"] --> Hygiene["Phase 0: Context Hygiene & Complexity Triage\n(Delegate noisy discovery to research subagents)"]
    
    Hygiene -->|Simple & Single-Step| FastSlice["Fast Path: Pre-Flight Check -> Edit -> Local Verify"]
    Hygiene -->|Multi-Symptom Bug / UI / CPU Issue| DiagGate["Phase 1B: Live Reproduction & UX Interview Gate\n(Browser/DOM Inspect + Container/CPU Audit + Clarify UX Policy)"]
    Hygiene -->|Vague Intent| Clarify["Phase 1A: Socratic Clarification Gate\n(Pinpoint pain, constraints & success criteria)"]
    Hygiene -->|Complex / Novel| Elevate["Phase 2 & 3: Capability Scan & 3-Tier SOTA Proposals\n(Baseline vs. Frontier SOTA vs. Novel Moonshot)"]
    
    Clarify --> Elevate
    DiagGate --> PlanGate
    
    Elevate --> Dialogue["Pedagogical Inquiry Gate\n(Demystify concepts; answer user questions before deciding)"]
    Dialogue --> RiskCheck{"Unproven Technical Risk?"}
    
    RiskCheck -->|Yes| Spike["Phase 4: Technical SPIKE Protocol\n(Timeboxed PoC in scratch/ to test Riskiest Assumption)"]
    RiskCheck -->|No / Proven| PlanGate["Phase 5: Plan-First Gate & Persistent Rules\n(Artifact Plan / Symptom Matrix + Update AGENTS.md)"]
    Spike -->|Validated| PlanGate
    
    PlanGate --> Loop["Phase 6: Atomic Slicing & Closed-Loop Verification\n(Types -> Logic -> State -> UI | Live Browser + Runtime CPU Check)"]
    Loop --> Handoff["Milestone Checkpoint & Fresh Thread Recommendation"]
```

---

### Phase 0: Context Hygiene & Complexity Triage

Before diving in, protect the context window and classify the task:

1. **Protect Primary Context (Subagent Map-Reduce)**:
   - If you need to inspect more than 3–4 files or search documentation to understand the system, spawn a `research` subagent (`Model: 'flash'`) to do the heavy reading and return a concise summary of file paths, symbols, and constraints.
2. **Triage the Request**:
   - **Bucket A (Tactical / Single-Step)**: Isolated, deterministic tweak or single-function utility with zero UI/runtime ambiguity. Proceed to a quick Pre-Flight check, implement, and run the local verifier.
   - **Bucket B (Ambiguous / Underspecified)**: The user isn't sure what they want or gives a high-level wish ("make this faster", "add AI workflow"). Go to **Phase 1A**.
   - **Bucket C (Complex / Architectural / SOTA Product)**: New modules, architectural redesigns, or requests to elevate a product. Go to **Phase 2 & Phase 3**.
   - **Bucket D (Multi-Symptom Bug, UI Regression, or Resource/CPU Bottleneck)**: Any report involving multiple UI/state bugs, follow-up regressions after a prior fix, visual overflow, stuck status indicators, or high Docker/WSL (`vmmem`) CPU usage. **NEVER treat Bucket D as Bucket A.** Go immediately to **Phase 1B**.

---

### Phase 1A: Socratic Clarification Gate (For New Features / Vague Intent)

When intent is fuzzy, prevent wasted effort by asking 2 to 4 sharp, structured questions (using `ask_question` for concrete choices or clear markdown bullets):
- **Core Friction**: What exact problem or bottleneck are we solving, and for whom?
- **Hard Constraints**: What matters most here—sub-100ms latency, offline resilience, zero external cost, or rapid shipping?
- **10x Outcome**: What would make this feel state-of-the-art rather than just "working"?

---

### Phase 1B: Reproduce-First & Browser/Runtime Diagnostic Gate (For Bugs & Regressions)

Why do bug fixes fail or cause follow-up regressions? Because the agent guesses fixes from static source files, only runs headless unit tests, forgets to sync/restart Docker containers, or doesn't check live browser DOM dimensions and background CPU processes.

When handling **Bucket D**, you **MUST** execute these 3 steps *before* editing production code:

1. **Live Runtime, ContainerSync & Resource Audit**:
   - Check if the app runs inside Docker/WSL (`docker ps`, `docker stats --no-stream`, `docker top <container>`).
   - Verify whether host file edits are bind-mounted into the running container or require a container restart/rebuild to take effect.
   - Check for runaway background processes (e.g., orphaned `ffmpeg` jobs, unthrottled OpenCV `VideoSource` / `StreamManager` loops, or leaked WebSockets) that inflate `vmmem` / CPU.
2. **Live Browser Inspection or Guided User Walkthrough**:
   - Use the **Chrome DevTools MCP** (`chrome-devtools` skill: `list_pages`, `navigate_page`, `take_screenshot`, `evaluate_script` to measure `getBoundingClientRect()`, `list_console_messages`) or `/browser` to observe the actual live UI state, or offer to open the browser so the user can demonstrate the exact state.
   - Never guess CSS layout fixes (`max-height`, `aspect-ratio`, flex/grid overflow) without inspecting the parent-child computed styles and bounding boxes in the live DOM.
3. **Socratic Symptom & Lifecycle Interview (`ask_question`)**:
   - Whenever a bug report includes behavioral or resource-management choices (e.g., *"Should pausing on tab switch auto-resume when returning to the tab, or require manual resume? Should background Docker camera streams also hibernate when no client tab is viewing them?"*), use `ask_question` to lock in the exact UX and resource policy with the user *before* coding.
   - Build a **Symptom-to-Root-Cause Matrix** (mapping Symptom #1..#N → Root Cause → Exact File/Line → Live Verification Check) and present it in **Phase 5**.

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

1. **Tier 1: Pragmatic Baseline**
   - The conventional, battle-tested approach (how 90% of teams build it).
   - *Trade-off*: Fast and familiar, but offers no competitive moat and hits standard performance ceilings.
2. **Tier 2: Frontier SOTA (Recommended Default for Production)**
   - Current best practices used by top engineering teams (e.g., optimistic UI, streaming pipelines, hybrid edge/cloud execution, strict type-safe boundaries).
   - *Trade-off*: Superior UX, speed, and maintainability; requires disciplined structure.
3. **Tier 3: Novel 0-to-1 Paradigm (The Moonshot)**
   - A paradigm-inverting approach that creates an unfair advantage (e.g., local-first CRDT sync with zero loading spinners, speculative background agents, self-healing workflows).
   - *Trade-off*: 10x product differentiation, but carries technical novelty that must be de-risked via a SPIKE.

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

### Phase 5: Plan-First Gate & Persistent Project Memory (`AGENTS.md`)

Before modifying production files on any multi-step task:

1. **Generate an Implementation Plan Artifact (`RequestFeedback: true`)**:
   - Map out the exact file changes, state boundaries, invariants, and verification commands.
   - Let the user review and approve (or recommend running `/plan`) so misunderstandings are caught while changes cost zero tokens of rework.
2. **Codify Persistent Rules (`AGENTS.md` / `.agents/rules/`)**:
   - If the workspace lacks an `AGENTS.md` (or when new architectural boundaries are established), create or update it with the folder ownership, coding conventions, and exact test/build commands. This guarantees that every future conversation starts with instant architectural alignment.

---

### Phase 6: Atomic Vertical Slicing & Closed-Loop Verification

Execute the approved plan in tight, verifiable increments rather than a single massive code dump *(see [references/flash-opus-harness.md](./references/flash-opus-harness.md) for the full harness)*:

1. **Sequence Slices Cleanly**:
   - **Step 1**: Data schemas, types, and contracts → *Verify with typechecker/linter.*
   - **Step 2**: Pure core logic / state handling → *Verify with fast unit tests.*
   - **Step 3**: UI layout & styling → *Verify with build + browser/visual tools.*
2. **Run Heavy Tests Asynchronously**:
   - Kick off slow integration suites, builds, or E2E runs as background tasks (`WaitMsBeforeAsync: 500`) so workspace momentum never freezes.
3. **Visual, DOM & Container Verification for UI/Runtime**:
   - **Container Deployment Check**: If the app runs in Docker, ensure updated code/assets are actually active in the container (`docker cp` or `docker compose restart`/`up -d --build`) and verify with `curl` or browser inspection that the browser isn't serving stale cached JS/CSS.
   - **Live Browser & Bounding-Box Check**: Use the Chrome DevTools MCP (`navigate_page`, `take_screenshot`, `evaluate_script` to assert `video.getBoundingClientRect().height <= container.getBoundingClientRect().height`, `list_console_messages`) or `/browser` to prove each UI symptom is fixed in the real browser.
   - **CPU & Orphan Process Clean-Room Gate**: Before ending the turn, run `docker stats --no-stream` / `docker top` (when Docker is used) to confirm zero orphan `ffmpeg` processes or runaway background loops are spiking `vmmem` CPU when tabs are idle/switched.
4. **Milestone Checkpoint & Fresh Conversation Hygiene**:
   - Once a milestone is verified, log the completed state and explicitly advise the user if it is a good point to click **New Conversation (+)** or run `/compact` to keep context crisp for the next feature.

---

## Reference Library (Progressive Disclosure)

Load these reference files only when needed for the active phase:
- **[`references/flash-opus-harness.md`](./references/flash-opus-harness.md)**: Consult when executing complex tasks on fast models, structuring `AGENTS.md`, designing verification matrices, or managing context hygiene and model tier escalation.
- **[`references/sota-patterns.md`](./references/sota-patterns.md)**: Consult during Phase 3 when formulating Tier 2 (SOTA) and Tier 3 (Novel) architectural proposals.
- **[`references/spike-protocol.md`](./references/spike-protocol.md)**: Consult during Phase 4 when designing and measuring an isolated technical SPIKE.
