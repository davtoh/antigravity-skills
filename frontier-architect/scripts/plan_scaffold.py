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
        for r in rows if r.get("reads_while_pending", 0) + r.get("subagent_overlap_reads", 0) >= 4
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
    if proj_n + skill_n + gap_n + esc_n > 0:
        lines.append(f"- Ready Prompt: `/learn Review .frontier/plans/{d['slug']}/LEARNING_SCAFFOLD.md and propose rules/skill updates (wait for approval)`")
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
    for p in sorted(d["plans"], key=lambda x: 0 if x["status"] != "completed" else 1)[:15]:
        lines.append(f"| {p['slug']} | {p['status']} | {p['done']}/{p['total']} | {p['retro_entries']} | {p['integrity_issues']} |")
    lines += _cap_section("Unresolved Project /learn Candidates", d.get("learn_candidates", []), 12)
    lines += _cap_section("Skill & Tooling /learn Candidates", d.get("skill_learn_candidates", []), 10)
    lines += _cap_section("Tooling & Script Gaps", d.get("tool_gaps", []), 10)
    lines += _cap_section("Escalated Root Causes (/app-debugger)", d.get("escalations", []), 8)
    lines += ["", "Next: Invoke `/learn` with user choice to promote queue items, or inspect `.frontier/plans/<slug>/LEARNING_SCAFFOLD.md`."]
    return "\n".join(lines[:78])


def _triage_candidates(items: list[str], doc_paths: list[Path]) -> list[str]:
    """Deduplicate near-identical /learn candidates and filter out items already codified on a line of AGENTS.md/SKILL.md."""
    import re
    doc_lines = [
        set(re.findall(r"[a-z_][a-z0-9_]{3,}", ln.lower()))
        for p in doc_paths if p.is_file()
        for ln in p.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()
    ]
    seen_norm: set[str] = set()
    kept: list[str] = []
    for raw in items:
        norm = re.sub(r"[^a-z0-9]+", " ", raw.lower()).strip()
        if not norm or norm in seen_norm:
            continue
        seen_norm.add(norm)
        ids = {t.lower() for t in re.findall(r"`([A-Za-z_][A-Za-z0-9_]{3,})(?:\(\))?`", raw)}
        ids |= {t.lower() for t in re.findall(r"\b([A-Za-z][a-z]+[A-Z][A-Za-z0-9]*|[a-z]+_[a-z0-9_]{3,})\b", raw)}
        if len(ids) >= 2 and any(len(ids & line_toks) >= 2 for line_toks in doc_lines):
            continue
        kept.append(raw)
    return kept


def merge_debug_retro_items(root: Path, learns: list[str], skill_learns: list[str], escalations: list[str]) -> None:
    """Fold DEBUG_RETRO.md lessons and unconfirmed/escalated root causes into digest lists."""
    import re
    for cand in (get_frontier_dir(root) / "DEBUG_RETRO.md", root / ".diagnostics" / "DEBUG_RETRO.md"):
        if not cand.is_file():
            continue
        for line in cand.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if m := re.match(r"^##\s+\[[^\]]+\]\s+\[(UNCONFIRMED|ESCALATED)\]\s+(.+)$", s, re.I):
                _append_unique(escalations, f"Debug retro ({m.group(1).lower()}): {m.group(2).strip()}")
            elif m := re.match(r"^-\s+\*\*Project\s+`/learn`\*\*:\s*(.+)$", s):
                _append_unique(learns, m.group(1).strip())
            elif m := re.match(r"^-\s+\*\*Skill\s+`/learn`\*\*:\s*(.+)$", s):
                _append_unique(skill_learns, m.group(1).strip())


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
    plans, active_digests, completed_digests = [], [], []
    for p in candidates:
        slug = slugify(p.stem)
        if slug in seen_slugs or not (d := build_digest_fn(root, str(p), None, brain_dir, backfill)):
            continue
        seen_slugs.add(d["slug"])
        done = sum(1 for m in d["milestones"] if m["status"] == "completed")
        plans.append({"slug": d["slug"], "title": d["title"], "status": d["status"], "done": done, "total": len(d["milestones"]), "retro_entries": d["retro_entries"], "integrity_issues": len(d["integrity_issues"])})
        (completed_digests if d["status"] == "completed" else active_digests).append(d)
    # Keep active plans + up to 5 recent completed plans in LEARN_QUEUE.md so historical backlogs don't drown active items.
    queued = active_digests + completed_digests[:5]
    learns = [item for d in queued for item in d["learn_candidates"]]
    skill_learns = [
        item for d in queued for item in d["skill_learn_candidates"]
        if not item.startswith("Transcript audit: repeated file reads")
    ]
    gaps = [item for d in queued for item in d["tool_gaps"]]
    escs = [item for d in queued for item in d["escalations"]]
    merge_debug_retro_items(root, learns, skill_learns, escs)
    skill_md = Path(__file__).resolve().parents[1] / "SKILL.md"
    return {
        "plans": plans,
        "learn_candidates": _triage_candidates(learns, [root / "AGENTS.md"]),
        "skill_learn_candidates": _triage_candidates(skill_learns, [skill_md]),
        "tool_gaps": list(dict.fromkeys(gaps)),
        "escalations": list(dict.fromkeys(escs)),
    }


