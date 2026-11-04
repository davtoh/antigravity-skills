# Refactor-Monolith CLI & Tooling Reference

Complete reference for all built-in CLI commands, subcommands, flag permutations, template injection recipes, and the full Scenario Combinations Matrix.

---

## 1. Quick Subcommand Index

| Category | Primary Subcommands | Purpose |
| :--- | :--- | :--- |
| **Campaign State** | `plan`, `state` | Provision `.refactor/`, track phases, save checkpoints, opt-in scan or quarantine defects. |
| **Contract Invariants** | `anchor`, `capture`, `inspect`, `verify` | Pre-refactor golden baseline capture, surface inspection, and regression diffing. |
| **Automated Testing** | `run-tests`, `generate-smoke-test` | Virtualenv test runner with headless guards; regression smoke tests. |
| **Quality & Inspection** | `code_health_audit.py`, `inspect-css`, `typecheck` | Quantitative line/method budgets, CSS specificity/`!important`, static type gates. |
| **Cross-Platform Patching**| `normalize-eol`, `patch`, `inject-scripts` | Line-ending normalization, CRLF-agnostic patching, templated script injection. |
| **Live Diagnostics** | `verify-ui`, `audit-container`, `diagnose` | Chrome DevTools Protocol layout audits, Docker container sync/CPU checks. |

---

## 2. Command Details & Recipes

### 2.1 Campaign State & Planning (`state`, `plan`)

#### `contract_snapshot.py plan`
Initializes a new refactoring plan, sets up `.refactor/state.json`, and optionally scans candidates for latent defects:
```bash
# Basic initialization (0 defect scanning overhead)
python "<skill_dir>/scripts/contract_snapshot.py" plan --path <target_dir> --phases 4 --phase-title "Core Domain Extraction"

# Opt-in candidate defect scan during planning
python "<skill_dir>/scripts/contract_snapshot.py" plan --path <target_dir> --phases 4 --scan-defects
```

#### `contract_snapshot.py state`
Manages in-repo `.refactor/state.json` across conversation turns:
```bash
# Initialize campaign
python "<skill_dir>/scripts/contract_snapshot.py" state --init --target <dir> --plan .refactor/plan.md --phases 4

# Initialize with opt-in candidate defect scan
python "<skill_dir>/scripts/contract_snapshot.py" state --init --target <dir> --plan .refactor/plan.md --phases 4 --scan-defects

# Display campaign status
python "<skill_dir>/scripts/contract_snapshot.py" state --show

# Save intermediate slice checkpoint (Anti-Token-Explosion Gate)
python "<skill_dir>/scripts/contract_snapshot.py" state --checkpoint --note "Completed Slices 1.1-1.3"

# Advance active phase upon Step 5 verification
python "<skill_dir>/scripts/contract_snapshot.py" state --advance --phase 1

# Passive Defect Quarantine Hook (Zero plan.md drift)
# Using separate CLI flags:
python "<skill_dir>/scripts/contract_snapshot.py" state --record-defect \
  --file src/app.py --symbol run --rule MUTABLE_DEFAULT_ARG \
  --message "items=[] persists mutated state across calls" --track tactical

# Using colon shorthand:
python "<skill_dir>/scripts/contract_snapshot.py" state \
  --record-defect "MUTABLE_DEFAULT_ARG:src/app.py:42:items=[] persists mutated state across calls"
```

---

### 2.2 Golden Baseline & Verification (`anchor`, `capture`, `verify`)

```bash
# Record git anchor and parallel worktree recipe
python "<skill_dir>/scripts/contract_snapshot.py" anchor --path <target_dir>

# Snapshot golden contract to .refactor/baseline.json
python "<skill_dir>/scripts/contract_snapshot.py" capture --path <target_dir>

# Interactive Surface Map (DOM IDs, interactive selects, globals, backend routes)
python "<skill_dir>/scripts/contract_snapshot.py" inspect --path <target_dir> --show-routes

# Strict diff against baseline contract
python "<skill_dir>/scripts/contract_snapshot.py" verify --path <target_dir> --strict

# Post-refactor regression comparison against pre-refactor git commit SHA
python "<skill_dir>/scripts/contract_snapshot.py" verify --path <target_dir> --git-ref <sha> --strict
```

