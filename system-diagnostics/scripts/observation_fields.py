#!/usr/bin/env python3
"""Field normalization and patch helpers for observation records.

Keeps multi-element attachment (`elements[]`) and observation relation (`related_ids[]`)
validation isolated from `observation_store.py` so both modules stay well under 350 lines.
"""

import re
from typing import Any

MAX_ELEMENTS = 20
MAX_RELATED = 30
OBS_ID_RE = re.compile(r"^OBS-\d+$")


def _normalize_one_element(item: Any) -> dict[str, Any]:
    """Validate and normalize a single `{selector, rect, attrs}` reference."""
    if not isinstance(item, dict):
        raise ValueError("each element must be an object")
    sel = str(item.get("selector") or "").strip()
    if not sel:
        raise ValueError("each element requires a non-empty selector")
    rect = item.get("rect")
    if rect is not None and not isinstance(rect, dict):
        raise ValueError("element rect must be an object or null")
    attrs = item.get("attrs", {})
    if not isinstance(attrs, dict):
        raise ValueError("element attrs must be an object")
    return {"selector": sel, "rect": rect, "attrs": attrs}


def normalize_elements(
    elements: Any, selector: str = "", rect: Any = None, attrs: Any = None
) -> list[dict[str, Any]]:
    """Normalize `elements[]`, hydrating from legacy `selector`/`rect`/`attrs` when omitted."""
    if elements is None:
        sel = str(selector or "").strip()
        if not sel:
            return []
        r = rect if isinstance(rect, dict) else None
        a = attrs if isinstance(attrs, dict) else {}
        return [{"selector": sel, "rect": r, "attrs": a}]
    if not isinstance(elements, list):
        raise ValueError("elements must be an array")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in elements:
        el = _normalize_one_element(raw)
        if el["selector"] in seen:
            continue
        seen.add(el["selector"])
        out.append(el)
        if len(out) >= MAX_ELEMENTS:
            break
    return out


def sync_primary_element(target: dict[str, Any]) -> None:
    """Mirror `elements[0]` into legacy `selector`, `rect`, and `attrs` fields."""
    els = target.get("elements") or []
    if els:
        first = els[0]
        target["selector"] = first["selector"]
        target["rect"] = first.get("rect")
        target["attrs"] = first.get("attrs") or {}
    else:
        target["selector"] = ""
        target["rect"] = None
        target["attrs"] = {}


def normalize_related_ids(value: Any, self_id: str = "") -> list[str]:
    """Validate, uppercase, deduplicate, and self-exclude `OBS-NNN` relation IDs."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("related_ids must be an array")
    self_key = (self_id or "").strip().upper()
    out: list[str] = []
    seen: set[str] = set()
    for raw in value:
        item = str(raw or "").strip().upper()
        if not OBS_ID_RE.fullmatch(item):
            raise ValueError(f"invalid related_id {raw!r}; expected OBS-NNN")
        if (self_key and item == self_key) or item in seen:
            continue
        seen.add(item)
        out.append(item)
        if len(out) >= MAX_RELATED:
            break
    return out


def _apply_element_patch(entry: dict[str, Any], clean: dict[str, Any]) -> None:
    """Apply `elements` or legacy `selector`/`rect`/`attrs` updates with bidirectional sync."""
    if "elements" in clean:
        entry["elements"] = normalize_elements(clean["elements"])
        sync_primary_element(entry)
        return
    if not any(k in clean for k in ("selector", "rect", "attrs")):
        return
    if "selector" in clean:
        entry["selector"] = str(clean["selector"] or "")
    if "rect" in clean:
        if clean["rect"] is not None and not isinstance(clean["rect"], dict):
            raise ValueError("rect must be an object or null")
        entry["rect"] = clean["rect"]
    if "attrs" in clean:
        if not isinstance(clean["attrs"], dict):
            raise ValueError("attrs must be an object")
        entry["attrs"] = clean["attrs"]
    sel = str(entry.get("selector") or "").strip()
    if not sel and "selector" in clean:
        entry["elements"] = []
        sync_primary_element(entry)
    elif sel:
        first = {"selector": sel, "rect": entry.get("rect"), "attrs": entry.get("attrs") or {}}
        tail = [e for e in (entry.get("elements") or []) if isinstance(e, dict) and e.get("selector") != sel]
        entry["elements"] = ([first] + tail)[:MAX_ELEMENTS]


def apply_patch_fields(
    entry: dict[str, Any],
    clean: dict[str, Any],
    kinds: tuple[str, ...],
    max_message: int,
    max_timeline: int,
) -> None:
    """Apply validated editable fields onto an existing catalog observation entry."""
    if "kind" in clean:
        if clean["kind"] not in kinds:
            raise ValueError(f"invalid kind {clean['kind']!r}; expected one of {', '.join(kinds)}")
        entry["kind"] = clean["kind"]
    if "message" in clean:
        entry["message"] = str(clean["message"] or "")[:max_message]
    if "page_path" in clean:
        entry["page_path"] = str(clean["page_path"] or "")
    _apply_element_patch(entry, clean)
    if "related_ids" in clean:
        entry["related_ids"] = normalize_related_ids(clean["related_ids"], self_id=str(entry.get("id") or ""))
    if "recording_id" in clean:
        entry["recording_id"] = str(clean["recording_id"]) if clean["recording_id"] else None
    if "window" in clean:
        if clean["window"] is not None and not isinstance(clean["window"], dict):
            raise ValueError("window must be an object or null")
        entry["window"] = clean["window"]
    if "timeline" in clean:
        if not isinstance(clean["timeline"], list):
            raise ValueError("timeline must be an array")
        entry["timeline"] = list(clean["timeline"])[-max_timeline:]
