# Master Roadmap: Universal Debug Observation Connector, HUD, Triage CLI, Pull, Brief & Audit Mode

> **Status: NOT IMPLEMENTED.** Rewritten 2026-11-26 (audit corrections) and extended the same day (wire contract, `pull`, `brief`, audit mode). This file is the single source of truth for intent and contracts. Execute **one milestone per session** with `/frontier-architect continue universal_debug_observation_connector_plan`; only Milestone 1 has a child plan (`step_1_observation_store_cli`).
> Read `ARCHITECTURE.md` (repo root) first for the current layout. Do not re-read this whole file each session: use `plan_engine.py status|next`, then open only the contract sections the active milestone cites.
> The app-side half of the contract is written for the consuming project in `.TODO/debug_observation_connector_adoption_plan.md` (shareable; see Related External Context).

Goal in one sentence: a user debugs a web app with a DevTools-style HUD, logs findings and ideas, and later says **"audit this app"**; the agent connects to the app, shows everything pending, and proceeds with the FOR AUDITS recipe, on both Claude Code and Gemini/Antigravity.

## Intent Ledger (do not drop any of these)

| ID | Intent | Where it lands |
| :--- | :--- | :--- |
| I1 | One standard way to capture what a human sees while debugging a web app, reusable across projects | M1-M3 |
| I2 | DevTools-style **Pick Element** and scoped **Record / Stop** session with a soft **Pause** while inspecting | M2 |
| I3 | Agents triage cheaply: default `list` shows only unresolved items, so `/frontier-architect`, `/app-debugger` and audit runs never re-read solved observations. ("FOR AUDITS" is the user's post-plan architecture audit prompt; see I10 and Related External Context.) | M1, M6 |
| I4 | Observations are linked to server-side runtime traces | M1, M3 |
| I5 | Connector scaffolder gives a Python project the whole thing in about 3 lines of setup (`fastapi`, `flask`, `generic`) | M3 |
| I6 | Skills tell agents to read open observations automatically and mark them resolved after a **verified** fix | M6 |
| I7 | Every new file <= 350 lines (target 150-250), every function <= 40 lines | all |
| I8 | **One codebase for Gemini/Antigravity (Windows) and Claude Code (macOS/Linux)**: no `.gemini`-only paths, no `python skills/...` assumptions, tests that pass on both | all |
| I9 | Debug data never leaks: off by default, local only, redacted, size-capped | M2, M3, M4 |
| I10 | **Feed the FOR AUDITS workflow:** findings and ideas captured with the HUD (or described in chat) arrive as structured observations, so the audit starts from them instead of retyped `[Finding N]` / `[Idea N]` placeholders; each triaged item records **why existing tests and diagnostics missed it** and the proposed guard | M1, M5, M6 |
| I11 | **A published standard** so any app (any language) implements its side without the skill's Python: HTTP wire contract + JSON Schema + a README for implementers + a conformance command; the skill itself can also guide an agent through integrating an app | M3, M4, M6 |
| I12 | **`brief`**: one command that connects to a project and prints everything pending (git, plans, observations, defects, traces, probes, architecture), with optional `--run-probes` | M5 |
| I13 | **`pull`**: fetch observations from a running app (including in a container or on another host) into the local catalog | M4 |
| I14 | **Audit mode**: `/frontier-architect audit <app>` runs `brief`, delegates cross-layer review, fills findings and ideas from observations, explains why tools missed each bug, then asks one decision at a time before editing | M6 |
| I15 | A shareable adoption plan so the consuming project (`intelligent-tracker`) implements the other side of the contract | `.TODO/debug_observation_connector_adoption_plan.md`, reconciled in M6 |

## Related External Context (not in this repository)

- `intelligent-tracker` PR #13 (`davtoh/intelligent-tracker`) has its own `.TODO/debug_observation_connector_adoption_plan.md`. It was not available when this roadmap was written, so its contents are **unverified here**. This repo now carries a proposed version of that file (the app-side plan, with the wire contract copied in). Reconcile the two at Milestone 6's pre-plan gate (the user supplies the PR's version); this roadmap's contracts win on conflicts unless the user decides otherwise.
- The user's reusable prompts **FOR RETROSPECTIVE** and **FOR AUDITS** live in that project's workflow and use Antigravity vocabulary (`ask_question`, `Model: 'flash'`, `RequestFeedback`). This roadmap does not change them; it changes what they can call: the FOR AUDITS baseline batch gains `diagnose.py brief --run-probes` (or `observations list --json`), and its "User-Observed Findings" and "Observations or Ideas" sections are filled from observations (kinds `element`/`error`/`network`/`note` for findings, `idea` for ideas).

## Decisions (defaults chosen; change here before the milestone that uses them)

| ID | Decision | Reason |
| :--- | :--- | :--- |
| D1 | Statuses: `open`, `triaged`, `in_progress`, `resolved`, `dismissed`. **ACTIVE** = open, triaged, in_progress. **CLOSED** = resolved, dismissed. | Reuses the defect catalog's `CLOSED_STATUSES` and `dismiss` verb; no third vocabulary |
| D2 | IDs are dual-key: sequential `OBS-001` and fingerprint `OBS-<KIND>-<6HEX>` | Mirrors `DEFECT-001`/`DEF-<RULE>-<6HEX>` and `TRC-<TYPE>-<6HEX>` |
| D3 | Correlation key is an exact **`recording_id`** (header `X-Debug-Recording-Id`); timestamp window +/-2 s is fallback only | Browser and server clocks skew |
| D4 | Observations correlate with **exception traces** only, not every request | Request logging does not exist; out of scope |
| D5 | Server routes exist only when env `FRONTIER_DEBUG_OBSERVATIONS=1`; loopback clients only; the HUD does nothing unless `window.__FRONTIER_DEBUG__ === true` | Safe by default |
| D6 | Docs use `python "<skill_dir>/scripts/diagnose.py" ...` where `<skill_dir>` is the `system-diagnostics` folder | Works from `.claude/skills/`, `~/.claude/skills/` and the monorepo |
| D7 | Fifth kind `idea`; fingerprint `OBS-IDEA-<6HEX>`; `list --kind` filter. **Confirmed by the user 2026-11-26.** | FOR AUDITS separates findings from ideas |
| D8 | `triage --missed-by LIST --guard TEXT` (tools: `tests,surface,scan,audit,ui,probes,trace,other`). **Confirmed by the user 2026-11-26.** | Captures the audit's "why did our tools miss it" answer |
| D9 | **Agreed:** a read route and `observations pull` are in | Needed to reach apps in containers or other hosts |
| D10 | **Agreed:** `brief` does not run probes by default; `--run-probes` runs fresh ones | Probes cost time and may open a browser |
| D11 | The wire contract is versioned: every response carries `X-Diagnostics-Contract: 1` and `GET .../health` reports `contract_version` | Lets `pull`, `verify-connector` and apps detect mismatches |
| D12 | `POST ...?dry_run=1` validates and answers exactly like a real POST but stores nothing | Lets the conformance command test without polluting data |
| D13 | The digest command is `diagnose.py brief` (not `audit`, which is the static auditor) | Avoids a name clash |
| D14 | `pull` refuses non-loopback URLs unless `--allow-remote`, and then warns; stdlib `urllib` only | Debug data should not cross networks by accident |
| D15 | Probe runs are not persisted today, so M5 adds a small `probe_history.py` that records the last result per probe in `.diagnostics/probe_last_run.json` (one-line hook in `probe_runner.py`, 293 L now) | `brief` needs "last known result" without re-running |

## Preconditions

- **P0:** all four suites pass before starting: `system-diagnostics` 264, `refactor-monolith` 159, `app-debugger` 24, `frontier-architect` 140 (the cross-platform test fixes are merged). If any is red, stop and fix that first.
- **P1:** `.diagnostics/` is gitignored by `defect_catalog.ensure_diagnostics_dir` (writes `.diagnostics/.gitignore` containing `*`). Reuse it.

## Architectural Pre-Flight

**Existing pieces to reuse (verified in the audit):**
- `trace_recorder.py` (282 L): `TraceCatalogManager` (atomic save), daily `.diagnostics/traces/trace_YYYYMMDD.jsonl`, events with `timestamp` and a `context` dict, fingerprint `TRC-<TYPE8>-<sha256[:6]>`.
- `trace_middleware.py` (63 L): ASGI and WSGI middleware that already put `http_method`, `http_path`, `client_host` into `context`.
- `trace_cli.py` (93 L): the delegating-CLI pattern. `connector_scaffolder.py` (150 L): writes `diagnostic_bridge.py`, templates embedded.
- `defect_catalog.py` (346 L, at the soft budget: **do not add code to it**): `ensure_diagnostics_dir`, lifecycle and dual-key patterns.
- `probe_runner.py` (293 L): `list_probes`, `run_probe`, `get_probe_search_dirs` (workspace `.diagnostics/probes`, built-in, custom). `arch_mapper.py` (327 L): `arch-map`. `skill_packager.py` ships every folder except `tests`, `evals`, `__pycache__`, `node_modules`.

**Wiring pattern for a new `diagnose.py` subcommand** (309 L): `import <module>` beside the others (about line 35), add the module to the tuple in `build_parser` (about line 269), add its entry to `dispatch` (about line 295). Three one-line edits; all logic in the new module. Re-check line numbers when implementing.

**Failure modes to handle:** corrupt `observations.jsonl` line (skip, count); concurrent appends (single `open("a")` write, atomic catalog save); missing `.diagnostics/traces/`; HUD disabled; non-loopback caller; oversized payload; framework missing in the target app (generated bridge imports cleanly, degrades to no-ops); remote app unreachable or speaking a different contract version (clear error, no partial import); a `brief` section failing (shown as `UNAVAILABLE (reason)`, never a crash).

## Data Contracts

**Raw record** (one JSON object per line in `.diagnostics/observations.jsonl`, UTF-8, `\n`):
```json
{"schema": 1, "ts": "2026-11-26T14:03:11.120Z", "kind": "element|error|network|note|idea",
 "page_path": "/dashboard", "selector": "main > button#save", "rect": {"x":0,"y":0,"w":0,"h":0},
 "attrs": {"tag":"button","id":"save","class":"btn primary","data-testid":"save","role":"button","aria-label":"Save"},
 "message": "Save does nothing", "recording_id": "rec-8f3a2c", "window": {"started_at": "...", "stopped_at": "..."},
 "timeline": [{"t": 0, "type": "click|input|nav|fetch|console|error", "target": "...", "status": 200, "ms": 41}]}
```
Limits on write: record <= 64 KB; `message` <= 500 chars; `timeline` <= 50 events (oldest dropped); file rotated at 5 MB to `observations.1.jsonl` (one backup).

**Fingerprint:** `sha256("{kind}|{page_path}|{selector or url_path}|{normalized_message}")[:6]` as `OBS-<KIND upper, max 7>-<6HEX>`. **Exact normalization (every implementation must match):** lowercase; remove `0x[0-9a-f]+`; remove `\d{5,}`; split on whitespace and rejoin with single spaces. `target` is `selector`, or the URL path for `network`, or empty. Hash input is the UTF-8 string `kind|page_path|target|normalized_message`; result is the first 6 hex chars of SHA-256. **Test vectors:** `element|/dashboard|main > button#save|"Save   does NOTHING"` -> `OBS-ELEMENT-fdd3fe`; `error|/tracker|/api/frames|"Request 123456 failed at 0xDEADBEEF"` -> `OBS-ERROR-f93b8a`; `idea|/dashboard||"Add a pause button"` -> `OBS-IDEA-eca73f`. Same fingerprint increments `occurrence_count` and refreshes `last_seen`; never a second entry.

**Catalog** (`.diagnostics/observation_catalog.json`, atomic save): `{"schema_version":"1.0","workspace":"<posix path>","updated_at":"...","summary":{"total":0,"open":0,"triaged":0,"in_progress":0,"resolved":0,"dismissed":0},"observations":[...]}`; each entry: `id`, `fingerprint`, `kind`, `status`, `first_seen`, `last_seen`, `occurrence_count`, `page_path`, `selector`, `rect`, `attrs`, `message`, `recording_id`, `window`, `timeline`, `correlated_traces` (list of `TRC-...`), `root_cause`, `missed_by` (list), `proposed_guard`, `resolution`, `linked_plan`, `linked_commit`, `source_url` (set by `pull`), `history` (list of `{ts, from, to, note}`).

**Transitions:** open -> triaged | in_progress | resolved | dismissed; triaged -> in_progress | resolved | dismissed; in_progress -> resolved | dismissed | triaged; resolved -> open (recurrence reopens, with a history note); dismissed stays dismissed unless explicitly reopened.

## Wire Contract v1 (HTTP; language-agnostic; the standard an app implements)

Base path `/api/diagnostics` (configurable). **Availability:** these routes exist only when env `FRONTIER_DEBUG_OBSERVATIONS=1`; otherwise the app must answer `404` for all of them. **Access:** loopback clients only (`127.0.0.1`, `::1`); anything else gets `403`. Every response carries header `X-Diagnostics-Contract: 1`. Errors are JSON `{"error": "<code>", "message": "..."}` with codes `invalid_json`, `invalid_record`, `payload_too_large`, `forbidden`, `not_found`, `unsupported_media_type`.

| Route | Request | Success | Errors |
| :--- | :--- | :--- | :--- |
| `GET /health` | none | `200 {"schema":1,"enabled":true,"contract_version":1,"store":"ok"}` | n/a |
| `POST /observation` | `Content-Type: application/json`, body = raw record; optional `?dry_run=1` | `201 {"id":"OBS-001","fingerprint":"OBS-ELEMENT-ab12cd","status":"open","deduplicated":false}`; `200` with `"deduplicated":true` when the fingerprint exists; `200` with `"dry_run":true` and nothing stored when `dry_run=1` | `400 invalid_json\|invalid_record`, `403 forbidden`, `413 payload_too_large` (> 64 KB), `415 unsupported_media_type` |
| `GET /observations` | query `status` (default `active`), `kind`, `limit` (default 20, max 200) | `200 {"schema":1,"count":N,"truncated":false,"observations":[{"id","fingerprint","status","kind","page_path","selector","message","occurrence_count","last_seen"}]}` | `403 forbidden` |
| `GET /observations/{id_or_fingerprint}` | none | `200` full catalog entry | `404 not_found`, `403 forbidden` |
| `GET /hud.js` | none | `200`, `Content-Type: application/javascript`, `Cache-Control: no-store`, body = the HUD bundle | `403 forbidden` |

**Request header (HUD to app):** `X-Debug-Recording-Id: rec-<6hex>` on every fetch or XHR made while recording. **App obligations:** (1) enforce gating, loopback, size and redaction (server-side drop of any field named `value`, `password`, `authorization`, `cookie`); (2) persist observations so `GET` reflects them; (3) stamp `recording_id` into its exception traces if it wants exact correlation.

**Two integration tiers:** **A (Python, uses the skill):** `diagnose.py traces --scaffold <fastapi|flask|generic> --dest <dir> --with-observations` generates a bridge implementing everything above and storing into `.diagnostics/`. **B (any language, no skill code):** implement the table above against any storage; the agent imports with `observations pull`. Both are checked by `observations verify-connector --url ...`.

## CLI Contract

Existing-style actions accept `--path DIR` (workspace root, default cwd) and `--json`. Exit codes: `0` success (including "nothing to show"), `1` not found or remote failure, `2` usage error.

| Command | Flags | Behavior |
| :--- | :--- | :--- |
| `observations list` | `--status active\|all\|open\|triaged\|in_progress\|resolved\|dismissed` (default `active`), `--kind element\|error\|network\|note\|idea`, `--limit N` (20) | Compact line per item: `OBS-003 [open] element /dashboard button#save "Save does nothing" (2x, 2026-11-26)`. Empty: `No active observations.` JSON mode: compact fields only. |
| `observations show` | `--id ID\|fingerprint`, `--full` | Full entry, timeline, correlated traces; `--full` adds all history. |
| `observations add` | `--kind`, `--page`, `--selector`, `--message`, `--recording-id` | Manual or chat-described capture; same dedup and caps as HUD posts. |
| `observations triage` | `--id`, `--root-cause` (required), `--plan SLUG`, `--status triaged\|in_progress`, `--missed-by LIST`, `--guard TEXT` | Unknown tool in `--missed-by` is a usage error (exit 2). |
| `observations resolve` | `--id`, `--resolution` (required), `--commit SHA` | Marks `resolved`; hidden from default `list`. |
| `observations dismiss` | `--id`, `--reason` (required) | Marks `dismissed`. |
| `observations pull` | `--url URL` (required), `--status`, `--kind`, `--allow-remote`, `--timeout S` (10) | Preflight `GET /health` (must report `contract_version` 1 and `enabled`), then list, then `GET` each entry that is new or has a newer `last_seen`; merge by fingerprint (remote `last_seen` newer wins for status; local triage fields kept; `source_url` recorded); one atomic catalog save at the end; refuses non-loopback hosts unless `--allow-remote` (then warns). Summary: `pulled N (new A, updated B, unchanged C)`. Network or contract error: exit 1, nothing written. |
| `observations verify-connector` | `--url URL`, `--json` | Conformance run against an app's routes (see the Conformance Contract). Exit 0 only if every applicable check passes. |
| `brief` | `--path DIR`, `--json`, `--run-probes`, `--pull URL`, `--max-lines N` (120) | One-shot state-of-project digest (see the Brief Contract). |

## Conformance Contract (`observations verify-connector`)

Checks, in order, each reported `PASS`, `FAIL` (with the exact expected vs actual) or `SKIP` (with the reason): health shape and `contract_version`; `X-Diagnostics-Contract` header on every response; `POST ?dry_run=1` with a valid record returns 200 `dry_run:true`; same for each invalid case (`invalid_json` 400, `invalid_record` 400, oversize 413, wrong content type 415); `GET /observations` shape and `limit`/`kind` honored; `GET /observations/OBS-DOES-NOT-EXIST` is 404; `GET /hud.js` content type and `no-store`; redaction (a dry-run record containing `value` and `password` keys must be accepted but those keys absent from the echoed `accepted` preview if the app returns one; otherwise `SKIP`); the non-loopback `403` rule is `SKIP` (cannot be tested from loopback) and listed as a manual check. Never writes real data (uses `dry_run`).

## Brief Contract (`diagnose.py brief`)

Prints a compact digest with a fixed section order and per-section line caps (total `--max-lines`, default 120). Each section is produced by an independent collector; a failing collector prints `UNAVAILABLE (<reason>)` and the run continues (honest reporting, Axiom 9). `--json` returns the same sections as objects. Sections:
1. **Git** (<= 8 lines): branch, ahead/behind, counts from `git status --short`.
2. **Plans** (<= 10): active plan, milestone and progress via `plan_engine.py status` when frontier-architect is installed (resolved by the same candidate order as the shims), else the number of `.TODO` plans and "frontier-architect not found".
3. **Observations** (<= 30): ACTIVE items grouped as **Findings** (`element`, `error`, `network`, `note`) and **Ideas** (`idea`), each with id, page, selector, message, occurrences, and correlated trace ids. With `--pull URL`, runs `observations pull` first.
4. **Defects** (<= 10): open defect count and top 5 from the defect catalog.
5. **Traces** (<= 10): active trace issues, top 5.
6. **Probes** (<= 15): registered probes and their **last recorded result** with age (from `.diagnostics/probe_last_run.json`, D15); with `--run-probes`, runs every workspace probe fresh (60 s timeout each, sequential) and labels results `fresh`; a probe that cannot run reports `INFRA_UNAVAILABLE`, never a pass.
7. **Architecture** (<= 10): `arch-map` summary (files over budget, top coupling).
Exit 0 unless usage error (2). `brief` never edits any file except `.diagnostics/probe_last_run.json` when `--run-probes` is used.

## Audit Mode (`/frontier-architect audit <app path or URL>`)

Packaged in `frontier-architect/references/audit-recipe.md` (dual vocabulary, Claude and Gemini) with a one-line pointer in the router. Flow: (1) `brief --run-probes [--pull URL]`; (2) delegate cross-layer review to read-only subagents (Claude: `Explore`; Gemini: research subagents) so the main thread stays small; (3) take **findings** and **ideas** from observations, not placeholders; (4) for each bug, answer why tests, `surface --verify`, `scan`, `audit`, `ui` and probes missed it (`--missed-by`) and propose the exact guard (`--guard`); (5) ask the user one decision at a time (`ask_question` / `AskUserQuestion`, recommended option first) **before any edit**; (6) only after decisions: update the architecture docs and register a Master Roadmap plus Step 1 child via `plan_engine.py init`, then stop with `/frontier-architect continue <step_1_slug>`. A companion recipe `references/connector-integration.md` tells an agent how to integrate an app (detect framework, scaffold or implement the contract, run `verify-connector`, fix failures).

## HUD Contract (Milestone 2)

- Three plain scripts in `system-diagnostics/assets/` (`hud_core.js`, `hud_picker.js`, `hud_recorder.js`, each <= 300 lines) concatenated in that fixed order by `observation_assets.hud_bundle()`. No dependencies, no build step.
- **Gate:** if `window.__FRONTIER_DEBUG__ !== true` the bundle returns immediately and touches nothing (no listeners, DOM or timers).
- **Pick Element:** capture-phase hover highlight; click records a unique CSS selector (prefer `#id`, then `[data-testid]`, then a short tag/class path verified with `querySelectorAll(sel).length === 1`), `getBoundingClientRect()`, and the allowlisted attributes only.
- **Record / Stop:** `recording_id` (`rec-<6hex>`), `started_at`, `stopped_at`; while recording, wrap `fetch` and XHR so each request carries `X-Debug-Recording-Id`; timeline logs click, navigation, fetch status + latency, `console.error`, `window.onerror`. (WebSocket frames are out of scope for contract v1.)
- **Soft Pause:** pauses `<video>`/`<audio>` and `requestAnimationFrame` loops and suppresses page click propagation while Pick is active; fully restored on exit.
- **Log Observation:** posts to `/api/diagnostics/observation` (configurable via `window.__FRONTIER_OBS_ENDPOINT__`).
- **Redaction (hard):** never read `input.value`, `textarea` content or `contenteditable` text: record only tag, `type`, `name`, value length; skip `type=password` entirely; record fetch URL **path** plus query **keys** (never values); never record bodies or `Authorization`/`Cookie` headers.

## Correlation Contract

1. **Stamp:** `trace_middleware.py` reads `x-debug-recording-id` (ASGI: `scope["headers"]`, lowercase byte keys; WSGI: `environ["HTTP_X_DEBUG_RECORDING_ID"]`) and adds `recording_id` to the trace event `context`.
2. **Match:** `observation_correlate.correlate(obs, traces_dir)` scans `trace_YYYYMMDD.jsonl` files in the window and returns trace fingerprints whose `context.recording_id` equals the observation's (exact). With no `recording_id`, fall back to events with `timestamp` in `[started_at - 2 s, stopped_at + 2 s]`.
3. **Store:** matches go in `correlated_traces`; `show` prints each with exception type and culprit.

## Security & Privacy Contract

Routes generated only when `FRONTIER_DEBUG_OBSERVATIONS=1`; loopback only (`403` otherwise); size, rotation and redaction enforced on write; `pull` is loopback-only by default; data lives only in `.diagnostics/` (gitignored) and the docs must say so; the HUD, the routes and the conformance command never store request or response bodies, cookies or credentials.

## Runtime Parity Contract (Gemini/Antigravity and Claude Code)

- Python 3.10+ standard library only; `pathlib`, forward slashes in stored paths, `encoding="utf-8"`, `\n` newlines.
- **Tests resolve temp dirs:** `Path(tempfile.mkdtemp()).resolve()`; compare paths with `.resolve()` on both sides (macOS `/var` is a symlink to `/private/var`; this broke seven tests before this plan). Tests needing `node`, Chrome or network sockets skip when unavailable; network tests bind `127.0.0.1` on an ephemeral port and never leave servers running.
- Generated bridges must find the engine on both runtimes: candidates in order `SYSTEM_DIAGNOSTICS_DIR`, `<project>/.claude/skills/system-diagnostics`, `~/.claude/skills/system-diagnostics`, sibling `../system-diagnostics`, `<project>/skills/system-diagnostics`, `~/.gemini/config/skills/system-diagnostics` (the old templates only had the last two plus a `parents[2]` guess, so under Claude the bridge silently did nothing).
- No new `ask_question`, `run_command`, `RequestFeedback`, `<appDataDir>` or `python skills/...` strings in any file; where prose needs a tool name write both (`ask_question` / `AskUserQuestion`), as the adapter-gated docs do.

## Scenario Combinations Matrix

| Scenario | Command or trigger | Expected result |
| :--- | :--- | :--- |
| Agent lists work (default) | `python "<skill_dir>/scripts/diagnose.py" observations list` | Only active items, compact lines; exit 0 |
| Nothing open | same | `No active observations.`; exit 0 |
| Include history | `... observations list --status all` | Resolved and dismissed appear too |
| Findings vs ideas | `... observations list --kind idea` | Only idea entries |
| Triage and link to plan | `... observations triage --id OBS-001 --root-cause "..." --plan <slug>` | Status `triaged`, plan linked, history entry |
| Record why tools missed it | `... observations triage --id OBS-004 --root-cause "..." --missed-by tests,surface --guard "add layout probe"` | Stored, shown by `show`; unknown tool exits 2 |
| Resolve after verified fix | `... observations resolve --id OBS-001 --resolution "..." --commit <sha>` | `resolved`; absent from default `list` |
| Unknown id / missing flag | `show --id OBS-999` / `resolve --id OBS-001` | exit 1 / exit 2 |
| Same problem twice | HUD posts identical element + message | One entry, `occurrence_count` 2 |
| Resolved problem recurs | same fingerprint after `resolve` | Reopened to `open`, history note |
| Corrupt jsonl line | one bad line among good ones | skipped and counted; no crash |
| Scaffold with observations | `... traces --scaffold fastapi --dest services --with-observations` | Bridge with trace middleware, gated routes (POST, GET, health, hud.js) |
| Scaffold without flag | `... traces --scaffold fastapi --dest services` | Output identical to today except the shared path bootstrap |
| Routes disabled | env `FRONTIER_DEBUG_OBSERVATIONS` unset | all `/api/diagnostics/*` answer 404 |
| Non-loopback caller | any route from another host | 403 |
| HUD disabled | `window.__FRONTIER_DEBUG__` not true | no listeners, no DOM changes |
| Exact correlation | app throws while recording | trace carries `recording_id`; `show` lists its `TRC-...` |
| Window fallback | observation without `recording_id` | traces within +/-2 s listed |
| Pull from running app | `... observations pull --url http://127.0.0.1:8000` | `pulled N (new A, updated B, unchanged C)`; atomic; local triage kept |
| Pull wrong contract version | server reports `contract_version` 2 | exit 1, nothing written |
| Pull remote host | `--url http://10.0.0.5:8000` | refused (exit 2) unless `--allow-remote`, then warning |
| App unreachable | server down | exit 1, clear message, nothing written |
| Conformance good app | `... observations verify-connector --url ...` | all PASS (loopback rule `SKIP`), exit 0 |
| Conformance bad app | app returns 200 for oversize POST | `FAIL` with expected vs actual, exit 1 |
| Brief, default | `... brief --path <app>` | all 7 sections; probes show last recorded results with age |
| Brief with probes | `... brief --path <app> --run-probes` | probes run fresh, labeled `fresh`; `INFRA_UNAVAILABLE` never shown as pass |
| Brief section fails | e.g. no `.diagnostics/` | that section `UNAVAILABLE (reason)`; others unaffected |
| Audit mode | `/frontier-architect audit <app>` | brief, subagent review, observations as findings/ideas, tool-gap answers, then one question at a time before edits |
| Claude install layout | skills copied to `.claude/skills/` | `observations`, `brief` and the generated bridge work from another cwd |

## SPIKE Spec (required at the start of Milestone 2, before its tasks)

1. **Riskiest assumption (SRA):** the HUD can pick elements and record in realistic pages, including a same-origin iframe, open shadow DOM, a strict `script-src 'self'` CSP, and a page with `<video>`.
2. **Metric:** for 6 fixture pages (`plain`, `spa`, `iframe`, `shadow`, `csp`, `media`), count pages where (a) the picked selector satisfies `document.querySelector(sel) === pickedElement` and (b) Record produces a non-empty timeline with `recording_id` on fetch headers.
3. **Pass / fail:** pass = at least 5 of 6; fail = 3 or fewer; 4 = inconclusive (add one fixture, rerun once).
4. **Fixture and timebox:** hand-written HTML under `tests/fixtures/hud/`, run with `cdp_inspect.py --headless` (skip with a clear note if no Chrome); one day.
5. **Decision rule:** pass -> build Milestone 2 as specified; fail -> ship without iframe and shadow DOM support, document the limits, and serve the HUD as an external script file with CSP nonce guidance.
6. **Lives in:** `.frontier/scratch/obs-hud/` (Claude Code; Antigravity: its scratch folder). Keep only the 6 fixtures and the result table.

## Milestones (execution order, strictly sequential)

Each milestone ends with: Pre-Flight Critic Gate -> sliced edits -> `diagnose.py audit --path <touched files>` (zero audit evasion) -> `plan_engine.py verify` -> **Review Gate** -> `advance`. **Review Gate:** a fresh reviewer (not the author; Claude: Opus, Gemini: planner tier) receives the diff plus verify output (not the author's conclusion) and must confirm each exit criterion; a failed gate counts as one attempt toward Anti-Thrash Stop-Loss (two attempts, then revert and escalate). If a milestone exceeds 8 files at its pre-plan gate, split it into `<N>A`/`<N>B` child plans.

## Milestone 1: Observation Store, Correlation Reader & Triage CLI (`diagnose.py observations`)

**Child Plan**: .TODO/step_1_observation_store_cli.md

- [x] **child plan .TODO/step_1_observation_store_cli.md**: execute the child plan (7 files: `observation_store.py`, `observation_correlate.py`, `observation_cli.py`, three test modules, three one-line edits in `diagnose.py`).

**Verifier**: `python -m unittest discover -s system-diagnostics/tests -p "test_observation_*.py"` then the four suite commands in the Definition of Done.
**Exit criteria:** all `list/show/add/triage/resolve/dismiss` rows pass in tests; default `list` hides CLOSED items; kinds incl. `idea`, `--kind`, `--missed-by/--guard` covered; dedup, reopen and corrupt-line cases covered; `diagnose.py` grew by 3 lines only; every new file <= 350 lines.

## Milestone 2: DevTools Observation HUD

- [x] **child plan .TODO/step_2_*.md**: created just in time (~7 files): SPIKE fixtures (`system-diagnostics/tests/fixtures/hud/*.html`), `system-diagnostics/assets/hud_core.js`, `hud_picker.js`, `hud_recorder.js`, `system-diagnostics/scripts/observation_assets.py` (bundle order and gate), `tests/test_observation_hud.py` (Node VM logic tests with a small fake DOM; skip without `node`), `tests/test_observation_hud_e2e.py` (Chrome-gated via `cdp_inspect`; skip without Chrome).

**Verifier**: `python -m unittest discover -s system-diagnostics/tests -p "test_observation_hud*.py"`
**Exit criteria:** SPIKE result recorded (pass or documented fallback); each HUD Contract row has a test; strict no-op when disabled; each JS file <= 300 lines.

## Milestone 3: Wire Routes, Correlation Stamping, Scaffolder & Published Contract

- [x] **child plan .TODO/step_3_*.md**: created just in time (about 11 files, so expect a split into **3A** stamping, shared bootstrap and POST/HUD routes, and **3B** GET/health/dry_run routes and the published contract): `trace_middleware.py` (stamp `recording_id`), `connector_bridge_common.py` (engine path bootstrap per the Parity Contract; replaces the three copies), `connector_templates_obs.py` (all Wire Contract routes for fastapi, flask, generic; **new module** because `connector_scaffolder.py` would exceed budget), `connector_scaffolder.py` (wire the flag, use the shared bootstrap), `trace_cli.py` (`--with-observations`, valid only with `--scaffold`), `system-diagnostics/references/observation-connector-contract.md` (the human README: wire contract, tiers A and B, copy-paste examples, curl checks, security notes), `system-diagnostics/references/observation_contract.schema.json` (JSON Schema for the raw record, list response and error), tests: `test_connector_scaffolder.py` (new; no direct test exists today), `test_trace_recorder.py` (recording_id cases), `test_observation_bridge_routes.py` (import generated bridges without frameworks; call handlers with fake requests; every Wire Contract row), `test_observation_contract_doc.py` (the doc's route table and the schema stay consistent with the templates).

**Verifier**: `python -m unittest discover -s system-diagnostics/tests -p "test_*.py"`
**Exit criteria:** "Scaffold without flag" unchanged except the shared bootstrap; generated bridges import with no framework installed and implement every Wire Contract row (status codes, headers, dry_run, gating, loopback, redaction, caps); Claude-layout test passes; the published contract and schema match the templates.

## Milestone 4: Remote Pull & Conformance (`observations pull`, `observations verify-connector`)

- [x] **child plan .TODO/step_4_*.md**: created just in time (~8 files): `observation_merge.py` (merge a remote entry into the local catalog using store primitives; **new module, do not grow `observation_store.py`**), `observation_pull.py` (preflight, fetch, merge, atomic save; stdlib `urllib`), `observation_verify.py` (Conformance Contract), `observation_cli_remote.py` (registers `pull` and `verify-connector`; one-line hook in `observation_cli.py`), tests `test_observation_merge.py`, `test_observation_pull.py` and `test_observation_verify.py` (local stub servers on `127.0.0.1`, ephemeral ports: compliant, wrong contract version, unreachable, non-compliant variants).

**Verifier**: `python -m unittest discover -s system-diagnostics/tests -p "test_observation_*.py"`
**Exit criteria:** every pull and conformance scenario row passes against stub servers; pull is atomic (failure writes nothing); loopback rule and `--allow-remote` enforced; the generated bridges from Milestone 3 pass `verify-connector` in a test that runs one in-process.

## Milestone 5: Project Brief (`diagnose.py brief`) & Probe History

- [x] **child plan .TODO/step_5_*.md**: created just in time (~6 files): `brief.py` (orchestration, rendering, caps, JSON), `brief_sections.py` (the seven collectors, each independent), `probe_history.py` (records last result per probe in `.diagnostics/probe_last_run.json`; one-line hook in `probe_runner.run_probe`), `diagnose.py` (three one-line edits), tests `test_brief.py` (caps, order, `UNAVAILABLE` isolation, JSON mode, `--pull` ordering) and `test_probe_history.py` (records and ages results; `--run-probes` path with a stub probe; `INFRA_UNAVAILABLE` never reported as pass).

**Verifier**: `python -m unittest discover -s system-diagnostics/tests -p "test_brief.py"` and `python -m unittest discover -s system-diagnostics/tests -p "test_probe_history.py"`, then the four suites.
**Exit criteria:** all Brief Contract rows covered; `brief` edits nothing except `probe_last_run.json` under `--run-probes`; `probe_runner.py` stays <= 350 lines.

## Milestone 6: Audit Mode, Skill Integration, Docs & Adoption Plan Reconciliation

- [x] **child plan .TODO/step_6_*.md**: **6A DONE** (`.TODO/step_6a_observation_docs_and_debugger.md`: observations.md, cli-reference, system-diagnostics pointer, app-debugger SKILL + eval 14, doc test; engine auto-closed this box after 6A, reopened because 6B is pending). **6B PENDING** (frontier-architect `audit-recipe.md`, `connector-integration.md`, SKILL.md one-liner, phase-protocols, audit-mode eval, `ARCHITECTURE.md`, `AGENTS.md`, adoption-plan reconciliation). Created just in time. Expected files (split into **6A** system-diagnostics + app-debugger and **6B** frontier-architect + repo docs if above 8): `frontier-architect/references/audit-recipe.md` and `connector-integration.md` (dual vocabulary), `frontier-architect/SKILL.md` (one short line only: **it must stay under 12,000 bytes with about 170 bytes of headroom, so put the text in references**), `frontier-architect/references/phase-protocols.md`, `system-diagnostics/SKILL.md` (pointer only; already 15.5 KB), `system-diagnostics/references/observations.md` (workflow, audit hand-off, privacy) and `cli-reference.md`, `app-debugger/SKILL.md` + its evals (read active observations, resolve after verified fix), eval cases for audit mode (pressure case with Antigravity wording), `ARCHITECTURE.md` and `AGENTS.md` refresh, regression guards. Also: reconcile `.TODO/debug_observation_connector_adoption_plan.md` with what was actually built and with the PR's version.

**Verifier**: the four suite commands in the Definition of Done, plus `python -m unittest discover -s frontier-architect/tests -p "test_adapter_gating.py"`.
**Exit criteria:** docs use `<skill_dir>` commands only; adapter-gating and router-size tests pass; audit-mode recipe has a passing A/B pressure eval under Claude (new skill not worse than baseline); `ARCHITECTURE.md` sections 3 and 7 updated; the adoption plan matches the shipped contract.

## Handoff Protocol (every session)

Start: `plan_engine.py status universal_debug_observation_connector_plan` then `next`; open only the contract sections the milestone cites. End: run `advance`, echo `Suggested Commit` (never commit without consent), **record this session for the retrospective** (follow "Capture Protocol" in `.TODO/retrospective_claude_support_plan.md`: one line appended to `.frontier/sessions.jsonl` using `$CLAUDE_CODE_SESSION_ID` under Claude Code, or the conversation id under Antigravity), and stop. If a milestone exceeds about 110 steps, pause with a Ready-to-Paste Handoff Prompt listing completed edits, pending items and verify commands.

## Risks and Rollback

| Risk | Mitigation |
| :--- | :--- |
| HUD does not work in some page types | SPIKE decides scope before Milestone 2; limits documented |
| Debug data exposed | Gating, loopback-only, redaction, caps, gitignored store, `pull` loopback default |
| Wire contract drifts between skill, doc and app | Versioned header, schema file, doc-consistency test, `verify-connector` |
| Apps in other languages mis-implement | Language-agnostic contract, curl checklist, conformance command |
| Third catalog diverges from the others | Same statuses, IDs and atomic-save pattern |
| Budget creep (`diagnose.py`, `connector_scaffolder.py`, `observation_store.py`, `probe_runner.py`) | New modules only; one-line hooks; budgets in exit criteria |
| Gemini regression from Claude-oriented changes | Parity Contract; no platform-specific code paths; all tests resolve paths |
| `brief` hides a failure | Per-section `UNAVAILABLE`, `INFRA_UNAVAILABLE` never a pass |

Rollback per milestone: revert that milestone's commit; everything is additive and off by default.

## Out of Scope

Request-level logging of every HTTP call; WebSocket frame capture (contract v1); non-web debugging; a graphical triage UI; syncing observations off the machine beyond loopback `pull`; a Windows installer.

## What Changed From the Previous Draft (traceability)

1. `traces scaffold --framework ... --with-observations` was not a real command; the real form is `traces --scaffold fastapi --dest services`, and the flag is added there.
2. `observations` is registered through a delegating `observation_cli.py`, not by editing `diagnose.py` logic.
3. One status vocabulary shared with the defect catalog (`dismissed` replaces `wontfix`).
4. Fingerprint, ID and record schemas defined.
5. Correlation uses an exact `recording_id` instead of a time window alone.
6. Security, privacy, caps and default-off gating are a contract.
7. A SPIKE Spec precedes the HUD, as the skill requires.
8. Milestone 3's templates moved to a new module; the bridge engine-path bug (silent no-op under Claude installs) is fixed there.
9. The verifier no longer runs a suite with known failures; P0 requires green suites.
10. FOR AUDITS clarified by the user: intents I3 and I10, decisions D7 and D8.
11. User-approved extension (2026-11-26): wire contract v1 and published standard (I11), `pull` (I13, D9, D14), `brief` with `--run-probes` (I12, D10, D13, D15), audit mode (I14), conformance command, adoption plan (I15); milestones grew from 4 to 6 (docs moved to 6).

## Definition of Done

- [ ] All four suites pass: `python -m unittest discover -s system-diagnostics/tests -p "test_*.py"`, `... -s refactor-monolith/tests ...`, `... -s app-debugger/tests ...`, `... -s frontier-architect/tests ...`.
- [ ] `python "<skill_dir>/scripts/diagnose.py" audit --path <all new and touched files>` exits 0 (no file over 350 lines, no function over 40).
- [ ] Every Intent Ledger row (I1-I15) traces to a passing test or a doc section.
- [ ] No new Gemini-only or repo-relative strings (`grep -rnE "ask_question|run_command|view_file|RequestFeedback|appDataDir|python skills/"` on touched files shows only dual-vocabulary lines).
- [ ] Scaffold-without-flag regression test passes; default `list` hides closed items; generated bridges pass `verify-connector`.
- [ ] `ARCHITECTURE.md` refreshed; Review Gate recorded for each milestone; the adoption plan reconciled.
- [ ] Final sign-off: Non-Mocked Branch Gate (`diagnose.py scan --path .`), `digest --backfill --write-scaffold`, `diagnose.py changelog add`.
