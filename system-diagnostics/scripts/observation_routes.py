#!/usr/bin/env python3
"""Framework-agnostic implementation of Wire Contract v1 (`/api/diagnostics/*`).

Generated bridges (FastAPI, Flask, generic) are thin adapters over :func:`handle`, so every
route row (gating, loopback, size caps, dry_run, redaction, headers) lives in one tested place.
Python standard library only.
"""

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import observation_assets
import observation_store as store

CONTRACT_VERSION = 1
ENABLE_ENV = "FRONTIER_DEBUG_OBSERVATIONS"
BASE_PATH = "/api/diagnostics"
LOOPBACK_HOSTS = ("127.0.0.1", "::1", "::ffff:127.0.0.1")
ERROR_CODES = (
    "invalid_json", "invalid_record", "payload_too_large", "forbidden", "not_found", "unsupported_media_type",
)
ROUTES = (
    "GET /health",
    "POST /observation",
    "GET /observations",
    "GET /observations/{id_or_fingerprint}",
    "PATCH /observations/{id_or_fingerprint}",
    "DELETE /observations/{id_or_fingerprint}",
    "GET /hud.js",
)
MAX_LIMIT = 200
DEFAULT_LIMIT = 20
LIST_FIELDS = (
    "id", "fingerprint", "status", "kind", "page_path", "selector", "elements",
    "related_ids", "message", "occurrence_count", "last_seen",
)


def _list_row(e: dict[str, Any]) -> dict[str, Any]:
    row = {k: e.get(k) for k in LIST_FIELDS}
    if row.get("elements") is None:
        sel = str(e.get("selector") or "").strip()
        row["elements"] = (
            [{"selector": sel, "rect": e.get("rect"), "attrs": e.get("attrs") or {}}] if sel else []
        )
    if row.get("related_ids") is None:
        row["related_ids"] = []
    return row

Response = tuple[int, dict[str, str], bytes]


def enabled(env: Any = None) -> bool:
    return (env if env is not None else os.environ).get(ENABLE_ENV) == "1"


def _json(status: int, payload: dict[str, Any], extra: dict[str, str] | None = None) -> Response:
    headers = {"Content-Type": "application/json", "X-Diagnostics-Contract": str(CONTRACT_VERSION)}
    headers.update(extra or {})
    return status, headers, json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _error(status: int, code: str, message: str) -> Response:
    return _json(status, {"error": code, "message": message})


def _post(body: bytes, headers: dict[str, str], query: dict[str, list[str]], workspace: Path) -> Response:
    if not headers.get("content-type", "").lower().startswith("application/json"):
        return _error(415, "unsupported_media_type", "Content-Type must be application/json")
    if len(body) > store.MAX_RECORD_BYTES:
        return _error(413, "payload_too_large", f"body exceeds {store.MAX_RECORD_BYTES} bytes")
    try:
        raw = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return _error(400, "invalid_json", "body is not valid JSON")
    try:
        rec = store.sanitize_record(raw)
    except ValueError as exc:
        return _error(400, "invalid_record", str(exc))
    fp = store.make_fingerprint(rec["kind"], rec.get("page_path", ""), store._target(rec), rec["message"])
    if query.get("dry_run", [""])[0] == "1":
        known = any(e.get("fingerprint") == fp for e in store.load_catalog(workspace)["observations"])
        return _json(200, {"dry_run": True, "fingerprint": fp, "status": "open", "deduplicated": known})
    entry, dedup = store.add_observation(workspace, raw)
    payload = {"id": entry["id"], "fingerprint": entry["fingerprint"], "status": entry["status"], "deduplicated": dedup}
    return _json(200 if dedup else 201, payload)


def _list(query: dict[str, list[str]], workspace: Path) -> Response:
    status = query.get("status", ["active"])[0]
    valid = ("active", "all") + store.ACTIVE_STATUSES + store.CLOSED_STATUSES
    kind = query.get("kind", [""])[0] or None
    if status not in valid or (kind and kind not in store.KINDS):
        return _error(400, "invalid_record", "invalid status or kind filter")
    try:
        limit = int(query.get("limit", [str(DEFAULT_LIMIT)])[0])
    except ValueError:
        return _error(400, "invalid_record", "limit must be an integer")
    limit = min(max(limit, 1), MAX_LIMIT)
    entries = store.list_observations(workspace, status=status, limit=0, kind=kind)
    shown = [_list_row(e) for e in entries[:limit]]
    return _json(200, {"schema": 1, "count": len(shown), "truncated": len(entries) > limit, "observations": shown})


def _patch(id_or_fp: str, body: bytes, headers: dict[str, str], workspace: Path) -> Response:
    if not headers.get("content-type", "").lower().startswith("application/json"):
        return _error(415, "unsupported_media_type", "Content-Type must be application/json")
    if len(body) > store.MAX_RECORD_BYTES:
        return _error(413, "payload_too_large", f"body exceeds {store.MAX_RECORD_BYTES} bytes")
    try:
        raw = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return _error(400, "invalid_json", "body is not valid JSON")
    try:
        entry = store.patch_observation(workspace, id_or_fp, raw)
    except KeyError:
        return _error(404, "not_found", "no such observation")
    except ValueError as exc:
        return _error(400, "invalid_record", str(exc))
    return _json(200, entry)


def _delete(id_or_fp: str, workspace: Path) -> Response:
    try:
        removed = store.delete_observation(workspace, id_or_fp)
    except KeyError:
        return _error(404, "not_found", "no such observation")
    return _json(200, {"deleted": True, "id": removed["id"]})


def handle(
    method: str,
    rel_path: str,
    query: str | dict[str, list[str]],
    headers: dict[str, str],
    client_host: str,
    body: bytes = b"",
    workspace: Path | None = None,
    env: Any = None,
) -> Response:
    """Answer one request. ``rel_path`` is the part after the base path (e.g. ``/health``)."""
    if not enabled(env):
        return _error(404, "not_found", "diagnostics routes are disabled")
    if client_host not in LOOPBACK_HOSTS:
        return _error(403, "forbidden", "loopback clients only")
    ws = Path(workspace) if workspace else Path.cwd()
    hdrs = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    qs = parse_qs(query) if isinstance(query, str) else query
    method, path = method.upper(), "/" + rel_path.strip("/")
    if method == "GET" and path == "/health":
        return _json(200, {"schema": 1, "enabled": True, "contract_version": CONTRACT_VERSION, "store": "ok"})
    if method == "POST" and path == "/observation":
        return _post(body, hdrs, qs, ws)
    if method == "GET" and path == "/observations":
        return _list(qs, ws)
    if path.startswith("/observations/"):
        key = path[len("/observations/"):]
        if method == "GET":
            entry = store.get_observation(ws, key)
            return _json(200, entry) if entry else _error(404, "not_found", "no such observation")
        if method == "PATCH":
            return _patch(key, body, hdrs, ws)
        if method == "DELETE":
            return _delete(key, ws)
    if method == "GET" and path == "/hud.js":
        js = observation_assets.hud_bundle().encode("utf-8")
        return 200, {"Content-Type": "application/javascript", "Cache-Control": "no-store",
                     "X-Diagnostics-Contract": str(CONTRACT_VERSION)}, js
    return _error(404, "not_found", "unknown route")
