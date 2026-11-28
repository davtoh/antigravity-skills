---
name: system-diagnostics
description: >-
  Centralized diagnostics engine for empirical browser UI layout inspection, Docker runtime/CPU audits, AST surface scanning, and automated virtualenv test runs. Make sure to use this skill whenever inspecting DOM bounding boxes, layout overflows, video/canvas element sizing, checking container CPU or host-vs-container file sync, discovering HTML element IDs and backend routes, or performing 3-tier empirical diagnostics before and after code changes across Windows, macOS, and Linux.
---

# System Diagnostics: Centralized Tool Engine & Unified CLI

**System Diagnostics** consolidates browser layout inspection, container runtime monitoring, AST surface analysis, polyglot defect scanning, transcript telemetry, and virtualenv test execution into a single zero-dependency CLI (`diagnose.py`).
For exhaustive per-subcommand flag permutations and internal script topology, read [`references/cli-reference.md`](./references/cli-reference.md).
For the HUD observation workflow (`observations`, `brief`, audit hand-off, privacy), read [`references/observations.md`](./references/observations.md).

---

## Core Capabilities

1. **Browser UI & Layout Inspection (`diagnose.py ui`)**:
   - Inspects DOM bounding boxes (`DOMRect`), computed styles, and scroll dimensions via zero-Node/npm pure-Python RFC 6455 WebSocket CDP.
   - Detects layout overflows and horizontal viewport blowouts; attaches to the user's active visible Chrome tab via `DevToolsActivePort` (`--live`, with `--no-fallback-headless` enforced unless `--allow-headless-fallback`) or runs an isolated temporary headless browser (`--headless`).
   - Supports `--eval-file <path>` (avoids Windows PowerShell quote-stripping; `--capture-runtime` defaults ON for `--eval`/`--eval-file`, opt out via `--no-capture-runtime`), `--click`, `--screenshot`, `--navigate`, `--window-size`, `--viewports`, `--wait`, and `--strict`.
2. **Docker Runtime & Sync Audit (`diagnose.py container`)**:
   - Snapshots container CPU, Memory, Network I/O, and PIDs (`docker stats --no-stream`) and active processes (`docker top`).
   - Verifies host-vs-container MD5 file synchronization (`--sync-check`) to catch stale mounted files, scans recent container logs for unhandled Tracebacks/exceptions (`--lines`), and auto-probes active containers when `--container` is omitted.
3. **AST Interactive Surface Scanner (`diagnose.py surface`)**:
   - Statically extracts HTML element IDs, interactive `<select>` dropdowns, modals, JavaScript/TypeScript `window.*` global exports and DOM queries, backend Python HTTP routes (`@app.get`, `@app.post`), and CSS custom properties / `!important` specificity counts without running servers.
   - Cross-verifies JS `fetch()` routes, `window.*` read/write symmetry, and HTML IDs via `--verify` and `--strict` (plus `--json` and `--include-tests`).
4. **Automated Test Runner (`diagnose.py tests`)**:
   - Auto-discovers local virtual environment interpreters (`.venv`, `venv`, `env`, falling back cleanly to system Python when missing), runs unit and integration tests without manual shell activation, forwards test arguments cleanly to `unittest` or `pytest`, and enforces a `--timeout` guard (default `180s`, `0` disables, returning exit code `124` on hung suites).
5. **Unified 3-Tier Diagnostic Audit (`diagnose.py all`)**:
   - Executes a 3-tier audit in one shot (Static Surface/Tests $\to$ Docker Container $\to$ Browser UI Layout), auto-probing local ports (`8000`, `3000`, `5000`, `8080`, `5173`) and active containers, summarizing under Axiom 9 Honest Verification Reporting (`VERIFIED`, `UNVERIFIED`, or `SKIPPED`), and supporting `--strict` (exit code `1` on failure).
6. **Dynamic & Extensible Probes (`diagnose.py probe`)**:
   - Discovers (`probe list`), runs (`probe run`), scaffolds (`probe new <name> --domain <domain>`), and promotes verified scratch scripts (`probe save <src> <name>`) across global and workspace `.diagnostics/probes/` registries.
   - Built-in `camera_hardware` probe validates DirectShow, Media Foundation, and V4L2 device indices, pixel frame decoding, and Windows PnP device locks.
7. **Static Quality, Defect & Code Smell Audit (`diagnose.py audit`)**:
   - Runs virtualenv static typecheckers (`ruff`, `mypy`, `pyright`, `dart analyze`), flags dynamic platform import ladders (`try...except ImportError` on `win32api`/`fcntl`) via `--smells` recommending static platform guards, runs callable smoke tests (`--callable-smoke`) to catch constructor `TypeErrors`, enforces a **Strict Token-Budget Guard** truncating output to the top 5 issues per category, and supports `--max-lines`, `--max-fn-lines`, `--json`, and `--strict`.
