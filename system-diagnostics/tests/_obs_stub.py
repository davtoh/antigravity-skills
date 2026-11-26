"""Loopback stub server for pull/verify tests: serves Wire Contract v1 on an ephemeral port."""

import http.server
import sys
import threading
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import observation_routes as R

ENV_ON = {"FRONTIER_DEBUG_OBSERVATIONS": "1"}
BASE = R.BASE_PATH
Override = Callable[[str, str, str, dict, bytes, Callable[[], R.Response]], Any]


class StubServer:
    """Compliant by default (delegates to observation_routes.handle); `override` can break a row."""

    def __init__(self, workspace: Path, override: Override | None = None, handler: Callable | None = None) -> None:
        stub = self

        class H(http.server.BaseHTTPRequestHandler):
            def _serve(self) -> None:
                parts = urlsplit(self.path)
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                rel = parts.path[len(BASE):] if parts.path.startswith(BASE) else "/__outside__"
                hdrs = dict(self.headers.items())
                default = lambda: (handler or R.handle)(  # noqa: E731
                    self.command, rel, parts.query, hdrs, self.client_address[0], body, workspace, ENV_ON)
                res = (override(self.command, rel, parts.query, hdrs, body, default) if override else None) or default()
                status, headers, payload = res
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_POST = _serve

            def log_message(self, *args: Any) -> None:
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self) -> "StubServer":
        self.thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
