#!/usr/bin/env python3
"""Observation store for the Universal Debug Observation Connector (system-diagnostics).

Raw records are appended to `<workspace>/.diagnostics/observations.jsonl`; an aggregated,
deduplicated catalog lives in `<workspace>/.diagnostics/observation_catalog.json`.
Zero third-party dependencies: strictly the Python standard library.
"""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

try:
    import defect_catalog
    import observation_fields
except ImportError:  # pragma: no cover - package-style import
    import importlib

    defect_catalog = importlib.import_module(".defect_catalog", __package__)
    observation_fields = importlib.import_module(".observation_fields", __package__)

SCHEMA_VERSION = "1.0"
ACTIVE_STATUSES = ("open", "triaged", "in_progress")
CLOSED_STATUSES = ("resolved", "confirmed", "dismissed")
KINDS = ("element", "error", "network", "note", "idea")
MISSED_BY = ("tests", "surface", "scan", "audit", "ui", "probes", "trace", "other")
MAX_RECORD_BYTES = 65536
MAX_MESSAGE = 500
MAX_TIMELINE = 50
MAX_ELEMENTS = observation_fields.MAX_ELEMENTS
MAX_RELATED = observation_fields.MAX_RELATED
ROTATE_BYTES = 5 * 1024 * 1024
FORBIDDEN_KEYS = ("value", "password", "authorization", "cookie")
TRANSITIONS = {
    "open": ("triaged", "in_progress", "resolved", "dismissed"),
    "triaged": ("in_progress", "resolved", "dismissed"),
    "in_progress": ("resolved", "dismissed", "triaged"),
    "resolved": ("confirmed", "open"),
    "confirmed": ("open",),
    "dismissed": ("open",),
}
RAW_NAME = "observations.jsonl"
BACKUP_NAME = "observations.1.jsonl"
CATALOG_NAME = "observation_catalog.json"
_META_FIELDS = observation_fields.META_FIELDS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_message(msg: str) -> str:
    """Lowercase, strip hex pointers and 5+ digit runs, collapse whitespace."""
    text = re.sub(r"0x[0-9a-f]+", "", (msg or "").lower())
    text = re.sub(r"\d{5,}", "", text)
    return " ".join(text.split())


def make_fingerprint(kind: str, page_path: str, target: str, message: str) -> str:
    """Return `OBS-<KIND>-<6HEX>` per the parent Data Contract."""
    basis = f"{kind}|{page_path or ''}|{target or ''}|{normalize_message(message)}"
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:6]
    return f"OBS-{kind.upper()[:7]}-{digest}"


def _strip_forbidden(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _strip_forbidden(v) for k, v in node.items() if str(k).lower() not in FORBIDDEN_KEYS}
    if isinstance(node, list):
        return [_strip_forbidden(v) for v in node]
    return node


