---
name: refactor-monolith
description: >-
  Audit, plan, and safely execute zero-regression decomposition of oversized files ("God Files" exceeding 350-500 lines), complex classes ("God Classes" exceeding 10-12 methods), or monolithic codebases across Python, JS/TS, CSS/SCSS, Dart/Flutter, Go, Rust, and C#. Enforces quantitative modularity budgets, contract snapshots (DOM IDs, routes, globals), and persistent in-repo state in .refactor/ (state.json, plan.md, baseline.json) for seamless continuation via '/refactor-monolith continue'. Features 1-phase turn gates, atomic slicing, and safe bailouts. Make sure to use this skill whenever the user asks to split or break down large files, refactor a monolith, modularize a project, continue a migration, reduce class or method count, audit codebase modularity, apply SRP, or decompose legacy code without breaking imports, DOM interactions, or test suites, even if they do not explicitly say 'monolith'.
compatibility: >-
  Delegates shared scanners (css_inspector.py, surface_scanners.py) to system-diagnostics/scripts/ SSOT in monorepo; run diagnose.py package-skill for standalone .skill distribution.
---

# Refactor Monolith: Adaptive Decomposition, Parity & Modularity Engine

**Refactor Monolith** provides a deterministic, 100% self-contained workflow for auditing codebase modularity, decomposing oversized "God Files" and "God Classes", and guaranteeing **zero behavioral regressions** ($\Delta\text{Behavior} \equiv 0$) across backend routes, services, and frontend DOM interactions.

---

## 1. Quantitative Modularity Budgets

| Code Element | Healthy Target | Soft Warning (Refactor Trigger) | Hard Ceiling (Mandatory Split) | Remediation Strategy |
| :--- | :--- | :--- | :--- | :--- |
| **Source File** | 150 – 300 SLOC | **350 SLOC** | **500 SLOC** | Extract domain submodules (`routers/`, `services/`, `repositories/`, `components/`). |
| **Class / Struct / Group** | 50 – 180 lines | **10 methods** (or 200 lines) | **12 methods** (or 300 lines) | Decompose into focused collaborator classes, domain services, or cohesive mixins. |
| **Function / Method / Rule** | 10 – 25 lines | **30 lines** | **40 lines** | Extract pure helper functions; replace deep nesting with guard clauses or strategy tables. |
| **Route / Controller** | 5 – 15 lines | **15 lines** | **25 lines** | Keep handlers thin: parse request, call a domain service, and return the response. |

- **SLOC-First & Heuristic Interpretation**: Budgets measure **Source Lines of Code (SLOC)** (discounting blank lines, docstrings, comments). **350 SLOC** is a heuristic trigger—if a ~350–450L file is cohesive with no clean SRP split, leave it intact. **500 SLOC** requires structural decomposition (never cosmetic compression or code-golfing).

---

## 2. Standardized `.refactor/` Workspace Architecture

Persistent refactoring metadata lives in `<workspace>/.refactor/` (`state.json`, `plan.md`, `baseline.json`, `scripts/`, `artifacts/`, and a self-contained `.gitignore`):
- **Zero-Pollution & Anti-Vendoring Mandate**: Never copy skill scripts into `<workspace>/scripts/` (run from `<skill_dir>/scripts/...`), place one-off project helpers in `.refactor/scripts/`, and never modify the target repo's root `.gitignore`.

---

## 3. Fast CLI Quick Reference

*(Exhaustive flag permutations & 36-row Scenario Combinations Matrix: [`references/cli-reference.md`](./references/cli-reference.md).)*

