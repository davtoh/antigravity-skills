# System Diagnostics (`diagnose.py`) — Complete CLI Flag Reference & Architecture

Consult this reference when you need exhaustive per-subcommand flag permutations or the internal script/test topology of `skills/system-diagnostics/`.

---

## 1. Per-Subcommand Flag Reference

### Subcommand: `ui`
```bash
python skills/system-diagnostics/scripts/diagnose.py ui [OPTIONS]
```
- `--url <URL>`: Target URL. If omitted, auto-probes local dev ports (`8000`, `3000`, `5000`, `8080`, `5173`, `4200`).
- `--live`: Attaches to user's active visible Chrome tab via `DevToolsActivePort`.
- `--headless`: Runs in isolated, auto-cleaned temporary headless Chrome (default).
- `--list-tabs`: Lists open tabs in the live browser and exits.
- `--audit-layout`: Scans DOM for bounding box (`DOMRect`) overflows, horizontal scrolling, and `<video>`/`<img>`/`<canvas>` layout issues.
- `--selectors <CSS>`: Comma-separated CSS selectors to measure (e.g. `'#video-player,.control-bar'`).
- `--screenshot <PATH>`: Saves a JPEG viewport screenshot.
- `--navigate`: Forces a page refresh before measuring.
- `--eval <JS>`: Evaluates arbitrary JavaScript expression in page context.
- `--eval-file <PATH>`: Reads UTF-8 JavaScript from a file (or `-` for stdin) and evaluates in page context (avoids Windows PowerShell quote-stripping).
- `--click <SELECTOR>`: Clicks an element before measuring.
- `--window-size <WxH>`: Headless viewport dimensions (default: `1440x900`).
- `--viewports <LIST>`: Comma-separated viewports for multi-viewport `--audit-layout` sweeps (e.g. `'960x720,1280x800,1920x1080'`).
- `--wait <SEC>`: Maximum post-load/click settle wait in seconds (default: `1.5`).
- `--stability-ms <MS>`: Early-exit layout stability window in milliseconds (default: `0`).
- `--connect-timeout <SEC>`: Live CDP handshake timeout in seconds (default: `15.0`).
- `--port <PORT>`: Debugging port override.
- `--strict`: Exits with code `1` if layout overflow warnings or runtime console/JS/network errors are detected.
- `--no-fallback-headless`: Fails immediately if live Chrome is unreachable instead of falling back to headless (automatically enforced with `--live` unless `--allow-headless-fallback` is set).
- `--allow-headless-fallback`: Permits silent fallback to headless Chrome if `--live` fails.
- `--capture-runtime` / `--no-capture-runtime`: Captures console errors, uncaught JS exceptions, HTTP $\ge 400$ / WebSocket errors, and `localStorage` state (default ON when `--eval` or `--eval-file` is set; pass `--no-capture-runtime` to opt out).

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
- `--verify`: Cross-verifies JS `fetch()` paths vs routes, `window.*` reader/writer symmetry, and JS IDs vs HTML IDs.
- `--include-tests`: Includes `tests/` files during `--verify` cross-contract scanning (excluded by default).
- `--strict`: Exits `1` if `--verify` detects mismatches.
- `--json`: Outputs structured JSON for automated contracts.

### Subcommand: `tests`
```bash
python skills/system-diagnostics/scripts/diagnose.py tests [--path <DIR>] [--timeout 180] [ARGS...]
```
- `--path <DIR>`: Workspace root to scan for `.venv` (default: current directory).
- `--timeout <SEC>`: Max seconds before aborting a hung suite (default: `180`; `0` disables; exits with code `124`).
- `[ARGS...]`: Arguments forwarded to `python -m unittest` (default: `discover -s tests -p "test_*.py"`).

### Subcommand: `all`
```bash
python skills/system-diagnostics/scripts/diagnose.py all [OPTIONS]
```
- `--path <DIR>`: Workspace directory (default: current directory).
- `--url <URL>`: Explicit dev server URL.
- `--container <NAME>`: Explicit Docker container name.
- `--wait <SEC>`: Wait seconds forwarded to Tier 3 browser layout audit (default: `1.5`).
- `--strict`: Exits with return code `1` if any tier fails.

### Subcommand: `probe`
```bash
python skills/system-diagnostics/scripts/diagnose.py probe {list,run,new,save} [OPTIONS]
```
- `list [--path <DIR>] [--json]`: Discovers and prints all registered probes across global and workspace registries.
- `run <NAME_OR_PATH> [ARGS...] [--path <DIR>] [--json]`: Executes a probe in an isolated subprocess with performance timing.
- `new <NAME> [--domain <DOMAIN>] [--path <DIR>]`: Scaffolds a new probe boilerplate in `.diagnostics/probes/<name>.py`.
- `save <SOURCE_PATH> <NAME> [--workspace] [--path <DIR>]`: Promotes a verified scratch script into the reusable probe registry.

