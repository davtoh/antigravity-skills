#!/usr/bin/env python3
"""Plan ledger reconciliation: detect stale states, duplicate milestones, and uncheckboxed tasks."""

import argparse
import json
from pathlib import Path
from typing import Any

from plan_parser import M_REGEX, discover_plans, parse_plan_markdown, slugify
from plan_state import get_frontier_dir, load_json, save_json


def _find_duplicate_milestones(text: str) -> list[int]:
    """Return milestone indices declared more than once in markdown."""
    seen: set[int] = set()
    dupes: list[int] = []
    for line in text.splitlines():
        if m := M_REGEX.match(line):
            idx = int(m.group(2))
            if idx in seen and idx not in dupes:
                dupes.append(idx)
            seen.add(idx)
    return dupes


def inspect_workspace_plans(root: Path) -> list[dict[str, Any]]:
    """Audit discovered markdown plans and .frontier/plans/*/state.json for drift."""
    fdir = get_frontier_dir(root)
    plans_by_slug: dict[str, Path] = {slugify(p.stem): p for p in discover_plans(root)}
    state_dirs = sorted((fdir / "plans").glob("*/state.json"))
    seen_slugs: set[str] = set()
    rows: list[dict[str, Any]] = []
    for sp in state_dirs:
        ps = load_json(sp, {})
        slug = ps.get("slug") or sp.parent.name
        seen_slugs.add(slug)
        plan_p = plans_by_slug.get(slug)
        if not plan_p and (rel := ps.get("plan_path")):
            cand = (root / rel).resolve()
            plan_p = cand if cand.is_file() else None
        rows.append(_analyze_one(root, slug, ps, plan_p, sp))
    for slug, plan_p in sorted(plans_by_slug.items()):
        if slug not in seen_slugs:
            rows.append(_analyze_one(root, slug, {}, plan_p, None))
    return rows


def _analyze_one(root: Path, slug: str, ps: dict[str, Any], plan_p: Path | None, sp: Path | None) -> dict[str, Any]:
    """Build one diagnostic row for a plan slug."""
    issues: list[str] = []
    state_status = ps.get("status", "untracked")
    unchecked_cb = plain_bullets = 0
    if not plan_p or not plan_p.is_file():
        if state_status == "in_progress":
            issues.append("stale_missing_plan")
    else:
        raw = plan_p.read_text(encoding="utf-8", errors="replace")
        if dupes := _find_duplicate_milestones(raw):
            issues.append(f"duplicate_milestones:{','.join(str(d) for d in dupes)}")
        parsed = parse_plan_markdown(raw)
        tasks = [t for m in parsed["milestones"] for t in m["tasks"]]
        unchecked_cb = sum(1 for t in tasks if t.get("has_checkbox") and not t["checked"])
        plain_bullets = sum(1 for t in tasks if not t.get("has_checkbox"))
        if plain_bullets > 0 and unchecked_cb == 0:
            issues.append(f"uncheckboxed_bullets:{plain_bullets}")
        elif state_status == "in_progress" and unchecked_cb == 0:
            issues.append("stale_in_progress_zero_unchecked" if parsed["milestones"] else "legacy_no_milestones")
    rel = plan_p.relative_to(root).as_posix() if plan_p and plan_p.is_relative_to(root) else (ps.get("plan_path") or "-")
    return {"slug": slug, "status": state_status, "path": rel, "unchecked": unchecked_cb, "issues": issues, "state_path": str(sp) if sp else ""}


def apply_reconcile(rows: list[dict[str, Any]]) -> list[str]:
    """Mark stale_in_progress_zero_unchecked / stale_missing_plan ledgers completed."""
    updated: list[str] = []
    for r in rows:
        if not r["state_path"] or not any(i in r["issues"] for i in ("stale_in_progress_zero_unchecked", "stale_missing_plan", "legacy_no_milestones")):
            continue
        sp = Path(r["state_path"])
        ps = load_json(sp, {})
        if ps.get("status") == "in_progress":
            ps["status"] = "completed"
            save_json(sp, ps)
            updated.append(r["slug"])
    return updated


def cmd_reconcile(root: Path, args: argparse.Namespace) -> int:
    """CLI handler for ``plan_engine.py reconcile``."""
    rows = inspect_workspace_plans(root)
    applied = apply_reconcile(rows) if getattr(args, "apply", False) else []
    flagged = [r for r in rows if r["issues"]]
    if getattr(args, "json", False):
        print(json.dumps({"total": len(rows), "flagged": flagged, "applied": applied}, indent=2))
        return 0
    print(f"[plan_engine] Reconciled {len(rows)} plan(s): {len(flagged)} issue(s) found.")
    for r in flagged:
        print(f"  - {r['slug']} [{r['status']}] ({r['path']}): {', '.join(r['issues'])}")
    if applied:
        print(f"[plan_engine] Marked {len(applied)} stale ledger(s) completed: {', '.join(applied)}")
    elif any("stale_" in i or "legacy_" in i for r in flagged for i in r["issues"]):
        print("  Tip: pass `--apply` to mark stale in_progress ledgers completed.")
    return 0


def register_reconcile_parser(sub: Any, root_parent: argparse.ArgumentParser) -> None:
    """Register the ``reconcile`` subcommand on plan_engine."""
    p = sub.add_parser("reconcile", parents=[root_parent], help="Detect stale in_progress plans, duplicate milestones, and uncheckboxed bullets")
    p.add_argument("--apply", action="store_true", help="Mark stale in_progress state ledgers completed")
    p.add_argument("--json", action="store_true", help="Output JSON")
