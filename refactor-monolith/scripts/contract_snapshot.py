#!/usr/bin/env python3
"""Cross-platform contract snapshot, regression auditor, and smoke-test generator.

Captures and diffs AST, DOM, global export, and route contracts before and after
refactoring across Python, HTML, JavaScript, and CSS without external dependencies.
Manages persistent campaign state in .refactor/state.json across conversation turns.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Ensure stdout handles UTF-8 on Windows consoles without charmap UnicodeEncodeError
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

from campaign_manager import (  # noqa: E402
    _add_state_cli_args,
    _format_phase_icon,
    cmd_state,
    get_git_sha,
    get_refactor_dir,
    get_repo_root,
)
from smoke_test_generator import (  # noqa: E402
    _build_smoke_template,
    cmd_generate_smoke_test,
)
from surface_scanners import (  # noqa: E402
    scan_css_surface,
    scan_html_surface,
    scan_js_surface,
    scan_python_surface,
)
from auxiliary_tool_bridge import (  # noqa: E402
    cmd_audit_container,
    cmd_diagnose,
    cmd_run_tests,
    cmd_verify_ui,
    discover_optional_tools,
    print_verification_matrix,
)
from file_patcher import (  # noqa: E402
    cmd_normalize_eol,
    inject_html_scripts,
    patch_file_content,
)
from css_inspector import cmd_inspect_css  # noqa: E402
from contract_diff_engine import (  # noqa: E402
    IGNORED_DIRS,
    CodebaseContract,
    _run_git,
    build_contract,
    diff_contracts,
    iter_repo_files,
    read_file_content,
)


def cmd_anchor(target: Path, worktree_dir: str = "") -> int:
    """Print reference git commit anchor and git worktree recipe."""
    sha = get_git_sha(target)
    if not sha:
        print("Error: Target path is not a git repository.", file=sys.stderr)
        return 2
    code, dirty = _run_git(["status", "--porcelain"], cwd=target)
    print(f"=== Reference Git Anchor ===\nCurrent HEAD SHA: {sha}")
    print("[WARNING] Uncommitted modifications present!" if dirty else "Working directory clean (golden anchor).")
    target_worktree = worktree_dir or str(target.parent / f"{target.name}_pre_refactor")
    print(f"\n--- Parallel Git Worktree Recipe ---\n  git -C \"{target}\" worktree add \"{target_worktree}\" {sha[:7]}")
    print(f"To remove after verification:\n  git -C \"{target}\" worktree remove \"{target_worktree}\"")
    return 0


def cmd_capture(target: Path, out_file: str, git_ref: str = "") -> int:
    """Capture codebase contract to JSON file (defaults to .refactor/baseline.json)."""
    contract = build_contract(target, git_ref)
    if out_file:
        out_path = Path(out_file)
    else:
        out_path = get_refactor_dir(target) / "baseline.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(contract.to_dict(), indent=2), encoding="utf-8")
    src = f"git ref {git_ref}" if git_ref else "live workspace"
    print(f"Contract captured from {src} -> {out_path} ({len(contract.html_ids)} IDs, {len(contract.select_ids)} Selects, {len(contract.js_global_exports)} Globals, {len(contract.python_routes)} Routes)")
    return 0


def cmd_inspect(target: Path, git_ref: str = "", before_file: str = "", show_routes: bool = False) -> int:
    """Print human-readable Interactive Surface Inventory."""
    contract = CodebaseContract.from_dict(json.loads(Path(before_file).read_text(encoding="utf-8"))) if before_file else build_contract(target, git_ref)
    print("=== Interactive Surface Inventory ===")
    print(f"Total HTML Element IDs:       {len(contract.html_ids)}")
    print(f"Interactive Select Dropdowns: {len(contract.select_ids)}")
    for s in contract.select_ids[:15]:
        print(f"  - #{s}")
    if len(contract.select_ids) > 15:
        print(f"  ... and {len(contract.select_ids) - 15} more")
    print(f"Inline Event Handlers:        {len(contract.inline_handlers)}")
    print(f"Global window.* Exports:      {len(contract.js_global_exports)}")
    for g in contract.js_global_exports[:15]:
        print(f"  - window.{g}")
    print(f"Backend API Routes:           {len(contract.python_routes)}")
    routes_to_show = contract.python_routes if show_routes else contract.python_routes[:15]
    for r in routes_to_show:
        f_loc = f":L{r['line']}-L{r['end_line']}" if r.get("end_line") and r.get("end_line") != r.get("line") else (f":L{r['line']}" if r.get("line") else "")
        loc = f" ({r['file']}{f_loc})" if r.get("file") else ""
        h_str = f" -> {r['handler']}()" if r.get("handler") else ""
        print(f"  - {r.get('method', 'GET')} {r.get('path', '')}{h_str}{loc}")
    if not show_routes and len(contract.python_routes) > 15:
        print(f"  ... and {len(contract.python_routes) - 15} more (use 'inspect --show-routes' to list all)")
    print(f"CSS !important Count:         {contract.css_important_count}")
    return 0


def _print_verification_results(before: CodebaseContract, after: CodebaseContract, issues: list[str]) -> None:
    """Print diff issues and status."""
    print(f"=== Contract Verification: Before ({before.commit_sha[:7] or 'snapshot'}) vs After ({after.commit_sha[:7] or 'current'}) ===")
    if not issues:
        print("OK: Zero contract regressions detected! (DOM IDs, selects, globals, routes, and CSS preserved)")
    else:
        print(f"CRITICAL: Found {len(issues)} contract discrepancy/discrepancies:")
        for iss in issues:
            print(f"  {iss}")


def _check_missing_smoke_test(target: Path) -> None:
    """Warn if no frontend contract smoke test exists."""
    repo_root = get_repo_root(target)
    test_candidates: list[Path] = []
    for search_dir in [target, target / "tests", target.parent / "tests", repo_root / "tests"]:
        if search_dir.is_dir():
            test_candidates.extend(iter_repo_files(search_dir))
    if not any("smoke" in f.name.lower() or "contract" in f.name.lower() for f in test_candidates):
        print("\n[BLINDSPOT WARNING] No frontend contract smoke test found in tests/!")
        print("Run `contract_snapshot.py generate-smoke-test --out tests/test_refactor_contract.py` to lock in parity.")


def _resolve_baseline_contract(target: Path, before_file: str, git_ref: str) -> CodebaseContract | None:
    """Locate and load pre-refactor baseline contract from file, .refactor, or git ref."""
    before_path = None
    if before_file and Path(before_file).is_file():
        before_path = Path(before_file)
    elif not before_file and not git_ref:
        candidate = get_refactor_dir(target) / "baseline.json"
        legacy_candidate = target / ".refactor_baseline.json"
        if candidate.is_file():
            before_path = candidate
        elif legacy_candidate.is_file():
            before_path = legacy_candidate

    if before_path:
        return CodebaseContract.from_dict(json.loads(before_path.read_text(encoding="utf-8")))
    if git_ref:
        return build_contract(target, git_ref)
    return None


def _execute_live_audits(
    target: Path, run_ui: bool, run_docker: bool, app_url: str, strict: bool, opt_tools: dict[str, str]
) -> tuple[int, int, str, str]:
    """Run Tier 2 and Tier 3 live UI/Docker verifications."""
    ui_status, docker_status = "SKIPPED", "SKIPPED"
    ui_code, docker_code = 0, 0
    if run_ui:
        ui_code = cmd_verify_ui(target, url=app_url, strict=strict)
        ui_status = "VERIFIED (Zero layout overflow)" if ui_code == 0 else "FAILED"
    elif opt_tools.get("cdp_inspect"):
        ui_status = "SKIPPED (Use verify --ui or verify-ui --url $APP_URL)"

    if run_docker:
        docker_code = cmd_audit_container(target)
        docker_status = "VERIFIED (Container synced)" if docker_code == 0 else "FAILED"
    elif opt_tools.get("docker_audit"):
        docker_status = "SKIPPED (Use verify --docker or audit-container)"
    return ui_code, docker_code, ui_status, docker_status


def cmd_verify(
    target: Path,
    before_file: str = "",
    git_ref: str = "",
    strict: bool = False,
    run_ui: bool = False,
    run_docker: bool = False,
    app_url: str = "",
) -> int:
    """Diff current codebase contract against baseline or historical git commit."""
    before = _resolve_baseline_contract(target, before_file, git_ref)
    if not before:
        print("Error: provide --before <file.json> or --git-ref <sha> to verify against (or ensure .refactor/baseline.json exists).", file=sys.stderr)
        return 2

    after = build_contract(target)
    issues = diff_contracts(before, after)
    _print_verification_results(before, after, issues)

    opt_tools = discover_optional_tools(target)
    print("\n--- Tool Discovery Status ---")
    if opt_tools:
        for name, p in opt_tools.items():
            print(f"  [Optional Tool Detected] {name} -> {p}")
    else:
        print("  [Self-Contained Mode] Built-in static contract verifier active. (Optional live tools not found)")

    _check_missing_smoke_test(target)
    ui_code, docker_code, ui_st, doc_st = _execute_live_audits(target, run_ui, run_docker, app_url, strict, opt_tools)
    print_verification_matrix(issues, ui_st, doc_st)
    return 1 if (strict and (issues or ui_code != 0 or docker_code != 0)) else 0


def _add_common_path_args(parser: argparse.ArgumentParser) -> None:
    """Add standard --path, --before, and --git-ref arguments."""
    parser.add_argument("--path", default=".", help="Target repository directory.")
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
    p_tst.add_argument("test_args", nargs="*", help="Arguments forwarded to unittest.")

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
        return cmd_run_tests(target, getattr(args, "test_args", []))
    if subcmd == "verify-ui":
        is_headless = not getattr(args, "live", False)
        return cmd_verify_ui(target, getattr(args, "url", ""), getattr(args, "selectors", ""), is_headless, getattr(args, "strict", False))
    if subcmd == "audit-container":
        return cmd_audit_container(target, getattr(args, "container", ""), getattr(args, "workdir", "/app"), getattr(args, "sync_check", []))
    if subcmd == "diagnose":
        return cmd_diagnose(target, getattr(args, "url", ""), getattr(args, "container", ""), getattr(args, "git_ref", ""), getattr(args, "before", ""), getattr(args, "strict", False))
    return _dispatch_patch_or_script_cmd(subcmd, args)


def _dispatch_cli(subcmd: str, target: Path, args: argparse.Namespace) -> int:
    """Dispatch parsed subcommand to corresponding implementation function."""
    if subcmd == "anchor":
        return cmd_anchor(target, getattr(args, "worktree_dir", ""))
    if subcmd == "capture":
        return cmd_capture(target, getattr(args, "out", ""), getattr(args, "git_ref", ""))
    if subcmd == "inspect":
        return cmd_inspect(target, getattr(args, "git_ref", ""), getattr(args, "before", ""), getattr(args, "show_routes", False))
    if subcmd == "verify":
        return cmd_verify(target, getattr(args, "before", ""), getattr(args, "git_ref", ""), args.strict, getattr(args, "ui", False), getattr(args, "docker", False), getattr(args, "url", ""))
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
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    args = build_cli_parser().parse_args(argv)
    target = Path(getattr(args, "path", ".")).resolve()
    if args.subcommand == "probe-tools":
        tools = discover_optional_tools(target)
        print("=== Optional Auxiliary Tools Discovery ===")
        for k, v in tools.items():
            print(f"  {k}: {v}")
        if not tools:
            print("  (None detected; running in 100% self-contained mode)")
        return 0
    return _dispatch_cli(args.subcommand, target, args)


if __name__ == "__main__":
    sys.exit(main())