def sanitize_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate and clean a raw record; raise ValueError when it must be rejected."""
    if not isinstance(raw, dict):
        raise ValueError("record must be a JSON object")
    if raw.get("kind") not in KINDS:
        raise ValueError(f"invalid kind {raw.get('kind')!r}; expected one of {', '.join(KINDS)}")
    if len(json.dumps(raw, ensure_ascii=False).encode("utf-8")) > MAX_RECORD_BYTES:
        raise ValueError(f"record exceeds {MAX_RECORD_BYTES} bytes")
    rec = _strip_forbidden(raw)
    rec["message"] = str(rec.get("message") or "")[:MAX_MESSAGE]
    timeline = rec.get("timeline")
    rec["timeline"] = list(timeline)[-MAX_TIMELINE:] if isinstance(timeline, list) else []
    has_el = "elements" in rec
    rec["elements"] = observation_fields.normalize_elements(
        rec.get("elements") if has_el else None,
        str(rec.get("selector") or ""),
        rec.get("rect"),
        rec.get("attrs"),
    )
    if has_el or rec["elements"]:
        observation_fields.sync_primary_element(rec)
    rec["related_ids"] = observation_fields.normalize_related_ids(rec.get("related_ids"))
    rec.setdefault("schema", 1)
    rec.setdefault("ts", _now())
    return rec


def _diag(workspace: Path) -> Path:
    return defect_catalog.ensure_diagnostics_dir(Path(workspace))


def append_raw(workspace: Path, record: dict[str, Any]) -> None:
    """Append one JSON line, rotating to a single backup at ROTATE_BYTES."""
    path = _diag(workspace) / RAW_NAME
    if path.exists() and path.stat().st_size >= ROTATE_BYTES:
        os.replace(path, path.with_name(BACKUP_NAME))
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


def iter_raw(workspace: Path) -> tuple[list[dict[str, Any]], int]:
    """Return (records, corrupt_line_count) from the raw log; never raises on bad lines."""
    path = _diag(workspace) / RAW_NAME
    records: list[dict[str, Any]] = []
    corrupt = 0
    if not path.exists():
        return records, corrupt
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                corrupt += 1
                continue
            if isinstance(obj, dict):
                records.append(obj)
            else:
                corrupt += 1
    return records, corrupt


def summarize(catalog: dict[str, Any]) -> dict[str, int]:
    entries = catalog.get("observations", [])
    out = {"total": len(entries)}
    out.update({s: sum(1 for e in entries if e.get("status") == s) for s in ACTIVE_STATUSES + CLOSED_STATUSES})
    return out


def load_catalog(workspace: Path) -> dict[str, Any]:
    path = _diag(workspace) / CATALOG_NAME
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("observations"), list):
                return data
        except ValueError:
            pass
    return {"schema_version": SCHEMA_VERSION, "workspace": Path(workspace).resolve().as_posix(),
            "updated_at": _now(), "summary": summarize({}), "observations": []}


def save_catalog(workspace: Path, catalog: dict[str, Any]) -> None:
    """Atomically persist the catalog (write .tmp, then os.replace)."""
    path = _diag(workspace) / CATALOG_NAME
    catalog["updated_at"] = _now()
    catalog["summary"] = summarize(catalog)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _next_id(entries: list[dict[str, Any]]) -> str:
    nums = [int(m.group(1)) for e in entries if (m := re.fullmatch(r"OBS-(\d+)", e.get("id", "")))]
    return f"OBS-{(max(nums) if nums else 0) + 1:03d}"


def _new_entry(rec: dict[str, Any], fp: str, entry_id: str) -> dict[str, Any]:
    return {
        "id": entry_id, "fingerprint": fp, "kind": rec["kind"], "status": "open",
        "first_seen": rec["ts"], "last_seen": rec["ts"], "updated_at": rec["ts"], "occurrence_count": 1,
        "page_path": rec.get("page_path", ""), "selector": rec.get("selector", ""),
        "rect": rec.get("rect"), "attrs": rec.get("attrs", {}),
        "elements": rec.get("elements", []), "related_ids": rec.get("related_ids", []),
        "message": rec["message"],
        "recording_id": rec.get("recording_id"), "window": rec.get("window"),
        "timeline": rec["timeline"], "correlated_traces": [], "root_cause": "", "missed_by": [],
        "proposed_guard": "", "resolution": "", "linked_plan": "", "linked_commit": "",
        **{k: str(rec.get(k) or "") for k in observation_fields.PROVENANCE_FIELDS},
        "source_url": rec.get("source_url", ""), "history": [],
    }


def _target(rec: dict[str, Any]) -> str:
    if rec.get("selector"):
        return rec["selector"]
    if rec["kind"] == "network":
        return rec.get("url_path") or rec.get("url") or ""
    return ""


def add_observation(workspace: Path, raw: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Sanitize, append and upsert. Returns (entry, deduplicated)."""
    rec = sanitize_record(raw)
    fp = make_fingerprint(rec["kind"], rec.get("page_path", ""), _target(rec), rec["message"])
    append_raw(workspace, rec)
    catalog = load_catalog(workspace)
    entries = catalog["observations"]
    entry = next((e for e in entries if e.get("fingerprint") == fp), None)
    dedup = entry is not None
    if entry is None:
        entry = _new_entry(rec, fp, _next_id(entries))
        entries.append(entry)
    else:
        entry["occurrence_count"] = entry.get("occurrence_count", 1) + 1
        entry["last_seen"] = rec["ts"]
        if entry.get("recording_id") is None and rec.get("recording_id"):
            entry["recording_id"], entry["window"] = rec["recording_id"], rec.get("window")
        if entry["status"] in ("resolved", "confirmed"):
            entry["history"].append({"ts": rec["ts"], "from": entry["status"], "to": "open", "note": "recurrence"})
            entry["status"] = "open"
    save_catalog(workspace, catalog)
    return entry, dedup


