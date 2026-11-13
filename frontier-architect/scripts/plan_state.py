#!/usr/bin/env python3
"""State ledger and workspace persistence for Frontier Architect plans.

Manages machine-readable JSON state ledgers in <workspace>/.frontier/ including
workspace manifests, per-plan milestone states, verification baselines, and retrospectives.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import subprocess
import sys

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from plan_parser import discover_plans, parse_plan_markdown, slugify


def get_repo_root(target: Path | None = None) -> Path:
    """Find the root workspace or repository containing target."""
    cur = (target or Path.cwd()).resolve()
    for parent in [cur, *cur.parents]:
        if any((parent / d).exists() for d in (".git", ".frontier", ".plans", ".TODO")):
            return parent
    return cur


def get_frontier_dir(root: Path) -> Path:
    """Get or provision the .frontier ledger directory with self-contained .gitignore."""
    fdir = root / ".frontier"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "plans").mkdir(parents=True, exist_ok=True)
    gitignore = fdir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(
            "# Local Frontier Architect state ledger, telemetry, and artifacts\n"
            "# Ignored by default so they never pollute git status; use `git add -f` if versioning is desired.\n"
            "*\n",
            encoding="utf-8",
        )
    return fdir


def get_git_sha(target_dir: Path) -> str:
    """Resolve current HEAD commit SHA."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=target_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return proc.stdout.strip() if proc.returncode == 0 else ""
    except Exception:
        return ""


def load_json(path: Path, default: Any = None) -> Any:
    """Safe JSON file reader."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    """Atomic JSON file writer."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_p = path.with_suffix(".tmp")
    temp_p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp_p.replace(path)


def resolve_plan_path(root: Path, target: str | None = None) -> Path | None:
    """Resolve plan path from explicit argument, active ledger, or discovery."""
    if target:
        direct = (root / target).resolve()
        if direct.is_file():
            return direct
        if Path(target).is_file():
            return Path(target).resolve()
        for p in discover_plans(root):
            if slugify(p.stem) == slugify(target) or target.lower() in p.name.lower():
                return p
        return None

    state = load_json(get_frontier_dir(root) / "state.json", {})
    active_path = state.get("active_plan", {}).get("plan_path")
    if active_path:
        p = (root / active_path).resolve()
        if p.is_file():
            return p

    discovered = discover_plans(root)
    return discovered[0] if discovered else None


def _calc_active_milestone(milestones: list[dict[str, Any]]) -> int:
    """Find the index of the first incomplete milestone."""
    for m in milestones:
        if not m["is_complete"]:
            return m["index"]
    return milestones[-1]["index"] if milestones else 1


