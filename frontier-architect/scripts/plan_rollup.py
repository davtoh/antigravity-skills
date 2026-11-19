#!/usr/bin/env python3
"""Master/child retrospective rollup and upsert helpers for Frontier Architect."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import subprocess

from plan_state import bootstrap_plan, get_frontier_dir, load_json, resolve_plan_path, save_json


def _merge_list_unique(base: list[Any], extra: list[Any]) -> list[str]:
    """Combine two lists preserving order and dropping blank/duplicate entries."""
    return list(dict.fromkeys(str(x).strip() for x in [*base, *extra] if str(x).strip()))


def _merge_master_child_entry(rollup: dict[str, Any], manual: dict[str, Any]) -> dict[str, Any]:
    """Merge manual master retrospective notes into a child-plan rollup entry."""
    merged = dict(rollup)
    if manual_cid := (manual.get("master_cid") or manual.get("cid")):
        merged["master_cid"] = manual_cid
    for key in ("went_well", "learn_candidates", "skill_learn_candidates", "tool_gaps", "root_causes_escalated"):
        merged[key] = _merge_list_unique(rollup.get(key) or [], manual.get(key) or [])
    if manual.get("notes"):
        merged["notes"] = manual["notes"]
    return merged


def _upsert_retro(entries: list[dict[str, Any]], entry: dict[str, Any], slug: str | None = None) -> None:
    """Replace an incomplete, same-CID, or child-rollup entry for the same milestone."""
    m_idx = entry.get("milestone_index")
    new_cid = str(entry.get("cid") or "").lower()
    for i, old in enumerate(entries):
        if not isinstance(old, dict) or old.get("milestone_index") != m_idx:
            continue
        if slug and old.get("_slug") != slug:
            continue
        old_cid = str(old.get("cid") or "").lower()
        cid_match = bool(old_cid and new_cid and (old_cid.startswith(new_cid) or new_cid.startswith(old_cid)))
        incomplete_retry = bool(old.get("steps") is None and (new_cid or entry.get("steps") is not None))
        if old.get("child_slug") and not entry.get("child_slug"):
            merged = _merge_master_child_entry(old, entry)
            entries[i] = {**merged, "_slug": slug} if slug else merged
            return
        if cid_match or incomplete_retry:
            entries[i] = entry
            return
    entries.append(entry)


def _build_rollup_entry(child_retros: list[dict[str, Any]], milestone_idx: int, c_slug: str) -> dict[str, Any]:
    """Aggregate child retrospective metrics and lessons into one master entry."""
    grades = [str(r.get("token_efficiency_grade") or "A").upper() for r in child_retros]
    worst_grade = max(grades, key=lambda g: {"A": 1, "B": 2, "C": 3, "D": 4, "F": 5}.get(g, 0))
    _collect = lambda k: list(dict.fromkeys(str(x) for r in child_retros for x in (r.get(k) or []) if str(x).strip()))
    return {
        "milestone_index": milestone_idx, "timestamp": datetime.now(timezone.utc).isoformat(),
        "token_efficiency_grade": worst_grade,
        "tool_reliability_scores": {"overall": child_retros[-1].get("tool_reliability_scores", {}).get("overall", 5)},
        "hypotheses_tested": sum(int(r.get("hypotheses_tested") or 1) for r in child_retros),
        "root_causes_escalated": _collect("root_causes_escalated"), "learn_candidates": _collect("learn_candidates"),
        "skill_learn_candidates": _collect("skill_learn_candidates"), "tool_gaps": _collect("tool_gaps"),
        "went_well": _collect("went_well"),
        "retries": sum(int(r.get("retries") or 0) for r in child_retros),
        "steps": sum(int(r.get("steps") or 0) for r in child_retros), "child_slug": c_slug,
    }


def rollup_child_retrospective(root: Path, ps: dict[str, Any], milestone_idx: int, refresh: bool = False) -> bool:
    """Synthesize or refresh a master milestone retrospective from its linked child plan."""
    c_info = (ps.get("child_plans") or {}).get(str(milestone_idx))
    c_slug = c_info.get("slug") if isinstance(c_info, dict) else None
    if not c_slug:
        return False
    fdir = get_frontier_dir(root)
    master_retro_p = fdir / "plans" / ps["slug"] / "retrospectives.json"
    master_retros = load_json(master_retro_p, [])
    hit = next((i for i, r in enumerate(master_retros) if isinstance(r, dict) and r.get("milestone_index") == milestone_idx), None)
    if hit is not None and not refresh:
        return False
    child_retros = [r for r in load_json(fdir / "plans" / c_slug / "retrospectives.json", []) if isinstance(r, dict)]
    if not child_retros:
        return False
    entry = _build_rollup_entry(child_retros, milestone_idx, c_slug)
    if hit is not None:
        entry = _merge_master_child_entry(entry, master_retros[hit])
        master_retros[hit] = entry
    else:
        master_retros.append(entry)
    save_json(master_retro_p, master_retros)
    ws = load_json(fdir / "state.json", {})
    ws_list = ws.setdefault("retrospectives", [])
    ws_hit = next((i for i, o in enumerate(ws_list) if isinstance(o, dict) and o.get("_slug") == ps["slug"] and o.get("milestone_index") == milestone_idx), None)
    if ws_hit is not None:
        ws_list[ws_hit] = {**entry, "_slug": ps["slug"]}
    else:
        _upsert_retro(ws_list, {**entry, "_slug": ps["slug"]}, slug=ps["slug"])
    save_json(fdir / "state.json", ws)
    return True


def _refresh_parent_rollup(root: Path, ps: dict[str, Any], brain_dir: str | None) -> None:
    """Refresh parent master rollup and scaffold when a child plan logs a retrospective."""
    parent = ps.get("parent_plan")
    if not isinstance(parent, dict) or not parent.get("slug"):
        return
    parent_p = resolve_plan_path(root, parent["slug"])
    if not parent_p:
        return
    _, parent_ps = bootstrap_plan(root, parent_p)
    if rollup_child_retrospective(root, parent_ps, int(parent["milestone"]), refresh=True):
        from plan_digest import write_learning_scaffold
        write_learning_scaffold(root, parent_ps["slug"], backfill=False, brain_dir=brain_dir)


def sync_pending_commit_shas(root: Path, ps: dict[str, Any]) -> bool:
    """Resolve `pending:<base_sha>` milestone commit SHAs from subsequent git commits."""
    milestones = ps.get("milestones") or []
    used = {str(m.get("commit_sha") or "") for m in milestones if m.get("commit_sha") and not str(m.get("commit_sha")).startswith("pending")}
    changed = False
    for m in milestones:
        sha = str(m.get("commit_sha") or "")
        if m.get("status") != "completed" or not sha.startswith("pending"):
            continue
        base = sha.split(":", 1)[1] if ":" in sha else ""
        rev_range = f"{base}..HEAD" if base else "HEAD"
        try:
            res = subprocess.run(
                ["git", "log", rev_range, "--format=%h", "--reverse", "-n", "50"],
                cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3.0,
            )
        except (OSError, subprocess.SubprocessError):
            break
        if res.returncode != 0:
            continue
        hit = next((h.strip() for h in res.stdout.splitlines() if h.strip() and h.strip() != base and h.strip() not in used), None)
        if hit:
            m["commit_sha"] = hit
            used.add(hit)
            changed = True
    if changed:
        save_json(get_frontier_dir(root) / "plans" / ps["slug"] / "state.json", ps)
    return changed
