#!/usr/bin/env python3
"""Deterministic transcript auditor: replaces ad-hoc scratch parsers for post-step retrospectives.

Streams ``<brain>/<conversation-id>/.system_generated/logs/transcript.jsonl`` and reports steps,
models, subagent usage (and parent re-reads after dispatch), same-file parallel edits, read
repeats, and real tool failures (non-zero command exits, edit/read errors).
"""

import argparse
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

from transcript_checks import (
    append_row_notes,
    classify_result,
    extract_user_correction,
    failure_snippet,
)

_MODEL_RE = re.compile(r"Model Selection` from [^\n]+? to ([^\n]+?)\. No need")
_USER_REQ_RE = re.compile(r"<USER_REQUEST>(.*?)</USER_REQUEST>", re.DOTALL)
_TASK_ID_RE = re.compile(r"\b(task-\d+)\b")
_SUB_CID_RE = re.compile(r'"conversationId"\s*:\s*"([^"]+)"')
_SENDER_RE = re.compile(r"sender=([^\s\]>]+)")
_LOG_REL = Path(".system_generated") / "logs" / "transcript.jsonl"


def _extract_models(content: str) -> list[str]:
    """Extract model switches from USER_INPUT metadata outside <USER_REQUEST> blocks."""
    return _MODEL_RE.findall(_USER_REQ_RE.sub("", content))

def default_brain_dir() -> Path:
    """Resolve the brain directory from AGY_BRAIN_DIR, else the standard per-user location."""
    env = os.getenv("AGY_BRAIN_DIR", "")
    return Path(env) if env else Path.home() / ".gemini" / "antigravity" / "brain"

def _iter_steps(path: Path) -> Iterator[dict[str, Any]]:
    """Yield decoded transcript steps line-by-line, skipping malformed rows."""
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

