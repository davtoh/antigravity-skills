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


def _cap_section(title: str, items: list[str], limit: int = 12) -> list[str]:
    """Render a capped markdown bullet section so aggregate scaffolds stay under 80 lines."""
    shown = [f"- {i}" for i in items[:limit]] or ["- none"]
    if len(items) > limit:
        shown.append(f"- ... (+{len(items) - limit} more; see per-plan LEARNING_SCAFFOLD.md)")
    return ["", f"## {title}"] + shown


def format_workspace_digest(d: dict[str, Any]) -> str:
    """Render a compact multi-plan workspace digest & LEARN_QUEUE.md (< 80 lines)."""
    lines = [
        f"# Workspace Learning Queue ({len(d['plans'])} plan(s))",
        "| Plan | Status | Milestones | Retro | Issues |",
        "|---|---:|---:|---:|---:|",
    ]
    for p in d["plans"][:15]:
        lines.append(f"| {p['slug']} | {p['status']} | {p['done']}/{p['total']} | {p['retro_entries']} | {p['integrity_issues']} |")
    lines += _cap_section("Unresolved Project /learn Candidates", d.get("learn_candidates", []), 12)
    lines += _cap_section("Skill & Tooling /learn Candidates", d.get("skill_learn_candidates", []), 10)
    lines += _cap_section("Tooling & Script Gaps", d.get("tool_gaps", []), 10)
    lines += _cap_section("Escalated Root Causes (/app-debugger)", d.get("escalations", []), 8)
    lines += ["", "Next: Invoke `/learn` with user choice to promote queue items, or inspect `.frontier/plans/<slug>/LEARNING_SCAFFOLD.md`."]
    return "\n".join(lines[:78])


def _triage_candidates(items: list[str], doc_paths: list[Path]) -> list[str]:
    """Deduplicate near-identical /learn candidates and filter out items already codified in AGENTS.md/SKILL.md."""
    import re
    doc_blob = "\n".join(
        p.read_text(encoding="utf-8", errors="replace").lower()
        for p in doc_paths if p.is_file()
    )
    doc_tokens = set(re.findall(r"[a-z_][a-z0-9_]{3,}", doc_blob))
    seen_norm: set[str] = set()
    kept: list[str] = []
    for raw in items:
        norm = re.sub(r"[^a-z0-9]+", " ", raw.lower()).strip()
        if not norm or norm in seen_norm:
            continue
        seen_norm.add(norm)
        if doc_tokens:
            bt_ids = {t.lower() for t in re.findall(r"`([A-Za-z_][A-Za-z0-9_]{3,})(?:\(\))?`", raw)}
            if len(bt_ids) >= 2 and bt_ids.issubset(doc_tokens):
                continue
        kept.append(raw)
    return kept


def _build_workspace_digest_core(root: Path, brain_dir: str | None, backfill: bool, build_digest_fn: Any) -> dict[str, Any]:
    """Aggregate active and completed plans across the workspace into one /learn queue."""
    from plan_parser import discover_plans, slugify
    from plan_state import load_json
    candidates = list(discover_plans(root))
    seen_paths = {p.resolve() for p in candidates}
    for sp in sorted((get_frontier_dir(root) / "plans").glob("*/state.json")):
        rel_p = load_json(sp, {}).get("plan_path", "")
        if rel_p and (rp := (root / rel_p).resolve()).is_file() and rp not in seen_paths:
            seen_paths.add(rp)
            candidates.append(rp)
    seen_slugs: set[str] = set()
    plans, learns, skill_learns, gaps, escs = [], [], [], [], []
    for p in candidates:
        slug = slugify(p.stem)
        if slug in seen_slugs or not (d := build_digest_fn(root, str(p), None, brain_dir, backfill)):
            continue
        seen_slugs.add(d["slug"])
        done = sum(1 for m in d["milestones"] if m["status"] == "completed")
        plans.append({"slug": d["slug"], "title": d["title"], "status": d["status"], "done": done, "total": len(d["milestones"]), "retro_entries": d["retro_entries"], "integrity_issues": len(d["integrity_issues"])})
        learns += d["learn_candidates"]
        skill_learns += d["skill_learn_candidates"]
        gaps += d["tool_gaps"]
        escs += d["escalations"]
    skill_md = Path(__file__).resolve().parents[1] / "SKILL.md"
    return {
        "plans": plans,
        "learn_candidates": _triage_candidates(learns, [root / "AGENTS.md"]),
        "skill_learn_candidates": _triage_candidates(skill_learns, [skill_md]),
        "tool_gaps": list(dict.fromkeys(gaps)),
        "escalations": list(dict.fromkeys(escs)),
    }


def write_workspace_scaffold(root: Path, digest: dict[str, Any]) -> str:
    """Persist ``.frontier/LEARN_QUEUE.md`` and return its workspace-relative POSIX path."""
    queue_p = get_frontier_dir(root) / "LEARN_QUEUE.md"
    queue_p.write_bytes((format_workspace_digest(digest) + "\n").encode("utf-8"))
    return queue_p.relative_to(root).as_posix()
