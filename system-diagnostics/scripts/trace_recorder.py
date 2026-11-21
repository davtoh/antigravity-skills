#!/usr/bin/env python3
"""Universal Runtime Diagnostic Trace Recorder & Catalog Aggregator (system-diagnostics).

Captures unhandled exceptions across main threads, background worker threads,
and asyncio event loops. Generates deterministic error fingerprints for deduplication
and enriches an aggregated SSOT catalog (<workspace>/.diagnostics/trace_catalog.json)
alongside daily JSONL trace logs (<workspace>/.diagnostics/traces/trace_YYYYMMDD.jsonl).

Zero third-party dependencies: strictly uses Python standard library.
"""

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


def _is_test_runner_active() -> bool:
    """Return True when running under unittest/pytest unless DIAGNOSTICS_TRACE_IN_TESTS=1."""
    if os.environ.get("DIAGNOSTICS_TRACE_IN_TESTS") == "1":
        return False
    return "unittest" in sys.modules or "pytest" in sys.modules


def _sanitize_message(msg: str) -> str:
    """Normalize dynamic values (PIDs, hex pointers, timestamps) from messages for fingerprinting."""
    if not msg:
        return ""
    msg = re.sub(r"0x[0-9a-fA-F]+", "0x...", msg)
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


def _rel_frame_path(filename: str, workspace_root: Path | None) -> str:
    if not workspace_root:
        return filename
    try:
        return str(Path(filename).resolve().relative_to(workspace_root.resolve())).replace("\\", "/")
    except (ValueError, RuntimeError):
        return filename


