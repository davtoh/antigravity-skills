# Audit Mode (`/frontier-architect audit <app>`)

> **Running under Claude Code?** Read [`claude-adapter.md`](./claude-adapter.md) first. Vocabulary here is dual: Antigravity term, then the Claude Code equivalent.

Turns what a human logged in the DevTools HUD (observations) into an evidence-based audit and then plans. Observation commands, flags and privacy: `system-diagnostics/references/observations.md`; wire contract and tiers: [`connector-integration.md`](./connector-integration.md). Run commands as `python "<skill_dir>/scripts/diagnose.py" ...` where `<skill_dir>` is the `system-diagnostics` folder.

**Intent gate:** run only on `audit`/"audit this app". A project's own FOR AUDITS prompt wins on section order; this recipe only supplies its inputs. Read-only until the user approves plans; never resolve an observation without a verified fix.

## Steps

1. **Baseline batch** (one turn, no ad-hoc scripts): `diagnose.py brief --run-probes [--pull http://127.0.0.1:<port>]` (add `--pull` only when the app runs with `FRONTIER_DEBUG_OBSERVATIONS=1`). Keep `surface --verify`, `scan`, `audit` and `arch-map` for finer output. A section shown as `UNAVAILABLE (reason)` is reported as **UNVERIFIED**, never as a pass.
2. **Findings**: active observations of kinds `element`, `error`, `network`, `note` (`observations list --json`). Each finding cites its `id`, `selector`, `recording_id` and correlated traces. Extra findings from the tools are added below the observation-derived ones.
3. **Ideas**: kind `idea` (`observations list --kind idea --json`).
4. **Alignment and catalog**: compare against the project's architecture doc (for example `docs/architecture/IDEAL_WORLD_ARCHITECTURE.md`); rank bugs P0 to P2 in a Symptom-to-Root-Cause Matrix. Delegate sweeps of more than 3 to 4 files to a read-only research subagent (`research`, `Model: 'flash'` / Claude: `Explore` agent) and do not re-read what it swept.
5. **Why our tools missed it**: for each bug record `observations triage --id <ID> --root-cause "..." --missed-by tests,surface,... --guard "<upgrade>"`.
6. **Interview**: confirm priorities with the user (`ask_question` / `AskUserQuestion`, 2 to 4 questions, same turn). Unattended: state assumptions in 1 to 2 lines and keep plans as proposals.
7. **Plans**: write `.TODO/<slug>.md` per the plan contract (`RequestFeedback: true` / Claude: `.TODO/<slug>.md` + `ExitPlanMode`), register with `plan_engine.py init`.
8. **After approved fixes**: `/app-debugger` verifies; then `observations resolve --id <ID> --resolution "..." --commit <sha>`.

## Report (Axiom 9)

End with `Verified` / `Not verified` / risks: which sections ran, which were `UNAVAILABLE`, whether the app was reachable (`pull` result), and that no observation data left the machine.
