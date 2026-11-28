# Retrospective Recipe Router

> Running under Claude Code? Read [`claude-adapter.md`](./claude-adapter.md) first. This router only picks a recipe; it holds no vendor vocabulary beyond the table below.

Invoked by `/frontier-architect retrospective [--plan SLUG | --cids ID...] [--vendor ...] [--recipe gemini|claude]`.

## 1. Recipe selection precedence (D3)

| Priority | Source | Result |
| :-- | :-- | :-- |
| 1 | `--recipe <name>` | that recipe |
| 2 | env `RETROSPECTIVE_RECIPE` | that recipe |
| 3 | runtime: `CLAUDECODE=1` | `claude` |
| 4 | anything else | `gemini` |

The recipe follows the **runtime**, not the logs: a Claude session may audit Antigravity logs (`--vendor gemini`) and still use the Claude recipe.

- Gemini / Antigravity runtime: follow [`retrospective-gemini.md`](./retrospective-gemini.md).
- Claude Code runtime: follow [`retrospective-claude.md`](./retrospective-claude.md).

## 2. Shared rules (both recipes)

1. **Audit, never load raw logs.** Start with `diagnose.py transcript-audit` (and `--list` to find sessions). Never read a session `.jsonl` or brain folder directly.
2. **Propose diffs only.** The deliverable is `learning_proposal*.md`; **no edits to skills, rules, `AGENTS.md`, `CLAUDE.md` or the repo before the user decides.**
3. **Surface the proposal before asking, one decision at a time, and close with open review.** Output the clickable link to `learning_proposal*.md` plus a 2–3 line summary in visible chat before/alongside invoking the question tool (naming the proposal filename in the first question) so the user never has to hunt for the artifact. Ask one decision per question, recommended option first, and **always end with a final open-review question** (`"Any additional observations, corrections to the learning proposal, or extra requests before we proceed?"`).
4. **Honest reporting (Axiom 9):** label every finding `Verified` or `UNVERIFIED`; call out tooling false positives instead of blaming the agent.
5. Never overwrite an existing `learning_proposal.md`; use a suffixed name (`learning_proposal_<scope>.md`).

## 3. The five parts (same in both recipes)

1. Chronology and before/after skill evolution.
2. Root-cause matrix: agent mistakes vs tooling bugs vs real product bugs.
3. Learning scaffold audit (`LEARNING_SCAFFOLD.md`, `LEARN_QUEUE.md`, `/learn` candidates) with the rules-file size check.
4. Plan granularity and master-roadmap alignment.
5. Deliverable `learning_proposal*.md` plus the decision questions.
