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

from plan_parser import discover_plans, parse_plan_markdown, patch_milestone_checkboxes, slugify
from plan_state import (
    bootstrap_plan, get_frontier_dir, get_git_sha, get_repo_root,
    load_json, record_milestone_advance, resolve_plan_path, save_json,
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


def cmd_init(root: Path, args: argparse.Namespace) -> int:
    """Explicitly bind or auto-initialize a plan ledger."""
    target = resolve_plan_path(root, args.plan)
    if not target:
        print(f"[plan_engine] Error: Plan '{args.plan or ''}' could not be resolved.")
        return 1
    _ws, ps = bootstrap_plan(root, target)
    print(f"[plan_engine] Initialized plan: {ps['title']}")
    print(f"  Slug: {ps['slug']} | Active Milestone: {ps['active_milestone_index']}/{ps['total_milestones']}")
    print(f"  Status: {ps['status']} | Path: {ps['plan_path']}")
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
    print(f"Progress: [{bar}] {pct}% (Milestone {ps['active_milestone_index']} of {ps['total_milestones']})")
    vb = ws.get("verification_baseline", {})
    if vb.get("command"):
        print(f"Baseline: {vb.get('command')} -> Exit: {vb.get('last_exit_code')} ({vb.get('passed_tests')} passed)")
    print("\nMilestones:")
    for m in ps["milestones"]:
        mark = "✓" if m["status"] == "completed" else ("▶" if m["status"] == "active" else " ")
        sha_str = f" [{m['commit_sha']}]" if m.get("commit_sha") else ""
        print(f"  [{mark}] Milestone {m['index']}: {m['title']} ({m['completed_tasks']}/{m['total_tasks']} tasks){sha_str}")
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

    all_done = ps["status"] == "completed" or (bool(parsed["milestones"]) and all(m["is_complete"] for m in parsed["milestones"]))
    if all_done or not target_m:
        if args.json:
            print(json.dumps({"status": "completed", "title": ps["title"], "milestone": None, "verifiers": parsed["verification_commands"]}, indent=2))
        else:
            print(f"[plan_engine] All milestones in '{ps['title']}' are completed! Run final sign-off.")
        return 0
    if args.json:
        print(json.dumps({"milestone": target_m, "verifiers": parsed["verification_commands"]}, indent=2))
        return 0

    print(f"=== Active Milestone: {target_m['index']} - {target_m['title']} ===")
    print("Tasks to implement in this vertical slice:")
    for t in target_m["tasks"]:
        chk = "[x]" if t["checked"] else "[ ]"
        print(f"  {chk} {t['text']}")

    if parsed["verification_commands"]:
        print("\nVerification Commands (OS-Agnostic):")
        for v in parsed["verification_commands"]:
            print(f"  {v}")

    print("\nPre-Flight Critic Gate:")
    print("  1. Public Surface Invariants: Document schemas & API contracts before code edits.")
    print("  2. Defensive Edge Cases: Handle timeouts, missing inputs, and boundary conditions.")
    print("  3. Modularity Line Budgets: Target < 350 lines; hard split ceiling at 500 lines.")
    return 0


def _build_commit_suggestion(ps: dict[str, Any], target_idx: int) -> str:
    """Build a conventional git commit suggestion for the completed milestone."""
    milestone_title = next(
        (m["title"] for m in ps.get("milestones", []) if m.get("index") == target_idx),
        f"milestone {target_idx}",
    )
    clean_scope = ps.get("slug", "feature").replace("_plan", "").replace("_", "-")
    clean_title = re.sub(r"[^\w\s-]", "", milestone_title).strip().lower()
    clean_title = re.sub(r"\s+", " ", clean_title) or f"complete milestone {target_idx}"
    return f'git commit -m "feat({clean_scope}): {clean_title}"'


def cmd_advance(root: Path, args: argparse.Namespace) -> int:
    """In-place patch markdown checklist, record commit SHA, and advance milestone."""
    plan_p = resolve_plan_path(root, args.plan)
    if not plan_p:
        print("[plan_engine] Error: No plan resolved.")
        return 1
    _ws, ps = bootstrap_plan(root, plan_p)
    target_idx = args.milestone or ps["active_milestone_index"]

    patched = patch_milestone_checkboxes(plan_p, target_idx)
    sha = args.commit or get_git_sha(root)
    now_iso = datetime.now(timezone.utc).isoformat()
    fdir = get_frontier_dir(root)
    ps = record_milestone_advance(fdir, ps, target_idx, sha, now_iso)
    commit_hint = _build_commit_suggestion(ps, target_idx)

    print(f"[plan_engine] Advanced Milestone {target_idx} (checked {patched} tasks).")
    print(f"  Commit: {sha or 'N/A'} | Status: {ps['status']}")
    print(f"  Suggested Commit: {commit_hint}")
    if ps["status"] == "completed":
        print("[plan_engine] All milestones COMPLETED! Enforce Final Sign-Off & Pre-Merge Gate.")
    else:
        print(f"  Status: in_progress | Next Milestone: {ps['active_milestone_index']}/{ps['total_milestones']}")
        print("=" * 72)
        print(f"[plan_engine] TURN GATE: Milestone {target_idx} COMPLETE!")
        print("MANDATORY: STOP calling tools. DO NOT execute the next milestone in this turn.")
        print("Present milestone verification and Suggested Commit to user, then prompt '/frontier-architect continue'.")
        print("=" * 72)
    return 0


def _parse_tri(tri_arg: str | None) -> dict[str, int]:
    """Parse tool reliability index argument into dictionary."""
    if not tri_arg:
        return {}
    scores = {}
    for item in tri_arg.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" in item:
            k, v = item.split("=", 1)
            try:
                scores[k.strip()] = int(v.strip())
            except ValueError:
                pass
        else:
            try:
                scores["overall"] = int(item.strip())
            except ValueError:
                pass
    return scores


def cmd_retrospective(root: Path, args: argparse.Namespace) -> int:
    """Record Token Efficiency Grade, TRI, and /learn candidate proposals."""
    plan_p = resolve_plan_path(root, args.plan)
    if not plan_p:
        print("[plan_engine] Error: No plan resolved.")
        return 1
    _ws, ps = bootstrap_plan(root, plan_p)
    fdir = get_frontier_dir(root)
    retro_path = fdir / "plans" / ps["slug"] / "retrospectives.json"
    retros = load_json(retro_path, [])

    entry = {
        "milestone_index": args.milestone or ps["active_milestone_index"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "token_efficiency_grade": (args.grade or "A").upper(),
        "tool_reliability_scores": _parse_tri(args.tri),
        "hypotheses_tested": args.hypotheses or 1,
        "root_causes_escalated": [args.escalate] if args.escalate else [],
        "learn_candidates": [args.learn] if args.learn else [],
    }
    retros.append(entry)
    save_json(retro_path, retros)

    ws = load_json(fdir / "state.json", {})
    ws.setdefault("retrospectives", []).append(entry)
    save_json(fdir / "state.json", ws)

    print(f"[plan_engine] Logged retrospective for Milestone {entry['milestone_index']}:")
    print(f"  Token Grade: {entry['token_efficiency_grade']} | TRI: {entry['tool_reliability_scores']}")
    if entry["learn_candidates"]:
        print(f"  /learn candidate: {entry['learn_candidates'][0]}")
    return 0


def cmd_lookup(root: Path, args: argparse.Namespace) -> int:
    """Surface past decisions, milestones, commits, and retrospectives."""
    q = args.query.lower().strip()
    fdir = get_frontier_dir(root)
    ws = load_json(fdir / "state.json", {})
    results: list[dict[str, Any]] = []

    for item in ws.get("plan_history", []):
        if q in item.get("slug", "").lower() or q in item.get("title", "").lower():
            results.append({"type": "plan", "item": item})

    for pdir in (fdir / "plans").glob("*"):
        st = load_json(pdir / "state.json", {})
        if not st:
            continue
        for m in st.get("milestones", []):
            if q in m.get("title", "").lower() or q in m.get("commit_sha", "").lower():
                results.append({"type": "milestone", "plan": st.get("slug"), "milestone": m})
        for r in load_json(pdir / "retrospectives.json", []):
            learns = " ".join(r.get("learn_candidates", [])).lower()
            escs = " ".join(r.get("root_causes_escalated", [])).lower()
            if q in learns or q in escs:
                results.append({"type": "retrospective", "plan": st.get("slug"), "retro": r})

    if not results:
        print(f"[plan_engine] No historical decisions or plans matched query '{args.query}'.")
        return 0

    print(f"[plan_engine] Lookup results for '{args.query}' ({len(results)} matches):")
    for r in results:
        if r["type"] == "plan":
            print(f"  [PLAN] {r['item'].get('title')} ({r['item'].get('slug')}) - {r['item'].get('status')}")
        elif r["type"] == "milestone":
            m = r["milestone"]
            print(f"  [MILESTONE] Plan: {r['plan']} -> M{m.get('index')}: {m.get('title')} (sha: {m.get('commit_sha')})")
        elif r["type"] == "retrospective":
            print(f"  [RETRO] Plan: {r['plan']} M{r['retro'].get('milestone_index')}: Learn={r['retro'].get('learn_candidates')}")
    return 0


def cmd_verify(root: Path, args: argparse.Namespace) -> int:
    """Run verification command and update baseline ledger."""
    cmd = args.command
    plan_p = resolve_plan_path(root, args.plan)
    if not cmd and plan_p:
        parsed = parse_plan_markdown(plan_p.read_text(encoding="utf-8"))
        if parsed["verification_commands"]:
            cmd = parsed["verification_commands"][0]
    if not cmd:
        ws_existing = load_json(get_frontier_dir(root) / "state.json", {})
        cmd = ws_existing.get("verification_baseline", {}).get("command")

    if not cmd:
        print(
            "[plan_engine] Error: No verification command specified or found in plan. "
            'Pass --command "<cmd>" or include runnable commands in code blocks / Scenario Matrix tables.'
        )
        return 1

    print(f"[plan_engine] Running verifier: {cmd}")
    proc = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    output = (proc.stdout or "") + (proc.stderr or "")
    print(output)

    passed, failed = 0, 0
    ok_match = re.search(r"Ran (\d+) tests?.*?\n\nOK", output)
    if ok_match:
        passed = int(ok_match.group(1))
    fail_match = re.search(r"FAILED \((?:failures=(\d+))?(?:, )?(?:errors=(\d+))?\)", output)
    if fail_match:
        failed = sum(int(x) for x in fail_match.groups() if x)

    fdir = get_frontier_dir(root)
    ws = load_json(fdir / "state.json", {})
    ws["verification_baseline"] = {
        "command": cmd,
        "last_exit_code": proc.returncode,
        "passed_tests": passed,
        "failed_tests": failed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    save_json(fdir / "state.json", ws)
    return proc.returncode


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser with subcommands."""
    parser = argparse.ArgumentParser(description="Frontier Architect Plan & Continuation Engine")
    sub = parser.add_subparsers(dest="subcommand", help="Engine subcommands")

    sub.add_parser("discover", help="Discover architectural plans in workspace")
    p_init = sub.add_parser("init", help="Initialize or bind active plan")
    p_init.add_argument("plan", nargs="?", help="Path or slug of plan")
    plan_parent = argparse.ArgumentParser(add_help=False)
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
    p_retro = sub.add_parser("retrospective", parents=[plan_parent], help="Log retrospective telemetry")
    p_retro.add_argument("--milestone", type=int, help="Milestone index")
    p_retro.add_argument("--grade", default="A", help="Token Efficiency Grade (A-F)")
    p_retro.add_argument("--tri", help="Tool Reliability Index score (1-5 or tool=score)")
    p_retro.add_argument("--hypotheses", type=int, default=1, help="Hypotheses tested")
    p_retro.add_argument("--escalate", help="Root cause escalated to /app-debugger")
    p_retro.add_argument("--learn", help="Candidate proposal for /learn")
    p_look = sub.add_parser("lookup", help="Search past plans and decisions")
    p_look.add_argument("query", help="Search term, slug, or commit SHA")
    p_ver = sub.add_parser("verify", parents=[plan_parent], help="Run plan verification baseline")
    p_ver.add_argument("--command", "--cmd", dest="command", help="Explicit verifier command")

    return parser


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    """Main CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = root or get_repo_root()
    cmd = args.subcommand or "status"

    handlers = {
        "discover": cmd_discover, "init": cmd_init, "status": cmd_status,
        "next": cmd_next, "continue": cmd_next, "advance": cmd_advance,
        "retrospective": cmd_retrospective, "lookup": cmd_lookup, "verify": cmd_verify,
    }
    handler = handlers.get(cmd)
    if not handler:
        parser.print_help()
        return 1
    return handler(repo_root, args)


if __name__ == "__main__":
    sys.exit(main())
