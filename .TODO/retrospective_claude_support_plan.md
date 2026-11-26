# Master Roadmap: Retrospective Support for Claude Code (without breaking Gemini/Antigravity)

> **Status: NOT IMPLEMENTED.** Written 2026-11-26. Execute one milestone per session with `/frontier-architect continue retrospective_claude_support_plan`. Only the **Capture Protocol** below is meant to be used **today**, while you run the milestones of `universal_debug_observation_connector_plan` in separate conversations; everything else is built afterwards, using the session ids you collect.
> This plan makes the existing retrospective workflow (the user's **FOR RETROSPECTIVE** prompt, `diagnose.py transcript-audit`, `debug-retro`, `plan_engine.py retrospective|digest`) work on Claude Code **and** keep working on Gemini/Antigravity. One codebase, a vendor flag, and a recipe the skill selects.

## Intent Ledger (do not drop any of these)

| ID | Intent |
| :--- | :--- |
| R1 | Run each milestone of a master plan (and its sub plans) in **separate conversations**, collect their ids, and feed them to one later session that audits them |
| R2 | The retrospective works for **Claude Code** sessions: same questions, same outputs (`learning_proposal.md`, `LEARNING_SCAFFOLD.md` audit, plan-granularity review), derived from Claude's own session logs |
| R3 | **Gemini/Antigravity keeps working unchanged**: same flags, same default behavior, byte-identical output for Antigravity-only runs |
| R4 | A **flag to choose the vendor** (`claude` or `gemini`), and the skill **knows which retrospective recipe to follow** when no flag is given |
| R5 | Keep the rule "do not load raw transcripts into context": audits go through the deterministic tool and compact summaries |
| R6 | Session ids should be **easy to get**, ideally recorded automatically, so the user does not copy them by hand |
| R7 | The retrospective must survive transcript cleanup (Claude Code may delete old sessions) |
| R8 | Every new file <= 350 lines, every function <= 40 lines; tests that pass on macOS, Linux and Windows |

## Verified facts (checked 2026-11-26 on this machine; structure only, no conversation content was read)

- **Claude Code session logs:** `~/.claude/projects/<project-slug>/<session-id>.jsonl`. The slug is the working directory with `/` and `.` replaced by `-` (for example `-Users-name-work-repo`). The session id is the file name (a UUID).
- **A session knows its own id:** env `CLAUDE_CODE_SESSION_ID` equals the log file name (verified); env `CLAUDECODE=1` marks a Claude Code runtime.
- **Record shape:** one JSON object per line. Top-level `type` values seen: `user`, `assistant`, `system`, `attachment`, `queue-operation`, `file-history-snapshot`, `ai-title`, `last-prompt`, `tools-used`, plus internal bookkeeping types. Common keys: `sessionId`, `uuid`, `parentUuid`, `timestamp` (ISO UTC), `cwd`, `gitBranch`, `version`, `isSidechain`, `message`.
- **Messages:** `message.content` is a list of blocks of type `text`, `thinking`, `tool_use` (`name`, `input`, `id`) and `tool_result` (`tool_use_id`, `content`, optional `is_error`). Assistant messages carry `message.usage` with `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` (Antigravity logs have no token counts).
- **Tool names seen:** `Bash`, `Read`, `Edit`, `Write`, `Agent`, `Skill`, `Monitor`, `ToolSearch`, `ExitPlanMode`, `TaskStop` (and `EnterPlanMode`, `Grep`, `Glob` exist).
- **Subagents** are **not inlined** in the main log: each has `<session-id>/subagents/agent-<agent-id>.jsonl` plus `agent-<agent-id>.meta.json`. A session with many subagents has many files (this session had 84).
- **Antigravity logs (existing tool):** `<brain>/<cid>/.system_generated/logs/transcript.jsonl`, brain dir from env `AGY_BRAIN_DIR` else `~/.gemini/antigravity/brain`; tool names such as `run_command`; failures parsed from `Command exited with code N` text.
- **Caveat:** Claude Code's log format is not a documented, stable API. The reader must tolerate unknown keys and missing fields, never crash, and be covered by synthetic fixtures so a format change fails a test instead of silently corrupting a retrospective.
- **Unverified:** Claude Code's transcript retention. Current versions may delete old sessions after a retention period (a `cleanupPeriodDays` setting is believed to exist, default about 30 days). Confirm in the user's settings before relying on old sessions; Milestone 3's summary export removes the dependency.

## Capture Protocol (works today, no new code)

For **every milestone conversation** of the observation plan (or any plan), as the last action before stopping:
1. Record the session in the local ledger (create `.frontier/` if missing; it is gitignored by `plan_engine`). Under Claude Code, run:
   `python3 -c "import json,os,time,sys;print(json.dumps({'v':1,'ts':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'plan':sys.argv[1],'milestone':int(sys.argv[2]),'event':'manual','vendor':'claude','session_id':os.environ.get('CLAUDE_CODE_SESSION_ID',''),'inferred':False}))" <plan_slug> <milestone_number> >> .frontier/sessions.jsonl`
   Under Antigravity, append the same shape with `"vendor":"gemini"` and the conversation id (the folder name under the brain directory).
2. Keep using the existing convention `plan_engine.py retrospective ... --cid <session id>` at milestone end; it already stores the id in `.frontier/plans/<slug>/retrospectives.json`.
3. If you work in another repository (for example `intelligent-tracker`), do this **in that repository's** checkout; its sessions live under its own project slug.
4. Do not delete session logs until the retrospective has run (or until Milestone 3 exists and you have run `--export-summary`).
Ledger line format (the contract Milestone 3 reads): `{"v":1,"ts":"<ISO UTC>","plan":"<slug>","milestone":<int or null>,"event":"advance|retrospective|handoff|manual","vendor":"claude|gemini","session_id":"<id>","inferred":false,"branch":"<optional>"}`.

## Sequencing with the Observation Plan (recommended)

1. **Retrospective Milestones 1-3 first** (reader, metrics, discovery, ledger, summary export): they are needed *during* the observation campaign, because they make session ids automatic, make `plan_engine retrospective --cid` return real telemetry under Claude, protect sessions from cleanup (`--export-summary`), and let you audit each milestone as it finishes.
2. **Then run the observation milestones** (one conversation each). After the first one, run `transcript-audit --cids <id>` as an early calibration: does the tool's step, failure and duplicate-read count match what you saw? Fix the reader before the next milestone if not.
3. **Retrospective Milestone 4** (recipes) any time after step 1; **Milestone 5** (calibration and sign-off) only after the observation milestones are done, using their sessions.
Fallback if the observation feature is urgent: run it first using only the Capture Protocol. The cost is manual telemetry (`--steps` by hand), no per-milestone learning loop, and a retention risk for old sessions (check the cleanup setting first).

## Decisions (change here before the milestone that uses them)

| ID | Decision | Reason |
| :--- | :--- | :--- |
| D1 | **Two independent axes.** *Source vendor* = format of the transcript being read (`--vendor auto\|gemini\|claude`, per session id). *Recipe* = which instructions and tool vocabulary the agent follows (`--recipe auto\|gemini\|claude`). A Claude session may audit Antigravity logs and the reverse. | Mixed histories are real, and the instructions must match the tools of the agent doing the work |
| D2 | **Source vendor precedence:** explicit `--vendor` > env `TRANSCRIPT_VENDOR` > where the id is found (a file `<id>.jsonl` under the Claude projects dir, or a folder under the brain dir; both found = error asking for `--vendor`) > default `gemini` | Keeps today's behavior as the fallback |
| D3 | **Recipe precedence:** explicit `--recipe` > env `RETROSPECTIVE_RECIPE` > runtime (`CLAUDECODE=1` means `claude`; otherwise `gemini`) | The recipe follows the runtime, not the logs |
| D4 | Antigravity-only runs produce **byte-identical output** to today. New columns and keys appear only when a Claude row is present. A golden-output test enforces it. | R3 |
| D5 | Claude subagent logs are read from `<session>/subagents/` and merged into the parent's metrics (duplicate-read detection needs them) | Subagents are not inlined |
| D6 | The ledger lives in `.frontier/sessions.jsonl` (written by `plan_engine` hooks and the Capture Protocol); `transcript-audit --plan <slug>` reads it | One file, gitignored, same format by hand and by tool |
| D7 | `--export-summary` writes compact per-session JSON to `.diagnostics/retro/<vendor>-<id8>.json` (metrics only, snippets <= 120 chars) | Survives log cleanup (R7) and keeps raw content out of context (R5) |
| D8 | **Confirmed by the user 2026-11-26:** one shared size threshold for both vendors, **24,000 bytes**, measured on `AGENTS.md` and, under Claude, on `CLAUDE.md` plus the files it imports. Kept as a single constant in one config location so the rule stays standard and shared; change it there if it is ever revised. | One standard rule across Gemini and Claude |

## Architectural Pre-Flight

**Files at or near the budget (do not grow them; extract first):** `system-diagnostics/scripts/transcript_auditor.py` (345 L), `transcript_checks.py` (134), `debug_retro.py` (169), `frontier-architect/scripts/plan_digest.py` (**351**, already over), `plan_engine.py` (342), `plan_state.py` (348).
**Seams to reuse:** `transcript_auditor.audit_conversation(brain_dir, cid)` returns a row dict (keys: `cid, steps, planner_turns, models, observed_models, tool_calls, failures, total_failures, audit_catches, tooling_cli_fails, failure_samples, user_corrections, workflow_redirects, subagents, reads_after_subagent, reads_while_pending, subagent_overlap_reads, repeated_reads, parallel_same_file_edits, plan_mode_calls, schedule_while_subagent, has_debug_retro, has_commit_hint, has_learning_block, cdp_live_fallbacks, cdp_live_failures, changelog_adds, suggested_grade_cap`); `transcript_checks.compute_grade_cap`; `plan_digest._transcript_rows/_resolve_one_cid/audit_single_cid/_dedupe_cids` (lines about 76-120, load the auditor through candidate paths); `debug_retro._audit_metrics`.
**Design:** a vendor router returns the **same row shape** for either vendor. The Antigravity reader stays as it is; a new Claude reader normalizes Claude records to the same internal step model and reuses the existing counting logic where it can.

## Contracts

**Normalized step (internal):** `{idx, ts, role: user|assistant|tool_result, kind: text|tool_call|tool_result, tool: <canonical>, args: {path, command, target}, ok: bool|None, exit_code: int|None, error: bool, model, tokens: {input, output, cache_read, cache_creation}|None, agent_id: str|None, text_snippet}`.

**Canonical tool names** (so existing checks work on both): `run_command` = Claude `Bash`; `view_file` = `Read`; `edit_file` = `Edit` (and `Write` counts as an edit of its path); `invoke_subagent` = `Agent`; `enter_plan_mode` = `EnterPlanMode`; `exit_plan_mode` = `ExitPlanMode`; `search` = `Grep`/`Glob`; `schedule` = `ScheduleWakeup`; `skill` = `Skill`.

**Metric derivation for Claude rows:**

| Row field | Claude derivation |
| :--- | :--- |
| `steps` | assistant `tool_use` blocks plus user turns (same counting rule as the Antigravity reader's "step"; documented in the reader) |
| `failures` / `total_failures` | `tool_result.is_error == true`; `Bash` results also parsed for a non-zero exit when `is_error` is absent; usage errors classified like `is_cli_usage_error` |
| `audit_catches` | test-runner failures (unittest/pytest) from `Bash`, as `classify_result` does today |
| `parallel_same_file_edits` | two or more `Edit`/`Write` blocks for the same path inside **one** assistant message |
| `reads_after_subagent`, `reads_while_pending`, `subagent_overlap_reads` | main-thread `Read`/`Bash cat` of a path that a subagent (from `subagents/agent-*.jsonl`) already read, or issued while an `Agent` call is still pending |
| `plan_mode_calls` | `EnterPlanMode` and `ExitPlanMode` counts with the same allowance rule as today |
| `schedule_while_subagent` | `ScheduleWakeup` call while an `Agent` call is pending |
| `models` / `observed_models` | `message.model` values seen |
| `user_corrections`, `workflow_redirects` | user `text` blocks matched by the same cue lists, **plus a configurable cue file** (`.diagnostics/retro_cues.json`) because the current cues are English-only and users also write in Spanish; calibrated in Milestone 5 |
| `has_debug_retro`, `has_commit_hint`, `has_learning_block`, `changelog_adds`, `cdp_*` | pattern matches in assistant text and `Bash` commands, same patterns |
| new: `vendor`, `session_id`, `branch`, `started_at`, `ended_at`, `tokens` | from `sessionId`, `gitBranch`, first and last `timestamp`, summed `usage`; `tokens` is `null` for Antigravity |
| `suggested_grade_cap` | `compute_grade_cap(steps, total_failures)` unchanged; an additional informational `token_note` may mention heavy cache or output totals but never changes the grade |

**CLI contract (`diagnose.py transcript-audit`, additive):** `--vendor auto|gemini|claude`, `--cids ID...` (either vendor, full id or 8-char prefix), `--latest N`, `--list`, `--plan SLUG`, `--since ISO|<N>d`, `--limit N` (default 20), `--project-dir DIR` (Claude: project slug folder; default derived from `--workspace` or cwd), `--claude-dir DIR` (default `$CLAUDE_CONFIG_DIR/projects` if set, else `~/.claude/projects`), `--brain-dir DIR` (unchanged), `--export-summary`, `--no-snippet`, `--json`. Exit code unchanged: 0 if any row could be read, else 1.
- `--list`: one line per session: `id8 | vendor | started | steps | branch | first prompt (<= 60 chars) | plan slugs mentioned`. `--no-snippet` omits the prompt text.
- `--plan SLUG`: session ids from the ledger, plus cids stored in `.frontier/plans/<slug>/retrospectives.json`, plus (fallback, labeled `inferred`) sessions whose commands mention the slug.
- `--export-summary`: write `.diagnostics/retro/<vendor>-<id8>.json` for each audited session.
- `debug-retro` and `plan_engine.py retrospective|digest` accept `--vendor` and either vendor's id for `--cid`/`--cids`.

**Output contract:** Antigravity-only runs: identical JSON keys and markdown table as today. Any Claude row present: JSON rows gain the new keys; the markdown table gains `vendor` and `tokens` columns. JSON consumers must ignore unknown keys (document it).

**Recipe contract** (`frontier-architect/references/`): `retrospective-recipe.md` (router: selection precedence D3 and shared rules), `retrospective-gemini.md` (the user's existing FOR RETROSPECTIVE structure, preserved: chronological and before/after skill evolution; root-cause matrix of agent mistakes vs tooling bugs vs real product bugs; `LEARNING_SCAFFOLD.md` / `LEARN_QUEUE.md` audit with the `AGENTS.md` size check; plan granularity and master-roadmap alignment; deliverable `learning_proposal.md` with `ask_question`), `retrospective-claude.md` (same five parts in Claude vocabulary: `AskUserQuestion` one decision at a time recommended option first, `Explore` agents for sweeps, the plan artifact as `.TODO/learning_proposal.md` presented with `ExitPlanMode` or a summary, session ids from `CLAUDE_CODE_SESSION_ID`, `CLAUDE.md` size per D8, never `Read` a session `.jsonl`). Both recipes: audit with `transcript-audit`, never load raw logs; propose diffs only; **no edits to skills, rules or the repo before the user decides**.
**Mode:** `/frontier-architect retrospective [--plan SLUG | --cids ...] [--vendor ...] [--recipe ...]`, a one-line router pointer (the router has about 170 bytes of headroom; the text lives in the reference).

## Scenario Combinations Matrix

| Scenario | Command or trigger | Expected result |
| :--- | :--- | :--- |
| Antigravity-only audit (regression) | `... transcript-audit --cids <gemini id>` | Output byte-identical to the golden file captured before the change |
| Claude session audit | `... transcript-audit --cids <claude session id>` | Row with Claude derivations, `vendor: claude`, tokens |
| Id found in both places | same id under both roots | exit 2, message asking for `--vendor` |
| Mixed audit | one gemini id and one claude id | both rows, `vendor` column present |
| List recent Claude sessions | `... transcript-audit --list --vendor claude` | compact lines, 60-char snippets, no raw logs printed |
| Everything for one plan | `... transcript-audit --plan <slug>` | rows for all ledger and retrospective-recorded sessions; inferred ones labeled |
| Session ledger written by hand | Capture Protocol line | `--plan` finds it |
| Ledger written by tool | `plan_engine.py advance` under Claude | line appended with `$CLAUDE_CODE_SESSION_ID`, `inferred:false` |
| Session id unknown | not under Claude, no brain match | no line, one-line notice; never guesses silently |
| Export for later | `--export-summary` | `.diagnostics/retro/claude-<id8>.json` with metrics only |
| Log deleted after export | session file gone | `--plan` uses the exported summary, labeled `from summary` |
| Subagent duplicate read | main thread reads a file a subagent read | counted in `reads_after_subagent` |
| Parallel same-file edits | two `Edit` blocks, same path, one message | `parallel_same_file_edits` 1 |
| Tool failure | `tool_result` with `is_error` | counted in `failures` |
| Unknown or missing keys | record with extra or absent fields | skipped or defaulted; no crash |
| Recipe under Claude | `/frontier-architect retrospective` with `CLAUDECODE=1` | follows `retrospective-claude.md` |
| Recipe under Antigravity | no `CLAUDECODE` | follows `retrospective-gemini.md` |
| Claude agent auditing Antigravity logs | `--vendor gemini --recipe claude` | gemini reader, claude instructions |
| Flags override | `--recipe gemini` under Claude | gemini instructions, noted in the output |

## Milestones (execution order, strictly sequential)

Each milestone ends with: Pre-Flight Critic Gate -> sliced edits -> `diagnose.py audit --path <touched files>` -> `plan_engine.py verify` -> **Review Gate** (fresh reviewer given diff and verify output) -> `advance` -> record the session (Capture Protocol). **No Antigravity-regression allowed:** the existing transcript, debug-retro and plan-digest tests must stay green and unchanged; if a test must change, record why in the child plan. If a milestone exceeds 8 files at its pre-plan gate, split it into `<N>A`/`<N>B`.

## Milestone 1: Vendor layer and Claude transcript reader

- [x] **child plan .TODO/step_1_*.md**: created at the pre-plan gate (~6 files): `system-diagnostics/scripts/transcript_sources.py` (vendor detection per D2, session discovery in both roots, `current_session_id(vendor)` from `CLAUDE_CODE_SESSION_ID`), `transcript_claude.py` (read one session plus its `subagents/` files; yield normalized steps; tolerant of unknown keys), `transcript_router.py` (`audit(cid, vendor, ...)` returning the common row shape; calls the existing Antigravity reader unchanged; a **hook of at most 5 lines** in `transcript_auditor.cmd_transcript_audit`, extracting helpers out first if that would push it past 350 lines), tests `test_transcript_sources.py`, `test_transcript_claude.py` (synthetic fixtures built in the test, **no real transcripts committed**), `test_transcript_router.py` (including the Antigravity golden-output test).

**Verifier**: `python -m unittest discover -s system-diagnostics/tests -p "test_transcript_*.py"` then the four suites.
**Exit criteria:** Claude fixture sessions (with and without subagents) yield normalized steps; precedence rules D2 covered; the Antigravity golden output is unchanged; no raw content printed beyond snippets.

## Milestone 2: Claude checks and metrics

- [x] **child plan .TODO/step_2_*.md**: created at the gate (~5 files): `transcript_claude_checks.py` (the metric derivation table above), `transcript_claude_rows.py` if needed to stay under budget, cue-file loader for `.diagnostics/retro_cues.json` (English cues plus Spanish defaults), tests `test_transcript_claude_checks.py` (one fixture per metric row), `test_transcript_cues.py`.

**Verifier**: `python -m unittest discover -s system-diagnostics/tests -p "test_transcript_*.py"`
**Exit criteria:** every derivation row has a passing fixture test; the row shape equals the Antigravity row plus the documented new keys; markdown and JSON output contracts honored (Antigravity-only output unchanged).

## Milestone 3: Session discovery, ledger, summary export and vendor wiring *(Deferred to Next Turn / Milestone)*

- [ ] **child plan .TODO/step_3_*.md**: created at the gate (about 9 files; likely split **3A** system-diagnostics and **3B** frontier-architect): `transcript_list.py` (`--list`, `--since`, `--plan`, `--export-summary`), `transcript_summary.py` (export and read summaries), `debug_retro.py` (`--vendor`, either id; keep under budget), `frontier-architect/scripts/plan_sessions.py` (ledger writer using `CLAUDE_CODE_SESSION_ID`; one-line hooks in `plan_engine advance` and `retrospective`), `frontier-architect/scripts/plan_transcripts.py` (**extract** `_transcript_rows`, `_resolve_one_cid`, `audit_single_cid`, `_dedupe_cids` out of `plan_digest.py` and route through the vendor router, which brings `plan_digest.py` from 351 to under 350), tests `test_transcript_list.py`, `test_transcript_summary.py`, `test_plan_sessions.py` (frontier-architect), updates to existing digest/retro tests only where the extraction moves code (documented).

**Verifier**: `python -m unittest discover -s system-diagnostics/tests -p "test_*.py"` and `python -m unittest discover -s frontier-architect/tests -p "test_*.py"`.
**Exit criteria:** all `--list/--plan/--since/--export-summary` and ledger scenario rows pass; a deleted-log scenario is served from the summary; Antigravity behavior of `debug-retro`, `retrospective` and `digest` unchanged (existing tests green); `plan_digest.py` under 350 lines.

## Milestone 4: Retrospective recipes and routing *(Deferred to Next Turn / Milestone)*

- [ ] **child plan .TODO/step_4_*.md**: created at the gate (~6 files): `frontier-architect/references/retrospective-recipe.md`, `retrospective-gemini.md`, `retrospective-claude.md`, `frontier-architect/SKILL.md` (**one short line**; the router must stay under 12,000 bytes), `references/phase-protocols.md` pointer, tests (`test_retrospective_recipes.py`: files exist, selection precedence table matches D3, adapter-gating and router-size tests still pass, the Gemini recipe still contains all five parts and `ask_question`), eval pressure case `retrospective-claude-fixture` (a fixture of two synthetic Claude sessions; new skill must produce a `learning_proposal` with the five parts and ask one decision at a time) plus one Antigravity-fixture case to prove no regression.

**Verifier**: `python -m unittest discover -s frontier-architect/tests -p "test_*.py"`
**Exit criteria:** recipe selection follows D3 in tests; both recipes keep the "no edits before the user decides" rule; the A/B pressure eval shows the new skill not worse than baseline; Gemini recipe text unchanged in substance.

## Milestone 5: Calibration on real sessions, docs and sign-off *(Deferred to Next Turn / Milestone)*

- [ ] **child plan .TODO/step_5_*.md**: created at the gate. Run `transcript-audit --plan universal_debug_observation_connector_plan` (and the `intelligent-tracker` sessions with `--project-dir`) on the sessions you collected; review false positives by hand (cue lists, Spanish messages, token notes); tune the cue file and thresholds; run the Claude recipe end to end and compare its proposal against what actually happened; refresh `ARCHITECTURE.md`, `AGENTS.md` and `HARDENING_PLAYBOOK.md`; final sign-off.

**Verifier**: the four suite commands, plus a recorded calibration table (sessions audited, metrics, false positives found and fixed).
**Exit criteria:** zero unexplained flags on the calibration set; a retrospective run on real Claude sessions produced a usable `learning_proposal.md`; the **user has Antigravity check** the Gemini recipe and an Antigravity-only audit (compare against the golden output) and records the result in the child plan. Until that check is recorded the plan is "done except the Antigravity check" (the author cannot run Antigravity from here).

## Risks and Rollback

| Risk | Mitigation |
| :--- | :--- |
| Claude log format changes (undocumented) | Tolerant reader, synthetic fixtures, `version` recorded, failures degrade to "row unreadable" not wrong numbers |
| Old sessions deleted by Claude Code | Capture Protocol, ledger, `--export-summary` summaries |
| Gemini regression | Golden-output test, unchanged existing tests, vendor default `gemini`, additive keys only |
| Wrong vendor guessed | Explicit flags, ambiguity is an error, both-roots check |
| Privacy (logs contain conversation content) | Only compact snippets (60/120 chars), `--no-snippet`, summaries are metrics, nothing raw in context or in git |
| Budget creep in near-limit files | Extractions first; new modules; hooks of one line |
| English-only cue lists miss Spanish corrections | Configurable cue file with Spanish defaults, calibrated in Milestone 5 |
| Ledger per checkout only | Document; run retrospectives from the same checkout; `--plan` also reads `retrospectives.json` |

Rollback per milestone: revert its commit; everything is additive and the default stays Antigravity-compatible.

## Out of Scope

Reading other tools' logs; uploading transcripts anywhere; changing the user's FOR RETROSPECTIVE prompt text in their project (this plan adds recipes inside the skill); automatic skill rewriting (the recipe only proposes diffs).

## Definition of Done

- [ ] All four suites pass; existing transcript, debug-retro and plan-digest tests unchanged and green; Antigravity golden output identical.
- [ ] `diagnose.py audit --path <all new and touched files>` exits 0 (no file over 350 lines, no function over 40); `plan_digest.py` under 350.
- [ ] Every Intent Ledger row (R1-R8) traces to a passing test or doc section.
- [ ] Adapter-gating and router-size tests pass; no new `python skills/...` or Gemini-only strings outside dual-vocabulary lines.
- [ ] Calibration table recorded; the Claude recipe produced a usable proposal from real sessions; the user had Antigravity check the Gemini recipe and an Antigravity-only audit, and the result is recorded.
- [ ] Final sign-off: `diagnose.py scan --path .`, `digest --backfill --write-scaffold`, `diagnose.py changelog add`.
