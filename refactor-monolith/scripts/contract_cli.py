#!/usr/bin/env python3
"""CLI argument parsing and command dispatch router for contract_snapshot.

Provides modular CLI definition and subcommand routing for all refactoring,
inspection, patching, and verification tools.
"""

import argparse
import sys
from pathlib import Path
from typing import Any

# Ensure stdout/stderr handle UTF-8 on Windows consoles without charmap UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from campaign_manager import _add_state_cli_args, cmd_state  # noqa: E402
from smoke_test_generator import cmd_generate_smoke_test  # noqa: E402
from auxiliary_tool_bridge import (  # noqa: E402
    cmd_audit_container,
    cmd_diagnose,
    cmd_run_tests,
    cmd_verify_ui,
    discover_optional_tools,
)
from file_patcher import (  # noqa: E402
    cmd_normalize_eol,
    inject_html_scripts,
    patch_file_content,
)
from css_inspector import cmd_inspect_css  # noqa: E402

def _add_common_path_args(parser: argparse.ArgumentParser) -> None:
    """Add standard --path, --before, and --git-ref arguments."""
    parser.add_argument("--path", nargs="+", default=["."], help="Target repository directory or paths.")
    parser.add_argument("--before", default="", help="Baseline JSON path.")
    parser.add_argument("--git-ref", default="", help="Historical git commit/branch.")

def _register_contract_subparsers(sub: Any) -> None:
    """Register core contract diff and state commands."""
    p_anc = sub.add_parser("anchor", help="Identify git reference anchor and worktree recipe.")
    p_anc.add_argument("--path", default=".", help="Target repository directory.")
    p_anc.add_argument("--worktree-dir", default="", help="Optional worktree path.")

    p_cap = sub.add_parser("capture", help="Capture contract to JSON file (defaults to .refactor/baseline.json).")
    _add_common_path_args(p_cap)
    p_cap.add_argument("--out", default="", help="Output JSON path.")

    p_ins = sub.add_parser("inspect", help="Display Interactive Surface Inventory.")
    _add_common_path_args(p_ins)
    p_ins.add_argument("--show-routes", action="store_true", help="List all detected backend API routes.")

    p_ver = sub.add_parser("verify", help="Diff contracts and check regressions.")
    _add_common_path_args(p_ver)
    p_ver.add_argument("--strict", action="store_true", help="Exit 1 on critical discrepancy.")
    p_ver.add_argument("--ui", action="store_true", help="Run live CDP browser layout verification.")
    p_ver.add_argument("--docker", action="store_true", help="Run container sync audit.")
    p_ver.add_argument("--url", default="", help="Application URL for live UI verification.")

    p_smk = sub.add_parser("generate-smoke-test", help="Generate permanent unittest contract test.")
    _add_common_path_args(p_smk)
    p_smk.add_argument("--out", default="", help="Output test file path.")

    p_st = sub.add_parser("state", help="Manage in-repo .refactor campaign state across conversation turns.")
    _add_state_cli_args(p_st)

