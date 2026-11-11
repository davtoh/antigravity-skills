---
name: app-debugger
description: >-
  Dedicated end-to-end bug fixing and regression debugging workflow. Use whenever investigating, reproducing, or fixing application bugs, unexpected exceptions, visual UI layout overflows, video clipping, Docker container crashes, broken DOM event handlers, scroll-snap alignment issues, DirectShow/camera hardware locks, or dev server auto-reload loops. Enforces empirical reproduction first via run_diagnose.py and domain probes, interactive Pre-Flight UX selection (Live Chrome vs. Headless vs. Backend), structured Symptom-to-Root-Cause Matrix mapping, and surgical atomic fixes with closed-loop verification. Do NOT use for greenfield system architecture (use frontier-architect) or large file decomposition (use refactor-monolith).
---

# App Debugger: Dedicated Bug Fixing & Regression Suite

The **App Debugger** skill provides an end-to-end, empirical debugging workflow. It eliminates speculative "whack-a-mole" fixes by enforcing reproduction before modification, mapping symptoms to verified root causes, avoiding throwaway scratch scripts via reusable diagnostic probes, and proving resolution via closed-loop diagnostics.

---

## The 5-Step Debugging Workflow

```
[Step 0: Arch Triage] ──> [Step 1: Pre-Flight UX] ──> [Step 2: Reproduce First] ──> [Step 3: Symptom Matrix] ──> [Step 4: Surgical Fix & Verify]
  Pure bug vs. new          ask_question up front       diagnose.py surface/tests/    Map symptom -> cause ->       Atomic code edit & hybrid
  component architecture?   (no 100-step delays)        ui or dynamic probe runner     file/line -> check            lifecycle verification
```

### Step 0: Intelligent Architectural Triage Gate & Co-Invocation Protocol

Before jumping into code, classify the user's request:
- **Pure Bug / Regressed State**: Isolated typo, broken selector, missing null-check, or straightforward layout overflow. Proceed directly to Step 1.
- **Quarantined Defect Remediation**: When resolving defects cataloged in `.diagnostics/defect_catalog.json` (or uncovered via `diagnose.py scan`):
  - Unlock tactical defects via `python skills/system-diagnostics/scripts/diagnose.py scaffold-defect --id <ID> [--branch]`. This synthesizes an empirical failing test in `tests/quarantine/test_<id>.py`. Skip UX interviews and proceed directly to Step 2 to verify failing Red status, followed by surgical fix in Step 4.
  - If classified as `track: architectural` (or unlocked with `--elevate`), yield to `/frontier-architect` + `/grill-me` for holistic architectural redesign instead of applying brittle local band-aids.
- **Architectural Solution or New Component**: The user's prompt combines a bug with a design or subsystem request (e.g., *"Can we create a class to manage all names..."*, *"Should we create a sturdy camera handler..."*).
  - **Enforce Separation of Concerns**: Maintain `app-debugger` for empirical reproduction (Steps 1–3), but **delegate architectural design to `frontier-architect`** or generate a formal **Implementation Plan Artifact** (`RequestFeedback: true`) defining API contracts, trade-offs, and invariants before modifying code.
- **Multi-Skill Co-Invocation Protocol (with `/frontier-architect`)**:
  When the user co-invokes `/app-debugger` and `/frontier-architect` in the same prompt:
  1. **Strict Division of Labor**: `app-debugger` handles empirical diagnosis and reproduction (Steps 1–3) strictly under the Pre-Flight Tool-Call Ceiling ($\le 3-5$ tools).
  2. **Yield Gate**: Once the Symptom-to-Root-Cause Matrix is constructed, `app-debugger` **must yield the floor to `frontier-architect`** to evaluate 3-tier SOTA alternatives, establish API contracts, and draft the formal Implementation Plan Artifact before modifying production code.
  3. `app-debugger` resumes in Step 4 for closed-loop verification after architectural plan approval.

### Step 1: Pre-Flight UX Gate (`ask_question`)

Before running browser diagnostics or when the execution mode is ambiguous, ask the user their preferred inspection environment via `ask_question` **immediately** (do not perform broad codebase sweeps or read dozens of files first):