def _loads_or(raw: str, fallback: Any) -> Any:
    """Decode a JSON string or return ``fallback`` on parse error."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback

def _unquote(value: Any) -> Any:
    """Transcripts store some arguments as JSON-encoded strings (``'"a.py"'``); decode them."""
    return _loads_or(value, value) if (isinstance(value, str) and len(value) >= 2 and value[0] == value[-1] == '"') else value

def _tool_args(call: dict[str, Any]) -> dict[str, Any]:
    """Return tool-call arguments as a dict regardless of string/dict encoding."""
    raw = call.get("args") or call.get("arguments") or {}
    args = _loads_or(raw, {}) if isinstance(raw, str) else raw
    return {k: _unquote(v) for k, v in args.items()} if isinstance(args, dict) else {}


def _norm_path(raw: str) -> str:
    """Normalize a file path to forward-slash lowercase for cross-transcript matching."""
    return raw.strip().replace("\\", "/").lower()

def _matches_any(candidate: str, refs: list[str] | set[str]) -> bool:
    """Return True if normalized ``candidate`` matches or shares a relative tail with ``refs``."""
    norm = _norm_path(candidate)
    if not norm:
        return False
    for r in refs:
        rn = _norm_path(r)
        if rn and (norm == rn or norm.endswith("/" + rn) or rn.endswith("/" + norm)):
            return True
    return False


def _collect_subagent_reads(brain_dir: Path, sub_cids: list[str]) -> set[str]:
    """Collect normalized file paths read by spawned subagents when their transcripts exist."""
    paths: set[str] = set()
    for scid in sub_cids:
        sp = brain_dir / scid / _LOG_REL
        if not sp.is_file():
            continue
        for step in _iter_steps(sp):
            for call in (step.get("tool_calls") or []) if step.get("type") == "PLANNER_RESPONSE" else ():
                if call.get("name") == "read_file":
                    raw = str(_tool_args(call).get("Path", ""))
                    if raw:
                        paths.add(_norm_path(raw))
    return paths


def _record_calls(step: dict[str, Any], idx: int, acc: dict[str, Any]) -> None:
    """Accumulate per-call statistics and FIFO pending_calls for one planner step."""
    acc["pending_calls"].clear()
    same_step_edits: Counter[str] = Counter()
    for call in step.get("tool_calls") or []:
        name, args = call.get("name", ""), _tool_args(call)
        acc["tools"][name] += 1
        p_str = str(args.get("Path", ""))
        target, cmd_line = (Path(p_str).name if p_str else (name or "tool")), ""
        if name == "read_file":
            acc["reads"][p_str] += 1
            if acc["pending_unnamed"] > 0 or acc["pending_cids"]:
                acc["reads_while_pending"] += 1
            elif acc["first_subagent_step"] is not None and p_str:
                acc["post_dispatch_reads"].append(p_str)
        elif name in ("edit_file", "write_file"):
            if p_str:
                acc["edited_paths"].add(_norm_path(p_str))
            if name == "edit_file":
                same_step_edits[p_str] += 1
        elif name == "run_command":
            cmd_line = str(args.get("CommandLine", "")).strip()
            acc["last_cmd"] = cmd_line
            if "changelog add" in cmd_line:
                acc["changelog_adds"] += 1
            target = cmd_line.splitlines()[0][:80] if cmd_line else "run_command"
        elif name == "invoke_subagent":
            acc["subagents"].append({"type": args.get("TypeName"), "model": args.get("Model", "inherit"), "step": idx})
            acc["pending_unnamed"] += 1
            if acc["first_subagent_step"] is None:
                acc["first_subagent_step"] = idx
        elif name in ("enter_plan_mode", "exit_plan_mode"):
            acc["plan_mode_calls"] += 1
        acc["last_target"] = target
        acc["pending_calls"].append((name, target, cmd_line))
    for path, count in same_step_edits.items():
        if count > 1:
            acc["parallel_same_file_edits"].append({"step": idx, "path": path, "calls": count})


def _track_subagent_events(kind: str, content: str, cid: str, acc: dict[str, Any]) -> None:
    """Track dispatched subagent IDs and completion SYSTEM_MESSAGE arrivals."""
    if kind == "GENERIC" and "conversationId" in content:
        for scid in _SUB_CID_RE.findall(content):
            if scid not in acc["subagent_cids"]:
                acc["subagent_cids"].append(scid)
                acc["pending_cids"].add(scid)
                acc["pending_unnamed"] = max(0, acc["pending_unnamed"] - 1)
    elif kind == "SYSTEM_MESSAGE":
        for sender in _SENDER_RE.findall(content):
            if sender == cid or "/task-" in sender:
                continue
            if sender in acc["pending_cids"]:
                acc["pending_cids"].remove(sender)
            elif acc["pending_unnamed"] > 0:
                acc["pending_unnamed"] -= 1


def _resolve_step_call(content: str, kind: str, acc: dict[str, Any]) -> tuple[str, str]:
    """Match a tool-result or SYSTEM_MESSAGE step back to its originating target and command."""
    if kind == "SYSTEM_MESSAGE":
        for sender in _SENDER_RE.findall(content):
            if m := _TASK_ID_RE.search(sender):
                return acc["bg_tasks"].pop(m.group(1), (f"bg:{m.group(1)}", ""))
        return (acc["last_target"], acc["last_cmd"])
    name, target, cmd = acc["pending_calls"].pop(0) if acc["pending_calls"] else ("", acc["last_target"], acc["last_cmd"])
    if name == "run_command" and (m := _TASK_ID_RE.search(content[:400])):
        acc["bg_tasks"][m.group(1)] = (target, cmd)
    return (target, cmd)


def _apply_result_step(content: str, status: str, kind: str, idx: int, acc: dict[str, Any]) -> None:
    """Classify one tool-result step against FIFO pending_calls or bg_tasks and record failures."""
    if "[CDP] Live connection failed" in content:
        acc["cdp_live_fallbacks"] += 1
    call_target, call_cmd = _resolve_step_call(content, kind, acc)
    fail = classify_result(content, status, call_cmd)
    if fail == "audit_catch":
        acc["audit_catches"] += 1
    elif fail:
        acc["failures"][fail] += 1
        if len(acc["failure_samples"]) < 5:
            acc["failure_samples"].append(f"step {idx} {fail} ({call_target or 'tool'}): {failure_snippet(content)}")


def audit_conversation(brain_dir: Path, cid: str) -> dict[str, Any]:
    """Audit one conversation; returns ``{"cid", "missing": True}`` when no transcript exists."""
    path = brain_dir / cid / _LOG_REL
    if not path.is_file():
        return {"cid": cid, "missing": True}
    acc: dict[str, Any] = {
        "tools": Counter(), "reads": Counter(), "subagents": [], "first_subagent_step": None,
        "pending_unnamed": 0, "pending_cids": set(), "subagent_cids": [], "reads_while_pending": 0,
        "post_dispatch_reads": [], "edited_paths": set(), "parallel_same_file_edits": [],
        "pending_calls": [], "bg_tasks": {}, "seen_first_user": False, "failures": Counter(),
        "audit_catches": 0, "failure_samples": [], "user_corrections": [], "plan_mode_calls": 0,
        "has_commit_hint": False, "has_learning_block": False, "last_target": "", "last_cmd": "", "models": [],
        "cdp_live_fallbacks": 0, "changelog_adds": 0,
    }
    steps = planner = 0
    for idx, step in enumerate(_iter_steps(path)):
        steps += 1
        content, kind = step.get("content") or "", step.get("type", "")
        if kind == "PLANNER_RESPONSE":
            planner += 1
            if "git commit" in content: acc["has_commit_hint"] = True
            if "Continuous Learning & Introspective Options" in content: acc["has_learning_block"] = True
            _record_calls(step, idx, acc)
        elif kind == "USER_INPUT":
            acc["models"].extend(_extract_models(content))
            extract_user_correction(content, idx, acc)
        else:
            _track_subagent_events(kind, content, cid, acc)
            _apply_result_step(content, step.get("status", ""), kind, idx, acc)
    sub_reads = _collect_subagent_reads(brain_dir, acc["subagent_cids"])
    acc["overlap_reads"] = sum(1 for p in acc["post_dispatch_reads"] if _matches_any(p, sub_reads) and not _matches_any(p, acc["edited_paths"]))
    return _summarize(cid, steps, planner, acc)


def _summarize(cid: str, steps: int, planner: int, acc: dict[str, Any]) -> dict[str, Any]:
    """Collapse accumulators into a JSON-friendly report row."""
    repeats = {p: n for p, n in acc["reads"].items() if n > 1 and p}
    dupes = acc["reads_while_pending"] + acc["overlap_reads"]
    return {
        "cid": cid, "steps": steps, "planner_turns": planner, "models": acc["models"], "tool_calls": dict(acc["tools"]),
        "failures": dict(acc["failures"]), "total_failures": sum(acc["failures"].values()), "audit_catches": acc["audit_catches"],
        "failure_samples": acc["failure_samples"], "user_corrections": acc["user_corrections"], "subagents": acc["subagents"],
        "reads_after_subagent": dupes, "reads_while_pending": acc["reads_while_pending"], "subagent_overlap_reads": acc["overlap_reads"],
        "repeated_reads": dict(sorted(repeats.items(), key=lambda kv: -kv[1])[:5]),
        "parallel_same_file_edits": acc["parallel_same_file_edits"], "plan_mode_calls": acc["plan_mode_calls"],
        "has_commit_hint": acc["has_commit_hint"], "has_learning_block": acc["has_learning_block"],
        "cdp_live_fallbacks": acc["cdp_live_fallbacks"], "changelog_adds": acc["changelog_adds"],
        "suggested_grade_cap": "C" if steps > 100 else ("B" if steps > 60 else "A"),
    }


def _has_min_steps(log_path: Path, min_steps: int) -> bool:
    """Return True when ``log_path`` contains at least ``min_steps`` non-empty lines."""
    count = 0
    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.strip():
                count += 1
                if count >= min_steps:
                    return True
    return False


def _resolve_cid_token(brain_dir: Path, token: str, dirs: list[Path]) -> str:
    """Resolve an exact or prefix conversation ID token within ``brain_dir``."""
    if (brain_dir / token / _LOG_REL).is_file():
        return token
    low = token.lower()
    return next((d.name for d in dirs if d.name.lower().startswith(low)), token)


def _resolve_cids(brain_dir: Path, cids: list[str] | None, latest: int | None, min_steps: int = 6, workspace: str | None = None) -> list[str]:
    """Pick explicit/prefix ids, or the ``latest`` most recently modified substantive conversations."""
    dirs = [d for d in brain_dir.iterdir() if (d / _LOG_REL).is_file()] if brain_dir.is_dir() else []
    if cids:
        return [_resolve_cid_token(brain_dir, tok.strip(), dirs) for raw in cids for tok in raw.split(",") if tok.strip()]
    if workspace:
        needle = workspace.replace("\\", "/").rstrip("/").lower()
        dirs = [d for d in dirs if needle in (d / _LOG_REL).read_text(encoding="utf-8", errors="replace").replace("\\\\", "/").replace("\\", "/").lower()]
    dirs.sort(key=lambda d: (d / _LOG_REL).stat().st_mtime, reverse=True)
    limit, substantive, short = latest or 1, [], []
    for d in dirs:
        (substantive if _has_min_steps(d / _LOG_REL, min_steps) else short).append(d.name)
        if len(substantive) >= limit:
            break
    return (substantive + short)[:limit]


def format_markdown(rows: list[dict[str, Any]]) -> str:
    """Render a compact markdown table plus waste, failure, repeat, and correction diagnostics."""
    out, notes = ["| cid | steps | fails | subagents | dup reads | grade cap |", "|---|---:|---:|---:|---:|:--:|"], []
    for r in rows:
        cid8 = r["cid"][:8]
        if r.get("missing"):
            out.append(f"| {cid8} | MISSING | - | - | - | - |")
            continue
        out.append(f"| {cid8} | {r['steps']} | {r['total_failures']} | {len(r['subagents'])} | {r['reads_after_subagent']} | {r['suggested_grade_cap']} |")
        append_row_notes(r, cid8, notes)
    return "\n".join(out + ([""] + notes if notes else [""]))


def cmd_transcript_audit(args: argparse.Namespace) -> int:
    """Run the audit for the requested conversations; exit 1 if none could be read."""
    brain = Path(args.brain_dir) if args.brain_dir else default_brain_dir()
    cids = _resolve_cids(brain, args.cids, args.latest, getattr(args, "min_steps", 6), getattr(args, "workspace", None))
    rows = [audit_conversation(brain, cid) for cid in cids]
    print(json.dumps(rows, indent=2) if args.json else format_markdown(rows))
    return 0 if any(not r.get("missing") for r in rows) else 1


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``transcript-audit`` subcommand in diagnose.py."""
    p = subparsers.add_parser("transcript-audit", help="Audit conversation transcripts for waste, errors and subagent duplication")
    p.add_argument("--cids", nargs="+", default=None, help="Conversation ids (full, 8-char prefix, or comma-separated)")
    p.add_argument("--latest", type=int, default=None, help="Audit the N most recently modified substantive conversations")
    p.add_argument("--min-steps", type=int, default=6, help="Minimum steps preferred for --latest (default: 6)")
    p.add_argument("--workspace", default=None, help="Filter --latest conversations to those referencing this workspace path")
    p.add_argument("--brain-dir", default=None, help="Override brain dir (default: AGY_BRAIN_DIR or ~/.gemini/antigravity/brain)")
    p.add_argument("--json", action="store_true", help="Emit JSON instead of markdown")
