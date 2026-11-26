# Master Roadmap: Universal Debug Observation Connector, DevTools HUD & Triage CLI

> **Status: NOT IMPLEMENTED.** Rewritten 2026-11-26 after an audit against branch `feature/add-debug-connectors` @ `7817b06`. This file is the single source of truth for intent and contracts. Execute **one milestone per session** with `/frontier-architect continue universal_debug_observation_connector_plan`; only Milestone 1 has a child plan.
> Read `ARCHITECTURE.md` (repo root) first for the current layout. Do not re-read this whole file each session: use `plan_engine.py status|next`, then open only the contract sections the active milestone cites.

Standardizes interactive browser observation capture, DevTools-style element picking with scoped session recording, and token-efficient agent triage across web projects (`intelligent_tracker`, `enterprise_website`, future apps), implemented once inside `system-diagnostics` (SSOT).

## Intent Ledger (do not drop any of these)

| ID | Intent | Where it lands |
| :--- | :--- | :--- |
| I1 | One standard way to capture what a human sees while debugging a web app, reusable across projects | Milestones 1-3 |
| I2 | DevTools-style **Pick Element** and scoped **Record / Stop** session with a soft **Pause** while inspecting | Milestone 2 |
| I3 | Agents triage cheaply: default `list` shows only unresolved items so `/frontier-architect`, `/app-debugger` and audit runs never re-read solved observations. (The original draft also named "FOR AUDITS"; that term is not defined anywhere in this repo. Treat it as "audit-style runs" and confirm with the user if it means something else.) | Milestone 1, 4 |
| I4 | Observations are linked to server-side runtime traces | Milestones 1, 3 |
| I5 | Connector scaffolder gives a project the whole thing in about 3 lines of setup (`fastapi`, `flask`, `generic`) | Milestone 3 |
| I6 | Skills tell agents to read open observations automatically and mark them resolved after a **verified** fix | Milestone 4 |
| I7 | Every new file <= 350 lines (target 150-250), every function <= 40 lines | all milestones |
| I8 | **One codebase for Gemini/Antigravity (Windows) and Claude Code (macOS/Linux)**: no `.gemini`-only paths, no `python skills/...` assumptions, tests that pass on both | all milestones |
| I9 | Debug data never leaks: off by default, local only, redacted, size-capped | Milestones 2, 3 |

## Decisions (defaults chosen by the audit; change here before Milestone 1 if you disagree)

| ID | Decision | Reason |
| :--- | :--- | :--- |
| D1 | Statuses: `open`, `triaged`, `in_progress`, `resolved`, `dismissed`. **ACTIVE** = open, triaged, in_progress. **CLOSED** = resolved, dismissed. The old draft's `wontfix` is dropped. | Reuses the defect catalog's `CLOSED_STATUSES = {resolved, dismissed}` and the `dismiss` verb; avoids a third vocabulary |
| D2 | IDs are dual-key: sequential `OBS-001` and fingerprint `OBS-<KIND>-<6HEX>` | Mirrors `DEFECT-001`/`DEF-<RULE>-<6HEX>` and `TRC-<TYPE>-<6HEX>` |
| D3 | Correlation key is an exact **`recording_id`** (sent as header `X-Debug-Recording-Id`), with a timestamp window of +/-2 s as fallback only | Browser and server clocks skew; a window alone mismatches |
| D4 | Observations correlate with **exception traces** (what `trace_recorder` stores today), not with every request | Request logging does not exist; out of scope |
| D5 | Server routes exist only when env `FRONTIER_DEBUG_OBSERVATIONS=1`; they accept loopback clients only; the HUD does nothing unless `window.__FRONTIER_DEBUG__ === true` | Safe by default |
| D6 | Commands in docs use `python "<skill_dir>/scripts/diagnose.py" ...` where `<skill_dir>` is the `system-diagnostics` folder | Works from `.claude/skills/`, `~/.claude/skills/` and the monorepo |

## Preconditions

- **P0:** the cross-platform test fixes are merged: `system-diagnostics` 264, `refactor-monolith` 159, `app-debugger` 24, `frontier-architect` 140 all pass (they compared unresolved temp paths on macOS). Verify with the commands under Verifiers before starting; if any suite is red, stop and fix that first.
- **P1:** `.diagnostics/` is gitignored by `defect_catalog.ensure_diagnostics_dir` (writes `.diagnostics/.gitignore` containing `*`). Reuse it; do not create another ignore mechanism.

