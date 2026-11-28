# Learning Proposal: Retrospective of Remaining 6 Claude Sessions

Scope: `11c409e0`, `0ca65d56`, `fcd392df`, `50a98de6`, `666ab17a`, `1b9ec22c` (all 2026-11-26, branch `feature/add-debug-connectors`). Produced via `retrospective-claude.md` using `diagnose.py transcript-audit --vendor claude` (`--cids`, `--list`, `--json`). No raw `.jsonl` was read. Parts 3 and 4 are light (see below). Nothing in skills, rules, `AGENTS.md` or `CLAUDE.md` was edited.

## Part 1. Chronology (audit data only)

| Order | cid | Started (UTC) | Role (from `--list` prompt) | Steps | Fails (floor) | Subagents | Grade cap |
|---|---|---|---|---:|---:|---:|:-:|
| 1 | 11c409e0 | 18:25 | `/frontier-architect retrospective` of earlier conversations | 36 | 2 | 0 | B |
| 2 | 0ca65d56 | 18:42 | `/frontier-architect continue plan universal_debug...` | 40 | 1 (+3 masked) | 2 | A |
| 3 | fcd392df | 19:13 | continue plan (next milestone) | 27 | 2 | 1 | B |
| 4 | 50a98de6 | 19:23 | continue plan (next milestone) | 31 | 0 | 0 | A |
| 5 | 666ab17a | 19:31 | continue universal_debug... | 28 | 2 (+1 masked) | 0 | B |
| 6 | 1b9ec22c | 19:40 | continue universal_debug... | 67 | 2 (+1 masked) | 0 | B |

All six show zero user corrections, zero workflow redirects, zero CDP fallbacks, zero parallel same-file edits. None recorded a commit hint or a continuous-learning block (`has_commit_hint` / `has_learning_block` false for all). Whether that is expected for these sessions: **UNVERIFIED** (per-session skill diffs were not made).

## Part 2. Root-cause matrix

| # | Finding | Class | Evidence | Proposed fix |
|---|---|---|---|---|
| 1 | `python ... plan_engine.py discover` raises SyntaxError because bare `python` is Python 2 here. Same issue as finding 4 in `learning_proposal_retro_m5.md`; **still recurring** in 3 of 6 sessions | agent mistake / environment (recurring) | 0ca65d56 step 3, fcd392df step 3, 666ab17a step 3 | Make `python3` the documented default in `frontier-architect/SKILL.md` Phase 0 and `cli-cheatsheet.md`, or resolve `<py>` once per session per `claude-adapter.md` |
| 2 | zsh `no matches found` for unquoted globs (`.venv*`, `connector_bridge*.py`) | agent mistake (recurring; a memory entry already exists) | 11c409e0 step 13, fcd392df step 12 | Memory `feedback-shell-edit-and-globs` is not preventing it; promote one line to `AGENTS.md` section 3 (or use `Glob`/`ls` with `2>/dev/null`) |
| 3 | `sleep 60; cat ...` blocked by the harness | agent mistake | 1b9ec22c step 106 | Use `run_in_background` or `Monitor` until-loop (already in tool guidance); add to `/learn` candidates |
| 4 | Tool use rejected by the user (`git log --stat -2 \| head`, an unspecified tool call) | not an agent defect without more context | 666ab17a step 58, 1b9ec22c step 12 | None. Counted as `fails` by the auditor; consider the auditor labeling user rejections separately (tooling false positive on grade) |
| 5 | `cd <projects dir>` exit 1 | unclear, **UNVERIFIED** | 11c409e0 step 58 | Likely a non-existent path while locating sessions; no fix proposed |
| 6 | Piped `\| head/tail` hid failing exit codes | tooling limitation (already surfaced as `masked_failures`) | 0ca65d56 (3), 666ab17a (1), 1b9ec22c (1) | None; the floor note already works |
| 7 | `universal_debug_observation_connector_plan.md` read twice | agent mistake (minor) | 50a98de6 | Zero-Plan-Re-Read Gate: use `plan_engine.py status/next`; no change needed to docs |
| 8 | 1b9ec22c used 8.4M cached tokens over 67 steps | informational | 1b9ec22c | Evidence the milestone was large (see Part 4) |

