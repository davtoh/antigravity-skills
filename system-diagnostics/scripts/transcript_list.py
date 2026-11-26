#!/usr/bin/env python3
"""Session discovery for ``transcript-audit``: ``--list``, ``--since``, ``--plan``, ``--export-summary``.

Never prints raw logs: list lines carry only a 60-char first-prompt snippet (``--no-snippet`` omits it).
Plan sessions come from the ledger ``.frontier/sessions.jsonl``, ``retrospectives.json`` cids and, as a
labeled fallback, sessions whose log mentions the plan slug.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import transcript_auditor as ta
import transcript_sources as src
from transcript_claude import iter_records
from transcript_summary import export_summary, read_summary

PROMPT_MAX = 60


def add_list_args(p: argparse.ArgumentParser) -> None:
    """Additive discovery flags (defaults leave Antigravity behavior untouched)."""
    p.add_argument("--list", action="store_true", help="List sessions (id8 | vendor | started | steps | branch | prompt | plans)")
    p.add_argument("--plan", default=None, help="Audit sessions recorded for this plan slug (ledger, retrospectives, inferred)")
    p.add_argument("--since", default=None, help="Only sessions at or after ISO date/time or <N>d")
    p.add_argument("--limit", type=int, default=20, help="Max sessions for --list/--plan (default: 20)")
    p.add_argument("--export-summary", action="store_true", help="Write .diagnostics/retro/<vendor>-<id8>.json per audited session")
    p.add_argument("--no-snippet", action="store_true", help="Omit the first-prompt text from --list")


def parse_since(value: str | None, now: datetime | None = None) -> datetime | None:
    """``<N>d`` or an ISO date/time (naive means UTC); ``None`` when absent or unparseable."""
    if not value:
        return None
    m = re.fullmatch(r"(\d+)d", value.strip())
    if m:
        return (now or datetime.now(timezone.utc)) - timedelta(days=int(m.group(1)))
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _ts(raw: Any) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00")) if raw else None
    except ValueError:
        return None
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _claude_prompt(rec: dict[str, Any]) -> str:
    content = (rec.get("message") or {}).get("content")
    blocks = content if isinstance(content, list) else [{"type": "text", "text": content}]
    for b in blocks:
        if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str):
            clean = re.sub(r"<[^>]+>", " ", b["text"])
            if clean.strip():
                return " ".join(clean.split())
    return ""


def session_info(vendor: str, sid: str, path: Path, slugs: list[str]) -> dict[str, Any]:
    """Cheap one-pass facts about a session log; tolerant of malformed content."""
    info: dict[str, Any] = {"id": sid, "vendor": vendor, "started": None, "steps": 0, "branch": "", "prompt": "", "plans": []}
    records = iter_records(path) if vendor == "claude" else ta._iter_steps(path)
    for rec in records:
        if not isinstance(rec, dict):
            continue
        info["started"] = info["started"] or _ts(rec.get("timestamp") or rec.get("created_at"))
        info["branch"] = info["branch"] or str(rec.get("gitBranch") or "")
        info["steps"] += 1
        is_user = rec.get("type") in ("user", "USER_INPUT")
        if not info["prompt"] and is_user:
            info["prompt"] = _claude_prompt(rec) if vendor == "claude" else " ".join(str(rec.get("content", "")).split())
    try:
        blob = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        blob = ""
    info["plans"] = [s for s in slugs if s in blob]
    return info


def known_slugs(root: Path) -> list[str]:
    todo = root / ".TODO"
    return sorted(p.stem for p in todo.glob("*.md")) if todo.is_dir() else []


def format_list(infos: list[dict[str, Any]], no_snippet: bool = False) -> str:
    lines = []
    for i in infos:
        started = i["started"].strftime("%Y-%m-%dT%H:%MZ") if i["started"] else "-"
        prompt = "" if no_snippet else i["prompt"][:PROMPT_MAX]
        lines.append(f"{i['id'][:8]} | {i['vendor']} | {started} | {i['steps']} | {i['branch'] or '-'} | {prompt} | {','.join(i['plans']) or '-'}")
    return "\n".join(lines) + ("\n" if lines else "")


def _vendors(args: argparse.Namespace) -> tuple[str, ...]:
    chosen = getattr(args, "vendor", "auto")
    return src.VENDORS if chosen in (None, "auto") else (chosen,)


def discover(args: argparse.Namespace, brain: Path, root: Path) -> list[dict[str, Any]]:
    """Sessions across the selected vendors, newest first, filtered by ``--since``, capped by ``--limit``."""
    claude, proj = getattr(args, "claude_dir", None), getattr(args, "project_dir", None)
    since, slugs, infos = parse_since(getattr(args, "since", None)), known_slugs(root), []
    for vendor in _vendors(args):
        for sid, path in src.list_sessions(vendor, brain, Path(claude) if claude else None, Path(proj) if proj else None):
            infos.append(session_info(vendor, sid, path, slugs))
    infos = [i for i in infos if not since or (i["started"] and i["started"] >= since)]
    infos.sort(key=lambda i: i["started"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return infos[: max(1, getattr(args, "limit", 20))]


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def plan_session_ids(root: Path, slug: str, infos: list[dict[str, Any]]) -> list[tuple[str, bool, str]]:
    """``(session_id, inferred, vendor)`` from the ledger, retrospectives and slug mentions, de-duplicated.

    ``vendor`` is the ledger's recorded vendor, else the vendor of the discovered log, else ``auto``."""
    found: dict[str, tuple[bool, str]] = {}
    ledger = root / ".frontier" / "sessions.jsonl"
    try:
        lines = ledger.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict) and rec.get("plan") == slug and rec.get("session_id"):
            found.setdefault(str(rec["session_id"]), (bool(rec.get("inferred")), str(rec.get("vendor") or "auto")))
    retros = _load(root / ".frontier" / "plans" / slug / "retrospectives.json")
    for e in retros if isinstance(retros, list) else []:
        if isinstance(e, dict) and e.get("cid"):
            found.setdefault(str(e["cid"]), (False, "auto"))
    for i in infos:
        if slug in i["plans"]:
            found.setdefault(i["id"], (True, i["vendor"]))
    return [(sid, inf, ven) for sid, (inf, ven) in found.items()]


