#!/usr/bin/env python3
"""Independent collectors for `diagnose.py brief`. Each returns {"lines": [...], "data": ...}.

A collector may raise; `brief.py` turns that into `UNAVAILABLE (<reason>)` for its section only.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import observation_store as store
import observation_correlate as correlate
import probe_history
import probe_runner

FINDING_KINDS = ("element", "error", "network", "note")
RUN_TIMEOUT = 60.0


class SectionUnavailable(Exception):
    """Raised by a collector when its data source does not exist (not an error in the app)."""


def _run(cmd: list[str], cwd: Path, timeout: float = 20.0) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def git(ws: Path, _ctx: dict) -> dict[str, Any]:
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], ws)
    if branch.returncode != 0:
        raise SectionUnavailable("not a git repository")
    lines = [f"branch: {branch.stdout.strip()}"]
    ab = _run(["git", "rev-list", "--left-right", "--count", "@{upstream}...HEAD"], ws)
    if ab.returncode == 0 and len(ab.stdout.split()) == 2:
        behind, ahead = ab.stdout.split()
        lines.append(f"ahead {ahead} / behind {behind}")
    else:
        lines.append("no upstream configured")
    status = [ln for ln in _run(["git", "status", "--short"], ws).stdout.splitlines() if ln.strip()]
    counts = {"untracked": sum(1 for s in status if s.startswith("??")), "modified": sum(1 for s in status if not s.startswith("??"))}
    lines.append(f"working tree: {counts['modified']} modified, {counts['untracked']} untracked" if status else "working tree: clean")
    return {"lines": lines, "data": {"branch": branch.stdout.strip(), **counts}}


def _plan_engine_candidates() -> list[Path]:
    here = Path(__file__).resolve().parent
    env_dir = os.environ.get("FRONTIER_ARCHITECT_DIR")
    rel = Path("scripts") / "plan_engine.py"
    return [c for c in (
        Path(env_dir) / rel if env_dir else None,
        here.parent.parent / "frontier-architect" / rel,
        Path.cwd() / ".claude" / "skills" / "frontier-architect" / rel,
        Path.home() / ".claude" / "skills" / "frontier-architect" / rel,
        Path.home() / ".gemini" / "config" / "skills" / "frontier-architect" / rel,
    ) if c]


def plans(ws: Path, _ctx: dict) -> dict[str, Any]:
    todo = ws / ".TODO"
    count = len(list(todo.glob("*.md"))) if todo.is_dir() else 0
    engine = next((c for c in _plan_engine_candidates() if c.is_file()), None)
    if engine is not None and not (ws / ".frontier").is_dir():
        # `plan_engine status` provisions .frontier/; brief is read-only, so do not trigger that.
        return {"lines": [f"{count} plan file(s) in .TODO; no .frontier ledger (register with plan_engine.py init)"], "data": {"plans": count, "engine": True}}
    if engine is None:
        return {"lines": [f"{count} plan file(s) in .TODO; frontier-architect not found"], "data": {"plans": count, "engine": False}}
    out = _run([sys.executable, str(engine), "status"], ws).stdout.splitlines()
    keep = [ln.strip() for ln in out if ln.startswith(("Plan:", "Slug:", "Progress:")) or "[▶]" in ln]
    return {"lines": keep or [f"{count} plan file(s) in .TODO; no active plan reported"], "data": {"plans": count, "engine": True}}


def _obs_line(entry: dict[str, Any], traces: list[str]) -> str:
    tail = f" traces: {', '.join(traces)}" if traces else ""
    return (f'{entry["id"]} {entry.get("page_path") or "-"} {entry.get("selector") or "-"} '
            f'"{entry.get("message", "")}" ({entry.get("occurrence_count", 1)}x){tail}')


def observations(ws: Path, _ctx: dict) -> dict[str, Any]:
    if not (ws / ".diagnostics" / store.CATALOG_NAME).is_file():  # load_catalog would create .diagnostics/
        return {"lines": ["No active observations."], "data": {"findings": [], "ideas": []}}
    active = store.list_observations(ws, status="active", limit=0)
    traces_dir = ws / ".diagnostics" / "traces"
    findings, ideas = [], []
    for entry in active:
        ids = entry.get("correlated_traces") or (correlate.correlate(entry, traces_dir) if traces_dir.is_dir() else [])
        (ideas if entry["kind"] == "idea" else findings).append((entry, ids))
    lines = [f"Findings ({len(findings)}):"] + [f"  {_obs_line(e, t)}" for e, t in findings]
    lines += [f"Ideas ({len(ideas)}):"] + [f"  {_obs_line(e, t)}" for e, t in ideas]
    if not active:
        lines = ["No active observations."]
    return {"lines": lines, "data": {"findings": [dict(e, correlated_traces=t) for e, t in findings], "ideas": [e for e, _ in ideas]}}


def defects(ws: Path, _ctx: dict) -> dict[str, Any]:
    path = ws / ".diagnostics" / "defect_catalog.json"
    if not path.is_file():
        raise SectionUnavailable("no .diagnostics/defect_catalog.json (run `diagnose.py scan`)")
    items = [d for d in json.loads(path.read_text(encoding="utf-8")).get("defects", []) if d.get("status", "active") == "active"]
    lines = [f"{len(items)} open defect(s)"] + [f'  {d.get("id", "?")} [{d.get("severity", "?")}] {d.get("file", d.get("path", ""))} {d.get("message", d.get("rule", ""))}' for d in items[:5]]
    return {"lines": lines, "data": {"open": len(items), "top": items[:5]}}


def traces(ws: Path, _ctx: dict) -> dict[str, Any]:
    path = ws / ".diagnostics" / "trace_catalog.json"
    if not path.is_file():
        raise SectionUnavailable("no .diagnostics/trace_catalog.json")
    issues = [i for i in json.loads(path.read_text(encoding="utf-8")).get("issues", []) if i.get("status", "active") == "active"]
    lines = [f"{len(issues)} active trace issue(s)"] + [f'  {i.get("id", i.get("fingerprint", "?"))} {i.get("exception_type", i.get("type", ""))}: {str(i.get("message", ""))[:80]}' for i in issues[:5]]
    return {"lines": lines, "data": {"active": len(issues), "top": issues[:5]}}


def probes(ws: Path, ctx: dict) -> dict[str, Any]:
    registered = probe_runner.list_probes(workspace_root=ws)
    if ctx.get("run_probes"):
        for p in registered:
            res = probe_runner.run_probe(p.name, python_bin=sys.executable, workspace_root=ws, timeout=RUN_TIMEOUT)
            probe_history.record(ws, res)
        label = "fresh"
    else:
        label = None
    history = probe_history.load(ws)
    lines, data = [f"{len(registered)} probe(s) registered"], []
    for p in registered:
        h = history.get(p.name)
        if not h:
            lines.append(f"  {p.name}: never run")
            data.append({"probe": p.name, "status": "never_run"})
            continue
        tag = label or f"last run {probe_history.age(h.get('ran_at', ''))} ago"
        lines.append(f"  {p.name}: {h['status']} ({tag}) {h.get('summary', '')}")
        data.append({"probe": p.name, **h, "source": label or "recorded"})
    return {"lines": lines, "data": data}


def architecture(ws: Path, _ctx: dict) -> dict[str, Any]:
    import arch_mapper
    rep = arch_mapper.scan_architecture(ws)
    viol = rep["modularity_violations"]
    over = viol["files_over_500"] + viol["files_350_to_499"]
    lines = [f"{rep['total_files']} files, {rep['total_lines']} lines; {len(over)} file(s) over 350 lines"]
    lines += [f"  {f['path']} ({f['lines']}L)" for f in over[:3]]
    lines += [f"coupling: {pkg} -> {', '.join(deps[:3])}" for pkg, deps in list(rep["cross_package_coupling"].items())[:3]]
    return {"lines": lines, "data": {"files_over_350": len(over), "total_files": rep["total_files"]}}
