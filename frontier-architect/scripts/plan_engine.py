#!/usr/bin/env python3
"""Cross-platform plan execution and continuation engine for Frontier Architect.

Command-line orchestrator that coordinates plan discovery, milestone advancement,
cognitive harness context emission, verification baselines, and retrospectives.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import argparse
import json
import re
import subprocess
import sys

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from plan_cli_helpers import add_retrospective_parser, assess_plan_scope, print_advance_summary, print_master_gate, print_milestone_body
from plan_digest import cmd_digest, register_digest_parser, write_learning_scaffold
from plan_parser import discover_plans, parse_plan_markdown, patch_milestone_checkboxes, slugify
from plan_state import (
    bootstrap_plan, get_frontier_dir, get_git_sha, get_repo_root,
    link_child_plan, load_json, record_milestone_advance, resolve_plan_path,
)
from plan_telemetry import (
    _extract_leading_env,
    _normalize_verify_cmd,
    _parse_test_counts,
    _parse_tri,
    _resolve_venv_python,
    cmd_lookup,
    cmd_retrospective,
    cmd_verify,
    get_prior_learn_candidates,
)


def cmd_discover(root: Path, _args: argparse.Namespace) -> int:
    """List all detected plans in the workspace."""
    plans = discover_plans(root)
    if not plans:
        print("[plan_engine] No architectural plans found in workspace.")
        return 0
    print(f"[plan_engine] Discovered {len(plans)} architectural plan(s):")
    for idx, p in enumerate(plans, 1):
        rel = p.relative_to(root).as_posix() if p.is_relative_to(root) else p.as_posix()
        print(f"  {idx}. {rel} (slug: {slugify(p.stem)})")
    return 0


def _check_plan_portability(text: str) -> str | None:
    """Warn if a plan embeds machine-local paths or file:/// URIs."""
    if re.search(r"(file:///|[A-Za-z]:[/\\]Users[/\\]|\.venv[/\\]Scripts)", text):
        return "[plan_engine] PORTABILITY WARNING: Machine-local paths/URIs detected; prefer POSIX repo-relative paths and portable commands."
    return None


def cmd_init(root: Path, args: argparse.Namespace) -> int:
    """Explicitly bind or auto-initialize a plan ledger."""
    target = resolve_plan_path(root, args.plan)
    if not target:
        print(f"[plan_engine] Error: Plan '{args.plan or ''}' could not be resolved.")
        return 1
    _ws, ps = bootstrap_plan(root, target)
    parent_arg = getattr(args, "parent", None)
    if parent_arg:
        parent_ps = link_child_plan(root, ps, parent_arg, getattr(args, "milestone", None))
        if not parent_ps:
            print(f"[plan_engine] Warning: Parent plan '{parent_arg}' could not be linked.")
    print(f"[plan_engine] Initialized plan: {ps['title']}")
    print(f"  Slug: {ps['slug']} | Active Milestone: {ps['active_milestone_index']}/{ps['total_milestones']}")
    print(f"  Status: {ps['status']} | Path: {ps['plan_path']}")
    if ps.get("parent_plan"):
        p = ps["parent_plan"]
        print(f"  Parent Master Plan: {p['slug']} (Step/Milestone {p['milestone']})")
    raw_text = target.read_text(encoding="utf-8")
    parsed = parse_plan_markdown(raw_text)
    if scope_msg := assess_plan_scope(parsed, ps, parent_arg):
        print(scope_msg)
    if port_msg := _check_plan_portability(raw_text):
        print(port_msg)
    return 0


