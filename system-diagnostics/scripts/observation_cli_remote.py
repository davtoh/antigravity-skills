#!/usr/bin/env python3
"""`observations pull` and `observations verify-connector` handlers (hooked into observation_cli)."""

import json
from pathlib import Path
from typing import Any

import observation_pull as pull
import observation_verify as verify

ACTIONS = ["pull", "verify-connector"]


def add_flags(p: Any) -> None:
    p.add_argument("--url", default=None, help="pull/verify-connector: app base URL, e.g. http://127.0.0.1:8000")
    p.add_argument("--allow-remote", action="store_true", help="pull: allow a non-loopback host (warns)")
    p.add_argument("--timeout", type=float, default=10.0, help="pull/verify-connector: seconds per request")


def _err(action: str, msg: str, code: int) -> int:
    print(f"[diagnose observations {action}] Error: {msg}", flush=True)
    return code


def _pull(ws: Path, a: Any) -> int:
    if not a.url:
        return _err("pull", "--url is required", 2)
    try:
        warning = pull.check_url(a.url, a.allow_remote)
        if warning:
            print(warning, flush=True)
        counts = pull.pull(ws, a.url, a.status or "all", a.kind, a.timeout)
    except pull.PullUsageError as exc:
        return _err("pull", str(exc), 2)
    except pull.PullError as exc:
        return _err("pull", f"{exc}; nothing written", 1)
    total = counts["new"] + counts["updated"] + counts["unchanged"]
    if a.json:
        print(json.dumps({"pulled": total, **counts}))
    else:
        print(f"pulled {total} (new {counts['new']}, updated {counts['updated']}, unchanged {counts['unchanged']})")
        if counts["truncated"]:
            print("note: remote list truncated at 200; narrow with --status or --kind")
    return 0


def _verify(ws: Path, a: Any) -> int:
    if not a.url:
        return _err("verify-connector", "--url is required", 2)
    try:
        results = verify.run(a.url, a.timeout)
    except pull.PullError as exc:
        return _err("verify-connector", str(exc), 1)
    ok = verify.passed(results)
    if a.json:
        print(json.dumps({"ok": ok, "checks": results}, indent=2))
    else:
        for r in results:
            print(f"{r['result']:<4} {r['check']}" + (f": {r['detail']}" if r["detail"] else ""))
        print("CONFORMANT" if ok else "NOT CONFORMANT")
    return 0 if ok else 1


HANDLERS = {"pull": _pull, "verify-connector": _verify}
