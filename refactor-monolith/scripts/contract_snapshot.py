#!/usr/bin/env python3
"""Cross-platform contract snapshot, regression auditor, and smoke-test generator.

Captures and diffs AST, DOM, global export, and route contracts before and after
refactoring across Python, HTML, JavaScript, and CSS without external dependencies.
Manages persistent campaign state in .refactor/state.json across conversation turns.
"""

import json
import sys
from pathlib import Path

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
    get_git_sha,
    get_refactor_dir,
    get_repo_root,
)
from auxiliary_tool_bridge import (  # noqa: E402
    cmd_audit_container,
    cmd_verify_ui,
    discover_optional_tools,
    print_verification_matrix,
)
from contract_diff_engine import (  # noqa: E402
    CodebaseContract,
    _run_git,
    build_contract,
    diff_contracts,
    iter_repo_files,
    merge_contracts,
    resolve_baseline_contract,
)

__all__ = [
    "cmd_anchor",
    "cmd_capture",
    "cmd_inspect",
    "cmd_verify",
]


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
    return resolve_baseline_contract(target, before_file, git_ref)


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
    target: Path | list[Path],
    before_file: str = "",
    git_ref: str = "",
    strict: bool = False,
    run_ui: bool = False,
    run_docker: bool = False,
    app_url: str = "",
) -> int:
    """Diff current codebase contract against baseline or historical git commit."""
    target_list = target if isinstance(target, list) else [target]
    primary_target = target_list[0]
    before = resolve_baseline_contract(target, before_file, git_ref)
    if not before:
        print("Error: provide --before <file.json> or --git-ref <sha> to verify against (or ensure .refactor/baseline.json exists).", file=sys.stderr)
        return 2

    if len(target_list) == 1:
        after = build_contract(primary_target)
    else:
        after = merge_contracts([build_contract(t) for t in target_list])
    issues = diff_contracts(before, after)
    _print_verification_results(before, after, issues)

    opt_tools = discover_optional_tools(primary_target)
    print("\n--- Tool Discovery Status ---")
    if opt_tools:
        for name, p in opt_tools.items():
            print(f"  [Optional Tool Detected] {name} -> {p}")
    else:
        print("  [Self-Contained Mode] Built-in static contract verifier active. (Optional live tools not found)")

    _check_missing_smoke_test(primary_target)
    ui_code, docker_code, ui_st, doc_st = _execute_live_audits(primary_target, run_ui, run_docker, app_url, strict, opt_tools)
    print_verification_matrix(issues, ui_st, doc_st)
    return 1 if (strict and (issues or ui_code != 0 or docker_code != 0)) else 0


from contract_cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
