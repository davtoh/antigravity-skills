#!/usr/bin/env python3
"""Zero-Code Runtime Runner for system-diagnostics (diagnose.py run).

Executes arbitrary commands with transparent trace_recorder bootstrap injection
via Python's sitecustomize mechanism.
"""

import argparse
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


def register_parser(sub: Any) -> None:
    """Register 'run' subparser."""
    p = sub.add_parser("run", help="Zero-code runner: launch application with auto-tracing bootstrapped")
    p.add_argument("command", nargs=argparse.REMAINDER, help="Command and arguments to execute")


def cmd_run(args: argparse.Namespace) -> int:
    """Execute a command with trace_recorder transparently injected via sitecustomize bootstrap."""
    cmd = getattr(args, "command", [])
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("Error: No command specified. Usage: diagnose.py run -- <command...>", file=sys.stderr)
        return 1

    scripts_dir = Path(__file__).resolve().parent
    bootstrap_dir = scripts_dir / "bootstrap"

    env = os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    new_pp = f"{bootstrap_dir}{os.pathsep}{scripts_dir}"
    if existing_pp:
        new_pp = f"{new_pp}{os.pathsep}{existing_pp}"
    env["PYTHONPATH"] = new_pp

    print(f"[diagnose run] Bootstrapping Runtime Diagnostic Trace Recorder...")
    print(f"  Command: {' '.join(cmd)}")

    try:
        res = subprocess.run(cmd, env=env)
        return res.returncode
    except Exception as exc:
        print(f"[diagnose run] Failed to spawn process: {exc}", file=sys.stderr)
        return 1