def refresh_stale_retro_entry(
    entry: dict[str, Any], row: dict[str, Any] | None, cap_fn: Any, worse_fn: Any
) -> bool:
    """Refresh stale mid-session steps/retries/grade on the latest retro entry for a CID."""
    if not row or row.get("missing") or entry.get("child_slug"):
        return False
    before = json_snap(entry)
    if (row.get("steps") or 0) > (entry.get("steps") or 0):
        entry["steps"] = row["steps"]
    if (row.get("total_failures") or 0) > (entry.get("retries") or 0):
        entry["retries"] = row["total_failures"]
    cap = cap_fn(entry.get("steps"), entry.get("retries"))
    if worse_fn(str(entry.get("token_efficiency_grade", "A")), cap):
        entry["token_efficiency_grade"] = cap
        tri = entry.get("tool_reliability_scores")
        lim = {"B": 4, "C": 3, "D": 2, "F": 1}.get(cap)
        if isinstance(tri, dict) and lim:
            for k in ("token_efficiency", "hypothesis_accuracy"):
                if isinstance(tri.get(k), int):
                    tri[k] = min(tri[k], lim)
            dims = [tri[k] for k in ("token_efficiency", "hypothesis_accuracy", "tool_reliability", "architectural_defense") if isinstance(tri.get(k), int)]
            if len(dims) == 4:
                avg = sum(dims) / 4.0
                tri["overall"] = int(avg) if avg.is_integer() else round(avg, 2)
    return json_snap(entry) != before


def json_snap(obj: Any) -> str:
    """Stable serialized snapshot for mutation checks."""
    import json
    return json.dumps(obj, sort_keys=True)


def _append_unique(items: list[str], msg: str) -> None:
    """Append ``msg`` unless already present."""
    if msg and msg not in items:
        items.append(msg)


def promote_transcript_findings(
    rows: list[dict[str, Any]] | None, skill_learns: list[str], escalations: list[str]
) -> None:
    """Surface transcript-audit anomalies and user corrections into digest /learn lists."""
    for r in rows or ():
        if not isinstance(r, dict) or r.get("missing"):
            continue
        cid8 = str(r.get("cid") or "")[:8]
        if p_edits := r.get("parallel_same_file_edits") or []:
            files = list(dict.fromkeys(Path(str(it.get("path") or it.get("file") or "?")).name for it in p_edits if isinstance(it, dict)))
            detail = f" ({', '.join(files[:4])})" if files else ""
            _append_unique(skill_learns, f"Transcript audit: {len(p_edits)} parallel same-file edit(s){detail}")
        if reps := [f"{Path(str(k)).name} ({v}x)" for k, v in (r.get("repeated_reads") or {}).items() if int(v) >= 3]:
            _append_unique(skill_learns, f"Transcript audit: repeated file reads (>=3x): {', '.join(reps[:4])}")
        if (rf := int((r.get("failures") or {}).get("read_fail", 0))) >= 2:
            _append_unique(skill_learns, f"Transcript audit: {cid8} had {rf} read_fail path-guess errors (use git grep/surface first)")
        if (ca := int(r.get("changelog_adds", 0))) >= 2:
            _append_unique(skill_learns, f"Transcript audit: {cid8} ran {ca} changelog add calls in one session")
        if (fb := int(r.get("cdp_live_fallbacks", 0))) >= 1:
            _append_unique(skill_learns, f"Transcript audit: {cid8} had {fb} CDP --live->headless fallback(s)")
        if (lf := int(r.get("cdp_live_failures", 0))) >= 1:
            _append_unique(skill_learns, f"Transcript audit: {cid8} had {lf} CDP --live handshake failure(s) (Chrome Allow prompt)")
        if (pm := int(r.get("plan_mode_calls", 0))) >= 1:
            _append_unique(skill_learns, f"Transcript audit: {cid8} called enter/exit_plan_mode ({pm}x)")
        for corr in r.get("user_corrections") or ():
            _append_unique(escalations, f"User correction ({cid8}): {corr}")
        for redir in r.get("workflow_redirects") or ():
            _append_unique(escalations, f"Workflow redirect ({cid8}): {redir}")


def write_workspace_scaffold(root: Path, digest: dict[str, Any]) -> str:
    """Persist ``.frontier/LEARN_QUEUE.md`` and return its workspace-relative POSIX path."""
    queue_p = get_frontier_dir(root) / "LEARN_QUEUE.md"
    queue_p.write_bytes((format_workspace_digest(digest) + "\n").encode("utf-8"))
    return queue_p.relative_to(root).as_posix()