def cmd_status(root: Path, args: argparse.Namespace) -> int:
    """Emit formatted status report or machine-readable JSON."""
    plan_p = resolve_plan_path(root, args.plan)
    if not plan_p:
        print("[plan_engine] No active or discovered plan. Run 'plan_engine.py init <path>' first.")
        return 1
    ws, ps = bootstrap_plan(root, plan_p)
    if args.json:
        print(json.dumps({"workspace": ws, "plan": ps}, indent=2))
        return 0

    done_m = sum(1 for m in ps["milestones"] if m["status"] == "completed")
    pct = int((done_m / ps["total_milestones"] * 100)) if ps["total_milestones"] else 0
    bar = "█" * (pct // 10) + "░" * (10 - (pct // 10))

    print("=== Frontier Architect Plan Status ===")
    print(f"Plan: {ps['title']} ({ps['plan_path']})")
    print(f"Slug: {ps['slug']} | Status: {ps['status'].upper()}")
    if ps.get("parent_plan"):
        p = ps["parent_plan"]
        print(f"Parent Master: {p['slug']} (Step/Milestone {p['milestone']})")
    print(f"Progress: [{bar}] {pct}% (Milestone {ps['active_milestone_index']} of {ps['total_milestones']})")
    vb = ws.get("verification_baseline", {})
    if vb.get("command"):
        print(f"Baseline: {vb.get('command')} -> Exit: {vb.get('last_exit_code')} ({vb.get('passed_tests')} passed)")
    print("\nMilestones:")
    children = ps.get("child_plans", {})
    for m in ps["milestones"]:
        mark = "✓" if m["status"] == "completed" else ("▶" if m["status"] == "active" else " ")
        sha_str = f" [{m['commit_sha']}]" if m.get("commit_sha") else ""
        print(f"  [{mark}] Milestone {m['index']}: {m['title']} ({m['completed_tasks']}/{m['total_tasks']} tasks){sha_str}")
        c_info = children.get(str(m["index"]))
        if c_info:
            print(f"      ↳ Child Plan: {c_info['slug']} [{c_info['status']} | M{c_info['active_milestone_index']}/{c_info['total_milestones']}] ({c_info['plan_path']})")
        elif m.get("child_plan"):
            print(f"      ↳ Child Plan (declared): {m['child_plan']}")
    return 0


def cmd_next(root: Path, args: argparse.Namespace) -> int:
    """Emit zero-token instructions and verifiers for active vertical slice."""
    plan_p = resolve_plan_path(root, args.plan)
    if not plan_p:
        print("[plan_engine] No plan resolved. Run 'init' first.")
        return 1
    _ws, ps = bootstrap_plan(root, plan_p)
    parsed = parse_plan_markdown(plan_p.read_text(encoding="utf-8"))
    active_idx = ps["active_milestone_index"]
    target_m = next((m for m in parsed["milestones"] if m["index"] == active_idx), None)
    prior_learns = get_prior_learn_candidates(root, ps["slug"])

    all_done = ps["status"] == "completed" or (bool(parsed["milestones"]) and all(m["is_complete"] for m in parsed["milestones"]))
    if all_done or not target_m:
        if args.json:
            payload = {"status": "completed", "title": ps["title"], "milestone": None, "verifiers": parsed["verification_commands"], "prior_learn_candidates": prior_learns, **({"parent_plan": ps["parent_plan"]} if ps.get("parent_plan") else {})}
            print(json.dumps(payload, indent=2))
        else:
            print(f"[plan_engine] All milestones in '{ps['title']}' are completed! Run final sign-off.")
            if p := ps.get("parent_plan"):
                print(f"[plan_engine] Parent Master Plan: {p['slug']} (Step/Milestone {p['milestone']}) -> Run 'plan_engine.py advance {p['slug']} --milestone {p['milestone']}' then 'plan_engine.py next {p['slug']}'.")
        return 0
    if args.json:
        print(json.dumps({"milestone": target_m, "verifiers": parsed["verification_commands"], "prior_learn_candidates": prior_learns}, indent=2))
        return 0

    print(f"=== Active Milestone: {target_m['index']} - {target_m['title']} ===")
    if ps.get("parent_plan"):
        p = ps["parent_plan"]
        print(f"Parent Master: {p['slug']} (Step/Milestone {p['milestone']}) -> {p['plan_path']}")
    c_info = ps.get("child_plans", {}).get(str(active_idx))
    if c_info:
        if c_info.get("status") == "completed":
            print(f"Linked Child Plan: {c_info['slug']} [completed] -> MASTER STEP SYNC GATE: Run 'plan_engine.py advance {ps['slug']} --milestone {active_idx}' to advance Master Milestone.")
        else:
            print(f"Linked Child Plan: {c_info['slug']} [{c_info['status']}] -> Run 'plan_engine.py next {c_info['slug']}'")
    else:
        print_master_gate(ps, active_idx, target_m.get("child_plan"))
    print_milestone_body(target_m, parsed, prior_learns)
    return 0


def _get_working_tree_code_changes(root: Path) -> tuple[list[str], bool]:
    """Return modified/untracked files excluding internal plan/ledger state and whether git was probed."""
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3.0,
        )
        if res.returncode != 0:
            return [], False

        tracking_prefixes = (".frontier", ".TODO", ".plans", ".refactor", ".changelogs")
        code_files = []
        for line in res.stdout.splitlines():
            if len(line) > 3:
                filepath = line[3:].strip()
                if " -> " in filepath:
                    filepath = filepath.split(" -> ")[-1].strip()
                norm = filepath.replace("\\", "/")
                if not any(
                    norm == p or norm.startswith(f"{p}/") or f"/{p}/" in norm
                    for p in tracking_prefixes
                ):
                    code_files.append(norm)
        return code_files, True
    except Exception:
        return [], False