### Subcommand: `audit`
```bash
python skills/system-diagnostics/scripts/diagnose.py audit [OPTIONS]
```
- `--path <PATHS...>`: Target root directory/directories or files to audit (default: current directory).
- `--typecheck`: Runs virtualenv-detected static type checkers (`ruff`, `mypy`).
- `--smells`: Scans for dynamic platform import ladders (`try...except ImportError`) and recommends static guards.
- `--callable-smoke`: Runs AST and signature checks, testing class instantiability to catch initialization `TypeErrors`.
- `--max-lines <N>`: Overrides the soft file line budget ceiling (default: `350`).
- `--max-fn-lines <N>`: Overrides the function line budget ceiling (default: `40`).
- `--json`: Outputs structured JSON report.
- `--strict`: Exits with return code `1` if any defects or smells are detected.

### Subcommand: `scan`
```bash
python skills/system-diagnostics/scripts/diagnose.py scan [OPTIONS]
```
- `--path <PATHS...>`: One or more files/directories to scan across Python, JS/TS, CSS, and Dart (default: current directory).
- `--deep` / `--all`: Scans extended rules (CSS `!important` specificity overruns, unbounded container growth, blocking loops).
- `--prune`: Purges closed (`resolved`/`dismissed`) or vanished defects from the catalog during scan reconciliation.
- `--json`: Outputs machine-readable catalog JSON to stdout.
- `--strict`: Exits with return code `1` if any active (`quarantined`/`scaffolded`/`elevated`) defects are detected.

### Subcommand: `scaffold-defect`, `resolve-defect`, & `dismiss-defect`
```bash
python skills/system-diagnostics/scripts/diagnose.py scaffold-defect --id <ID_OR_FP> [--path <DIR>] [--branch] [--fix] [--elevate] [--json]
python skills/system-diagnostics/scripts/diagnose.py resolve-defect --id <ID_FP_OR_RULE> [--path <DIR>] [--note "<TEXT>"] [--json]
python skills/system-diagnostics/scripts/diagnose.py dismiss-defect --id <ID_FP_OR_RULE> [--path <DIR>] [--reason "<TEXT>"] [--json]
```
- `--id <ID_FP_OR_RULE>`: Sequential ID (`DEFECT-001`), fingerprint (`DEF-MUTABLE-8749e9`), or comma-separated IDs/rules (for `resolve-defect` / `dismiss-defect`).
- `--path <DIR>`: Target project workspace directory (default: current directory).
- `--branch`: Pre-flight checks git status (ignoring `.diagnostics/` and `.refactor/`). If clean, checks out micro-branch `fix/<defect_id>`; if dirty, prints a safety notice and proceeds in-place.
- `--fix` / `--elevate`: Forces Track A tactical test generation (`tests/quarantine/test_<id>.py`) or Track B architectural elevation brief.
- `--note` / `--reason`: Audit note persisted in the `Resolved & Dismissed History` table.
- `--json`: Emits machine-readable JSON output.

### Subcommand: `changelog`
```bash
python skills/system-diagnostics/scripts/diagnose.py changelog {add,migrate,show,status} [OPTIONS]
```
- `add --title "<T>" --type <TYPE> --summary "<S>" [--files <FILES...>] [--verify "<V>"] [--path <DIR>] [--max-lines 150] [--no-commit-hint]`: Appends a sanitized milestone entry to `CHANGELOG.md`, auto-migrates any legacy `MIGRATION_LOG.md`, shards overflow into `.changelogs/`, and prints a copy-pasteable `git commit` snippet by default (pass `--no-commit-hint` to suppress).
- `migrate [--path <DIR>] [--source-log <NAME>] [--target-log <NAME>] [--max-lines 150]`: Migrates and shards an oversized legacy log into `CHANGELOG.md`.
- `show [--path <DIR>] [--recent 3] [--json]` / `status [--path <DIR>] [--max-lines 150] [--json]`: Reads recent entries or inspects line/shard status.

### Subcommand: `transcript-audit`
```bash
python skills/system-diagnostics/scripts/diagnose.py transcript-audit [--cids <IDs...>] [--latest <N>] [--min-steps <N>] [--brain-dir <DIR>] [--workspace <DIR>] [--json]
```
- `--cids <IDs...>`: Full UUIDs, 8-char prefixes, or comma-separated IDs from `<appDataDir>/brain`.
- `--latest <N>` / `--min-steps <N>`: Audits the `N` most recent substantive conversations (prefers `>= 6` steps).
- `--brain-dir <DIR>`: Overrides brain directory (or set `AGY_BRAIN_DIR`).
- `--workspace <DIR>`: Filters recent conversations to those matching the given workspace path.
- `--json`: Emits structured JSON reporting `steps`, `planner_turns`, `total_failures`, `- FAIL`, `- REPEAT`, `- CORRECTION`, `- REDIRECT` workflow/model switches, `schedule_while_subagent`, `parallel_same_file_edits`, `subagent_overlap_reads`, `has_debug_retro` (detecting unescalated thrashing when `>= 4` failures accumulate without `/app-debugger` or `debug-retro`), and failure-based `suggested_grade_cap` matching the `plan_digest` rubric (`>= 2` failures caps at `B`; `> 3` failures caps at `C`).

