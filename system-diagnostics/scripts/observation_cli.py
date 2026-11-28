#!/usr/bin/env python3
"""CLI subparser and handlers for `diagnose.py observations` (system-diagnostics)."""

import json
from pathlib import Path
import subprocess
import sys
from typing import Any

try:
    import observation_store as store
    import observation_correlate as correlate
    import observation_cli_remote as remote
except ImportError:  # pragma: no cover - package-style import
    from . import observation_store as store
    from . import observation_correlate as correlate
    from . import observation_cli_remote as remote

ACTIONS = ["list", "show", "add", "triage", "resolve", "confirm", "dismiss"] + remote.ACTIONS
COMPACT_FIELDS = ("id", "fingerprint", "status", "kind", "page_path", "selector", "message", "occurrence_count", "last_seen")


def register_parser(sub: Any) -> None:
    """Register the 'observations' subparser."""
    p = sub.add_parser("observations", help="Capture, triage and resolve debug observations (HUD findings and ideas)")
    p.add_argument("action", nargs="?", choices=ACTIONS, default="list")
    p.add_argument("--path", default=None, help="Workspace root (default: current directory)")
    p.add_argument("--json", action="store_true", help="Machine-readable output")
    p.add_argument("--id", dest="obs_id", default=None, help="OBS-NNN or fingerprint")
    p.add_argument("--status", default=None, help="list: active|all|<status>; triage: triaged|in_progress")
    p.add_argument("--kind", default=None, choices=list(store.KINDS))
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--full", action="store_true", help="show: include full history")
    p.add_argument("--page", default="", help="add: page path")
    p.add_argument("--selector", default="", help="add: CSS selector")
    p.add_argument("--message", default=None, help="add: what was observed")
    p.add_argument("--recording-id", dest="recording_id", default=None)
    p.add_argument("--root-cause", dest="root_cause", default=None)
    p.add_argument("--plan", default=None, help="triage/resolve: linked or resolved plan slug")
    p.add_argument("--milestone", default=None, help="resolve: milestone identifier")
    p.add_argument("--task", default=None, help="resolve: task reference")
    p.add_argument("--base-commit", dest="base_commit", default=None, help="resolve: base commit SHA (auto pending:<sha> if --commit omitted)")
    p.add_argument("--missed-by", dest="missed_by", default=None, help="triage: comma list of " + ",".join(store.MISSED_BY))
    p.add_argument("--guard", default=None, help="triage: proposed guard (test/probe/rule)")
    p.add_argument("--resolution", default=None)
    p.add_argument("--commit", default=None)
    p.add_argument("--note", default=None, help="confirm: optional confirmation note")
    p.add_argument("--reason", default=None, help="dismiss: reason")
    remote.add_flags(p)


def _compact(entry: dict[str, Any]) -> dict[str, Any]:
    return {k: entry.get(k) for k in COMPACT_FIELDS}


def format_line(entry: dict[str, Any]) -> str:
    """`OBS-003 [open] element /dashboard button#save "Save does nothing" (2x, 2026-11-26)`."""
    day = str(entry.get("last_seen", ""))[:10]
    return (f'{entry["id"]} [{entry["status"]}] {entry["kind"]} {entry.get("page_path") or "-"} '
            f'{entry.get("selector") or "-"} "{entry.get("message", "")}" ({entry.get("occurrence_count", 1)}x, {day})')


def _err(action: str, msg: str, code: int) -> int:
    print(f"[diagnose observations {action}] Error: {msg}", flush=True)
    return code


def _list(ws: Path, a: Any) -> int:
    status = a.status or "active"
    valid = ("active", "all") + store.ACTIVE_STATUSES + store.CLOSED_STATUSES
    if status not in valid:
        return _err("list", f"invalid --status {status!r}", 2)
    items = store.list_observations(ws, status=status, limit=a.limit, kind=a.kind)
    if a.json:
        print(json.dumps([_compact(e) for e in items], indent=2, ensure_ascii=False))
    elif not items:
        print(f"No {status} observations." if status != "all" else "No observations.")
    else:
        for e in items:
            print(format_line(e))
    return 0


def _trace_summary(ws: Path, fp: str) -> str:
    cat = ws / ".diagnostics" / "trace_catalog.json"
    try:
        for issue in json.loads(cat.read_text(encoding="utf-8")).get("issues", []):
            if issue.get("fingerprint") == fp:
                return f'{fp} {issue.get("exception_type")} at {issue.get("culprit_file")}:{issue.get("culprit_line")}'
    except (OSError, ValueError):
        pass
    return fp


def _refresh_correlation(ws: Path, entry: dict[str, Any]) -> dict[str, Any]:
    if not (entry.get("recording_id") or entry.get("window")):
        return entry
    traces = correlate.correlate(entry, ws / ".diagnostics" / "traces")
    catalog = store.load_catalog(ws)
    live = next((e for e in catalog["observations"] if e["id"] == entry["id"]), None)
    if live is not None and live.get("correlated_traces") != traces:
        live["correlated_traces"] = traces
        store.save_catalog(ws, catalog)
    entry["correlated_traces"] = traces
    return entry


