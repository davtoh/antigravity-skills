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
except ImportError:  # pragma: no cover - package-style import
    from . import defect_catalog

SCHEMA_VERSION = "1.0"
ACTIVE_STATUSES = ("open", "triaged", "in_progress")
CLOSED_STATUSES = ("resolved", "dismissed")
KINDS = ("element", "error", "network", "note", "idea")
MISSED_BY = ("tests", "surface", "scan", "audit", "ui", "probes", "trace", "other")
MAX_RECORD_BYTES = 65536
MAX_MESSAGE = 500
MAX_TIMELINE = 50
ROTATE_BYTES = 5 * 1024 * 1024
FORBIDDEN_KEYS = ("value", "password", "authorization", "cookie")
TRANSITIONS = {
    "open": ("triaged", "in_progress", "resolved", "dismissed"),
    "triaged": ("in_progress", "resolved", "dismissed"),
    "in_progress": ("resolved", "dismissed", "triaged"),
    "resolved": ("open",),
    "dismissed": ("open",),
}
RAW_NAME = "observations.jsonl"
BACKUP_NAME = "observations.1.jsonl"
CATALOG_NAME = "observation_catalog.json"
_META_FIELDS = ("root_cause", "linked_plan", "resolution", "linked_commit", "proposed_guard")


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
        "first_seen": rec["ts"], "last_seen": rec["ts"], "occurrence_count": 1,
        "page_path": rec.get("page_path", ""), "selector": rec.get("selector", ""),
        "rect": rec.get("rect"), "attrs": rec.get("attrs", {}), "message": rec["message"],
        "recording_id": rec.get("recording_id"), "window": rec.get("window"),
        "timeline": rec["timeline"], "correlated_traces": [], "root_cause": "", "missed_by": [],
        "proposed_guard": "", "resolution": "", "linked_plan": "", "linked_commit": "",
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
        if entry["status"] == "resolved":
            entry["history"].append({"ts": rec["ts"], "from": "resolved", "to": "open", "note": "recurrence"})
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
    entry["status"] = new_status
    entry["history"].append({"ts": _now(), "from": old, "to": new_status, "note": note})
    save_catalog(workspace, catalog)
    return entry


def list_observations(workspace: Path, status: str = "active", limit: int = 20, kind: str | None = None) -> list[dict[str, Any]]:
    """Newest-first listing; `status` is active, all, or one concrete status."""
    entries = load_catalog(workspace)["observations"]
    if status == "active":
        entries = [e for e in entries if e["status"] in ACTIVE_STATUSES]
    elif status != "all":
        entries = [e for e in entries if e["status"] == status]
    if kind:
        entries = [e for e in entries if e["kind"] == kind]
    entries = sorted(entries, key=lambda e: e.get("last_seen", ""), reverse=True)
    return entries[:limit] if limit and limit > 0 else entries


def _apply_patch_fields(entry: dict[str, Any], clean: dict[str, Any]) -> None:
    """Apply validated editable fields onto an existing catalog observation entry."""
    if "kind" in clean:
        if clean["kind"] not in KINDS:
            raise ValueError(f"invalid kind {clean['kind']!r}; expected one of {', '.join(KINDS)}")
        entry["kind"] = clean["kind"]
    if "message" in clean:
        entry["message"] = str(clean["message"] or "")[:MAX_MESSAGE]
    for str_key in ("page_path", "selector"):
        if str_key in clean:
            entry[str_key] = str(clean[str_key] or "")
    if "rect" in clean:
        if clean["rect"] is not None and not isinstance(clean["rect"], dict):
            raise ValueError("rect must be an object or null")
        entry["rect"] = clean["rect"]
    if "attrs" in clean:
        if not isinstance(clean["attrs"], dict):
            raise ValueError("attrs must be an object")
        entry["attrs"] = clean["attrs"]
    if "recording_id" in clean:
        entry["recording_id"] = str(clean["recording_id"]) if clean["recording_id"] else None
    if "window" in clean:
        if clean["window"] is not None and not isinstance(clean["window"], dict):
            raise ValueError("window must be an object or null")
        entry["window"] = clean["window"]
    if "timeline" in clean:
        if not isinstance(clean["timeline"], list):
            raise ValueError("timeline must be an array")
        entry["timeline"] = list(clean["timeline"])[-MAX_TIMELINE:]


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
    _apply_patch_fields(entry, clean)
    entry["fingerprint"] = make_fingerprint(entry["kind"], entry.get("page_path", ""), _target(entry), entry["message"])
    now = _now()
    entry["last_seen"] = now
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
