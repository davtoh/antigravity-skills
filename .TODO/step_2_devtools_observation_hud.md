# Child Plan: DevTools Observation HUD

Parent: `universal_debug_observation_connector_plan`, Milestone 2. The parent's **HUD Contract**, **Data Contracts**, **Wire Contract** (`POST /observation`, `GET /hud.js`) and **SPIKE Spec** are the specification; this file adds build order only.

**Pre-Flight:** invariants = HUD is a strict no-op unless `window.__FRONTIER_DEBUG__ === true`; never reads input values/textarea/contenteditable text; Soft Pause fully restores. Flow = Pick/Record -> raw record (Data Contract) -> `POST` endpoint. Edge cases = password input, iframe, open shadow DOM, strict CSP, `<video>`, double install. Verifier = commands below.

## Milestone 2

- [x] **system-diagnostics/tests/fixtures/hud/*.html** (+ `flag.js`): six SPIKE fixtures `plain, spa, iframe, shadow, csp, media`.
- [x] **system-diagnostics/assets/hud_core.js**: gate, helpers, unique selector, redaction, panel, POST.
- [x] **system-diagnostics/assets/hud_picker.js**: Pick Element + Soft Pause.
- [x] **system-diagnostics/assets/hud_recorder.js**: Record/Stop, fetch/XHR wrap, timeline.
- [x] **system-diagnostics/scripts/observation_assets.py**: `hud_bundle()` fixed order + gate wrapper.
- [x] **system-diagnostics/tests/test_observation_hud.py**: Node VM logic tests (skip without `node`).
- [x] **system-diagnostics/tests/test_observation_hud_e2e.py**: Chrome-gated SPIKE + E2E (skip without Chrome).

**SPIKE result:** recorded in `.frontier/scratch/obs-hud/RESULT.md` after the E2E run.

**Verifier**: `python -m unittest discover -s system-diagnostics/tests -p "test_observation_hud*.py"`

## Known HUD limitations (accepted 2026-11-26; improve later)

- Iframe/shadow selectors use ` >>> `; re-find with `H.resolve` (strict `document.querySelector` cannot cross those boundaries).
- Requests made from inside an iframe window are not tagged with `X-Debug-Recording-Id`.
- Soft Pause covers the top document only (not media in iframes/shadow roots); closed shadow roots unsupported.
- Only same-origin requests are tagged; WebSocket frames out of scope (contract v1).
- SPIKE decided on the extended metric (strict 4/6 inconclusive; extended pass): see `.frontier/scratch/obs-hud/RESULT.md`.

## Pending After Plan (follow-ups; none block Milestone 3)

Untested contract rows:
- [ ] Selector uniqueness check (`querySelectorAll(sel).length === 1`) and the path fallback: needs a real-DOM test (Node fake DOM cannot).
- [ ] Hover highlight (`onMove`) rect/box placement.
- [ ] Review Gate: 2 attempts used; fixes from attempt 2 were not re-reviewed by a fresh reviewer (accepted by the user 2026-11-26).
- [ ] Run `refactor-monolith`, `app-debugger`, `frontier-architect` suites before committing.

Known limitations to improve (see "Known HUD limitations"):
- [ ] Tag requests made from inside iframes (wrap the frame window's fetch/XHR).
- [ ] Soft Pause for media inside iframes and shadow roots.
- [ ] Stop removes a `fetch` wrapper the page installed during recording (restore only if `win.fetch` is still ours).
- [ ] Closed shadow roots; WebSocket frames (contract v1 out of scope).
- [ ] Strict SPIKE metric was 4/6 (inconclusive); re-run with an added fixture if strictness matters.
