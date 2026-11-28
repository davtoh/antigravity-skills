#!/usr/bin/env python3
"""Correlate observations with runtime exception traces (system-diagnostics).

Exact `context.recording_id` match first; timestamp-window fallback (+/- skew) otherwise.
Never raises on malformed trace lines or a missing traces directory.
"""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from typing import Any

_FILE_RE = re.compile(r"trace_(\d{8})\.jsonl$")


def parse_iso(ts: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp (trailing `Z` accepted); naive values are treated as UTC."""
    if not isinstance(ts, str) or not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def trace_files_for_window(traces_dir: Path, start: datetime | None, end: datetime | None) -> list[Path]:
    """Daily trace files whose date lies within [start, end] +/- 1 day (all files if no window)."""
    traces_dir = Path(traces_dir)
    if not traces_dir.is_dir():
        return []
    files = sorted(traces_dir.glob("trace_*.jsonl"))
    if start is None or end is None:
        return files
    lo, hi = (start - timedelta(days=1)).date(), (end + timedelta(days=1)).date()
    out = []
    for f in files:
        m = _FILE_RE.search(f.name)
        try:
            day = datetime.strptime(m.group(1), "%Y%m%d").date() if m else None
        except ValueError:
            day = None
        if day is not None and lo <= day <= hi:
            out.append(f)
    return out


def _iter_events(files: list[Path]):
    for f in files:
        try:
            handle = open(f, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with handle:
            for line in handle:
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if isinstance(ev, dict):
                    yield ev


def _window(obs: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
    win = obs.get("window") or {}
    if not isinstance(win, dict):
        return None, None
    return parse_iso(win.get("started_at")), parse_iso(win.get("stopped_at"))


def correlate(obs: dict[str, Any], traces_dir: Path, skew_s: float = 2.0) -> list[str]:
    """Return sorted unique `TRC-...` fingerprints correlated with the observation."""
    rec_id = obs.get("recording_id")
    start, end = _window(obs)
    if not rec_id and (start is None or end is None):
        return []
    files = trace_files_for_window(traces_dir, start, end)
    found: set[str] = set()
    skew = timedelta(seconds=skew_s)
    for ev in _iter_events(files):
        fp = ev.get("fingerprint")
        if not isinstance(fp, str):
            continue
        if rec_id:
            ctx = ev.get("context")
            if isinstance(ctx, dict) and ctx.get("recording_id") == rec_id:
                found.add(fp)
            continue
        when = parse_iso(ev.get("timestamp"))
        if when is not None and start - skew <= when <= end + skew:
            found.add(fp)
    return sorted(found)
