---
name: app-debugger
description: >-
  Dedicated end-to-end bug fixing and regression debugging workflow. Use whenever investigating, reproducing, or fixing application bugs, unexpected exceptions, visual UI layout overflows, video clipping, Docker container crashes, broken DOM event handlers, scroll-snap alignment issues, DirectShow/camera hardware locks, or dev server auto-reload loops. Enforces empirical reproduction first via run_diagnose.py and domain probes, interactive Pre-Flight UX selection (Live Chrome vs. Headless vs. Backend), structured Symptom-to-Root-Cause Matrix mapping, and surgical atomic fixes with closed-loop verification. Do NOT use for greenfield system architecture (use frontier-architect) or large file decomposition (use refactor-monolith).
---

# App Debugger: Dedicated Bug Fixing & Regression Suite

**App Debugger** enforces empirical reproduction before modification, maps symptoms to verified root causes, avoids disposable `scratch/` scripts via reusable probes, and proves fixes via closed-loop diagnostics.

---

## The 5-Step Debugging Workflow

```
[Step 0: Arch Triage] ──> [Step 1: Pre-Flight UX] ──> [Step 2: Reproduce First] ──> [Step 3: Symptom Matrix] ──> [Step 4: Surgical Fix & Verify]
  Pure bug vs. new          ask_question up front       run_diagnose.py /             Map symptom -> cause ->       Atomic code edit & hybrid
  component architecture?   (<= 3-5 tool calls)         dynamic probe runner          file/line -> check            lifecycle verification
```

### Step 0: Intelligent Architectural Triage Gate & Co-Invocation Protocol

> [!NOTE]
> **Cross-Conversation Context Inheritance**: Check existence first (`Test-Path .frontier/DEBUG_RETRO.md; Test-Path .diagnostics/DEBUG_RETRO.md` or `ls`) before calling `read_file`—read the last 3 entries if present (prefer `.frontier/DEBUG_RETRO.md`) to avoid `read_fail` turns. From a product workspace, prefix `<config_dir>/` (`%USERPROFILE%\.gemini\config` on Windows, `~/.gemini/config` on POSIX) before `skills/...`.

Classify the request before editing:
- **Pure Bug / Regressed State**: Isolated typo, broken selector, null-check, or layout overflow $\rightarrow$ **Step 1**.
- **Quarantined Defect Remediation** (`.diagnostics/defect_catalog.json`): Unlock tactical defects via `diagnose.py scaffold-defect --id <ID> [--branch]` (synthesizes `tests/quarantine/test_<id>.py`), skip UX interviews, verify failing **Red** in Step 2, and fix in Step 4. If `track: architectural` (or `--elevate`), yield to `/frontier-architect` + `/grill-me`.
- **Architectural Solution / Multi-Skill Co-Invocation (with `/frontier-architect`)**:
  1. **Division of Labor**: `app-debugger` owns empirical reproduction (Steps 1–3) strictly under the **Pre-Flight Tool-Call Ceiling ($\le 3–5$ calls)**.
  2. **Yield Gate**: Once the Symptom-to-Root-Cause Matrix is built, **yield the floor to `frontier-architect`** for 3-tier SOTA design, API contracts, and formal Implementation Plan Artifact (`RequestFeedback: true`) before production edits.
  3. **Mid-Plan Escalation Bridge**: When invoked from `/frontier-architect` Phase 6.5 (`>= 2` failed attempts), read `.frontier/plans/<slug>/` contracts and pass `--plan <slug>` to `run_diagnose.py debug-retro`.

### Step 1: Pre-Flight UX Gate (`ask_question`)

> [!IMPORTANT]
> **Pre-Flight Tool-Call Ceiling ($\le 3–5$ calls)**: Locate paths via `git grep -n` or `surface --show-routes` first (never guess `read_file` paths or endpoints); delegate `> 3–4` file sweeps to `research` (`Model: 'flash'`). If mode/environment ambiguity remains after 3 calls, **STOP and call `ask_question` immediately** (no 50–100 tool sweeps or blind port loops). Cap third-party library inspection at $\le 3$ probes.

