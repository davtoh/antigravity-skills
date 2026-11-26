# Debug Observation Connector: Integration Notes for Plans

> **Running under Claude Code?** Read [`claude-adapter.md`](./claude-adapter.md) first. Gemini terms below name their Claude equivalent.

Use when a plan or audit touches an app that exposes (or should expose) the debug observation connector. The contract lives in `system-diagnostics/references/observation-connector-contract.md`; this file only says how planning work uses it.

## Who does what

| Piece | Owner |
| :--- | :--- |
| HUD, store, `observations`, `pull`, `verify-connector`, `brief` | `system-diagnostics` skill (`python "<skill_dir>/scripts/diagnose.py" ...`) |
| Routes under `/api/diagnostics`, behind `FRONTIER_DEBUG_OBSERVATIONS=1`, loopback only | The app (Tier A: scaffold `traces --scaffold fastapi --dest <dir> --with-observations`; Tier B: any language, by hand) |
| Audit workflow and plans | This skill ([`audit-recipe.md`](./audit-recipe.md)) |

## Planning rules

- An app-side plan copies the wire contract verbatim and never redefines it; on a conflict the skill repo's contract wins. Record the chosen tier.
- Gate every plan task that adds routes: flag off means 404, non-loopback means 403, redaction tested, `.diagnostics/` gitignored.
- Verifier for any connector work: `observations verify-connector --url http://127.0.0.1:<port>` (all `PASS`; the loopback check may show `SKIP`). A `FAIL` or unreachable app is `UNVERIFIED`, not done.
- WebSocket frames are out of scope for contract v1; say so in plans for WebSocket-heavy apps.
- Never plan to sync observations off the machine; `pull` is loopback-only unless the user explicitly passes `--allow-remote`.

## Vocabulary

| Antigravity | Claude Code |
| :--- | :--- |
| `ask_question` | `AskUserQuestion` |
| `research` subagent, `Model: 'flash'` | `Agent` with `subagent_type: Explore` |
| `RequestFeedback: true` plan artifact | `.TODO/<slug>.md` + `ExitPlanMode` |
| `run_command` | `Bash` |
