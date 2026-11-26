# Step 3: Session discovery, ledger, summary export and vendor wiring

Parent: `.TODO/retrospective_claude_support_plan.md#milestone-3` (Master Step 3). Split per the master plan: **3A** system-diagnostics, **3B** frontier-architect.

## Architectural Pre-Flight
- Invariants: Antigravity-only output stays byte-identical (D4); `transcript_auditor.py` is at 349 lines so `cmd_transcript_audit` is *replaced* by a short delegate (net lines down); `plan_digest.py` 351 -> under 350 via extraction.
- Flow: `transcript-audit --list/--plan/--since/--export-summary` -> `transcript_list.run_cli` -> router `audit()`; summaries in `.diagnostics/retro/<vendor>-<id8>.json` (metrics only, strings <= 120 chars); a missing log falls back to the summary (`from_summary: true`).
- Edge cases: unreadable/missing logs, malformed ledger lines, plan with no sessions, ambiguous id, no session id outside Claude (no line, one-line notice).
- Verifier: `python -m unittest discover -s system-diagnostics/tests -p "test_*.py"` and `python -m unittest discover -s frontier-architect/tests -p "test_*.py"`.

## 3A system-diagnostics
- [ ] **system-diagnostics/scripts/transcript_summary.py**: export/read metrics-only summaries (D7).
- [ ] **system-diagnostics/scripts/transcript_list.py**: `--list`, `--since`, `--plan`, `--export-summary`, `run_cli`.
- [ ] **system-diagnostics/scripts/transcript_auditor.py**: `cmd_transcript_audit` delegates to `run_cli` (net line decrease).
- [ ] **system-diagnostics/scripts/debug_retro.py**: `--vendor`, either vendor's id for `--cid` (via router).
- [ ] **system-diagnostics/tests/test_transcript_list.py**, **test_transcript_summary.py**, debug-retro vendor test.

## 3B frontier-architect
- [ ] **frontier-architect/scripts/plan_sessions.py**: ledger writer (`CLAUDE_CODE_SESSION_ID`), hooks in `advance` and `retrospective`.
- [ ] **frontier-architect/scripts/plan_transcripts.py**: extract `_transcript_rows`, `_resolve_one_cid`, `audit_single_cid`, `_dedupe_cids`; route via router.
- [ ] **frontier-architect/tests/test_plan_sessions.py**.