def _find(catalog: dict[str, Any], id_or_fp: str) -> dict[str, Any] | None:
    key = (id_or_fp or "").strip().upper()
    return next((e for e in catalog["observations"] if key in (e["id"].upper(), e["fingerprint"].upper())), None)


def get_observation(workspace: Path, id_or_fp: str) -> dict[str, Any] | None:
    return _find(load_catalog(workspace), id_or_fp)


def _parse_missed_by(value: Any) -> list[str]:
    items = value.split(",") if isinstance(value, str) else list(value or [])
    items = [str(i).strip().lower() for i in items if str(i).strip()]
    bad = [i for i in items if i not in MISSED_BY]
    if bad:
        raise ValueError(f"unknown missed_by tool(s): {', '.join(bad)}; expected {', '.join(MISSED_BY)}")
    return items


def update_status(workspace: Path, id_or_fp: str, new_status: str, note: str = "", **meta: Any) -> dict[str, Any]:
    """Apply a lifecycle transition. Raises ValueError (illegal/unknown) or KeyError (not found)."""
    if new_status not in TRANSITIONS:
        raise ValueError(f"unknown status {new_status!r}")
    missed = _parse_missed_by(meta["missed_by"]) if meta.get("missed_by") else None
    catalog = load_catalog(workspace)
    entry = _find(catalog, id_or_fp)
    if entry is None:
        raise KeyError(id_or_fp)
    old = entry["status"]
    if new_status != old and new_status not in TRANSITIONS[old]:
        raise ValueError(f"illegal transition {old} -> {new_status}")
    for field in _META_FIELDS:
        if meta.get(field):
            entry[field] = meta[field]
    if missed is not None:
        entry["missed_by"] = missed
    now = _now()
    if new_status == "confirmed" and not meta.get("confirmed_at"):
        entry["confirmed_at"] = now
    entry["status"] = new_status
    entry["history"].append({"ts": now, "from": old, "to": new_status, "note": note})
    save_catalog(workspace, catalog)
    return entry


def _id_num(entry: dict[str, Any]) -> int:
    m = re.fullmatch(r"OBS-(\d+)", str(entry.get("id") or ""))
    return int(m.group(1)) if m else 0


def list_observations(
    workspace: Path, status: str = "active", limit: int = 20, kind: str | None = None, sort: str = "recent",
) -> list[dict[str, Any]]:
    """Listing sorted by `recent` (default), `id_desc`, or `id_asc`; `status` is active, all, or one status."""
    entries = load_catalog(workspace)["observations"]
    if status == "active":
        entries = [e for e in entries if e["status"] in ACTIVE_STATUSES]
    elif status != "all":
        entries = [e for e in entries if e["status"] == status]
    if kind:
        entries = [e for e in entries if e["kind"] == kind]
    if sort == "id_asc":
        entries = sorted(entries, key=_id_num)
    elif sort == "id_desc":
        entries = sorted(entries, key=_id_num, reverse=True)
    elif sort == "recent":
        entries = sorted(entries, key=lambda e: (e.get("last_seen", ""), _id_num(e)), reverse=True)
    else:
        raise ValueError(f"unknown sort {sort!r}; expected recent, id_asc, or id_desc")
    return entries[:limit] if limit and limit > 0 else entries