### Subcommand: `debug-retro`
```bash
python skills/system-diagnostics/scripts/diagnose.py debug-retro --symptom "<S>" --cause "<C>" [--status {verified,unconfirmed,escalated}] [--cid <CID>] [--plan <SLUG>] [--path <DIR>] [--brain-dir <DIR>] [--learn "<L>"] [--skill-learn "<SL>"]
```
- Records a post-debug retrospective in `.frontier/DEBUG_RETRO.md` (or `.diagnostics/DEBUG_RETRO.md`), updates `.diagnostics/LEARNING_SCAFFOLD.md` and `LEARN_QUEUE.md`, auto-records `followup_cids` and backfills `.frontier/plans/<slug>/LEARNING_SCAFFOLD.md` when `--plan <SLUG>` is given, and prints `--- Turn-End Echo ---`.

### Subcommands: `arch-map`, `traces`, `run`, & `package-skill`
```bash
python skills/system-diagnostics/scripts/diagnose.py arch-map [--path <PATHS...>] [--include-tests] [--json] [--full] [--out <FILE>]
python skills/system-diagnostics/scripts/diagnose.py traces [list|resolve] [--id <TRC_ID>] [--note "<TEXT>"] [--path <DIR>] [--recent <N>] [--clear] [--scaffold {fastapi,flask,generic}] [--dest <DIR>] [--json]
python skills/system-diagnostics/scripts/diagnose.py run <COMMAND...>
python skills/system-diagnostics/scripts/diagnose.py package-skill [<SKILL_OR_ALL>] [--out <DIR>]
```

---

## 2. Architecture & Bundled Scripts

```text
skills/system-diagnostics/
├── SKILL.md                          # Concise operational manual and 38-row scenario matrix
├── references/
│   └── cli-reference.md              # Exhaustive subcommand flags and architecture reference
├── probes/
│   └── camera_hardware.py            # Built-in camera hardware & acquisition probe
├── scripts/
│   ├── diagnose.py                   # Unified CLI entrypoint
│   ├── diagnose_cli.py               # Core parser builders & 3-tier runner
│   ├── arch_mapper.py                # Compact architecture, modularity & coupling mapper
│   ├── ast_guard_rules.py            # AST guard rules for silent shape-guarded skips
│   ├── audit_layout.js               # Injected DOM bounding box & overflow auditor
│   ├── audit_layout_extra.js         # SVG data-URI, flex overflow & canvas luminance checks
│   ├── cdp_inspect.py                # CDP layout, DOMRect, and runtime inspector
│   ├── cdp_runtime.py                # Console, exception, network & DevToolsActivePort helpers
│   ├── cdp_transport.py              # Zero-dependency RFC 6455 WebSocket client
│   ├── cdp_viewport.py               # Viewport parsing & multi-viewport audit helpers
│   ├── changelog_archive.py          # Semester sharding & sanitization helpers
│   ├── changelog_manager.py          # Unified CHANGELOG.md & commit-hint engine
│   ├── connector_scaffolder.py       # Framework trace middleware scaffolder
│   ├── cross_module_rules.py         # Cross-module lock, event & clock-domain AST rules
│   ├── css_inspector.py              # CSS layout, overflow, and specificity checks
│   ├── debug_retro.py                # Post-debug retrospective & followup_cids bridge
│   ├── defect_catalog.py             # SSOT catalog manager, git safety & JIT router
│   ├── docker_audit.py               # Docker stats, top, and MD5 sync auditor
│   ├── probe_runner.py               # Pluggable extension runner & probe registry
│   ├── runtime_runner.py             # Zero-code runtime trace bootstrapper
│   ├── scaffold_templates.py         # Tactical Red/Green tests & architectural briefs
│   ├── shadow_prober.py              # Polyglot AST/lexer rules, sandbox & scan runner
│   ├── skill_packager.py             # Standalone .skill bundler materializing SSOT shims
│   ├── static_auditor.py             # Modular static defect, smell & callable auditor
│   ├── surface_contracts.py          # Surface CLI & response-key contract matcher
│   ├── surface_layout_checks.py      # Undefined layout class & App.navigate target checks
│   ├── surface_scanners.py           # AST surface parser for HTML/JS/Python/CSS
│   ├── surface_verifier.py           # Cross-contract verifier (fetch vs routes, window.*, IDs)
│   ├── trace_cli.py                  # CLI handler for runtime trace inspection & resolution
│   ├── trace_middleware.py           # WSGI/ASGI trace middleware helpers
│   ├── trace_recorder.py             # Universal runtime crash/trace catalog engine
│   ├── transcript_auditor.py         # Brain transcript.jsonl telemetry & rubric auditor
│   ├── transcript_checks.py          # Wakeup race, parallel-edit & subagent-overlap detectors
│   └── bootstrap/sitecustomize.py    # Subprocess runtime trace hook
└── tests/                            # 233+ unit & integration tests across 22 test modules
```
