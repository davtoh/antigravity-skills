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


def _write_standalone_scaffold(root: Path, retro_path: Path, cid: str | None, brain_dir: str | None) -> str:
    """Write/refresh .diagnostics/LEARNING_SCAFFOLD.md when no .frontier plan digest runs."""
    scaf_path = root / ".diagnostics" / "LEARNING_SCAFFOLD.md"
    scaf_path.parent.mkdir(parents=True, exist_ok=True)
    raw = retro_path.read_text(encoding="utf-8", errors="replace") if retro_path.is_file() else ""
    recent = [ln.strip() for ln in raw.splitlines() if ln.startswith(("## [", "- **Root Cause**:", "- **Project", "- **Skill"))][:16]
    ta_cmd = f"`diagnose.py transcript-audit --cids {cid}`" if cid else "`diagnose.py transcript-audit --latest 1`"
    lines = [
        "# Debug Learning Scaffold",
        f"- **Source Ledger**: `{retro_path.relative_to(root).as_posix() if retro_path.is_relative_to(root) else retro_path}`",
        f"- **Latest Telemetry**: {_audit_metrics(cid, brain_dir)}",
        "",
        "## Recent Debug Entries & `/learn` Candidates",
        *(recent or ["- none"]),
        "",
        "## Introspective Commands (User Choice)",
        f"- Transcript Audit: {ta_cmd}",
        "- Persist Lessons: `/learn` (review above candidates and promote to `AGENTS.md` or skill rules)",
    ]
    scaf_path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    return scaf_path.relative_to(root).as_posix() if scaf_path.is_relative_to(root) else str(scaf_path)


def _sync_learning_scaffold(root: Path, retro_path: Path, plan: str | None, cid: str | None, brain_dir: str | None) -> str:
    """Refresh .frontier/LEARN_QUEUE.md (and plan scaffold) if frontier-architect is present, else .diagnostics/LEARNING_SCAFFOLD.md."""
    fa_scripts = Path(__file__).resolve().parents[2] / "frontier-architect" / "scripts"
    if (root / ".frontier").is_dir() and (fa_scripts / "plan_digest.py").is_file():
        import sys
        if str(fa_scripts) not in sys.path:
            sys.path.insert(0, str(fa_scripts))
        try:
            import plan_digest as pd
            if plan and (scaf := pd.write_learning_scaffold(root, plan, backfill=False, brain_dir=brain_dir)):
                return scaf
            wd = pd.build_workspace_digest(root, brain_dir=brain_dir, backfill=False)
            return pd.write_workspace_scaffold(root, wd)
        except Exception:
            pass
    return _write_standalone_scaffold(root, retro_path, cid, brain_dir)


def _print_turn_end_echo(scaffold_rel: str, symptom: str, cause: str, learn: str | None, skill_learn: str | None, plan: str | None) -> None:
    """Emit copy-pasteable Turn-End Echo block matching frontier-architect format."""
    print("\n--- Turn-End Echo (Copy-Paste Into Final Response) ---")
    print("### Continuous Learning & Introspective Options")
    print(f"- **Root Cause Logged**: `{symptom.strip()}` -> {cause.strip()}")
    if learn and learn.strip().lower() not in ("", "none", "n/a"):
        print(f"- **`/learn` candidate (project)**: {learn.strip()}")
    if skill_learn and skill_learn.strip().lower() not in ("", "none", "n/a"):
        print(f"- **`/learn` candidate (skill)**: {skill_learn.strip()}")
    plan_opt = f"`plan_engine.py digest {plan} --backfill --write-scaffold`, " if plan else ""
    print(f"- **Introspective Options**: Review `{scaffold_rel}`, run `/learn`, {plan_opt}or run `diagnose.py transcript-audit --latest 1`.")


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
    scaffold_rel = _sync_learning_scaffold(root, out, getattr(args, "plan", None), args.cid, args.brain_dir)
    print(f"[debug-retro] Learning scaffold: {scaffold_rel}")
    _print_turn_end_echo(scaffold_rel, args.symptom, args.cause, args.learn, args.skill_learn, getattr(args, "plan", None))
    return 0


def register_parser(subparsers: Any) -> None:
    """Register the `debug-retro` subcommand in diagnose.py."""
    p = subparsers.add_parser("debug-retro", help="Log a bounded /app-debugger retrospective entry")
    p.add_argument("--path", default=None, help="Workspace root (default: cwd)")
    p.add_argument("--symptom", required=True, help="Concise bug symptom")
    p.add_argument("--cause", required=True, help="Verified root cause")
    p.add_argument("--status", choices=("verified", "unconfirmed", "escalated"), default="verified")
    p.add_argument("--cid", default=None, help="Conversation ID for transcript telemetry")
    p.add_argument("--plan", default=None, help="Optional active .frontier plan slug to refresh LEARNING_SCAFFOLD.md")
    p.add_argument("--brain-dir", default=None, help="Optional brain dir override")
    p.add_argument("--learn", default=None, help="Project-level /learn candidate")
    p.add_argument("--skill-learn", default=None, help="Skill/tooling /learn candidate")
