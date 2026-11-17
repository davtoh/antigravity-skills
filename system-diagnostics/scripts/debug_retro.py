#!/usr/bin/env python3
"""Standalone debug retrospective logger (works with or without .frontier/)."""

import argparse
import datetime
from pathlib import Path
from typing import Any

import transcript_auditor as ta


def _resolve_retro_path(root: Path) -> Path:
    """Use .frontier/DEBUG_RETRO.md when .frontier exists, else .diagnostics/DEBUG_RETRO.md."""
    frontier_dir = root / ".frontier"
    target_dir = frontier_dir if frontier_dir.is_dir() else (root / ".diagnostics")
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / "DEBUG_RETRO.md"


def _audit_metrics(cid: str | None, brain_dir: str | None) -> str:
    """Summarize transcript steps/failures/fallbacks when --cid is supplied."""
    if not cid:
        return "steps=? | fails=?"
    brain = Path(brain_dir) if brain_dir else ta.default_brain_dir()
    resolved = ta._resolve_cids(brain, [cid], None)
    if not resolved:
        return f"cid={cid[:8]} (missing)"
    row = ta.audit_conversation(brain, resolved[0])
    if row.get("missing"):
        return f"cid={resolved[0][:8]} (missing)"
    return (
        f"cid={row['cid'][:8]} steps={row['steps']} fails={row['total_failures']} "
        f"cap={row['suggested_grade_cap']} cdp_fallbacks={row.get('cdp_live_fallbacks', 0)}"
    )


def _merge_bounded_retro(retro_path: Path, entry: str, max_lines: int = 120) -> str:
    """Prepend entry onto existing DEBUG_RETRO.md content, capped at max_lines."""
    existing: list[str] = []
    if retro_path.is_file():
        raw = retro_path.read_text(encoding="utf-8", errors="replace")
        body = raw.split("\n## ", 1)[1] if "\n## " in raw else ""
        if body:
            existing = ["## " + chunk.strip() for chunk in body.split("\n## ") if chunk.strip()]
    kept, line_count = [], 2
    for blk in [entry, *existing]:
        blk_lines = len(blk.splitlines()) + 1
        if kept and line_count + blk_lines > max_lines:
            break
        kept.append(blk)
        line_count += blk_lines
    return "# Debug Retrospectives\n\n" + "\n\n".join(kept) + "\n"


def record_debug_retro(
    root: Path,
    symptom: str,
    cause: str,
    status: str = "verified",
    cid: str | None = None,
    learn: str | None = None,
    skill_learn: str | None = None,
    brain_dir: str | None = None,
) -> Path:
    """Prepend a bounded debug retrospective entry into DEBUG_RETRO.md (<= 120 lines)."""
    retro_path = _resolve_retro_path(root)
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"## [{today}] [{status.upper()}] {symptom.strip()}",
        f"- **Root Cause**: {cause.strip()}",
        f"- **Telemetry**: {_audit_metrics(cid, brain_dir)}",
    ]
    if learn and learn.strip().lower() not in ("", "none", "n/a"):
        lines.append(f"- **Project `/learn`**: {learn.strip()}")
    if skill_learn and skill_learn.strip().lower() not in ("", "none", "n/a"):
        lines.append(f"- **Skill `/learn`**: {skill_learn.strip()}")
    retro_path.write_bytes(_merge_bounded_retro(retro_path, "\n".join(lines)).encode("utf-8"))
    return retro_path


def cmd_debug_retro(args: argparse.Namespace) -> int:
    """CLI handler for `diagnose.py debug-retro`."""
    root = Path(args.path or ".").resolve()
    out = record_debug_retro(
        root=root,
        symptom=args.symptom,
        cause=args.cause,
        status=args.status,
        cid=args.cid,
        learn=args.learn,
        skill_learn=args.skill_learn,
        brain_dir=args.brain_dir,
    )
    rel = out.relative_to(root).as_posix() if out.is_relative_to(root) else str(out)
    print(f"[debug-retro] Recorded {args.status} entry in {rel}")
    return 0


def register_parser(subparsers: Any) -> None:
    """Register the `debug-retro` subcommand in diagnose.py."""
    p = subparsers.add_parser("debug-retro", help="Log a bounded /app-debugger retrospective entry")
    p.add_argument("--path", default=None, help="Workspace root (default: cwd)")
    p.add_argument("--symptom", required=True, help="Concise bug symptom")
    p.add_argument("--cause", required=True, help="Verified root cause")
    p.add_argument("--status", choices=("verified", "unconfirmed", "escalated"), default="verified")
    p.add_argument("--cid", default=None, help="Conversation ID for transcript telemetry")
    p.add_argument("--brain-dir", default=None, help="Optional brain dir override")
    p.add_argument("--learn", default=None, help="Project-level /learn candidate")
    p.add_argument("--skill-learn", default=None, help="Skill/tooling /learn candidate")
