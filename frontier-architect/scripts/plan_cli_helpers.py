#!/usr/bin/env python3
"""Console rendering and parser helpers extracted from plan_engine (keeps plan_engine within budget)."""

from typing import Any
import argparse
import re

_TASK_PATH_RE = re.compile(r"(?:\*\*|`)([A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+)(?:\*\*|`)")


def build_commit_suggestion(ps: dict[str, Any], target_idx: int) -> str:
    """Build a conventional git commit suggestion for the completed milestone."""
    milestone_title = next(
        (m["title"] for m in ps.get("milestones", []) if m.get("index") == target_idx),
        f"milestone {target_idx}",
    )
    stripped_title = re.sub(
        r"\s*(?:—|--)\s*\*?(?:Active Execution Target|Deferred to (?:Next|Future) Turn(?:\s*/\s*Milestone)?|Completed|Pending|In Progress)\*?\s*$",
        "",
        milestone_title,
        flags=re.IGNORECASE,
    )
    stripped_title = re.sub(r"\*?\([^)]*\)\*?", "", stripped_title)
    clean_scope = ps.get("slug", "feature").replace("_plan", "").replace("_", "-")
    clean_title = re.sub(r"[^\w\s-]", "", stripped_title).strip().lower()
    clean_title = re.sub(r"\s+", " ", clean_title) or f"complete milestone {target_idx}"
    return f'git commit -m "feat({clean_scope}): {clean_title}"'


def resolve_commit_hint(
    ps: dict[str, Any],
    target_idx: int,
    code_changes: list[str],
    is_git: bool,
    commit_arg: str | None,
) -> tuple[str, bool]:
    """Return (commit_hint, has_code_diff) without misreporting pre-committed milestones."""
    if is_git and not code_changes:
        if commit_arg:
            return f"(Already committed as {commit_arg})", True
        return "(None - Milestone was verification/audit only; no application code changes)", False
    return build_commit_suggestion(ps, target_idx), True


def assess_plan_scope(parsed: dict[str, Any], ps: dict[str, Any], parent_arg: str | None) -> str | None:
    """Recommend Master Plan hierarchy when a flat roadmap spans >=4 milestones or >=3 subsystems."""
    is_master = (
        bool(ps.get("child_plans"))
        or any(k in ps.get("slug", "").lower() for k in ("master", "roadmap"))
        or any(k in ps.get("title", "").lower() for k in ("master", "roadmap"))
    )
    if parent_arg or ps.get("parent_plan") or is_master:
        return None
    milestones = parsed.get("milestones", [])
    total_tasks = sum(len(m.get("tasks", [])) for m in milestones)
    dirs = {m.group(1).split("/", 1)[0] for ms in milestones for t in ms.get("tasks", []) if (m := _TASK_PATH_RE.search(t.get("text", "")))}
    if len(milestones) >= 4 or (len(dirs) >= 3 and total_tasks >= 10):
        return (
            f"[plan_engine] SCOPE RECOMMENDATION (MASTER PLAN): '{ps['slug']}' has {len(milestones)} milestones, "
            f"{total_tasks} tasks, and {len(dirs)} subsystem prefixes ({', '.join(sorted(dirs)[:4]) or 'multi-area'}).\n"
            f"  Promote to Master Roadmap + Step 1 child plan: plan_engine.py init .TODO/step_1_<slug>.md --parent {ps['slug']} --milestone 1"
        )
    return None


