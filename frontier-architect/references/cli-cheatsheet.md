# Frontier Architect & System Diagnostics CLI Cheatsheet

Consult this quick-reference sheet during **Phase 1B (Diagnostics)** and **Phase 6 (Plan Execution & Milestone Sign-Off)** to avoid `--help` round-trips and quote-stripping errors on Windows PowerShell.

---

## 1. Plan Continuation Engine (`scripts/plan_engine.py`)

```bash
# Initialize or register a markdown plan (.TODO/<slug>.md, .plans/<slug>.md, or explicit path)
python skills/frontier-architect/scripts/plan_engine.py init <plan_or_slug> --root .

# Inspect visual progress bar, active milestone, and verification baseline
python skills/frontier-architect/scripts/plan_engine.py status <plan_or_slug> --root .

# Emit ONLY the active milestone's checklist items and verifiers (Zero-Token Slicer)
python skills/frontier-architect/scripts/plan_engine.py next <plan_or_slug> --root .

# Run verification command (auto-normalizes leading .venv/bin/python on Windows & parses unittest/pytest counts)
python skills/frontier-architect/scripts/plan_engine.py verify <plan_or_slug> --command "<test_cmd>" --root .

# Advance completed milestone (patches [ ] -> [x] in-place and emits copy-pasteable git commit snippet)
python skills/frontier-architect/scripts/plan_engine.py advance <plan_or_slug> --milestone <N> --commit <sha> --root .

# Log mandatory 4-Dimensional Retrospective telemetry (dual-writes to .frontier/state.json and retrospectives.json)
python skills/frontier-architect/scripts/plan_engine.py retrospective <plan_or_slug> \
  --milestone <N> --grade A --tri "plan_engine:5,diagnose:5" --hypotheses 1 \
  --learn "<reusable insight>" --escalate "none" --root .

# Lookup historical plans, commit SHAs, and retrospective lessons
python skills/frontier-architect/scripts/plan_engine.py lookup "<keyword_or_sha>" --root .
```

---

## 2. Browser UI, Layout & Multi-Statement JS Inspection (`diagnose.py ui` / `cdp_inspect.py`)

```bash
# Attach to active visible Chrome tab (--live) and audit DOM bounding boxes & overflow
python skills/system-diagnostics/scripts/diagnose.py ui --url http://localhost:8000 --live --audit-layout --selectors "#app,.card"

# Evaluate multi-statement JS in page context via --eval-file (avoids PowerShell quote stripping)
python skills/system-diagnostics/scripts/diagnose.py ui --url http://localhost:8000 --live --eval-file scratch/probe_dom.js

# Isolated headless inspection with screenshot capture
python skills/system-diagnostics/scripts/diagnose.py ui --url http://localhost:8000 --headless --audit-layout --screenshot scratch/ui.jpg
```

---

## 3. Changelog Echo & Standalone Skill Packaging (`diagnose.py`)

```bash
# Record completed milestone in CHANGELOG.md (<=150L auto-archived) and emit git commit snippet
python skills/system-diagnostics/scripts/diagnose.py changelog add \
  --title "<Milestone Title>" --type feat --summary "<1-line summary>" --verify "<test_cmd>" --path .

# Package standalone .skill archive (resolves SSOT shims into full scripts & strips tests/evals per /skill-creator)
python skills/system-diagnostics/scripts/diagnose.py package-skill all --out dist/
```

---

## 4. Windows PowerShell Multi-Line & Quoting Rules

- Never pass nested quotes inside `python -c "..."` in PowerShell (PowerShell strips inner `"` before Python parses argv).
- Pipe a PowerShell single-quoted here-string (`@' ... '@ | python -`) or use `--eval-file <path>`.
