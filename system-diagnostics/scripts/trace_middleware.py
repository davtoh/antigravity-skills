#!/usr/bin/env python3
"""Zero-dependency framework middleware for Runtime Diagnostic Trace Recorder.

Provides:
- DiagnosticTraceMiddleware: Framework-agnostic pure ASGI middleware (FastAPI, Starlette, Litestar).
- DiagnosticWSGIMiddleware: WSGI middleware (Flask, Django).
"""

from typing import Any, Callable, Dict, Optional
from pathlib import Path

RECORDING_HEADER = "x-debug-recording-id"
_MAX_RECORDING_ID = 64


def _clean_recording_id(value: Any) -> Optional[str]:
    """Return a safe recording id or None (header values are untrusted input)."""
    text = str(value or "").strip()
    ok = text and text.isascii() and len(text) <= _MAX_RECORDING_ID and all(c.isalnum() or c in "-_." for c in text)
    return text if ok else None


def _add_recording_id(context: Dict[str, Any], value: Any) -> None:
    rid = _clean_recording_id(value)
    if rid:
        context["recording_id"] = rid


class DiagnosticTraceMiddleware:
    """Framework-agnostic pure ASGI middleware capturing unhandled exceptions into trace catalog."""

    def __init__(self, app: Any, workspace_root: Optional[Path] = None):
        self.app = app
        self.workspace_root = workspace_root

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        try:
            await self.app(scope, receive, send)
        except Exception as exc:
            import trace_recorder

            client = scope.get("client")
            client_host = client[0] if client and len(client) > 0 else "unknown"
            raw_path = scope.get("path", "/")
            method = scope.get("method", "UNKNOWN")

            context = {
                "http_method": method,
                "http_path": raw_path,
                "client_host": client_host,
            }
            for key, val in scope.get("headers") or []:
                if bytes(key).lower() == RECORDING_HEADER.encode():
                    _add_recording_id(context, bytes(val).decode("latin-1"))
                    break
            trace_recorder.record_exception(exc, context=context, workspace_root=self.workspace_root)
            raise exc


class DiagnosticWSGIMiddleware:
    """Standard WSGI middleware capturing unhandled HTTP exceptions into trace catalog."""

    def __init__(self, app: Any, workspace_root: Optional[Path] = None):
        self.app = app
        self.workspace_root = workspace_root

    def __call__(self, environ: Dict[str, Any], start_response: Callable) -> Any:
        try:
            return self.app(environ, start_response)
        except Exception as exc:
            import trace_recorder

            context = {
                "http_method": environ.get("REQUEST_METHOD", "GET"),
                "http_path": environ.get("PATH_INFO", "/"),
                "client_host": environ.get("REMOTE_ADDR", "unknown"),
            }
            _add_recording_id(context, environ.get("HTTP_X_DEBUG_RECORDING_ID"))
            trace_recorder.record_exception(exc, context=context, workspace_root=self.workspace_root)
            raise exc