## Architectural Pre-Flight

**Existing pieces to reuse (verified in the audit):**
- `trace_recorder.py` (282 L): `TraceCatalogManager` persists `.diagnostics/trace_catalog.json` (atomic tmp + `os.replace`) and daily `.diagnostics/traces/trace_YYYYMMDD.jsonl`; events carry `timestamp` (UTC ISO) and a `context` dict; fingerprint = `TRC-<TYPE8>-<sha256[:6]>`.
- `trace_middleware.py` (63 L): ASGI and WSGI middleware that already put `http_method`, `http_path`, `client_host` into `context`.
- `trace_cli.py` (93 L): the delegating-CLI pattern (`register_parser`, handler) used by `diagnose.py traces`.
- `connector_scaffolder.py` (150 L): writes `diagnostic_bridge.py`; the three framework templates are embedded in this file.
- `defect_catalog.py` (346 L, at the soft budget: **do not add code to it**): `ensure_diagnostics_dir`, lifecycle and dual-key patterns to mirror.
- `skill_packager.py` copies every folder except `tests`, `evals`, `__pycache__`, `node_modules`, so a new `assets/` folder ships in packaged skills.

**Wiring pattern for a new subcommand** (`diagnose.py`, 309 L): add `import observation_cli` beside the other imports (about line 35), add `observation_cli` to the module tuple in `build_parser` (about line 269), add `"observations": observation_cli.cmd_observations` to the `dispatch` dict (about line 295). Three one-line edits; all logic lives in the new module. Re-check the line numbers when implementing.

**Failure modes to handle:** corrupt or truncated `observations.jsonl` line (skip, count, never crash); two writers appending at once (single `open("a")` write per record, atomic catalog save); missing `.diagnostics/traces/`; HUD disabled; endpoint called from a non-loopback host; oversized payload; framework not installed in the target project (generated bridge must import cleanly and degrade to no-ops).

## Data Contracts

**Raw record** (one JSON object per line in `.diagnostics/observations.jsonl`, UTF-8, `\n` newlines):
```json
{"schema": 1, "ts": "2026-11-26T14:03:11.120Z", "kind": "element|error|network|note",
 "page_path": "/dashboard", "selector": "main > button#save", "rect": {"x":0,"y":0,"w":0,"h":0},
 "attrs": {"tag":"button","id":"save","class":"btn primary","data-testid":"save","role":"button","aria-label":"Save"},
 "message": "Save does nothing", "recording_id": "rec-8f3a2c", "window": {"started_at": "...", "stopped_at": "..."},
 "timeline": [{"t": 0, "type": "click|input|nav|fetch|console|error", "target": "...", "status": 200, "ms": 41}]}
```
Limits enforced on write: record <= 64 KB; `message` <= 500 chars; `timeline` <= 50 events (oldest dropped); file rotated at 5 MB to `observations.1.jsonl` (one backup kept).

**Fingerprint:** `sha256("{kind}|{page_path}|{selector or url_path}|{normalized_message}")[:6]`, formatted `OBS-<KIND upper, max 7>-<6HEX>`. Normalization = lowercase, collapse whitespace, strip digits runs longer than 4 and hex pointers (same idea as `trace_recorder._sanitize_message`). Same fingerprint increments `occurrence_count` and refreshes `last_seen`; it never creates a second entry.

**Catalog** (`.diagnostics/observation_catalog.json`, atomic save): `{"schema_version":"1.0","workspace":"<posix path>","updated_at":"...","summary":{"total":0,"open":0,"triaged":0,"in_progress":0,"resolved":0,"dismissed":0},"observations":[ ... ]}` where each entry has `id`, `fingerprint`, `kind`, `status`, `first_seen`, `last_seen`, `occurrence_count`, `page_path`, `selector`, `rect`, `attrs`, `message`, `recording_id`, `window`, `timeline`, `correlated_traces` (list of `TRC-...` fingerprints), `root_cause`, `resolution`, `linked_plan`, `linked_commit`, `history` (list of `{ts, from, to, note}`).

**Allowed transitions:** open -> triaged | in_progress | resolved | dismissed; triaged -> in_progress | resolved | dismissed; in_progress -> resolved | dismissed | triaged; resolved -> open (re-occurrence of the same fingerprint reopens it and appends a history note); dismissed stays dismissed unless explicitly reopened.

