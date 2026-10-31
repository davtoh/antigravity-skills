---
name: app-debugger
description: >-
  Dedicated end-to-end bug fixing and regression debugging workflow. Use whenever investigating or fixing application bugs, unexpected exceptions, visual UI layout overflows, video clipping, Docker container crashes, or broken DOM event handlers. Enforces a 4-step workflow: interactive Pre-Flight UX gate (Live Chrome vs. Headless vs. Backend), empirical reproduction first via run_diagnose.py, a structured Symptom-to-Root-Cause Matrix, and surgical atomic fixes with closed-loop verification. Do NOT use for greenfield system architecture (use frontier-architect) or large file decomposition (use refactor-monolith).
---

# App Debugger: Dedicated Bug Fixing & Regression Suite

The **App Debugger** skill provides an end-to-end, empirical debugging workflow. It eliminates speculative "whack-a-mole" fixes by enforcing reproduction before modification, mapping symptoms to verified root causes, and proving resolution via closed-loop diagnostics.

---

## The 4-Step Debugging Workflow

```
[Step 1: Pre-Flight UX Gate] ──> [Step 2: Reproduce First] ──> [Step 3: Symptom Matrix] ──> [Step 4: Surgical Fix & Verify]
  ask_question (Live/Headless/      Capture empirical evidence     Map symptom -> cause ->       Atomic code edit & closed-
  Backend) unless specified         via run_diagnose.py            file/line -> check            loop re-run of diagnostics
```

### Step 1: Pre-Flight UX Gate (`ask_question`)

Before running browser diagnostics or when the execution mode is ambiguous, ask the user their preferred inspection environment via `ask_question`:

- **Option 1 (Recommended)**: `(Recommended) Live Chrome Tab - Attach to active visible browser tab to inspect DOM layout and errors in real time`
- **Option 2**: `Headless Background Sandbox - Run isolated Chrome in the background without disturbing desktop windows`
- **Option 3**: `Backend & Runtime Only - Audit container stats, logs, tracebacks, and tests without browser CDP`

> [!NOTE]
> If the user has already specified the mode in their prompt (e.g., "debug the live tab", "test in headless mode", or "fix container crash"), **skip** `ask_question` and proceed directly to Step 2.

### Step 2: Reproduce First (3-Tier Empirical Evidence)

Never edit code on speculation. Always establish a reproducible failing baseline using `skills/app-debugger/scripts/run_diagnose.py`:

1. **Tier 1 (Surface & Tests)**:
   ```bash
   python skills/app-debugger/scripts/run_diagnose.py surface --show-ids --show-routes
   python skills/app-debugger/scripts/run_diagnose.py tests
   ```
2. **Tier 2 (Container Runtime & Sync)**:
   ```bash
   python skills/app-debugger/scripts/run_diagnose.py container --lines 100 --sync-check <modified_files>
   ```
3. **Tier 3 (Browser UI Layout via CDP)**:
   ```bash
   # Live visible tab
   python skills/app-debugger/scripts/run_diagnose.py ui --live --audit-layout
   # Or isolated headless background
   python skills/app-debugger/scripts/run_diagnose.py ui --headless --audit-layout --screenshot scratch/bug_before.jpg
   ```

### Step 3: Symptom-to-Root-Cause Matrix

Before touching code, synthesize findings into a structured matrix that maps every observed symptom to its verified root cause:

| # | Observed Symptom | Failing Evidence / Traceback | Root Cause Analysis | Target File & Line | Verification Check |
|---|---|---|---|---|---|
| 1 | Player overflows viewport | Bounding width 1600px > 1200px | Missing defensive layout containment (`min-width: 0`) | `static/css/player.css:42` | `run_diagnose.py ui --audit-layout` |
| 2 | Dropdown reset on filter click | ReferenceError: `updateSelect is not defined` | HTML element `#model-select` renamed without updating event listener | `static/js/app.js:115` | `run_diagnose.py surface --show-ids` |

### Step 4: Surgical Atomic Fix & Closed-Loop Verification

1. **Apply Surgical Edits**:
   - Adhere to Modularity Budgets ($\le$ 350 lines per file, functions $\le$ 30 lines).
   - Fix the identified root causes without side effects or unneeded refactoring.
