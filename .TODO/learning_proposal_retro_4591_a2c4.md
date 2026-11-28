# Learning Proposal: Retrospective of sessions 4591654c and a2c46284 (Claude)

Scope: `4591654c-651e-4cd1-aec3-911b24ea3c57` (Retro M4; the id in the request was one character short, resolved by prefix) and `a2c46284-616b-4e45-93aa-65f0aec9d3b7` (Retro M5 start). "Any pending": every other Claude session on this branch is already covered by `learning_proposal_retro_m1_3_obs_m1.md` or `learning_proposal_retro_m5.md`; the only uncovered one is the current session `11c409e0`, which is still running and is excluded. This pass completes Parts 3 and 4, which `learning_proposal_retro_m5.md` skipped. Source: `diagnose.py transcript-audit --vendor claude --cids 4591654c a2c46284` and `--list`. No raw `.jsonl` was read.

## Part 1. Chronology

| Order | Session | Start (UTC) | Role | Steps | Fails | Subagents | Dup reads | Cap |
|---|---|---|---|---:|---:|---:|---:|:--:|
| 1 | `4591654c` | 17:53 | Retro M4 (advance + retrospective logged 17:55) | 22 | 1 | 0 | 0 | A |
| 2 | `a2c46284` | 18:07 | Retro M5 (advance logged 18:20) | 47 | 1 | 0 | 0 | A |

Skill/rule changes made during each session were not diffed: **UNVERIFIED**.

## Part 2. Root-cause matrix

| # | Finding | Class | Evidence | Proposed fix |
|---|---|---|---|---|
| 1 | `plan_engine.py` run with bare `python` (Python 2.7.16 here) fails with SyntaxError. **Recurrence:** now 4 sessions (`48f3c30e`, `4591654c`, `a2c46284`, and this one at its first command, `diagnose.py`). Verified. | Tooling bug (docs) + environment | FAIL: 4591654c step 6, a2c46284 step 5; `python --version` = 2.7.16, `python3` = 3.14.7 | **Revised after user feedback:** do NOT hard-code `python3` (absent on Windows, where `python` is Python 3). Add one "pick the interpreter" rule to `claude-adapter.md` and `cli-cheatsheet.md`: use the first of `python3`, `python`, `py -3` that passes `<py> -c "import sys; sys.exit(sys.version_info < (3, 10))"`, then use that as `<py>` in every command. Optional: scripts fail fast with a clear "needs Python 3.10+" message. |
| 2 | The `sys.executable` fallback proposed earlier **did ship** (`frontier-architect/scripts/plan_verify.py:49-50`, verified by grep). It only covers commands the scripts launch themselves. The first, docs-driven command the agent types (`python ".../plan_engine.py" ...`) has no interpreter resolution anywhere. I found no existing recipe for that step (grep of skill docs and scripts). | Tooling gap | grep results; FAIL lines above | See revised fix in #1. |
| 3 | 1 piped (`\| head/tail`) command hid a failing exit code in `a2c46284` | Tooling limitation (mitigated by `masked_failures` note) | NOTE line | None. |
| 4 | Neither session shows duplicate reads, subagent overuse, or `EnterPlanMode` errors | Positive | audit counters | None. |

No real product bugs found in these two sessions.

## Part 3. Learning scaffold and `/learn` audit

- `LEARNING_SCAFFOLD.md` does not exist at the repo root. Per-plan scaffolds live in `.frontier/plans/<slug>/`; I did not open them.
- `.frontier/LEARN_QUEUE.md`: lists 16 plans. Every candidate section reads "none". Two entries are noise rather than plans: `learning_proposal_retro_m5` and `learning_proposal_retro_m1_3_obs_m1` appear as `in_progress 0/0` (proposal files picked up as plans). **Proposed:** exclude `learning_proposal*` from `discover`/queue.
- `retrospective_claude_support_plan` shows `completed 5/5`, Retro count 3. `step_1_observation_store_cli` is completed.
- `/learn` candidates (proposal only, nothing promoted):
  1. "Use `python3`, not `python`, on this machine" (finding 1). Fits memory or the `AGENTS.md` verification section.
  2. Prefer the Edit tool over `sed -i`; quote zsh globs (carried over from the M5 proposal, finding 5).
- Rules-file size check: `CLAUDE.md` is 11 bytes (the `@AGENTS.md` import); `AGENTS.md` is 5,919 bytes. Both are far below the 24,000 byte limit, so rule additions are safe.

## Part 4. Plan granularity and master-roadmap alignment

- `retrospective_claude_support_plan` completed 5 of 5 milestones in 5 sessions. Retro M4 took 22 steps and M5 took 47. M5 is the largest because calibration on real sessions was done there. No split needed.
- Prior proposals already flagged the extra accidental `continue` (`eb974282`) and the stale `next` hint on a completed child plan. Whether that `next` hint was fixed: **UNVERIFIED**.
- `universal_debug_observation_connector_plan` is 1/6; its M2 is the next unit of work.
- Suggestion: add one line to the handoff prompt of each milestone naming the Python interpreter, to avoid repeat #1.

## Verified / Not verified / Risks

- **Verified:** audit counters for both sessions, the Python 2 versus 3 environment, the existence and size of the files named above.
- **Not verified:** per-session skill diffs; whether the `plan_verify` fallback shipped; contents of `.frontier/plans/*/LEARNING_SCAFFOLD.md`; whether the stale `next` hint was fixed.
- **Risks:** leaving docs on `python` makes every fresh session on this machine fail its first command.

## Decisions for the user (nothing applied yet)

1. Add the cross-platform "pick the interpreter" rule (finding 1; replaces the earlier plain `python3` idea)? Recommended.
2. Exclude `learning_proposal*` files from plan discovery / the learn queue?
3. Promote the two `/learn` candidates to `AGENTS.md` or memory?

## Decisions taken
1. Interpreter rule: **applied** to `frontier-architect/references/claude-adapter.md` and `cli-cheatsheet.md` (docs only; frontier-architect suite: 165 tests OK).
2. Exclude `learning_proposal*` from plan discovery / learn queue: **approved, not yet implemented** (follow-up turn: SSOT change plus a test).
3. `/learn` candidates: candidate 1 saved to memory (`feedback-shell-edit-and-globs`); candidate 2 not promoted (already in the docs).
