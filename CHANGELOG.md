# Changelog

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