def _suggest_slice_tools(target_m: dict[str, Any]) -> list[str]:
    """Infer high-leverage diagnostic tools from the active milestone's tasks."""
    blob = " ".join(t.get("text", "").lower() for t in target_m.get("tasks", []))
    tools: list[str] = []
    if any(k in blob for k in (".html", ".css", ".js", ".ts", ".jsx", ".tsx", "layout", "modal", "dashboard")) or re.search(r"\b(?:dom|ui)\b", blob):
        tools.append("diagnose.py surface --show-ids --show-routes")
        tools.append("diagnose.py ui --headless --audit-layout")
    if any(k in blob for k in (".py", "router", "service", "refactor", "module", "pool", "pipeline")):
        tools.append("diagnose.py audit --path <modified_files> --max-lines 350 --max-fn-lines 40")
    if any(k in blob for k in ("camera", "directshow", "hardware", "probe", "database", "sqlite", "mqtt")):
        tools.append("diagnose.py probe list")
    if any(k in blob for k in ("defect", "bug", "fix", "scan", "regression")):
        tools.append("diagnose.py scan --path .")
    if any(k in blob for k in ("extract", "split", "helper", ".js", ".py")):
        tools.append('git grep -n "<modified_module_stem>" tests/ (run matching legacy tests before advance)')
    return tools


_SECTION_HEADER_RE = re.compile(r"^\s*\*{0,2}(?:files|verification)\*{0,2}\s*:?\s*$", re.IGNORECASE)


def _is_tactical_master_step(tasks: list[dict[str, Any]] | None) -> bool:
    """Return True when a master step is a concrete, bounded slice (<=4 files, <=6 actionable tasks) or <=3 abstract tasks."""
    if tasks is None:
        return False
    actionable = [t for t in tasks if not _SECTION_HEADER_RE.match(t.get("text", ""))]
    unique_files = {m.group(1) for t in actionable if (m := _TASK_PATH_RE.search(t.get("text", "")))}
    if unique_files:
        return len(unique_files) <= 4 and len(actionable) <= 6
    return len(actionable) <= 3


def print_master_gate(
    ps: dict[str, Any],
    active_idx: int,
    declared_child: str | None = None,
    tasks: list[dict[str, Any]] | None = None,
) -> None:
    """Emit the MASTER STEP PRE-PLAN GATE (or tactical bypass) when a master step has no child plan."""
    if declared_child:
        print(f"Declared Child Plan: {declared_child}")
    is_master_roadmap = (
        bool(ps.get("child_plans"))
        or any(k in ps.get("slug", "").lower() for k in ("master", "roadmap"))
        or any(k in ps.get("title", "").lower() for k in ("master", "roadmap"))
    )
    if is_master_roadmap:
        print("\n" + "=" * 72)
        print(f"[plan_engine] MASTER STEP PRE-PLAN GATE (Step {active_idx}):")
        print("No child implementation plan is linked to this master step yet.")
        if not declared_child and _is_tactical_master_step(tasks):
            print("Tactical Master Step (<=4 files / <=3 abstract tasks, no child plan declared): You MAY execute this step directly in one turn without creating a child plan unless exploration reveals >=3 subsystems or >=10 sub-tasks.")
        else:
            print("MANDATORY: DO NOT implement this entire master step in one turn.")
            print("Instead, execute Pre-Plan -> Child Plan Synthesis:")
            print("  1. Read AGENTS.md and any referenced architecture blueprint (e.g. docs/architecture/).")
            print("  2. Run 'diagnose.py arch-map --path .' and delegate file/import sweeps to a research subagent.")
            print(f"  3. Draft a vertical-sliced child plan (.TODO/step_{active_idx}_<slug>.md) + RequestFeedback artifact.")
            print(f"  4. Register via: plan_engine.py init .TODO/step_{active_idx}_<slug>.md --parent {ps['slug']} --milestone {active_idx}")
        print("=" * 72)


def print_milestone_body(
    target_m: dict[str, Any],
    parsed: dict[str, Any],
    prior_learns: list[str],
    prior_tool_gaps: list[str] | None = None,
) -> None:
    """Print the active slice's tasks, verifiers, prior /learn & tool-gap guards, and pre-flight gate."""
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

    if prior_tool_gaps:
        print("\nPrior Milestone Tool Gaps / Workarounds (Apply Until Fixed):")
        for tg in prior_tool_gaps:
            print(f"  [~] {tg}")

    if slice_tools := _suggest_slice_tools(target_m):
        print("\nAuto-Selected Slice Tools (Use First):")
        for cmd in slice_tools:
            print(f"  - {cmd}")

    print("\nPre-Flight Critic Gate:")
    print("  1. Public Surface Invariants: Document schemas & API contracts before code edits.")
    print("  2. Defensive Edge Cases: Handle timeouts, missing inputs, and boundary conditions.")
    print("  3. Modularity Line Budgets: Target < 350 lines; hard split ceiling at 500 lines.")