def _register_tool_subparsers(sub: Any) -> None:
    """Register tool discovery, test execution, CSS, and container audit parsers."""
    p_prb = sub.add_parser("probe-tools", help="Discover optional auxiliary tools.")
    p_prb.add_argument("--path", default=".", help="Target repository directory.")

    p_css = sub.add_parser("inspect-css", help="Inspect stylesheet sections, @imports, CRLF, and !important.")
    p_css.add_argument("--path", default=".", help="Target CSS file or directory.")
    p_css.add_argument("--all", action="store_true", help="Display all section banners without truncation.")
    p_css.add_argument("--strict", action="store_true", help="Exit 1 if any !important found.")

    p_tst = sub.add_parser("run-tests", help="Run test suite using auto-detected virtualenv interpreter.")
    p_tst.add_argument("--path", default=".", help="Target repository directory.")
    p_tst.add_argument("--runner", choices=["auto", "unittest", "pytest"], default="auto", help="Test runner framework (default: auto).")
    p_tst.add_argument("--timeout", type=int, default=180, help="Test execution timeout in seconds (default: 180).")
    p_tst.add_argument("-c", "--command", default=None, help="Execute Python command string directly in virtualenv.")
    p_tst.add_argument("-m", "--module", default=None, help="Execute Python module directly in virtualenv.")
    p_tst.add_argument("test_args", nargs=argparse.REMAINDER, help="Arguments forwarded to test runner or python.")

    p_vui = sub.add_parser("verify-ui", help="Run CDP browser layout and overflow inspection.")
    p_vui.add_argument("--path", default=".", help="Target repository directory.")
    p_vui.add_argument("--url", default="", help="Application URL (defaults to $APP_URL).")
    p_vui.add_argument("--selectors", default="", help="CSS selectors to inspect.")
    p_vui.add_argument("--live", action="store_true", help="Attach to live visible Chrome (requires clicking Allow). Default: headless.")
    p_vui.add_argument("--strict", action="store_true", help="Exit 1 on layout error or overflow.")

    p_doc = sub.add_parser("audit-container", help="Run Docker CPU and file sync auditor.")
    p_doc.add_argument("--path", default=".", help="Target repository directory.")
    p_doc.add_argument("--container", default="", help="Target container name.")
    p_doc.add_argument("--workdir", default="/app", help="Container working directory.")
    p_doc.add_argument("--sync-check", nargs="*", default=[], help="Files to verify MD5 sync.")

def _register_diagnostic_and_patch_subparsers(sub: Any) -> None:
    """Register diagnose, EOL normalizer, patch, and script injection parsers."""
    p_diag = sub.add_parser("diagnose", help="Execute 1-command 3-tier diagnostic (AST/DOM contract, Docker sync, live CDP).")
    _add_common_path_args(p_diag)
    p_diag.add_argument("--url", default="", help="Application URL (auto-detected if omitted).")
    p_diag.add_argument("--container", default="", help="Target container name (auto-detected if omitted).")
    p_diag.add_argument("--strict", action="store_true", help="Exit 1 if any tier fails.")

    p_eol = sub.add_parser("normalize-eol", help="Normalize line endings across text files to prevent CRLF mismatches.")
    p_eol.add_argument("--path", default=".", help="Target repository directory or file.")
    p_eol.add_argument("--to", choices=["lf", "crlf"], default="lf", help="Target line ending (default: lf).")

    p_ptc = sub.add_parser("patch", help="Line-ending agnostic file search/replace.")
    p_ptc.add_argument("--file", required=True, help="Path to file to patch.")
    p_ptc.add_argument("--find", default="", help="Target text to find.")
    p_ptc.add_argument("--replace", default="", help="Replacement text.")
    p_ptc.add_argument("--find-file", default="", help="File containing target text.")
    p_ptc.add_argument("--replace-file", default="", help="File containing replacement text.")
    p_ptc.add_argument("--count", type=int, default=1, help="Max replacements (default: 1, 0 for all).")

    p_inj = sub.add_parser("inject-scripts", help="Inject <script src='...'> tags into HTML safely.")
    p_inj.add_argument("--html", required=True, help="Target HTML file.")
    p_inj.add_argument("--scripts", nargs="+", required=True, help="Script paths/URLs to inject.")
    p_inj.add_argument("--before", default="", help="Existing script name to inject before.")

