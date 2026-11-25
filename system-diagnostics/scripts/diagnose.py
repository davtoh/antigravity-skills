#!/usr/bin/env python3
"""Unified Diagnostics CLI (system-diagnostics).

Single entrypoint for browser UI/layout inspection, Docker runtime/sync audit,
AST interactive surface scanning, and automated virtualenv test runs.

Zero external dependencies; standard library Python 3.10+ only.
Cross-platform: Windows, macOS, Linux.
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import surface_scanners
import probe_runner
import static_auditor
import shadow_prober
import changelog_manager
import trace_recorder
import runtime_runner
import skill_packager
import arch_mapper
import transcript_auditor
import debug_retro
import diagnose_cli

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
    cmd = diagnose_cli.build_ui_command(SCRIPTS_DIR, target_url, args)
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
    """Delegate source collection to surface_scanners.walk_source_files."""
    return surface_scanners.walk_source_files(root, include_tests=True)


def cmd_surface(args: argparse.Namespace) -> int:
    """Delegate directory surface scanning to surface_scanners.cmd_surface."""
    return surface_scanners.cmd_surface(args)

def cmd_tests(args: argparse.Namespace) -> int:
    """Execute automated test runner using virtualenv Python if available."""
    target_path = Path(args.path).resolve() if args.path else Path.cwd()
    py_bin = find_virtualenv_python(target_path)
    start_dir = "tests" if (target_path / "tests").is_dir() else "."
    test_args = args.args if args.args else ["discover", "-s", start_dir, "-p", "test_*.py"]
    cmd = [py_bin, "-m", "unittest", *test_args]
    raw_timeout = getattr(args, "timeout", 180.0)
    timeout = raw_timeout if (raw_timeout is not None and raw_timeout > 0) else None

    print(f"=== Diagnose Tests: Test Suite Runner (Interpreter: {py_bin}) ===")
    print(f"Command: {' '.join(cmd)}\n")
    try:
        res = subprocess.run(cmd, cwd=str(target_path), timeout=timeout)
        return res.returncode
    except subprocess.TimeoutExpired:
        print(f"[TIMEOUT] Test runner exceeded {timeout}s — check for un-signaled events or blocking I/O.", file=sys.stderr)
        return 124

def cmd_audit(args: argparse.Namespace) -> int:
    """Execute static quality, defect, and code smell audit."""
    raw_paths = args.path if isinstance(args.path, list) else ([args.path] if args.path else [])
    targets = [Path(p).resolve() for p in raw_paths] if raw_paths else [Path.cwd()]
    py_bin = find_virtualenv_python(targets[0])
    overall_code = 0
    for target_path in targets:
        rc = static_auditor.cmd_audit(target_path, py_bin, args)
        overall_code = max(overall_code, rc)
    return overall_code

def cmd_scan(args: argparse.Namespace) -> int:
    """Execute polyglot defect scan and update .diagnostics/ SSOT catalog."""
    return shadow_prober.cmd_scan(args)

def cmd_scaffold_defect(args: argparse.Namespace) -> int:
    """Execute JIT defect scaffolding for remediation."""
    return shadow_prober.cmd_scaffold_defect(args)

def cmd_resolve_defect(args: argparse.Namespace) -> int:
    """Mark one or more catalog defects as resolved."""
    return shadow_prober.cmd_status_transition(args, "resolved")

def cmd_dismiss_defect(args: argparse.Namespace) -> int:
    """Mark one or more catalog defects as dismissed."""
    return shadow_prober.cmd_status_transition(args, "dismissed")

def cmd_all(args: argparse.Namespace) -> int:
    """Execute unified 3-tier diagnostic audit in 1 command."""
    return diagnose_cli.run_all_tiers(sys.modules[__name__], args)

def _print_probe_run_result(result: dict, as_json: bool) -> None:
    """Format and print probe execution result."""
    if as_json:
        print(json.dumps(result, indent=2))
        return
    sym = {"ok": "✓", "warning": "⚠", "error": "✗"}.get(result.get("status", ""), "•")
    print(f"\n[{sym}] Diagnostic Probe: {result.get('probe')} ({result.get('latency_ms', 0)}ms)\n    Summary: {result.get('summary')}")
    details = result.get("details", {})
    if isinstance(details, dict):
        for k, v in details.items():
            print(f"    - {k}: {v}")
    else:
        print(f"    - Output: {details}")
    print()

def _run_probe_list_or_exec(action: str, root: Path | None, args: argparse.Namespace) -> int:
    """Handle 'list' and 'run' probe actions."""
    if action == "list":
        probes = probe_runner.list_probes(workspace_root=root)
        if getattr(args, "json", False):
            print(json.dumps([p.to_dict() for p in probes], indent=2))
            return 0
        print(f"\n=== Registered Diagnostic Probes ({len(probes)}) ===")
        if not probes:
            print("  No probes registered yet. Use 'diagnose.py probe new <name>' to scaffold one.")
            return 0
        for p in probes:
            print(f"  - {p.name:<20} [{p.scope}] {p.description}")
        print()
        return 0
    if not args.name:
        print("[diagnose probe run] Error: Probe name or path required.", file=sys.stderr)
        return 2
    py_bin = find_virtualenv_python(root or Path.cwd())
    res = probe_runner.run_probe(
        args.name,
        probe_args=args.probe_args,
        python_bin=py_bin,
        workspace_root=root,
        timeout=getattr(args, "timeout", 60.0),
    )
    _print_probe_run_result(res, getattr(args, "json", False))
    return 0 if res.get("status") in ("ok", "warning") else 1

def cmd_probe(args: argparse.Namespace) -> int:
    """Execute dynamic probe commands (list, run, new, save)."""
    action = getattr(args, "probe_action", None)
    if not action:
        print("[diagnose probe] Error: Probe action required. Use 'list', 'run', 'new', or 'save'.", file=sys.stderr)
        return 2
    root = Path(args.path).resolve() if getattr(args, "path", None) else None
    if action in ("list", "run"):
        return _run_probe_list_or_exec(action, root, args)
    if action == "new":
        if not getattr(args, "name", None):
            print("[diagnose probe new] Error: Probe name required.", file=sys.stderr)
            return 2
        domain = getattr(args, "domain", "general") or "general"
        dest = probe_runner.scaffold_probe(args.name, domain=domain, target_dir=(root / ".diagnostics" / "probes" if root else None))
        print(f"[diagnose probe new] Scaffolded new probe template: {dest}")
        return 0
    if action == "save":
        if not getattr(args, "source", None) or not getattr(args, "name", None):
            print("[diagnose probe save] Error: Both source script and probe name are required.", file=sys.stderr)
            return 2
        scope = "workspace" if getattr(args, "workspace", False) else "global"
        dest = probe_runner.save_probe(args.source, args.name, scope=scope, workspace_root=root)
        print(f"[diagnose probe save] Successfully registered probe '{args.name}' ({scope}): {dest}")
        return 0
    print(f"[diagnose probe] Error: Unknown probe action '{action}'.", file=sys.stderr)
    return 2

def build_parser() -> argparse.ArgumentParser:
    """Build unified CLI argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="diagnose.py",
        description="Unified System Diagnostics CLI - Browser, Container, Surface & Test Engine",
    )
    sub = parser.add_subparsers(dest="subcommand", help="Diagnostic domain to run")
    diagnose_cli.register_ui_parser(sub)
    diagnose_cli.register_core_parsers(sub)
    for mod in (
        probe_runner, static_auditor, shadow_prober, changelog_manager,
        trace_recorder, runtime_runner, skill_packager, arch_mapper, transcript_auditor, debug_retro,
    ):
        reg = getattr(mod, "register_parsers", None) or getattr(mod, "register_parser")
        reg(sub)
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
        "probe": cmd_probe,
        "audit": cmd_audit,
        "scan": cmd_scan,
        "scaffold-defect": cmd_scaffold_defect,
        "resolve-defect": cmd_resolve_defect,
        "dismiss-defect": cmd_dismiss_defect,
        "changelog": changelog_manager.cmd_changelog,
        "traces": trace_recorder.cmd_traces,
        "run": runtime_runner.cmd_run,
        "package-skill": skill_packager.cmd_package_skill,
        "arch-map": arch_mapper.cmd_arch_map,
        "transcript-audit": transcript_auditor.cmd_transcript_audit,
        "debug-retro": debug_retro.cmd_debug_retro,
    }
    handler = dispatch.get(args.subcommand)
    if not handler:
        parser.print_help()
        return 2
    return handler(args)

if __name__ == "__main__":
    sys.exit(main())