---

### 2.3 Web Template Script Injection (`inject-scripts`)

Injects modular `<script>` tags before target entrypoints with automatic indentation, CRLF/LF preservation, duplicate tag filtering, and template engine syntax formatting:

```bash
# 1. Plain HTML (Default)
python "<skill_dir>/scripts/contract_snapshot.py" inject-scripts \
  --html index.html --before app.js --scripts /static/js/nav.js /static/js/player.js

# 2. Django Templates ({% static '...' %})
python "<skill_dir>/scripts/contract_snapshot.py" inject-scripts \
  --html templates/base.html --before main.js --scripts js/nav.js js/player.js \
  --format '<script src="{% static \'{src}\' %}"></script>'

# 3. Flask / Jinja2 Templates ({{ url_for('static', filename='...') }})
python "<skill_dir>/scripts/contract_snapshot.py" inject-scripts \
  --html templates/index.html --before bundle.js --scripts components/chart.js \
  --format '<script src="{{ url_for(\'static\', filename=\'{src}\') }}"></script>'

# 4. Laravel Blade ({{ asset('...') }})
python "<skill_dir>/scripts/contract_snapshot.py" inject-scripts \
  --html resources/views/layout.blade.php --before app.js --scripts js/tracker.js \
  --format '<script src="{{ asset(\'{src}\') }}"></script>'
```

---

### 2.4 Virtualenv Test Runner (`run-tests`)

Runs tests using the auto-detected workspace virtual environment (`.venv`, `venv`, `env`) with headless environment variables (`MPLBACKEND=Agg`, `QT_QPA_PLATFORM=offscreen`, `CI=true`) and execution timeouts:

```bash
# Run unittest discovery
python "<skill_dir>/scripts/contract_snapshot.py" run-tests --path . -- discover tests -p "test_*.py"

# Run pytest suite
python "<skill_dir>/scripts/contract_snapshot.py" run-tests --path . --runner pytest -- tests/ -v

# Run direct module in virtualenv (e.g. documentation, static typecheckers)
python "<skill_dir>/scripts/contract_snapshot.py" run-tests --path . -m mypy src/

# Run Django management commands with auto-detected settings
python "<skill_dir>/scripts/contract_snapshot.py" run-tests --path . manage.py check
python "<skill_dir>/scripts/contract_snapshot.py" run-tests --path . manage.py test

# Execute quick inline verification in virtualenv
python "<skill_dir>/scripts/contract_snapshot.py" run-tests --path . -c "import pkg; print(pkg.__all__)"
```

---

### 2.5 Multi-Language Code Health Auditor (`code_health_audit.py`)

Enforces quantitative budgets (files $\le 350/500$ L, classes $\le 10/12$ methods, functions $\le 40$ L):

```bash
# Directory-level triage (group lines by subfolder)
python "<skill_dir>/scripts/code_health_audit.py" --path . --by-dir

# Multi-target audit
python "<skill_dir>/scripts/code_health_audit.py" --path src/main.py src/services/

# Split point preview (inspect lines safely before editing)
python "<skill_dir>/scripts/code_health_audit.py" --split-preview src/app.py:280:10

# Section & banner outline (view classes and banners without code)
python "<skill_dir>/scripts/code_health_audit.py" --inspect-sections src/main.py

# Pre-commit strict gate (exit code 1 on CRITICAL breach)
python "<skill_dir>/scripts/code_health_audit.py" --path src/ --strict
```

---

## 3. Complete Scenario Combinations Matrix

