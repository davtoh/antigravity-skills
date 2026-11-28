#!/usr/bin/env python3
"""`observations verify-connector`: conformance run against an app's Wire Contract v1 routes.

Each check is `PASS`, `FAIL` (expected vs actual) or `SKIP` (reason). Never stores data: every
POST uses `?dry_run=1`. Stdlib `urllib` only; redirects are not followed.
"""

import json
from typing import Any, Callable
import urllib.error
import urllib.request

import observation_pull as pull

VALID = {"kind": "note", "page_path": "/__verify__", "message": "verify-connector dry run"}
OVERSIZE = {"kind": "note", "message": "x", "attrs": {"pad": "p" * 70000}}
Resp = tuple[int, dict[str, str], bytes]


class _Client:
    """Tiny HTTP client that returns error statuses instead of raising and records every response."""

    def __init__(self, base: str, timeout: float) -> None:
        self.base = base
        self.timeout = timeout
        self.seen: list[tuple[str, dict[str, str]]] = []
        self._opener = urllib.request.build_opener(pull._NoRedirect)

    def call(self, method: str, path: str, body: bytes | None = None, ctype: str | None = None) -> Resp:
        headers = {"Content-Type": ctype} if ctype else {}
        req = urllib.request.Request(self.base + path, data=body, method=method, headers=headers)
        try:
            with self._opener.open(req, timeout=self.timeout) as resp:
                out = (resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read(pull.MAX_BODY))
        except urllib.error.HTTPError as exc:
            out = (exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read(pull.MAX_BODY))
            exc.close()
        except (urllib.error.URLError, OSError) as exc:
            raise pull.PullError(f"cannot reach {self.base + path}: {getattr(exc, 'reason', exc)}") from exc
        self.seen.append((method + " " + path, out[1]))
        return out


def _json(resp: Resp) -> dict[str, Any]:
    try:
        data = json.loads(resp[2].decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except (ValueError, UnicodeDecodeError):
        return {}


def _expect(name: str, ok: bool, expected: str, actual: Any) -> dict[str, str]:
    return {"check": name, "result": "PASS" if ok else "FAIL",
            "detail": "" if ok else f"expected {expected}; actual {actual}"}


def _post(c: _Client, rec: Any, ctype: str = "application/json", raw: bytes | None = None) -> Resp:
    body = raw if raw is not None else json.dumps(rec).encode("utf-8")
    return c.call("POST", "/observation?dry_run=1", body, ctype)


def _check_health(c: _Client) -> dict[str, str]:
    r = c.call("GET", "/health")
    d = _json(r)
    ok = r[0] == 200 and d.get("contract_version") == 1 and d.get("enabled") is True and "store" in d
    return _expect("health shape and contract_version", ok, "200 with enabled=true, contract_version=1, store", (r[0], d))


def _check_dry_run(c: _Client) -> dict[str, str]:
    r = _post(c, VALID)
    return _expect("POST dry_run valid record", r[0] == 200 and _json(r).get("dry_run") is True,
                   "200 {dry_run: true}", (r[0], _json(r)))


def _error_check(name: str, resp: Resp, status: int, code: str) -> dict[str, str]:
    return _expect(name, resp[0] == status and _json(resp).get("error") == code,
                   f"{status} {code}", (resp[0], _json(resp).get("error")))


def _check_list(c: _Client) -> dict[str, str]:
    r = c.call("GET", "/observations?status=all&limit=1&kind=idea")
    d = _json(r)
    items = d.get("observations")
    ok = (r[0] == 200 and isinstance(items, list) and d.get("count") == len(items) <= 1
          and "truncated" in d and all(i.get("kind") == "idea" for i in items))
    return _expect("GET /observations shape, limit and kind", ok, "200, count<=1, only kind=idea", (r[0], d))


def _check_hud(c: _Client) -> dict[str, str]:
    r = c.call("GET", "/hud.js")
    ok = r[0] == 200 and "javascript" in r[1].get("content-type", "") and "no-store" in r[1].get("cache-control", "")
    return _expect("GET /hud.js content type and no-store", ok, "200, javascript, Cache-Control no-store",
                   (r[0], r[1].get("content-type"), r[1].get("cache-control")))


def _check_redaction(c: _Client) -> dict[str, str]:
    r = _post(c, {**VALID, "value": "secret", "attrs": {"password": "secret", "id": "a"}})
    preview = _json(r).get("accepted")
    if r[0] != 200:
        return _expect("redaction of value/password", False, "200 accepting the record", r[0])
    if preview is None:
        return {"check": "redaction of value/password", "result": "SKIP", "detail": "app returns no `accepted` preview"}
    return _expect("redaction of value/password", "secret" not in json.dumps(preview), "no secret in preview", preview)


def _check_header(c: _Client) -> dict[str, str]:
    missing = [name for name, h in c.seen if h.get("x-diagnostics-contract") != "1"]
    return _expect("X-Diagnostics-Contract on every response", not missing, "header '1' on all responses", missing)


def run(url: str, timeout: float = 10.0) -> list[dict[str, str]]:
    """Run every check in contract order. Raises PullError only when the app is unreachable."""
    c = _Client(pull.api_base(url), timeout)
    health = _check_health(c)  # also proves reachability; a network error propagates below
    checks: list[Callable[[], dict[str, str]]] = [
        lambda: _check_dry_run(c),
        lambda: _error_check("invalid_json -> 400", _post(c, None, raw=b"{not json"), 400, "invalid_json"),
        lambda: _error_check("invalid_record -> 400", _post(c, {"kind": "bogus"}), 400, "invalid_record"),
        lambda: _error_check("oversize -> 413", _post(c, OVERSIZE), 413, "payload_too_large"),
        lambda: _error_check("wrong content type -> 415", _post(c, VALID, ctype="text/plain"), 415, "unsupported_media_type"),
        lambda: _check_list(c),
        lambda: _error_check("unknown id -> 404", c.call("GET", "/observations/OBS-DOES-NOT-EXIST"), 404, "not_found"),
        lambda: _check_hud(c),
        lambda: _check_redaction(c),
    ]
    results = [health] + [fn() for fn in checks]
    results.insert(1, _check_header(c))
    results.append({"check": "non-loopback -> 403", "result": "SKIP",
                    "detail": "cannot be tested from loopback; verify manually from another host"})
    return results


def passed(results: list[dict[str, str]]) -> bool:
    return all(r["result"] != "FAIL" for r in results)
