# Triage Edge Cases & Multi-Skill Co-Invocation Protocols

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
