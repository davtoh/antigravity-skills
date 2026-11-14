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
        if _worse(str(e.get("token_efficiency_grade", "A")), _grade_cap(steps, retries)):
            issues.append(f"{tag}: grade {e.get('token_efficiency_grade')} exceeds rubric cap {_grade_cap(steps, retries)}")
    return issues


def _unresolved(entries: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Deduplicated /learn candidates and meaningful escalations across entries."""
    learns = list(dict.fromkeys(str(t).strip() for e in entries for t in (e.get("learn_candidates") or []) if str(t).strip()))
    escs = list(dict.fromkeys(str(t).strip() for e in entries for t in (e.get("root_causes_escalated") or []) if str(t).strip().lower() not in _IGNORED_ESCALATIONS))
    return learns, escs


def _unresolved_skill_items(entries: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Deduplicated skill /learn candidates and tooling gaps across entries."""
    skill_learns = list(dict.fromkeys(str(t).strip() for e in entries for t in (e.get("skill_learn_candidates") or []) if str(t).strip()))
    tool_gaps = list(dict.fromkeys(str(t).strip() for e in entries for t in (e.get("tool_gaps") or []) if str(t).strip().lower() not in _IGNORED_ESCALATIONS))
    return skill_learns, tool_gaps


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


def audit_single_cid(cid: str, brain_dir: str | None = None) -> dict[str, Any] | None:
    """Audit one conversation ID via transcript_auditor, or None if unavailable/missing."""
    loaded = _load_auditor(brain_dir)
    row = loaded[0].audit_conversation(loaded[1], cid) if loaded else None
    return None if not row or row.get("missing") else row


def _transcript_rows(cids: list[str] | None, brain_dir: str | None) -> list[dict[str, Any]] | None:
    """Optional telemetry; returns None when system-diagnostics is unavailable (standalone mode)."""
    if not cids:
        return []
    loaded = _load_auditor(brain_dir)
    return [loaded[0].audit_conversation(loaded[1], c) for c in cids] if loaded else None


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
    """Resolve matching conversation ID by explicit cid, learn text, timestamp, or cids position."""
    if e.get("cid"):
        return str(e["cid"])
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


def backfill_retrospectives(root: Path, ps: dict[str, Any], cids: list[str] | None = None, brain_dir: str | None = None) -> int:
    """Match retrospective entries missing telemetry to transcripts and persist updates."""
    loaded = _load_auditor(brain_dir)
    if not loaded:
        return 0
    ta, brain = loaded
    rel = Path(".system_generated") / "logs" / "transcript.jsonl"
    dirs = [brain / c for c in cids] if cids else (list(brain.iterdir()) if brain.is_dir() else [])
    idx_rows = [_index_conversation(d.name, d / rel, ta) for d in dirs if (d / rel).is_file()]
    slugs = [ps["slug"]] + [c.get("slug") for c in (ps.get("child_plans") or {}).values() if c.get("slug")]
    cache, updated, pos = {}, 0, 0
    for slug in slugs:
        rpath = get_frontier_dir(root) / "plans" / slug / "retrospectives.json"
        rows = load_json(rpath, [])
        if not isinstance(rows, list):
            continue
        dirty = False
        for e in rows:
            if not isinstance(e, dict):
                continue
            row = None
            if idx_rows and (e.get("steps") is None or e.get("retries") is None or not e.get("tool_reliability_scores")):
                if cid := _match_entry_cid(e, idx_rows, cids, pos):
                    row = cache.setdefault(cid, ta.audit_conversation(brain, cid))
                pos += 1
            if _apply_backfill_row(e, row):
                dirty, updated = True, updated + 1
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
    rows = _transcript_rows(cids, brain_dir)
    return {
        "slug": ps["slug"], "title": ps["title"], "status": ps["status"],
        "milestones": [{"index": m["index"], "title": m["title"], "status": m["status"], "sha": m.get("commit_sha")} for m in ps["milestones"]],
        "children": [c.get("slug") for c in (ps.get("child_plans") or {}).values()],
        "retro_entries": len(entries), "backfilled_entries": backfilled, "integrity_issues": check_retro_integrity(entries),
        "learn_candidates": learns, "skill_learn_candidates": skill_learns,
        "tool_gaps": tool_gaps, "escalations": escalations,
        "transcripts": rows, "transcripts_unavailable": rows is None,
        "next_step": "Run `diagnose.py scan` on touched packages, or invoke `/learn` to promote project/skill candidates.",
    }


def format_digest(d: dict[str, Any]) -> str:
    """Render the digest as compact dual-axis markdown with user-selectable introspective commands."""
    done = sum(1 for m in d["milestones"] if m["status"] == "completed")
    bf = f" | backfilled: {d['backfilled_entries']}" if d.get("backfilled_entries") else ""
    lines = [f"# Plan Digest: {d['title']} ({d['slug']}) - {d['status']}", f"Milestones: {done}/{len(d['milestones'])} complete | retro entries: {d['retro_entries']}{bf}"]
    lines += [f"- M{m['index']} [{m['status']}] {m['title']}" + (f" ({m['sha']})" if m["sha"] else "") for m in d["milestones"]]
    lines += ["", "## Retrospective integrity"] + ([f"- {i}" for i in d["integrity_issues"]] or ["- OK"])
    lines += ["", "## Unresolved /learn candidates"] + ([f"- {i}" for i in d["learn_candidates"]] or ["- none"])
    lines += ["", "## Skill & Tooling /learn candidates"] + ([f"- {i}" for i in d.get("skill_learn_candidates", [])] or ["- none"])
    lines += ["", "## Tooling & Script Gaps"] + ([f"- {i}" for i in d.get("tool_gaps", [])] or ["- none"])
    lines += ["", "## Escalated root causes (/app-debugger)"] + ([f"- {i}" for i in d["escalations"]] or ["- none"])
    if d["transcripts_unavailable"]:
        lines += ["", "## Transcripts", "- system-diagnostics not found; skipped telemetry."]
    elif d["transcripts"]:
        lines += ["", "## Transcripts"] + [
            f"- {r['cid'][:8]}: " + ("MISSING" if r.get("missing") else f"steps={r['steps']} fails={r['total_failures']} cap={r['suggested_grade_cap']} subagents={len(r['subagents'])}")
            for r in d["transcripts"]]
    lines += [
        "", "## Introspective Commands (User Choice)",
        f"- Digest + Scaffold: `plan_engine.py digest {d['slug']} --backfill --write-scaffold`",
        "- Transcript Audit: `diagnose.py transcript-audit --latest 1`",
        "- Persist Lessons: `/learn`",
    ]
    return "\n".join(lines + ["", f"Next: {d['next_step']}"])


def cmd_digest(root: Path, args: argparse.Namespace) -> int:
    """CLI handler for ``plan_engine.py digest``."""
    digest = build_digest(root, args.plan, getattr(args, "cids", None), getattr(args, "brain_dir", None), getattr(args, "backfill", False))
    if digest is None:
        print("[plan_engine] Error: No plan resolved.")
        return 1
    rendered = json.dumps(digest, indent=2) if getattr(args, "json", False) else format_digest(digest)
    if getattr(args, "write_scaffold", False):
        scaffold_p = get_frontier_dir(root) / "plans" / digest["slug"] / "LEARNING_SCAFFOLD.md"
        scaffold_p.parent.mkdir(parents=True, exist_ok=True)
        scaffold_p.write_bytes((format_digest(digest) + "\n").encode("utf-8"))
        if not getattr(args, "json", False):
            rendered += f"\n\n[plan_engine] Wrote learning scaffold: {scaffold_p.relative_to(root).as_posix()}"
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
