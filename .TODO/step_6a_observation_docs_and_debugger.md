# Child Plan: Observation Docs & App-Debugger Integration (6A)

Parent: `universal_debug_observation_connector_plan`, Milestone 6 (part 6A of 6A/6B). 6B (frontier-architect audit recipe, `ARCHITECTURE.md`, `AGENTS.md`, adoption-plan reconciliation) follows in the next turn.

**Pre-Flight:** invariants = docs use `python "<skill_dir>/scripts/diagnose.py" ...` only (D6); `system-diagnostics/SKILL.md` gets a pointer line only (15.5 KB already); `app-debugger/SKILL.md` stays under 350 lines; privacy rule stated (observations never leave the machine, `pull` loopback-only). Flow = new reference doc -> pointers -> eval case -> evaluator rule -> test. Edge cases = eval expectations must hit an explicit rule (no generic-keyword fallback). Verifier = commands below.

## Milestone 6A

- [x] **system-diagnostics/references/observations.md**: workflow (record, list, triage, resolve, pull, brief), audit hand-off, privacy.
- [x] **system-diagnostics/references/cli-reference.md**: `observations` and `brief` flag tables.
- [x] **system-diagnostics/SKILL.md**: one pointer line.
- [x] **app-debugger/SKILL.md**: read active observations in Step 2, resolve after a verified fix in Step 4.
- [x] **app-debugger/evals/evals.json** and **app-debugger/tests/test_skill_evals.py**: eval 14 plus evaluator rules.
- [x] **system-diagnostics/tests/test_observation_docs.py**: doc guards (pointer, `<skill_dir>` form, flags exist in the CLI).

**Verifier**: `python3 -m unittest discover -s system-diagnostics/tests -p "test_*.py"` and `python3 -m unittest discover -s app-debugger/tests -p "test_*.py"`
