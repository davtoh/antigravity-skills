# Observation Connector Contract (Wire Contract v1)

The standard an app implements so the DevTools HUD can post what a human sees while debugging, and the agent can later read it (`diagnose.py observations list`, `observations pull`). Machine-readable shapes: [`observation_contract.schema.json`](./observation_contract.schema.json).

Run commands as `python "<skill_dir>/scripts/diagnose.py" ...` where `<skill_dir>` is the `system-diagnostics` folder.

## Rules

- Base path `/api/diagnostics`. Routes exist only when env `FRONTIER_DEBUG_OBSERVATIONS=1`; otherwise every route answers `404`.
- Loopback clients only (`127.0.0.1`, `::1`); anything else gets `403`.
- Every response carries `X-Diagnostics-Contract: 1`.
- Errors are JSON `{"error": "<code>", "message": "..."}` with codes `invalid_json`, `invalid_record`, `payload_too_large`, `forbidden`, `not_found`, `unsupported_media_type`.
- The server drops any field named `value`, `password`, `authorization` or `cookie`, caps a record at 64 KB, `message` at 500 chars and `timeline` at 50 events.

## Routes

| Route | Success | Errors |
| :--- | :--- | :--- |
| `GET /health` | `200 {"schema":1,"enabled":true,"contract_version":1,"store":"ok"}` | n/a |
| `POST /observation` | `201` new, `200` deduplicated, `200` with `"dry_run":true` when `?dry_run=1` (nothing stored) | `400 invalid_json\|invalid_record`, `403`, `413`, `415` |
| `GET /observations` | `200` list (`status` default `active`, `kind`, `limit` default 20, max 200) | `400 invalid_record`, `403` |
| `GET /observations/{id_or_fingerprint}` | `200` full entry | `404`, `403` |
| `PATCH /observations/{id_or_fingerprint}` | `200` updated full entry (edit message/kind, attach pick/trace, update status) | `400 invalid_json\|invalid_record`, `403`, `404`, `413`, `415` |
| `DELETE /observations/{id_or_fingerprint}` | `200 {"deleted":true,"id":"OBS-001"}` | `404`, `403` |
| `GET /hud.js` | `200 application/javascript`, `Cache-Control: no-store` | `403` |

The HUD sends `X-Debug-Recording-Id: rec-<6hex>` on every same-origin fetch/XHR while recording. An app that wants exact correlation stamps that value into its exception traces.

## Tier A: Python apps (uses the skill)

```bash
python "<skill_dir>/scripts/diagnose.py" traces --scaffold fastapi --dest services --with-observations
```

Then in the app (`fastapi` shown; `flask` calls `register_observation_routes(app)` the same way; `generic` exposes `handle_diagnostics_request(method, rel_path, query, headers, client_host, body)` for any router):

```python
from services.diagnostic_bridge import init_diagnostic_tracer, DiagnosticTraceMiddleware, register_observation_routes
init_diagnostic_tracer()
app.add_middleware(DiagnosticTraceMiddleware)
register_observation_routes(app)
```

## Tier B: any language

Implement the table above against any storage and import with `observations pull --url http://127.0.0.1:<port>`.

## Check it

```bash
export FRONTIER_DEBUG_OBSERVATIONS=1
curl -i http://127.0.0.1:8000/api/diagnostics/health
curl -i -X POST -H 'Content-Type: application/json' -d '{"kind":"note","message":"hello"}' 'http://127.0.0.1:8000/api/diagnostics/observation?dry_run=1'
curl -i 'http://127.0.0.1:8000/api/diagnostics/observations?limit=5'
```

## Security notes

Data lands only in `.diagnostics/` (gitignored). Never enable `FRONTIER_DEBUG_OBSERVATIONS` outside local development; never store request/response bodies, cookies or credentials.
