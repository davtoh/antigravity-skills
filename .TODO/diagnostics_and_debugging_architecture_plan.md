# Architectural Blueprint: Unified Diagnostics & Dedicated App Debugger

## Executive Summary & Design Alignment

Following our interactive `/grill-me` session, we have resolved all architectural dependencies and established a clean separation of concerns across our Antigravity skills:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 HIGH-LEVEL WORKFLOW SKILLS                             │
│                                                                                        │
│  ┌───────────────────────┐  ┌───────────────────────┐  ┌────────────────────────────┐  │
│  │   /app-debugger       │  │  /frontier-architect  │  │    /refactor-monolith      │  │
│  │ (End-to-End Bug Fixes)│  │ (SOTA Architecture &  │  │(Modularity Budgets &       │  │
│  │ • Pre-Flight Gate     │  │  System Design)       │  │ File Decomposition)        │  │
│  │ • Symptom Matrix      │  │ • 3-Tier SOTA Pattern │  │ • AST Contract Parity      │  │
│  │ • Surgical Atomic Fix │  │ • SPIKE Protocols     │  │ • Line Count Ceilings      │  │
│  │ • Closed-Loop Proof   │  │ • Architectural Pre-Fl│  │ • .refactor/state.json     │  │
│  └───────────┬───────────┘  └───────────┬───────────┘  └─────────────┬──────────────┘  │
└──────────────┼──────────────────────────┼────────────────────────────┼─────────────────┘
               │                          │                            │
               ▼                          ▼                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                 CENTRALIZED TOOL POOL & UNIFIED CLI: /system-diagnostics               │
│                                                                                        │
│   Unified Entrypoint: python ~/.gemini/config/skills/system-diagnostics/scripts/       │
│                       diagnose.py <subcommand>                                         │
│                                                                                        │
│   Subcommands:                                                                         │
│   ├── diagnose ui        --> cdp_inspect.py (Headless/Live Chrome, DOM overflow, JS)   │
│   ├── diagnose container --> docker_audit.py (Docker top, CPU stats, sync, traces)    │
│   ├── diagnose surface   --> surface_scanners.py (HTML IDs, Selects, Window, Routes)  │
│   ├── diagnose tests     --> auxiliary_tool_bridge.py (Virtualenv auto-discovery)      │
│   └── diagnose all       --> Unified 3-Tier System Audit in 1 command                  │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Locked Decisions & Core Architecture

| Decision Dimension | Locked Choice | Architectural Rationale |
| :--- | :--- | :--- |
| **Skill Topology** | **Option C**: Two distinct skills (`system-diagnostics` + `app-debugger`) | Cleanly separates the low-level **Evidence Engine** (tools pool) from the high-level **Bug Fixing Workflow**, while freeing `/refactor-monolith` (file splitting) and `/frontier-architect` (system architecture) to focus strictly on their core missions. |
| **Tool Execution** | **Direct Primary Turn Execution** via `run_command` | Zero subagent indirection. Both the user and all skills call `diagnose.py` directly in the active turn, preventing context fragmentation, subagent tool-stripping, and latency. |
| **CLI Architecture** | **Unified Single Entrypoint (`diagnose.py`)** with subcommands | Replaces fragmented multi-script calls with a uniform, discoverable interface: `ui`, `container`, `surface`, `tests`, `all`. |
| **Auto-Discovery** | **Full Auto-Discovery with Flag Overrides** | Auto-probes active dev ports (`8000`, `3000`, `5000`, `8080`), active Docker containers via `docker ps`, and virtualenv Pythons (`.venv`), while supporting explicit flags (`--url`, `--container`, `--path`). |
| **Pre-Flight UX** | **Interactive Pre-Flight Gate (`ask_question`)** | If the user doesn't specify `--live` or `--headless`, `/app-debugger` prompts once between: (1) Live Visible Chrome Tab, (2) Headless Background Sandbox, or (3) Backend/Docker Runtime Only. |
| **Output Format** | **Dual Output Strategy** | Single-step/simple bug fixes receive concise inline markdown responses. Complex or multi-symptom bugs generate a structured Markdown Artifact (`RequestFeedback: true`) containing the Symptom-to-Root-Cause Matrix and before/after verification proof. |
| **Migration & Compatibility** | **Single Source of Truth + Backward-Compatible Shims** | Consolidated scripts pool lives in `skills/system-diagnostics/scripts/`. Lightweight redirect shims remain in `frontier-architect` and `refactor-monolith` so legacy paths never fail with `FileNotFoundError`. |
| **Testing Strategy** | **Automated Unit Test Suite (`test_diagnose.py`)** | Complete test suite covering all CLI subcommands (`ui`, `container`, `surface`, `tests`, `all`), verifiable via `python -m unittest discover tests`. |

