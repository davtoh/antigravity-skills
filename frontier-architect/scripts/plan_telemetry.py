#!/usr/bin/env python3
"""Telemetry, retrospective logging, lookup, and verification helpers for plan_engine."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import argparse
import sys

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from plan_cli_helpers import print_retrospective_summary
from plan_state import bootstrap_plan, get_frontier_dir, load_json, resolve_plan_path, save_json
from plan_verify import (  # noqa: F401
    _extract_leading_env,
    _normalize_verify_cmd,
    _parse_test_counts,
    _resolve_venv_python,
    cmd_verify,
)


def _clamp_tri_score(val: int) -> int:
    """Clamp a TRI dimension score to the valid 1..5 inclusive scale."""
    return max(1, min(5, val))


def _parse_tri(tri_arg: str | None) -> dict[str, Any]:
    """Parse tool reliability index argument into dictionary with scores clamped 1..5."""
    if not tri_arg:
        return {}
    items = [item.strip() for item in tri_arg.split(",") if item.strip()]
    if items and all("=" not in item and ":" not in item for item in items) and len(items) == 4:
        dims = ["token_efficiency", "hypothesis_accuracy", "tool_reliability", "architectural_defense"]
        try:
            vals = [_clamp_tri_score(int(x)) for x in items]
            scores: dict[str, Any] = dict(zip(dims, vals))
            avg = sum(vals) / 4.0
            scores["overall"] = int(avg) if avg.is_integer() else round(avg, 2)
            return scores
        except ValueError:
            pass
    scores = {}
    for item in items:
        sep = "=" if "=" in item else (":" if ":" in item else None)
        if sep:
            k, v = item.split(sep, 1)
            try:
                scores[k.strip()] = _clamp_tri_score(int(v.strip()))
            except ValueError:
                pass
        else:
            try:
                scores["overall"] = _clamp_tri_score(int(item))
            except ValueError:
                pass
    return scores


def _collect_prior_retro_field(root: Path, slug: str, field: str) -> list[str]:
    """Return deduplicated non-empty strings from ``field`` across prior milestones for ``slug``."""
    entries = load_json(get_frontier_dir(root) / "plans" / slug / "retrospectives.json", [])
    if not isinstance(entries, list):
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for item in entry.get(field, []) or []:
            text = str(item).strip()
            if text and text not in seen:
                seen.add(text)
                ordered.append(text)
    return ordered


def get_prior_learn_candidates(root: Path, slug: str) -> list[str]:
    """Return deduplicated learn_candidates recorded in prior milestones for ``slug``."""
    return _collect_prior_retro_field(root, slug, "learn_candidates")


def get_prior_tool_gaps(root: Path, slug: str) -> list[str]:
    """Return deduplicated tool_gaps recorded in prior milestones for ``slug``."""
    return _collect_prior_retro_field(root, slug, "tool_gaps")


def _cap_grade_by_rubric(grade: str, retries: int | None, steps: int | None) -> str:
    """Cap retrospective Token Efficiency Grade against --retries and --steps thresholds."""
    norm = (grade or "A").strip().upper()[:1]
    grade = norm if norm in ("A", "B", "C", "D", "F") else "A"
    if retries is not None:
        if retries > 3 and grade in ("A", "B"):
            print(f"[plan_engine] Rubric Guard: {retries} retries > 3 -> capping Token Grade '{grade}' to 'C'.")
            grade = "C"
        elif retries >= 2 and grade == "A":
            print(f"[plan_engine] Rubric Guard: {retries} retries >= 2 -> capping Token Grade 'A' to 'B'.")
            grade = "B"
    if steps is not None:
        if steps > 100 and grade in ("A", "B"):
            print(f"[plan_engine] Rubric Guard: {steps} steps > 100 -> capping Token Grade '{grade}' to 'C'.")
            grade = "C"
        elif steps > 60 and grade == "A":
            print(f"[plan_engine] Rubric Guard: {steps} steps > 60 -> capping Token Grade 'A' to 'B'.")
            grade = "B"
    return grade


def _cap_tri_by_grade(tri_scores: dict[str, Any], grade: str) -> dict[str, Any]:
    """Keep token_efficiency and hypothesis_accuracy consistent with capped grade."""
    cap = {"B": 4, "C": 3, "D": 2, "F": 1}.get(grade)
    if cap and tri_scores:
        for k in ("token_efficiency", "hypothesis_accuracy"):
            if isinstance(tri_scores.get(k), int):
                tri_scores[k] = min(tri_scores[k], cap)
        dims = [tri_scores[k] for k in ("token_efficiency", "hypothesis_accuracy", "tool_reliability", "architectural_defense") if isinstance(tri_scores.get(k), int)]
        if len(dims) == 4:
            avg = sum(dims) / 4.0
            tri_scores["overall"] = int(avg) if avg.is_integer() else round(avg, 2)
    return tri_scores


_IGNORED_ITEMS = {"", "none", "n/a", "null"}


def _clean_list(val: str | None) -> list[str]:
    """Return single-item list unless ``val`` is empty or a placeholder ('none', 'N/A', 'null')."""
    text = str(val).strip() if val is not None else ""
    return [text] if text and text.lower() not in _IGNORED_ITEMS else []


def _build_retrospective_entry(
    milestone_idx: int, tri_scores: dict[str, int], grade: str,
    retries: int | None, steps: int | None, args: argparse.Namespace,
) -> dict[str, Any]:
    """Assemble retrospective telemetry payload with optional retry/step/skill/went_well fields."""
    went_well = _clean_list(getattr(args, "went_well", None))
    if not went_well and steps is not None and grade in ("A", "B") and (retries is None or retries <= 1):
        went_well = [f"Completed within budget (steps={steps if steps is not None else '?'}, retries={retries if retries is not None else 0})"]
    entry: dict[str, Any] = {
        "milestone_index": milestone_idx,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "token_efficiency_grade": grade,
        "tool_reliability_scores": tri_scores,
        "hypotheses_tested": args.hypotheses or 1,
        "root_causes_escalated": _clean_list(args.escalate),
        "learn_candidates": _clean_list(args.learn),
        "skill_learn_candidates": _clean_list(getattr(args, "skill_learn", None)),
        "tool_gaps": _clean_list(getattr(args, "tool_gap", None)),
        "went_well": went_well,
    }
    if retries is not None:
        entry["retries"] = retries
    if steps is not None:
        entry["steps"] = steps
    return entry


def _resolve_cid_telemetry(
    args: argparse.Namespace, steps: int | None, retries: int | None
) -> tuple[int | None, int | None, str | None]:
    """Populate steps/retries (preferring empirical --cid transcript counts) and canonicalize short CIDs."""
    cid = getattr(args, "cid", None)
    if not cid:
        return steps, retries, None
    from plan_digest import audit_single_cid
    if row := audit_single_cid(cid, getattr(args, "brain_dir", None)):
        cid = str(row.get("cid") or cid)
        steps = row["steps"]
        retries = row["total_failures"]
    return steps, retries, cid


from plan_rollup import (  # noqa: F401
    _merge_list_unique,
    _merge_master_child_entry,
    _refresh_parent_rollup,
    _upsert_retro,
    rollup_child_retrospective,
)


def _enrich_entry_from_audit(entry: dict[str, Any], cid: str | None, brain_dir: str | None) -> None:
    """Auto-surface transcript-audit flags and high repeat reads into skill_learn_candidates."""
    if not cid:
        return
    try:
        from plan_digest import audit_single_cid
        row = audit_single_cid(cid, brain_dir)
    except Exception:
        return
    if not row:
        return
    cands = entry.setdefault("skill_learn_candidates", [])
    parallel_items = row.get("parallel_same_file_edits") or []
    if parallel_items:
        files = list(dict.fromkeys(
            Path(str(it.get("path") or it.get("file") or "?")).name
            for it in parallel_items if isinstance(it, dict)
        ))
        detail = f" ({', '.join(files[:4])})" if files else ""
        msg = f"Transcript audit: {len(parallel_items)} parallel same-file edit(s){detail}"
        if msg not in cands:
            cands.append(msg)
    heavy_repeats = [f"{Path(str(k)).name} ({v}x)" for k, v in (row.get("repeated_reads") or {}).items() if int(v) >= 3]
    if heavy_repeats:
        msg = f"Transcript audit: repeated file reads (>=3x): {', '.join(heavy_repeats[:4])}"
        if msg not in cands:
            cands.append(msg)


def _apply_retry_floors(tri_scores: dict[str, Any], entry: dict[str, Any], retries: int | None, raw_hyp: int | None) -> None:
    """Ensure tool_reliability <= 4 and hypotheses_tested > 1 when retries occurred."""
    if retries is None or retries <= 0:
        return
    if isinstance(tri_scores.get("tool_reliability"), int):
        tri_scores["tool_reliability"] = min(tri_scores["tool_reliability"], 4)
        dims = [tri_scores[k] for k in ("token_efficiency", "hypothesis_accuracy", "tool_reliability", "architectural_defense") if isinstance(tri_scores.get(k), int)]
        if len(dims) == 4:
            avg = sum(dims) / 4.0
            tri_scores["overall"] = int(avg) if avg.is_integer() else round(avg, 2)
    if (raw_hyp or 1) == 1:
        entry["hypotheses_tested"] = max(1, 1 + retries)


def _resolve_retro_inputs(args: argparse.Namespace) -> tuple[dict[str, Any], int | None, int | None, str | None]:
    """Parse --tri, steps, retries, and --cid, warning when telemetry metadata is omitted."""
    tri_scores = _parse_tri(args.tri)
    if args.tri and not tri_scores:
        print(f"[plan_engine] Warning: Could not parse --tri '{args.tri}'. Use 'k=5,k2=4' or '5,5,5,5'.")
    elif not args.tri:
        print("[plan_engine] Warning: --tri omitted; tool_reliability_scores will be empty.")
    raw_retries, raw_steps = getattr(args, "retries", None), getattr(args, "steps", None)
    retries = raw_retries if isinstance(raw_retries, int) and not isinstance(raw_retries, bool) else None
    steps = raw_steps if isinstance(raw_steps, int) and not isinstance(raw_steps, bool) else None
    steps, retries, cid = _resolve_cid_telemetry(args, steps, retries)
    if steps is None or retries is None:
        print("[plan_engine] Warning: --steps/--retries unresolved (pass --cid <id> or explicit --steps/--retries for rubric validation).")
    return tri_scores, retries, steps, cid


def cmd_retrospective(root: Path, args: argparse.Namespace) -> int:
    """Record Token Efficiency Grade, TRI, /learn candidates, and refresh LEARNING_SCAFFOLD.md."""
    plan_p = resolve_plan_path(root, args.plan)
    if not plan_p:
        print("[plan_engine] Error: No plan resolved.")
        return 1
    _ws, ps = bootstrap_plan(root, plan_p)
    fdir = get_frontier_dir(root)
    retro_path = fdir / "plans" / ps["slug"] / "retrospectives.json"
    retros = load_json(retro_path, [])
    milestone_idx = args.milestone if args.milestone is not None else ps.get("last_advanced_milestone", ps["active_milestone_index"])
    tri_scores, retries, steps, cid = _resolve_retro_inputs(args)
    grade = _cap_grade_by_rubric((args.grade or "A").upper(), retries, steps)
    tri_scores = _cap_tri_by_grade(tri_scores, grade)
    entry = _build_retrospective_entry(milestone_idx, tri_scores, grade, retries, steps, args)
    _apply_retry_floors(tri_scores, entry, retries, args.hypotheses)
    if cid:
        entry["cid"] = cid
        _enrich_entry_from_audit(entry, cid, getattr(args, "brain_dir", None))
    _upsert_retro(retros, entry)
    save_json(retro_path, retros)
    ws = load_json(fdir / "state.json", {})
    _upsert_retro(ws.setdefault("retrospectives", []), {**entry, "_slug": ps["slug"]}, slug=ps["slug"])
    save_json(fdir / "state.json", ws)
    from plan_sessions import record_session; record_session(root, ps["slug"], milestone_idx, "retrospective", session_id=cid)  # noqa: E702
    from plan_digest import build_workspace_digest, write_learning_scaffold, write_workspace_scaffold
    scaffold_rel = write_learning_scaffold(root, ps["slug"], backfill=False, brain_dir=getattr(args, "brain_dir", None))
    if ps.get("status") == "completed":
        write_workspace_scaffold(root, build_workspace_digest(root, getattr(args, "brain_dir", None), backfill=False))
    _refresh_parent_rollup(root, ps, getattr(args, "brain_dir", None))
    print_retrospective_summary(entry, ps["slug"], scaffold_rel)
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

