# Plan Contracts, Modularity & Sign-Off Details

Consult this reference when **authoring a new plan (Phase 5)** or **closing a plan / Master Step (Phase 6.7)**.

---

## 1. Dual-Write, Master Roadmap & Runtime Wiring (Phase 5)

- **Dual-Write Registration**: Write identical content to (1) `<appDataDir>/brain/<conversation-id>/<slug>.md` (`ArtifactMetadata`, `RequestFeedback: true`) and (2) `<workspace>/.TODO/<slug>.md` (or `.plans/<slug>.md`, no `ArtifactMetadata`), then run `python "<skill_dir>/scripts/plan_engine.py" init .TODO/<slug>.md`.
- **Master Plans of Plans Threshold**: Create a Master Roadmap (`<slug>_master_roadmap.md`) + Step 1 child plan (`--parent <master_slug> --milestone 1`) whenever a roadmap has `>= 4` milestones, spans `>= 3` subsystems/directories with `>= 10` tasks, or requires cross-layer refactoring (`plan_engine.py init` emits `SCOPE RECOMMENDATION (MASTER PLAN)`). Distill subagent findings into `docs/architecture/`. Consolidate child plans into **2–3 cohesive milestones** (`~40–70 steps` each) instead of fracturing 1–2 file edits across 4+ tiny conversations.
- **Runtime Wiring & Frozen-Monolith Signal Adapters**: Pair every new coordinator, mapper, or service with explicit live runtime constructor/pool/lifecycle wiring (`PipelineEngine`, `CameraPool`, app startup) in the same step. When freezing an oversized `WARN`/`HARD` file (e.g., `gallery.py`), schedule a small extracted signal/helper adapter so upstream producers populate downstream attributes instead of leaving duck-typed `getattr(..., 0.0)` stubs.
- **Vertical Slice Parity**: Pair every milestone's implementation edits with a targeted unit test.
- **Changelog Task Formulation Invariant**: Never target raw log files (`MIGRATION_LOG.md`). Always use:
  `- [ ] **CHANGELOG.md**: Record milestone completion via 'python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" changelog add'`
- **Persistent Memory (`AGENTS.md` / `.agents/rules/`)**: Merge ownership, modularity budgets, and test commands into `AGENTS.md` rather than overwriting existing project rules (project rules win on conflict).

---

## 2. Modularity Budgets, Portability & SSOT (Phase 5)

- **Audit First**: Run `python "<config_dir>/skills/system-diagnostics/scripts/diagnose.py" audit --path <targets>` before planning edits.
- **Budgets**: File soft warning `350L`, hard ceiling `500L`; class `<= 10–12` methods (`200–300L`); function `<= 40L`; route handler `<= 15–25L`. Never append into files `>= 350L`—split into `routers/`, `services/`, `repositories/`, `components/`.
- **Plan Budget Calibration**: If `AGENTS.md` or a master plan enforces a tighter ceiling (e.g., `< 300L`), pass `diagnose.py audit --max-lines <N>` rather than inventing unreachable `< 250L` budgets.
- **Export-Ready Portable Plan Contract**:
  - Use POSIX repo-relative paths (`src/module/component.js#L94-L105`); never embed machine-local paths or `file:///` URIs.
  - Use OS-agnostic test commands (`python -m unittest discover tests`, `pytest tests/`, `$APP_URL`) and an executable **Scenario Combinations Matrix**.
- **SSOT & Filesystem Verification**:
  - Zero dead re-export facades/shims; repoint callers to the authoritative SSOT and delete or 1-line delegate legacy helpers.
  - Verify file vs. package-directory paths (`os.path.isfile` / `Test-Path`) and root doc filenames (`README.md` vs. `README.rst`, `pyproject.toml` `readme` field) before writing plan targets.
  - Implement and verify every CLI subcommand/tool promised in the plan or amend the plan before sign-off.

---

