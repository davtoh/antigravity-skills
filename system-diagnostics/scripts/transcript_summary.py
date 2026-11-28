#!/usr/bin/env python3
"""Metrics-only session summaries that survive transcript cleanup (decision D7).

``export_summary`` writes ``.diagnostics/retro/<vendor>-<id8>.json``; every string is clamped to
120 characters and nothing raw is stored. ``read_summary`` rebuilds a row (``from_summary: true``).
"""

import json
from pathlib import Path
from typing import Any

SNIPPET_MAX = 120
_DIR = Path(".diagnostics") / "retro"


def _clamp(value: Any) -> Any:
    if isinstance(value, str):
        return value[:SNIPPET_MAX]
    if isinstance(value, list):
        return [_clamp(v) for v in value]
    if isinstance(value, dict):
        return {str(k)[:SNIPPET_MAX]: _clamp(v) for k, v in value.items()}
    return value


def summary_path(root: Path, vendor: str, cid: str) -> Path:
    return root / _DIR / f"{vendor}-{cid[:8]}.json"


def export_summary(root: Path, row: dict[str, Any]) -> Path | None:
    """Write the summary for an audited (non-missing) row; returns the file or ``None``."""
    if row.get("missing") or not row.get("cid"):
        return None
    path = summary_path(root, str(row.get("vendor", "gemini")), str(row["cid"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_clamp(row), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def read_summary(root: Path, token: str) -> dict[str, Any] | None:
    """Return the stored row whose id starts with ``token`` (>= 6 chars, unique), else ``None``."""
    low = token.strip().lower()
    folder = root / _DIR
    if len(low) < 6 or not folder.is_dir():
        return None
    hits: list[dict[str, Any]] = []
    for f in sorted(folder.glob("*.json")):
        try:
            row = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(row, dict) and str(row.get("cid", "")).lower().startswith(low):
            hits.append(row)
    return {**hits[0], "from_summary": True} if len(hits) == 1 else None