def _build_commit_suggestion(ps: dict[str, Any], target_idx: int) -> str:
    """Build a conventional git commit suggestion for the completed milestone."""
    milestone_title = next(
        (m["title"] for m in ps.get("milestones", []) if m.get("index") == target_idx),
        f"milestone {target_idx}",
    )
    stripped_title = re.sub(
        r"\s*(?:—|--)\s*\*?(?:Active Execution Target|Deferred to Next Turn(?:\s*/\s*Milestone)?|Completed|Pending|In Progress)\*?\s*$",
        "",
        milestone_title,
        flags=re.IGNORECASE,
    )
    stripped_title = re.sub(r"\*?\([^)]*\)\*?", "", stripped_title)
    clean_scope = ps.get("slug", "feature").replace("_plan", "").replace("_", "-")
    clean_title = re.sub(r"[^\w\s-]", "", stripped_title).strip().lower()
    clean_title = re.sub(r"\s+", " ", clean_title) or f"complete milestone {target_idx}"
    return f'git commit -m "feat({clean_scope}): {clean_title}"'


def _auto_sync_parent(root: Path, ps: dict[str, Any], sha: str | None, now_iso: str, no_sync: bool) -> tuple[str, int] | None:
    """Auto-advance the linked parent Master Milestone when a child plan completes."""
    if no_sync or ps.get("status") != "completed" or not isinstance(ps.get("parent_plan"), dict):
        return None
    p = ps["parent_plan"]
    parent_p = resolve_plan_path(root, p.get("slug"))
    p_idx = p.get("milestone")
    if not parent_p or p_idx is None:
        return None
    _ws, parent_ps = bootstrap_plan(root, parent_p)
    if any(m.get("index") == p_idx and m.get("status") == "completed" for m in parent_ps.get("milestones", [])):
        return None
    patch_milestone_checkboxes(parent_p, int(p_idx))
    parent_ps = record_milestone_advance(get_frontier_dir(root), parent_ps, int(p_idx), sha, now_iso)
    from plan_telemetry import rollup_child_retrospective
    rollup_child_retrospective(root, parent_ps, int(p_idx), refresh=True)
    write_learning_scaffold(root, parent_ps["slug"], backfill=False)
    return parent_ps["slug"], int(p_idx)


