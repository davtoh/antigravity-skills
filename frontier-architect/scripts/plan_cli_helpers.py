#!/usr/bin/env python3
"""Console rendering and parser helpers extracted from plan_engine (keeps plan_engine within budget)."""

from typing import Any
import argparse


def print_master_gate(ps: dict[str, Any], active_idx: int) -> None:
    """Emit the MASTER STEP PRE-PLAN GATE when a master roadmap step has no child plan."""
    is_master_roadmap = (
        bool(ps.get("child_plans"))
        or any(k in ps.get("slug", "").lower() for k in ("master", "roadmap"))
        or any(k in ps.get("title", "").lower() for k in ("master", "roadmap"))
    )
    if is_master_roadmap:
        print("\n" + "=" * 72)
        print(f"[plan_engine] MASTER STEP PRE-PLAN GATE (Step {active_idx}):")
        print("No child implementation plan is linked to this master step yet.")
        print("MANDATORY: DO NOT implement this entire master step in one turn.")
        print("Instead, execute Pre-Plan -> Child Plan Synthesis:")
        print("  1. Read AGENTS.md and any referenced architecture blueprint (e.g. docs/architecture/).")
        print("  2. Run 'diagnose.py arch-map --path .' and delegate file/import sweeps to a research subagent.")
        print(f"  3. Draft a vertical-sliced child plan (.TODO/step_{active_idx}_<slug>.md) + RequestFeedback artifact.")
        print(f"  4. Register via: plan_engine.py init .TODO/step_{active_idx}_<slug>.md --parent {ps['slug']} --milestone {active_idx}")
        print("=" * 72)


def print_milestone_body(target_m: dict[str, Any], parsed: dict[str, Any], prior_learns: list[str]) -> None:
    """Print the active slice's tasks, verifiers, prior /learn guards and the pre-flight critic gate."""
    print("Tasks to implement in this vertical slice:")
    for t in target_m["tasks"]:
        chk = "[x]" if t["checked"] else "[ ]"
        print(f"  {chk} {t['text']}")

    if parsed["verification_commands"]:
        print("\nVerification Commands (OS-Agnostic):")
        for v in parsed["verification_commands"]:
            print(f"  {v}")

    if prior_learns:
        print("\nPrior Milestone /learn Guards (Do Not Repeat):")
        for lc in prior_learns:
            print(f"  [!] {lc}")

    print("\nPre-Flight Critic Gate:")
    print("  1. Public Surface Invariants: Document schemas & API contracts before code edits.")
    print("  2. Defensive Edge Cases: Handle timeouts, missing inputs, and boundary conditions.")
    print("  3. Modularity Line Budgets: Target < 350 lines; hard split ceiling at 500 lines.")


def print_advance_summary(ps: dict[str, Any], target_idx: int, sha: str | None, commit_hint: str, has_code_diff: bool, patched: int) -> None:
    """Print the milestone-advance result and the mandatory turn gate."""
    print(f"[plan_engine] Advanced Milestone {target_idx} (checked {patched} tasks).")
    print(f"  Commit: {sha or 'N/A'} | Status: {ps['status']}")
    print(f"  Suggested Commit: {commit_hint}")
    if ps["status"] == "completed":
        print("[plan_engine] All milestones COMPLETED! Enforce Final Sign-Off & Pre-Merge Gate.")
        if ps.get("parent_plan"):
            p = ps["parent_plan"]
            print(f"[plan_engine] Master Sync: Run 'plan_engine.py advance {p['slug']} --milestone {p['milestone']}' to complete parent step.")
    else:
        print(f"  Status: in_progress | Next Milestone: {ps['active_milestone_index']}/{ps['total_milestones']}")
        print("=" * 72)
        print(f"[plan_engine] TURN GATE: Milestone {target_idx} COMPLETE!")
        print("MANDATORY: STOP calling tools. DO NOT execute the next milestone in this turn.")
        if has_code_diff:
            print("Present milestone verification and Suggested Commit to user, then prompt '/frontier-architect continue'.")
        else:
            print("Milestone was verification/audit only (no application code files modified; skip git commit).")
            print("Present verification results to user, then prompt '/frontier-architect continue'.")
        print("=" * 72)


def add_retrospective_parser(sub: Any, plan_parent: argparse.ArgumentParser) -> None:
    """Register the ``retrospective`` subcommand on plan_engine's subparsers."""
    p_retro = sub.add_parser("retrospective", parents=[plan_parent], help="Log retrospective telemetry")
    p_retro.add_argument("--milestone", type=int, help="Milestone index")
    p_retro.add_argument("--grade", default="A", help="Token Efficiency Grade (A-F)")
    p_retro.add_argument("--tri", help="Tool Reliability Index score (1-5 or tool=score)")
    p_retro.add_argument("--hypotheses", type=int, default=1, help="Hypotheses tested")
    p_retro.add_argument("--retries", type=int, default=None, help="Failed verification/test retries during milestone")
    p_retro.add_argument("--steps", type=int, default=None, help="Total conversation/turn steps taken for milestone")
    p_retro.add_argument("--escalate", help="Root cause escalated to /app-debugger")
    p_retro.add_argument("--learn", help="Candidate proposal for /learn")
