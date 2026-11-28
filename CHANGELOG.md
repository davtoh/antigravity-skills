# Changelog

## [2026-11-28] feat: HUD Confirmation UX, Provenance Display & Plan-Engine Closure Gate
- **Type**: feat
- **Summary**: Add confirmed/resolved filters, resolution provenance badges, and one-click Confirm/Reopen actions in HUD drawer; warn on unresolved active OBS-NNN IDs during plan_engine.py advance.
- **Files** (10):
  - `.TODO/observation_confirmation_provenance_and_plan_gate_plan.md`
  - `frontier-architect/references/cli-cheatsheet.md`
  - `frontier-architect/scripts/plan_cli_helpers.py`
  - `frontier-architect/scripts/plan_engine.py`
  - `frontier-architect/tests/test_plan_engine_fixes.py`
  - `system-diagnostics/assets/hud_drawer.js`
  - `system-diagnostics/assets/hud_drawer_render.js`
  - `system-diagnostics/references/observations.md`
  - ... (+2 more)
- **Verification**: python -m unittest discover -s system-diagnostics/tests -p test_observation*.py; python -m unittest discover -s frontier-architect/tests -p test_*.py

## [2026-11-27] feat: Observation HUD v1.1 UX Fixes (U1-U7)
- **Type**: feat
- **Summary**: Added composer edit mode, drawer draft preservation, multi-element picks without kind overwrite, clickable related_ids linker, Dismissed filter with Reopen/Undo, live counts, and 2-step delete confirmation.
- **Files** (8):
  - `.TODO/observation_hud_ux_v1_1_plan.md`
  - `system-diagnostics/assets/hud_core.js`
  - `system-diagnostics/assets/hud_drawer.js`
  - `system-diagnostics/assets/hud_drawer_render.js`
  - `system-diagnostics/assets/hud_picker.js`
  - `system-diagnostics/scripts/observation_assets.py`
  - `system-diagnostics/tests/fixtures/hud/ux_driver.js`
  - `system-diagnostics/tests/test_observation_hud.py`
- **Verification**: python -m unittest discover -s skills/system-diagnostics/tests -p test_*.py
