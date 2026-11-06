#!/usr/bin/env python3
"""Universal Runtime Diagnostic Trace Recorder & Catalog Aggregator (system-diagnostics).

Captures unhandled exceptions across main threads, background worker threads,
and asyncio event loops. Generates deterministic error fingerprints for deduplication
and enriches an aggregated SSOT catalog (<workspace>/.diagnostics/trace_catalog.json)
alongside daily JSONL trace logs (<workspace>/.diagnostics/traces/trace_YYYYMMDD.jsonl).

Zero third-party dependencies: strictly uses Python standard library.
"""

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import threading
import traceback
from typing import Any

# Optional ASGI / WSGI middleware re-exports
try:
    from trace_middleware import DiagnosticTraceMiddleware, DiagnosticWSGIMiddleware
except ImportError:
    DiagnosticTraceMiddleware = None  # type: ignore
    DiagnosticWSGIMiddleware = None  # type: ignore

# Global singleton state
_INSTALLED = False
_WORKSPACE_ROOT: Path | None = None
_LOCK = threading.RLock()


def _sanitize_message(msg: str) -> str:
    """Normalize dynamic values (PIDs, hex pointers, timestamps) from messages for fingerprinting."""
    if not msg:
        return ""
    # Strip hex memory addresses: 0x0000021A87536660
    msg = re.sub(r"0x[0-9a-fA-F]+", "0x...", msg)
    # Strip numeric PIDs / port numbers / timestamps
    msg = re.sub(r"\b\d{4,}\b", "<N>", msg)
    return msg.strip()


def generate_trace_fingerprint(
    exception_type: str,
    culprit_file: str,
    culprit_func: str,
    message: str,
) -> str:
    """Generate a deterministic 6-character hex fingerprint for deduplicating related traces."""
    norm_file = culprit_file.replace("\\", "/").lower()
    norm_func = culprit_func.lower()
    norm_msg = _sanitize_message(message).lower()
    raw = f"{exception_type}:{norm_file}:{norm_func}:{norm_msg}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:6]
    clean_type = re.sub(r"[^A-Za-z0-9]", "", exception_type)[:8].upper()
    return f"TRC-{clean_type}-{digest}"