> [!IMPORTANT]
> **Pre-Flight Tool-Call Ceiling ($\le 3-5$ calls)**:
> Before calling `ask_question`, execute at most **3 to 5 targeted tool calls** (e.g. 1 status check, 1 targeted grep, or 1 device probe). If port, process, or environment ambiguity remains after 3 tool calls, **STOP immediately and present the Pre-Flight UX Gate (`ask_question`)**. NEVER embark on a 50–100 tool exploration marathon, run repetitive ad-hoc Python socket loops, scan ports blindly, or reverse-engineer the entire architecture before presenting the Pre-Flight UX Gate.

- **Option 1 (Recommended)**: `(Recommended) Live Chrome Tab - Attach to active visible browser tab to inspect DOM layout and errors in real time`
- **Option 2**: `Headless Background Sandbox - Run isolated Chrome in the background without disturbing desktop windows`
- **Option 3**: `Backend & Runtime Only - Audit container stats, logs, tracebacks, and tests without browser CDP`

> [!NOTE]
> If the user has already specified the mode in their prompt (e.g., "debug the live tab", "test in headless mode", or "fix container crash"), **skip** `ask_question` and proceed directly to Step 2.

### Step 2: Reproduce First (3-Tier & Dynamic Domain Probes)

Never edit code on speculation. Always establish a reproducible failing baseline using `run_diagnose.py`:

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
   # Live visible tab (with optional settle delay for scroll-snap resting offsets and transitions)
   python skills/app-debugger/scripts/run_diagnose.py ui --live --audit-layout
   python skills/app-debugger/scripts/run_diagnose.py ui --live --wait 2.0 --audit-layout
   # Or isolated headless background
   python skills/app-debugger/scripts/run_diagnose.py ui --headless --audit-layout --screenshot scratch/bug_before.jpg
   ```
4. **Dynamic Domain Probes (Hardware, Databases, Network)**:
   - **Do NOT create throwaway scripts in `scratch/`**.
   - Check available probes:
     ```bash
     python skills/app-debugger/scripts/run_diagnose.py probe list
     ```
   - Run built-in or registered probes (e.g. camera acquisition, device locks):
     ```bash
     python skills/app-debugger/scripts/run_diagnose.py probe run camera_hardware
     ```
   - When a missing domain requires new probing logic:
     - Scaffold a reusable probe: `python skills/app-debugger/scripts/run_diagnose.py probe new <name> --domain <domain>`
     - Or promote a verified script: `python skills/app-debugger/scripts/run_diagnose.py probe save <script> <name>`
5. **Hardware & Device Diagnostic Routing (DirectShow, Webcams, Ports)**:
   - When diagnosing hardware devices (e.g. OpenCV camera indices, DirectShow locks, OBS virtual loops, COM ports, or audio capture), **do NOT invoke browser CDP layout commands (`ui`)**.
   - Execute the project's native status command (e.g. `python scripts/camera_manager.py --status`) or run dynamic domain probes (`run_diagnose.py probe run camera_hardware`).
   - Always run with the project's active virtualenv (let `run_diagnose.py` auto-resolve `.venv`, or invoke `.venv/bin/python` / `.venv/Scripts/python.exe`) to prevent `ModuleNotFoundError: No module named 'cv2'`.
6. **Quarantined Tactical Defect Reproduction (Red-to-Green)**:
   - Unlock the quarantined defect and checkout an isolated micro-branch:
     ```bash
     python skills/system-diagnostics/scripts/diagnose.py scaffold-defect --id DEFECT-001 --branch
     ```
   - Execute the synthesized test to verify it fails (**Red**):
     ```bash
     python -m unittest tests/quarantine/test_defect_001.py
     ```
   - Proceed to Step 3 and Step 4 to apply the surgical fix guided by the defect's `suggested_fix` and re-verify (**Green**).

### Step 3: Symptom-to-Root-Cause Matrix

Before touching code, synthesize findings into a structured matrix that maps every observed symptom to its verified root cause:

> [!IMPORTANT]
> **Filesystem & Target Path Verification**:
> Before entering Target File & Line into the matrix, empirically verify that the target path physically exists as a file (os.path.isfile / Test-Path). Never guess filenames or mistake package directories for source files.

| # | Observed Symptom | Failing Evidence / Traceback | Root Cause Analysis | Target File & Line | Verification Check |
|---|---|---|---|---|---|
| 1 | Player overflows viewport | Bounding width 1600px > 1200px | Missing defensive layout containment (`min-width: 0`) | `static/css/player.css:42` | `run_diagnose.py ui --audit-layout` |
| 2 | Dropdown reset on filter click | ReferenceError: `updateSelect is not defined` | HTML element `#model-select` renamed without updating event listener | `static/js/app.js:115` | `run_diagnose.py surface --show-ids` |
| 3 | Camera acquisition timeout | Processed frames: 0 | `is_physical_camera` rejected UVC webcams returning `-1.0` registers | `intelligent_tracker/video.py:45` | `run_diagnose.py probe run camera_hardware` |