def bootstrap_plan(root: Path, plan_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Initialize or synchronize workspace and plan state ledgers."""
    content = plan_path.read_text(encoding="utf-8")
    parsed = parse_plan_markdown(content)
    slug = slugify(plan_path.stem)
    fdir = get_frontier_dir(root)
    pdir = fdir / "plans" / slug
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "artifacts").mkdir(parents=True, exist_ok=True)

    existing = load_json(pdir / "state.json", {})
    prev_shas = {m.get("index"): m.get("commit_sha", "") for m in existing.get("milestones", [])}
    active_idx = _calc_active_milestone(parsed["milestones"])
    all_done = bool(parsed["milestones"]) and all(m["is_complete"] for m in parsed["milestones"])
    now_iso = datetime.now(timezone.utc).isoformat()
    rel_path = plan_path.relative_to(root).as_posix() if plan_path.is_relative_to(root) else plan_path.as_posix()

    plan_state: dict[str, Any] = {
        "slug": slug,
        "title": parsed["title"],
        "plan_path": rel_path,
        "active_milestone_index": active_idx,
        "total_milestones": len(parsed["milestones"]),
        "status": "completed" if all_done else "in_progress",
        "updated_at": now_iso,
        "milestones": [
            {
                "index": m["index"],
                "title": m["title"],
                "total_tasks": len(m["tasks"]),
                "completed_tasks": sum(1 for t in m["tasks"] if t["checked"]),
                "status": "completed" if m["is_complete"] else ("active" if m["index"] == active_idx else "pending"),
                "commit_sha": prev_shas.get(m["index"], ""),
                **({"child_plan": m["child_plan"]} if m.get("child_plan") else {}),
            }
            for m in parsed["milestones"]
        ],
    }
    if existing.get("parent_plan"):
        plan_state["parent_plan"] = existing["parent_plan"]
    if existing.get("child_plans"):
        plan_state["child_plans"] = existing["child_plans"]
    save_json(pdir / "state.json", plan_state)
    if not (pdir / "retrospectives.json").exists():
        save_json(pdir / "retrospectives.json", [])

    ws_state = _sync_workspace_state(fdir, slug, plan_state, get_git_sha(root), now_iso)
    return ws_state, plan_state


def _sync_workspace_state(
    fdir: Path, slug: str, plan_state: dict[str, Any], sha: str, now_iso: str
) -> dict[str, Any]:
    """Sync active plan info into workspace manifest."""
    ws = load_json(fdir / "state.json", {
        "version": "1.0.0",
        "active_plan_slug": slug,
        "active_plan": {},
        "verification_baseline": {"command": "", "last_exit_code": 0, "passed_tests": 0, "failed_tests": 0, "timestamp": ""},
        "retrospectives": [],
        "plan_history": [],
    })
    ws["active_plan_slug"] = slug
    ws["active_plan"] = {
        "title": plan_state["title"],
        "slug": slug,
        "plan_path": plan_state["plan_path"],
        "branch": sha,
        "active_milestone_index": plan_state["active_milestone_index"],
        "total_milestones": plan_state["total_milestones"],
        "status": plan_state["status"],
        "last_checkpoint_at": now_iso,
    }
    history = [p for p in ws.get("plan_history", []) if p.get("slug") != slug]
    history.append({
        "slug": slug,
        "title": plan_state["title"],
        "plan_path": plan_state["plan_path"],
        "status": plan_state["status"],
        "last_updated": now_iso,
    })
    ws["plan_history"] = history
    save_json(fdir / "state.json", ws)
    return ws


def record_milestone_advance(
    fdir: Path, ps: dict[str, Any], target_idx: int, sha: str, now_iso: str
) -> dict[str, Any]:
    """Update plan and workspace ledgers after advancing a milestone."""
    for m in ps["milestones"]:
        if m["index"] == target_idx:
            m["status"] = "completed"
            m["completed_tasks"] = m["total_tasks"]
            m["commit_sha"] = sha
            m["completed_at"] = now_iso

    incomplete = [m for m in ps["milestones"] if m["status"] != "completed"]
    all_done = len(incomplete) == 0
    if not all_done:
        incomplete[0]["status"] = "active"
        ps["active_milestone_index"] = incomplete[0]["index"]
    else:
        ps["active_milestone_index"] = ps["milestones"][-1]["index"] if ps["milestones"] else ps["total_milestones"]
    ps["status"] = "completed" if all_done else "in_progress"
    ps["updated_at"] = now_iso

    save_json(fdir / "plans" / ps["slug"] / "state.json", ps)
    ws = load_json(fdir / "state.json", {})
    if "active_plan" in ws:
        ws["active_plan"]["active_milestone_index"] = ps["active_milestone_index"]
        ws["active_plan"]["status"] = ps["status"]
        ws["active_plan"]["last_checkpoint_at"] = now_iso
        for p in ws.get("plan_history", []):
            if p.get("slug") == ps["slug"]:
                p["status"] = ps["status"]
                p["last_updated"] = now_iso
        save_json(fdir / "state.json", ws)
    sync_parent_child_status(fdir, ps)
    return ps


def link_child_plan(
    root: Path, child_ps: dict[str, Any], parent_target: str, milestone_idx: int | None = None
) -> dict[str, Any] | None:
    """Bind a child implementation plan to a parent master plan milestone/step."""
    parent_p = resolve_plan_path(root, parent_target)
    if not parent_p or parent_p.resolve() == (root / child_ps["plan_path"]).resolve():
        return None
    fdir = get_frontier_dir(root)
    parent_slug = slugify(parent_p.stem)
    parent_ps = load_json(fdir / "plans" / parent_slug / "state.json")
    if not parent_ps:
        _, parent_ps = bootstrap_plan(root, parent_p)
    target_m = milestone_idx if milestone_idx is not None else parent_ps.get("active_milestone_index", 1)

    child_ps["parent_plan"] = {
        "slug": parent_slug,
        "title": parent_ps.get("title", parent_slug),
        "plan_path": parent_ps["plan_path"],
        "milestone": target_m,
    }
    save_json(fdir / "plans" / child_ps["slug"] / "state.json", child_ps)

    parent_ps.setdefault("child_plans", {})[str(target_m)] = {
        "slug": child_ps["slug"],
        "title": child_ps["title"],
        "plan_path": child_ps["plan_path"],
        "status": child_ps["status"],
        "active_milestone_index": child_ps["active_milestone_index"],
        "total_milestones": child_ps["total_milestones"],
    }
    save_json(fdir / "plans" / parent_slug / "state.json", parent_ps)
    # Re-sync workspace active plan back to child plan
    _sync_workspace_state(fdir, child_ps["slug"], child_ps, get_git_sha(root), child_ps["updated_at"])
    return parent_ps


def sync_parent_child_status(fdir: Path, child_ps: dict[str, Any]) -> dict[str, Any] | None:
    """Propagate child plan progress/completion back into its parent master plan state."""
    parent_ref = child_ps.get("parent_plan")
    if not isinstance(parent_ref, dict) or not parent_ref.get("slug"):
        return None
    parent_path = fdir / "plans" / parent_ref["slug"] / "state.json"
    parent_ps = load_json(parent_path)
    if not parent_ps:
        return None
    m_key = str(parent_ref.get("milestone", 1))
    parent_ps.setdefault("child_plans", {})[m_key] = {
        "slug": child_ps["slug"],
        "title": child_ps["title"],
        "plan_path": child_ps["plan_path"],
        "status": child_ps["status"],
        "active_milestone_index": child_ps["active_milestone_index"],
        "total_milestones": child_ps["total_milestones"],
    }
    save_json(parent_path, parent_ps)
    return parent_ps

