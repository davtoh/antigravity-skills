# Child Plan: Audit Mode, Repo Docs & Adoption Plan Reconciliation (6B)

Parent: `universal_debug_observation_connector_plan`, Milestone 6 (part 6B of 6A/6B).

**Pre-Flight:** invariants = `frontier-architect/SKILL.md` stays under 12,000 bytes (one line only); references carry Antigravity terms with Claude equivalents and the adapter banner; the adoption plan keeps the wire contract verbatim. Edge cases = eval expectations must hit explicit rules; no function over 40 lines. Verifier = four suites.

## Milestone 6B

- [x] **frontier-architect/references/audit-recipe.md** and **connector-integration.md**: audit steps and planning rules (dual vocabulary).
- [x] **frontier-architect/SKILL.md** and **references/phase-protocols.md**: one-line mode pointer and audit paragraph.
- [x] **frontier-architect/evals/evals.json**, **evals/audit-mode-pressure/**, **tests/test_skill_evals.py**, **tests/test_regression_guards.py**, **tests/README.md**: eval 29, pressure case, guards.
- [x] **ARCHITECTURE.md** and **AGENTS.md**: sections 3, 6, 7, 8 refresh; connector note; app-debugger suite.
- [x] **.TODO/debug_observation_connector_adoption_plan.md**: reconciled to the shipped contract, with a ready-to-paste prompt.

**Verifier**: `python3 -m unittest discover -s system-diagnostics/tests -p "test_*.py"` and the refactor-monolith, app-debugger and frontier-architect suites.