2. **Execute Closed-Loop Verification**:
   - Re-run the exact diagnostic commands from Step 2 to prove the issue is resolved:
     - Layout overflows cleared (`hasOverflow: false`).
     - Tracebacks resolved.
     - Tests passing cleanly.
     - Visual proof captured (`scratch/bug_after.jpg`).
3. **Report Axiom 9 Honest Verification**:
   - Clearly report each tier as `VERIFIED`, `UNVERIFIED`, or `SKIPPED`.

---

## Dual Output Reporting Rules

Depending on the scope of the bug, apply the appropriate reporting pattern:

### 1. Simple / Single-Step Bug
- **Trigger**: Single straightforward symptom and root cause (e.g. typo, broken selector, missing import).
- **Format**: Concise inline Markdown response in chat.
- **Content**: Summary of root cause, surgical code diff, and one-liner verification output. No artifact overhead.

### 2. Complex / Multi-Symptom Bug
- **Trigger**: Multiple symptoms, cross-cutting layers (frontend + container + backend), or layout regressions.
- **Format**: Structured Markdown Artifact in the artifact directory (`RequestFeedback: true`, `UserFacing: true`).
- **Content**:
  - Executive summary and root cause breakdown.
  - Complete Symptom-to-Root-Cause Matrix.
  - Empirical before/after verification evidence (DOMRect measurements, test runs, log diffs).
  - Axiom 9 Honest Verification Matrix.
  - Chat response simply points user to the artifact.

---

## Pre-Run Verification One-Liners

Before starting a debugging session, verify tools readiness:

```bash
# Verify system-diagnostics tool engine resolution
python skills/app-debugger/scripts/run_diagnose.py --probe

# Run app-debugger automated unit and eval tests
python -m unittest discover -s skills/app-debugger/tests -p "test_*.py"
```

---

## Scenario Combinations Matrix

Per `executable_documentation.md`, match user intent with the exact copy-pasteable command:

| Real-World Scenario / Objective | Mode / Inputs | Key Parameters | Exact Runnable Command |
| :--- | :--- | :--- | :--- |
| **Check Tool Engine Readiness** | Diagnostic probe | `--probe` | `python skills/app-debugger/scripts/run_diagnose.py --probe` |
| **Inspect Live Chrome Tab Bug** | Live visible tab | `--live --audit-layout` | `python skills/app-debugger/scripts/run_diagnose.py ui --live --audit-layout` |
| **Capture Pre-Fix Visual Proof** | Headless sandbox | `--screenshot` | `python skills/app-debugger/scripts/run_diagnose.py ui --screenshot scratch/bug_before.jpg` |
| **Audit Specific Failing Elements** | CSS selectors | `--selectors` | `python skills/app-debugger/scripts/run_diagnose.py ui --selectors "#player,.error-banner"` |
| **Diagnose Container Crash / CPU** | Docker service | `--lines --sync-check` | `python skills/app-debugger/scripts/run_diagnose.py container --lines 100 --sync-check app.py` |
| **Check AST Surface for Broken IDs** | Source repository | `--show-ids --show-routes` | `python skills/app-debugger/scripts/run_diagnose.py surface --show-ids --show-routes` |
| **Run Virtualenv Unit Test Suite** | Test runner | Auto-detects `.venv` | `python skills/app-debugger/scripts/run_diagnose.py tests` |
| **Full 3-Tier System Health Audit** | Dev server / repo | All tiers | `python skills/app-debugger/scripts/run_diagnose.py all` |

---

## Architecture & Dynamic Discovery

```
skills/app-debugger/
├── SKILL.md                          # 4-step workflow, Symptom Matrix & Dual Output rules
├── scripts/
│   └── run_diagnose.py               # Dynamic resolver & executor for system-diagnostics
├── evals/
│   └── evals.json                    # 5 realistic evaluation scenarios & expectations
└── tests/
    ├── __init__.py
    ├── test_run_diagnose.py          # Unit tests for dynamic resolver & fallbacks
    └── test_skill_evals.py           # Eval verification test suite
```

