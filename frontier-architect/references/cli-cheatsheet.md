# Frontier Architect & System Diagnostics CLI Cheatsheet

Consult this quick-reference sheet during **Phase 1B (Diagnostics)** and **Phase 6 (Plan Execution & Milestone Sign-Off)** to avoid `--help` round-trips and quote-stripping errors on Windows PowerShell.

> `<config_dir>` = `%USERPROFILE%\.gemini\config` (Windows) or `~/.gemini/config` (POSIX). Always use the full quoted path when running from a product repo (relative `skills/...` only resolves inside `<config_dir>`). Note: `<config_dir>` itself is **not** a git repo—run `git -C "<config_dir>/skills" ...` when inspecting skill git state.

> **Launcher:** prefer `sh "<skill_dir>/scripts/py.sh" <script> ...` on POSIX or `& "<skill_dir>/scripts/py.cmd" <script> ...` on Windows PowerShell (`py.cmd` in `cmd.exe`); it resolves `$VIRTUAL_ENV` or the first Python 3.10+ (`py -3`, `python`, `python3`) and preserves exit codes.
> **Interpreter:** every `python` below means `<py>`, the first of `VIRTUAL_ENV`, `python3`, `python`, `py -3` that is Python 3.10+ (see [`claude-adapter.md`](./claude-adapter.md#python-interpreter-py)). Bare `python` can be Python 2 on macOS; `python3` may not exist (or may be a Microsoft Store stub) on Windows.

---

## 1. Plan Continuation Engine (`scripts/plan_engine.py`)

```bash
# Discover existing plans before exploring an unfamiliar repo
python "<config_dir>/skills/frontier-architect/scripts/plan_engine.py" discover --root .

# Initialize or register a markdown plan (.TODO/<slug>.md, .plans/<slug>.md, or explicit path)
python "<config_dir>/skills/frontier-architect/scripts/plan_engine.py" init <plan_or_slug> --root .

# Link a child step plan to a Master Roadmap (when >=4 milestones or >=3 subsystems)
python "<config_dir>/skills/frontier-architect/scripts/plan_engine.py" init .TODO/step_1_<slug>.md --parent <master_slug> --milestone 1 --root .

# Inspect visual progress bar, active milestone, and verification baseline (omit <plan_or_slug> to auto-resolve .frontier/state.json)
python "<config_dir>/skills/frontier-architect/scripts/plan_engine.py" status [<plan_or_slug>] --root .

# Emit ONLY the active milestone's checklist items and verifiers (Zero-Token Slicer)
python "<config_dir>/skills/frontier-architect/scripts/plan_engine.py" next [<plan_or_slug>] --root .

# Run verification command (auto-normalizes leading .venv/bin/python on Windows, streams live, aborts at --timeout 180s [0 disables] with exit 124)
# If exit 124 shows active test progress in partial output, re-run slow suites with --timeout 600 (or --timeout 0); otherwise debug deadlocks / blocking I/O.
python "<config_dir>/skills/frontier-architect/scripts/plan_engine.py" verify <plan_or_slug> --command "<test_cmd>" [--timeout 180] --root .

# Advance completed milestone (patches [ ] -> [x] in-place, records SHA or pending:<base_sha> if uncommitted edits exist, emits git commit snippet, and auto-syncs completed child -> parent master milestone unless --no-sync-parent)
# Never run git add/commit before advance or without user consent; run retrospective sequentially after advance (never in parallel).
python "<config_dir>/skills/frontier-architect/scripts/plan_engine.py" advance <plan_or_slug> --milestone <N> --commit <sha> [--note "<summary>"] [--no-sync-parent] --root .

# Log mandatory 4-Dimensional Retrospective telemetry (dual-writes to .frontier/state.json & retrospectives.json and auto-refreshes LEARNING_SCAFFOLD.md)
# Positional --tri maps to: token_efficiency, hypothesis_accuracy, tool_reliability, architectural_defense (or use named k=score pairs)
python "<config_dir>/skills/frontier-architect/scripts/plan_engine.py" retrospective <plan_or_slug> \
  --milestone <N> --grade A --cid <conv_id> --steps <N> --retries <R> --tri "5,5,5,5" --hypotheses 1 \
  --went-well "<what worked well>" --learn "<project rule>" --skill-learn "<skill/script lesson>" --tool-gap "<gap_or_none>" --escalate "none" --root .

# Targeted Python unittest execution (enforces 180s --timeout guard against deadlocks/hangs)
python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" tests <modules...>

# Project-agnostic Mini-CI parity runner (host --fast or isolated Linux --linux via WSL/Docker; respects .diagnostics/mini_ci.json)
python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" ci --path . --fast [--tests <targets...>] [--skip-lint] [--dry-run]
python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" ci --path . --linux [--backend auto|wsl|docker] [--clean-snapshot] [--dry-run]

# Follow-up /app-debugger escalation linked to an active plan (auto-records followup_cids & refreshes LEARNING_SCAFFOLD.md; run transcript-audit last)
python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" debug-retro --plan <slug> --cid <conv_id> --symptom "<symptom>" --cause "<cause>" --status <verified|unconfirmed>

# Pre-test modularity & function-length audit (catches >40L functions and >N line overruns before unittest)
python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" audit --path <files...> --max-lines 350 --max-fn-lines 40

# Polyglot defect scan across one or multiple paths
python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" scan --path <paths...>

# List active HUD observations & close resolved OBS-NNN entries at milestone/plan sign-off (uses --path, NOT --root)
python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" observations list --path .
python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" observations resolve --id <OBS-NNN> --resolution "<summary>" --commit <sha> --path .

# Architecture, coupling & route/CLI map (supports single root or multiple subpaths)
python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" arch-map --path .

# End-of-plan digest: retro integrity, dual-axis /learn candidates, optional transcript backfill & LEARNING_SCAFFOLD.md (use --all for workspace LEARN_QUEUE.md)
python "<config_dir>/skills/frontier-architect/scripts/plan_engine.py" digest <plan_or_slug> --cids <conv_id...> --backfill --write-scaffold --root .
python "<config_dir>/skills/frontier-architect/scripts/plan_engine.py" digest --all --backfill --write-scaffold --root .

# Deterministic transcript audit (steps, failures, repeated reads, corrections, parallel edits); --cids accepts 8-char prefixes or comma-separated IDs
python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" transcript-audit --cids <conv_id...> [--json] [--brain-dir <dir>]

# Reconcile stale in_progress states, duplicate milestones, and uncheckboxed bullets
python "<config_dir>/skills/frontier-architect/scripts/plan_engine.py" reconcile --root . [--apply]

# Lookup historical plans, commit SHAs, and retrospective lessons
python "<config_dir>/skills/frontier-architect/scripts/plan_engine.py" lookup "<keyword_or_sha>" --root .
```

---

## 2. Browser UI, Layout & Multi-Statement JS Inspection (`diagnose.py ui` / `cdp_inspect.py`)

```bash
# Attach to active visible Chrome tab (--live) and audit DOM bounding boxes & overflow
python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" ui --url http://localhost:8000 --live --capture-runtime --audit-layout --selectors "#app,.card"

# Evaluate multi-statement JS in page context via --eval-file (captures console/JS exceptions by default; pass --no-capture-runtime to opt out)
python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" ui --url http://localhost:8000 --live --capture-runtime --eval-file scratch/probe_dom.js

# Isolated headless inspection with screenshot capture
python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" ui --url http://localhost:8000 --headless --capture-runtime --audit-layout --screenshot scratch/ui.jpg
```

---

## 3. Changelog Echo & Standalone Skill Packaging (`diagnose.py`)

```bash
# Record completed milestone in CHANGELOG.md (<=150L auto-archived) and emit git commit snippet
python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" changelog add \
  --title "<Milestone Title>" --type feat --summary "<1-line summary>" --verify "<test_cmd>" --path .

# Generate a PR description from branch commits, CHANGELOG.md, and completed plans
python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" changelog pr-description --base main --recent 5 --path .

# Package standalone .skill archive (resolves SSOT shims into full scripts & strips tests/evals per /skill-creator)
python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" package-skill all --out dist/
```

---

## 4. Windows PowerShell Hygiene & Quoting Rules

- **No `rg`:** Never assume `rg` is installed on Windows; always use `git grep -n "<pattern>"` (in Git repos) or `Select-String -Pattern "<pattern>"`.
- **No `&&`:** PowerShell 5.1 rejects `&&`; chain commands cleanly with `; if ($LASTEXITCODE -ne 0) { throw "step failed" }`.
- **Virtualenv First:** In Python repositories containing `.venv\`, always run `.venv\Scripts\python.exe`, never bare system `python`.
- **Zero Fragile Quotes:** Never pass nested quotes inside `python -c "..."` or `--eval "..."` in PowerShell (PowerShell strips inner `"` before Python parses `argv`). Use `--eval-file <path>` or pipe a PowerShell single-quoted here-string (`@' ... '@ | python -`).
