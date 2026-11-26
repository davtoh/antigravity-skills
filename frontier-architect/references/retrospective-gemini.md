# Retrospective Recipe: Gemini / Antigravity

> Running under Claude Code? Read [`claude-adapter.md`](./claude-adapter.md) first, then use [`retrospective-claude.md`](./retrospective-claude.md) instead. This file keeps the Antigravity vocabulary (`ask_question`, `research`, `RequestFeedback`) of the user's FOR RETROSPECTIVE prompt, unchanged in substance. Shared rules: [`retrospective-recipe.md`](./retrospective-recipe.md).

Inputs: plan slug or conversation ids (`--plan SLUG | --cids ID...`). Session ids come from the brain folder names.

## Part 1. Chronology and before/after skill evolution

Run `diagnose.py transcript-audit --plan <slug>` (or `--cids`), `--list` to find sessions. Order sessions by start time; for each give role, steps, failures, subagents, duplicate reads. Note skill/rule changes between sessions; mark any not diffed as **not verified**. Delegate sweeps of more than 3 to 4 files to a `research` subagent (`Model: 'flash'`) and wait for its `SYSTEM_MESSAGE`.

## Part 2. Root-cause matrix

Table: `# | Finding | Class | Evidence | Proposed fix`. Class is one of **agent mistake**, **tooling bug**, **real product bug**, **tooling false positive**. Evidence is a step number from the audit, never a raw log excerpt.

## Part 3. Learning scaffold and `/learn` audit

Audit `LEARNING_SCAFFOLD.md` and `LEARN_QUEUE.md`: stale, duplicate or polluted entries (false flags). Check the `AGENTS.md` size against the 24,000-byte threshold before proposing any rule addition. Keep `/learn` handling as the user wrote it.

## Part 4. Plan granularity and master-roadmap alignment

Were milestones sized right (steps per session, handoff prompts used)? Does the master roadmap still match what was built? Propose splits or merges as diffs.

## Part 5. Deliverable

Write `learning_proposal.md` (artifact with `RequestFeedback: true`; if it already exists use a suffixed name) containing parts 1 to 4 and a numbered list of proposed changes as diffs. Then call `ask_question` once per decision, recommended option first. **Do not edit skills, rules or the repo before the user decides.**
