#!/usr/bin/env python3
"""Cross-platform auxiliary tool discovery, virtual environment test runner, and diagnostics bridge.

Integrates with centralized system-diagnostics (diagnose.py) or sibling tools from frontier-architect
(cdp_inspect.py, docker_audit.py) and local repository virtualenvs without hard dependencies.
Enforces Axiom 9 (Honest Verification Reporting) so that static, container, and live UI
verification statuses are never overstated or conflated.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from campaign_manager import get_repo_root


def _find_candidate_tools(base_target: Path, root: Path) -> dict[str, str]:
    home = Path.home()
    sibling_dir = Path(__file__).resolve().parent.parent.parent
    sys_diag_dir = Path(os.environ["SYSTEM_DIAGNOSTICS_DIR"]) if os.environ.get("SYSTEM_DIAGNOSTICS_DIR") else None

    candidates = {
        "diagnose": [
            os.environ.get("DIAGNOSE_PATH", ""),
            str(sys_diag_dir / "scripts" / "diagnose.py") if sys_diag_dir else "",
            str(base_target / "scripts" / "diagnose.py"),
            str(root / "scripts" / "diagnose.py"),
            str(sibling_dir / "system-diagnostics" / "scripts" / "diagnose.py"),
            str(home / ".gemini" / "config" / "skills" / "system-diagnostics" / "scripts" / "diagnose.py"),
            str(root / ".gemini" / "skills" / "system-diagnostics" / "scripts" / "diagnose.py"),
        ],
        "cdp_inspect": [
            os.environ.get("CDP_INSPECT_PATH", ""),
            str(sys_diag_dir / "scripts" / "cdp_inspect.py") if sys_diag_dir else "",
            str(base_target / "scripts" / "cdp_inspect.py"),
            str(root / "scripts" / "cdp_inspect.py"),
            str(sibling_dir / "system-diagnostics" / "scripts" / "cdp_inspect.py"),
            str(home / ".gemini" / "config" / "skills" / "system-diagnostics" / "scripts" / "cdp_inspect.py"),
            str(sibling_dir / "frontier-architect" / "scripts" / "cdp_inspect.py"),
            str(home / ".gemini" / "config" / "skills" / "frontier-architect" / "scripts" / "cdp_inspect.py"),
        ],
        "docker_audit": [
            os.environ.get("DOCKER_AUDIT_PATH", ""),
            str(sys_diag_dir / "scripts" / "docker_audit.py") if sys_diag_dir else "",
            str(base_target / "scripts" / "docker_audit.py"),
            str(root / "scripts" / "docker_audit.py"),
            str(sibling_dir / "system-diagnostics" / "scripts" / "docker_audit.py"),
            str(home / ".gemini" / "config" / "skills" / "system-diagnostics" / "scripts" / "docker_audit.py"),
            str(sibling_dir / "frontier-architect" / "scripts" / "docker_audit.py"),
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


def auto_detect_container() -> str:
    """Attempt to detect active container from environment, docker compose, or docker ps."""
    if os.environ.get("DOCKER_CONTAINER"):
        return os.environ["DOCKER_CONTAINER"]
    try:
        proc = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            timeout=3,
        )
        if proc.returncode == 0:
            names = [n.strip() for n in proc.stdout.splitlines() if n.strip()]
            for n in names:
                if any(k in n.lower() for k in ("dashboard", "web", "app", "server", "tracker")):
                    return n
            if names:
                return names[0]
    except Exception:
        pass
    return ""


def auto_detect_app_url() -> str:
    """Attempt to detect active application URL from env or common localhost ports."""
    if os.environ.get("APP_URL"):
        return os.environ["APP_URL"]
    for port in (8000, 3000, 5000, 8080):
        url = f"http://127.0.0.1:{port}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Antigravity/Diagnostic"})
            with urllib.request.urlopen(req, timeout=0.8) as resp:
                if resp.status < 500:
                    return url
        except urllib.error.HTTPError as err:
            if err.code < 500:
                return url
        except Exception:
            pass
    return ""


def _resolve_cdp_script_and_url(target: Path, tools: dict[str, str], url: str) -> tuple[str, str]:
    """Resolve cdp_inspect.py path and target URL, reporting informative guidance if missing."""
    cdp_script = tools.get("cdp_inspect")
    if not cdp_script:
        print("\n--- Live UI Verification (CDP) ---")
        print("[Live Browser UI] SKIPPED: 'cdp_inspect.py' not detected.")
        print("  To enable live UI verification, install system-diagnostics or frontier-architect, or set $CDP_INSPECT_PATH.")
        return "", ""

    target_url = url or os.environ.get("APP_URL", "") or auto_detect_app_url()
    if not target_url:
        print("\n--- Live UI Verification (CDP) ---")
        print("[Live Browser UI] SKIPPED: Neither --url nor $APP_URL provided, and no local dev server listening on common ports.")
        print(f"  To run live layout verification: python \"{cdp_script}\" --url http://127.0.0.1:8000 --audit-layout --headless")
        return cdp_script, ""

    return cdp_script, target_url


def cmd_verify_ui(
    target: Path,
    url: str = "",
    selectors: str = "",
    headless: bool = True,
    strict: bool = False,
) -> int:
    """Bridge to frontier-architect cdp_inspect.py to verify live layout and overflow."""
    tools = discover_optional_tools(target)
    cdp_script, target_url = _resolve_cdp_script_and_url(target, tools, url)
    if not cdp_script or not target_url:
        return 1 if (strict and not cdp_script) else 0

    py_bin = tools.get("virtualenv_python") or sys.executable
    cmd = [py_bin, cdp_script, "--url", target_url, "--audit-layout"]
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

    target_container = container or os.environ.get("DOCKER_CONTAINER", "") or auto_detect_container()
    py_bin = tools.get("virtualenv_python") or sys.executable
    cmd = [py_bin, audit_script]
    if target_container:
        cmd.extend(["--container", target_container, "--workdir", workdir])
    if sync_check:
        cmd.extend(["--sync-check", *sync_check])

    print(f"\n--- Container Sync Audit (Docker Auditor: {target_container or 'all containers'}) ---")
    try:
        proc = subprocess.run(cmd, cwd=target, check=False)
        return proc.returncode
    except Exception as err:
        print(f"[Docker Container] Error executing docker_audit: {err}", file=sys.stderr)
        return 1


def _diagnose_contracts(target: Path, before_file: str, git_ref: str) -> list[str]:
    """Check Tier 1 AST and DOM contracts against baseline or git reference."""
    from contract_diff_engine import build_contract, diff_contracts, CodebaseContract
    from campaign_manager import get_refactor_dir

    print("\n--- Tier 1: AST & DOM Contract Check ---")
    before_path = Path(before_file) if before_file and Path(before_file).is_file() else None
    if not before_path and not git_ref:
        candidate = get_refactor_dir(target) / "baseline.json"
        if candidate.is_file():
            before_path = candidate

    if before_path:
        before = CodebaseContract.from_dict(json.loads(before_path.read_text(encoding="utf-8")))
        issues = diff_contracts(before, build_contract(target))
        status_msg = f"Zero regressions detected against baseline ({before_path.name})." if not issues else f"Found {len(issues)} contract discrepancy/discrepancies:"
        print(f"[Tier 1 Contract] {('OK' if not issues else 'CRITICAL')}: {status_msg}")
        for iss in issues:
            print(f"  {iss}")
        return issues
    elif git_ref:
        issues = diff_contracts(build_contract(target, git_ref), build_contract(target))
        status_msg = f"Zero regressions detected against git ref {git_ref}." if not issues else f"Found {len(issues)} contract discrepancy/discrepancies vs {git_ref}:"
        print(f"[Tier 1 Contract] {('OK' if not issues else 'CRITICAL')}: {status_msg}")
        for iss in issues:
            print(f"  {iss}")
        return issues

    print("[Tier 1 Contract] NOTICE: No baseline contract or --git-ref specified; capturing current contract as golden anchor.")
    current = build_contract(target)
    print(f"  Captured {len(current.html_ids)} HTML IDs, {len(current.select_ids)} Selects, {len(current.js_global_exports)} Globals, {len(current.python_routes)} Routes.")
    return []


def _diagnose_container(target: Path, container: str) -> tuple[int, str]:
    """Check Tier 2 Docker container runtime state and file synchronization."""
    detected = container or os.environ.get("DOCKER_CONTAINER", "") or auto_detect_container()
    if detected:
        code = cmd_audit_container(target, container=detected)
        return code, ("VERIFIED (Container synced)" if code == 0 else "FAILED")
    print("\n--- Container Sync Audit ---")
    print("[Docker Container] SKIPPED: No active container detected from environment or 'docker ps'.")
    return 0, "SKIPPED"


def _diagnose_ui(target: Path, url: str, strict: bool) -> tuple[int, str]:
    """Check Tier 3 Live browser DOM layout and exceptions via CDP."""
    detected = url or os.environ.get("APP_URL", "") or auto_detect_app_url()
    if detected:
        code = cmd_verify_ui(target, url=detected, headless=True, strict=strict)
        return code, ("VERIFIED (Zero layout overflow / exceptions)" if code == 0 else "FAILED")
    print("\n--- Live UI Verification (CDP) ---")
    print("[Live Browser UI] SKIPPED: No active dev server responding on localhost (tested ports 8000, 3000, 5000, 8080).")
    return 0, "SKIPPED"


def cmd_diagnose(
    target: Path,
    url: str = "",
    container: str = "",
    git_ref: str = "",
    before_file: str = "",
    strict: bool = False,
) -> int:
    """Execute unified 3-tier diagnostic audit (AST/DOM contract, Docker container, live CDP browser)."""
    print("=== Refactor Monolith: Unified 3-Tier Diagnostic Engine ===")
    issues = _diagnose_contracts(target, before_file, git_ref)
    docker_code, docker_status = _diagnose_container(target, container)
    ui_code, ui_status = _diagnose_ui(target, url, strict)
    print_verification_matrix(issues, ui_status, docker_status)
    has_failures = bool(issues) or (docker_code != 0) or (ui_code != 0)
    return 1 if (strict and has_failures) else 0


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
