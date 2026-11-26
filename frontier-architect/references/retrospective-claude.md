# Retrospective Recipe: Claude Code

> Claude Code vocabulary. Adapter: [`claude-adapter.md`](./claude-adapter.md). Shared rules and the five parts: [`retrospective-recipe.md`](./retrospective-recipe.md). The Antigravity twin is [`retrospective-gemini.md`](./retrospective-gemini.md).

Inputs: `--plan SLUG` or `--cids ID...` (Claude session ids; the current one is `$CLAUDE_CODE_SESSION_ID`, recorded in `.frontier/sessions.jsonl`). Pass `--vendor` when the id could be either vendor.

## Part 1. Chronology and before/after skill evolution

Run `diagnose.py transcript-audit --plan <slug>` (or `--cids`) and `--list` with `Bash`. **Never `Read` a session `.jsonl`.** Order sessions by start time; give role, steps, failures, subagents, duplicate reads. Skill/rule changes not diffed per session are **not verified**. Delegate sweeps of more than 3 to 4 files to `Agent` with `subagent_type: Explore` and wait for its notification.

## Part 2. Root-cause matrix

Table: `# | Finding | Class | Evidence | Proposed fix`. Class: **agent mistake**, **tooling bug**, **real product bug**, **tooling false positive**. Evidence is an audit step number only.

## Part 3. Learning scaffold and `/learn` audit

Audit `LEARNING_SCAFFOLD.md` and `LEARN_QUEUE.md` for stale or polluted entries. Collect `/learn` candidates **in the proposal file only**; promote them to `AGENTS.md` or memory only after the user decides. Do not use `learn-from-review` (it learns from PR review comments only). Check the `CLAUDE.md` size per D8 (24,000 bytes; follow the `@AGENTS.md` import) before proposing rule additions.

## Part 4. Plan granularity and master-roadmap alignment

Were milestones sized right (steps per session, handoff prompts used)? Does the master roadmap match what was built? Propose splits or merges as diffs.

## Part 5. Deliverable

Write `.TODO/learning_proposal.md`; if it exists, write `.TODO/learning_proposal_<scope>.md` (never overwrite). Present it with `ExitPlanMode` or a short chat summary. Then ask each decision with `AskUserQuestion`, **one decision at a time, recommended option first** (Zero-Dangling-Question Invariant applies). **No edits to skills, rules, `AGENTS.md`, `CLAUDE.md` or the repo before the user decides.**
