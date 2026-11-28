# Learning Proposal: Retrospective M1-M3 and Observation M1 (Claude sessions)

Scope: sessions `ada031af` (Retro M1), `48f3c30e` (Retro M2), `c38b1a90` (Retro M3), `d7976ea6` (Observation M1), `eb974282` (accidental `continue`), `18774ef4` (planning session that authored the observation master plan).
Method: `diagnose.py transcript-audit` and `--list` only; no raw transcript was read. Nothing below has been applied; every change waits for a decision.

## 1. Chronology and before/after

| Order | Session | Start (UTC) | Role | Steps | Fails | Subagents | Dup reads | Cap |
| :-- | :-- | :-- | :-- | --: | --: | --: | --: | :-: |
| 1 | `18774ef4` | before 11-26 | planned observation master | 269 | 7 | 38 | 1 | C |
| 2 | `ada031af` | 15:45 | Retro M1 | 22 | 0 | 0 | 0 | A |
| 3 | `48f3c30e` | 16:21 | Retro M2 | 29 | 1 | 1 | 0 | A |
| 4 | `c38b1a90` | 16:41 | Retro M3 | 50 | 1 | 1 | 0 | A |
| 5 | `d7976ea6` | 17:22 | Observation M1 | 19 | 0 | 0 | 0 | A |
| 6 | `eb974282` | 17:29 | extra `continue` | 6 | 0 | 0 | 0 | A |

- `18774ef4` is the earlier planning conversation, not a Step 3 session: its retrospective entry on the Step 3 child plan is misattributed (calibration item 4 resolved).
- Mid-stream skill/rule changes per session: **not verified** (skills were not diffed per session).
- Only `18774ef4` shows an `EnterPlanMode` error and a duplicate read; milestone sessions are clean by these counters.

## 2. Root-cause matrix

| # | Finding | Class | Evidence | Proposed fix |
| :-- | :-- | :-- | :-- | :-- |
| 1 | `python` on this machine is **Python 2.7.16**; `plan_verify` runs the plan's `python ...` verbatim when no venv exists, so every baseline/verify fails (`Exit: 1 (0 passed)` for both master plans; the retrospective master's baseline was `Exit: 0 (80 passed)` before). Also `48f3c30e` step 4 SyntaxError | Tooling bug | `python --version`; `plan_verify.py:100-103` returns `cmd` unchanged without a venv | Fall back to `sys.executable` in `plan_verify._resolve...` + test (SSOT, `frontier-architect/scripts/`) |
| 2 | `plan_engine next <completed child>` still says "Run `advance <master> --milestone 1`" although the master already shows M1 done (auto-sync). It never says the child plan is finished and which prompt to paste next. This is why a second `continue` (`eb974282`) was run | Tooling bug | `next step_1_observation_store_cli` output; master status `[✓] M1 [ff77f72]` | On a completed child whose master milestone is already done, print: `plan complete; master step N+1 active; run /frontier-architect continue <master>` and suppress the stale advance line |
| 3 | `--list` `steps` column counts raw records (200/291/473) while the audit counts tool calls + user turns (22/29/50) | Tooling bug (mine, M3) | `--list` vs audit table | Count steps the audit way, or rename the column `records` |
| 4 | `sed -i` with a macOS-incompatible pattern failed (`c38b1a90` step 44) | Avoidable agent error | audit FAIL line | Use the Edit tool for file edits; already the skill's rule, no new rule |
| 5 | `EnterPlanMode` "not in plan mode" error and an unquoted zsh glob (`18774ef4` steps 16, 206) | Avoidable agent error | audit FAIL lines | none (one-off) |
| 6 | Audit counts `grep` no-match / count output (`...: 0`) as `cmd_fail` (`18774ef4` steps 213, 384, 390 look like this) | Tooling false positive (likely, unverified) | FAIL lines show grep-style output | Calibrate in M5: treat `grep` exit 1 with empty/count output as not a failure |
| 7 | Questions flagged as `CORRECTION` (`c38b1a90` steps 84, 92; probably `18774ef4` step 191) | Tooling false positive | CORRECTION lines | Already in M5 list |
| 8 | CDP fallback flags on `ada031af`, `48f3c30e` | Suspected false positive, unverified | FLAG lines | Already in M5 list |
| 9 | Failures behind `| head`/`| tail` are invisible | Tooling limit | `c38b1a90`: 1 reported, 3 real | Already in M5 list |

No finding in (a) "necessary empirical bug discovery": these were build milestones, not bug hunts.

## 3. Learning scaffold and `/learn` audit

- `AGENTS.md` is 5,603 bytes and `CLAUDE.md` is 11 bytes (an `@AGENTS.md` import): about 5.6 KB, far under the 24,000-byte threshold (D8). No size blocker for rule additions.
- `LEARNING_SCAFFOLD.md` for the Step 3 child plan is 2.3 KB; whether it was polluted by false flags was **not verified**.
- **`/learn` is not available under Claude here.** The closest skill, `learn-from-review`, saves lessons from *PR review comments you wrote*; it is not a general `/learn`. Candidates in the Claude recipe should therefore be written into this proposal and promoted to `AGENTS.md` or memory only after your decision (see Decision 1).

## 4. Granularity and master-roadmap alignment

- Audit steps per milestone: 22, 29, 50, 19. Against the Gemini-era target (~40-90 steps) four of five look small, but the Claude step definition (tool calls + user turns) is not the same unit as Antigravity's, so **do not conclude "undersized" yet**; recalibrate the 60/100/140 grade thresholds in M5.
- Pending git state: Retro **M3 is implemented but uncommitted**, together with the M5 calibration-list edit. Observation M1 is committed (`ff77f72`).
- Next steps: observation master **M2 (HUD)** is active; retrospective master **M4 (recipes)** is next. Whether M2 should be split was not evaluated.

## 5. Decisions (asked one at a time, recommended first)

1. How should the Claude retrospective recipe handle `/learn` candidates? (recommended: collect them in `learning_proposal.md`, promote to `AGENTS.md`/memory after your decision; do not depend on `learn-from-review`)
2. Apply fix 1 (`sys.executable` fallback in `plan_verify`)?
3. Apply fix 2 (completion message and stale advance line in `plan_engine next`)?
4. Apply fix 3 (`--list` steps column)?
5. Keyword: `/frontier-architect retrospective [--plan SLUG | --cids ...]` as already planned in M4; your prompt becomes `retrospective-gemini.md` with only the `/learn` wording changed per Decision 1.

## Outcome (2026-11-26)

All five decisions were answered as recommended. Applied: fix 1 (`plan_verify` interpreter fallback, 154+ tests green), fix 2 (`plan_handoff.py`, `next` hand-off message, `test_plan_handoff.py`), fix 3 (`--list` steps use the audit definition). Decisions 1 and 5 are recorded in Milestone 4 of `retrospective_claude_support_plan.md`. Still open: findings 6-9 (calibration in M5); committing the working tree.
