#!/usr/bin/env python3
"""Unified Diagnostics CLI (system-diagnostics).

Single entrypoint for browser UI/layout inspection, Docker runtime/sync audit,
AST interactive surface scanning, and automated virtualenv test runs.

Zero external dependencies; standard library Python 3.10+ only.
Cross-platform: Windows, macOS, Linux.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import surface_scanners

# Configure UTF-8 stdout/stderr across all platforms
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def probe_local_port(ports: list[int] | None = None) -> str | None:
    """Probe common dev server ports on 127.0.0.1 to auto-discover active web app."""
    target_ports = ports or [8000, 3000, 5000, 8080, 5173, 4200]
    for port in target_ports:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.15):
                return f"http://localhost:{port}"
        except (OSError, ConnectionRefusedError, TimeoutError):
            continue
    return None


def probe_docker_container() -> str | None:
    """Probe active Docker containers and return the first running application container."""
    if not shutil.which("docker"):
        return None
    try:
        res = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5.0,
        )
        if res.returncode == 0:
            lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
            for name in lines:
                if not any(k in name.lower() for k in ("db", "redis", "postgres", "mysql", "mongo")):
                    return name
            return lines[0] if lines else None
    except Exception:
        return None
    return None


def find_virtualenv_python(root: Path) -> str:
    """Auto-discover virtualenv python binary inside root or common sibling directories."""
    candidates = [
        root / ".venv", root / "venv", root / "env",
        root.parent / ".venv", root.parent / "venv",
    ]
    for v in candidates:
        if v.is_dir():
            py_bin = v / "Scripts" / "python.exe" if os.name == "nt" else v / "bin" / "python"
            if py_bin.is_file():
                return str(py_bin)
    return sys.executable


def cmd_ui(args: argparse.Namespace) -> int:
    """Execute CDP browser layout and UI inspection."""
    target_url = args.url or os.getenv("APP_URL") or probe_local_port()
    if not target_url and not args.list_tabs:
        print("[diagnose ui] Error: No --url provided and no local dev server detected on common ports (8000, 3000, 5000, 8080, 5173).", file=sys.stderr)
        return 2

    cmd = [sys.executable, str(SCRIPTS_DIR / "cdp_inspect.py")]
    if target_url:
        cmd.extend(["--url", target_url])
    if args.list_tabs:
        cmd.append("--list-tabs")
    if args.audit_layout:
        cmd.append("--audit-layout")
    if args.selectors:
        cmd.extend(["--selectors", args.selectors])
    if args.screenshot:
        cmd.extend(["--screenshot", args.screenshot])
    if args.eval:
        cmd.extend(["--eval", args.eval])
    if args.click:
        cmd.extend(["--click", args.click])
    if args.navigate:
        cmd.append("--navigate")
    if args.window_size:
        cmd.extend(["--window-size", args.window_size])
    if args.headless or not args.live:
        cmd.append("--headless")

    print(f"=== Diagnose UI: Browser Inspection ({target_url or 'Live Tabs'}) ===")
    res = subprocess.run(cmd)
    return res.returncode


def cmd_container(args: argparse.Namespace) -> int:
    """Execute Docker runtime, process top, and host-container sync audit."""
    target_container = args.container or os.getenv("DOCKER_CONTAINER") or probe_docker_container()
    cmd = [sys.executable, str(SCRIPTS_DIR / "docker_audit.py")]
    if target_container:
        cmd.extend(["--container", target_container])
    if args.workdir:
        cmd.extend(["--workdir", args.workdir])
    if args.sync_check:
        cmd.extend(["--sync-check", *args.sync_check])
    if args.lines:
        cmd.extend(["--tail-errors", str(args.lines)])

    print(f"=== Diagnose Container: Runtime Audit ({target_container or 'All Containers'}) ===")
    res = subprocess.run(cmd)
    return res.returncode


def _walk_source_files(root: Path) -> dict[str, list[Path]]:
    """Collect source files for surface scanning, filtering ignore directories."""
    ignored = {".git", ".venv", "venv", "env", "node_modules", "__pycache__", "dist", "build", ".refactor"}
    files: dict[str, list[Path]] = {"html": [], "js": [], "py": [], "css": []}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ignored and not d.startswith(".")]
        for fn in filenames:
            ext = fn.rsplit(".", 1)[-1].lower() if "." in fn else ""
            p = Path(dirpath) / fn
            if ext in ("html", "htm", "jinja", "jinja2"):
                files["html"].append(p)
            elif ext in ("js", "mjs", "ts", "jsx", "tsx"):
                files["js"].append(p)
            elif ext == "py":
                files["py"].append(p)
            elif ext in ("css", "scss"):
                files["css"].append(p)
    return files


def cmd_surface(args: argparse.Namespace) -> int:
    """Scan directory surface for HTML element IDs, JS globals, and Python routes."""
    target_path = Path(args.path).resolve() if args.path else Path.cwd()
    files = _walk_source_files(target_path)

    all_ids, all_selects, all_globals, all_routes, important_count = set(), set(), set(), [], 0
    for hp in files["html"]:
        try:
            surf = surface_scanners.scan_html_surface(hp.read_text(encoding="utf-8", errors="replace"))
            all_ids.update(surf.ids)
            all_selects.update(surf.selects)
        except Exception:
            pass

    for jp in files["js"]:
        try:
            surf = surface_scanners.scan_js_surface(jp.read_text(encoding="utf-8", errors="replace"))
            all_globals.update(surf.global_exports)
        except Exception:
            pass

    for pp in files["py"]:
        try:
            surf = surface_scanners.scan_python_surface(pp.read_text(encoding="utf-8", errors="replace"))
            all_routes.extend(surf.routes)
        except Exception:
            pass

    for cp in files["css"]:
        try:
            surf = surface_scanners.scan_css_surface(cp.read_text(encoding="utf-8", errors="replace"))
            important_count += surf.important_count
        except Exception:
            pass

    data = {
        "workspace": str(target_path),
        "total_html_files": len(files["html"]),
        "total_ids": len(all_ids),
        "ids": sorted(all_ids),
        "interactive_selects": sorted(all_selects),
        "global_window_exports": sorted(all_globals),
        "backend_routes": all_routes,
        "css_important_count": important_count,
    }

    if args.json:
        print(json.dumps(data, indent=2))
        return 0

    print(f"=== Surface Inventory ({target_path}) ===")
    print(f"HTML Files: {len(files['html'])} | Unique IDs: {len(all_ids)} | Selects: {len(all_selects)}")
    print(f"JS Files:   {len(files['js'])} | window.* Globals: {len(all_globals)}")
    print(f"Python Files: {len(files['py'])} | API Routes: {len(all_routes)}")
    print(f"CSS Files:  {len(files['css'])} | !important Count: {important_count}")

    if args.show_ids and all_ids:
        print("\n--- Element IDs ---")
        for i in sorted(all_ids):
            print(f"  #{i}")
    if args.show_globals and all_globals:
        print("\n--- window.* Exports ---")
        for g in sorted(all_globals):
            print(f"  {g}")
    if args.show_routes and all_routes:
        print("\n--- Backend Routes ---")
        for r in all_routes:
            print(f"  {r.get('method', 'GET')} {r.get('path', '')}")
    return 0


def cmd_tests(args: argparse.Namespace) -> int:
    """Execute automated test runner using virtualenv Python if available."""
    target_path = Path(args.path).resolve() if args.path else Path.cwd()
    py_bin = find_virtualenv_python(target_path)
    test_args = args.args if args.args else ["discover", "-s", "tests", "-p", "test_*.py"]
    cmd = [py_bin, "-m", "unittest", *test_args]

    print(f"=== Diagnose Tests: Test Suite Runner (Interpreter: {py_bin}) ===")
    print(f"Command: {' '.join(cmd)}\n")
    res = subprocess.run(cmd, cwd=str(target_path))
    return res.returncode


def cmd_all(args: argparse.Namespace) -> int:
    """Execute unified 3-tier diagnostic audit in 1 command."""
    target_path = Path(args.path).resolve() if args.path else Path.cwd()
    print("================================================================================")
    print("                    UNIFIED 3-TIER SYSTEM DIAGNOSTIC AUDIT                      ")
    print("================================================================================\n")

    # Tier 1: Static Surface & Test Suite Check
    print("--- Tier 1: Static Surface & Tests ---")
    surface_args = argparse.Namespace(path=str(target_path), json=False, show_ids=False, show_globals=False, show_routes=False)
    cmd_surface(surface_args)

    tests_dir = target_path / "tests"
    t1_status = "SKIPPED (no tests/ directory)"
    if tests_dir.is_dir():
        t1_code = cmd_tests(argparse.Namespace(path=str(target_path), args=[]))
        t1_status = "VERIFIED (Passed)" if t1_code == 0 else f"FAILED (Exit Code {t1_code})"
    else:
        print(f"\n[Tier 1] Notice: {t1_status}")

    # Tier 2: Docker Container Runtime Check
    print("\n--- Tier 2: Container Runtime & Resource Audit ---")
    t2_status = "SKIPPED (Docker inactive or not found)"
    if shutil.which("docker"):
        c_name = args.container or probe_docker_container()
        t2_code = cmd_container(argparse.Namespace(container=c_name, workdir="/app", sync_check=[], lines=50))
        t2_status = "VERIFIED (Active)" if t2_code == 0 else "UNVERIFIED (Container error)"
    else:
        print(f"[Tier 2] Notice: {t2_status}")

    # Tier 3: Browser UI Layout & Exception Check
    print("\n--- Tier 3: Live Browser UI & Layout Audit ---")
    url = args.url or probe_local_port()
    t3_status = "SKIPPED (No web service active on ports 8000/3000/5000/8080)"
    if url:
        ui_args = argparse.Namespace(
            url=url, list_tabs=False, audit_layout=True, selectors=None,
            screenshot=None, eval=None, click=None, navigate=False,
            window_size="1440x900", headless=True, live=False
        )
        t3_code = cmd_ui(ui_args)
        t3_status = "VERIFIED (Layout clean)" if t3_code == 0 else f"FAILED (Layout issue / Code {t3_code})"
    else:
        print(f"[Tier 3] Notice: {t3_status}")

    print("\n================================================================================")
    print("                         AXIOM 9 VERIFICATION SUMMARY                           ")
    print("================================================================================")
    print(f"  Tier 1 (Surface & Tests):   {t1_status}")
    print(f"  Tier 2 (Container Runtime): {t2_status}")
    print(f"  Tier 3 (Browser UI/Layout): {t3_status}")
    print("================================================================================\n")

    if args.strict:
        if any("FAILED" in st for st in (t1_status, t2_status, t3_status)):
            return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build unified CLI argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="diagnose.py",
        description="Unified System Diagnostics CLI - Browser, Container, Surface & Test Engine",
    )
    sub = parser.add_subparsers(dest="subcommand", help="Diagnostic domain to run")

    # 1. UI subcommand
    p_ui = sub.add_parser("ui", help="Browser layout, DOM overflow, and JS exception inspector")
    p_ui.add_argument("--url", default=None, help="Target URL (auto-probes ports if omitted)")
    p_ui.add_argument("--live", action="store_true", help="Inspect visible live Chrome tab")
    p_ui.add_argument("--headless", action="store_true", default=True, help="Run headless Chrome (default)")
    p_ui.add_argument("--audit-layout", action="store_true", help="Audit bounding box overflow")
    p_ui.add_argument("--selectors", default=None, help="Comma-separated CSS selectors to measure")
    p_ui.add_argument("--screenshot", default=None, help="Path to save JPEG screenshot")
    p_ui.add_argument("--navigate", action="store_true", help="Force fresh page reload")
    p_ui.add_argument("--eval", default=None, help="Evaluate JS expression and return JSON")
    p_ui.add_argument("--click", default=None, help="CSS selector to click before auditing")
    p_ui.add_argument("--window-size", default="1440x900", help="Viewport size WxH (default: 1440x900)")
    p_ui.add_argument("--list-tabs", action="store_true", help="List active Chrome tabs")

    # 2. Container subcommand
    p_cnt = sub.add_parser("container", help="Docker CPU, active top processes, and MD5 sync audit")
    p_cnt.add_argument("--container", default=None, help="Container name (auto-probed if omitted)")
    p_cnt.add_argument("--workdir", default="/app", help="Container working dir (default: /app)")
    p_cnt.add_argument("--sync-check", nargs="*", default=[], help="Files to verify host-vs-container MD5 sync")
    p_cnt.add_argument("--lines", type=int, default=150, help="Log lines to scan for tracebacks")

    # 3. Surface subcommand
    p_surf = sub.add_parser("surface", help="AST/DOM surface scanner (HTML IDs, JS globals, Python routes)")
    p_surf.add_argument("--path", default=None, help="Root directory to scan (default: current directory)")
    p_surf.add_argument("--show-ids", action="store_true", help="List all HTML element IDs")
    p_surf.add_argument("--show-globals", action="store_true", help="List all window.* JS exports")
    p_surf.add_argument("--show-routes", action="store_true", help="List all backend Python routes")
    p_surf.add_argument("--json", action="store_true", help="Output JSON report")

    # 4. Tests subcommand
    p_test = sub.add_parser("tests", help="Run automated tests using discovered virtualenv")
    p_test.add_argument("--path", default=None, help="Root directory (default: current directory)")
    p_test.add_argument("args", nargs="*", default=[], help="Arguments passed to test runner")

    # 5. All subcommand
    p_all = sub.add_parser("all", help="Unified 3-Tier Diagnostic Audit in 1 command")
    p_all.add_argument("--path", default=None, help="Root directory (default: current directory)")
    p_all.add_argument("--url", default=None, help="Explicit web URL")
    p_all.add_argument("--container", default=None, help="Explicit Docker container name")
    p_all.add_argument("--strict", action="store_true", help="Exit code 1 if any tier fails")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.subcommand:
        parser.print_help()
        return 0

    dispatch = {
        "ui": cmd_ui,
        "container": cmd_container,
        "surface": cmd_surface,
        "tests": cmd_tests,
        "all": cmd_all,
    }
    handler = dispatch.get(args.subcommand)
    if not handler:
        parser.print_help()
        return 2
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
