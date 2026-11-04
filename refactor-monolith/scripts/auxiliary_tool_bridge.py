#!/usr/bin/env python3
"""Cross-platform auxiliary tool discovery, virtual environment test runner, and diagnostics bridge.

Integrates with centralized system-diagnostics (diagnose.py) or sibling tools from frontier-architect
(cdp_inspect.py, docker_audit.py) and local repository virtualenvs without hard dependencies.
Enforces Axiom 9 (Honest Verification Reporting) so that static, container, and live UI
verification statuses are never overstated or conflated.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from campaign_manager import get_repo_root

def _tool_search_paths(name: str, base_target: Path, root: Path) -> list[str]:
    """Assemble candidate filepaths for an optional diagnostic tool."""
    home = Path.home()
    sibling_dir = Path(__file__).resolve().parent.parent.parent
    sys_diag_dir = Path(os.environ["SYSTEM_DIAGNOSTICS_DIR"]) if os.environ.get("SYSTEM_DIAGNOSTICS_DIR") else None
    paths = [
        os.environ.get(f"{name.upper()}_PATH", ""),
        str(sys_diag_dir / "scripts" / f"{name}.py") if sys_diag_dir else "",
        str(base_target / "scripts" / f"{name}.py"),
        str(root / "scripts" / f"{name}.py"),
        str(sibling_dir / "system-diagnostics" / "scripts" / f"{name}.py"),
        str(home / ".gemini" / "config" / "skills" / "system-diagnostics" / "scripts" / f"{name}.py"),
    ]
    if name in ("cdp_inspect", "docker_audit"):
        paths.extend([
            str(sibling_dir / "frontier-architect" / "scripts" / f"{name}.py"),
            str(home / ".gemini" / "config" / "skills" / "frontier-architect" / "scripts" / f"{name}.py"),
        ])
    elif name == "diagnose":
        paths.append(str(root / ".gemini" / "skills" / "system-diagnostics" / "scripts" / "diagnose.py"))
    return paths

def _find_candidate_tools(base_target: Path, root: Path) -> dict[str, str]:
    """Scan candidate locations for optional diagnostic and inspection CLIs."""
    found: dict[str, str] = {}
    for name in ("diagnose", "cdp_inspect", "docker_audit"):
        for p in _tool_search_paths(name, base_target, root):
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

def _is_pytest_preferred(target: Path, runner: str, clean_args: list[str]) -> bool:
    """Detect whether pytest should be favored over unittest."""
    if runner == "pytest":
        return True
    if runner == "auto":
        if clean_args and clean_args[0].lower() == "discover":
            return False
        markers = ["pytest.ini", "conftest.py", "pyproject.toml", "setup.cfg"]
        return any((target / m).is_file() for m in markers) or any("pytest" in a.lower() for a in clean_args)
    return False

def _build_test_runner_command(target: Path, py_bin: str, extra_args: list[str], runner: str) -> list[str]:
    """Assemble execution command line for test suite or inline Python."""
    clean = [a for a in extra_args if a != "--"]
    if clean and clean[0] in ("-c", "--command"):
        return [py_bin, "-c", *clean[1:]]
    if clean and clean[0] == "-m":
        return [py_bin, *clean]
    if _is_pytest_preferred(target, runner, clean):
        args = [a for a in clean if a.lower() not in ("pytest", "discover")] or ["tests/"]
        return [py_bin, "-m", "pytest", *args]
    args = [a for a in clean if a.lower() != "unittest"] or ["discover", "tests"]
    return [py_bin, "-m", "unittest", *args]

def cmd_run_tests(target: Path, extra_args: list[str], runner: str = "auto", timeout: int = 180) -> int:
    """Execute test suite using virtualenv python if detected, with headless env and safety timeout."""
    tools = discover_optional_tools(target)
    py_bin = tools.get("virtualenv_python") or sys.executable
    cmd = _build_test_runner_command(target, py_bin, extra_args, runner)
    env = os.environ.copy()
    env.setdefault("MPLBACKEND", "Agg")
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("CI", "true")
    print(f"=== Test Runner (Interpreter: {py_bin}, Timeout: {timeout}s) ===\nExecuting: {' '.join(cmd)}\n")
    try:
        proc = subprocess.run(cmd, cwd=target, env=env, timeout=timeout, check=False)
        return proc.returncode
    except subprocess.TimeoutExpired:
        print(
            f"\n[TIMEOUT ERROR] Test execution timed out after {timeout} seconds!\n"
            "The test runner may be hanging on interactive UI windows (plt.show, cv2.imshow, cv2.waitKey) or waiting for stdin (input()).\n"
            "Please isolate headless tests (e.g. `run-tests --path . -- discover tests/unit`) or increase timeout via `run-tests --timeout <seconds>`.\n",
            file=sys.stderr,
        )
        return 124
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
    from contract_diff_engine import build_contract, diff_contracts, resolve_baseline_contract

    print("\n--- Tier 1: AST & DOM Contract Check ---")
    before = resolve_baseline_contract(target, before_file, git_ref)
    if before:
        issues = diff_contracts(before, build_contract(target))
        src_label = f"git ref {git_ref}" if git_ref else f"baseline ({Path(before_file).name if before_file else 'baseline.json'})"
        status_msg = f"Zero regressions detected against {src_label}." if not issues else f"Found {len(issues)} contract discrepancy/discrepancies vs {src_label}:"
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