---

## 2. Directory Layout & File Responsibilities

```
skills/
├── system-diagnostics/
│   ├── SKILL.md                          <-- Tool manual, CLI recipes & Scenario Matrix
│   ├── scripts/
│   │   ├── diagnose.py                   <-- Unified Single-Entrypoint CLI
│   │   ├── cdp_inspect.py                <-- Browser layout, DOM bounding boxes, JS exceptions
│   │   ├── cdp_transport.py              <-- WebSocket CDP protocol transport
│   │   ├── audit_layout.js               <-- Injected DOM bounding box auditor
│   │   ├── docker_audit.py               <-- Container sync, CPU stats, and tracebacks
│   │   ├── surface_scanners.py           <-- AST/DOM inventory (HTML IDs, selects, globals, routes)
│   │   └── css_inspector.py              <-- CSS layout, overflow, and specificity checks
│   └── tests/
│       ├── __init__.py
│       └── test_diagnose.py              <-- Automated unit test suite
│
├── app-debugger/
│   └── SKILL.md                          <-- 4-step workflow, Pre-Flight gate, Symptom Matrix
│
├── frontier-architect/
│   ├── SKILL.md                          <-- Updated Phase 1B to call diagnose.py
│   └── scripts/
│       ├── cdp_inspect.py                <-- Backward-compatible forwarding shim
│       └── docker_audit.py               <-- Backward-compatible forwarding shim
│
└── refactor-monolith/
    ├── SKILL.md                          <-- Preserved for modularity & file splitting
    └── scripts/
        └── auxiliary_tool_bridge.py      <-- Updated to discover diagnose.py in system-diagnostics
```

---

## 3. Unified CLI Specification (`diagnose.py`)

### Subcommands & Capabilities

```bash
# 1. Live Browser UI & Layout Overflow Inspection
python ~/.gemini/config/skills/system-diagnostics/scripts/diagnose.py ui [OPTIONS]
  --url <URL>           # Target URL (auto-probes localhost 8000/3000/5000/8080 if omitted)
  --live                # Connect to user's active visible Chrome desktop tab
  --headless            # Run isolated background headless Chrome (default)
  --audit-layout        # Check bounding box overflows and horizontal blowout
  --selectors <CSS>     # Specific CSS selectors to measure bounding boxes & styles
  --screenshot <PATH>   # Save visual viewport capture (e.g. scratch/bug.jpg)
  --navigate            # Force fresh page reload before measuring
  --eval <JS>           # Evaluate JS in page context and return result
  --click <SELECTOR>    # Click element before inspection

# 2. Docker Container & Runtime Audit
python ~/.gemini/config/skills/system-diagnostics/scripts/diagnose.py container [OPTIONS]
  --container <NAME>    # Target container (auto-probes active docker ps if omitted)
  --workdir <PATH>      # Container working directory (default: /app)
  --sync-check <FILES>  # Verify host-container MD5 sync for files
  --lines <N>           # Scan recent N log lines for Tracebacks (default: 150)

# 3. Interactive Surface & AST Scanner
python ~/.gemini/config/skills/system-diagnostics/scripts/diagnose.py surface [OPTIONS]
  --path <DIR>          # Workspace root (default: current directory)
  --show-ids            # List all HTML element IDs and interactive select dropdowns
  --show-globals        # List all window.* JavaScript global exports
  --show-routes         # List all backend Python HTTP routes

# 4. Automated Test Runner via Virtualenv
python ~/.gemini/config/skills/system-diagnostics/scripts/diagnose.py tests [OPTIONS]
  --path <DIR>          # Workspace root (auto-discovers .venv/Scripts/python.exe)
  --args <ARGS>         # Extra arguments to pass to unittest/pytest

# 5. Unified 3-Tier Diagnostic Audit
python ~/.gemini/config/skills/system-diagnostics/scripts/diagnose.py all [OPTIONS]
  --path <DIR>          # Workspace root
  --url <URL>           # Optional explicit URL
  --container <NAME>    # Optional explicit container name
  --strict              # Exit with error code if any tier cannot execute
```

