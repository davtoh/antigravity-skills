# Environment Safety, Windows Resilience & Dual Output Rules

Consult this reference for **dev server reload safety**, **Windows PowerShell/CRLF hygiene**, **Dual Output formatting**, and **post-session retrospective ordering**.

---

## 1. Execution Discipline & Dev Server Safety

1. **Dev Server & File Watcher Safety**:
   - Modifying backend or test files in watched directories triggers auto-reloaders (`StatReload`, `uvicorn --reload`, `vite`, `nodemon`), aborting in-flight HTTP/WebSocket requests, disrupting containers, and flooding the user with browser permission prompts.
   - **Isolate Test Fixtures**: Keep test fixtures outside watched application trees.
   - **Single-Pass Atomic Edits**: Batch multi-line edits into a single atomic turn rather than triggering successive reloads.
   - **Headless Sandbox for Multi-Step Audits**: Use `--headless` for iterative automated layout audits to avoid repeated desktop permission prompts.
2. **Reactive Task Discipline**:
   - Never poll `manage_task status` or sleep in a loop; background tasks wake up the agent reactively upon completion.

---

## 2. Windows Shell & Tooling Resilience

1. **PowerShell Script Policy Bypass**: Invoke Node/NPM CLI tools via `cmd /c npx -y <tool> ...` so `npx.ps1` execution policy does not block execution.
2. **Codebase Grepping**: Prefer `git grep -n "<pattern>"` over `rg` unless `rg` is explicitly verified in `%PATH%`.
3. **Line Ending & File Editing Safety**:
   - Before multi-line `edit_file` replacements on Windows repos with `core.autocrlf = true`, inspect line endings (`CRLF` vs `LF`):
     `python -c "print('CRLF' if b'\r\n' in open('path/to/file','rb').read() else 'LF')"`
   - Match target line endings exactly in `Target` and `Replacement`.
   - Never write disposable Python file-patching scripts in `scratch/` when `edit_file` hits a whitespace mismatch; read exact context and apply targeted edits.
4. **Virtualenv Auto-Detection & Python Execution**:
   - `run_diagnose.py` auto-resolves `.venv/Scripts/python.exe` (Windows) or `.venv/bin/python` (POSIX). Never invoke bare system `python`/`python3` when `.venv` exists; if `.venv` is absent, prompt the user to create it (`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`).

---

## 3. Dual Output Reporting Rules

### Simple / Single-Step Bug
- **Trigger**: Single straightforward symptom and root cause (e.g., typo, broken selector, missing import).
- **Format**: Concise inline Markdown response in chat (no artifact overhead).
- **Content**: Root cause summary, surgical diff, and one-liner verification output.

### Complex / Multi-Symptom Bug
- **Trigger**: Multiple symptoms, cross-cutting layers (frontend + container + backend), or layout regressions.
- **Format**: Structured Markdown Artifact (`RequestFeedback: true`, `UserFacing: true`).
- **Content**: Executive summary, complete Symptom-to-Root-Cause Matrix, empirical before/after verification (`DOMRect`, test runs, log diffs), and Axiom 9 Honest Verification Matrix. Point the user to the artifact in chat.

---

## 4. Retrospective & Closeout Order (Step 4.3)

For non-trivial sessions (`>= 20` steps, `>= 1` retry, or Mac/cross-platform RCA), run in this exact order:
1. `python "<config_dir>/skills/app-debugger/scripts/run_diagnose.py" debug-retro --symptom "<Symptom>" --cause "<Cause>" --status <verified|unconfirmed> --cid <cid>` (add `--plan <slug>` when tied to an active `.frontier` plan—auto-persists `followup_cids` and backfills `LEARNING_SCAFFOLD.md`—plus `--learn` / `--skill-learn`; updates `DEBUG_RETRO.md`, `.diagnostics/LEARNING_SCAFFOLD.md` or `.frontier/LEARN_QUEUE.md`, and prints `--- Turn-End Echo ---`).
2. `python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" transcript-audit --latest 1 --workspace .` (**never** run `transcript-audit` or `digest` *before* `debug-retro`).
3. Copy-paste the emitted `### Continuous Learning & Introspective Options` block (`diagnose.py transcript-audit --latest 1`, `plan_engine.py digest <slug> --backfill --write-scaffold`, `/learn`), and promote reusable CDP/runtime verification scripts into Chrome-gated `tests/test_*_e2e*.py` tests or `run_diagnose.py probe save`.