8. **Polyglot Defect Scanner & JIT Scaffolder (`diagnose.py scan`, `scaffold-defect`, `resolve-defect`, `dismiss-defect`)**:
   - Scans Python, JS/TS, CSS, and Dart across one or more files/directories (`--path <paths...>`) with deterministic Dual-Key IDs (`DEFECT-XXX` + `DEF-<RULE>-<6HEX>`) that survive file moves and line shifts.
   - Persists findings in the Single Source of Truth (SSOT) catalog (`.diagnostics/defect_catalog.json` and `DEFECT_CATALOG.md`), supporting `--deep`/`--all` (extended rules: CSS `!important`, unbounded containers, blocking loops), `--prune` (purging `resolved`/`dismissed` or vanished items), and `--strict`.
   - Dispatches **Dual-Track Remediation**: `scaffold-defect --id <ID> [--path <DIR>] [--branch]` (Track A tactical Red-to-Green test in `tests/quarantine/test_<id>.py` for `/app-debugger` with git dirty-tree safety guard) or `--elevate` (Track B Architectural Elevation Brief for `/frontier-architect` + `/grill-me`). `resolve-defect --id <id> --note` and `dismiss-defect --id <id> --reason` accept comma-separated defect IDs, fingerprints, or rule IDs.
9. **Unified Changelog, Transcript Telemetry, Debug Retro & Skill Packager**:
   - `changelog {add,migrate,show,status,pr-description}`: Bounded `CHANGELOG.md` ($\le 150$ lines) with path/URI sanitization, auto-migration of legacy `MIGRATION_LOG.md`, `.changelogs/` sharding, `show --recent 3`, `pr-description` PR summary generation, and default Single-Generation Echo commit snippets (`--no-commit-hint` to opt out).
   - `transcript-audit`: Audits Antigravity `<appDataDir>/brain` and Claude Code `~/.claude/projects/` logs (`--vendor auto|gemini|claude`, `--list`, `--plan`, `--latest <N>`, `--cids <IDs...>`, `--brain-dir` / `AGY_BRAIN_DIR`, `--workspace`, `--json`) reporting steps, failures (`user_rejected` tool calls excluded from failures/grade caps and surfaced as `- NOTE`), `- FAIL`, `- REPEAT`, `- CORRECTION`, `- REDIRECT` workflow/model switches, `schedule-while-subagent` flags, parallel same-file edits, subagent duplicate reads, rubric grade caps (`suggested_grade_cap` matching the `plan_digest` rubric: `>= 2` failures $\to$ `B`, `> 3` failures $\to$ `C`), and `has_debug_retro` tracking to flag unescalated thrashing when failures accumulate.
   - `debug-retro`: Records post-debug retrospectives (`DEBUG_RETRO.md`, `LEARNING_SCAFFOLD.md`, `--- Turn-End Echo ---`) with `--plan`, `--learn`, and `--skill-learn` flags.
           - `diagnose.py arch-map` (`--path <paths...>`, `--json`, `--full`, `--include-tests`, `--out`), `diagnose.py traces` (`--scaffold fastapi|flask|generic`, `--clear`, `resolve` to inspect `.diagnostics/` runtime crash and trace catalogs), `diagnose.py run <command>` (zero-code runner with automatic runtime tracing bootstrapped), and `diagnose.py package-skill <skill_or_all> --out dist/` (temp-stages skills, materializes thin SSOT shims into standalone scripts, strips `tests/` and `evals/`, and runs `package_skill.py` validation).
10. **Project-Agnostic Local Mini-CI Runner (`diagnose.py ci`)**:
    - Auto-detects `skills_monorepo` (`.github/scripts/validate_skills.py` + `*/tests/test_*.py`) vs `python_repo` (`ruff` + `pytest`/`unittest`), or loads optional `.diagnostics/mini_ci.json` overrides (`steps`, `apt_packages`, `pip_packages`, `env`, `docker_image`, `exclude_dirs`, `wsl_distro`).
    - Supports host virtualenv execution (`--fast`, default, with clean CI env and optional `--simulate-ci-chrome`) and isolated Linux parity (`--linux` via `--backend auto|wsl|docker`, `--wsl-distro`, `--docker-image`, isolated `CLEAN_HOME`, hash-keyed venvs/images, `--clean-snapshot`, `--tests`, `--skip-lint`, `--dry-run`).

---

## Pre-Run Verification & Scenario Combinations Matrix

```bash
# Run the comprehensive diagnostic test suite (460+ unit & integration tests)
python -m unittest discover -s skills/system-diagnostics/tests -p "test_*.py"
```