---

## 4. Scenario Combinations Matrix

Per `executable_documentation.md`, this matrix pairs user intent with the exact copy-pasteable command:

| Real-World Scenario / Objective | Mode / Inputs | Key Parameters | Exact Runnable Command |
| :--- | :--- | :--- | :--- |
| **Quick Headless Health Audit** | Local dev server | Auto-probes port; background headless | `python ~/.gemini/config/skills/system-diagnostics/scripts/diagnose.py all` |
| **Inspect Active Buggy Chrome Tab** | Live visible tab | Connects via CDP to open tab | `python ~/.gemini/config/skills/system-diagnostics/scripts/diagnose.py ui --live --audit-layout` |
| **Capture Visual Proof of Bug** | Headless sandbox | Viewport render to file | `python ~/.gemini/config/skills/system-diagnostics/scripts/diagnose.py ui --screenshot scratch/bug.jpg` |
| **Verify Docker Container Sync & CPU** | Docker service | Auto-detects container + MD5 sync | `python ~/.gemini/config/skills/system-diagnostics/scripts/diagnose.py container --sync-check app.py static/app.js` |
| **Scan Surface for Broken IDs/Routes** | Source repository | AST parsing without running server | `python ~/.gemini/config/skills/system-diagnostics/scripts/diagnose.py surface --show-ids --show-routes` |
| **Run Test Suite with Local Virtualenv** | Test suite | Auto-detects `.venv` interpreter | `python ~/.gemini/config/skills/system-diagnostics/scripts/diagnose.py tests` |

---

## 5. Implementation Roadmap (Phases 1–5)

- [ ] **Phase 1: Centralize Tools Pool (`system-diagnostics`)**
  - Create directory `skills/system-diagnostics/scripts/`.
  - Migrate/consolidate `cdp_inspect.py`, `cdp_transport.py`, `audit_layout.js`, `docker_audit.py`, `surface_scanners.py`, `css_inspector.py`.
  - Author `diagnose.py` (Unified CLI entrypoint with auto-discovery and subcommands).
  - Create `skills/system-diagnostics/SKILL.md` with instructions, CLI recipes, and Scenario Matrix.

- [ ] **Phase 2: Comprehensive Automated Test Suite**
  - Create `skills/system-diagnostics/tests/test_diagnose.py`.
  - Implement unit tests for `ui`, `container`, `surface`, `tests`, and `all` subcommands using synthetic mocks.
  - Run and verify test suite passes cleanly with zero failures.

- [ ] **Phase 3: Scaffold `/app-debugger` Skill**
  - Create `skills/app-debugger/SKILL.md`.
  - Define the 4-step workflow:
    1. Pre-Flight Gate (`ask_question` for Live vs. Headless vs. Backend).
    2. Reproduce First (`diagnose.py` 3-tier check).
    3. Symptom-to-Root-Cause Matrix (Symptom $\to$ Root Cause $\to$ File/Line $\to$ Check).
    4. Surgical Atomic Fix & Closed-Loop Verification.
  - Integrate Dual Output reporting rules.

- [ ] **Phase 4: Sibling Skill Modernization & Forwarding Shims**
  - In `skills/frontier-architect/scripts/`: add backward-compatible shims for `cdp_inspect.py` and `docker_audit.py`.
  - Update `skills/frontier-architect/SKILL.md` (Phase 1B) to reference `diagnose.py`.
  - In `skills/refactor-monolith/scripts/auxiliary_tool_bridge.py`: update tool discovery to target `system-diagnostics/scripts/diagnose.py`.

- [ ] **Phase 5: Pre-Commit Staging Audit & Final Verification**
  - Verify zero `file:///` URLs or local machine absolute paths in committable files.
  - Verify line count budgets ($\le$ 350-500 lines per file).
  - Run full test suite across the workspace.
