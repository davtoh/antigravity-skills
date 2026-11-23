#!/usr/bin/env python3
"""CDP browser discovery, URL matching, and runtime telemetry helpers."""

import os
import platform
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def _devtools_port_candidates() -> list[Path]:
    """Return OS-specific candidate paths for browser DevToolsActivePort."""
    system = platform.system().lower()
    home = Path.home()
    if system == "windows":
        lad = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return [
            lad / "Google" / "Chrome" / "User Data" / "DevToolsActivePort",
            lad / "Microsoft" / "Edge" / "User Data" / "DevToolsActivePort",
            lad / "Chromium" / "User Data" / "DevToolsActivePort",
        ]
    if system == "darwin":
        app_sup = home / "Library" / "Application Support"
        return [
            app_sup / "Google" / "Chrome" / "DevToolsActivePort",
            app_sup / "Microsoft Edge" / "DevToolsActivePort",
            app_sup / "Chromium" / "DevToolsActivePort",
        ]
    cfg = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    cands = [
        cfg / "google-chrome" / "DevToolsActivePort",
        cfg / "chromium" / "DevToolsActivePort",
        home / "snap" / "chromium" / "common" / "chromium" / "DevToolsActivePort",
    ]
    if Path("/mnt/c/Users").exists():
        cands.extend(Path("/mnt/c/Users").glob("*/AppData/Local/Google/Chrome/User Data/DevToolsActivePort"))
    return cands


def find_devtools_active_port() -> tuple[int, str] | None:
    """Locate browser DevToolsActivePort file across Windows, macOS, Linux, and WSL."""
    for path in _devtools_port_candidates():
        if path.exists():
            try:
                lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
                if len(lines) >= 2:
                    return int(lines[0]), lines[1]
            except Exception:
                pass
    return None


def urls_match(target_url: str, page_url: str) -> bool:
    """Return True if page_url matches target_url, treating localhost/127.0.0.1 equivalently."""
    if not target_url or not page_url:
        return False
    wanted = target_url.rstrip("/")
    if wanted in page_url:
        return True
    pw, pp = urlparse(wanted), urlparse(page_url)
    if (pw.hostname or "").lower() in _LOCAL_HOSTS and (pp.hostname or "").lower() in _LOCAL_HOSTS:
        w_port = pw.port or (443 if pw.scheme == "https" else 80)
        p_port = pp.port or (443 if pp.scheme == "https" else 80)
        return pw.scheme == pp.scheme and w_port == p_port and (pp.path or "/").startswith(pw.path or "")
    return False


async def enable_runtime_capture(cdp: Any, session_id: str | None) -> None:
    """Best-effort enable Log and Network domains for console/HTTP/WS capture."""
    for method in ("Log.enable", "Network.enable"):
        try:
            await cdp.send(method, session_id=session_id)
        except Exception:
            pass


def summarize_cdp_events(events: list[dict[str, Any]]) -> dict[str, list[Any]]:
    """Distill captured CDP events into bounded console, exception, and network error lists."""
    console_errors: list[str] = []
    exceptions: list[str] = []
    network_errors: list[dict[str, Any]] = []
    for ev in events:
        method, params = ev.get("method", ""), ev.get("params") or {}
        if method == "Runtime.consoleAPICalled" and params.get("type") in ("error", "assert"):
            txt = " ".join(str(a.get("value") or a.get("description") or "") for a in params.get("args", []))
            if txt:
                console_errors.append(txt[:200])
        elif method == "Log.entryAdded":
            entry = params.get("entry") or {}
            if entry.get("level") == "error" and entry.get("text"):
                console_errors.append(str(entry["text"])[:200])
        elif method == "Runtime.exceptionThrown":
            det = params.get("exceptionDetails") or {}
            desc = (det.get("exception") or {}).get("description") or det.get("text") or "Uncaught JS exception"
            exceptions.append(str(desc).splitlines()[0][:200])
        elif method == "Network.responseReceived":
            resp = params.get("response") or {}
            if int(resp.get("status", 0) or 0) >= 400:
                network_errors.append({"url": str(resp.get("url", ""))[:160], "status": resp.get("status")})
        elif method == "Network.loadingFailed":
            network_errors.append({"url": str(params.get("type", "")), "error": str(params.get("errorText", "failed"))[:120]})
        elif method == "Network.webSocketHandshakeResponseReceived":
            resp = params.get("response") or {}
            if int(resp.get("status", 0) or 0) >= 400:
                network_errors.append({"wsStatus": resp.get("status"), "text": str(resp.get("statusText", ""))[:120]})
    return {
        "consoleErrors": console_errors[:15],
        "exceptions": exceptions[:10],
        "networkErrors": network_errors[:15],
    }


async def collect_runtime_report(cdp: Any, session_id: str | None, evaluate_fn: Any) -> dict[str, Any]:
    """Drain CDP events and capture localStorage snapshot from the active page."""
    events = await cdp.drain_events(timeout=0.05) if hasattr(cdp, "drain_events") else list(getattr(cdp, "events", []))
    report: dict[str, Any] = summarize_cdp_events(events)
    try:
        ls = await evaluate_fn(
            cdp, session_id,
            "(() => { const o = {}; try { for (let i = 0; i < Math.min(localStorage.length, 30); i++) { const k = localStorage.key(i); o[k] = String(localStorage.getItem(k) || '').slice(0, 120); } } catch (_) {} return o; })()"
        )
        if isinstance(ls, dict) and "jsException" not in ls:
            report["localStorage"] = ls
    except Exception:
        pass
    return report
