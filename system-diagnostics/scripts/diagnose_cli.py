#!/usr/bin/env python3
"""CLI parser registration and multi-tier execution helpers for diagnose.py."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def register_ui_parser(sub: Any) -> None:
    """Register the `ui` browser inspection subcommand."""
    p = sub.add_parser("ui", help="Browser layout, DOM overflow, and JS exception inspector")
    p.add_argument("--url", default=None, help="Target URL (auto-probes ports if omitted)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true", help="Inspect visible live Chrome tab")
    mode.add_argument("--headless", action="store_true", default=None, help="Run headless Chrome (default unless --live)")
    p.add_argument("--no-fallback-headless", dest="fallback_headless", action="store_false", help="Fail if live browser unreachable")
    p.add_argument("--allow-headless-fallback", action="store_true", help="Permit fallback to isolated headless Chrome when --live fails")
    p.set_defaults(fallback_headless=True)
    p.add_argument("--capture-runtime", dest="capture_runtime", action="store_true", default=None, help="Capture console errors, uncaught exceptions, HTTP>=400, and localStorage (default ON with --eval/--eval-file)")
    p.add_argument("--no-capture-runtime", dest="capture_runtime", action="store_false", help="Disable runtime exception capture when running --eval/--eval-file")
    p.add_argument("--audit-layout", action="store_true", help="Audit bounding box overflow")
    p.add_argument("--selectors", default=None, help="Comma-separated CSS selectors to measure")
    p.add_argument("--screenshot", default=None, help="Path to save JPEG screenshot")
    p.add_argument("--navigate", action="store_true", help="Force fresh page reload")
    p.add_argument("--eval", default=None, help="Evaluate JS expression and return JSON")
    p.add_argument("--eval-file", default=None, help="Path to UTF-8 JS file (or '-' for stdin) to evaluate in target page")
    p.add_argument("--click", default=None, help="CSS selector to click before auditing")
    p.add_argument("--window-size", default="1440x900", help="Viewport size WxH (default: 1440x900)")
    p.add_argument("--wait", type=float, default=1.5, help="Seconds to wait before inspection (default: 1.5)")
    p.add_argument("--connect-timeout", type=float, default=None, help="Live CDP WebSocket handshake timeout (seconds)")
    p.add_argument("--port", type=int, default=None, help="Debugging port override")
    p.add_argument("--strict", action="store_true", help="Exit code 1 if layout audit contains warnings or horizontal window scroll")
    p.add_argument("--list-tabs", action="store_true", help="List active Chrome tabs")


def register_core_parsers(sub: Any) -> None:
    """Register `container`, `surface`, `tests`, and `all` subcommands."""
    p_cnt = sub.add_parser("container", help="Docker CPU, active top processes, and MD5 sync audit")
    p_cnt.add_argument("--container", default=None, help="Container name (auto-probed if omitted)")
    p_cnt.add_argument("--workdir", default="/app", help="Container working dir (default: /app)")
    p_cnt.add_argument("--sync-check", nargs="*", default=[], help="Files to verify host-vs-container MD5 sync")
    p_cnt.add_argument("--lines", type=int, default=150, help="Log lines to scan for tracebacks")

    p_surf = sub.add_parser("surface", help="AST/DOM surface scanner (HTML IDs, JS globals, Python routes)")
    p_surf.add_argument("--path", default=None, help="Root directory to scan (default: current directory)")
    p_surf.add_argument("--show-ids", action="store_true", help="List all HTML element IDs")
    p_surf.add_argument("--show-globals", action="store_true", help="List all window.* JS exports")
    p_surf.add_argument("--show-routes", action="store_true", help="List all backend Python routes")
    p_surf.add_argument("--verify", action="store_true", help="Verify cross-contract parity (JS fetch vs routes, window.* read/write, JS IDs vs HTML)")
    p_surf.add_argument("--strict", action="store_true", help="Exit 1 if --verify detects mismatches")
    p_surf.add_argument("--json", action="store_true", help="Output JSON report")

    p_test = sub.add_parser("tests", help="Run automated tests using discovered virtualenv")
    p_test.add_argument("--path", default=None, help="Root directory (default: current directory)")
    p_test.add_argument("--timeout", type=float, default=180.0, help="Max seconds before aborting hung suite (default: 180; 0 disables)")
    p_test.add_argument("args", nargs="*", default=[], help="Arguments passed to test runner")

    p_all = sub.add_parser("all", help="Unified 3-Tier Diagnostic Audit in 1 command")
    p_all.add_argument("--path", default=None, help="Root directory (default: current directory)")
    p_all.add_argument("--url", default=None, help="Explicit web URL")
    p_all.add_argument("--container", default=None, help="Explicit Docker container name")
    p_all.add_argument("--wait", type=float, default=1.5, help="Seconds to wait for UI tier settle (default: 1.5)")
    p_all.add_argument("--strict", action="store_true", help="Exit code 1 if any tier fails")


def build_ui_command(scripts_dir: Path, target_url: str | None, args: argparse.Namespace) -> list[str]:
    """Assemble cdp_inspect.py invocation arguments from parsed CLI args."""
    cmd = [sys.executable, str(scripts_dir / "cdp_inspect.py")]
    if target_url:
        cmd.extend(["--url", target_url])
    for attr, flag in (
        ("list_tabs", "--list-tabs"), ("audit_layout", "--audit-layout"),
        ("navigate", "--navigate"), ("strict", "--strict"),
        ("allow_headless_fallback", "--allow-headless-fallback"),
    ):
        if getattr(args, attr, False):
            cmd.append(flag)
    cap_rt = getattr(args, "capture_runtime", None)
    if cap_rt is True or (cap_rt is None and (getattr(args, "eval", None) or getattr(args, "eval_file", None))):
        cmd.append("--capture-runtime")
    elif cap_rt is False:
        cmd.append("--no-capture-runtime")
    for attr, flag in (
        ("selectors", "--selectors"), ("screenshot", "--screenshot"),
        ("eval", "--eval"), ("eval_file", "--eval-file"),
        ("click", "--click"), ("window_size", "--window-size"),
    ):
        if val := getattr(args, attr, None):
            cmd.extend([flag, str(val)])
    for attr, flag in (("wait", "--wait"), ("connect_timeout", "--connect-timeout"), ("port", "--port")):
        if (val := getattr(args, attr, None)) is not None:
            cmd.extend([flag, str(val)])
    no_fallback = (getattr(args, "fallback_headless", True) is False) or (
        getattr(args, "live", False) and not getattr(args, "allow_headless_fallback", False)
    )
    if no_fallback:
        cmd.append("--no-fallback-headless")
    if not getattr(args, "live", False):
        cmd.append("--headless")
    return cmd


def _run_tier_checks(diag: Any, args: argparse.Namespace, target_path: Path) -> tuple[str, str, str]:
    """Run Tiers 1-3 via diagnose module helpers so tests patching `diagnose.*` work cleanly."""
    print("--- Tier 1: Static Surface & Tests ---")
    diag.cmd_surface(argparse.Namespace(path=str(target_path), json=False, show_ids=False, show_globals=False, show_routes=False))
    t1 = "SKIPPED (no tests/ directory)"
    if (target_path / "tests").is_dir():
        rc1 = diag.cmd_tests(argparse.Namespace(path=str(target_path), args=[]))
        t1 = "VERIFIED (Passed)" if rc1 == 0 else f"FAILED (Exit Code {rc1})"
    else:
        print(f"\n[Tier 1] Notice: {t1}")

    print("\n--- Tier 2: Container Runtime & Resource Audit ---")
    t2 = "SKIPPED (Docker inactive or not found)"
    if shutil.which("docker"):
        c_name = args.container or diag.probe_docker_container()
        rc2 = diag.cmd_container(argparse.Namespace(container=c_name, workdir="/app", sync_check=[], lines=50))
        t2 = "VERIFIED (Active)" if rc2 == 0 else "UNVERIFIED (Container error)"
    else:
        print(f"[Tier 2] Notice: {t2}")

    print("\n--- Tier 3: Live Browser UI & Layout Audit ---")
    url = args.url or diag.probe_local_port()
    t3 = "SKIPPED (No web service active on ports 8000/3000/5000/8080)"
    if url:
        ui_args = argparse.Namespace(
            url=url, list_tabs=False, audit_layout=True, selectors=None, screenshot=None,
            eval=None, click=None, navigate=False, window_size="1440x900", headless=True,
            live=False, wait=getattr(args, "wait", 1.5), strict=getattr(args, "strict", False),
        )
        rc3 = diag.cmd_ui(ui_args)
        t3 = "VERIFIED (Layout clean)" if rc3 == 0 else f"FAILED (Layout issue / Code {rc3})"
    else:
        print(f"[Tier 3] Notice: {t3}")
    return t1, t2, t3


def run_all_tiers(diag: Any, args: argparse.Namespace) -> int:
    """Execute unified 3-tier diagnostic audit and print Axiom 9 summary."""
    target_path = Path(args.path).resolve() if args.path else Path.cwd()
    print("=" * 80 + "\n                    UNIFIED 3-TIER SYSTEM DIAGNOSTIC AUDIT                      \n" + "=" * 80 + "\n")
    t1, t2, t3 = _run_tier_checks(diag, args, target_path)
    print("\n" + "=" * 80 + "\n                         AXIOM 9 VERIFICATION SUMMARY                           \n" + "=" * 80)
    print(f"  Tier 1 (Surface & Tests):   {t1}\n  Tier 2 (Container Runtime): {t2}\n  Tier 3 (Browser UI/Layout): {t3}\n" + "=" * 80 + "\n")
    return 1 if (args.strict and any("FAILED" in st for st in (t1, t2, t3))) else 0


def register_scan_parsers(subparsers: Any) -> tuple[Any, Any]:
    """Register `scan`, `scaffold-defect`, `resolve-defect`, and `dismiss-defect` subparsers."""
    p_scan = subparsers.add_parser("scan", help="Polyglot scan for latent defects, smells, and vulnerabilities")
    p_scan.add_argument("--path", nargs="+", default=None, help="Directory or file path(s) to scan (default: current directory)")
    for flag, dest, h in (("--deep", "deep", "Include CSS/SCSS and deeper AST rules"), ("--all", "deep", "Alias for --deep"),
                          ("--prune", "prune", "Purge closed/vanished defects"), ("--json", "json", "Output JSON catalog"),
                          ("--strict", "strict", "Exit 1 if active defects found")):
        p_scan.add_argument(flag, dest=dest, action="store_true", help=h)

    p_scaf = subparsers.add_parser("scaffold-defect", help="Unlock and scaffold a defect for remediation")
    p_scaf.add_argument("--id", required=True, help="Defect ID (e.g. DEFECT-001) or fingerprint")
    for flag, h in (("--branch", "Checkout micro-branch"), ("--elevate", "Force elevation brief"),
                    ("--fix", "Force tactical test"), ("--json", "Output JSON result")):
        p_scaf.add_argument(flag, action="store_true", help=h)
    p_scaf.add_argument("--path", default=None, help="Target workspace directory")

    for name, flag, h in (("resolve-defect", "--note", "Mark defect(s) resolved"), ("dismiss-defect", "--reason", "Dismiss defect(s)")):
        p = subparsers.add_parser(name, help=h)
        p.add_argument("--id", required=True, help="Defect ID(s), fingerprint(s), or rule_id")
        p.add_argument(flag, default="", help="Resolution or dismissal note")
        p.add_argument("--path", default=None, help="Target workspace directory")
        p.add_argument("--json", action="store_true", help="Output JSON result")
    return p_scan, p_scaf
