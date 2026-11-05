# Architectural Implementation & Roadmap: Opportunistic Formatter & Line Discipline Engine

**Context & Origin**:
Resolved via `/grill-me` and `/frontier-architect` following post-mortem analysis of conversations:
- [`f46f2b6c-e750-4baf-996a-7e5d8199cdb7`](conversation://f46f2b6c-e750-4baf-996a-7e5d8199cdb7)
- [`6cdbdf76-0caa-4fac-9bce-1abeb5f8ed1d`](conversation://6cdbdf76-0caa-4fac-9bce-1abeb5f8ed1d)

---

## 1. Architectural Accomplishments (Completed in Current Turn)

### A. Dedicated, Decoupled Formatter Module (`code_formatter_engine.py`)
- **Single Responsibility Principle (SRP)**: Rather than appending $\sim 100$ lines into `auxiliary_tool_bridge.py` (which is already at 445 lines and approaching the 500-line hard ceiling), we created a focused module:
  [`code_formatter_engine.py`](file:///C:/Users/User/.gemini/config/skills/refactor-monolith/scripts/code_formatter_engine.py) (147 lines, 112 SLOC, 0 critical modularity breaches).
- **Supported Formatters**:
  - **Python**: `.venv/Scripts/ruff` or `ruff format` on PATH; fallback to `black`.
  - **JavaScript / TypeScript / CSS / SCSS / HTML / JSON**: `node_modules/.bin/prettier` or `npx --no-install prettier --write` or `prettier` on PATH.
  - **Go**: `gofmt -w`.
  - **Rust**: `rustfmt`.
  - **Dart**: `dart format`.

### B. Resilient Hybrid Gate
- **Tool Absent**: Graceful, silent bypass (`SLOC verified`). No hard dependencies are imposed on projects that lack npm/ruff.
- **Tool Present + Syntax Error**: Fails fast (returns exit code 1) and prints compiler/syntax errors immediately, preventing broken ASTs from proceeding to test runners.
- **Slice-Only Scoping**: Formatters strictly process `--files <active_slice_files>`. **Never runs repository-wide**, guaranteeing that untouched files harboring quarantined defects in `.diagnostics/defect_catalog.json` maintain static line numbers.

### C. CLI & Verification Ladder Integration
- Standalone CLI command:
  ```bash
  python "<skill_dir>/scripts/contract_snapshot.py" format --files <f1> <f2>
  ```
- Verification Ladder integration:
  ```bash
  python "<skill_dir>/scripts/contract_snapshot.py" verify --path <slice> --strict [--format]
  ```

### D. SLOC Code Health Auditor
- [`code_health_audit.py`](file:///C:/Users/User/.gemini/config/skills/refactor-monolith/scripts/code_health_audit.py) now evaluates modularity budgets against **Source Lines of Code (SLOC)** via `compute_sloc()`, discounting blank lines, docstrings, and comments.
- Evaluates `Lines (SLOC)` in table outputs, completely removing artificial incentives for agents to "code-golf" or squash formatting.

---

## 2. Follow-Up Extensions for Future Conversations

For teams or workspaces requiring deeper integration, the following extensions can be carried out:

### 1. Custom Config File Detection
- Check for `.prettierrc`, `.prettierrc.json`, `ruff.toml`, `pyproject.toml`, or `biome.json` at repo root before executing format commands, allowing project-specific print widths (e.g. 100 vs 80 columns) to be respected natively.

### 2. Biome & Prettier Alternative Fast-Path
- If `biome` is present in `node_modules/.bin/biome` or on PATH, use `biome format --write <files>` as a faster 20x alternative to Prettier for large TypeScript/JavaScript/CSS mono-repos.

### 3. C / C++ / Swift Formatter Bindings
- Map `.c`, `.cpp`, `.h`, `.hpp` to `clang-format -i` if detected.
- Map `.swift` to `swift-format` or `swiftformat` if detected.

---

## 3. Reference Verification Commands

```bash
# Run unit tests for the code formatter engine
python -m unittest "C:\Users\User\.gemini\config\skills\refactor-monolith\tests\test_code_formatter_engine.py"

# Run code health audit on the new module
python "C:\Users\User\.gemini\config\skills\refactor-monolith\scripts\code_health_audit.py" --path "C:\Users\User\.gemini\config\skills\refactor-monolith\scripts\code_formatter_engine.py"
```
