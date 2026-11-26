#!/usr/bin/env python3
"""Last-known probe results (`.diagnostics/probe_last_run.json`), read by `diagnose.py brief`."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HISTORY_NAME = "probe_last_run.json"


def _path(workspace: Path) -> Path:
    return Path(workspace) / ".diagnostics" / HISTORY_NAME


def load(workspace: Path) -> dict[str, dict[str, Any]]:
    """Return {probe: {status, summary, ran_at, latency_ms}}; empty on missing or corrupt file."""
    try:
        data = json.loads(_path(workspace).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def record(workspace: Path, result: dict[str, Any]) -> None:
    """Atomically store the latest result for one probe. Never raises (history is best-effort)."""
    name = str(result.get("probe") or "")
    if not name:
        return
    try:
        history = load(workspace)
        history[name] = {
            "status": str(result.get("status", "error")),
            "summary": str(result.get("summary", ""))[:200],
            "latency_ms": result.get("latency_ms", 0),
            "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        path = _path(workspace)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(history, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        return


def age(ran_at: str, now: datetime | None = None) -> str:
    """Human age such as `5m`, `3h`, `2d`; `unknown` when the timestamp is unparseable."""
    try:
        then = datetime.fromisoformat(str(ran_at).replace("Z", "+00:00"))
    except ValueError:
        return "unknown"
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    secs = max(0, int(((now or datetime.now(timezone.utc)) - then).total_seconds()))
    if secs < 3600:
        return f"{secs // 60}m"
    return f"{secs // 3600}h" if secs < 86400 else f"{secs // 86400}d"