def cmd_advance(root: Path, args: argparse.Namespace) -> int:
    """In-place patch markdown checklist, record commit SHA, and advance milestone."""
    plan_p = resolve_plan_path(root, args.plan)
    if not plan_p:
        print("[plan_engine] Error: No plan resolved.")
        return 1
    _ws, ps = bootstrap_plan(root, plan_p)
    target_idx = args.milestone if args.milestone is not None else ps["active_milestone_index"]

    patched = patch_milestone_checkboxes(plan_p, target_idx)
    sha = args.commit or get_git_sha(root)
    now_iso = datetime.now(timezone.utc).isoformat()
    fdir = get_frontier_dir(root)
    ps = record_milestone_advance(fdir, ps, target_idx, sha, now_iso)

    code_changes, is_git = _get_working_tree_code_changes(root)
    has_code_diff = bool(code_changes) if is_git else True
    if is_git and not code_changes:
        commit_hint = "(None - Milestone was verification/audit only; no application code changes)"
    else:
        commit_hint = _build_commit_suggestion(ps, target_idx)

    from plan_telemetry import rollup_child_retrospective
    rollup_child_retrospective(root, ps, target_idx)

    missing_prior_retro = None
    if target_idx > 1:
        retros = load_json(fdir / "plans" / ps["slug"] / "retrospectives.json", [])
        logged = {r.get("milestone_index") for r in retros if isinstance(r, dict)}
        if (target_idx - 1) not in logged:
            missing_prior_retro = target_idx - 1

    scaffold_rel = write_learning_scaffold(root, ps["slug"], backfill=False) if (ps["status"] == "completed" or ps.get("child_plans")) else None
    parent_synced = _auto_sync_parent(root, ps, sha, now_iso, getattr(args, "no_sync_parent", False))
    print_advance_summary(ps, target_idx, sha, commit_hint, has_code_diff, patched, missing_prior_retro, scaffold_rel=scaffold_rel, parent_synced=parent_synced)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser with subcommands."""
    parser = argparse.ArgumentParser(description="Frontier Architect Plan & Continuation Engine")
    parser.add_argument("--root", type=Path, default=None, help="Optional workspace root override")
    sub = parser.add_subparsers(dest="subcommand", help="Engine subcommands")

    root_parent = argparse.ArgumentParser(add_help=False)
    root_parent.add_argument("--root", type=Path, default=argparse.SUPPRESS, help="Optional workspace root override")

    sub.add_parser("discover", parents=[root_parent], help="Discover architectural plans in workspace")
    p_init = sub.add_parser("init", parents=[root_parent], help="Initialize or bind active plan")
    p_init.add_argument("plan", nargs="?", help="Path or slug of plan")
    p_init.add_argument("--parent", default=None, help="Optional parent master plan path or slug")
    p_init.add_argument("--milestone", type=int, default=None, help="Parent milestone/step index for child plan")
    plan_parent = argparse.ArgumentParser(add_help=False, parents=[root_parent])
    plan_parent.add_argument("plan", nargs="?", help="Optional plan target")
    p_status = sub.add_parser("status", parents=[plan_parent], help="Show active plan status")
    p_status.add_argument("--json", action="store_true", help="Output compact JSON")
    p_next = sub.add_parser("next", parents=[plan_parent], help="Output next active milestone tasks")
    p_next.add_argument("--json", action="store_true", help="Output JSON")
    p_cont = sub.add_parser("continue", parents=[plan_parent], help="Resume execution of active milestone")
    p_cont.add_argument("--json", action="store_true", help="Output JSON")
    p_adv = sub.add_parser("advance", parents=[plan_parent], help="Check off tasks and advance milestone")
    p_adv.add_argument("--milestone", type=int, help="Milestone number to complete")
    p_adv.add_argument("--commit", help="Commit SHA to record")
    p_adv.add_argument("--no-sync-parent", action="store_true", help="Skip auto-advancing parent master milestone when child plan completes")
    add_retrospective_parser(sub, plan_parent)
    p_look = sub.add_parser("lookup", parents=[root_parent], help="Search past plans and decisions")
    p_look.add_argument("query", help="Search term, slug, or commit SHA")
    p_ver = sub.add_parser("verify", parents=[plan_parent], help="Run plan verification baseline")
    p_ver.add_argument("--command", "--cmd", dest="command", help="Explicit verifier command")
    register_digest_parser(sub, plan_parent)

    return parser


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    """Main CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)
    arg_root = getattr(args, "root", None)
    repo_root = root or (arg_root.resolve() if arg_root is not None else get_repo_root())
    cmd = args.subcommand or "status"

    handlers = {
        "discover": cmd_discover, "init": cmd_init, "status": cmd_status,
        "next": cmd_next, "continue": cmd_next, "advance": cmd_advance,
        "retrospective": cmd_retrospective, "lookup": cmd_lookup, "verify": cmd_verify, "digest": cmd_digest,
    }
    handler = handlers.get(cmd)
    if not handler:
        parser.print_help()
        return 1
    return handler(repo_root, args)


if __name__ == "__main__":
    sys.exit(main())
