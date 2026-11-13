#!/usr/bin/env python3
"""Telemetry, retrospective logging, lookup, and verification helpers for plan_engine."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import argparse
import os
import re
import subprocess
import sys

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from plan_parser import parse_plan_markdown
from plan_state import bootstrap_plan, get_frontier_dir, load_json, resolve_plan_path, save_json


def _clamp_tri_score(val: int) -> int:
    """Clamp a TRI dimension score to the valid 1..5 inclusive scale."""
    return max(1, min(5, val))


def _parse_tri(tri_arg: str | None) -> dict[str, Any]:
    """Parse tool reliability index argument into dictionary with scores clamped 1..5."""
    if not tri_arg:
        return {}
    items = [item.strip() for item in tri_arg.split(",") if item.strip()]
    if items and all("=" not in item and ":" not in item for item in items) and len(items) == 4:
        dims = ["token_efficiency", "hypothesis_accuracy", "tool_reliability", "architectural_defense"]
        try:
            vals = [_clamp_tri_score(int(x)) for x in items]
            scores: dict[str, Any] = dict(zip(dims, vals))
            avg = sum(vals) / 4.0
            scores["overall"] = int(avg) if avg.is_integer() else round(avg, 2)
            return scores
        except ValueError:
            pass
    scores = {}
    for item in items:
        sep = "=" if "=" in item else (":" if ":" in item else None)
        if sep:
            k, v = item.split(sep, 1)
            try:
                scores[k.strip()] = _clamp_tri_score(int(v.strip()))
            except ValueError:
                pass
        else:
            try:
                scores["overall"] = _clamp_tri_score(int(item))
            except ValueError:
                pass
    return scores


def get_prior_learn_candidates(root: Path, slug: str) -> list[str]:
    """Return deduplicated learn_candidates recorded in prior milestones for ``slug``."""
    retro_path = get_frontier_dir(root) / "plans" / slug / "retrospectives.json"
    entries = load_json(retro_path, [])
    if not isinstance(entries, list):
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for item in entry.get("learn_candidates", []) or []:
            text = str(item).strip()
            if text and text not in seen:
                seen.add(text)
                ordered.append(text)
    return ordered


def cmd_retrospective(root: Path, args: argparse.Namespace) -> int:
    """Record Token Efficiency Grade, TRI, and /learn candidate proposals."""
    plan_p = resolve_plan_path(root, args.plan)
    if not plan_p:
        print("[plan_engine] Error: No plan resolved.")
        return 1
    _ws, ps = bootstrap_plan(root, plan_p)
    fdir = get_frontier_dir(root)
    retro_path = fdir / "plans" / ps["slug"] / "retrospectives.json"
    retros = load_json(retro_path, [])

    milestone_idx = (
        args.milestone
        if args.milestone is not None
        else ps.get("last_advanced_milestone", ps["active_milestone_index"])
    )
    tri_scores = _parse_tri(args.tri)
    if args.tri and not tri_scores:
        print(f"[plan_engine] Warning: Could not parse --tri '{args.tri}'. Use 'k=5,k2=4' or '5,5,5,5'.")
    entry = {
        "milestone_index": milestone_idx,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "token_efficiency_grade": (args.grade or "A").upper(),
        "tool_reliability_scores": tri_scores,
        "hypotheses_tested": args.hypotheses or 1,
        "root_causes_escalated": [args.escalate] if args.escalate else [],
        "learn_candidates": [args.learn] if args.learn else [],
    }
    retros.append(entry)
    save_json(retro_path, retros)

    ws = load_json(fdir / "state.json", {})
    ws.setdefault("retrospectives", []).append(entry)
    save_json(fdir / "state.json", ws)

    print(f"[plan_engine] Logged retrospective for Milestone {entry['milestone_index']}:")
    print(f"  Token Grade: {entry['token_efficiency_grade']} | TRI: {entry['tool_reliability_scores']}")
    if entry["learn_candidates"]:
        print(f"  /learn candidate: {entry['learn_candidates'][0]}")
    return 0


def cmd_lookup(root: Path, args: argparse.Namespace) -> int:
    """Surface past decisions, milestones, commits, and retrospectives."""
    q = args.query.lower().strip()
    fdir = get_frontier_dir(root)
    ws = load_json(fdir / "state.json", {})
    results: list[dict[str, Any]] = []

    for item in ws.get("plan_history", []):
        if q in item.get("slug", "").lower() or q in item.get("title", "").lower():
            results.append({"type": "plan", "item": item})

    for pdir in (fdir / "plans").glob("*"):
        st = load_json(pdir / "state.json", {})
        if not st:
            continue
        for m in st.get("milestones", []):
            if q in m.get("title", "").lower() or q in m.get("commit_sha", "").lower():
                results.append({"type": "milestone", "plan": st.get("slug"), "milestone": m})
        for r in load_json(pdir / "retrospectives.json", []):
            learns = " ".join(r.get("learn_candidates", [])).lower()
            escs = " ".join(r.get("root_causes_escalated", [])).lower()
            if q in learns or q in escs:
                results.append({"type": "retrospective", "plan": st.get("slug"), "retro": r})

    if not results:
        print(f"[plan_engine] No historical decisions or plans matched query '{args.query}'.")
        return 0

    print(f"[plan_engine] Lookup results for '{args.query}' ({len(results)} matches):")
    for r in results:
        if r["type"] == "plan":
            print(f"  [PLAN] {r['item'].get('title')} ({r['item'].get('slug')}) - {r['item'].get('status')}")
        elif r["type"] == "milestone":
            m = r["milestone"]
            print(f"  [MILESTONE] Plan: {r['plan']} -> M{m.get('index')}: {m.get('title')} (sha: {m.get('commit_sha')})")
        elif r["type"] == "retrospective":
            print(f"  [RETRO] Plan: {r['plan']} M{r['retro'].get('milestone_index')}: Learn={r['retro'].get('learn_candidates')}")
    return 0


def _extract_leading_env(cmd: str) -> tuple[dict[str, str], str]:
    """Extract leading POSIX VAR=VAL assignments so Windows shell=True runs cleanly."""
    extra_env: dict[str, str] = {}
    rest = cmd.lstrip()
    while True:
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=([^\s'\"]+)\s+(.+)$", rest)
        if not m:
            break
        extra_env[m.group(1)] = m.group(2)
        rest = m.group(3).lstrip()
    return extra_env, rest


def _resolve_venv_python(root: Path) -> str | None:
    """Return relative virtualenv python path if .venv/venv/env exists under root."""
    rel_candidates = (
        (".venv\\Scripts\\python.exe", "venv\\Scripts\\python.exe", "env\\Scripts\\python.exe")
        if os.name == "nt"
        else (".venv/bin/python", "venv/bin/python", "env/bin/python")
    )
    for rel in rel_candidates:
        if (root / rel.replace("\\", "/")).is_file():
            return rel
    return None


def _normalize_verify_cmd(cmd: str, root: Path) -> str:
    """Normalize leading python/venv paths for the host OS while preserving arguments."""
    if not cmd.strip():
        return cmd
    stripped = cmd.lstrip()
    quote = stripped[0] if stripped[0] in ('"', "'") else ""
    if quote:
        end_idx = stripped.find(quote, 1)
        if end_idx == -1:
            return cmd
        first_token, rest = stripped[1:end_idx], stripped[end_idx + 1 :]
    else:
        parts = stripped.split(None, 1)
        first_token, rest = parts[0], (" " + parts[1] if len(parts) > 1 else "")
    if first_token in ("python", "python3"):
        venv_py = _resolve_venv_python(root)
        return f"{venv_py}{rest}" if venv_py else cmd
    if os.name != "nt" or "/" not in first_token:
        return cmd
    clean = first_token.removeprefix("./")
    if clean in (".venv/bin/python", "venv/bin/python", "env/bin/python"):
        win_py = root / clean.split("/")[0] / "Scripts" / "python.exe"
        if win_py.is_file():
            first_token = first_token.replace("/bin/python", "\\Scripts\\python.exe").replace("/", "\\")
    elif clean.startswith((".venv/", "venv/", "env/")) or (root / clean.replace("/", "\\")).exists():
        first_token = first_token.replace("/", "\\")
    return f"{quote}{first_token}{quote}{rest}"


def _parse_test_counts(output: str) -> tuple[int, int]:
    """Extract passed and failed test counts from unittest or pytest output."""
    passed, failed = 0, 0
    ok_match = re.search(r"Ran (\d+) tests?.*?\n\nOK", output)
    if ok_match:
        passed = int(ok_match.group(1))
    fail_match = re.search(r"FAILED \((?:failures=(\d+))?(?:, )?(?:errors=(\d+))?\)", output)
    if fail_match:
        failed = sum(int(x) for x in fail_match.groups() if x)
    if passed == 0 and failed == 0:
        pt_pass = re.search(r"(\d+)\s+passed", output)
        pt_fail = re.search(r"(\d+)\s+failed", output)
        pt_err = re.search(r"(\d+)\s+errors?", output)
        if pt_pass or pt_fail or pt_err:
            passed = int(pt_pass.group(1)) if pt_pass else 0
            failed = (int(pt_fail.group(1)) if pt_fail else 0) + (int(pt_err.group(1)) if pt_err else 0)
    return passed, failed


def cmd_verify(root: Path, args: argparse.Namespace) -> int:
    """Run verification command and update baseline ledger."""
    cmd = args.command
    plan_p = resolve_plan_path(root, args.plan)
    if not cmd and plan_p:
        parsed = parse_plan_markdown(plan_p.read_text(encoding="utf-8"))
        if parsed["verification_commands"]:
            cmd = parsed["verification_commands"][0]
    if not cmd:
        ws_existing = load_json(get_frontier_dir(root) / "state.json", {})
        cmd = ws_existing.get("verification_baseline", {}).get("command")

    if not cmd:
        print(
            "[plan_engine] Error: No verification command specified or found in plan. "
            'Pass --command "<cmd>" or include runnable commands in code blocks / Scenario Matrix tables.'
        )
        return 1

    extra_env, stripped_cmd = _extract_leading_env(cmd)
    exec_cmd = _normalize_verify_cmd(stripped_cmd, root)
    run_env = {**os.environ, **extra_env} if extra_env else None
    print(f"[plan_engine] Running verifier: {exec_cmd}")
    proc = subprocess.run(exec_cmd, shell=True, cwd=root, env=run_env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    output = (proc.stdout or "") + (proc.stderr or "")
    print(output)

    passed, failed = _parse_test_counts(output)

    fdir = get_frontier_dir(root)
    ws = load_json(fdir / "state.json", {})
    ws["verification_baseline"] = {
        "command": cmd,
        "last_exit_code": proc.returncode,
        "passed_tests": passed,
        "failed_tests": failed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    save_json(fdir / "state.json", ws)
    return proc.returncode
