#!/usr/bin/env python3
"""`diagnose.py brief`: one-shot, capped digest of everything pending in a project."""

import json
from pathlib import Path
from typing import Any

import brief_sections as sec

# (key, title, per-section line cap, collector) in the fixed output order.
SECTIONS = (
    ("git", "Git", 8, sec.git),
    ("plans", "Plans", 10, sec.plans),
    ("observations", "Observations", 30, sec.observations),
    ("defects", "Defects", 10, sec.defects),
    ("traces", "Traces", 10, sec.traces),
    ("probes", "Probes", 15, sec.probes),
    ("architecture", "Architecture", 10, sec.architecture),
)


def register_parser(sub: Any) -> None:
    p = sub.add_parser("brief", help="One-shot state-of-project digest (git, plans, observations, defects, traces, probes, architecture)")
    p.add_argument("--path", default=None, help="Workspace root (default: current directory)")
    p.add_argument("--json", action="store_true", help="Machine-readable output")
    p.add_argument("--run-probes", dest="run_probes", action="store_true", help="Run every workspace probe fresh (60s each)")
    p.add_argument("--pull", default=None, metavar="URL", help="Pull remote observations before collecting")
    p.add_argument("--max-lines", dest="max_lines", type=int, default=120, help="Total line cap (default 120)")


def _collect(key: str, collector: Any, ws: Path, ctx: dict) -> dict[str, Any]:
    try:
        out = collector(ws, ctx)
        return {"status": "ok", "lines": list(out["lines"]), "data": out.get("data")}
    except Exception as exc:  # honest isolation: one failing section never hides the others
        return {"status": "unavailable", "lines": [f"UNAVAILABLE ({exc or type(exc).__name__})"], "data": None}


def _pull_first(ws: Path, url: str) -> dict[str, Any]:
    import observation_pull as pull
    try:
        warning = pull.check_url(url, False)
        if warning:
            return {"ok": False, "reason": warning}
        counts = pull.pull(ws, url)
        return {"ok": True, "counts": counts}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def build(ws: Path, run_probes: bool = False, pull_url: str | None = None, max_lines: int = 120) -> dict[str, Any]:
    """Collect all sections in order; caps each section, then the total (never dropping a header)."""
    ctx: dict[str, Any] = {"run_probes": run_probes}
    pulled = _pull_first(ws, pull_url) if pull_url else None
    sections, budget = [], max(len(SECTIONS), max_lines)
    for key, title, cap, collector in SECTIONS:
        res = _collect(key, collector, ws, ctx)
        lines = res["lines"]
        if key == "observations" and pulled is not None:
            note = f"pull: {pulled['counts']}" if pulled["ok"] else f"pull failed: {pulled['reason']}"
            lines = [note] + lines
        shown = lines[:cap]
        if len(lines) > cap:
            shown[-1] = f"... +{len(lines) - cap + 1} more (use the dedicated command)"
        sections.append({"key": key, "title": title, "status": res["status"], "lines": shown, "data": res["data"]})
    return {"workspace": str(ws), "sections": _apply_total_cap(sections, budget)}


def _apply_total_cap(sections: list[dict[str, Any]], budget: int) -> list[dict[str, Any]]:
    """Trim from the last sections backwards so earlier sections stay intact; each keeps >= 1 body line."""
    used = sum(1 + len(s["lines"]) for s in sections)
    for s in reversed(sections):
        if used <= budget:
            break
        drop = min(used - budget, len(s["lines"]) - 1)
        if drop > 0:
            s["lines"] = s["lines"][:-drop - 1] + [f"... +{drop + 1} more"]
            used -= drop
    return sections


def render(report: dict[str, Any]) -> str:
    out: list[str] = []
    for s in report["sections"]:
        out.append(f"## {s['title']}")
        out.extend(s["lines"])
    return "\n".join(out)


def cmd_brief(args: Any) -> int:
    if args.max_lines is not None and args.max_lines < 1:
        print("[diagnose brief] Error: --max-lines must be >= 1", flush=True)
        return 2
    ws = Path(args.path).resolve() if args.path else Path.cwd().resolve()
    report = build(ws, args.run_probes, args.pull, args.max_lines)
    print(json.dumps(report, indent=2, default=str) if args.json else render(report), flush=True)
    return 0