def _show(ws: Path, a: Any) -> int:
    if not a.obs_id:
        return _err("show", "--id is required", 2)
    entry = store.get_observation(ws, a.obs_id)
    if entry is None:
        return _err("show", f"'{a.obs_id}' not found", 1)
    entry = _refresh_correlation(ws, entry)
    if a.json:
        print(json.dumps(entry, indent=2, ensure_ascii=False))
        return 0
    print(format_line(entry))
    for key in ("rect", "attrs", "recording_id", "window", "root_cause", "missed_by", "proposed_guard",
                "resolution", "linked_plan", "linked_commit", "resolved_plan", "resolved_milestone",
                "resolved_task", "base_commit", "confirmed_at", "confirmed_note", "source_url"):
        if entry.get(key):
            print(f"  {key}: {entry[key]}")
    for ev in entry.get("timeline", []):
        print(f"  timeline: {json.dumps(ev, ensure_ascii=False)}")
    for fp in entry.get("correlated_traces", []):
        print(f"  trace: {_trace_summary(ws, fp)}")
    hist = entry.get("history", [])
    for h in (hist if a.full else hist[-3:]):
        print(f'  history: {h.get("ts")} {h.get("from")} -> {h.get("to")} {h.get("note", "")}')
    return 0


def _add(ws: Path, a: Any) -> int:
    if not a.kind or not a.message:
        return _err("add", "--kind and --message are required", 2)
    raw = {"kind": a.kind, "page_path": a.page, "selector": a.selector, "message": a.message,
           "recording_id": a.recording_id}
    try:
        entry, dedup = store.add_observation(ws, raw)
    except ValueError as exc:
        return _err("add", str(exc), 2)
    out = {"id": entry["id"], "fingerprint": entry["fingerprint"], "status": entry["status"], "deduplicated": dedup}
    print(json.dumps(out) if a.json else f'{"Updated" if dedup else "Added"} {entry["id"]} ({entry["fingerprint"]})')
    return 0


def _transition(ws: Path, a: Any, action: str, status: str, note: str, meta: dict[str, Any]) -> int:
    try:
        entry = store.update_status(ws, a.obs_id, status, note=note, **meta)
    except KeyError:
        return _err(action, f"'{a.obs_id}' not found", 1)
    except ValueError as exc:
        return _err(action, str(exc), 2)
    print(json.dumps(_compact(entry)) if a.json else f'{entry["id"]} -> {entry["status"]}')
    return 0


def _triage(ws: Path, a: Any) -> int:
    if not a.obs_id or not a.root_cause:
        return _err("triage", "--id and --root-cause are required", 2)
    status = a.status or "triaged"
    if status not in ("triaged", "in_progress"):
        return _err("triage", "--status must be triaged or in_progress", 2)
    meta = {"root_cause": a.root_cause, "linked_plan": a.plan, "missed_by": a.missed_by, "proposed_guard": a.guard}
    return _transition(ws, a, "triage", status, a.root_cause, meta)


def _git_short_head(ws: Path) -> str:
    try:
        p = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ws, capture_output=True, text=True, encoding="utf-8", timeout=5
        )
        return p.stdout.strip() if p.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _resolve(ws: Path, a: Any) -> int:
    if not a.obs_id or not a.resolution:
        return _err("resolve", "--id and --resolution are required", 2)
    base_commit = a.base_commit
    if not base_commit and not a.commit:
        sha = _git_short_head(ws)
        base_commit = f"pending:{sha}" if sha else None
    meta = {
        "resolution": a.resolution, "linked_commit": a.commit, "resolved_plan": a.plan,
        "resolved_milestone": a.milestone, "resolved_task": a.task, "base_commit": base_commit,
    }
    return _transition(ws, a, "resolve", "resolved", a.resolution, meta)


def _confirm(ws: Path, a: Any) -> int:
    if not a.obs_id:
        return _err("confirm", "--id is required", 2)
    note = a.note or ""
    return _transition(ws, a, "confirm", "confirmed", note, {"confirmed_note": note})


def _dismiss(ws: Path, a: Any) -> int:
    if not a.obs_id or not a.reason:
        return _err("dismiss", "--id and --reason are required", 2)
    return _transition(ws, a, "dismiss", "dismissed", a.reason, {"resolution": a.reason})


def cmd_observations(args: Any) -> int:
    """CLI handler for 'diagnose.py observations'."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ws = Path(args.path).resolve() if getattr(args, "path", None) else Path.cwd().resolve()
    handlers = {
        "list": _list, "show": _show, "add": _add, "triage": _triage,
        "resolve": _resolve, "confirm": _confirm, "dismiss": _dismiss, **remote.HANDLERS,
    }
    return handlers[getattr(args, "action", None) or "list"](ws, args)