def build_cli_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser."""
    p = argparse.ArgumentParser(description="Cross-platform codebase contract snapshot and regression auditor.")
    sub = p.add_subparsers(dest="subcommand", required=True)
    _register_contract_subparsers(sub)
    _register_tool_subparsers(sub)
    _register_diagnostic_and_patch_subparsers(sub)
    return p

def _dispatch_patch_or_script_cmd(subcmd: str, args: argparse.Namespace) -> int:
    """Handle patch, inject-scripts, and normalize-eol commands."""
    if subcmd == "normalize-eol":
        return cmd_normalize_eol(Path(getattr(args, "path", ".")), getattr(args, "to", "lf"))
    if subcmd == "patch":
        find_str = args.find or (Path(args.find_file).read_text(encoding="utf-8") if args.find_file else "")
        replace_str = args.replace or (Path(args.replace_file).read_text(encoding="utf-8") if args.replace_file else "")
        ok, msg = patch_file_content(Path(args.file), find_str, replace_str, args.count)
        print(msg)
        return 0 if ok else 1
    if subcmd == "inject-scripts":
        ok, msg = inject_html_scripts(Path(args.html), args.scripts, getattr(args, "before", ""))
        print(msg)
        return 0 if ok else 1
    return 0

def _dispatch_auxiliary_cmd(subcmd: str, target: Path, args: argparse.Namespace) -> int:
    """Handle testing, inspection, and live verification commands."""
    if subcmd == "inspect-css":
        return cmd_inspect_css(target, getattr(args, "all", False), getattr(args, "strict", False))
    if subcmd == "run-tests":
        test_args = list(getattr(args, "test_args", []))
        if getattr(args, "command", None):
            test_args = ["-c", args.command]
        elif getattr(args, "module", None):
            test_args = ["-m", args.module, *test_args]
        timeout = getattr(args, "timeout", 180)
        return cmd_run_tests(target, test_args, runner=getattr(args, "runner", "auto"), timeout=timeout)
    if subcmd == "verify-ui":
        is_headless = not getattr(args, "live", False)
        return cmd_verify_ui(target, getattr(args, "url", ""), getattr(args, "selectors", ""), is_headless, getattr(args, "strict", False))
    if subcmd == "audit-container":
        return cmd_audit_container(target, getattr(args, "container", ""), getattr(args, "workdir", "/app"), getattr(args, "sync_check", []))
    if subcmd == "diagnose":
        return cmd_diagnose(target, getattr(args, "url", ""), getattr(args, "container", ""), getattr(args, "git_ref", ""), getattr(args, "before", ""), getattr(args, "strict", False))
    return _dispatch_patch_or_script_cmd(subcmd, args)

def dispatch_cli(subcmd: str, target: Path, args: argparse.Namespace) -> int:
    """Dispatch parsed subcommand to corresponding implementation function."""
    from contract_snapshot import cmd_anchor, cmd_capture, cmd_inspect, cmd_verify

    if subcmd == "anchor":
        return cmd_anchor(target, getattr(args, "worktree_dir", ""))
    if subcmd == "capture":
        return cmd_capture(target, getattr(args, "out", ""), getattr(args, "git_ref", ""))
    if subcmd == "inspect":
        return cmd_inspect(target, getattr(args, "git_ref", ""), getattr(args, "before", ""), getattr(args, "show_routes", False))
    if subcmd == "verify":
        raw_paths = args.path if isinstance(args.path, list) else [args.path]
        targets = [Path(p).resolve() for p in raw_paths]
        target_param = targets if len(targets) > 1 else targets[0]
        return cmd_verify(target_param, getattr(args, "before", ""), getattr(args, "git_ref", ""), args.strict, getattr(args, "ui", False), getattr(args, "docker", False), getattr(args, "url", ""))
    if subcmd == "generate-smoke-test":
        return cmd_generate_smoke_test(target, getattr(args, "out", ""), getattr(args, "before", ""), getattr(args, "git_ref", ""))
    if subcmd == "state":
        return cmd_state(
            target, action=args.action, plan=getattr(args, "plan", ""), phases=getattr(args, "phases", 4),
            phase=getattr(args, "phase", None), phase_title=getattr(args, "phase_title", ""),
            status=getattr(args, "status", ""), sha=getattr(args, "sha", ""), note=getattr(args, "note", ""),
            as_json=getattr(args, "json", False),
        )
    return _dispatch_auxiliary_cmd(subcmd, target, args)

def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = build_cli_parser()
    args, extra = parser.parse_known_args(argv)
    if extra:
        if args.subcommand == "run-tests":
            args.test_args.extend(extra)
        else:
            parser.error("unrecognized arguments: " + " ".join(extra))
    raw_paths = args.path if isinstance(getattr(args, "path", "."), list) else [getattr(args, "path", ".")]
    target = Path(raw_paths[0]).resolve()
    if args.subcommand == "probe-tools":
        tools = discover_optional_tools(target)
        print("=== Optional Auxiliary Tools Discovery ===")
        for k, v in tools.items():
            print(f"  {k}: {v}")
        if not tools:
            print("  (None detected; running in 100% self-contained mode)")
        return 0
    return dispatch_cli(args.subcommand, target, args)

if __name__ == "__main__":
    sys.exit(main())