def extract_trace_event(
    exc_type: type[BaseException] | str,
    exc_value: BaseException | str,
    exc_tb: Any = None,
    context: dict[str, Any] | None = None,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    """Extract structured, machine-readable trace event from an exception."""
    type_name = exc_type.__name__ if isinstance(exc_type, type) else str(exc_type)
    msg_str = str(exc_value) if exc_value is not None else ""

    frames = []
    culprit_file = "unknown"
    culprit_line = 0
    culprit_func = "unknown"

    if exc_tb is not None and hasattr(exc_tb, "tb_frame"):
        extracted = traceback.extract_tb(exc_tb)
        for frame in extracted:
            f_path = frame.filename
            if workspace_root:
                try:
                    f_path = str(Path(f_path).resolve().relative_to(workspace_root.resolve())).replace("\\", "/")
                except (ValueError, RuntimeError):
                    pass
            frames.append(f"File '{f_path}', line {frame.lineno}, in {frame.name}: {frame.line}")

        if extracted:
            last = extracted[-1]
            culprit_file = last.filename
            if workspace_root:
                try:
                    culprit_file = str(Path(culprit_file).resolve().relative_to(workspace_root.resolve())).replace("\\", "/")
                except (ValueError, RuntimeError):
                    pass
            culprit_line = last.lineno or 0
            culprit_func = last.name or "unknown"
    else:
        frames = [msg_str]

    fingerprint = generate_trace_fingerprint(type_name, culprit_file, culprit_func, msg_str)
    now_utc = datetime.now(timezone.utc).isoformat()

    return {
        "fingerprint": fingerprint,
        "timestamp": now_utc,
        "severity": "ERROR",
        "exception_type": type_name,
        "message": msg_str,
        "culprit_file": culprit_file,
        "culprit_line": culprit_line,
        "culprit_func": culprit_func,
        "traceback": frames,
        "environment": {
            "python_version": sys.version.split()[0],
            "platform": sys.platform,
            "pid": os.getpid(),
        },
        "context": context or {},
    }


class TraceCatalogManager:
    """Manages thread-safe persistence and enrichment of runtime traces in .diagnostics/."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self.diag_dir = self.workspace_root / ".diagnostics"
        self.traces_dir = self.diag_dir / "traces"
        self.catalog_path = self.diag_dir / "trace_catalog.json"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.traces_dir.mkdir(parents=True, exist_ok=True)

    def load_catalog(self) -> dict[str, Any]:
        """Load catalog from disk or initialize a blank schema."""
        if not self.catalog_path.exists():
            return {
                "schema_version": "1.0",
                "workspace": str(self.workspace_root).replace("\\", "/"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "summary": {"total_events": 0, "unique_issues": 0, "active": 0, "resolved": 0},
                "issues": [],
            }
        try:
            with open(self.catalog_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {
                "schema_version": "1.0",
                "workspace": str(self.workspace_root).replace("\\", "/"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "summary": {"total_events": 0, "unique_issues": 0, "active": 0, "resolved": 0},
                "issues": [],
            }

    def save_catalog(self, catalog: dict[str, Any]) -> None:
        """Atomically persist catalog to disk."""
        catalog["updated_at"] = datetime.now(timezone.utc).isoformat()
        tmp_path = self.catalog_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2)
        os.replace(tmp_path, self.catalog_path)

    def record_trace(self, event: dict[str, Any]) -> dict[str, Any]:
        """Record event into daily JSONL and enrich existing issue or create new issue in catalog."""
        # 1. Append raw event to daily JSONL log
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        daily_log = self.traces_dir / f"trace_{date_str}.jsonl"
        with open(daily_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

        # 2. Enrich or insert into trace_catalog.json
        catalog = self.load_catalog()
        fp = event["fingerprint"]
        issue = next((item for item in catalog.get("issues", []) if item.get("fingerprint") == fp), None)

        if issue:
            issue["occurrence_count"] = issue.get("occurrence_count", 1) + 1
            issue["last_seen"] = event["timestamp"]
            # Enrich sample contexts without unbounded growth (max 5 distinct samples)
            sample_contexts = issue.setdefault("sample_contexts", [])
            new_ctx = event.get("context")
            if new_ctx and new_ctx not in sample_contexts and len(sample_contexts) < 5:
                sample_contexts.append(new_ctx)
            # Enrich sample messages if distinct
            sample_messages = issue.setdefault("sample_messages", [])
            msg = event.get("message", "")
            if msg and msg not in sample_messages and len(sample_messages) < 5:
                sample_messages.append(msg)
        else:
            issue_count = len(catalog.get("issues", [])) + 1
            issue = {
                "id": f"TRC-{issue_count:03d}",
                "fingerprint": fp,
                "exception_type": event["exception_type"],
                "culprit_file": event["culprit_file"],
                "culprit_line": event["culprit_line"],
                "culprit_func": event["culprit_func"],
                "first_seen": event["timestamp"],
                "last_seen": event["timestamp"],
                "occurrence_count": 1,
                "status": "active",
                "sample_messages": [event["message"]] if event.get("message") else [],
                "sample_contexts": [event["context"]] if event.get("context") else [],
            }
            catalog.setdefault("issues", []).append(issue)

        # Update summary counters
        total_events = sum(item.get("occurrence_count", 1) for item in catalog["issues"])
        unique_issues = len(catalog["issues"])
        active_issues = sum(1 for item in catalog["issues"] if item.get("status") == "active")
        resolved_issues = sum(1 for item in catalog["issues"] if item.get("status") == "resolved")
        catalog["summary"] = {
            "total_events": total_events,
            "unique_issues": unique_issues,
            "active": active_issues,
            "resolved": resolved_issues,
        }

        self.save_catalog(catalog)
        return issue


def record_exception(
    exc: BaseException,
    context: dict[str, Any] | None = None,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    """Capture, enrich, and persist an exception explicitly."""
    ws = workspace_root or _WORKSPACE_ROOT or Path.cwd()
    with _LOCK:
        event = extract_trace_event(type(exc), exc, exc.__traceback__, context=context, workspace_root=ws)
        mgr = TraceCatalogManager(ws)
        return mgr.record_trace(event)


def install_trace_recorder(workspace_root: Path | None = None) -> bool:
    """Install global exception hooks for sys, threading, and asyncio."""
    global _INSTALLED, _WORKSPACE_ROOT
    if _INSTALLED:
        return True

    _WORKSPACE_ROOT = (workspace_root or Path.cwd()).resolve()
    orig_excepthook = sys.excepthook

    def _sys_hook(exc_type, exc_value, exc_tb):
        try:
            if not issubclass(exc_type, KeyboardInterrupt):
                with _LOCK:
                    event = extract_trace_event(exc_type, exc_value, exc_tb, workspace_root=_WORKSPACE_ROOT)
                    mgr = TraceCatalogManager(_WORKSPACE_ROOT)
                    mgr.record_trace(event)
        except Exception:
            pass
        orig_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = _sys_hook

    orig_thread_hook = getattr(threading, "excepthook", None)

    def _thread_hook(args):
        try:
            with _LOCK:
                event = extract_trace_event(
                    args.exc_type,
                    args.exc_value,
                    args.exc_traceback,
                    context={"thread_name": args.thread.name if args.thread else "unknown"},
                    workspace_root=_WORKSPACE_ROOT,
                )
                mgr = TraceCatalogManager(_WORKSPACE_ROOT)
                mgr.record_trace(event)
        except Exception:
            pass
        if orig_thread_hook:
            orig_thread_hook(args)

    threading.excepthook = _thread_hook

    _INSTALLED = True
    return True


def register_parser(sub: Any) -> None:
    """Register 'traces' subparser."""
    p = sub.add_parser("traces", help="Inspect, summarize, and manage runtime crash and trace catalog")
    p.add_argument("--path", default=None, help="Root directory (default: current directory)")
    p.add_argument("--recent", type=int, default=5, help="Number of recent issues to display (default: 5)")
    p.add_argument("--json", action="store_true", help="Output full JSON catalog")
    p.add_argument("--clear", action="store_true", help="Clear active trace catalog and logs")
    p.add_argument("--scaffold", choices=["fastapi", "flask", "generic"], help="Scaffold framework connector bridge")
    p.add_argument("--dest", default="services", help="Destination folder for scaffold bridge (default: services)")


def cmd_traces(args: Any) -> int:
    """CLI handler for 'diagnose.py traces'."""
    if getattr(args, "scaffold", None):
        import connector_scaffolder
        setattr(args, "framework", args.scaffold)
        return connector_scaffolder.cmd_traces_scaffold(args)

    root = Path(args.path).resolve() if getattr(args, "path", None) else Path.cwd().resolve()
    mgr = TraceCatalogManager(root)

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

    issues = catalog.get("issues", [])
    summary = catalog.get("summary", {})
    print(f"\n=== Runtime Trace Catalog ({root.name}) ===")
    print(
        f"Total Events: {summary.get('total_events', 0)} | "
        f"Unique Issues: {summary.get('unique_issues', 0)} | "
        f"Active: {summary.get('active', 0)} | "
        f"Resolved: {summary.get('resolved', 0)}"
    )

    if not issues:
        print("  ✓ Zero runtime crashes or tracebacks recorded.\n")
        return 0

    recent = getattr(args, "recent", 5)
    sorted_issues = sorted(issues, key=lambda x: x.get("last_seen", ""), reverse=True)[:recent]

    for item in sorted_issues:
        iid = item.get("id", "TRC-???")
        exc = item.get("exception_type", "Exception")
        count = item.get("occurrence_count", 1)
        last_seen = item.get("last_seen", "")
        file_loc = f"{item.get('culprit_file')}:{item.get('culprit_line')}"
        func = item.get("culprit_func", "")
        print(f"\n[{iid}] {exc} (x{count}) | Last seen: {last_seen}")
        print(f"  Location: {file_loc} in {func}()")
        samples = item.get("sample_messages", [])
        if samples:
            print(f"  Message:  {samples[-1]}")
        contexts = item.get("sample_contexts", [])
        if contexts:
            print(f"  Context:  {contexts[-1]}")
    print()
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_script = sys.argv[1]
        install_trace_recorder()
        sys.argv = sys.argv[1:]
        with open(target_script, "rb") as _f:
            code = compile(_f.read(), target_script, "exec")
        globals_dict = {"__name__": "__main__", "__file__": os.path.abspath(target_script)}
        exec(code, globals_dict)
    else:
        print("Universal Runtime Diagnostic Trace Recorder")
        print("Usage: python -m trace_recorder <script.py> [args...]")


