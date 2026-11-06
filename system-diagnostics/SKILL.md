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
6. **Dynamic & Extensible Probes (`diagnose.py probe`)**:
   - Discovers, runs, scaffolds, and promotes reusable domain probes (e.g., `camera_hardware`, databases, sockets) across global and workspace `.diagnostics/probes/` registries.
   - Eliminates disposable scratch script sprawl: agents test domain-specific logic and promote working checks into permanent diagnostic tools via `diagnose.py probe save`.
   - Built-in `camera_hardware.py` probe tests DirectShow, Media Foundation, and V4L2 device indices, validates pixel frame decoding without crashing on `-1.0` register queries, and audits Windows PnP device states.
7. **Static Quality, Defect & Code Smell Audit (`diagnose.py audit`)**:
   - Executes virtualenv-native static typecheckers (`ruff`, `mypy`, `pyright`, `dart analyze`) on target paths or whole repositories.
   - Detects dynamic platform import ladder smells (`try...except ImportError` on platform libraries like `win32api`, `fcntl`, `_xlmac`) and recommends static platform guards (`if sys.platform == 'win32':`).
   - Runs callable smoke tests to verify module importability, signature validity, and catch constructor `TypeErrors` before runtime.
   - **Strict Token-Budget Guard**: Automatically truncates error output to the top 5 defects per checker/category, preventing context window explosion during AI agent interactions.
8. **Polyglot Defect Scanner & JIT Scaffolder (`diagnose.py scan` & `diagnose.py scaffold-defect`)**:
   - Statically scans across Python (AST), JavaScript/TypeScript, CSS/SCSS, and Dart for 12+ classes of latent defects, smells, resource leaks, and vulnerabilities.
   - Computes deterministic Dual-Key identifiers: sequential `DEFECT-XXX` + AST symbol/arity content fingerprint (`DEF-<RULE>-<6HEX>`), maintaining identity stability across file moves and line shifts.
   - Persists ground truth in the workspace's Single Source of Truth (SSOT) catalog: machine-readable `<workspace>/.diagnostics/defect_catalog.json` and human-readable `DEFECT_CATALOG.md` (protected by auto-generated `.gitignore`).
   - Dispatches **Dual-Track Remediation**:
     - **Track A (Tactical)**: Generates self-contained Red-to-Green tests in `tests/quarantine/test_<id>.py` with optional micro-branching (`--branch`) guarded by git dirty-tree safety checks.
     - **Track B (Architectural)**: Emits structured Architectural Elevation Briefs for `/frontier-architect` + `/grill-me` when defects reveal structural design flaws.
9. **Unified Changelog & Auto-Archiving Engine (`diagnose.py changelog`)**:
   - Manages bounded, zero-read-token changelogs (`CHANGELOG.md`) capped at $\le 150$ lines with entry-boundary safety (min 3 entries kept).
   - Declaratively sanitizes local paths, `file:///` URIs, `.venv` references, and localhost ports via `SANITIZATION_RULES`.
   - Auto-migrates legacy `MIGRATION_LOG.md` files, merges distinct entries without data loss, and auto-shards historical entries into `.changelogs/changelog_YYYY_H1.md` / `H2.md` with explicit AI-guard banners.
   - Implements the Single-Generation Echo Protocol (`--commit-hint`) to emit copy-pasteable `git commit` commands directly from CLI arguments, cutting milestone completion token overhead in half.

---

## Pre-Run Verification One-Liners

Before executing diagnostic commands on a project, verify the diagnostics test suite:

```bash
# Run the comprehensive diagnostic test suite (105 unit & integration tests, < 3.5s)
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
| **List Registered Probes** | Probe registry | Discovers global & workspace probes | `python skills/system-diagnostics/scripts/diagnose.py probe list` |
| **Probe Camera Hardware & Locks** | Physical/virtual video | Probes backends, decoding & locks | `python skills/system-diagnostics/scripts/diagnose.py probe run camera_hardware` |
| **Scaffold New Domain Probe** | Missing domain | Generates protocol boilerplate | `python skills/system-diagnostics/scripts/diagnose.py probe new db_pool --domain database` |
| **Promote Scratch Script to Probe** | Verified scratch | Saves script to reusable registry | `python skills/system-diagnostics/scripts/diagnose.py probe save scratch/check_db.py db_pool` |
| **Static Defect & Type Audit** | Source repository | Runs venv ruff/mypy (top-5 capped) | `python skills/system-diagnostics/scripts/diagnose.py audit --path src/` |
| **Detect Platform Import Smells** | Source repository | Flags dynamic try..except ladders | `python skills/system-diagnostics/scripts/diagnose.py audit --smells` |
| **Callable Smoke & Init Check** | Source repository | Checks signatures & constructor TypeErrors | `python skills/system-diagnostics/scripts/diagnose.py audit --callable-smoke` |
| **Export Static Defect JSON** | Source repository | Full machine-readable audit report | `python skills/system-diagnostics/scripts/diagnose.py audit --json` |
| **Polyglot Latent Defect Scan** | Source repository | Scans Py, JS/TS, CSS, Dart (SSOT catalog) | `python skills/system-diagnostics/scripts/diagnose.py scan --path src/` |
| **Deep Scan with CSS & Extended AST** | Source repository | Full polyglot rules + specificity leaks | `python skills/system-diagnostics/scripts/diagnose.py scan --path src/ --deep` |
| **Strict CI Defect Gate** | CI / Pre-commit | Returncode 1 if any defects found | `python skills/system-diagnostics/scripts/diagnose.py scan --strict` |
| **Unlock Tactical Defect (Test Synthesis)** | Quarantined defect | Generates Red repro in tests/quarantine/ | `python skills/system-diagnostics/scripts/diagnose.py scaffold-defect --id DEFECT-001` |
| **Unlock Tactical Defect + Micro-Branch** | Quarantined defect | Clean git checkout + Red repro test | `python skills/system-diagnostics/scripts/diagnose.py scaffold-defect --id DEFECT-001 --branch` |
| **Elevate Structural Defect to Architecture**| Quarantined defect | Emits brief for /frontier-architect | `python skills/system-diagnostics/scripts/diagnose.py scaffold-defect --id DEFECT-002 --elevate` |
| **Record Milestone & Emit Commit Snippet** | Any repo (auto-migrates legacy log) | `--title --type --summary --verify` | `python skills/system-diagnostics/scripts/diagnose.py changelog add --title "Worker Split" --type refactor --summary "SRP decomposition" --verify "pytest (45 passed)"` |
| **Auto-Migrate Oversized MIGRATION_LOG.md** | Legacy repo migration | `--path --max-lines 150` | `python skills/system-diagnostics/scripts/diagnose.py changelog migrate --path . --max-lines 150` |
| **Custom Source/Target Log Names** | Custom file override | `--source-log --target-log` | `python skills/system-diagnostics/scripts/diagnose.py changelog migrate --source-log HISTORY.md --target-log CHANGELOG.md` |
| **Check Changelog & Archive Health** | Status inspection | `--path` | `python skills/system-diagnostics/scripts/diagnose.py changelog status --path .` |
| **Read Recent 3 Milestones (On Demand)** | Bounded context lookup | `--recent 3` | `python skills/system-diagnostics/scripts/diagnose.py changelog show --recent 3` |

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

### Subcommand: `probe`
```bash
python skills/system-diagnostics/scripts/diagnose.py probe {list,run,new,save} [OPTIONS]
```
- `list [--json]`: Discovers and prints all registered probes across global and workspace registries.
- `run <NAME_OR_PATH> [ARGS...] [--json]`: Executes a probe in an isolated subprocess with performance timing.
- `new <NAME> [--domain <DOMAIN>]`: Scaffolds a new probe boilerplate in `.diagnostics/probes/<name>.py`.
- `save <SOURCE_PATH> <NAME> [--workspace]`: Promotes a verified scratch script into the reusable probe registry.

### Subcommand: `audit`
```bash
python skills/system-diagnostics/scripts/diagnose.py audit [OPTIONS]
```
- `--path <PATH>`: Target root directory or file to audit (default: current directory).
- `--typecheck`: Runs virtualenv-detected static type checkers (`ruff`, `mypy`).
- `--smells`: Scans for dynamic platform import ladders (`try...except ImportError`) and recommends static guards.
- `--callable-smoke`: Runs AST and signature checks, testing class instantiability to catch initialization `TypeErrors`.
- `--json`: Outputs structured JSON report.
- `--strict`: Exits with return code 1 if any defects or smells are detected.

### Subcommand: `scan`
```bash
python skills/system-diagnostics/scripts/diagnose.py scan [OPTIONS]
```
- `--path <PATH>`: Target file or directory to scan across Python, JS/TS, CSS, and Dart (default: current directory).
- `--deep` / `--all`: Scans extended rules (CSS `!important` specificity overruns, unbounded container growth, blocking loops).
- `--json`: Outputs machine-readable catalog JSON to stdout.
- `--strict`: Exits with return code 1 if any defects are detected (ideal for CI pipelines).
- *Automatic Catalog Sync*: Automatically saves findings into `<workspace>/.diagnostics/defect_catalog.json` and `DEFECT_CATALOG.md`.

### Subcommand: `scaffold-defect`
```bash
python skills/system-diagnostics/scripts/diagnose.py scaffold-defect --id <ID_OR_FP> [OPTIONS]
```
- `--id <ID_OR_FP>`: Sequential ID (`DEFECT-001`) or content fingerprint (`DEF-MUTABLE-8749e9`).
- `--branch`: Pre-flight checks git status (ignoring `.diagnostics/` and `.refactor/`). If clean, checks out micro-branch `fix/<defect_id>`. If dirty, prints safety notice and proceeds safely in-place.
- `--fix`: Forces Track A tactical test generation (`tests/quarantine/test_<id>.py`) even if classified as architectural.
- `--elevate`: Forces Track B architectural elevation brief generation for `/frontier-architect` + `/grill-me`.
- `--workspace <PATH>`: Target project directory (defaults to current directory).

---

## Windows Shell & Tooling Resilience

1. **PowerShell Script Policy Bypass**:
   - When executing Node/NPM CLI tools on Windows, always invoke via `cmd /c npx -y <tool> ...` to bypass `npx.ps1 cannot be loaded because running scripts is disabled on this system`.
2. **Codebase Grepping**:
   - Prefer `git grep -n "<pattern>"` over `rg` unless `rg` is explicitly verified in `%PATH%`.
3. **Line Ending & File Editing Safety**:
   - When inspecting or patching files on Windows, preserve CRLF/LF line endings and avoid generating throwaway python patching scripts.

---

## Architecture & Bundled Scripts

```
skills/system-diagnostics/
├── SKILL.md                          # Tool manual and scenario matrix
├── probes/                           # Global diagnostic probe extensions
│   └── camera_hardware.py            # Built-in camera hardware & acquisition probe
├── scripts/
│   ├── diagnose.py                   # Unified CLI entrypoint with delegated subparsers
│   ├── static_auditor.py             # Modular static defect, smell & callable auditor
│   ├── shadow_prober.py              # Polyglot AST/lexer rules, sandbox & scan runner
│   ├── defect_catalog.py             # SSOT catalog manager, git safety & JIT router
│   ├── scaffold_templates.py         # Tactical Red/Green tests & architectural briefs
│   ├── probe_runner.py               # Pluggable extension runner & probe registry
│   ├── cdp_inspect.py                # CDP layout, DOMrect, and overflow inspector
│   ├── cdp_transport.py              # Zero-dependency RFC 6455 WebSocket client
│   ├── audit_layout.js               # Injected DOM bounding box auditor
│   ├── docker_audit.py               # Docker stats, top, and MD5 sync auditor
│   ├── surface_scanners.py           # AST surface parser for HTML/JS/Python/CSS
│   ├── changelog_manager.py          # Unified changelog, sanitization & auto-archiving engine
│   └── css_inspector.py              # CSS layout, overflow, and specificity checks
└── tests/
    ├── test_diagnose.py              # Automated unit tests for CLI & discovery
    ├── test_changelog_manager.py     # Automated unit tests for changelog & auto-archiving
    ├── test_static_auditor.py        # Automated unit tests for static & smell audit
    ├── test_shadow_prober.py         # Automated unit tests for AST rules & sandbox
    ├── test_defect_catalog.py        # Automated unit tests for catalog & git safety
    ├── test_e2e_latent_defects.py    # E2E integration tests for Dual-Key & dual-track
    └── test_probe_runner.py          # Automated unit tests for dynamic probe extensions
```
