#!/usr/bin/env python3
"""End-of-plan retrospective digest: one deterministic command instead of a manual post-mortem.

Merges the plan ledger, ``retrospectives.json`` integrity checks, unresolved /learn candidates and
escalations, and (optionally) transcript telemetry from ``system-diagnostics`` into a compact report.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import argparse
import json
import sys

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from plan_state import bootstrap_plan, get_frontier_dir, load_json, resolve_plan_path, save_json

_GRADE_ORDER = "ABCDF"
_IGNORED_ESCALATIONS = {"", "none", "n/a", "null"}


def _grade_cap(steps: int | None, retries: int | None) -> str:
    """Best grade the SKILL.md rubric allows for the observed steps/retries."""
    cap = "A"
    if (steps is not None and steps > 100) or (retries is not None and retries > 3):
        cap = "C"
    elif (steps is not None and steps > 60) or (retries is not None and retries >= 2):
        cap = "B"
    return cap


def _worse(grade: str, cap: str) -> bool:
    """True when ``grade`` is better than the rubric ``cap`` (i.e. inflated)."""
    base = (grade or "A").strip().upper()[:1]
    return base in _GRADE_ORDER and _GRADE_ORDER.index(base) < _GRADE_ORDER.index(cap)


def check_retro_integrity(entries: list[dict[str, Any]]) -> list[str]:
    """Return human-readable integrity warnings for retrospective entries."""
    issues: list[str] = []
    for e in entries:
        tag = (f"{e['_plan']}:" if e.get("_plan") else "") + f"M{e.get('milestone_index')}"
        steps, retries = e.get("steps"), e.get("retries")
        if steps is None:
            issues.append(f"{tag}: --steps missing (grade cannot be validated; pass `transcript-audit` step count)")
        if retries is None:
            issues.append(f"{tag}: --retries missing")
        if not e.get("tool_reliability_scores"):
            issues.append(f"{tag}: empty tool_reliability_scores (unparsed --tri)")
        if not e.get("child_slug") and _worse(str(e.get("token_efficiency_grade", "A")), _grade_cap(steps, retries)):
            issues.append(f"{tag}: grade {e.get('token_efficiency_grade')} exceeds rubric cap {_grade_cap(steps, retries)}")
    return issues


def _clean_items(entries: list[dict[str, Any]], key: str) -> list[str]:
    """Return deduplicated non-placeholder strings for ``key`` across retrospective entries."""
    return list(dict.fromkeys(str(t).strip() for e in entries for t in (e.get(key) or []) if str(t).strip().lower() not in _IGNORED_ESCALATIONS))


def _unresolved(entries: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Deduplicated /learn candidates and meaningful escalations across entries."""
    return _clean_items(entries, "learn_candidates"), _clean_items(entries, "root_causes_escalated")


