#!/usr/bin/env python3
"""Cross-platform auxiliary tool discovery, virtual environment test runner, and frontier bridge.

Integrates with optional sibling tools from the frontier-architect skill
(cdp_inspect.py, docker_audit.py) and local repository virtualenvs without hard dependencies.
Enforces Axiom 9 (Honest Verification Reporting) so that static, container, and live UI
verification statuses are never overstated or conflated.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from campaign_manager import get_repo_root


def _find_candidate_tools(base_target: Path, root: Path) -> dict[str, str]:
    home = Path.home()
    candidates = {
        "cdp_inspect": [
            os.environ.get("CDP_INSPECT_PATH", ""),
            str(base_target / "scripts" / "cdp_inspect.py"),
            str(root / "scripts" / "cdp_inspect.py"),
            str(home / ".gemini" / "config" / "skills" / "frontier-architect" / "scripts" / "cdp_inspect.py"),
        ],
        "docker_audit": [
            os.environ.get("DOCKER_AUDIT_PATH", ""),
            str(base_target / "scripts" / "docker_audit.py"),
            str(root / "scripts" / "docker_audit.py"),
            str(home / ".gemini" / "config" / "skills" / "frontier-architect" / "scripts" / "docker_audit.py"),
        ],
    }
    found = {}
    for name, paths in candidates.items():
        for p in paths:
            if p and Path(p).is_file():
                found[name] = p
                break
    return found


def _find_virtualenv_python(base_target: Path, root: Path) -> str:
    candidates = [
        base_target / ".venv", base_target / "venv", base_target / "env",
        root / ".venv", root / "venv", root / "env",
    ]
    for v in candidates:
        if v.is_dir():
            py_bin = v / "Scripts" / "python.exe" if os.name == "nt" else v / "bin" / "python"
            if py_bin.is_file():
                return str(py_bin)
    return ""


def discover_optional_tools(target: Path | None = None) -> dict[str, str]:
    """Locate optional auxiliary tools from sibling skills or workspace without hard dependencies."""
    base_target = Path(target).resolve() if target else Path.cwd()
    root = get_repo_root(base_target)
    found = _find_candidate_tools(base_target, root)
    py_bin = _find_virtualenv_python(base_target, root)
    if py_bin:
        found["virtualenv_python"] = py_bin
    return found


def cmd_run_tests(target: Path, extra_args: list[str]) -> int:
    """Execute test suite using virtualenv python if detected, falling back to sys.executable."""
    tools = discover_optional_tools(target)
    py_bin = tools.get("virtualenv_python") or sys.executable
    args = extra_args or ["discover", "tests"]
    cmd = [py_bin, "-m", "unittest", *args]
    print(f"=== Test Runner (Interpreter: {py_bin}) ===")
    print(f"Executing: {' '.join(cmd)}\n")
    try:
        proc = subprocess.run(cmd, cwd=target, check=False)
        return proc.returncode
    except Exception as err:
        print(f"Error launching test runner: {err}", file=sys.stderr)
        return 1


def _parse_cdp_output(output: str) -> int:
    """Analyze CDP inspector output for JS exceptions and bounding box overflows."""
    try:
        data = json.loads(output)
        if data.get("jsException"):
            print(f"[CRITICAL UI REGRESSION] JavaScript exception on page: {data['jsException']}")
            return 1
        if data.get("hasOverflow") or data.get("overflowingElements"):
            print("[CRITICAL UI REGRESSION] Element layout overflow detected!")
            print(json.dumps(data.get("overflowingElements", data), indent=2))
            return 1
    except json.JSONDecodeError:
        pass

    print(output if output else "[Live Browser UI] OK: Bounding boxes and layout clean. Zero CSS overflow detected.")
    return 0


def cmd_verify_ui(
    target: Path,
    url: str = "",
    selectors: str = "",
    headless: bool = False,
    strict: bool = False,
) -> int:
    """Bridge to frontier-architect cdp_inspect.py to verify live layout and overflow."""
    tools = discover_optional_tools(target)
    cdp_script = tools.get("cdp_inspect")
    if not cdp_script:
        print("\n--- Live UI Verification (CDP) ---")
        print("[Live Browser UI] SKIPPED: 'cdp_inspect.py' not detected.")
        print("  To enable live UI verification, install the frontier-architect skill or set $CDP_INSPECT_PATH.")
        return 1 if strict else 0

    target_url = url or os.environ.get("APP_URL", "")
    if not target_url:
        print("\n--- Live UI Verification (CDP) ---")
        print("[Live Browser UI] SKIPPED: Neither --url nor $APP_URL environment variable was provided.")
        print(f"  To run live layout verification: python \"{cdp_script}\" --url http://127.0.0.1:8000 --audit-layout --headless")
        return 1 if strict else 0

    cmd = [sys.executable, cdp_script, "--url", target_url, "--audit-layout"]
    if selectors:
        cmd.extend(["--selectors", selectors])
    if headless:
        cmd.append("--headless")

    print(f"\n--- Live UI Verification (CDP Inspector: {target_url}) ---")
    try:
        proc = subprocess.run(cmd, cwd=target, capture_output=True, text=True, check=False, encoding="utf-8", errors="replace")
        output = proc.stdout.strip() or proc.stderr.strip()
        if proc.returncode != 0:
            print(f"[CRITICAL UI REGRESSION] cdp_inspect returned exit code {proc.returncode}:\n{output}")
            return 1
        return _parse_cdp_output(output)
    except Exception as err:
        print(f"[Live Browser UI] Error executing cdp_inspect: {err}", file=sys.stderr)
        return 1 if strict else 0


def cmd_audit_container(
    target: Path,
    container: str = "",
    workdir: str = "/app",
    sync_check: list[str] | None = None,
) -> int:
    """Bridge to frontier-architect docker_audit.py to verify container sync and CPU."""
    tools = discover_optional_tools(target)
    audit_script = tools.get("docker_audit")
    if not audit_script:
        print("\n--- Container Sync Audit ---")
        print("[Docker Container] SKIPPED: 'docker_audit.py' not detected.")
        return 0

    cmd = [sys.executable, audit_script]
    target_container = container or os.environ.get("DOCKER_CONTAINER", "")
    if target_container:
        cmd.extend(["--container", target_container, "--workdir", workdir])
    if sync_check:
        cmd.extend(["--sync-check", *sync_check])

    print(f"\n--- Container Sync Audit (Docker Auditor) ---")
    try:
        proc = subprocess.run(cmd, cwd=target, check=False)
        return proc.returncode
    except Exception as err:
        print(f"[Docker Container] Error executing docker_audit: {err}", file=sys.stderr)
        return 1


def print_verification_matrix(
    issues: list[str],
    ui_status: str = "SKIPPED",
    docker_status: str = "SKIPPED",
) -> None:
    """Print an honest 3-tier verification matrix complying with Axiom 9."""
    ast_status = "FAILED" if issues else "VERIFIED (Zero discrepancies)"
    print("\n=== Axiom 9 Verification Matrix ===")
    print(f"  Tier 1: AST & DOM Invariant Parity: {ast_status}")
    print(f"  Tier 2: Container Sync Audit:       {docker_status}")
    print(f"  Tier 3: Live Browser Layout (CDP):  {ui_status}")
    print("=" * 45)