### Step 4: Surgical Atomic Fix & Hybrid Verification

1. **Apply Surgical Edits**:
   - Adhere to Modularity Budgets ($\le$ 350 lines per file, functions $\le$ 30 lines).
   - Fix the identified root causes without side effects or unneeded refactoring.
2. **Execute Environment-Parity & Lifecycle Verification**:
   - Re-run diagnostic commands and domain probes.
   - **Environment Parity**: Never verify solely against synthetic mocks when a live database or hardware device is configured. Test against real configuration states (e.g. existing database embedding dimensions).
   - **Resource Lifecycle Check**: Explicitly verify cleanup (no lingering DirectShow COM locks, leaked sockets, or orphaned background Python processes).
   - **Test Job & Daemon Cleanup Invariant**: Before completing Step 4, query active background tasks (`manage_task list`) and API job ledgers (`GET /api/.../jobs`). Terminate test daemons (`manage_task kill`) and cancel any unfinished test jobs so zero orphan tasks survive into subsequent user turns.
   - **Interactive User Gate**: When confidence is partial, physical hardware is involved, or an operation is sensitive/destructive, provide a 1-line verification recipe and prompt the user to confirm live execution before closing the milestone.
   - **Milestone Recording (Single-Generation Echo Protocol)**: When closing a verified bug fix milestone, record it via `python skills/system-diagnostics/scripts/diagnose.py changelog add --title "<Title>" --type fix --summary "<Summary>" --verify "<Command>"`. Re-use the emitted commit command directly rather than regenerating commit prose.
3. **Report Axiom 9 Honest Verification**:
   - Clearly report each tier as `VERIFIED`, `PARTIALLY_VERIFIED (Synthetic Only)`, or `UNVERIFIED`.

---

## Execution Discipline & Dev Server Safety

1. **Dev Server & File Watcher Safety**:
   - When diagnosing a live web app, be aware that modifying backend or test files in active directories triggers auto-reloaders (`StatReload`, `uvicorn --reload`, `vite`, `nodemon`).
   - Auto-reload cascades abort pending HTTP/WebSocket requests, disrupt running containers, and flood the user with browser permission prompts.
   - **Isolate Test Fixtures**: Keep test fixtures outside watched application trees.
   - **Single-Pass Atomic Edits**: Bundle multi-line edits into a single atomic turn rather than triggering multiple successive reloads.
   - **Headless Sandbox for Multi-Step Audits**: Use `--headless` when running iterative automated layout audits to avoid popping live desktop browser permission banners repeatedly.
2. **Reactive Task Discipline**:
   - Never call `manage_task status` or sleep in a loop. Background tasks wake up the agent reactively upon completion.

---

## Windows Shell & Tooling Resilience

1. **PowerShell Script Policy Bypass**:
   - On Windows, always invoke Node/NPM CLI tools via `cmd /c npx -y <tool> ...` to prevent `npx.ps1 cannot be loaded because running scripts is disabled on this system`.
2. **Codebase Grepping**:
   - Prefer `git grep -n "<pattern>"` over `rg` unless `rg` is explicitly verified in `%PATH%`.