def patch_observation(workspace: Path, id_or_fp: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Edit fields, attach element/trace data, or update status on an existing observation."""
    if not isinstance(updates, dict):
        raise ValueError("patch payload must be a JSON object")
    if len(json.dumps(updates, ensure_ascii=False).encode("utf-8")) > MAX_RECORD_BYTES:
        raise ValueError(f"patch exceeds {MAX_RECORD_BYTES} bytes")
    clean = _strip_forbidden(updates)
    catalog = load_catalog(workspace)
    entry = _find(catalog, id_or_fp)
    if entry is None:
        raise KeyError(id_or_fp)
    old_status = entry["status"]
    if "status" in clean and clean["status"] != old_status:
        new_status = clean["status"]
        if new_status not in TRANSITIONS:
            raise ValueError(f"unknown status {new_status!r}")
        if new_status not in TRANSITIONS[old_status]:
            raise ValueError(f"illegal transition {old_status} -> {new_status}")
        entry["status"] = new_status
    observation_fields.apply_patch_fields(entry, clean, KINDS, MAX_MESSAGE, MAX_TIMELINE)
    entry["fingerprint"] = make_fingerprint(entry["kind"], entry.get("page_path", ""), _target(entry), entry["message"])
    now = _now()
    if entry["status"] == "confirmed" and old_status != "confirmed" and not clean.get("confirmed_at"):
        entry["confirmed_at"] = now
    entry["updated_at"] = now
    entry.setdefault("history", []).append({"ts": now, "from": old_status, "to": entry["status"], "note": "edited"})
    save_catalog(workspace, catalog)
    return entry


def delete_observation(workspace: Path, id_or_fp: str) -> dict[str, Any]:
    """Remove an observation from the catalog by id or fingerprint."""
    catalog = load_catalog(workspace)
    entry = _find(catalog, id_or_fp)
    if entry is None:
        raise KeyError(id_or_fp)
    catalog["observations"] = [e for e in catalog["observations"] if e is not entry]
    save_catalog(workspace, catalog)
    return entry


def export_observations(workspace: Path, status: str = "all", kind: str | None = None) -> dict[str, Any]:
    """Return a deep-redacted JSON export bundle of observations."""
    clean = [_strip_forbidden(e) for e in list_observations(workspace, status=status, limit=0, kind=kind)]
    return {"schema": 1, "schema_version": SCHEMA_VERSION, "exported_at": _now(), "count": len(clean), "observations": clean}


def _import_candidate(raw: dict[str, Any]) -> dict[str, Any]:
    rec = sanitize_record(raw)
    fp = make_fingerprint(rec["kind"], rec.get("page_path", ""), _target(rec), rec["message"])
    cand = _new_entry(rec, fp, str(raw.get("id") or "").strip().upper())
    observation_fields.apply_import_metadata(cand, raw, ACTIVE_STATUSES + CLOSED_STATUSES, _parse_missed_by)
    return cand


def import_observations(workspace: Path, payload: Any) -> dict[str, Any]:
    """Validate and merge an exported JSON bundle into the local catalog."""
    candidates = [_import_candidate(item) for item in observation_fields.validate_import_payload(payload)]
    catalog = load_catalog(workspace)
    entries = catalog["observations"]
    imported, updated, skipped = observation_fields.apply_import_candidates(entries, candidates, _next_id, _now())
    if imported or updated:
        save_catalog(workspace, catalog)
    return {"schema": 1, "imported": imported, "updated": updated, "skipped": skipped, "total": len(entries)}
