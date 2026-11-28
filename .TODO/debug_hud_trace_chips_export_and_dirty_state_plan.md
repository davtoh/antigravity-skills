# Debug Observation HUD: Trace Chips, Export/Import & Collapsed Dirty Indicator

> **Scope**: Shared `system-diagnostics` skill (`skills/system-diagnostics/`) — separate from the `intelligent_tracker` Master Roadmap per `/grill-me` Q1 (`OBS-020`, `OBS-021`, `OBS-022`).
> **Architecture & Privacy Contract**: Preserve Wire Contract v1 (`X-Diagnostics-Contract: 1`), loopback-only enforcement (`127.0.0.1` / `::1`, `403` otherwise), 64 KB payload cap, and recursive redaction of `value`/`password`/`authorization`/`cookie`. Observations never leave the machine.
> **Goal**: Surface trace chips on Registered Observations cards and when re-opening an observation in the composer (`OBS-020`), add safe JSON export/import controls and endpoints in the Debug HUD (`OBS-021`), and render an unsaved-changes badge on collapsed observation cards (`OBS-022`).

---

## Public Surface, Modularity Budgets & Scenario Matrix

### 1. Target Files (`skills/system-diagnostics/`)
- `scripts/observation_routes.py` (`LIST_FIELDS`, export/import endpoints)
- `scripts/observation_store.py` (full catalog export / validated import helper)
- `assets/hud_core.js` (`openInComposer` trace chip restoration)
- `assets/hud_drawer_render.js` (trace `fh-chip` on cards + collapsed `dirty` indicator)
- `assets/hud_drawer.js` (Export / Import toolbar actions & file-picker/download wiring)
- `tests/test_observation_connector.py` (or sibling `tests/test_observation_hud_ux.py`)

### 2. Scenario Combinations Matrix
| Scenario | Input / Trigger | Expected Outcome | Verification |
| :--- | :--- | :--- | :--- |
| **Trace Chip on List & Re-Edit (`OBS-020`)** | Capture observation with `recording_id` / `window` / `timeline`; open Registered Observations drawer; click Edit | `GET /api/diagnostics/observations` returns trace metadata; drawer card renders `fh-chip` trace pill; `openInComposer` restores `H.finished` & shows trace chip in composer | `test_observation_hud_ux.py` |
| **Debug HUD Export / Import (`OBS-021`)** | Click Export in drawer, edit JSON externally (within schema), click Import | Export downloads redacted JSON observations bundle; Import validates schema/size, deduplicates/merges cleanly, and refreshes drawer list | `test_observation_hud_ux.py` |
| **Collapsed Card Unsaved Badge (`OBS-022`)** | Expand an observation card, modify note/kind/status without clicking Save, collapse card | Collapsed card header displays visible unsaved/dirty badge (`*` / `Unsaved`) reflecting `drawerState.drafts[id]` | `test_observation_hud_ux.py` |

---

## Milestone 1: Trace Chips, Export/Import & Collapsed Unsaved Indicator *(Active)*

- [x] **skills/system-diagnostics/scripts/observation_routes.py**: Include `recording_id`, `window`, and `trace_count` / `timeline` summary in `LIST_FIELDS` (`lines 36-51`) so drawer list responses carry trace attachment state without exceeding payload budgets (`OBS-020`).
- [x] **skills/system-diagnostics/assets/hud_drawer_render.js**: Render the trace `fh-chip` on observation cards inside `renderCard()` when `recording_id` or `timeline`/`window` is present (`OBS-020`), and display a visible unsaved indicator (`* Unsaved` badge) in the collapsed card header whenever `dirty === true` (`lines 58-66`, `OBS-022`).
- [x] **skills/system-diagnostics/assets/hud_core.js**: Update `H.openInComposer()` (`lines 164-178`) to restore `H.finished` (or composer trace chip state) from `item.recording_id` / `item.window` / `item.timeline` instead of unconditionally resetting `H.finished = null` (`OBS-020`).
- [x] **skills/system-diagnostics/scripts/observation_store.py**: Add redacted JSON export and schema-validated bulk import helpers (`<= 35L`/fn) and wire loopback-gated `GET /api/diagnostics/observations/export` + `POST /api/diagnostics/observations/import` in `scripts/observation_routes.py` (`OBS-021`).
- [x] **skills/system-diagnostics/assets/hud_drawer.js**: Add `Export` and `Import` controls to `H.buildDrawer()` (`lines 189-198`) calling the new export/import endpoints, triggering client-side JSON download and file-input upload + drawer refresh (`OBS-021`).
- [x] **skills/system-diagnostics/tests/test_observation_hud_ux.py**: Add unit + Node VM tests covering `LIST_FIELDS` trace fields, drawer card trace chip + collapsed dirty badge rendering, `openInComposer` trace preservation, and loopback-gated export/import round-trips.
- [x] **Verifier (HUD Milestone 1)**:
  - [x] `python -m unittest discover -s "skills/system-diagnostics/tests" -p "test_*.py"`
  - [x] `python "skills/system-diagnostics/scripts/diagnose.py" audit --path skills/system-diagnostics/scripts/observation_routes.py skills/system-diagnostics/scripts/observation_store.py skills/system-diagnostics/assets/hud_core.js skills/system-diagnostics/assets/hud_drawer_render.js skills/system-diagnostics/assets/hud_drawer.js --max-lines 350 --max-fn-lines 40`