3. **Line Ending & File Editing Safety**:
   - Before applying multi-line `edit_file` replacements on Windows repositories with `core.autocrlf = true`, verify file line endings (CRLF vs LF):
     `python -c "print('CRLF' if b'\r\n' in open('path/to/file','rb').read() else 'LF')"`
   - Match the target line endings exactly in `Target` and `Replacement` strings.
   - Never write disposable Python file-patching scripts in `scratch/` when `edit_file` encounters a whitespace mismatch; inspect the exact context and apply targeted edits.
4. **Virtualenv Auto-Detection & Python Execution**:
   - `run_diagnose.py` automatically resolves workspace virtual environment binaries (`.venv/Scripts/python.exe` on Windows or `.venv/bin/python` on POSIX). When executing custom python one-liners or project scripts directly, resolve the active `.venv` binary rather than bare system `python` to guarantee access to project dependencies.

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
| **Inspect Live Tab with Settle Delay (Scroll-Snap / Resting Offsets)** | Live visible tab | `--live --wait 2.0 --audit-layout` | `python skills/app-debugger/scripts/run_diagnose.py ui --live --wait 2.0 --audit-layout` |
| **Inspect Live Chrome Tab Bug** | Live visible tab | `--live --audit-layout` | `python skills/app-debugger/scripts/run_diagnose.py ui --live --audit-layout` |
| **Capture Pre-Fix Visual Proof** | Headless sandbox | `--screenshot` | `python skills/app-debugger/scripts/run_diagnose.py ui --screenshot scratch/bug_before.jpg` |
| **Audit Specific Failing Elements** | CSS selectors | `--selectors` | `python skills/app-debugger/scripts/run_diagnose.py ui --selectors "#player,.error-banner"` |
| **Inspect File Line Endings Before Edit** | Environment probe | Python one-liner | `python -c "print('CRLF' if b'\r\n' in open('file.py','rb').read() else 'LF')"` |
| **Diagnose Container Crash / CPU** | Docker service | `--lines --sync-check` | `python skills/app-debugger/scripts/run_diagnose.py container --lines 100 --sync-check app.py` |
| **Check AST Surface for Broken IDs** | Source repository | `--show-ids --show-routes` | `python skills/app-debugger/scripts/run_diagnose.py surface --show-ids --show-routes` |
| **Run Virtualenv Unit Test Suite** | Test runner | Auto-detects `.venv` | `python skills/app-debugger/scripts/run_diagnose.py tests` |
| **Full 3-Tier System Health Audit** | Dev server / repo | All tiers | `python skills/app-debugger/scripts/run_diagnose.py all` |
| **List Registered Domain Probes** | Probe registry | Discovers domain probes | `python skills/app-debugger/scripts/run_diagnose.py probe list` |
| **Probe Camera Hardware & Acquisition** | Video capture | Tests DirectShow/V4L2 & locks | `python skills/app-debugger/scripts/run_diagnose.py probe run camera_hardware` |
| **Scaffold Reusable Domain Probe** | Missing domain | Generates boilerplate probe | `python skills/app-debugger/scripts/run_diagnose.py probe new db_pool --domain database` |
| **Promote Scratch Script to Probe** | Verified scratch | Saves script to probe registry | `python skills/app-debugger/scripts/run_diagnose.py probe save scratch/probe.py db_pool` |
| **Unlock Quarantined Tactical Defect** | Quarantined defect | Generates failing Red repro in tests/quarantine/ | `python skills/system-diagnostics/scripts/diagnose.py scaffold-defect --id DEFECT-001` |
| **Unlock Defect & Checkout Micro-Branch** | Quarantined defect | Clean git branch checkout + Red repro test | `python skills/system-diagnostics/scripts/diagnose.py scaffold-defect --id DEFECT-001 --branch` |
| **Polyglot Latent Defect & Smell Scan** | Source repository | Scans across Py, JS/TS, CSS, Dart (SSOT) | `python skills/system-diagnostics/scripts/diagnose.py scan --path src/` |

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