## CLI Contract (`diagnose.py observations`)

All actions accept `--path DIR` (workspace root, default cwd) and `--json`. Exit codes: `0` success (including "nothing to show"), `1` id not found, `2` usage error (missing required flag).

| Action | Flags | Behavior |
| :--- | :--- | :--- |
| `list` | `--status active\|all\|open\|triaged\|in_progress\|resolved\|dismissed` (default `active`), `--limit N` (default 20) | One compact line per item: `OBS-003 [open] element /dashboard button#save "Save does nothing" (2x, 2026-11-26)`. Empty: `No active observations.` JSON mode returns only `id,status,kind,page_path,selector,message,occurrence_count,last_seen`. |
| `show` | `--id OBS-001\|fingerprint`, `--full` | Full entry; timeline and correlated traces; `--full` includes all history. |
| `add` | `--kind`, `--page`, `--selector`, `--message`, `--recording-id` | Manual or test capture (also what an agent uses when the user describes a problem in chat). Goes through the same dedup and caps as HUD posts. |
| `triage` | `--id`, `--root-cause` (required), `--plan SLUG`, `--status triaged\|in_progress` | Records root cause and plan link. |
| `resolve` | `--id`, `--resolution` (required), `--commit SHA` | Marks `resolved`; hidden from default `list`. |
| `dismiss` | `--id`, `--reason` (required) | Marks `dismissed`. |

## HUD Contract (Milestone 2)

- Delivered as three plain scripts in `system-diagnostics/assets/` (`hud_core.js`, `hud_picker.js`, `hud_recorder.js`, each <= 300 lines) concatenated in that fixed order by `observation_assets.hud_bundle()`. No dependencies, no build step.
- **Gate:** if `window.__FRONTIER_DEBUG__ !== true` the bundle returns immediately and touches nothing (no listeners, no DOM, no timers).
- **Pick Element:** capture-phase hover highlight; click records a unique CSS selector (prefer `#id`, then `[data-testid]`, then a short tag/class path verified with `querySelectorAll(sel).length === 1`), `getBoundingClientRect()`, and the allowlisted attributes only.
- **Record / Stop:** creates `recording_id` (`rec-<6hex>`), `started_at`, `stopped_at`; while recording, wraps `fetch` and XHR so each request carries header `X-Debug-Recording-Id`, and logs click, navigation, fetch status + latency, `console.error`, `window.onerror` into the timeline.
- **Soft Pause:** pauses `<video>`/`<audio>` and `requestAnimationFrame` loops, and suppresses page click propagation while Pick is active; fully restored on exit.
- **Log Observation:** posts the record to `/api/diagnostics/observation` (configurable via `window.__FRONTIER_OBS_ENDPOINT__`).
- **Redaction (hard rules):** never read `input.value`, `textarea` content or `contenteditable` text: record only tag, `type`, `name` and value length; skip `type=password` entirely; record fetch URL **path** plus query **keys** (never values); never record request or response bodies or `Authorization`/`Cookie` headers.

## Correlation Contract (Milestone 3 completes it; Milestone 1 builds the reader)

1. **Stamp:** `trace_middleware.py` reads header `x-debug-recording-id` (ASGI: from `scope["headers"]`, lowercase byte keys; WSGI: `environ["HTTP_X_DEBUG_RECORDING_ID"]`) and adds `recording_id` to the trace event `context`.
2. **Match:** `observation_correlate.correlate(obs, traces_dir)` scans `trace_YYYYMMDD.jsonl` files for dates inside the window and returns trace fingerprints whose `context.recording_id == obs.recording_id` (exact). If the observation has no `recording_id`, fall back to events with `timestamp` inside `[started_at - 2 s, stopped_at + 2 s]`.
3. **Store:** matched fingerprints go in `correlated_traces`; `show` prints each with its exception type and culprit.

## Security & Privacy Contract

- Server routes are generated only when `FRONTIER_DEBUG_OBSERVATIONS=1`; otherwise the bridge exposes no observation route and serves no HUD.
- Handlers reject any client that is not `127.0.0.1` or `::1` with HTTP 403.
- The write path enforces the size and rotation limits above and the redaction rules (server-side re-check: drop any field named `value`, `password`, `authorization`, `cookie`).
- Data lives only in `.diagnostics/` (gitignored). The docs must say so.

