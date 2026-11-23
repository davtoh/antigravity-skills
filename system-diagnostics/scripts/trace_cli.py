#!/usr/bin/env python3
"""CLI subparser registration and formatting for `diagnose.py traces`."""

import json
from pathlib import Path
from typing import Any


def register_parser(sub: Any) -> None:
    """Register 'traces' subparser."""
    p = sub.add_parser("traces", help="Inspect, summarize, and manage runtime crash and trace catalog")
    p.add_argument("action", nargs="?", choices=["list", "resolve"], default="list", help="Action: list (default) or resolve")
    p.add_argument("--id", dest="issue_id", default=None, help="Trace issue ID for 'resolve' (e.g. TRC-001)")
    p.add_argument("--note", default=None, help="Optional resolution audit note for 'resolve'")
    p.add_argument("--path", default=None, help="Root directory (default: current directory)")
    p.add_argument("--recent", type=int, default=5, help="Number of recent issues to display (default: 5)")
    p.add_argument("--json", action="store_true", help="Output full JSON catalog")
    p.add_argument("--clear", action="store_true", help="Clear active trace catalog and logs")
    p.add_argument("--scaffold", choices=["fastapi", "flask", "generic"], help="Scaffold framework connector bridge")
    p.add_argument("--dest", default="services", help="Destination folder for scaffold bridge (default: services)")


def resolve_trace_issue(mgr: Any, issue_id: str | None, note: str | None = None) -> int:
    """Mark a trace issue by ID as resolved in trace_catalog.json."""
    if not issue_id:
        print("[diagnose traces resolve] Error: --id <TRC-ID> is required.", flush=True)
        return 2
    catalog = mgr.load_catalog()
    target = issue_id.strip().upper()
    matched = next((i for i in catalog.get("issues", []) if i.get("id", "").upper() == target), None)
    if not matched:
        print(f"[diagnose traces resolve] Error: Issue '{issue_id}' not found in {mgr.catalog_path}.")
        return 1
    matched["status"] = "resolved"
    if note:
        matched["resolution_note"] = note
    issues = catalog.get("issues", [])
    catalog["summary"] = {
        "total_events": sum(i.get("occurrence_count", 1) for i in issues),
        "unique_issues": len(issues),
        "active": sum(1 for i in issues if i.get("status") == "active"),
        "resolved": sum(1 for i in issues if i.get("status") == "resolved"),
    }
    mgr.save_catalog(catalog)
    print(f"[diagnose traces] Resolved {matched['id']} ({matched.get('exception_type')}).")
    return 0


def _print_trace_summary(root: Path, catalog: dict[str, Any], recent: int) -> None:
    """Print human-readable trace catalog summary."""
    issues = catalog.get("issues", [])
    s = catalog.get("summary", {})
    print(f"\n=== Runtime Trace Catalog ({root.name}) ===")
    print(
        f"Total Events: {s.get('total_events', 0)} | Unique Issues: {s.get('unique_issues', 0)} "
        f"| Active: {s.get('active', 0)} | Resolved: {s.get('resolved', 0)}"
    )
    if not issues:
        print("  ✓ Zero runtime crashes or tracebacks recorded.\n")
        return
    for item in sorted(issues, key=lambda x: x.get("last_seen", ""), reverse=True)[:recent]:
        print(f"\n[{item.get('id', 'TRC-???')}] {item.get('exception_type', 'Exception')} (x{item.get('occurrence_count', 1)}) | Status: {item.get('status', 'active')} | Last seen: {item.get('last_seen', '')}")
        print(f"  Location: {item.get('culprit_file')}:{item.get('culprit_line')} in {item.get('culprit_func', '')}()")
        if samples := item.get("sample_messages", []):
            print(f"  Message:  {samples[-1]}")
        if contexts := item.get("sample_contexts", []):
            print(f"  Context:  {contexts[-1]}")
    print()


def cmd_traces(args: Any, mgr_cls: Any) -> int:
    """CLI handler for 'diagnose.py traces'."""
    if getattr(args, "scaffold", None):
        import connector_scaffolder
        setattr(args, "framework", args.scaffold)
        return connector_scaffolder.cmd_traces_scaffold(args)
    root = Path(args.path).resolve() if getattr(args, "path", None) else Path.cwd().resolve()
    mgr = mgr_cls(root)
    if getattr(args, "action", "list") == "resolve":
        return resolve_trace_issue(mgr, getattr(args, "issue_id", None), getattr(args, "note", None))
    if getattr(args, "clear", False):
        if mgr.catalog_path.exists():
            mgr.catalog_path.unlink()
        for f in mgr.traces_dir.glob("trace_*.jsonl"):
            f.unlink()
        print(f"[diagnose traces] Cleared trace catalog and logs in {mgr.diag_dir}")
        return 0
    catalog = mgr.load_catalog()
    if getattr(args, "json", False):
        print(json.dumps(catalog, indent=2))
        return 0
    _print_trace_summary(root, catalog, getattr(args, "recent", 5))
    return 0