Present mode options when unspecified:
- `(Recommended) Live Chrome Tab - Attach to active visible browser tab to inspect DOM layout and errors in real time`
- `Headless Background Sandbox - Run isolated Chrome in the background without disturbing desktop windows`
- `Backend & Runtime Only - Audit container stats, logs, tracebacks, and tests without browser CDP`

> [!NOTE]
> If the user already specified the mode (e.g., `"debug the live tab"`, `"headless"`, `"container"`), **skip** `ask_question` and proceed to Step 2. Inside subagents or `/goal` (no user access), never call `ask_question`—use `--headless` or report `UNVERIFIED`. In an interactive parent coordinator, never chain `ui --live` behind another command or background it silently; probe `ui --live --list-tabs` upfront or run `--headless` during edits and call `ask_question` before `--live` (and on handshake `TimeoutError`).

### Step 2: Reproduce First (3-Tier & Dynamic Domain Probes)

Establish a failing baseline with `run_diagnose.py` before editing *(full command matrix & examples: [`references/command-matrix.md`](./references/command-matrix.md))*:

1. **Tier 1 (Surface & Tests)**:
   - `python skills/app-debugger/scripts/run_diagnose.py surface --show-ids --show-routes` (detects broken IDs, selectors, event listeners, routes).
   - `python skills/app-debugger/scripts/run_diagnose.py tests` and targeted runs `python skills/app-debugger/scripts/run_diagnose.py tests tests.test_mod1 tests.test_mod2` (enforces `180s --timeout` guard against hangs).
   - **Virtualenv Auto-Detection**: `run_diagnose.py` auto-resolves `.venv` (`.venv\Scripts\python.exe` / `.venv/bin/python`). Never invoke bare system `python`/`python3` when `.venv` exists.
2. **Tier 2 (Container Runtime & Sync)**:
   - `python skills/app-debugger/scripts/run_diagnose.py container --lines 100 --sync-check <files>` (checks tracebacks, CPU, and host-vs-container MD5 drift).
3. **Tier 3 (Browser UI & CDP)**:
   - `run_diagnose.py ui --live --capture-runtime --audit-layout`, `--wait 2.0` (scroll-snap / resting offset settle), `--selectors`, `--eval-file scratch/probe.js`, or `--headless --screenshot scratch/bug_before.jpg`.
4. **Dynamic Domain Probes & Hardware Diagnostic Routing**:
   - **Discover Workspace Probes First**: Always run `run_diagnose.py probe list` in Step 2 to discover project-specific probes in `.diagnostics/probes/` (and global probes), and execute relevant ones via `run_diagnose.py probe run <name>` before writing ad-hoc checks.
   - Avoid disposable `scratch/` scripts: use `probe new <name> --domain <domain>` and `probe save <script> <name>`.
   - **Hardware & Device Diagnostic Routing**: For DirectShow locks, OpenCV indices, COM ports, or audio capture, **do NOT invoke browser `ui` CDP**—run native device status or `probe run camera_hardware` under `.venv`.
5. **Quarantined Tactical Defect (Red-to-Green)**: Run `diagnose.py scaffold-defect --id DEFECT-001 --branch` and verify Red failure in `tests/quarantine/test_defect_001.py`.

### Step 3: Symptom-to-Root-Cause Matrix

Verify every target path exists (`os.path.isfile` / `Test-Path`) before filling the matrix. If ending at Step 3 without edits (RCA-only, `>= 30` steps, or RCA saved to `.TODO/`/`.diagnostics/`), run `debug-retro --status unconfirmed --cid <cid>` and emit `### Continuous Learning & Introspective Options` before ending the turn.