| Real-World Scenario / Objective | Mode / Inputs | Key Parameters | Exact Runnable Command |
| :--- | :--- | :--- | :--- |
| **Quick 3-Tier Health Audit** | Dev server / repo | Auto-probes ports & containers | `python skills/system-diagnostics/scripts/diagnose.py all` |
| **Inspect Active Buggy Chrome Tab** | Live visible tab | Brings tab to front; fails loud unless fallback allowed | `python skills/system-diagnostics/scripts/diagnose.py ui --live --capture-runtime --audit-layout` |
| **Log Debug Retrospective** | Post-fix debug session | Records `DEBUG_RETRO.md`, `LEARNING_SCAFFOLD.md`, & `--- Turn-End Echo ---` (`--plan`, `--learn`, `--skill-learn`) | `python skills/system-diagnostics/scripts/diagnose.py debug-retro --symptom "..." --cause "..." --status verified --cid <cid>` |
| **Capture Headless Visual Proof** | Headless sandbox | Viewport render to file | `python skills/system-diagnostics/scripts/diagnose.py ui --screenshot scratch/bug.jpg` |
| **Inspect Target Selectors** | Specific elements | Measures bounding box & styles | `python skills/system-diagnostics/scripts/diagnose.py ui --selectors "#app,#main-canvas,video"` |
| **Hard Reload & Verify Post-Fix** | Fresh assets reload | Forces page refresh before audit | `python skills/system-diagnostics/scripts/diagnose.py ui --navigate --audit-layout` |
| **Verify Docker Container Sync** | Docker service | Compares host vs container MD5s | `python skills/system-diagnostics/scripts/diagnose.py container --sync-check app.py static/app.js` |
| **Scan Recent Container Tracebacks** | Docker service | Scans recent log lines for panic | `python skills/system-diagnostics/scripts/diagnose.py container --lines 100` |
| **Scan Surface for Broken IDs/Routes** | Source repository | Static AST scan without server | `python skills/system-diagnostics/scripts/diagnose.py surface --show-ids --show-routes` |
| **Verify Cross-Contract Surface Parity** | HTML/JS/Python repo | Fetch vs routes, `window.*`, IDs | `python skills/system-diagnostics/scripts/diagnose.py surface --verify --strict` |
| **Export Full Surface Inventory JSON** | Source repository | JSON contract baseline | `python skills/system-diagnostics/scripts/diagnose.py surface --json` |
| **Run Test Suite with Virtualenv** | Test suite | Auto-detects `.venv` & `180s --timeout` | `python skills/system-diagnostics/scripts/diagnose.py tests` |
| **Run Host Mini-CI Parity (`--fast`)** | Any repo / monorepo | Auto-detects layout or `.diagnostics/mini_ci.json` | `python skills/system-diagnostics/scripts/diagnose.py ci --path . --fast` |
| **Run Isolated Linux Mini-CI (`WSL`)** | Windows + WSL2 | Isolated `CLEAN_HOME`, `/mnt/...` path, hash-keyed venv | `python skills/system-diagnostics/scripts/diagnose.py ci --path . --linux` |
| **Run Isolated Linux Mini-CI (`Docker`)** | Docker / `--clean-snapshot` | Ephemeral container (`HOME=/tmp/mini_ci_home`) & clean copy | `python skills/system-diagnostics/scripts/diagnose.py ci --path . --linux --backend docker --clean-snapshot` |
| **List Registered Probes** | Probe registry | Discovers global & workspace probes | `python skills/system-diagnostics/scripts/diagnose.py probe list` |
| **Probe Camera Hardware & Locks** | Physical/virtual video | Probes backends, decoding & locks | `python skills/system-diagnostics/scripts/diagnose.py probe run camera_hardware` |
| **Scaffold New Domain Probe** | Missing domain | Generates protocol boilerplate | `python skills/system-diagnostics/scripts/diagnose.py probe new db_pool --domain database` |
| **Promote Scratch Script to Probe** | Verified scratch | Saves script to reusable registry | `python skills/system-diagnostics/scripts/diagnose.py probe save scratch/check_db.py db_pool` |
| **Static Defect & Type Audit** | Source repository | Runs venv ruff/mypy (top-5 capped) | `python skills/system-diagnostics/scripts/diagnose.py audit --path src/` |
| **Detect Platform Import Smells** | Source repository | Flags dynamic try..except ladders | `python skills/system-diagnostics/scripts/diagnose.py audit --smells` |
| **Callable Smoke & Init Check** | Source repository | Checks signatures & constructor TypeErrors | `python skills/system-diagnostics/scripts/diagnose.py audit --callable-smoke` |
| **Export Static Defect JSON** | Source repository | Full machine-readable audit report | `python skills/system-diagnostics/scripts/diagnose.py audit --json` |
| **Polyglot Latent Defect Scan** | Source repository | Scans Py, JS/TS, CSS, Dart across 1+ paths | `python skills/system-diagnostics/scripts/diagnose.py scan --path src/ tests/` |
| **Deep Scan with CSS & Extended AST** | Source repository | Full polyglot rules + specificity leaks | `python skills/system-diagnostics/scripts/diagnose.py scan --path src/ --deep` |
| **Audit Conversation Transcripts** | Brain logs | Steps, failures, parallel edits & subagent dupes | `python skills/system-diagnostics/scripts/diagnose.py transcript-audit --latest 1` |
| **Strict CI Defect Gate** | CI / Pre-commit | Returncode 1 if any defects found | `python skills/system-diagnostics/scripts/diagnose.py scan --strict` |
| **Unlock Tactical Defect (Test Synthesis)** | Quarantined defect | Generates Red repro in tests/quarantine/ | `python skills/system-diagnostics/scripts/diagnose.py scaffold-defect --id DEFECT-001` |
| **Unlock Tactical Defect + Micro-Branch** | Quarantined defect | Clean git checkout + Red repro test | `python skills/system-diagnostics/scripts/diagnose.py scaffold-defect --id DEFECT-001 --branch` |
| **Elevate Structural Defect to Architecture**| Quarantined defect | Emits brief for /frontier-architect | `python skills/system-diagnostics/scripts/diagnose.py scaffold-defect --id DEFECT-002 --elevate` |
| **Mark Defect Resolved in Catalog** | Verified fix | Updates status & resolution audit note | `python skills/system-diagnostics/scripts/diagnose.py resolve-defect --id DEFECT-001 --note "Fixed"` |
| **Dismiss False Positive or Risk** | Non-actionable item | Excludes from active count & strict gate | `python skills/system-diagnostics/scripts/diagnose.py dismiss-defect --id DEFECT-002 --reason "False positive"` |
| **Rescan & Prune Closed/Vanished Items** | Catalog cleanup | Drops closed/obsolete entries on scan | `python skills/system-diagnostics/scripts/diagnose.py scan --deep --prune` |
| **Record Milestone & Emit Commit Snippet** | Any repo (auto-migrates legacy log) | `--title --type --summary --verify` | `python skills/system-diagnostics/scripts/diagnose.py changelog add --title "Worker Split" --type refactor --summary "SRP decomposition" --verify "pytest (45 passed)"` |
| **Auto-Migrate Oversized MIGRATION_LOG.md** | Legacy repo migration | `--path --max-lines 150` | `python skills/system-diagnostics/scripts/diagnose.py changelog migrate --path . --max-lines 150` |
| **Custom Source/Target Log Names** | Custom file override | `--source-log --target-log` | `python skills/system-diagnostics/scripts/diagnose.py changelog migrate --source-log HISTORY.md --target-log CHANGELOG.md` |
| **Check Changelog & Archive Health** | Status inspection | `--path` | `python skills/system-diagnostics/scripts/diagnose.py changelog status --path .` |
| **Read Recent 3 Milestones (On Demand)** | Bounded context lookup | `--recent 3` | `python skills/system-diagnostics/scripts/diagnose.py changelog show --recent 3` |
| **Generate PR Description** | Changelog, plans & git | `--base --plan --recent` | `python skills/system-diagnostics/scripts/diagnose.py changelog pr-description --base main --recent 5` |
| **Evaluate Multi-Statement JS in Page** | Live or headless CDP | `--eval-file <js_path>` | `python skills/system-diagnostics/scripts/diagnose.py ui --live --eval-file scratch/check_dom.js` |
| **Package Standalone `.skill` Bundle** | Distribution / `/skill-creator` | Resolves SSOT shims & strips `tests/` | `python skills/system-diagnostics/scripts/diagnose.py package-skill all --out dist/` |
| **Generate Compact Architecture Map** | Single root or multi-subpath | `--path <paths...> --json --full --include-tests --out` | `python skills/system-diagnostics/scripts/diagnose.py arch-map --path . --json` |

---

## Windows Shell & Tooling Resilience

1. **PowerShell Script Policy Bypass**: Invoke Node/NPM CLI tools via `cmd /c npx -y <tool> ...` to bypass `npx.ps1` execution policy blocks.
2. **Codebase Grepping**: Prefer `git grep -n "<pattern>"` over `rg` unless `rg` is verified on `PATH`.
3. **Line Ending & File Editing Safety**: Preserve `CRLF/LF` line endings on Windows and avoid throwaway python patching scripts.