```bash
# 1. Campaign state & planning
python "<skill_dir>/scripts/contract_snapshot.py" state --show
python "<skill_dir>/scripts/contract_snapshot.py" plan --path <target_dir> --phases 4 [--scan-defects]
python "<skill_dir>/scripts/contract_snapshot.py" state --init --target <dir> --plan .refactor/plan.md --phases 4 [--scan-defects]
python "<skill_dir>/scripts/contract_snapshot.py" state --checkpoint --note "Completed Slices X-Y"
python "<skill_dir>/scripts/contract_snapshot.py" state --advance --phase 1

# 2. Golden contract baseline, formatting & verification
python "<skill_dir>/scripts/contract_snapshot.py" anchor --path <target_dir>
python "<skill_dir>/scripts/contract_snapshot.py" capture --path <target_dir>
python "<skill_dir>/scripts/contract_snapshot.py" format --files <slice_file1> <slice_file2>
python "<skill_dir>/scripts/contract_snapshot.py" verify --path <target_dir> --strict [--format]

# 3. Virtualenv-isolated automated tests (headless guards, CI=true; forwards -k, -v, -p cleanly)
python "<skill_dir>/scripts/contract_snapshot.py" run-tests --path <dir> -- discover tests -p "test_*.py" -v -k "test_feature"
python "<skill_dir>/scripts/contract_snapshot.py" run-tests --path <dir> --runner pytest -- tests/ -v -k "test_unit"

# 4. Batch modularity audits (ast, brace, stylesheet, fallback modes; auto-excludes vendor/minified files)
python "<skill_dir>/scripts/code_health_audit.py" --path <target1> <target2> ... --show-methods
python "<skill_dir>/scripts/code_health_audit.py" --path <dir> --by-dir

# 5. Cross-platform EOL normalization, patching & template script injection
python "<skill_dir>/scripts/contract_snapshot.py" normalize-eol --path <active_slice> --to lf
python "<skill_dir>/scripts/contract_snapshot.py" patch --file <f> --find "<target>" --replace "<replacement>"
python "<skill_dir>/scripts/contract_snapshot.py" inject-scripts --html <f> --before <target> --scripts <srcs...> [--format '<script src="{src}"></script>']

# 6. Passive defect quarantine hook (zero plan.md drift)
python "<skill_dir>/scripts/contract_snapshot.py" state --record-defect --file <f> --symbol <s> --rule <r> --message "<m>"
```

---

## 4. Execution Modes & Turn-Boundary Discipline

- **Mode A: Single-File Fast-Track (`SINGLE_FILE`)**: Specific file/class named or $\le 2$ critical files $\rightarrow$ outline cohesion clusters, extract submodules sequentially behind a backward-compatible facade (`__init__.py` or re-export module), verify per slice, and finish in the current turn without multi-file roadmap ceremony.
- **Mode B1 (`PROJECT_CAMPAIGN` Init)**: Multi-monolith repo $\rightarrow$ design a layered target DAG (`Level 0 models/utils -> Level 1 repositories -> Level 2 services -> Level 3 routers/UI -> Level 4 facade entrypoints`), write `.refactor/plan.md` with `[ ]` checkboxes, initialize `.refactor/state.json`, update `AGENTS.md` with a Monolith Freeze and ownership map, and authorize **Phase 1 (or Sub-Phase 1.1) only** (*1-Phase Turn Gate*; subsequent phases *Deferred to Next Turn*).
  - **Effort-Weighted Phase Sizing & Domain Isolation**: Target $\sim 600–1,000$ SLOC per phase/turn (1 major monolith $\ge 600$L or 2–3 cohesive files $\le 400$L); isolate by runtime/domain affinity (never mix backend test suites with browser DOM controllers).
  - **Turn Ceiling Gate ($\le 20–25$ tool calls / 1–2 monoliths)**: Checkpoint state (`contract_snapshot.py state --checkpoint --note "Completed Slices X-Y"`), record the milestone and emit a commit snippet via `python skills/system-diagnostics/scripts/diagnose.py changelog add --title "Completed Slices X-Y" --type refactor --summary "<Summary>" --verify "<Command>"`, reuse the emitted `git commit` snippet, and **STOP** advising `/refactor-monolith continue` in a fresh chat.
- **Mode B2 (`CAMPAIGN_RESUME` / `/refactor-monolith continue`)**: Check `.refactor/state.json` and `.refactor/plan.md` first, automatically select the active phase / next pending `[ ]` milestone without asking the user to pick a file, execute slices within the $\sim 600–1,000$L effort budget, run Step 5 verification, checkpoint/advance state, and stop.
- **Mode C (`REGRESSION_RECOVERY` / Fix Mode)**: Run `python "<skill_dir>/scripts/contract_snapshot.py" diagnose --path <target_dir> [--git-ref <sha>] [--url $APP_URL] [--container <name>]` as Step 1 (no guesswork or ad-hoc CDP scripts) to compare AST/DOM contracts against `.refactor/baseline.json`, check Docker sync and headless CDP layout, avoid infinite reload traps on `window.*` built-ins, and apply surgical fixes (`patch` / `inject-scripts`).

---

## 5. Phase 0: Project Rules Check, Scope Detection & Baseline Anchor

