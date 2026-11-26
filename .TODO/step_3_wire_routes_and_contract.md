# Child Plan: Wire Routes, Correlation Stamping, Scaffolder & Published Contract

Parent: `universal_debug_observation_connector_plan`, Milestone 3. The parent's **Wire Contract v1**, **Correlation Contract**, **Security & Privacy Contract** and **Runtime Parity Contract** are the specification.

**Pre-Flight:** invariants = routes absent (404) unless `FRONTIER_DEBUG_OBSERVATIONS=1`, loopback only, size/redaction on write, scaffold without the flag unchanged except the shared bootstrap. Flow = framework adapter -> `observation_routes.handle` -> `observation_store`. Edge cases = no framework installed, engine missing, Claude layout, oversize body, bad recording id header. Verifier = command below.

**Deviation from the master list (decided during implementation):** route logic lives in a new engine module `observation_routes.py`, with `connector_templates_obs.py` holding only thin adapters. One tested implementation of every Wire Contract row beats three copies embedded in template strings. The 3A/3B split was not needed.

## Milestone 3

- [x] **system-diagnostics/scripts/trace_middleware.py**: stamp validated `recording_id` (ASGI and WSGI).
- [x] **system-diagnostics/scripts/connector_bridge_common.py**: shared engine-path bootstrap (Parity order).
- [x] **system-diagnostics/scripts/observation_routes.py**: all Wire Contract routes, framework-agnostic.
- [x] **system-diagnostics/scripts/connector_templates_obs.py**: fastapi, flask and generic adapters.
- [x] **system-diagnostics/scripts/connector_scaffolder.py**: bootstrap placeholder, `with_observations`.
- [x] **system-diagnostics/scripts/trace_cli.py**: `--with-observations` (exit 2 without `--scaffold`).
- [x] **system-diagnostics/references/observation-connector-contract.md** and **observation_contract.schema.json**.
- [x] **system-diagnostics/tests/**: `test_connector_scaffolder.py`, `test_observation_bridge_routes.py`, `test_observation_contract_doc.py`, recording_id cases in `test_trace_recorder.py`.

**Verifier**: `python -m unittest discover -s system-diagnostics/tests -p "test_*.py"`

## Known limitations

- Real FastAPI/Flask are not installed in CI; adapters are tested against fake framework modules. Live check with real frameworks is UNVERIFIED.
- `X-Debug-Recording-Id` stamping is exercised through the middleware only, not through a live browser.
