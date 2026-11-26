#!/usr/bin/env python3
"""`observations pull`: import observations from a running app's Wire Contract v1 routes.

Atomic: every fetch completes before the single catalog save, so any failure writes nothing.
Stdlib `urllib` only; redirects are never followed (a redirect could leave loopback).
"""

import json
from pathlib import Path
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

import observation_merge as merge
import observation_store as store

BASE_PATH = "/api/diagnostics"
CONTRACT_VERSION = 1
LOOPBACK = ("127.0.0.1", "::1", "localhost")
MAX_BODY = 2 * 1024 * 1024


class PullError(Exception):
    """Network or contract failure (CLI exit 1, nothing written)."""


class PullUsageError(Exception):
    """Refused before any request (CLI exit 2)."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
        return None


def api_base(url: str) -> str:
    base = url.rstrip("/")
    return base if base.endswith(BASE_PATH) else base + BASE_PATH


def check_url(url: str, allow_remote: bool) -> str | None:
    """Validate scheme and host; return a warning when a remote host is allowed."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise PullUsageError(f"--url must be http(s)://host[:port], got {url!r}")
    if parts.hostname in LOOPBACK:
        return None
    if not allow_remote:
        raise PullUsageError(f"refusing non-loopback host {parts.hostname!r}; pass --allow-remote to override")
    return f"WARNING: pulling debug data from non-loopback host {parts.hostname!r}"


def get_json(url: str, timeout: float) -> tuple[dict[str, Any], dict[str, str]]:
    """GET `url`; return (parsed JSON object, headers). Raises PullError on any failure."""
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=timeout) as resp:
            raw = resp.read(MAX_BODY + 1)
            headers = {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as exc:
        exc.close()
        raise PullError(f"{url} answered HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise PullError(f"cannot reach {url}: {getattr(exc, 'reason', exc)}") from exc
    if len(raw) > MAX_BODY:
        raise PullError(f"{url} response exceeds {MAX_BODY} bytes")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise PullError(f"{url} did not return JSON") from exc
    if not isinstance(data, dict):
        raise PullError(f"{url} did not return a JSON object")
    return data, headers


def preflight(base: str, timeout: float) -> None:
    health, headers = get_json(base + "/health", timeout)
    version = health.get("contract_version")
    if version != CONTRACT_VERSION or headers.get("x-diagnostics-contract") != str(CONTRACT_VERSION):
        raise PullError(f"contract mismatch: expected {CONTRACT_VERSION}, app reports {version!r}")
    if health.get("enabled") is not True:
        raise PullError("app reports diagnostics disabled")


def pull(ws: Path, url: str, status: str = "all", kind: str | None = None, timeout: float = 10.0) -> dict[str, Any]:
    """Fetch and merge; returns counts plus `truncated`. One atomic save at the end."""
    base = api_base(url)
    preflight(base, timeout)
    query = {"status": status, "limit": "200"}
    if kind:
        query["kind"] = kind
    listing, _ = get_json(base + "/observations?" + urllib.parse.urlencode(query), timeout)
    catalog = store.load_catalog(ws)
    counts = {"new": 0, "updated": 0, "unchanged": 0}
    for item in listing.get("observations", []):
        if not merge.needs_fetch(catalog, item):
            counts["unchanged"] += 1
            continue
        full, _ = get_json(f"{base}/observations/{urllib.parse.quote(str(item.get('id', '')))}", timeout)
        try:
            counts[merge.merge_remote(catalog, full, url)] += 1
        except ValueError as exc:
            raise PullError(f"invalid remote entry {item.get('id')}: {exc}") from exc
    if counts["new"] or counts["updated"]:
        store.save_catalog(ws, catalog)
    counts["truncated"] = bool(listing.get("truncated"))
    return counts