## Part 3. Learning scaffold and `/learn` audit

- `LEARNING_SCAFFOLD.md` and `LEARN_QUEUE.md` do not exist in this repo, so there is nothing stale to audit.
- Rules-file size (D8, 24,000 bytes): `CLAUDE.md` is 11 bytes (an `@AGENTS.md` import), `AGENTS.md` is 6,403 bytes, so there is plenty of room.
- `/learn` candidates (proposal only, not promoted):
  1. Use `python3` for skill scripts on this macOS machine.
  2. Quote or avoid shell globs in zsh; prefer `Glob`.
  3. Never `sleep N; cat` to wait; use background run or `Monitor`.

## Part 4. Plan granularity and master-roadmap alignment

- Session 6 (67 steps, 15 planner turns) is about double the others (27 to 40 steps). That milestone was probably too big for one turn. Whether it matches the 1-Phase-Per-Turn rule is **UNVERIFIED**, because I did not diff the plan file per session.
- Sessions 2 to 6 are consecutive `continue` runs of the same master plan, and the git log (M4, M5, M6A, M6B) matches that sequence. This is consistent with the roadmap but not independently checked.
- Suggestion: for milestones that can exceed about 50 steps, split into A/B sub-milestones up front, as M6A/M6B already did.

## Verified / Not verified
- **Verified:** audit table and failure lines above (ran `transcript-audit`, saw output); `CLAUDE.md`/`AGENTS.md` sizes; absence of scaffold files.
- **Not verified:** per-session skill/rule diffs, session roles beyond the truncated `--list` prompt, the cause of 11c409e0 step 58, absence of commit hints.

## Decisions for the user (nothing applied yet)
1. ~~Switch docs to `python3`~~ **Decided differently: launcher pair. Applied & Verified on Windows + Gemini.** The user noted Windows lacks `python3` (or hits the Microsoft Store stub). Added `frontier-architect/scripts/py.sh` and `py.cmd`, pointed `SKILL.md` Phase 0, `phase-protocols.md`, `claude-adapter.md`, and `cli-cheatsheet.md` at them (`& "<skill_dir>/scripts/py.cmd"` for PowerShell), and added `.gitattributes` (`*.sh text eol=lf`, `*.cmd text eol=crlf`) plus `.sh` LF normalization in `skill_packager.py`. **Windows follow-up fixes:** fixed eager `%errorlevel%` expansion inside `py.cmd` parenthesized blocks (which previously returned exit `0` when scripts exited non-zero), added `$VIRTUAL_ENV` precedence and `python`-before-`python3` probe order on Windows, trimmed `SKILL.md` so CRLF byte length stays `< 12,000` (`test_retrospective_recipes.py`), and added `PyCmdLauncherTests` in `tests/test_py_launcher.py` + Eval 30.
2. ~~Promote the zsh-glob and `sleep` rules~~ **Applied** to `AGENTS.md` section 3 (rules 8, 9, and 10—updated for dual-vendor Antigravity `WaitMsBeforeAsync` + Claude `run_in_background`/`Monitor`, `.venv` precedence, and Windows PowerShell `& "<skill_dir>/scripts/py.cmd"`).
3. ~~Label user-rejected tool calls separately~~ **Applied across both Claude and Gemini.** Centralized `is_user_rejected` in `transcript_checks.py`, recorded `"user_rejected"` on full `tool_result` text in `transcript_claude.py` (fixing multi-line user rejection reasons dropped by `failure_snippet`), and wired `user_rejected` into `transcript_auditor.py` (preserving D4 legacy keys when `0`, emitting `- NOTE` and excluding from `total_failures` / `suggested_grade_cap` when `>= 1`) + Eval 21.