1. **Existing Campaign**: If `<workspace>/.refactor/state.json` exists, run `state --show` and jump to Mode B2.
2. **Project Memory & Pre-Flight Asset Check**: Respect `AGENTS.md` / `.agents/rules/` and honor any user-specified planner (`/plan` or architectural planner) before modifying production code. Do not block planning on missing host dependencies (e.g. OpenCV/CUDA); never run `pip install` into host environments. Exclude vendor/minified assets (e.g. `slick.js`) and verify whether stylesheets (`static/css/main.css`) are compiled from upstream SCSS (`static/scss/theme/`) before splitting directly.
3. **Structural Audit & Golden Baseline**: Run `code_health_audit.py --path <target_dir> --by-dir`, `contract_snapshot.py anchor --path <target_dir>`, and `contract_snapshot.py capture --path <target_dir>` (writes `.refactor/baseline.json`).

---

## 6. The 5-Step Zero-Regression Decomposition Workflow

1. **Step 1 — Zero-Token Structural Audit**: Run `code_health_audit.py --show-methods` or `--split-preview <file>:<line>[:window]`. **Batch Audit Mandate**: Write all cohesive submodules for the active slice first, then audit them together in one call (`code_health_audit.py --path <file1> <file2> ... --show-methods`).
2. **Step 2 — Cohesion Clustering, Surface Map & Facade Design**:
   - Run `contract_snapshot.py inspect --path <target_dir> --show-routes` and `inspect-css --path <css_path>` (`@import` chains, section banners, CRLF, `!important`).
   - Load on-demand playbooks: [`references/decomposition-patterns.md`](./references/decomposition-patterns.md) (Python DAG routes, Bidirectional Proxy Pattern for monkeypatched globals) and [`references/language-playbooks.md`](./references/language-playbooks.md) (TS barrel `export *` + custom hooks, vanilla JS `window.<Namespace>` & DOM ID preservation, ITCSS stylesheet order, Go same-package file split, Rust/Dart/C#).
3. **Step 3 — Atomic Slice Extraction**: Keep new modules $< 350$ lines (classes $\le 10–12$ methods, functions $\le 40$ lines); preserve docstrings, rationale comments, and mathematical algorithms verbatim; use `normalize-eol`, `patch`, and `inject-scripts`. **Anti-Mega-Batch Rule**: Never extract $> 1–2$ files/routers without verifying contract parity (`Slice 1 -> Verify -> Slice 2 -> Verify -> Wire Facade`).
4. **Step 4 — Wire Facade & Per-Slice Contract Verification**: Re-export moved symbols in the monolith facade, enforce acyclic DAG (`Facade -> Routers/UI -> Services -> Repositories -> Leaf Utils`), and run `contract_snapshot.py verify --path <target_slice> --strict` (with optional `--format` / `contract_snapshot.py format --files ...`).
5. **Step 5 — 3-Tier Closed-Loop Verification Ladder (Axiom 9)**:
   - **Tier 1 (Static & Tests)**: `contract_snapshot.py run-tests --path <dir> -- discover tests -p "test_*.py"`, `code_health_audit.py --path <target_dir> --strict`, `contract_snapshot.py verify --path <target_dir> --strict`, and `contract_snapshot.py generate-smoke-test --path <target_dir>`.
   - **Tier 2 (Container Sync)**: `contract_snapshot.py audit-container --path <dir> --container <name> --sync-check <files...>`.
   - **Tier 3 (Live Browser CDP)**: `contract_snapshot.py verify-ui --url $APP_URL` (if offline, report honestly under Axiom 9: `"Tier 1: VERIFIED | Tier 2: SKIPPED | Tier 3: SKIPPED (Server offline / URL unset)"`).

---

## 7. Two-Tier Execution & Reactive Turn-Yield Protocol

1. **Sync Wait Optimization (Tier 1)**: Pass `WaitMsBeforeAsync: 10000` on fast targeted slice test runs ($\le 5$s) so they finish in-turn.
2. **Reactive Turn-Yield Mandate (Tier 2)**: When a command backgrounds (`Tool is running as a background task with task id: <task_id>`), **do NOT** poll `manage_task(action='status')` or call `time.sleep` / `Start-Sleep`; output a 1-sentence handoff and end the turn immediately for reactive wakeup.

---

## 8. Asymmetric Defect Protocol, Quarantine & Targeted Slicing

Enforce the **Refactoring Invariant** ($\Delta(\text{Observable Behavior}) \equiv 0$) and **behavior preservation**: never fix production business-logic bugs inline during decomposition turns.
1. **Zero-Token Default vs. Opt-In Scan**: Regular `continue` turns skip defect scanning (`0` extra tokens). Passing `--scan-defects` to `plan` or `state --init` scans ASTs (`SYNTAX_ERROR`, `MUTABLE_DEFAULT_ARG`, `UNREACHABLE_CODE`, `UNDEFINED_NAME`) into `.diagnostics/defect_catalog.json` and `.diagnostics/DEFECT_CATALOG.md`, linking once in `.refactor/plan.md` (zero `plan.md` table drift).
2. **Passive Quarantine Safety Net & Lifecycle Handoff**: Quarantine bugs discovered in-flight via `contract_snapshot.py state --record-defect --file <f> --symbol <s> --rule <r> --message "<m>"`. At campaign closeout, `campaign_manager.py` outputs copy-pasteable handoff commands (`diagnose.py scaffold-defect`) for `/app-debugger` and `/frontier-architect`.
3. **Phase-Isolation & Targeted Slicing Rules**:
   - **Hermetic Environment Invariant**: Always run tests via `contract_snapshot.py run-tests --path . -- <args>` (auto-resolves `.venv` and sets `QT_QPA_PLATFORM=offscreen`, `MPLBACKEND=Agg`), never bare `python` or hardcoded OS-locked `.venv\Scripts\python.exe`.
   - **Targeted Slicing (`run-tests`, `verify`, `normalize-eol`)**: Target only the active slice (`discover tests -p "test_<slice>*.py"`, `verify --path <target_slice> --strict`, `normalize-eol --path <active_slice> --to lf`). Never run repo-wide `verify --path .` or global `normalize-eol` during intermediate slices (reserve repo-wide `verify` for campaign closeout).
   - **Environment & Out-of-Phase Failures**: Quarantine missing GUI/hardware dependency gaps (`state --record-defect --file <path> --symbol <sym> --rule ENVIRONMENT_DEP --message "<missing_dep>"`) or pre-existing out-of-phase failures without expanding turn scope.
   - **Safe Deprecated Script Facades**: When relocating legacy scripts with top-level side effects or legacy imports (`past`, `future`) to `deprecated/`, wrap facade imports in `try...except ImportError` or lazy `__getattr__` lookups rather than eager `from .deprecated.mod import *`.

---

## 9. Strict No-Staging Invariant & Working Tree Discipline

- **Never run `git add`, `git rm`, `git checkout --`, `git reset`, or `git clean`** during a refactoring turn (delete superseded monoliths via `Remove-Item` / `os.remove`; leave all changes unstaged for `git diff`).
- Run `git status --short` defensively before milestone closeout to avoid pathspec errors on deleted/renamed files, and reuse the commit snippet from `diagnose.py changelog add`.

---

## 10. Anti-Thrash Stop-Loss, Hot/Cold Split & Anti-Code-Golfing

1. **Performance Guard (Hot/Cold Split)**: Warn explicitly before splitting tight per-frame/NumPy/DSP hot loops that share buffers or memory locality—keep the hot kernel cohesive and extract only cold helpers (CLI, config, I/O, telemetry).
2. **Anti-Thrash Stop-Loss & "Leave at Best Working Version" Bailout**: After 2 failed verification attempts (or when `Parser: fallback` / unknown DSLs resist clean extraction), halt immediately, advise reverting unstable edits to the **best working version**, and escalate via `/plan` or `/grill-me` unless instructed to continue.
3. **Structural vs. Cosmetic Invariant (Anti-Code-Golfing)**: Never squash lines, strip comments, or combine declarations (`one-var`) to beat line budgets.

---

## 11. Pre-Run Verification, References & In-Flight Tool Elevation

```bash
python "<skill_dir>/scripts/code_health_audit.py" --path "<skill_dir>" --strict
python -m unittest discover -s "<skill_dir>/tests"
```
- **References**: [`references/cli-reference.md`](./references/cli-reference.md), [`references/decomposition-patterns.md`](./references/decomposition-patterns.md), [`references/language-playbooks.md`](./references/language-playbooks.md).
- **In-Flight Tool Elevation Protocol**: Fix skill script bugs directly in `<skill_dir>/scripts/` (or `system-diagnostics/scripts/` SSOT), never run git commands against `<skill_dir>` from the project workspace, add a unit test in `<skill_dir>/tests/`, and verify all skill tests pass before resuming.
