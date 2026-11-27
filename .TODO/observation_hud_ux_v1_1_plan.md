# Plan: Observation Connector & HUD v1.1 UX (`observation_hud_ux_v1_1_plan`)

## Goal
Resolve the 7 verified UX and schema gaps (`U1`–`U7`) discovered during real user testing of the DevTools Observation HUD (`e19f6d62`) while preserving Wire Contract v1 backward compatibility and modularity budgets (<=350L/file, <=40L/function).

## Scope & Scenario Combinations Matrix

| Scenario | Category / Status | Expected Behavior |
|---|---|---|
| Attach multiple elements to any category (`U3`) | `note`, `idea`, `error`, `network`, `element` | `elements[]` stores up to 20 `{selector, rect, attrs}` items; `kind` is preserved; `selector`/`rect`/`attrs` mirror `elements[0]` |
| Legacy single-selector POST/PATCH/LIST (`U3`) | Any kind | Missing `elements` hydrates from `selector`/`rect`/`attrs`; clearing `elements: []` clears `selector` |
| Observation relations (`U4`) | Any status | `related_ids` normalizes `OBS-NNN`, deduplicates, excludes `self_id`, caps at 30, rejects invalid IDs with `400 invalid_record` |
| Reopen dismissed/resolved item (`U5`) | `dismissed` / `resolved` -> `open` | Backend `PATCH {"status":"open"}` succeeds (`200`); UI shows `Reopen`, `Dismissed` filter, and inline `Undo` |
| Drawer `Open` in composer (`U1`), Drafts (`U2`), Counts (`U6`), Delete confirm (`U7`) | HUD JS (`Milestone 2`) | Deferred to Milestone 2 |

---

## Milestone 1: Backend Multi-Element & Relation Schema (`U3`, `U4`)

- [x] **system-diagnostics/scripts/observation_fields.py**: Extract field normalization/validation (`normalize_elements`, `sync_primary_element`, `normalize_related_ids`, `apply_patch_fields`) with `MAX_ELEMENTS=20`, `MAX_RELATED=30`.
- [x] **system-diagnostics/scripts/observation_store.py**: Wire `observation_fields` into `sanitize_record`, `_new_entry`, and `patch_observation` (re-export `MAX_ELEMENTS`, `MAX_RELATED`, keep file <350L).
- [x] **system-diagnostics/scripts/observation_routes.py**: Expose `elements` and `related_ids` in `LIST_FIELDS` with legacy-entry hydration fallback in `_list`.
- [x] **system-diagnostics/references/observation_contract.schema.json**: Add `element_ref`, `elements` (`maxItems: 20`), and `related_ids` (`maxItems: 30`, `^OBS-\d+$`) to `record.properties`.
- [x] **system-diagnostics/references/observation-connector-contract.md**: Document `elements` and `related_ids` limits and PATCH support.
- [x] **system-diagnostics/tests/test_observation_bridge_routes.py**: Add tests for multi-element POST/PATCH on non-`element` kinds, forbidden-key stripping in `elements`, `related_ids` validation/self-exclusion, legacy list hydration, and `dismissed -> open` reopen.
- [x] **system-diagnostics/tests/test_observation_contract_doc.py**: Assert `MAX_ELEMENTS` and `MAX_RELATED` match `observation_contract.schema.json`.

### Verification
- `python -m unittest discover -s system-diagnostics/tests -p "test_*.py"`
- `python system-diagnostics/scripts/diagnose.py audit --path system-diagnostics/scripts/observation_fields.py system-diagnostics/scripts/observation_store.py system-diagnostics/scripts/observation_routes.py`

---

## Milestone 2: HUD Composer & Drawer UX Fixes (`U1`–`U7`)

- [x] **system-diagnostics/assets/hud_core.js**: *Deferred to Next Turn / Milestone* — Add `H.picks[]` multi-element composer state (without forcing `note -> element`), `H.openInComposer(entry)` (`H.editingId` mode with Pick/Record/Stop + `Save`/`Cancel`).
- [x] **system-diagnostics/assets/hud_picker.js**: *Deferred to Next Turn / Milestone* — Append picked elements cleanly for composer and drawer attach modes.
- [x] **system-diagnostics/assets/hud_drawer.js**: *Deferred to Next Turn / Milestone* — Add `Open` (`U1`), `drawerState.drafts` + `Save *` (`U2`), multi-element chips without kind overwrite (`U3`), clickable `related_ids` chips & linker (`U4`), `Reopen` + `Dismissed` filter + inline `Undo` (`U5`), `H.refreshCounts()` (`U6`), and inline 2-step `Delete` confirmation (`U7`).
- [x] **system-diagnostics/scripts/observation_assets.py**: *Deferred to Next Turn / Milestone* — Include any split drawer helper asset in `hud_bundle()` if `hud_drawer.js` approaches 300L.
- [x] **system-diagnostics/tests/test_observation_hud.py**: *Deferred to Next Turn / Milestone* — Node VM tests covering `U1`–`U7` end-to-end.
