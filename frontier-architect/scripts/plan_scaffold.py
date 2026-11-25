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
        "", "## Learning Scaffold Highlights",
        f"- Health: {len(alerts)} alert(s), {esc_n} escalation(s)" + (f" ({alerts[0]})" if alerts else ""),
        f"- Top Project Lesson: {d['learn_candidates'][0]}" if d["learn_candidates"] else "- Top Project Lesson: none",
        f"- Top Skill/Tooling Lesson: {d['skill_learn_candidates'][0]}" if d.get("skill_learn_candidates") else "- Top Skill/Tooling Lesson: none",
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
    stop = {"with", "from", "that", "this", "when", "into", "only", "must", "never", "always", "before", "after", "instead", "rather", "than", "also", "keep", "stay", "under", "files"}
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
        sig = {t for t in re.findall(r"[a-z_][a-z0-9_]{3,}", raw.lower()) if t not in stop}
        if (len(ids) >= 2 and any(len(ids & lt) >= 2 for lt in doc_lines)) or (len(sig) >= 4 and any(len(sig & lt) * 5 >= len(sig) * 3 for lt in doc_lines)):
            continue
        kept.append(raw)
    return kept


def triage_plan_candidates(root: Path, learns: list[str], skill_learns: list[str]) -> tuple[list[str], list[str]]:
    """Filter per-plan /learn candidates against AGENTS.md/.agents/rules/SKILL.md and drop noisy repeated-read warnings."""
    skill_md = Path(__file__).resolve().parents[1] / "SKILL.md"
    rules_dir = root / ".agents" / "rules"
    proj_docs = [root / "AGENTS.md", *(sorted(rules_dir.glob("*.md")) if rules_dir.is_dir() else ())]
    cleaned_skill = [x for x in skill_learns if not x.startswith("Transcript audit: repeated file reads")]
    return _triage_candidates(learns, proj_docs), _triage_candidates(cleaned_skill, [skill_md])


def record_followup_cid(root: Path, slug: str, cid: str | None, brain_dir: str | None = None) -> bool:
    """Persist a follow-up /app-debugger CID on state.json so future digests keep it in ## Transcripts."""
    if not cid or not slug:
        return False
    from plan_digest import _load_auditor, _resolve_one_cid
    from plan_state import load_json, save_json
    st_path = get_frontier_dir(root) / "plans" / slug / "state.json"
    if not st_path.is_file() or not isinstance(ps := load_json(st_path, {}), dict):
        return False
    loaded = _load_auditor(brain_dir)
    full_cid = _resolve_one_cid(loaded[1], cid.strip()) if loaded else cid.strip()
    fcids = [str(c) for c in (ps.get("followup_cids") or []) if c]
    if any(c.lower().startswith(full_cid.lower()) or full_cid.lower().startswith(c.lower()) for c in fcids):
        return False
    ps["followup_cids"] = [*fcids, full_cid]
    save_json(st_path, ps)
    return True


def _cid_matches(entry_cid: str, cids: list[str] | None) -> bool:
    """Return True if entry_cid is unscoped (empty) or matches any cid in cids."""
    if cids is None or not entry_cid:
        return True
    return any(c.startswith(entry_cid) or entry_cid.startswith(c) for c in cids if c)


def _collect_verified_retros(blocks: list[str]) -> tuple[set[str], set[str]]:
    """Return (verified_cid_prefixes, verified_titles) across DEBUG_RETRO blocks."""
    import re
    v_cids, v_titles = set(), set()
    for blk in blocks:
        if vm := re.search(r"^##\s+\[[^\]]+\]\s+\[VERIFIED\]\s+(.+)$", blk, re.M | re.I):
            v_titles.add(re.sub(r"\s+", " ", vm.group(1).strip().lower()))
            if mc := re.search(r"-\s+\*\*Telemetry\*\*:.*\bcid=([a-zA-Z0-9_-]+)", blk):
                v_cids.add(mc.group(1)[:8].lower())
    return v_cids, v_titles


