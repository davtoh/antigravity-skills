#!/usr/bin/env python3
"""Observation-route adapter templates appended to generated bridges by ``--with-observations``.

Each template is a thin framework adapter over ``observation_routes.handle`` (the engine owns the
Wire Contract). When the engine or the framework is missing the adapter degrades to a no-op that
returns ``False`` so the host app still boots.
"""

COMMON = '''

# --- Observation connector (Wire Contract v1) ---------------------------------------------------
try:
    import observation_routes as _obs
except ImportError:  # engine not found: routes are simply not registered
    _obs = None

DIAGNOSTICS_BASE_PATH = "/api/diagnostics"


def handle_diagnostics_request(method, rel_path, query, headers, client_host, body=b"", workspace_root=None):
    """Framework-neutral entry point: returns (status, headers, body_bytes)."""
    if _obs is None:
        return 404, {"X-Diagnostics-Contract": "1"}, b'{"error": "not_found", "message": "engine unavailable"}'
    return _obs.handle(method, rel_path, query, headers, client_host, body, workspace_root)


MAX_BODY_READ = 65537  # contract cap (64 KB) + 1 so oversize bodies still answer 413


def _readable(host):
    return _obs is not None and host in _obs.LOOPBACK_HOSTS


def observations_enabled():
    return _obs is not None and _obs.enabled()
'''

ADAPTERS = {
    "fastapi": '''

def register_observation_routes(app, workspace_root=None):
    """Mount the Wire Contract routes on a FastAPI app (only when FRONTIER_DEBUG_OBSERVATIONS=1)."""
    if not observations_enabled():
        return False
    from fastapi import Request
    from fastapi.responses import Response

    @app.api_route(DIAGNOSTICS_BASE_PATH + "/{rest:path}", methods=["GET", "POST"], include_in_schema=False)
    async def _frontier_diagnostics(rest: str, request: Request):
        host = request.client.host if request.client else ""
        body = b""
        if _readable(host):  # never buffer bodies for remote callers; cap the read for local ones
            async for chunk in request.stream():
                body += chunk
                if len(body) >= MAX_BODY_READ:
                    break
        status, headers, payload = handle_diagnostics_request(
            request.method, "/" + rest, request.url.query, dict(request.headers), host, body, workspace_root
        )
        return Response(content=payload, status_code=status, headers=headers)

    return True
''',
    "flask": '''

def register_observation_routes(app, workspace_root=None):
    """Mount the Wire Contract routes on a Flask app (only when FRONTIER_DEBUG_OBSERVATIONS=1)."""
    if not observations_enabled():
        return False
    import flask

    def _frontier_diagnostics(rest):
        req = flask.request
        host = req.remote_addr or ""
        body = req.stream.read(MAX_BODY_READ) if _readable(host) else b""
        status, headers, payload = handle_diagnostics_request(
            req.method, "/" + rest, req.query_string.decode("utf-8", "replace"), dict(req.headers),
            host, body, workspace_root,
        )
        return flask.Response(payload, status=status, headers=headers)

    app.add_url_rule(DIAGNOSTICS_BASE_PATH + "/<path:rest>", "frontier_diagnostics",
                     _frontier_diagnostics, methods=["GET", "POST"])
    return True
''',
    "generic": '''

def register_observation_routes(app=None, workspace_root=None):
    """Generic stack: call ``handle_diagnostics_request`` from your own router; nothing to mount."""
    return observations_enabled()
''',
}


def observation_block(framework: str) -> str:
    """Return the full observation section for a framework (unknown names use ``generic``)."""
    return COMMON + ADAPTERS.get(framework.lower(), ADAPTERS["generic"])
