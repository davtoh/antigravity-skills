#!/usr/bin/env python3
"""End-of-plan retrospective digest: one deterministic command instead of a manual post-mortem.

Merges the plan ledger, ``retrospectives.json`` integrity checks, unresolved /learn candidates and
escalations, and (optionally) transcript telemetry from ``system-diagnostics`` into a compact report.
"""

from pathlib import Path
from typing import Any
import argparse
import json
import sys

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from plan_state import bootstrap_plan, get_frontier_dir, load_json, resolve_plan_path

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
    learns: list[str] = []
    escalations: list[str] = []
    for e in entries:
        for text in e.get("learn_candidates") or []:
            if str(text).strip() and text not in learns:
                learns.append(str(text).strip())
        for text in e.get("root_causes_escalated") or []:
            if str(text).strip().lower() not in _IGNORED_ESCALATIONS and text not in escalations:
                escalations.append(str(text).strip())
    return learns, escalations


def _transcript_rows(cids: list[str] | None, brain_dir: str | None) -> list[dict[str, Any]] | None:
    """Optional telemetry; returns None when system-diagnostics is unavailable (standalone mode)."""
    if not cids:
        return []
    sibling = _SCRIPTS_DIR.parent.parent / "system-diagnostics" / "scripts"
    for candidate in (_SCRIPTS_DIR, sibling):
        if (candidate / "transcript_auditor.py").is_file():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            import transcript_auditor
            brain = Path(brain_dir) if brain_dir else transcript_auditor.default_brain_dir()
            return [transcript_auditor.audit_conversation(brain, c) for c in cids]
    return None


def _load_entries(root: Path, ps: dict[str, Any]) -> list[dict[str, Any]]:
    """Retrospective entries for the plan plus its child plans (tagged with ``_plan``)."""
    slugs = [ps["slug"]] + [c.get("slug") for c in (ps.get("child_plans") or {}).values() if c.get("slug")]
    entries: list[dict[str, Any]] = []
    for slug in slugs:
        rows = load_json(get_frontier_dir(root) / "plans" / slug / "retrospectives.json", [])
        entries += [{**e, "_plan": slug} for e in rows if isinstance(e, dict)] if isinstance(rows, list) else []
    return entries


def build_digest(root: Path, plan: str | None, cids: list[str] | None = None, brain_dir: str | None = None) -> dict[str, Any] | None:
    """Assemble the digest dict, or None when the plan cannot be resolved."""
    plan_p = resolve_plan_path(root, plan)
    if not plan_p:
        return None
    _ws, ps = bootstrap_plan(root, plan_p)
    entries = _load_entries(root, ps)
    learns, escalations = _unresolved(entries)
    rows = _transcript_rows(cids, brain_dir)
    return {
        "slug": ps["slug"], "title": ps["title"], "status": ps["status"],
        "milestones": [{"index": m["index"], "title": m["title"], "status": m["status"], "sha": m.get("commit_sha")} for m in ps["milestones"]],
        "children": [c.get("slug") for c in (ps.get("child_plans") or {}).values()],
        "retro_entries": len(entries), "integrity_issues": check_retro_integrity(entries),
        "learn_candidates": learns, "escalations": escalations,
        "transcripts": rows, "transcripts_unavailable": rows is None,
        "next_step": "Run `diagnose.py scan` on touched packages, then propose /learn for the items above.",
    }


def format_digest(d: dict[str, Any]) -> str:
    """Render the digest as compact markdown."""
    done = sum(1 for m in d["milestones"] if m["status"] == "completed")
    lines = [f"# Plan Digest: {d['title']} ({d['slug']}) - {d['status']}", f"Milestones: {done}/{len(d['milestones'])} complete | retro entries: {d['retro_entries']}"]
    for m in d["milestones"]:
        lines.append(f"- M{m['index']} [{m['status']}] {m['title']}" + (f" ({m['sha']})" if m["sha"] else ""))
    lines += ["", "## Retrospective integrity"] + ([f"- {i}" for i in d["integrity_issues"]] or ["- OK"])
    lines += ["", "## Unresolved /learn candidates"] + ([f"- {i}" for i in d["learn_candidates"]] or ["- none"])
    lines += ["", "## Escalated root causes (/app-debugger)"] + ([f"- {i}" for i in d["escalations"]] or ["- none"])
    if d["transcripts_unavailable"]:
        lines += ["", "## Transcripts", "- system-diagnostics not found; skipped telemetry."]
    elif d["transcripts"]:
        lines += ["", "## Transcripts"] + [
            f"- {r['cid'][:8]}: " + ("MISSING" if r.get("missing") else f"steps={r['steps']} fails={r['total_failures']} cap={r['suggested_grade_cap']} subagents={len(r['subagents'])}")
            for r in d["transcripts"]]
    return "\n".join(lines + ["", f"Next: {d['next_step']}"])


def cmd_digest(root: Path, args: argparse.Namespace) -> int:
    """CLI handler for ``plan_engine.py digest``."""
    digest = build_digest(root, args.plan, getattr(args, "cids", None), getattr(args, "brain_dir", None))
    if digest is None:
        print("[plan_engine] Error: No plan resolved.")
        return 1
    print(json.dumps(digest, indent=2) if getattr(args, "json", False) else format_digest(digest))
    return 0


def register_digest_parser(sub: Any, plan_parent: argparse.ArgumentParser) -> None:
    """Register the ``digest`` subcommand on plan_engine's subparsers."""
    p = sub.add_parser("digest", parents=[plan_parent], help="End-of-plan retrospective digest (integrity, /learn candidates, telemetry)")
    p.add_argument("--cids", nargs="+", default=None, help="Conversation ids to include via transcript-audit")
    p.add_argument("--brain-dir", default=None, help="Override brain dir for transcript telemetry")
    p.add_argument("--json", action="store_true", help="Output JSON")
