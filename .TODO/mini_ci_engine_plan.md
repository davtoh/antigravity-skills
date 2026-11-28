# Implementation Plan: Generic `diagnose.py ci` (Mini-CI Engine)

## Goal
Provide a project-agnostic, stdlib-only local Mini-CI runner (`diagnose.py ci` backed by `system-diagnostics/scripts/mini_ci.py`) that mirrors GitHub Actions CI parity on both host (`--fast`) and Linux (`--linux` via WSL or Docker with isolated `HOME`), working out-of-the-box across both the `antigravity-skills` monorepo and product repositories (e.g., `intelligent_tracker`).

## Architectural Pre-Flight
- **Invariants**:
  - Zero external Python dependencies (Python 3.10+ stdlib only).
  - Never mutate host `$HOME` / `$USERPROFILE` or live repo caches when running `--linux` or `--clean-snapshot`.
  - Respect modularity budgets (`mini_ci.py` <= 300 lines, functions <= 30 lines, `diagnose.py` <= 350 lines).
  - Preserve full cross-platform support (Windows, Linux, macOS; `pathlib.Path`, `sys.executable`, no shell injection).
- **Auto-Detection & Config Override Flow**:
  1. Resolve target workspace `--path` (default `.`).
  2. Load optional `.diagnostics/mini_ci.json` if present (allows project-specific `steps`, `apt_packages`, `pip_packages`, `env`, `docker_image`, `exclude_dirs`, `wsl_distro`).
  3. Otherwise auto-detect layout:
     - **Skills monorepo** (`.github/scripts/validate_skills.py` or multiple `*/tests/test_*.py` dirs): runs `validate_skills.py` (if present) + `unittest discover` per skill `tests/` dir.
     - **Standard Python repo**: runs `ruff check` (if installed and not `--skip-lint`) + `pytest` (if `pytest.ini`/`conftest.py` and pytest installed) or `unittest discover tests` (or targeted `--tests`).
  4. **Execution Backends**:
     - `--fast` (default): runs with host `.venv` Python (auto-resolved via `diagnose.find_virtualenv_python`) and clean CI env (`CI=true`, `MPLBACKEND=Agg`, `QT_QPA_PLATFORM=offscreen`, plus optional `--simulate-ci-chrome`).
     - `--linux`: auto-selects `wsl` (Windows with `wsl.exe`) or `docker` (`python:3.12-slim`), isolates `HOME=$(mktemp -d)`, syncs a hash-keyed venv (WSL) or cached image (Docker) when `requirements.txt` exists, and streams commands safely via stdin (`bash -s`) with zero PowerShell quoting traps.

---

## Milestone 1: Core `mini_ci.py` Engine, `diagnose.py ci` Wiring & Unit Tests
- [x] **`system-diagnostics/scripts/mini_ci.py`**: Implement project-agnostic `mini_ci` module (`<= 300` lines) with:
  - [x] Layout auto-detection (`skills_monorepo` vs `python_repo`) + optional `.diagnostics/mini_ci.json` override loader.
  - [x] Pure builders (`windows_to_wsl_path`, `select_linux_backend`, `create_clean_snapshot`, `build_fast_env`, `build_ci_steps`, `build_wsl_script`, `build_dockerfile`, `build_docker_run_command`).
  - [x] `register_parser(subparsers)` & `cmd_ci(args)` CLI entrypoint (`--path`, `--fast`, `--linux`, `--backend`, `--wsl-distro`, `--docker-image`, `--tests`, `--skip-lint`, `--clean-snapshot`, `--dry-run`).
- [x] **`system-diagnostics/scripts/diagnose.py`**: Register `mini_ci` in `build_parser()` and `"ci": mini_ci.cmd_ci` in `main()` dispatch (+3 lines, stays `< 335` lines).
- [x] **`system-diagnostics/tests/test_mini_ci.py`**: Add comprehensive unit tests covering layout auto-detection (monorepo vs single repo vs `.diagnostics/mini_ci.json`), Windows-to-WSL path conversion, backend selection, clean snapshot exclusion, WSL/Docker command builders, and `--dry-run` / `--fast` execution.
- [x] **Verification**:
  - [x] `python -m unittest discover -s system-diagnostics/tests -p "test_mini_ci.py" -v`
  - [x] `python system-diagnostics/scripts/diagnose.py ci --path . --fast --dry-run`
  - [x] `python system-diagnostics/scripts/diagnose.py ci --path . --linux --dry-run`
  - [x] `python system-diagnostics/scripts/diagnose.py audit --path system-diagnostics/scripts/mini_ci.py system-diagnostics/scripts/diagnose.py`

## Milestone 2: Documentation, Live Linux Parity Run & Full Regression
- [x] **`system-diagnostics/SKILL.md`** & **`frontier-architect/references/cli-cheatsheet.md`**: Document `diagnose.py ci` recipes (`--fast`, `--linux`, `--backend docker`, `--clean-snapshot`, `.diagnostics/mini_ci.json`) and Scenario Combinations Matrix.
- [x] **Live Parity Verification**: Run `python system-diagnostics/scripts/diagnose.py ci --path . --linux` (WSL Ubuntu-24.04 / Python 3.12) and `python .github/scripts/validate_skills.py` end-to-end.

---

## Scenario Combinations Matrix

| Scenario | Command | Expected Result |
|---|---|---|
| Host fast dry-run (monorepo) | `diagnose.py ci --path . --fast --dry-run` | Prints `validate_skills.py` + per-skill `unittest discover` steps, exits `0` |
| Linux WSL dry-run | `diagnose.py ci --path . --linux --backend wsl --dry-run` | Prints bash script with isolated `CLEAN_HOME` and `/mnt/...` path, exits `0` |
| Linux Docker dry-run | `diagnose.py ci --path . --linux --backend docker --dry-run` | Prints `docker build` / `docker run --rm -e HOME=/tmp/mini_ci_home ...`, exits `0` |
| Targeted tests | `diagnose.py ci --path . --fast --tests system-diagnostics/tests/test_mini_ci.py` | Runs only the specified test target |
| Custom project config | `.diagnostics/mini_ci.json` present | Uses configured `steps`, `env`, and `apt_packages` overrides |