def _extract_tb_frames(
    exc_tb: Any, msg_str: str, workspace_root: Path | None
) -> tuple[list[str], str, int, str]:
    if exc_tb is None or not hasattr(exc_tb, "tb_frame"):
        return [msg_str], "unknown", 0, "unknown"
    extracted = traceback.extract_tb(exc_tb)
    frames = [
        f"File '{_rel_frame_path(fr.filename, workspace_root)}', line {fr.lineno}, in {fr.name}: {fr.line}"
        for fr in extracted
    ]
    if not extracted:
        return frames, "unknown", 0, "unknown"
    last = extracted[-1]
    return frames, _rel_frame_path(last.filename, workspace_root), last.lineno or 0, last.name or "unknown"


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
    frames, culprit_file, culprit_line, culprit_func = _extract_tb_frames(exc_tb, msg_str, workspace_root)
    return {
        "fingerprint": generate_trace_fingerprint(type_name, culprit_file, culprit_func, msg_str),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": "ERROR",
        "exception_type": type_name,
        "message": msg_str,
        "culprit_file": culprit_file,
        "culprit_line": culprit_line,
        "culprit_func": culprit_func,
        "traceback": frames,
        "environment": {"python_version": sys.version.split()[0], "platform": sys.platform, "pid": os.getpid()},
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

    def _blank_catalog(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "workspace": str(self.workspace_root).replace("\\", "/"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {"total_events": 0, "unique_issues": 0, "active": 0, "resolved": 0},
            "issues": [],
        }

    def load_catalog(self) -> dict[str, Any]:
        """Load catalog from disk or initialize a blank schema."""
        if not self.catalog_path.exists():
            return self._blank_catalog()
        try:
            with open(self.catalog_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return self._blank_catalog()

    def save_catalog(self, catalog: dict[str, Any]) -> None:
        """Atomically persist catalog to disk."""
        catalog["updated_at"] = datetime.now(timezone.utc).isoformat()
        tmp_path = self.catalog_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2)
        os.replace(tmp_path, self.catalog_path)

    def _enrich_or_create(self, catalog: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
        fp = event["fingerprint"]
        issue = next((item for item in catalog.get("issues", []) if item.get("fingerprint") == fp), None)
        if issue:
            issue["occurrence_count"] = issue.get("occurrence_count", 1) + 1
            issue["last_seen"] = event["timestamp"]
            sc = issue.setdefault("sample_contexts", [])
            if (ctx := event.get("context")) and ctx not in sc and len(sc) < 5:
                sc.append(ctx)
            sm = issue.setdefault("sample_messages", [])
            if (msg := event.get("message", "")) and msg not in sm and len(sm) < 5:
                sm.append(msg)
            return issue
        issue_count = len(catalog.get("issues", [])) + 1
        issue = {
            "id": f"TRC-{issue_count:03d}", "fingerprint": fp, "exception_type": event["exception_type"],
            "culprit_file": event["culprit_file"], "culprit_line": event["culprit_line"],
            "culprit_func": event["culprit_func"], "first_seen": event["timestamp"],
            "last_seen": event["timestamp"], "occurrence_count": 1, "status": "active",
            "sample_messages": [event["message"]] if event.get("message") else [],
            "sample_contexts": [event["context"]] if event.get("context") else [],
        }
        catalog.setdefault("issues", []).append(issue)
        return issue

    def record_trace(self, event: dict[str, Any]) -> dict[str, Any]:
        """Record event into daily JSONL and enrich existing issue or create new issue in catalog."""
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        with open(self.traces_dir / f"trace_{date_str}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
        catalog = self.load_catalog()
        issue = self._enrich_or_create(catalog, event)
        issues = catalog["issues"]
        catalog["summary"] = {
            "total_events": sum(item.get("occurrence_count", 1) for item in issues),
            "unique_issues": len(issues),
            "active": sum(1 for item in issues if item.get("status") == "active"),
            "resolved": sum(1 for item in issues if item.get("status") == "resolved"),
        }
        self.save_catalog(catalog)
        return issue


def record_exception(
    exc: BaseException,
    context: dict[str, Any] | None = None,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    """Capture, enrich, and persist an exception explicitly."""
    if workspace_root is None and _is_test_runner_active():
        return {"skipped": True, "reason": "test_runner_active"}
    ws = workspace_root or _WORKSPACE_ROOT or Path.cwd()
    with _LOCK:
        event = extract_trace_event(type(exc), exc, exc.__traceback__, context=context, workspace_root=ws)
        return TraceCatalogManager(ws).record_trace(event)


def _record_hook_event(exc_type: Any, exc_value: Any, exc_tb: Any, ctx: dict[str, Any] | None = None) -> None:
    try:
        with _LOCK:
            event = extract_trace_event(exc_type, exc_value, exc_tb, context=ctx, workspace_root=_WORKSPACE_ROOT)
            if _WORKSPACE_ROOT is not None:
                TraceCatalogManager(_WORKSPACE_ROOT).record_trace(event)
    except Exception:
        pass


def install_trace_recorder(workspace_root: Path | None = None) -> bool:
    """Install global exception hooks for sys and threading (skipped under test runners)."""
    global _INSTALLED, _WORKSPACE_ROOT
    if _is_test_runner_active():
        return False
    if _INSTALLED:
        return True
    _WORKSPACE_ROOT = (workspace_root or Path.cwd()).resolve()
    orig_excepthook = sys.excepthook
    orig_thread_hook = getattr(threading, "excepthook", None)

    def _sys_hook(exc_type: Any, exc_value: Any, exc_tb: Any) -> None:
        if not issubclass(exc_type, KeyboardInterrupt):
            _record_hook_event(exc_type, exc_value, exc_tb)
        orig_excepthook(exc_type, exc_value, exc_tb)

    def _thread_hook(args: Any) -> None:
        _record_hook_event(
            args.exc_type, args.exc_value, args.exc_traceback,
            {"thread_name": args.thread.name if args.thread else "unknown"},
        )
        if orig_thread_hook:
            orig_thread_hook(args)

    sys.excepthook = _sys_hook
    threading.excepthook = _thread_hook
    _INSTALLED = True
    return True


def register_parser(sub: Any) -> None:
    """Delegate 'traces' subparser registration to trace_cli."""
    try:
        import trace_cli
    except ImportError:
        from . import trace_cli
    trace_cli.register_parser(sub)


def cmd_traces(args: Any) -> int:
    """Delegate CLI handler for 'diagnose.py traces' to trace_cli."""
    try:
        import trace_cli
    except ImportError:
        from . import trace_cli
    return trace_cli.cmd_traces(args, TraceCatalogManager)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        import runpy
        target_script = sys.argv[1]
        install_trace_recorder()
        sys.argv = sys.argv[1:]
        runpy.run_path(target_script, run_name="__main__")
    else:
        print("Universal Runtime Diagnostic Trace Recorder\nUsage: python -m trace_recorder <script.py> [args...]")