| Scenario / Objective | Mode / Target | Key Parameters | Exact Runnable Command |
| :--- | :--- | :--- | :--- |
| **Directory-Level Triage** | Group line counts by subfolder | `--path <dir> --by-dir` | `python "<skill_dir>/scripts/code_health_audit.py" --path . --by-dir` |
| **Multi-Target Audit** | Multiple files/dirs in one run | `--path <f1> <d2>` | `python "<skill_dir>/scripts/code_health_audit.py" --path src/main.py src/services/` |
| **Split Point Preview** | View lines around split safely | `--split-preview <file>:<line>[:window]` | `python "<skill_dir>/scripts/code_health_audit.py" --split-preview src/app.py:280:10` |
| **Section & Banner Outline** | Inspect classes/banners without inline code | `--inspect-sections <file>` | `python "<skill_dir>/scripts/code_health_audit.py" --inspect-sections src/main.py` |
| **Record Reference Anchor & Worktree** | Git commit anchor & parallel worktree recipe | `anchor --path <dir>` | `python "<skill_dir>/scripts/contract_snapshot.py" anchor --path .` |
| **Capture Baseline Contract** | Snapshot to .refactor/baseline.json | `capture --path <dir>` | `python "<skill_dir>/scripts/contract_snapshot.py" capture --path .` |
| **Interactive Surface Map** | Inventory of selects, modals, globals, routes | `inspect --path <dir>` | `python "<skill_dir>/scripts/contract_snapshot.py" inspect --path .` |
| **Stylesheet & Specificity Audit** | Audit @imports, banners, CRLF & !important | `inspect-css --path <file_or_dir>` | `python "<skill_dir>/scripts/contract_snapshot.py" inspect-css --path styles/` |
| **Init Campaign State** | Track campaign in .refactor/state.json | `state --init` | `python "<skill_dir>/scripts/contract_snapshot.py" state --init --target <dir> --plan .refactor/plan.md --phases 4` |
| **Init Campaign with Defect Scan** | Opt-in candidate defect audit | `state --init --scan-defects` | `python "<skill_dir>/scripts/contract_snapshot.py" state --init --target <dir> --scan-defects` |
| **Initialize Plan & State** | Plan subcommand | `plan --path <dir>` | `python "<skill_dir>/scripts/contract_snapshot.py" plan --path . --phases 4` |
| **Show Campaign Progress** | Check active phase and status | `state --show` | `python "<skill_dir>/scripts/contract_snapshot.py" state --show` |
| **Save Phase Checkpoint** | Save sub-phase note & prevent token drain | `state --checkpoint` | `python "<skill_dir>/scripts/contract_snapshot.py" state --checkpoint --note "Slices 1-3 complete"` |
| **Advance Campaign Phase** | Mark phase complete and advance | `state --advance` | `python "<skill_dir>/scripts/contract_snapshot.py" state --advance --phase 1` |
| **Record Discovered Latent Defect** | Quarantine defect to .diagnostics/ without plan drift | `state --record-defect` | `python "<skill_dir>/scripts/contract_snapshot.py" state --record-defect --file src/app.py --symbol run --rule MUTABLE_DEFAULT_ARG --message "items=[] persists state"` |
| **Per-Slice & Checkpoint Verification** | Diff against baseline contract | `verify --path <dir> --strict` | `python "<skill_dir>/scripts/contract_snapshot.py" verify --path <dir> --strict` |
| **Multi-Directory Verification** | Verify contract across source and test packages | `verify --path <dir1> <dir2> --strict` | `python "<skill_dir>/scripts/contract_snapshot.py" verify --path erp tests/erp --strict` |
| **Post-Refactor Regression Audit** | Diff live tree directly against pre-refactor Git SHA | `verify --path <dir> --git-ref <sha> --strict` | `python "<skill_dir>/scripts/contract_snapshot.py" verify --path . --git-ref HEAD~1 --strict` |
| **Unified 3-Tier Diagnostic** | 1-call AST diff + Docker audit + live CDP UI | `diagnose --path <dir>` | `python "<skill_dir>/scripts/contract_snapshot.py" diagnose --path .` |
| **Line-Ending Normalizer** | Normalize files to LF/CRLF before editing | `normalize-eol --path <dir> --to lf` | `python "<skill_dir>/scripts/contract_snapshot.py" normalize-eol --path . --to lf` |
| **Line-Ending Agnostic Patch** | Search/replace without shell quoting issues | `patch --file <f> --find ".." --replace ".."` | `python "<skill_dir>/scripts/contract_snapshot.py" patch --file index.html --find "old" --replace "new"` |
| **Safe HTML Script Injector (Plain)** | Insert modular <script> tags safely into HTML | `inject-scripts --html <f> --scripts ..` | `python "<skill_dir>/scripts/contract_snapshot.py" inject-scripts --html index.html --before app.js --scripts /static/js/a.js` |
| **Template Script Injector (Django)** | Insert <script> with Django static tag | `inject-scripts --format '<script src="{% static ...' ` | `python "<skill_dir>/scripts/contract_snapshot.py" inject-scripts --html index.html --before app.js --scripts js/a.js --format '<script src="{% static \'{src}\' %}"></script>'` |
| **Template Script Injector (Jinja2)** | Insert <script> with Flask url_for | `inject-scripts --format '<script src="{{ url_for ...' ` | `python "<skill_dir>/scripts/contract_snapshot.py" inject-scripts --html index.html --before app.js --scripts a.js --format '<script src="{{ url_for(\'static\', filename=\'{src}\') }}"></script>'` |
| **Venv Automated Test Runner (Unittest)** | Run workspace unit tests in target virtualenv | `run-tests --path <dir> -- [args...]` | `python "<skill_dir>/scripts/contract_snapshot.py" run-tests --path . -- discover tests -p "test_*.py"` |
| **Venv Test Runner (Pytest)** | Run pytest suite in target virtualenv | `run-tests --runner pytest -- [args...]` | `python "<skill_dir>/scripts/contract_snapshot.py" run-tests --path . --runner pytest -- tests/ -v` |
| **Venv Direct Module Execution** | Run module (sphinx, mypy, pytest) in virtualenv | `run-tests -m <module> [args...]` | `python "<skill_dir>/scripts/contract_snapshot.py" run-tests --path . -m sphinx -W documentation/ _build/` |
| **Venv Django Command Runner** | Run manage.py with auto DJANGO_SETTINGS_MODULE | `run-tests --path <dir> manage.py [args]` | `python "<skill_dir>/scripts/contract_snapshot.py" run-tests --path . manage.py check` |
| **Venv Direct Python Verification** | Run Python one-liner in target virtualenv | `run-tests -c "<code>"` | `python "<skill_dir>/scripts/contract_snapshot.py" run-tests --path . -c "import pkg; print(pkg.__all__)"` |
| **Token-Optimized Static Quality Gate** | Run ruff/mypy on slice (top-5 capped, auto-skip) | `typecheck --path <slice>` | `python "<skill_dir>/scripts/contract_snapshot.py" typecheck --path enhancer/udf/` |
| **Headless CDP Layout Audit** | Tier 3 UI verification (100% automated, default) | `verify-ui --url <url>` | `python "<skill_dir>/scripts/contract_snapshot.py" verify-ui --url $APP_URL` |
| **Live Browser UI Audit** | Attach to open visible Chrome (requires Allow) | `verify-ui --url <url> --live` | `python "<skill_dir>/scripts/contract_snapshot.py" verify-ui --url $APP_URL --live` |
| **Container Sync & Health Check** | Tier 2 Docker container file sync check | `audit-container --container <name>` | `python "<skill_dir>/scripts/contract_snapshot.py" audit-container --path . --container tracker --sync-check app.py` |
| **Generate Scoped Contract Test** | Emit unittest regression suite scoped to target | `generate-smoke-test --path <dir>` | `python "<skill_dir>/scripts/contract_snapshot.py" generate-smoke-test --path <dir> --out tests/test_refactor_contract.py` |
| **Discover Optional Tools** | Probe cdp_inspect & docker_audit | `probe-tools` | `python "<skill_dir>/scripts/contract_snapshot.py" probe-tools` |
| **Pre-Commit Strict Gate** | Exit 1 on critical breach | `--path <dir> --strict` | `python "<skill_dir>/scripts/code_health_audit.py" --path src --strict` |

