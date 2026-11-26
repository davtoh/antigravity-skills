# Universal Debug Observation Connector, DevTools HUD & Triage CLI

Standardizes interactive browser observation capture, DevTools-style element picking + scoped session recording, and token-efficient agent triage/resolution across all web projects (`intelligent_tracker`, `enterprise_website`, and future apps) inside `system-diagnostics`.

## Architectural Pre-Flight
- **SSOT Storage**: Append-only `.diagnostics/observations.jsonl` + structured triage ledger `.diagnostics/observation_catalog.json` (mirroring `defect_catalog.json` with deterministic `OBS-001` IDs and fingerprints), correlated by `[started_at, stopped_at]` window against `.diagnostics/traces/`.
- **Token-Saving Default**: `diagnose.py observations list` returns **only `open` / `triaged`** items by default (`--all` to include `resolved`/`wontfix`) so `/frontier-architect`, `/app-debugger`, and `FOR AUDITS` never burn tokens re-reading solved observations.
- **Modularity**: Keep every new script and JS module strictly `<= 350` lines (target `150–250L`) and every function `<= 40` lines.

## Scenario Combinations Matrix

| Scenario | Command / Trigger | Expected Result |
| :--- | :--- | :--- |
| **List Open Observations (Agent Default)** | `python system-diagnostics/scripts/diagnose.py observations list` | Prints compact open/triaged `OBS-XXX` entries only; exits `0`. |
| **Triage & Link Observation to Plan** | `python system-diagnostics/scripts/diagnose.py observations triage --id OBS-001 --root-cause "..." --plan <slug>` | Updates status to `triaged` with root cause + plan link. |
| **Resolve Observation (Prevent Re-Read)** | `python system-diagnostics/scripts/diagnose.py observations resolve --id OBS-001 --resolution "..." --commit <sha>` | Marks `resolved`; excluded from default `list` runs. |
| **Scaffold Connector with Observations** | `python system-diagnostics/scripts/diagnose.py traces scaffold --framework fastapi --with-observations` | Generates thin `diagnostic_bridge.py` with trace middleware + observation endpoints + HUD asset hook. |
| **DevTools Pick Element + Record/Stop** | Browser HUD (`Pick Element`, `Record`/`Stop`, `Pause`) | Captures unique CSS selector + `DOMRect`, scoped click/fetch/error timeline, and soft-pauses media/clicks while inspecting. |

---

## Milestone 1: Standardized Observation Store, Trace Correlation & Triage CLI (`diagnose.py observations`)
- [ ] **system-diagnostics/scripts/observation_store.py**: Create SSOT observation store managing `.diagnostics/observations.jsonl` + `.diagnostics/observation_catalog.json` with `OBS-001` IDs, fingerprints, lifecycle states (`open`, `triaged`, `in_progress`, `resolved`, `wontfix`), triage metadata (`root_cause`, `resolution`, `linked_plan`, `linked_commit`), and `[started_at, stopped_at]` correlation against `.diagnostics/traces/`.
- [ ] **system-diagnostics/scripts/diagnose.py**: Register `observations` subcommand (`list [--status open|all] [--json]`, `show --id <ID>`, `triage --id <ID> --root-cause ... [--plan ...]`, `resolve --id <ID> --resolution ... [--commit ...]`, `dismiss --id <ID> --reason ...`).
- [ ] **system-diagnostics/tests/test_observation_store.py**: Add unit tests covering persistence, deduplication, trace-window correlation, `open`-only default filtering, and CLI subcommands using isolated `tempfile.TemporaryDirectory()`.

**Verifier**: `python -m unittest discover -s system-diagnostics/tests -p "test_observation_store.py"`

---

## Milestone 2: Standardized DevTools Observation HUD Asset *(Deferred to Next Turn / Milestone)*
- [ ] **system-diagnostics/assets/debug_observation_hud.js**: Build a zero-dependency embeddable DevTools HUD (`<= 300L`, split cleanly if needed) supporting: (1) **Pick Element** (capture-phase hover highlight + unique CSS selector path + `DOMRect` + key attributes), (2) **Record / Stop** scoped capture session (`recording_id`, `started_at`, `stopped_at`, clicks/inputs/nav/fetch status+latency/console/JS errors), (3) **Soft Pause** toggle (pauses HTML5 `<video>`/`requestAnimationFrame` hooks and suppresses page click propagation while inspecting), and (4) **Log Observation** form posting structured payload to `/api/diagnostics/observation` (or configurable endpoint).
- [ ] **system-diagnostics/tests/test_observation_hud.py**: Add Node VM / DOM contract tests verifying Pick Element selector generation, Record/Stop window bounding, Soft Pause suppression, and strict no-op when debug mode is disabled.

**Verifier**: `python -m unittest discover -s system-diagnostics/tests -p "test_observation_*.py"`

---

## Milestone 3: Connector Scaffolder (`--with-observations`) & Skill Integration *(Deferred to Next Turn / Milestone)*
- [ ] **system-diagnostics/scripts/connector_scaffolder.py**: Add `--with-observations` flag to `diagnose.py traces scaffold` for `fastapi`, `flask`, and `generic` templates so projects get trace middleware, observation POST/GET routes, and HUD JS serving in 3 lines of setup.
- [ ] **system-diagnostics/SKILL.md**, **app-debugger/SKILL.md**, **frontier-architect/SKILL.md**: Document `diagnose.py observations {list,triage,resolve}` and instruct agents to read open observations automatically and mark them resolved on verified fix.
- [ ] **system-diagnostics/tests/test_connector_scaffolder.py**: Verify scaffolded FastAPI/Flask/Generic connectors import cleanly and pass modularity budgets (`diagnose.py audit`).

**Verifier**: `python -m unittest discover -s system-diagnostics/tests -p "test_*.py"`
