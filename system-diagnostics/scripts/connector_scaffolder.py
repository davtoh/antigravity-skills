#!/usr/bin/env python3
"""Framework Connector Scaffolder for system-diagnostics runtime traces.

Generates self-contained, decoupled bridge connectors for target web frameworks
(FastAPI, Flask, Django, generic) with dynamic sys.path discovery.
"""

import argparse
from pathlib import Path
import sys
from typing import Any

from connector_bridge_common import BOOTSTRAP_SRC, PLACEHOLDER
from connector_templates_obs import observation_block

TEMPLATES = {
    "fastapi": """#!/usr/bin/env python3
# -*- coding: utf-8 -*-
\"\"\"Diagnostic Trace Bridge & FastAPI Exception Middleware.\"\"\"

from typing import Optional

# @@ENGINE_BOOTSTRAP@@

try:
    from trace_recorder import install_trace_recorder, record_exception
    from trace_middleware import DiagnosticTraceMiddleware
except ImportError:
    install_trace_recorder = lambda *args, **kwargs: False  # type: ignore
    record_exception = lambda *args, **kwargs: None  # type: ignore
    DiagnosticTraceMiddleware = None  # type: ignore


def init_diagnostic_tracer(workspace_root: Optional[Path] = None) -> bool:
    \"\"\"Initialize global exception hooks for sys, threading, and asyncio.\"\"\"
    return bool(install_trace_recorder(workspace_root=workspace_root))
""",
    "flask": """#!/usr/bin/env python3
# -*- coding: utf-8 -*-
\"\"\"Diagnostic Trace Bridge & Flask Error Handler Hook.\"\"\"

from typing import Optional

# @@ENGINE_BOOTSTRAP@@

try:
    from trace_recorder import install_trace_recorder, record_exception
    from trace_middleware import DiagnosticWSGIMiddleware
except ImportError:
    install_trace_recorder = lambda *args, **kwargs: False  # type: ignore
    record_exception = lambda *args, **kwargs: None  # type: ignore
    DiagnosticWSGIMiddleware = None  # type: ignore


def init_diagnostic_tracer(app=None, workspace_root: Optional[Path] = None) -> bool:
    \"\"\"Initialize global exception hooks and optional Flask WSGI middleware.\"\"\"
    ok = bool(install_trace_recorder(workspace_root=workspace_root))
    if app is not None and DiagnosticWSGIMiddleware:
        app.wsgi_app = DiagnosticWSGIMiddleware(app.wsgi_app, workspace_root=workspace_root)
    return ok
""",
    "generic": """#!/usr/bin/env python3
# -*- coding: utf-8 -*-
\"\"\"Universal Runtime Diagnostic Trace Connector.\"\"\"

from typing import Optional

# @@ENGINE_BOOTSTRAP@@

try:
    from trace_recorder import install_trace_recorder, record_exception
except ImportError:
    install_trace_recorder = lambda *args, **kwargs: False  # type: ignore
    record_exception = lambda *args, **kwargs: None  # type: ignore


def init_diagnostic_tracer(workspace_root: Optional[Path] = None) -> bool:
    \"\"\"Initialize process-level exception hooks for sys and threading.\"\"\"
    return bool(install_trace_recorder(workspace_root=workspace_root))
""",
}


def scaffold_connector(
    target_root: Path,
    framework: str = "generic",
    dest_dir: str = "services",
    with_observations: bool = False,
) -> Path:
    """Scaffold a framework connector file into the target project."""
    fw = framework.lower()
    tmpl = TEMPLATES.get(fw, TEMPLATES["generic"]).replace(PLACEHOLDER, BOOTSTRAP_SRC.rstrip("\n"))
    if with_observations:
        tmpl += observation_block(fw)
    out_dir = target_root / dest_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "diagnostic_bridge.py"

    out_file.write_text(tmpl, encoding="utf-8")
    return out_file


def cmd_traces_scaffold(args: Any) -> int:
    """CLI handler for 'diagnose.py traces scaffold'."""
    root = Path(args.path).resolve() if getattr(args, "path", None) else Path.cwd().resolve()
    framework = getattr(args, "framework", "fastapi") or "fastapi"
    dest = getattr(args, "dest", "services") or "services"

    with_obs = bool(getattr(args, "with_observations", False))
    out_file = scaffold_connector(root, framework=framework, dest_dir=dest, with_observations=with_obs)
    try:
        rel_path = out_file.relative_to(root)
    except ValueError:
        rel_path = out_file

    print(f"\n[diagnose traces scaffold] Successfully generated {framework} bridge:")
    print(f"  Path: {rel_path}")
    print(f"\nQuick Setup:")
    if framework == "fastapi":
        print(f"  from {dest.replace('/', '.')}.diagnostic_bridge import init_diagnostic_tracer, DiagnosticTraceMiddleware")
        print(f"  init_diagnostic_tracer()")
        print(f"  app.add_middleware(DiagnosticTraceMiddleware)\n")
    elif framework == "flask":
        print(f"  from {dest.replace('/', '.')}.diagnostic_bridge import init_diagnostic_tracer")
        print(f"  init_diagnostic_tracer(app)\n")
    else:
        print(f"  from {dest.replace('/', '.')}.diagnostic_bridge import init_diagnostic_tracer")
        print(f"  init_diagnostic_tracer()\n")
    if with_obs:
        print("  Observations: call register_observation_routes(app) and set FRONTIER_DEBUG_OBSERVATIONS=1")
        print("  (routes under /api/diagnostics, loopback only; see references/observation-connector-contract.md)\n")
    return 0