def print_advance_summary(
    ps: dict[str, Any], target_idx: int, sha: str | None, commit_hint: str,
    has_code_diff: bool, patched: int, missing_prior_retro: int | None = None,
    scaffold_rel: str | None = None, parent_synced: tuple[str, int] | tuple[str, int, bool] | None = None,
) -> None:
    """Print the milestone-advance result, turn gate, and user-selectable introspective commands."""
    plan_ref = ps.get("plan_path") or ps.get("slug", "plan")
    print(f"[plan_engine] Advanced Milestone {target_idx} (checked {patched} tasks in {plan_ref}).")
    print(f"  Commit: {sha or 'N/A'} | Status: {ps['status']}")
    print(f"  Suggested Commit: {commit_hint}")
    if missing_prior_retro is not None:
        print(f"[plan_engine] RETROSPECTIVE REMINDER: Milestone {missing_prior_retro} has no retrospective logged yet (run `plan_engine.py retrospective {ps['slug']} --milestone {missing_prior_retro} ...`).")
    if ps["status"] == "completed":
        print(f"[plan_engine] MANDATORY BEFORE SIGN-OFF: Log Milestone {target_idx} telemetry via `plan_engine.py retrospective {ps['slug']} --milestone {target_idx} --cid <cid> --tri \"5,5,5,5\" ...`.")
        print(f"[plan_engine] All milestones COMPLETED! Enforce Final Sign-Off Gate (`diagnose.py scan --path .` + `plan_engine.py digest {ps['slug']} --cids <all_cids> --backfill --write-scaffold`).")
        if scaffold_rel:
            print(f"[plan_engine] Learning Scaffold: {scaffold_rel}")
        if ps.get("parent_plan"):
            p = ps["parent_plan"]
            if parent_synced:
                parent_done = len(parent_synced) >= 3 and bool(parent_synced[2])
                if parent_done:
                    print(f"[plan_engine] Master Sync (Auto): Parent '{parent_synced[0]}' Milestone {parent_synced[1]} completed -> Master Roadmap is 100% COMPLETE! (Learning scaffold refreshed; run `/learn` or start a New Conversation (+)).")
                else:
                    print(f"[plan_engine] Master Sync (Auto): Marked parent '{parent_synced[0]}' Milestone {parent_synced[1]} complete -> continue with '/frontier-architect continue {parent_synced[0]}'.")
            else:
                print(f"[plan_engine] Master Sync: Run 'plan_engine.py advance {p['slug']} --milestone {p['milestone']}' then prompt '/frontier-architect continue {p['slug']}'.")
        print(f"[plan_engine] Introspectives (User Choice): Review `{scaffold_rel or 'LEARNING_SCAFFOLD.md'}` -> run `/learn` to persist lessons | optional: `plan_engine.py digest {ps['slug']} --backfill --write-scaffold`")
    else:
        print(f"  Status: in_progress | Next Milestone: {ps['active_milestone_index']}/{ps['total_milestones']}")
        print("=" * 72)
        print(f"[plan_engine] TURN GATE: Milestone {target_idx} COMPLETE!")
        print(f"MANDATORY NEXT STEP: Run `diagnose.py scan --path <modified_paths>` then `plan_engine.py retrospective {ps['slug']} --milestone {target_idx} --cid <cid> --tri \"5,5,5,5\" ...`, then STOP. DO NOT execute Milestone {ps['active_milestone_index']} in this turn.")
        if has_code_diff:
            print(f"Present milestone verification and Suggested Commit to user, then prompt '/frontier-architect continue {ps['slug']}'.")
        else:
            print("Milestone was verification/audit only (no application code files modified; skip git commit).")
            print(f"Present verification results to user, then prompt '/frontier-architect continue {ps['slug']}'.")
        print("Introspectives (User Choice): `/learn` | `diagnose.py transcript-audit --latest 1`")
        print("=" * 72)


