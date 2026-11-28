# Implementation Plan: `mini_ci` Project Agnosticism & GitHub CI Parity

## Goal
Make `diagnose.py ci` (`system-diagnostics/scripts/mini_ci.py`) genuinely project-agnostic across Python (unittest, pytest, `pyproject.toml`, Django, nested `requirements/*.txt`, editable packages), `skills_monorepo` (including `*-workspace` exclusion and default `pyyaml`), and non-Python stacks (`package.json`, `go.mod`, `Cargo.toml`, `pubspec.yaml`), plus add `diagnose.py ci --init` to scaffold `.diagnostics/mini_ci.json` from `.github/workflows/*.yml` and repo markers.

## Architectural Pre-Flight
- **Invariants**:
  - Zero external Python dependencies (Python 3.10+ stdlib only).
  - Split-Before-You-Grow: `mini_ci.py` is currently ~342 lines (near the 350L soft limit); extract detection, stack presets, requirements resolution, and `--init` scaffolding into `system-diagnostics/scripts/mini_ci_detect.py` (`<= 220` lines) so both modules stay well under 350 lines.
  - Never leak Windows host `PATH` (`shutil.which("pytest"|"ruff")`) into target `.venv` decisions or `--linux` (`PY_TOKEN`) command construction.
  - Note on `.gitignore`: `skills/.gitignore` ignores `/*/` (including `.diagnostics/`), so `skills_monorepo` must default `pyyaml` automatically in code rather than relying on a tracked `.diagnostics/mini_ci.json`.
  - Cross-platform `pathlib.Path` + POSIX relative paths, UTF-8 LF normalized, isolated `CLEAN_HOME` / `HOME=/tmp/mini_ci_home` in `--linux`.

---

## Milestone 1: Agnostic Tool/Stack Detection, Nested Requirements & Linux Parity *(Active)*
- [ ] **`system-diagnostics/scripts/mini_ci_detect.py`**: Extract pure detection & manifest helpers (`<= 220` lines):
  - [ ] Resolve `pytest` / `ruff` inside the target `.venv` (`_venv_has_tool(python_bin, tool)`) and detect `pyproject.toml` (`[tool.pytest.ini_options]`, `[tool.ruff]`) in addition to `pytest.ini` / `conftest.py`.
  - [ ] Exclude `*-workspace` directories in `discover_skill_test_dirs()` and default `pip_packages` to `["pyyaml"]` for `skills_monorepo` when not overridden.
  - [ ] Auto-detect Django (`manage.py` -> `{python} manage.py check`) and non-Python stacks (`package.json`, `go.mod`, `Cargo.toml`, `pubspec.yaml`) when no Python test layout applies.
  - [ ] Recursively resolve `requirements_files` + `-r <subfile>` includes (e.g., `requirements/base.txt`, `requirements/local.txt`, `requirements/production.txt`) and optional `editable_install: true` (`pip install --no-build-isolation --no-deps -e .`).
- [ ] **`system-diagnostics/scripts/mini_ci.py`**: Wire `mini_ci_detect.py` helpers, fix `--linux` host `PATH` leak (`PY_TOKEN` path checks target manifests instead of host `which`), stage recursive requirements files into Docker build context + content-addressed tag hash, and propagate `--simulate-ci-chrome` env vars into `build_wsl_script()` and `build_docker_run_command()`.
- [ ] **`system-diagnostics/tests/test_mini_ci_detect.py`** & **`system-diagnostics/tests/test_mini_ci.py`**: Add unit tests for target `.venv` `pytest`/`ruff` resolution (host `PATH` isolated), `pyproject.toml`, Django `manage.py check`, non-Python stack presets, `*-workspace` exclusion, recursive `-r` requirements + Docker context staging, and `--linux --simulate-ci-chrome`.
- [ ] **Verification**:
  - [ ] `python -m unittest discover -s system-diagnostics/tests -p "test_mini_ci*.py" -v`
  - [ ] `python system-diagnostics/scripts/diagnose.py audit --path system-diagnostics/scripts/mini_ci.py system-diagnostics/scripts/mini_ci_detect.py`
  - [ ] `python system-diagnostics/scripts/diagnose.py ci --path . --fast --dry-run`

## Milestone 2: `diagnose.py ci --init` Workflow Scaffolder, Docs & Multi-Repo Verification *(Deferred to Next Turn / Milestone 2)*
- [ ] **`system-diagnostics/scripts/mini_ci_detect.py`** & **`system-diagnostics/scripts/mini_ci.py`**: Add `--init` flag to `diagnose.py ci` to inspect `.github/workflows/*.yml` and repo markers and write `.diagnostics/mini_ci.json` (refusing to overwrite without `--force`).
- [ ] **`system-diagnostics/SKILL.md`** & **`frontier-architect/references/cli-cheatsheet.md`**: Document `--init`, `requirements_files`, `editable_install`, `--root`, and multi-stack auto-detection + Scenario Combinations Matrix.
- [ ] **Multi-Repo Parity Verification**: Verify `diagnose.py ci --fast --dry-run` and `--linux --dry-run` across `skills`, `intelligent_tracker`, and `enterprise_website`, plus run full `system-diagnostics`, `frontier-architect`, `refactor-monolith`, and `app-debugger` regression suites.

---

## Scenario Combinations Matrix

| Scenario | Command | Expected Result |
|---|---|---|
| Repo with `pytest.ini` + `.venv` `pytest` (not on host `PATH`) | `diagnose.py ci --path <repo> --fast --dry-run` | Selects `.venv` `python -m pytest` (never `unittest` fallback) |
| Django repo (`manage.py` + `pytest.ini`) | `diagnose.py ci --path <repo> --fast --dry-run` | Includes `{python} manage.py check` + `{python} -m pytest` |
| Nested `-r requirements/base.txt` in Docker | `diagnose.py ci --path <repo> --linux --backend docker --dry-run` | Stages all referenced requirements files & hashes all into image tag |
| Skills monorepo in Docker | `diagnose.py ci --path . --linux --backend docker --dry-run` | Skips `*-workspace` dirs and includes `pyyaml` install |
| Linux Chrome simulation | `diagnose.py ci --path <repo> --linux --simulate-ci-chrome --dry-run` | Exports `CI_SIMULATE_CHROME=1`, `CHROME_NO_SANDBOX=1`, `HEADLESS=1` |
| Scaffold project config | `diagnose.py ci --path <repo> --init` | Generates `.diagnostics/mini_ci.json` from workflow/repo markers |
