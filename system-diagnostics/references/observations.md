# Debug Observations: Workflow, Audit Hand-off & Privacy

Observations are what a human sees while testing an app (picked elements, recorded sessions, errors, ideas), logged through the DevTools HUD and stored in `.diagnostics/`. Wire format and routes: [`observation-connector-contract.md`](./observation-connector-contract.md). Flags: [`cli-reference.md`](./cli-reference.md).

Run every command as `python "<skill_dir>/scripts/diagnose.py" ...` where `<skill_dir>` is the `system-diagnostics` folder.

## Workflow

1. **Enable** (app owner, local dev only): start the app with `FRONTIER_DEBUG_OBSERVATIONS=1`; the HUD loads when `window.__FRONTIER_DEBUG__ === true`.
2. **Record**: in the browser, pick an element, record a short session, log a finding or an idea. Kinds: `element`, `error`, `network`, `note` (findings) and `idea`.
3. **Read**: `observations list` (active only by default; `--kind`, `--status all`, `--json`), `observations show --id <ID> [--full]`. Remote or containerized app: `observations pull --url http://127.0.0.1:<port>` first (loopback only unless `--allow-remote`).
4. **Triage**: `observations triage --id <ID> --root-cause "..." [--missed-by tests,surface,scan,audit,ui,probes,trace,other] [--guard "..."] [--plan <slug>]`. Status moves `open -> triaged -> in_progress`.
5. **Fix and close**: after a **verified** fix, `observations resolve --id <ID> --resolution "..." --commit <sha>`. Not a bug or not worth doing: `observations dismiss --id <ID> --reason "..."`. Never resolve on an unverified patch.
6. **Digest**: `brief` prints one capped summary (observations, probe last results, defects, traces). `brief --run-probes` runs fresh probes; `brief --pull URL` pulls first. A failing section shows `UNAVAILABLE (reason)`, never a pass.
7. **Conformance** (app implementers): `observations verify-connector --url http://127.0.0.1:<port>` reports `PASS`/`FAIL`/`SKIP` per check and stores nothing.

## Audit Hand-off

For an audit (`/frontier-architect audit`, or the project's FOR AUDITS prompt):

- Start with `brief` (add `--run-probes` and `--pull URL` when the app is running).
- Findings = active observations of kinds `element|error|network|note`; ideas = kind `idea` (`observations list --kind idea --json`).
- Record "why did our tools miss it" with `triage --missed-by ... --guard ...` so it stays queryable.
- Close the loop with `resolve` after verification, citing the commit.

Under Claude Code, `ask_question` is `AskUserQuestion` and `Model: 'flash'` research subagents are `Explore` agents.

## Privacy

Observations stay in `.diagnostics/` (gitignored) and never leave the machine. The server drops `value`, `password`, `authorization` and `cookie` fields and stores no request or response bodies. `pull` refuses non-loopback URLs unless `--allow-remote`, and then warns. Never enable the flag outside local development, and do not paste raw observation data into external services.