## Runtime Parity Contract (Gemini/Antigravity and Claude Code)

- Python 3.10+ standard library only; `pathlib`, forward slashes in stored paths, `encoding="utf-8"`, `\n` newlines.
- **Tests must resolve temp dirs**: `Path(tempfile.mkdtemp()).resolve()` (macOS `/var` is a symlink to `/private/var`; this exact mistake broke seven tests before this plan). Compare paths with `.resolve()` on both sides.
- Tests that need `node` or Chrome **skip** when absent (`shutil.which`), never fail.
- Generated bridges must find the engine on both runtimes: candidates in order `SYSTEM_DIAGNOSTICS_DIR`, `<project>/.claude/skills/system-diagnostics`, `~/.claude/skills/system-diagnostics`, sibling `../system-diagnostics`, `<project>/skills/system-diagnostics`, `~/.gemini/config/skills/system-diagnostics` (the old templates only had the last two plus a `parents[2]` guess, so under Claude the bridge silently did nothing).
- No new `ask_question`, `run_command`, `RequestFeedback`, `<appDataDir>` or `python skills/...` strings in any file. If prose needs a tool name, write both (`ask_question` / `AskUserQuestion`) like the existing adapter-gated docs.

## Scenario Combinations Matrix

| Scenario | Command or trigger | Expected result |
| :--- | :--- | :--- |
| Agent lists work (default) | `python "<skill_dir>/scripts/diagnose.py" observations list` | Only open, triaged and in_progress items, compact lines; exit 0 |
| Nothing open | same | `No active observations.`; exit 0 |
| Include history | `... observations list --status all` | Resolved and dismissed appear too |
| Triage and link to plan | `... observations triage --id OBS-001 --root-cause "..." --plan <slug>` | Status `triaged`, plan linked, history entry |
| Resolve after verified fix | `... observations resolve --id OBS-001 --resolution "..." --commit <sha>` | `resolved`; absent from default `list` |
| Unknown id | `... observations show --id OBS-999` | message on stderr; exit 1 |
| Missing required flag | `... observations resolve --id OBS-001` | usage error; exit 2 |
| Same problem seen twice | HUD posts identical element + message | One entry, `occurrence_count` 2 |
| Resolved problem recurs | same fingerprint after `resolve` | Reopened to `open`, history note |
| Corrupt jsonl line | one bad line among good ones | bad line skipped and counted; nothing crashes |
| Scaffold with observations | `... traces --scaffold fastapi --dest services --with-observations` | `diagnostic_bridge.py` with trace middleware, gated observation routes and HUD route |
| Scaffold without flag | `... traces --scaffold fastapi --dest services` | Output identical to today (regression guard) |
| Routes disabled | env `FRONTIER_DEBUG_OBSERVATIONS` unset | no observation route, no HUD |
| Non-loopback caller | POST from another host | 403 |
| HUD disabled | `window.__FRONTIER_DEBUG__` not true | no listeners, no DOM changes |
| Exact correlation | HUD records, app throws during recording | trace has `recording_id`; `show` lists its `TRC-...` |
| Window fallback | observation without `recording_id` | traces inside +/-2 s are listed |
| Claude install layout | skills copied to `.claude/skills/` | `observations` and the generated bridge both work from another cwd |

## SPIKE Spec (required before Milestone 2 tasks; run at the start of Milestone 2)

1. **Riskiest assumption (SRA):** the HUD can pick elements and record in realistic pages, including a same-origin iframe, open shadow DOM, a strict `script-src 'self'` CSP, and a page with `<video>`.
2. **Metric:** for 6 fixture pages (`plain`, `spa`, `iframe`, `shadow`, `csp`, `media`), count pages where (a) the picked selector satisfies `document.querySelector(sel) === pickedElement` and (b) Record produces a non-empty timeline with `recording_id` on fetch headers.
3. **Pass / fail:** pass = at least 5 of 6; fail = 3 or fewer; 4 = inconclusive (add one more fixture, rerun once).
4. **Fixture and timebox:** hand-written HTML under `tests/fixtures/hud/`, run with `cdp_inspect.py --headless` (skip with a clear note if no Chrome); one day.
5. **Decision rule:** pass -> build Milestone 2 as specified; fail -> ship without iframe and shadow DOM support, document the limits, and serve the HUD as an external script file with CSP nonce guidance.
6. **Lives in:** `.frontier/scratch/obs-hud/` (Claude Code; Antigravity: its scratch folder). Only the 6 fixtures and the measured result table are kept; the spike code is discarded.