def merge_debug_retro_items(
    root: Path, learns: list[str], skill_learns: list[str], escalations: list[str], cids: list[str] | None = None
) -> None:
    """Fold DEBUG_RETRO.md lessons and unconfirmed/escalated root causes into digest lists."""
    import re
    for cand in (get_frontier_dir(root) / "DEBUG_RETRO.md", root / ".diagnostics" / "DEBUG_RETRO.md"):
        if not cand.is_file():
            continue
        blocks = re.split(r"(?=^##\s+\[)", cand.read_text(encoding="utf-8", errors="replace"), flags=re.M)
        v_cids, v_titles = _collect_verified_retros(blocks)
        for blk in blocks:
            m_cid = re.search(r"-\s+\*\*Telemetry\*\*:.*\bcid=([a-zA-Z0-9_-]+)", blk)
            ecid = m_cid.group(1) if m_cid else ""
            if not _cid_matches(ecid, cids):
                continue
            if ecid:
                escalations[:] = [x for x in escalations if not x.startswith(f"Unescalated thrash ({ecid[:8]}):")]
            for line in blk.splitlines():
                s = line.strip()
                if m := re.match(r"^##\s+\[[^\]]+\]\s+\[(UNCONFIRMED|ESCALATED)\]\s+(.+)$", s, re.I):
                    norm_t = re.sub(r"\s+", " ", m.group(2).strip().lower())
                    if (not ecid or ecid[:8].lower() not in v_cids) and norm_t not in v_titles:
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
    plans, active_digests, completed_digests = [list[dict[str, Any]]() for _ in range(3)]
    for p in candidates:
        slug = slugify(p.stem)
        if slug in seen_slugs or not (d := build_digest_fn(root, str(p), None, brain_dir, backfill)):
            continue
        seen_slugs.add(d["slug"])
        done = sum(1 for m in d["milestones"] if m["status"] == "completed")
        plans.append({"slug": d["slug"], "title": d["title"], "status": d["status"], "done": done, "total": len(d["milestones"]), "retro_entries": d["retro_entries"], "integrity_issues": len(d["integrity_issues"])})
        (completed_digests if d["status"] == "completed" else active_digests).append(d)
    completed_digests.sort(key=lambda d: str(d.get("latest_retro_at") or ""), reverse=True)
    queued = active_digests + completed_digests[:5]
    learns = [item for d in queued for item in d["learn_candidates"]]
    skill_learns = [
        item for d in queued for item in d["skill_learn_candidates"]
        if not item.startswith("Transcript audit: repeated file reads") and "parallel same-file edit(s)" not in item
    ]
    gaps = [item for d in queued for item in d["tool_gaps"]]
    escs = [item for d in queued for item in d["escalations"]]
    merge_debug_retro_items(root, learns, skill_learns, escs)
    learns, skill_learns = triage_plan_candidates(root, learns, skill_learns)
    return {
        "plans": plans, "learn_candidates": learns, "skill_learn_candidates": skill_learns,
        "tool_gaps": list(dict.fromkeys(gaps)), "escalations": list(dict.fromkeys(escs)),
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
        if reps := [f"{Path(str(k)).name} ({v}x)" for k, v in (r.get("repeated_reads") or {}).items() if int(v) >= 3]:
            _append_unique(skill_learns, f"Transcript audit: repeated file reads (>=3x): {', '.join(reps[:4])}")
        if (rf := int((r.get("failures") or {}).get("read_fail", 0))) >= 2:
            _append_unique(skill_learns, f"Transcript audit: {cid8} had {rf} read_fail path-guess errors (use git grep/surface first)")
        if (fb := int(r.get("cdp_live_fallbacks", 0))) >= 1:
            _append_unique(skill_learns, f"Transcript audit: {cid8} had {fb} CDP --live->headless fallback(s)")
        if (lf := int(r.get("cdp_live_failures", 0))) >= 1:
            _append_unique(skill_learns, f"Transcript audit: {cid8} had {lf} CDP --live handshake failure(s) (Chrome Allow prompt)")
        cli_errs = max(int(r.get("tooling_cli_fails") or 0), sum(1 for s in (r.get("failure_samples") or []) if "plan_engine.py" in s and "error:" in s))
        raw_cmd = (r.get("failures") or {}).get("cmd_fail")
        samples = r.get("failure_samples") or []
        non_tdd_fails = sum(1 for s in samples if "unittest" not in s and "AssertionError" not in s and "plan_engine.py" not in s)
        cmd_fails = (int(raw_cmd) if raw_cmd is not None else int(r.get("total_failures") or 0)) - cli_errs
        if cmd_fails >= 4 and (not samples or non_tdd_fails >= 2) and not r.get("has_debug_retro"):
            _append_unique(escalations, f"Unescalated thrash ({cid8}): {r['total_failures']} failures without /app-debugger or debug-retro")
        for corr in r.get("user_corrections") or ():
            _append_unique(escalations, f"User correction ({cid8}): {corr}")
        for redir in r.get("workflow_redirects") or ():
            _append_unique(escalations, f"Workflow redirect ({cid8}): {redir}")


def write_workspace_scaffold(root: Path, digest: dict[str, Any]) -> str:
    """Persist ``.frontier/LEARN_QUEUE.md`` and return its workspace-relative POSIX path."""
    queue_p = get_frontier_dir(root) / "LEARN_QUEUE.md"
    queue_p.write_bytes((format_workspace_digest(digest) + "\n").encode("utf-8"))
    return queue_p.relative_to(root).as_posix()
