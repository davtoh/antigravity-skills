# Audit Mode (`/frontier-architect audit <app>`)

> **Running under Claude Code?** Read [`claude-adapter.md`](./claude-adapter.md) first. Vocabulary here is dual: Antigravity term, then the Claude Code equivalent.

Turns what a human logged in the DevTools HUD (observations) into an evidence-based audit and then plans. Observation commands, flags and privacy: `system-diagnostics/references/observations.md`; wire contract and tiers: [`connector-integration.md`](./connector-integration.md). Run commands as `python "<skill_dir>/scripts/diagnose.py" ...` where `<skill_dir>` is the `system-diagnostics` folder.

**Intent gate:** run only on `audit`/"audit this app". A project's own FOR AUDITS prompt wins on section order; this recipe only supplies its inputs. Read-only until the user approves plans; never resolve an observation without a verified fix.

## Steps

1. **Baseline batch** (one turn, no ad-hoc scripts): `diagnose.py brief --run-probes [--pull http://127.0.0.1:<port>]` (add `--pull` only when the app runs with `FRONTIER_DEBUG_OBSERVATIONS=1`). Keep `surface --verify`, `scan`, `audit` and `arch-map` for finer output. A section shown as `UNAVAILABLE (reason)` is reported as **UNVERIFIED**, never as a pass.
2. **Findings**: active observations of kinds `element`, `error`, `network`, `note` (`observations list --json`). Each finding cites its `id`, `selector`, `recording_id` and correlated traces. Extra findings from the tools are added below the observation-derived ones.
3. **Ideas**: kind `idea` (`observations list --kind idea --json`).
4. **Alignment and catalog**: locate and read the project's current-state and target-state architecture docs if present (for example `docs/architecture/CURRENT_ARCHITECTURE.md` and `IDEAL_WORLD_ARCHITECTURE.md`, or `ARCHITECTURE.md` / `AGENTS.md`; if none exist, note `no architecture docs found` and baseline from `diagnose.py arch-map`). Rank bugs P0 to P2 in a Symptom-to-Root-Cause Matrix. Delegate deep cross-layer verification (`> 3–4` files) to 2–3 parallel read-only subagents (`research`, `Model: 'flash'` / Claude: `Explore` agent) across: (a) runtime/concurrency/locks/resources, (b) domain/storage/parity vs target architecture, and (c) frontend/API contracts & UI layout; do not re-read what they swept.
5. **Why our tools missed it**: for each bug record `observations triage --id <ID> --root-cause "..." --missed-by tests,surface,... --guard "<upgrade>"`.
6. **Interview**: confirm priorities with the user (`ask_question` / `AskUserQuestion`, 2 to 4 questions, same turn). Note briefly that Step 7 (Docs & Plans) runs right after these answers resolve—and that if running on a fast/executor tier, now is the optimal seam to switch to a Planner/Reviewer tier (e.g., Neon/Opus) before replying. Unattended: state assumptions in 1 to 2 lines and keep plans as proposals.
7. **Docs & Plans (only after interview decisions resolve)**: update existing current/target architecture docs (if used in step 4) and `AGENTS.md` (keeping `< 24 KB`), then write the Master Roadmap + Step 1 child plan (`.TODO/<slug>.md`, `RequestFeedback: true` / Claude: `ExitPlanMode`), register via `plan_engine.py init`, and hand off with `/frontier-architect continue <step_1_slug>`.
8. **After approved fixes**: `/app-debugger` verifies; then `observations resolve --id <ID> --resolution "..." --commit <sha>`.

## Report (Axiom 9)

End with `Verified` / `Not verified` / risks: which sections ran, which were `UNAVAILABLE`, whether the app was reachable (`pull` result), and that no observation data left the machine.
