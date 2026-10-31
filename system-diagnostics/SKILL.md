---
name: system-diagnostics
description: >-
  Centralized diagnostics engine for empirical browser UI layout inspection, Docker runtime/CPU audits, AST surface scanning, and automated virtualenv test runs. Make sure to use this skill whenever inspecting DOM bounding boxes, layout overflows, video/canvas element sizing, checking container CPU or host-vs-container file sync, discovering HTML element IDs and backend routes, or performing 3-tier empirical diagnostics before and after code changes across Windows, macOS, and Linux.
---

# System Diagnostics: Centralized Tool Engine & Unified CLI

The **System Diagnostics** skill provides a zero-overhead, project-agnostic diagnostic engine. It consolidates browser layout inspection, container runtime monitoring, AST codebase surface analysis, and test execution into a single, unified command-line interface (`diagnose.py`).

---

## Core Capabilities

1. **Browser UI & Layout Inspection (`diagnose.py ui`)**:
   - Inspects DOM element bounding boxes (`DOMRect`), computed styles, and scroll dimensions via the Chrome DevTools Protocol (CDP).
   - Detects layout overflows, clipped content, and horizontal viewport blowouts with zero Node/npm dependencies (pure-Python RFC 6455 WebSocket transport).
   - Connects to the user's active visible Chrome tab via `DevToolsActivePort` or runs an auto-cleaned temporary headless browser instance.
2. **Docker Runtime & Sync Audit (`diagnose.py container`)**:
   - Snapshots container CPU, Memory, Network I/O, and PIDs (`docker stats --no-stream`).
   - Audits active container processes (`docker top`) to detect runaway CPU loops.
   - Verifies host-vs-container MD5 file synchronization (`--sync-check`) to catch stale mounted files.
   - Scans recent container logs for unhandled Tracebacks and exceptions.
3. **AST Interactive Surface Scanner (`diagnose.py surface`)**:
   - Statically extracts all HTML element IDs, interactive `<select>` dropdowns, and modals.
   - Discovers `window.*` global exports and DOM queries in JavaScript/TypeScript files.
   - Extracts backend Python HTTP routes (`@app.get`, `@app.post`, etc.).
   - Detects CSS custom properties and counts `!important` occurrences to guard specificity.
4. **Automated Test Runner (`diagnose.py tests`)**:
   - Auto-discovers local virtual environment interpreters (`.venv`, `venv`, `env`).
   - Runs unit and integration test suites without requiring manual shell path activations.
5. **Unified 3-Tier Diagnostic Audit (`diagnose.py all`)**:
   - Executes a comprehensive 3-tier audit in one shot: Static Surface/Tests $\to$ Docker Container $\to$ Browser UI Layout.
   - Summarizes results under Axiom 9 (Honest Verification Reporting: `VERIFIED`, `UNVERIFIED`, or `SKIPPED`).

---

## Pre-Run Verification One-Liners

Before executing diagnostic commands on a project, verify the diagnostics test suite:

```bash
# Run the fast automated diagnostic test suite (18 unit tests, < 0.1s)
python -m unittest discover -s skills/system-diagnostics/tests -p "test_*.py"
```

---

## Scenario Combinations Matrix

Per `executable_documentation.md`, use this matrix to match your objective with the exact copy-pasteable command:

| Real-World Scenario / Objective | Mode / Inputs | Key Parameters | Exact Runnable Command |
| :--- | :--- | :--- | :--- |
| **Quick 3-Tier Health Audit** | Dev server / repo | Auto-probes ports & containers | `python skills/system-diagnostics/scripts/diagnose.py all` |
| **Inspect Active Buggy Chrome Tab** | Live visible tab | Attaches via CDP to open tab | `python skills/system-diagnostics/scripts/diagnose.py ui --live --audit-layout` |
| **Capture Headless Visual Proof** | Headless sandbox | Viewport render to file | `python skills/system-diagnostics/scripts/diagnose.py ui --screenshot scratch/bug.jpg` |
| **Inspect Target Selectors** | Specific elements | Measures bounding box & styles | `python skills/system-diagnostics/scripts/diagnose.py ui --selectors "#app,#main-canvas,video"` |
| **Hard Reload & Verify Post-Fix** | Fresh assets reload | Forces page refresh before audit | `python skills/system-diagnostics/scripts/diagnose.py ui --navigate --audit-layout` |
| **Verify Docker Container Sync** | Docker service | Compares host vs container MD5s | `python skills/system-diagnostics/scripts/diagnose.py container --sync-check app.py static/app.js` |
| **Scan Recent Container Tracebacks** | Docker service | Scans recent log lines for panic | `python skills/system-diagnostics/scripts/diagnose.py container --lines 100` |
| **Scan Surface for Broken IDs/Routes** | Source repository | Static AST scan without server | `python skills/system-diagnostics/scripts/diagnose.py surface --show-ids --show-routes` |
| **Export Full Surface Inventory JSON** | Source repository | JSON contract baseline | `python skills/system-diagnostics/scripts/diagnose.py surface --json` |
| **Run Test Suite with Virtualenv** | Test suite | Auto-detects `.venv` interpreter | `python skills/system-diagnostics/scripts/diagnose.py tests` |

