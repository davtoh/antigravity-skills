# Diagnostics, Browser Protocols & Model Tier Strategy

> *Antigravity vocabulary below; Claude Code users translate it with [`claude-adapter.md`](./claude-adapter.md).*

Consult this reference during **Phase 1B (Reproduce-First Bug & Regression Diagnostics)** and **Phase 2 (Capability & Model Tier Scan)**.

---

## 1. Phase 1B: Runtime, Container & Browser Diagnostics

When handling **Bucket D** (multi-symptom bugs, UI regressions, CPU bottlenecks), never write ad-hoc CDP or Docker inspection scripts from scratch:

1. **Centralized Engine vs. Bundled Fallback**:
   - Prefer `python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py"` (`all`, `ui --live --audit-layout`, `container --sync-check`, `probe run <name>`).
   - Standalone fallback scripts live in `<skill_dir>/scripts/`: `docker_audit.py` and `cdp_inspect.py`.
2. **Runtime, Sync & CPU Audit (`docker_audit.py` / `diagnose.py container`)**:
   - Checks `docker stats --no-stream`, `docker top`, host-vs-container MD5 sync (`--container <name> --sync-check <files>`), and recent tracebacks across Windows, macOS, and Linux.
3. **Browser Diagnostic Modes**:
   - **Mode A: Python CDP Inspector (`scripts/cdp_inspect.py`, ~500–1,000 tokens — Default for Layout & Math)**: Deterministic Python `asyncio` audit returning `DOMRect` boxes, styles, and overflow flags (`--url $APP_URL --audit-layout --selectors "<css>"`, plus `--headless`, `--navigate`, `--click`, `--eval-file`, `--screenshot`). Exits non-zero on `{"jsException": ...}`.
   - **Mode B: Interactive `/browser` Agent (`chrome_devtools` MCP, ~5k–20k+ tokens)**: Use when qualitative visual aesthetics or multi-step UX flows are needed. Pre-Flight if `npx` is missing: check Node.js install, advise IDE/CLI restart or `winget`/`brew` install, and enable Chrome remote debugging + "Allow" prompt.
   - **Pre-Flight Pause & Unverified Rule**: Never chain `ui --live` behind another command or background it silently. In an interactive parent session (never in a subagent or `/goal`), either probe `--live --list-tabs` up front or use `--headless` during edits and call `ask_question` before the final `--live` check (and immediately on handshake `TimeoutError`) offering `--live` retry, `--headless` unsupervised fallback, or `UNVERIFIED`. If `docker_audit.py` returns `UNVERIFIABLE`, report honestly per **Axiom 9** (*"Live Browser: UNVERIFIED"*).
4. **Socratic Symptom & Lifecycle Interview (`ask_question`)**:
   - Lock in ambiguous UX/resource policies (e.g., background stream hibernation, auto-resume) *before* coding, then build a **Symptom-to-Root-Cause Matrix** (`Symptom -> Root Cause -> File/Line -> Live Check`) for **Phase 5**.

---

## 2. Phase 2: Capability Expansion and Model Tier Strategy

- **MCP & Tool Expansion**: Check whether an MCP server (Chrome DevTools, database, Flutter inspector) or frontier SDK (e.g., Gemini Live bidirectional streaming, local WASM vector search) eliminates custom boilerplate; use `search_marketplace` when a missing integration would replace a fragile workaround.
- **Model Tier Strategy**:
  - Use the **Executor tier + Reasoning Harness** (Claude: Sonnet + `Explore` agents; Antigravity: Flash `research` subagents for `> 3–4` file sweeps) for rapid exploration, debugging, technical SPIKEs, and iterative vertical slices.
  - Execute already-approved `.TODO/` plans directly in single-agent `Hydrogen` rather than toggling IDE Plan/Execution split mode (which causes redundant re-planning and context reloads).
  - Reserve the **Planner/Reviewer tier** (Claude: Opus; Antigravity: `Orchestrator`/`Neon`) and, for master roadmaps, the **Strategist tier** (Ultra) for upfront `/plan` + `/grill-me` architecture design, final review, or deep theoretical bottlenecks that resist 2–3 empirical loops—never for raw un-delegated file-reading marathons.