| # | Observed Symptom | Failing Evidence / Traceback | Root Cause Analysis | Target File & Line | Verification Check |
|---|---|---|---|---|---|
| 1 | Player overflows viewport | Bounding width 1600px > 1200px | Missing defensive layout containment (`min-width: 0`) | `static/css/player.css:42` | `run_diagnose.py ui --audit-layout` |
| 2 | Submit / filter error | `ReferenceError` on click | HTML ID `#model-select` changed without updating event listener | `static/js/app.js:115` | `run_diagnose.py surface --show-ids` |

### Step 4: Surgical Atomic Fix & Hybrid Verification

1. **Surgical Edits & SSOT Escalation**: Adhere to Modularity Budgets ($\le 350$ lines/file, $\le 30$ lines/fn) and defensive CSS containment (`min-width: 0`, overflow containment). If `git grep` shows `>= 3` files owning the same state or 1 patch fails live verification, **STOP** and yield to `/frontier-architect` for an SSOT contract.
2. **Environment-Parity & Lifecycle Verification**:
   - Re-run diagnostics (`--capture-runtime`, `hasOverflow: false`, `tests`). Never rely solely on synthetic mocks, blank `--headless` profiles, or `now=100.0` stubs—verify real-clock **single clock-domain parity** (`time.monotonic()` vs `time.time()`) and clean resource release.
   - **Test Job & Daemon Cleanup**: Query `manage_task list` and kill test daemons (`manage_task kill`) before finishing.
   - **Pending User-Verification Gate**: For interactive UI/live-browser/hardware bugs (or retry $\ge 1$), report `"Patch Applied — Ready for Live Verification"` and confirm via `--live` or 1-click `ask_question` before running `diagnose.py changelog add` or claiming `"FIXED"`.
3. **Axiom 9 Reporting, `debug-retro` & Continuous Learning**:
   - Report each tier honestly (`VERIFIED`, `PARTIALLY_VERIFIED (Synthetic Only)`, or `UNVERIFIED`).
   - For non-trivial sessions (`>= 20` steps, `>= 1` retry, or Mac/cross-platform RCA), execute in exact order: (1) `run_diagnose.py debug-retro --symptom ... --cause ... --status <verified|unconfirmed> --cid <cid>` (pass `--plan <slug>` to auto-persist `followup_cids` and backfill `LEARNING_SCAFFOLD.md`; updates `DEBUG_RETRO.md` and `LEARN_QUEUE.md`, and prints `--- Turn-End Echo ---`), then (2) `diagnose.py transcript-audit --latest 1 --workspace .` (never run `transcript-audit` or `digest` *before* `debug-retro`), and echo `### Continuous Learning & Introspective Options` (`transcript-audit`, `plan_engine.py digest`, `/learn`).
   - Promote reusable CDP/runtime scripts into Chrome-gated `tests/test_*_e2e*.py` tests or `run_diagnose.py probe save` rather than leaving them in `scratch/`.

---

## Operational Guardrails, Dual Output & References

*(Full protocols: [`references/environment-and-reporting.md`](./references/environment-and-reporting.md); full 17-scenario matrix: [`references/command-matrix.md`](./references/command-matrix.md).)*

- **Dev Server & Watcher Safety**: When `StatReload` / `uvicorn --reload` / `vite` is active, isolate test fixtures, batch **single-pass atomic edits**, use `--headless` for iterative layout audits to avoid repeated permission popups, and follow **reactive task discipline** (never poll `manage_task status`).
- **Windows & File Hygiene**: Use `cmd /c npx -y ...`, `git grep -n`, inspect `CRLF` vs `LF` line endings before multi-line edits, and never write disposable `scratch/` file-patching scripts on whitespace mismatches.
- **Dual Output Rules**: Simple single-step bugs $\rightarrow$ concise **inline Markdown** (no artifact overhead); complex multi-symptom bugs $\rightarrow$ **Markdown Artifact** (`RequestFeedback: true`, `UserFacing: true`) with Symptom Matrix and Axiom 9 verification.
