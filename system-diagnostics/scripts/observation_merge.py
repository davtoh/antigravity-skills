#!/usr/bin/env python3
"""Merge a remote observation entry into the local catalog (used by `observations pull`).

Rules (parent CLI Contract): merge by fingerprint; a remote `last_seen` newer than the local
one wins for status and counters; local triage fields are always kept; `source_url` recorded.
Python standard library only.
"""

from typing import Any

import observation_store as store

_TRIAGE_FIELDS = ("root_cause", "linked_plan", "resolution", "linked_commit", "proposed_guard")
ALL_STATUSES = store.ACTIVE_STATUSES + store.CLOSED_STATUSES


def _clean(remote: dict[str, Any]) -> dict[str, Any]:
    """Re-apply caps and redaction to untrusted remote data."""
    rec = store.sanitize_record({"kind": remote.get("kind"), **remote})
    rec["ts"] = str(remote.get("last_seen") or rec["ts"])
    return rec


def _new_from_remote(catalog: dict[str, Any], rec: dict[str, Any], remote: dict[str, Any], url: str) -> None:
    entries = catalog["observations"]
    fp = remote.get("fingerprint") or store.make_fingerprint(
        rec["kind"], rec.get("page_path", ""), store._target(rec), rec["message"])
    entry = store._new_entry(rec, fp, store._next_id(entries))
    entry["first_seen"] = str(remote.get("first_seen") or rec["ts"])
    entry["occurrence_count"] = int(remote.get("occurrence_count") or 1)
    if remote.get("status") in ALL_STATUSES:
        entry["status"] = remote["status"]
    for field in _TRIAGE_FIELDS:
        entry[field] = str(remote.get(field) or "")
    entry["source_url"] = url
    entries.append(entry)


def _update_from_remote(entry: dict[str, Any], remote: dict[str, Any], url: str) -> None:
    old = entry["status"]
    entry["last_seen"] = str(remote["last_seen"])
    entry["occurrence_count"] = max(entry.get("occurrence_count", 1), int(remote.get("occurrence_count") or 1))
    new = remote.get("status")
    if new in ALL_STATUSES and new != old:
        entry["status"] = new
        entry["history"].append({"ts": entry["last_seen"], "from": old, "to": new, "note": f"pulled from {url}"})
    entry["source_url"] = url


def merge_remote(catalog: dict[str, Any], remote: dict[str, Any], url: str) -> str:
    """Merge into `catalog` in memory. Returns `new`, `updated` or `unchanged`; ValueError if unusable."""
    if not isinstance(remote, dict):
        raise ValueError("remote entry is not a JSON object")
    rec = _clean(remote)
    fp = str(remote.get("fingerprint") or "")
    local = next((e for e in catalog["observations"] if fp and e.get("fingerprint") == fp), None)
    if local is None:
        _new_from_remote(catalog, rec, remote, url)
        return "new"
    if str(remote.get("last_seen") or "") > str(local.get("last_seen") or ""):
        _update_from_remote(local, remote, url)
        return "updated"
    return "unchanged"


def needs_fetch(catalog: dict[str, Any], summary: dict[str, Any]) -> bool:
    """True when a listed remote item is unknown locally or has a newer `last_seen`."""
    fp = summary.get("fingerprint")
    local = next((e for e in catalog["observations"] if e.get("fingerprint") == fp), None)
    return local is None or str(summary.get("last_seen") or "") > str(local.get("last_seen") or "")
