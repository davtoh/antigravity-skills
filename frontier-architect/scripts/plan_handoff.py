#!/usr/bin/env python3
"""Completion hand-off text for a finished child plan, so ``next`` says what to do instead of repeating a stale gate."""

from pathlib import Path

from plan_state import get_frontier_dir, load_json


def parent_handoff(root: Path, parent: dict) -> list[str]:
    """Lines to print when a child plan is complete; reflects whether the master step is already advanced."""
    slug, idx = parent["slug"], int(parent["milestone"])
    pstate = load_json(get_frontier_dir(root) / "plans" / slug / "state.json", {})
    done = next((m for m in pstate.get("milestones", []) if m.get("index") == idx and m.get("status") == "completed"), None)
    if not done:
        return [f"[plan_engine] Parent Master Plan: {slug} (Step/Milestone {idx}) -> Run 'plan_engine.py advance {slug} --milestone {idx}' then 'plan_engine.py next {slug}'."]
    nxt = pstate.get("active_milestone_index")
    total = pstate.get("total_milestones")
    if pstate.get("status") == "completed" or (isinstance(nxt, int) and isinstance(total, int) and nxt > total):
        return [f"[plan_engine] Plan complete: master '{slug}' is fully advanced. Run its final sign-off."]
    return [f"[plan_engine] Plan complete: master step {idx} of '{slug}' is already advanced (no further 'advance' needed).",
            f"[plan_engine] Next: Master Step {nxt} is active -> run `/frontier-architect continue {slug}` to pre-plan Step {nxt} into a multi-milestone child plan."]