---

## CLI Reference & Flags

### Subcommand: `ui`
```bash
python skills/system-diagnostics/scripts/diagnose.py ui [OPTIONS]
```
- `--url <URL>`: Target URL. If omitted, auto-probes local dev ports (`8000`, `3000`, `5000`, `8080`, `5173`).
- `--live`: Attaches to user's active visible Chrome tab.
- `--headless`: Runs in isolated, auto-cleaned temporary headless Chrome (default).
- `--audit-layout`: Scans DOM for bounding box overflows, horizontal scrolling, and `<video>`/`<img>`/`<canvas>` layout issues.
- `--selectors <CSS>`: Comma-separated CSS selectors to measure (e.g. `'#video-player,.control-bar'`).
- `--screenshot <PATH>`: Saves a JPEG viewport screenshot.
- `--navigate`: Forces a page refresh before measuring.
- `--eval <JS>`: Evaluates arbitrary JavaScript expression in page context.
- `--click <SELECTOR>`: Clicks an element before measuring.
- `--window-size <WxH>`: Headless viewport dimensions (default: `1440x900`).

### Subcommand: `container`
```bash
python skills/system-diagnostics/scripts/diagnose.py container [OPTIONS]
```
- `--container <NAME>`: Target container name. If omitted, auto-detects from active `docker ps`.
- `--workdir <PATH>`: Container working directory prefix (default: `/app`).
- `--sync-check <FILES...>`: Relative host files to compare against `<workdir>/<file>` MD5 checksums.
- `--lines <N>`: Recent log lines to scan for unhandled exceptions (default: `150`).

### Subcommand: `surface`
```bash
python skills/system-diagnostics/scripts/diagnose.py surface [OPTIONS]
```
- `--path <DIR>`: Workspace directory to scan (default: current directory).
- `--show-ids`: Prints all discovered HTML element IDs and interactive controls.
- `--show-globals`: Prints all discovered `window.*` global exports in JavaScript/TypeScript.
- `--show-routes`: Prints all discovered backend Python routes.
- `--json`: Outputs structured JSON for automated contracts.

### Subcommand: `tests`
```bash
python skills/system-diagnostics/scripts/diagnose.py tests [ARGS...]
```
- `--path <DIR>`: Workspace root to scan for `.venv` (default: current directory).
- `[ARGS...]`: Arguments forwarded to `python -m unittest` (default: `discover -s tests -p "test_*.py"`).

### Subcommand: `all`
```bash
python skills/system-diagnostics/scripts/diagnose.py all [OPTIONS]
```
- `--path <DIR>`: Workspace directory (default: current directory).
- `--url <URL>`: Explicit dev server URL.
- `--container <NAME>`: Explicit Docker container name.
- `--strict`: Exits with return code 1 if any tier fails.

---

## Architecture & Bundled Scripts

```
skills/system-diagnostics/
├── SKILL.md                          # Tool manual and scenario matrix
├── scripts/
│   ├── diagnose.py                   # Unified CLI entrypoint with auto-discovery
│   ├── cdp_inspect.py                # CDP layout, DOMrect, and overflow inspector
│   ├── cdp_transport.py              # Zero-dependency RFC 6455 WebSocket client
│   ├── audit_layout.js               # Injected DOM bounding box auditor
│   ├── docker_audit.py               # Docker stats, top, and MD5 sync auditor
│   ├── surface_scanners.py           # AST surface parser for HTML/JS/Python/CSS
│   └── css_inspector.py              # CSS layout, overflow, and specificity checks
└── tests/
    └── test_diagnose.py              # 18 automated unit tests for CLI & discovery
```
