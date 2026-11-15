#!/usr/bin/env python3
"""Markdown formatter and LEARNING_SCAFFOLD.md writer for Frontier Architect plan digests."""

from pathlib import Path
from typing import Any

from plan_state import get_frontier_dir


def _build_health_alerts(d: dict[str, Any]) -> list[str]:
    """Collect high-signal transcript and escalation alerts for the digest."""
    rows = [r for r in (d.get("transcripts") or []) if not r.get("missing")]
    alerts = [
        f"Grade cap {r['suggested_grade_cap']} on {r['cid'][:8]} (steps={r['steps']}, fails={r['total_failures']})"
        for r in rows if r.get("suggested_grade_cap") in ("C", "D", "F")
    ]
    alerts += [f"{r['cid'][:8]}: {len(r['parallel_same_file_edits'])} parallel same-file edit(s)" for r in rows if r.get("parallel_same_file_edits")]
    alerts += [
        f"{r['cid'][:8]}: {r.get('reads_while_pending', 0) + r.get('subagent_overlap_reads', 0)} subagent dup reads"
        for r in rows if r.get("reads_while_pending", 0) + r.get("subagent_overlap_reads", 0) > 5
    ]
    return alerts


def format_digest(d: dict[str, Any]) -> str:
    """Render the digest as compact dual-axis markdown with /learn readiness and user-selectable commands."""
    done = sum(1 for m in d["milestones"] if m["status"] == "completed")
    bf = f" | backfilled: {d['backfilled_entries']}" if d.get("backfilled_entries") else ""
    lines = [f"# Plan Digest: {d['title']} ({d['slug']}) - {d['status']}", f"Milestones: {done}/{len(d['milestones'])} complete | retro entries: {d['retro_entries']}{bf}"]
    lines += [f"- M{m['index']} [{m['status']}] {m['title']}" + (f" ({m['sha']})" if m["sha"] else "") for m in d["milestones"]]
    lines += ["", "## Retrospective integrity"] + ([f"- {i}" for i in d["integrity_issues"]] or ["- OK"])
    alerts = _build_health_alerts(d)
    if alerts or d["escalations"]:
        lines += ["", "## Health Alerts"] + [f"- {a}" for a in alerts] + [f"- Escalated: {e}" for e in d["escalations"]]
    lines += ["", "## What Went Well"] + ([f"- {i}" for i in d.get("went_well", [])] or ["- none"])
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
    proj_n, skill_n, gap_n, esc_n = len(d["learn_candidates"]), len(d.get("skill_learn_candidates", [])), len(d.get("tool_gaps", [])), len(d["escalations"])
    lines += [
        "", "## /learn Readiness",
        f"- Candidates: {proj_n} project | {skill_n} skill/tooling | {gap_n} tool gaps | {esc_n} escalations" + (" -> invoke `/learn`." if (proj_n + skill_n + gap_n) else " -> clean (no pending candidates)."),
    ]
    ta_cmd = f"`diagnose.py transcript-audit --cids {' '.join(d['cids'])}` (or `--latest 1`)" if d.get("cids") else "`diagnose.py transcript-audit --latest 1`"
    lines += [
        "", "## Introspective Commands (User Choice)",
        f"- Digest + Scaffold: `plan_engine.py digest {d['slug']} --backfill --write-scaffold`",
        f"- Transcript Audit: {ta_cmd}",
        "- Persist Lessons: `/learn`",
    ]
    return "\n".join(lines + ["", f"Next: {d['next_step']}"])


def _write_scaffold_file(root: Path, digest: dict[str, Any]) -> str:
    """Persist ``LEARNING_SCAFFOLD.md`` under ``.frontier/plans/<slug>/`` and return POSIX path."""
    scaffold_p = get_frontier_dir(root) / "plans" / digest["slug"] / "LEARNING_SCAFFOLD.md"
    scaffold_p.parent.mkdir(parents=True, exist_ok=True)
    scaffold_p.write_bytes((format_digest(digest) + "\n").encode("utf-8"))
    return scaffold_p.relative_to(root).as_posix()


def write_learning_scaffold(root: Path, slug: str, backfill: bool = False, brain_dir: str | None = None) -> str | None:
    """Generate/refresh ``LEARNING_SCAFFOLD.md`` for ``slug``; safe no-op if plan fails to resolve."""
    from plan_digest import build_digest
    try:
        digest = build_digest(root, slug, brain_dir=brain_dir, backfill=backfill)
        return _write_scaffold_file(root, digest) if digest else None
    except Exception:
        return None
