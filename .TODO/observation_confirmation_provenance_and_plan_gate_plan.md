# Observation Confirmation State, Resolution Provenance & Plan-Engine Closure Gate

> **Scope**: `system-diagnostics` (`scripts/observation_store.py`, `scripts/observation_fields.py`, `scripts/observation_cli.py`, `scripts/observation_routes.py`, `scripts/observation_merge.py`, `assets/hud_drawer.js`, `assets/hud_drawer_render.js`, `references/observations.md`) and `frontier-architect` (`scripts/plan_cli_helpers.py`, `tests/`).
> **Modularity Budget**: `system-diagnostics/scripts/observation_store.py` is currently `339L` (near the `350L` soft ceiling); place new provenance normalization/helpers in `system-diagnostics/scripts/observation_fields.py` (`233L`) so `observation_store.py` stays `< 350L`.

---

## Milestone 1: Observation `confirmed` State & Resolution Provenance CLI/Store *(Active)*

- [ ] **system-diagnostics/scripts/observation_fields.py** & **system-diagnostics/scripts/observation_store.py**: Add `"confirmed"` to `CLOSED_STATUSES` and `TRANSITIONS` (`resolved -> confirmed | open`, `confirmed -> open`), add provenance metadata fields (`resolved_plan`, `resolved_milestone`, `resolved_task`, `base_commit`, `confirmed_at`, `confirmed_note`) to `_META_FIELDS` / import-export helpers, keeping `observation_store.py < 350L`.
- [ ] **system-diagnostics/scripts/observation_cli.py**: Extend `observations resolve` with optional `--plan`, `--milestone`, `--task`, `--base-commit` (auto-populating `base_commit` from `git rev-parse --short HEAD` as `pending:<sha>` when `--commit` is omitted), and add `observations confirm --id <OBS-NNN> [--note "..."]` subcommand.
- [ ] **system-diagnostics/scripts/observation_routes.py** & **system-diagnostics/scripts/observation_merge.py**: Accept `confirmed` status transitions and provenance fields in Wire Contract v1 PATCH/POST routes and merge logic.
- [ ] **system-diagnostics/tests/test_observation_store.py** & **system-diagnostics/tests/test_observation_cli.py**: Add unit tests for `resolved -> confirmed -> open` transitions, provenance metadata persistence, auto `base_commit` fallback, and `confirm` CLI round-trip.
- [ ] **Verifier**: `python -m unittest discover -s system-diagnostics/tests -p "test_observation*.py"`

---

## Milestone 2: HUD Confirmation UX, Provenance Display & `plan_engine.py advance` Warning Gate *(Deferred to Next Turn / Milestone 2)*

- [ ] **system-diagnostics/assets/hud_drawer.js** & **system-diagnostics/assets/hud_drawer_render.js**: Add `confirmed` to status filter options, render AI resolution note + provenance badges (`plan`, `milestone`, `commit`/`base_commit`) on `resolved`/`confirmed` cards, and add one-click `Confirm` / `Reopen` buttons on `resolved` cards.
- [ ] **frontier-architect/scripts/plan_cli_helpers.py**: On `plan_engine.py advance`, scan the completed milestone/plan markdown for `OBS-\d+` IDs and, if `.diagnostics/observation_catalog.json` exists with any still in `ACTIVE_STATUSES`, emit an `OBSERVATION WARNING` banner listing the unresolved IDs and the exact `diagnose.py observations resolve` command.
- [ ] **system-diagnostics/references/observations.md** & **frontier-architect/references/cli-cheatsheet.md**: Document `observations confirm`, `--plan`/`--milestone`/`--base-commit`, and the `advance` warning gate.
- [ ] **system-diagnostics/tests/test_observation_hud.py** & **frontier-architect/tests/test_plan_engine_fixes.py**: Add HUD confirmation/provenance rendering tests and `plan_engine.py advance` unresolved-observation warning tests.
- [ ] **Verifier**: `python -m unittest discover -s system-diagnostics/tests -p "test_observation*.py"` and `python -m unittest discover -s frontier-architect/tests -p "test_*.py"`

---

## Scenario Combinations Matrix

| Scenario | Trigger / Inputs | Expected Behavior | Milestone / Verifier |
| :--- | :--- | :--- | :--- |
| **AI resolves before user commits** | `diagnose.py observations resolve --id OBS-031 --resolution "..." --plan step_2 --milestone 1` (no `--commit`) | Status -> `resolved`; stores `resolved_plan=step_2`, `resolved_milestone="1"`, and `base_commit=pending:<HEAD_short_sha>` | M1 (`test_observation_cli.py`) |
| **User verifies fix in HUD & confirms** | User clicks `Confirm` on a `resolved` card (or runs `observations confirm --id OBS-031 --note "..."`) | Status transitions `resolved -> confirmed`; records `confirmed_at` & optional `confirmed_note`; provenance badges remain visible | M1–M2 (`test_observation_store.py`, `test_observation_hud.py`) |
| **User finds regression after resolve/confirm** | User clicks `Reopen` on a `resolved` or `confirmed` card | Status transitions back to `open` with history entry preserving prior resolution provenance | M1–M2 (`test_observation_store.py`, `test_observation_hud.py`) |
| **`advance` on milestone with active `OBS-NNN`** | `plan_engine.py advance <slug> --milestone <N>` when milestone cites `OBS-031` still in `ACTIVE_STATUSES` (or workspace has no catalog) | Prints `OBSERVATION WARNING` listing active `OBS-031` + exact `observations resolve` command; non-observation workspaces advance silently without error | M2 (`test_plan_engine_fixes.py`) |
