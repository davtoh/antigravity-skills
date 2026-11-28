# Learning Proposal: Retrospective Claude Support M5 (calibration run)

Scope: sessions `ada031af` (M1), `48f3c30e` (M2), `c38b1a90` (M3), `d7976ea6`, `eb974282`, `18774ef4`, `4591654c`, `a2c46284` (M5 start). Produced by running `retrospective-claude.md` (Part 1 and 2 via `transcript-audit --plan` and `--list`); Parts 3 and 4 not run in this pass.

## Root-cause matrix

| # | Finding | Class | Evidence | Proposed fix |
|---|---|---|---|---|
| 1 | User questions flagged as CORRECTION | tooling false positive | c38b1a90 step 92 | Fixed in M5 (question gate, pasted-content strip incl. unclosed tags) |
| 2 | `no-brain`, quoted prompt text flagged | tooling false positive | 18774ef4 steps 358, 495 | Fixed in M5 (hyphen boundary, `\Z` paste strip) |
| 3 | CDP fallback counted from Read/heredoc | tooling false positive | ada031af, 48f3c30e | Fixed in M5 (real runs only) |
| 4 | `python` is Python 2 here: `plan_engine.py` SyntaxError | agent mistake / environment | 48f3c30e step 4, 4591654c step 6, a2c46284 step 5 | Proposal: skill docs and cheatsheet say `python3`; decide with user |
| 5 | BSD `sed -i` misuse, zsh glob `--include=*.md` | agent mistake | c38b1a90 step 44, 18774ef4 step 206 | Proposal: prefer Edit tool / quote globs (candidate `/learn`) |
| 6 | `--plan` lists nearly every plan per session (ledger attribution loose) | tooling bug (minor) | `--list` output | Optional: rank by mention count; not done |
| 7 | `fails` is a floor under `\| head/tail` | tooling limitation | c38b1a90, 18774ef4 | Mitigated: `masked_failures` note |

## Comparison with what happened
The recipe ran on Claude without reading raw `.jsonl`, and its table matches the milestone history (M1 to M3 grade A/B, planning session C). Mid-stream skill diffs per session: **not verified**.

## Decisions for the user (nothing applied yet)
1. Change docs to say `python3` (finding 4)?
2. Promote finding 5 to `AGENTS.md` / memory?
3. Rank `--plan` attribution by mentions (finding 6)?
