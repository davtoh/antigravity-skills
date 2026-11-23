# Claude Code Adapter

This skill was authored in Antigravity (Gemini) vocabulary. When running under Claude Code (Sonnet, Opus or Ultra), translate every tool or path name below. The *behavior* of each gate is unchanged; only the mechanism differs.

## Tool mapping

| Antigravity term in these docs | Claude Code equivalent |
| :--- | :--- |
| `ask_question` | `AskUserQuestion` (2–4 structured questions, same turn; Zero-Dangling-Question Invariant still applies) |
| `run_command` / `WaitMsBeforeAsync` | `Bash`; for long suites use `run_in_background: true` and read the result on completion (no polling) |
| `manage_task kill` (daemon teardown) | `TaskStop` / kill the background `Bash` before ending the turn |
| `view_file` / `read_file` | `Read` (use `offset`/`limit`; locate with `Grep` first) |
| `edit_file` | `Edit` (never parallel edits to one file) |
| `research` subagent, `Model: 'flash'` | `Agent` with `subagent_type: Explore` (cheap, read-only fan-out); set `model: "haiku"` or `"sonnet"` when the task is pure search |
| Planning subagent | `Agent` with `subagent_type: Plan` |
| `enter_plan_mode` / `exit_plan_mode` | `EnterPlanMode` / `ExitPlanMode`. Still **never** call them on a `continue` of an existing plan |
| Plan artifact with `RequestFeedback: true` | Write `.TODO/<slug>.md` (the durable copy) and present it with `ExitPlanMode` or a short chat summary; skip the second `<appDataDir>/brain/...` copy |
| `<appDataDir>/brain/<conversation-id>/` (scratch, SPIKEs) | `.frontier/scratch/<slug>/` in the workspace (git-ignored by `plan_engine`) |
| `search_marketplace` | `ToolSearch` and the connected MCP list |
| `AGENTS.md` / `.agents/rules/` | `CLAUDE.md` (a one-line `@AGENTS.md` import keeps one source of truth) |
| "no interactive user" / `/goal` / subagent mode | Headless `claude -p`, `/loop`, cron or any subagent: state assumptions in 1–2 lines, keep destructive actions as proposals |
| `/boost`, `Opus`/`Neon` escalation | Switch tier per [`reasoning-harness.md`](./reasoning-harness.md#5-tier-escalation-which-model-tier-does-what) (`/model`) |
| `TaskCreate` | Optional mirror of `plan_engine.py next` tasks for visibility; `plan_engine.py` stays the source of truth for status |

## Script paths

Never assume the repo sits at `./skills/`. Resolve scripts relative to this skill's folder:

- `<skill_dir>` = the directory containing `SKILL.md` (Claude: `.claude/skills/frontier-architect/` or `~/.claude/skills/frontier-architect/`; monorepo: `skills/frontier-architect/`).
- `python "<skill_dir>/scripts/plan_engine.py" status`
- The shared diagnostics engine is found automatically by the shims (`SYSTEM_DIAGNOSTICS_DIR` env, sibling folder, `.claude/skills/`, `~/.claude/skills/`, then legacy `~/.gemini/...`).

## Context budget

Do not read `.TODO/` plans, `evals/` or `tests/` unless the task is about them. Use `plan_engine.py status` / `next` instead of opening a plan file.