def audit_plan(args: argparse.Namespace, brain: Path, root: Path) -> list[dict[str, Any]] | None:
    """Rows for a plan; a deleted log is served from its exported summary (``from_summary``)."""
    from transcript_router import audit  # lazy: the router imports transcript_auditor
    claude, proj = getattr(args, "claude_dir", None), getattr(args, "project_dir", None)
    ids = plan_session_ids(root, args.plan, discover(args, brain, root))[: max(1, args.limit)]
    rows: list[dict[str, Any]] = []
    chosen = getattr(args, "vendor", "auto")
    for sid, inferred, ledger_vendor in ids:
        vendor = chosen if chosen != "auto" else (ledger_vendor if ledger_vendor in src.VENDORS else "auto")
        try:
            row = audit(sid, vendor, brain, Path(claude) if claude else None, Path(proj) if proj else None, root)
        except ValueError as exc:  # ambiguous id: ask for --vendor (exit 2)
            print(f"transcript-audit: {exc}", file=sys.stderr)
            return None
        if row.get("missing") and (saved := read_summary(root, sid)):
            row = saved
        rows.append({**row, "inferred": True} if inferred else row)
    return rows


def run_cli(args: argparse.Namespace, brain: Path, root: Path | None = None) -> int:
    """Entry for ``transcript-audit``; keeps the legacy path byte-identical when no new flag is used."""
    ws = Path(getattr(args, "workspace", None) or ".")
    root = (root or (ws if ws.is_dir() else Path.cwd())).resolve()
    if getattr(args, "list", False):
        print(format_list(discover(args, brain, root), getattr(args, "no_snippet", False)), end="")
        return 0
    from transcript_router import audit_for_cli, format_rows  # lazy: the router imports transcript_auditor
    if getattr(args, "plan", None):
        rows = audit_plan(args, brain, root)
    else:
        cids = ta._resolve_cids(brain, args.cids, args.latest, getattr(args, "min_steps", 6), getattr(args, "workspace", None))
        rows = audit_for_cli(args, brain, cids)
    if rows is None:
        return 2
    if getattr(args, "export_summary", False):
        for r in rows:
            export_summary(root, r)
    print(json.dumps(rows, indent=2) if args.json else format_rows(rows))
    return 0 if any(not r.get("missing") for r in rows) else 1