## Milestones (execution order, strictly sequential)

Each milestone ends with: Pre-Flight Critic Gate -> sliced edits -> `diagnose.py audit --path <touched files>` (zero audit evasion) -> `plan_engine.py verify` -> **Review Gate** -> `advance`. The **Review Gate**: a fresh reviewer (not the author; Claude: Opus, Antigravity: the planner tier) receives the diff plus verify output (not the author's conclusion) and must confirm each exit criterion; a failed gate counts as one attempt toward Anti-Thrash Stop-Loss (two attempts, then revert and escalate).

## Milestone 1: Observation Store, Correlation Reader & Triage CLI (`diagnose.py observations`)

**Child Plan**: .TODO/step_1_observation_store_cli.md

- [ ] **child plan .TODO/step_1_observation_store_cli.md**: execute the child plan (7 files: `observation_store.py`, `observation_correlate.py`, `observation_cli.py`, three test modules, three one-line edits in `diagnose.py`).

**Verifier**: `python -m unittest discover -s system-diagnostics/tests -p "test_observation_*.py"` then the four suite commands in the Definition of Done.
**Exit criteria:** all CLI contract rows pass in tests; default `list` hides CLOSED items; dedup, reopen and corrupt-line cases covered; `diagnose.py` grew by 3 lines only and stays under 350 lines; every new file <= 350 lines.

## Milestone 2: DevTools Observation HUD *(Deferred to Next Turn / Milestone)*

- [ ] **child plan .TODO/step_2_*.md**: created just in time at the Master Step Pre-Plan Gate (~7 files): SPIKE fixtures (`system-diagnostics/tests/fixtures/hud/*.html`), `system-diagnostics/assets/hud_core.js`, `hud_picker.js`, `hud_recorder.js`, `system-diagnostics/scripts/observation_assets.py` (bundle order and gate), `tests/test_observation_hud.py` (Node VM logic tests with a tiny fake DOM; skip without `node`), `tests/test_observation_hud_e2e.py` (Chrome-gated via `cdp_inspect`; skip without Chrome).

**Verifier**: `python -m unittest discover -s system-diagnostics/tests -p "test_observation_hud*.py"`
**Exit criteria:** SPIKE result recorded in the child plan (pass or documented fallback); HUD contract rows each have a test; HUD is a strict no-op when disabled; each JS file <= 300 lines.

## Milestone 3: Correlation Stamping & Connector Scaffolder (`--with-observations`) *(Deferred to Next Turn / Milestone)*

- [ ] **child plan .TODO/step_3_*.md**: created just in time (~8 files): `trace_middleware.py` (stamp `recording_id`), `connector_bridge_common.py` (engine path bootstrap with the Parity Contract candidate list; replaces the three copies in the templates), `connector_templates_obs.py` (observation routes for fastapi, flask, generic; **new module, because `connector_scaffolder.py` would exceed budget**), `connector_scaffolder.py` (wire the flag; use the shared bootstrap), `trace_cli.py` (`--with-observations`, valid only with `--scaffold`), `tests/test_connector_scaffolder.py` (**new; the scaffolder has no direct test today**), `tests/test_trace_recorder.py` (recording_id cases), `tests/test_observation_bridge_routes.py` (import generated bridges; call handlers with fake requests).

**Verifier**: `python -m unittest discover -s system-diagnostics/tests -p "test_*.py"`
**Exit criteria:** the "Scaffold without flag" row is byte-identical to the pre-change output except for the new shared path bootstrap; generated bridges import with no framework installed; gating, loopback-only, redaction and size caps tested; Claude-layout test passes (bridge found under `.claude/skills/`).

## Milestone 4: Skill Integration, Docs & Claude/Gemini Parity *(Deferred to Next Turn / Milestone)*

- [ ] **child plan .TODO/step_4_*.md**: created just in time. Expected files: `system-diagnostics/SKILL.md` (pointer only; it is already 15.5 KB, so detail goes in references), `system-diagnostics/references/observations.md` (new workflow doc), `system-diagnostics/references/cli-reference.md`, `app-debugger/SKILL.md` and its evals (read open observations in Step 0/2, resolve after verified fix), `frontier-architect/SKILL.md` + `references/phase-protocols.md` (Phase 0 auto-pickup; **SKILL.md must stay under 12,000 bytes: only about 170 bytes of headroom, so put the text in the reference and keep one short line in the router**), `ARCHITECTURE.md` and `AGENTS.md` (refresh), regression guards. If that exceeds 8 files at the gate, split into **4A** (system-diagnostics + app-debugger) and **4B** (frontier-architect + repo docs + guards).

**Verifier**: the four suite commands in the Definition of Done, plus `python -m unittest discover -s frontier-architect/tests -p "test_adapter_gating.py"`.
**Exit criteria:** docs use `<skill_dir>` commands only; adapter-gating and router-size tests still pass; evals for `system-diagnostics` and `app-debugger` include observation expectations; `ARCHITECTURE.md` section 3 and 7 updated.

## Handoff Protocol (every session)

Start: `plan_engine.py status universal_debug_observation_connector_plan` then `next`; open only the contract sections the milestone cites. End: run `advance`, echo `Suggested Commit` (never commit without consent), and stop. If a milestone exceeds about 110 steps, pause with a Ready-to-Paste Handoff Prompt listing completed edits, pending items and verify commands.

## Risks and Rollback

| Risk | Mitigation |
| :--- | :--- |
| HUD does not work in some page types | SPIKE decides scope before Milestone 2; limits documented |
| Debug data exposed | Gating, loopback-only, redaction, caps, gitignored store (Security Contract) |
| Third catalog diverges from the others | Same statuses, same dual-key IDs, same atomic-save pattern |
| Budget creep in `diagnose.py` / `connector_scaffolder.py` | New modules only; three one-line edits to `diagnose.py` |
| Gemini regression from Claude-oriented fixes | Parity Contract; no platform-specific code paths; all tests resolve paths |

Rollback per milestone: revert that milestone's commit; the store and routes are additive and off by default, so nothing else depends on them until Milestone 3 ships.

## Out of Scope

Request-level logging of every HTTP call; non-web debugging; a graphical triage UI; syncing observations off the machine; a Windows-specific installer.

## What Changed From the Previous Draft (traceability)

1. `traces scaffold --framework ... --with-observations` was not a real command; the real form is `traces --scaffold fastapi --dest services`, and the flag is added there.
2. `observations` is registered through a delegating `observation_cli.py` (like `trace_cli.py`), not by editing `diagnose.py` logic.
3. One status vocabulary shared with the defect catalog (`dismissed` replaces `wontfix`).
4. Fingerprint, ID and record schemas were missing; now defined.
5. Correlation uses an exact `recording_id` instead of a time window alone.
6. Security, privacy, size caps and default-off gating were missing; now a contract.
7. A SPIKE Spec now precedes the HUD, as the skill requires.
8. Milestone 3's templates moved to a new module because `connector_scaffolder.py` would exceed 350 lines; the bridge engine-path bug (silent no-op under Claude installs) is fixed there.
9. Milestone 3's verifier previously ran a suite with 4 known failures; Precondition P0 now requires green suites first.
10. Docs milestone added (4), with the router-size constraint for `frontier-architect`; the plan is now four milestones, hence a master roadmap with just-in-time child plans.

## Definition of Done

- [ ] All four suites pass: `python -m unittest discover -s system-diagnostics/tests -p "test_*.py"`, `... -s refactor-monolith/tests ...`, `... -s app-debugger/tests ...`, `... -s frontier-architect/tests ...`.
- [ ] `python "<skill_dir>/scripts/diagnose.py" audit --path <all new and touched files>` exits 0 (no file over 350 lines, no function over 40).
- [ ] Every Intent Ledger row (I1-I9) is traceable to a passing test or a doc section.
- [ ] No new Gemini-only or repo-relative strings (`grep -rnE "ask_question|run_command|view_file|RequestFeedback|appDataDir|python skills/"` on touched files shows only dual-vocabulary lines).
- [ ] Scaffold-without-flag regression test passes; default `list` hides closed items.
- [ ] `ARCHITECTURE.md` refreshed; Review Gate recorded for each milestone.
- [ ] Final sign-off: Non-Mocked Branch Gate (`diagnose.py scan --path .`), `digest --backfill --write-scaffold`, `diagnose.py changelog add`.