def _parse_hypotheses_arg(val: str) -> int:
    """Accept either an integer count or a descriptive hypothesis summary string."""
    s = str(val).strip()
    if s.isdigit():
        return max(1, int(s))
    clauses = [c.strip() for c in re.split(r"[;\n]+|\bH\d+\s*:", s) if c.strip()]
    return max(1, len(clauses))


def add_retrospective_parser(sub: Any, plan_parent: argparse.ArgumentParser) -> None:
    """Register the ``retrospective`` subcommand on plan_engine's subparsers."""
    p_retro = sub.add_parser("retrospective", parents=[plan_parent], help="Log retrospective telemetry")
    p_retro.add_argument("--milestone", type=int, help="Milestone index")
    p_retro.add_argument("--grade", default="A", help="Token Efficiency Grade (A-F)")
    p_retro.add_argument("--tri", help="Tool Reliability Index score (1-5 or tool=score)")
    p_retro.add_argument("--hypotheses", type=_parse_hypotheses_arg, default=1, help="Hypotheses tested (int or summary string)")
    p_retro.add_argument("--retries", type=int, default=None, help="Failed verification/test retries during milestone")
    p_retro.add_argument("--steps", type=int, default=None, help="Total conversation/turn steps taken for milestone")
    p_retro.add_argument("--cid", default=None, help="Conversation ID to auto-populate --steps and --retries from transcript")
    p_retro.add_argument("--brain-dir", default=None, help="Optional brain dir override for --cid")
    p_retro.add_argument("--escalate", help="Root cause escalated to /app-debugger")
    p_retro.add_argument("--learn", help="Project-level candidate proposal for /learn (AGENTS.md)")
    p_retro.add_argument("--skill-learn", help="Skill/script candidate improvement for /learn (SKILL.md or scripts/)")
    p_retro.add_argument("--tool-gap", help="Tooling or script defect encountered during execution")
    p_retro.add_argument("--went-well", default=None, help="Positive execution or architectural pattern that worked well")


def print_retrospective_summary(entry: dict[str, Any], slug: str, scaffold_rel: str | None) -> None:
    """Print retrospective confirmation and copy-pasteable turn-end learning block."""
    print(f"[plan_engine] Logged retrospective for Milestone {entry['milestone_index']}:")
    print(f"  Token Grade: {entry['token_efficiency_grade']} | TRI: {entry['tool_reliability_scores']}")
    pairs = (
        ("/learn candidate (project)", "learn_candidates"),
        ("/learn candidate (skill)", "skill_learn_candidates"),
        ("Tool gap", "tool_gaps"),
        ("Went well", "went_well"),
    )
    for label, key in pairs:
        if entry.get(key):
            print(f"  {label}: {entry[key][0]}")
    if scaffold_rel:
        print(f"  Learning scaffold: {scaffold_rel}")
    print("\n--- Turn-End Echo (Copy-Paste Into Final Response) ---")
    print("### Continuous Learning & Introspective Options")
    if entry.get("went_well"):
        print(f"- **What went well**: {entry['went_well'][0]}")
    for label, key in (("project", "learn_candidates"), ("skill", "skill_learn_candidates")):
        if entry.get(key):
            print(f"- **`/learn` candidate ({label})**: {entry[key][0]}")
    target = scaffold_rel or f".frontier/plans/{slug}/LEARNING_SCAFFOLD.md"
    print(f"- **Introspective Options**: Review `{target}`, run `/learn`, or run `diagnose.py transcript-audit --latest 1`.")
    print("- **Commit Reminder**: Echo the `Suggested Commit` block from `plan_engine.py advance` verbatim when code changed (never run `git commit` before `advance` or without user consent).")