def _unresolved_skill_items(entries: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Deduplicated skill /learn candidates and tooling gaps across entries."""
    return _clean_items(entries, "skill_learn_candidates"), _clean_items(entries, "tool_gaps")


def _load_auditor(brain_dir: str | None = None) -> tuple[Any, Path] | None:
    """Load transcript_auditor and resolved brain dir, else None in standalone mode."""
    sibling = _SCRIPTS_DIR.parent.parent / "system-diagnostics" / "scripts"
    for candidate in (_SCRIPTS_DIR, sibling):
        if (candidate / "transcript_auditor.py").is_file():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            import transcript_auditor
            return transcript_auditor, (Path(brain_dir) if brain_dir else transcript_auditor.default_brain_dir())
    return None


def _resolve_one_cid(brain: Path, cid: str) -> str:
    """Resolve an exact or unique 6+ char conversation ID prefix in ``brain``."""
    rel = Path(".system_generated") / "logs" / "transcript.jsonl"
    if (brain / cid / rel).is_file() or len(cid) < 6 or not brain.is_dir():
        return cid
    low = cid.lower()
    hits = [d.name for d in brain.iterdir() if d.is_dir() and d.name.lower().startswith(low) and (d / rel).is_file()]
    return hits[0] if len(hits) == 1 else cid


def audit_single_cid(cid: str, brain_dir: str | None = None) -> dict[str, Any] | None:
    """Audit one conversation ID (exact or unique prefix), or None if unavailable/missing."""
    loaded = _load_auditor(brain_dir)
    if not loaded:
        return None
    row = loaded[0].audit_conversation(loaded[1], _resolve_one_cid(loaded[1], cid))
    return None if not row or row.get("missing") else row


def _dedupe_cids(cids: list[str], brain: Path | None = None) -> list[str]:
    """Resolve and deduplicate CIDs case-insensitively, dropping >=6-char prefixes of longer CIDs."""
    res = [_resolve_one_cid(brain, str(c).strip()) if brain else str(c).strip() for c in cids if c and str(c).strip()]
    kept = [c for c in res if not any(len(c) >= 6 and o.lower() != c.lower() and o.lower().startswith(c.lower()) for o in res)]
    seen: set[str] = set()
    return [c for c in kept if not (c.lower() in seen or seen.add(c.lower()))]


def _transcript_rows(cids: list[str] | None, brain_dir: str | None) -> list[dict[str, Any]] | None:
    """Optional telemetry; returns None when system-diagnostics is unavailable (standalone mode)."""
    if not cids:
        return []
    loaded = _load_auditor(brain_dir)
    if not loaded:
        return None
    return [loaded[0].audit_conversation(loaded[1], c) for c in _dedupe_cids(cids, loaded[1])]


def _parse_iso(ts: str) -> datetime | None:
    """Parse an ISO-8601 timestamp into a timezone-aware datetime, else None."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None
        return dt.replace(tzinfo=timezone.utc) if dt and not dt.tzinfo else dt
    except ValueError:
        return None


def _index_conversation(cid: str, log_path: Path, ta: Any) -> dict[str, Any]:
    """Extract timestamp bounds and command text from one transcript for backfill matching."""
    first_dt = last_dt = None
    retro_cmds, all_cmds = [], []
    for step in ta._iter_steps(log_path):
        if dt := _parse_iso(str(step.get("created_at") or "")):
            first_dt, last_dt = (first_dt or dt), dt
        for tc in (step.get("tool_calls") or []) if step.get("type") == "PLANNER_RESPONSE" else ():
            if tc.get("name") == "run_command":
                txt = str(tc.get("args") or "")
                all_cmds.append(txt)
                if "retrospective" in txt:
                    retro_cmds.append(txt)
    return {"cid": cid, "first": first_dt, "last": last_dt, "retro": "\n".join(retro_cmds), "cmds": "\n".join(all_cmds)}


def _match_entry_cid(e: dict[str, Any], idx_rows: list[dict[str, Any]], cids: list[str] | None, pos: int) -> str | None:
    """Resolve matching conversation ID by explicit/prefix cid, learn text, timestamp, or position."""
    if raw_cid := str(e.get("cid") or "").strip():
        low = raw_cid.lower()
        hits = [r["cid"] for r in idx_rows if r["cid"].lower().startswith(low)]
        return hits[0] if len(hits) == 1 else raw_cid
    lc = str((e.get("learn_candidates") or [""])[0]).strip()[:40]
    for field in ("retro", "cmds") if len(lc) >= 8 else ():
        if hits := [r["cid"] for r in idx_rows if lc in r[field]]:
            return hits[0]
    if dt := _parse_iso(str(e.get("timestamp") or "")):
        scored = [
            (0.0 if r["first"] <= dt <= r["last"] else min(abs((dt - r["first"]).total_seconds()), abs((dt - r["last"]).total_seconds())), r["cid"])
            for r in idx_rows if r["first"] and r["last"]
        ]
        if valid := [s for s in scored if s[0] <= 600.0]:
            return min(valid)[1]
    return cids[pos] if cids and pos < len(cids) else None


def _apply_backfill_row(e: dict[str, Any], row: dict[str, Any] | None) -> bool:
    """Populate missing telemetry fields from an audited transcript row and cap inflated grades."""
    before = dict(e)
    if row and not row.get("missing"):
        e["cid"] = row["cid"]
        if e.get("steps") is None:
            e["steps"] = row["steps"]
        if e.get("retries") is None:
            e["retries"] = row["total_failures"]
        if not e.get("tool_reliability_scores"):
            e["tool_reliability_scores"] = {"overall": 5 if row["total_failures"] == 0 else 4}
    cap = _grade_cap(e.get("steps"), e.get("retries"))
    if _worse(str(e.get("token_efficiency_grade", "A")), cap):
        e["token_efficiency_grade"] = cap
    return e != before


def _dedupe_retro_rows(rows: list[Any]) -> tuple[list[Any], int]:
    """Drop incomplete or duplicate-CID retrospective entries when a complete entry exists."""
    complete_ms = {e.get("milestone_index") for e in rows if isinstance(e, dict) and e.get("steps") is not None}
    kept_rev: list[Any] = []
    seen_pairs: set[tuple[Any, str]] = set()
    removed = 0
    for e in reversed(rows):
        if not isinstance(e, dict):
            kept_rev.append(e)
            continue
        m_idx = e.get("milestone_index")
        cid = str(e.get("cid") or "").lower()
        if e.get("steps") is None and m_idx in complete_ms:
            removed += 1
            continue
        if cid and (m_idx, cid) in seen_pairs:
            removed += 1
            continue
        if cid:
            seen_pairs.add((m_idx, cid))
        kept_rev.append(e)
    kept_rev.reverse()
    return kept_rev, removed


def backfill_retrospectives(root: Path, ps: dict[str, Any], cids: list[str] | None = None, brain_dir: str | None = None) -> int:
    """Match retrospective entries missing telemetry to transcripts and persist updates."""
    loaded = _load_auditor(brain_dir)
    if not loaded:
        return 0
    ta, brain = loaded
    rel = Path(".system_generated") / "logs" / "transcript.jsonl"
    idx_rows: list[dict[str, Any]] | None = None
    slugs = [ps["slug"]] + [c.get("slug") for c in (ps.get("child_plans") or {}).values() if c.get("slug")]
    cache, updated, pos = {}, 0, 0
    for slug in slugs:
        rpath = get_frontier_dir(root) / "plans" / slug / "retrospectives.json"
        if not isinstance(rows := load_json(rpath, []), list):
            continue
        dirty = False
        for e in (r for r in rows if isinstance(r, dict)):
            row = None
            if e.get("steps") is None or e.get("retries") is None or not e.get("tool_reliability_scores"):
                if idx_rows is None:
                    dirs = [brain / _resolve_one_cid(brain, c) for c in cids] if cids else (list(brain.iterdir()) if brain.is_dir() else [])
                    idx_rows = [_index_conversation(d.name, d / rel, ta) for d in dirs if (d / rel).is_file()]
                if idx_rows:
                    if cid := _match_entry_cid(e, idx_rows, cids, pos):
                        row = cache.setdefault(cid, ta.audit_conversation(brain, cid))
                    pos += 1
            if _apply_backfill_row(e, row):
                dirty, updated = True, updated + 1
        rows, dropped = _dedupe_retro_rows(rows)
        if dropped:
            dirty, updated = True, updated + dropped
        if dirty:
            save_json(rpath, rows)
    return updated


def _load_entries(root: Path, ps: dict[str, Any]) -> list[dict[str, Any]]:
    """Retrospective entries for the plan plus its child plans (tagged with ``_plan``)."""
    slugs = [ps["slug"]] + [c.get("slug") for c in (ps.get("child_plans") or {}).values() if c.get("slug")]
    entries: list[dict[str, Any]] = []
    for slug in slugs:
        rows = load_json(get_frontier_dir(root) / "plans" / slug / "retrospectives.json", [])
        entries += [{**e, "_plan": slug} for e in rows if isinstance(e, dict)] if isinstance(rows, list) else []
    return entries


def build_digest(root: Path, plan: str | None, cids: list[str] | None = None, brain_dir: str | None = None, backfill: bool = False) -> dict[str, Any] | None:
    """Assemble the digest dict, or None when the plan cannot be resolved."""
    plan_p = resolve_plan_path(root, plan)
    if not plan_p:
        return None
    _ws, ps = bootstrap_plan(root, plan_p)
    backfilled = backfill_retrospectives(root, ps, cids, brain_dir) if backfill else 0
    entries = _load_entries(root, ps)
    learns, escalations = _unresolved(entries)
    skill_learns, tool_gaps = _unresolved_skill_items(entries)
    went_well = _clean_items(entries, "went_well")
    entry_cids = _dedupe_cids([str(e["cid"]) for e in entries if e.get("cid")])
    all_recorded = bool(entries) and all(e.get("cid") or e.get("child_slug") for e in entries)
    extra_cids = [] if (ps["status"] == "completed" and all_recorded) else (cids or [])
    rows = _transcript_rows(_dedupe_cids([*entry_cids, *extra_cids]), brain_dir)
    return {
        "slug": ps["slug"], "title": ps["title"], "status": ps["status"],
        "milestones": [{"index": m["index"], "title": m["title"], "status": m["status"], "sha": m.get("commit_sha")} for m in ps["milestones"]],
        "children": [c.get("slug") for c in (ps.get("child_plans") or {}).values()],
        "retro_entries": len(entries), "backfilled_entries": backfilled, "integrity_issues": check_retro_integrity(entries),
        "went_well": went_well, "learn_candidates": learns, "skill_learn_candidates": skill_learns,
        "tool_gaps": tool_gaps, "escalations": escalations,
        "cids": entry_cids, "transcripts": rows, "transcripts_unavailable": rows is None,
        "next_step": "Run `diagnose.py scan` on touched packages, or invoke `/learn` to promote project/skill candidates.",
    }


from plan_scaffold import _write_scaffold_file, format_digest, write_learning_scaffold


def cmd_digest(root: Path, args: argparse.Namespace) -> int:
    """CLI handler for ``plan_engine.py digest``."""
    digest = build_digest(root, args.plan, getattr(args, "cids", None), getattr(args, "brain_dir", None), getattr(args, "backfill", False))
    if digest is None:
        print("[plan_engine] Error: No plan resolved.")
        return 1
    rendered = json.dumps(digest, indent=2) if getattr(args, "json", False) else format_digest(digest)
    if getattr(args, "write_scaffold", False):
        rel_path = _write_scaffold_file(root, digest)
        if not getattr(args, "json", False):
            rendered += f"\n\n[plan_engine] Wrote learning scaffold: {rel_path}"
    print(rendered)
    return 0


def register_digest_parser(sub: Any, plan_parent: argparse.ArgumentParser) -> None:
    """Register the ``digest`` subcommand on plan_engine's subparsers."""
    p = sub.add_parser("digest", parents=[plan_parent], help="End-of-plan retrospective digest (integrity, /learn candidates, telemetry)")
    p.add_argument("--cids", nargs="+", default=None, help="Conversation ids to include via transcript-audit")
    p.add_argument("--brain-dir", default=None, help="Override brain dir for transcript telemetry")
    p.add_argument("--backfill", action="store_true", help="Backfill missing --steps/--retries and re-cap grades in retrospectives.json from transcripts")
    p.add_argument("--write-scaffold", action="store_true", help="Write .frontier/plans/<slug>/LEARNING_SCAFFOLD.md")
    p.add_argument("--json", action="store_true", help="Output JSON")
