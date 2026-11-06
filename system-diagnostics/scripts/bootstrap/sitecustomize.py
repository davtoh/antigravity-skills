# -*- coding: utf-8 -*-
"""Transparent runtime bootstrap for system-diagnostics trace recording.

When diagnose.py run injects this directory into PYTHONPATH, CPython executes
sitecustomize.py at interpreter startup, auto-installing exception hooks across
all child processes and worker threads without modifying application source code.
"""

import os
import sys

if os.environ.get("SYS_DIAG_DISABLE_AUTOTRACE") != "1":
    try:
        # Locate system-diagnostics/scripts directory (parent of bootstrap/)
        _scripts_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _scripts_dir not in sys.path:
            sys.path.insert(0, _scripts_dir)

        import trace_recorder

        # Workspace root defaults to current working directory
        trace_recorder.install_trace_recorder()
    except Exception:
        pass