## 3. Retrospective Rubric, Tier-1 Nuances & Final Sign-Off (Phase 6)

- **4-Dimensional Retrospective (`plan_engine.py retrospective`)**:
  - Positional `--tri "5,5,5,5"` maps to: *Token Efficiency (1–5)*, *Hypothesis Accuracy (1–5)* (`<= 2` attempts), *Tool Reliability Index (1–5)*, *Architectural Defense (1–5)*.
  - Grading rubric (auto-capped by `plan_engine.py`): `A` (`0–1` retries, `<= 60` steps), `B` (`2–3` retries or `61–100` steps), `C` (`>3` retries or `>100` steps), `D/F` (thrash or unverified).
  - Pass `--cid <current_cid>` once to auto-populate `--steps`/`--retries`. Echo the printed `--- Turn-End Echo ---` block directly without re-reading `SKILL.md`. Default to running `/learn` once at Child Plan completion via `LEARNING_SCAFFOLD.md` (mid-plan only if a rule prevents an immediate repeat failure).
  - For follow-up `/app-debugger` sessions after a milestone, running `diagnose.py debug-retro --plan <slug> --cid <cid>` automatically records `followup_cids` and refreshes `LEARNING_SCAFFOLD.md` with `--backfill` (no manual `digest` re-run needed unless merging external CIDs via `plan_engine.py digest <slug> --cids <all_cids> --backfill --write-scaffold`). Run `diagnose.py scan` *before* `retrospective`/`digest` and `diagnose.py transcript-audit --latest 1` *last*.
- **Tier-1 Audit, Concurrency & Build Nuances**:
  - Route targeted Python `unittest` runs through `diagnose.py tests <modules...>` (enforces the 180s `--timeout` guard) before full discovery, and promote milestone CDP E2E probes into permanent Chrome-gated `tests/test_*_e2e*.py` tests (ephemeral `port=0`, isolated temp dir) rather than leaving them in `scratch/`.
  - Enforce **Second-Check Verification Gate**: verify interruptibility with `threading.Timer`, grep upstream call-sites for shadowing defaults, verify single clock-domain parity (`time.monotonic()` vs `time.time()`) without hiding behind synthetic `now=` stubs, and ensure waits/joins occur strictly outside lock blocks.
  - Preserve `try/except ImportError` availability probes when pruning `arch-map` unused imports.
  - Keep Sphinx `.. automodule::` directives in one canonical `.rst` file for `-W` builds.
  - Use `subprocess.run([sys.executable, ...])` or AST parsing for `sys.modules` / import-boundary tests.
- **Post-Step Integration & Final Sign-Off Checklist**:
  1. Before ticking a Master Step `[x]`, run `diagnose.py scan --path .` (including `tests/`), exercise unconfigured/empty/fallback branches (`api_key=""`, `None` deps, missing config) without hiding them behind mocks, and run `plan_engine.py digest <slug> [--cids <ids>] --backfill --write-scaffold`.
  2. Before dismissing a failing test as "pre-existing", run `git log -n 3 -- <failing_file>` to confirm it wasn't pushed over budget by an earlier milestone; never tick a Master Step `[x]` while a `test_step*_budgets.py` test fails on a touched file.
  3. On 100% completion: run the full regression suite (verifying cross-step URL/contract parity in earlier `test_step1_*` tests and event isolation like `get_shutdown_event()`), verify zero `file:///` links/secrets and 350/500L compliance, run `diagnose.py changelog add`, provide `git diff main...plan/<slug>`, summarize `LEARNING_SCAFFOLD.md` + Introspective Options, and advise **New Conversation (+)** or `/compact` (or `/frontier-architect continue <parent_slug>`).
  4. When `/learn` runs on `LEARNING_SCAFFOLD.md`, process both `Unresolved /learn candidates` and `Skill & Tooling /learn candidates`, emitting `learning_proposal.md` (`RequestFeedback: true`) before editing any rule or skill.
