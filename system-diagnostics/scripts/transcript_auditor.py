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

_EXIT_RE = re.compile(r"(?:^|\n)Command exited with code (-?\d+)")
_MODEL_RE = re.compile(r"Model Selection` from [^\n]+? to ([^\n]+?)\. No need")
_USER_REQ_RE = re.compile(r"<USER_REQUEST>.*?</USER_REQUEST>", re.DOTALL)
_SUB_CID_RE = re.compile(r'"conversationId"\s*:\s*"([^"]+)"')
_SENDER_RE = re.compile(r"sender=([^\s\]>]+)")
_LOG_REL = Path(".system_generated") / "logs" / "transcript.jsonl"


def _extract_models(content: str) -> list[str]:
    """Extract model switches from USER_INPUT metadata outside <USER_REQUEST> blocks."""
    cleaned = _USER_REQ_RE.sub("", content)
    return _MODEL_RE.findall(cleaned)


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


def _tool_args(call: dict[str, Any]) -> dict[str, Any]:
    """Return tool-call arguments as a dict regardless of string/dict encoding."""
    args = call.get("args") or call.get("arguments") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return {}
    if not isinstance(args, dict):
        return {}
    return {k: _unquote(v) for k, v in args.items()}


def _unquote(value: Any) -> Any:
    """Transcripts store some arguments as JSON-encoded strings (``'"a.py"'``); decode them."""
    if isinstance(value, str) and len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _classify_result(content: str, status: str) -> str | None:
    """Classify a tool-result step as cmd_fail / edit_fail / read_fail, else None."""
    head = content[:400]
    is_read_output = "Showing lines " in content[:220] or "Partial read " in content[:220]
    match = _EXIT_RE.search(head)
    if match and not is_read_output:
        return "cmd_fail" if int(match.group(1)) != 0 else None
    if status == "ERROR":
        if "target content not found" in content:
            return "edit_fail"
        if "file does not exist" in content:
            return "read_fail"
    return None


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
    """Accumulate per-call statistics for one planner step."""
    same_step_edits: Counter[str] = Counter()
    for call in step.get("tool_calls") or []:
        name, args = call.get("name", ""), _tool_args(call)
        acc["tools"][name] += 1
        if name == "read_file":
            p_str = str(args.get("Path", ""))
            acc["reads"][p_str] += 1
            if acc["pending_unnamed"] > 0 or acc["pending_cids"]:
                acc["reads_while_pending"] += 1
            elif acc["first_subagent_step"] is not None and p_str:
                acc["post_dispatch_reads"].append(p_str)
        elif name in ("edit_file", "write_file"):
            p_str = str(args.get("Path", ""))
            if p_str:
                acc["edited_paths"].add(_norm_path(p_str))
            if name == "edit_file":
                same_step_edits[p_str] += 1
        elif name == "invoke_subagent":
            acc["subagents"].append({"type": args.get("TypeName"), "model": args.get("Model", "inherit"), "step": idx})
            acc["pending_unnamed"] += 1
            if acc["first_subagent_step"] is None:
                acc["first_subagent_step"] = idx
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


def audit_conversation(brain_dir: Path, cid: str) -> dict[str, Any]:
    """Audit one conversation; returns ``{"cid", "missing": True}`` when no transcript exists."""
    path = brain_dir / cid / _LOG_REL
    if not path.is_file():
        return {"cid": cid, "missing": True}
    acc: dict[str, Any] = {
        "tools": Counter(), "reads": Counter(), "subagents": [], "first_subagent_step": None,
        "pending_unnamed": 0, "pending_cids": set(), "subagent_cids": [], "reads_while_pending": 0,
        "post_dispatch_reads": [], "edited_paths": set(), "parallel_same_file_edits": [],
        "failures": Counter(), "models": [],
    }
    steps = planner = 0
    for idx, step in enumerate(_iter_steps(path)):
        steps += 1
        content, kind = step.get("content") or "", step.get("type", "")
        if kind == "PLANNER_RESPONSE":
            planner += 1
            _record_calls(step, idx, acc)
        elif kind == "USER_INPUT":
            acc["models"].extend(_extract_models(content))
        else:
            _track_subagent_events(kind, content, cid, acc)
            if fail := _classify_result(content, step.get("status", "")):
                acc["failures"][fail] += 1
    sub_reads = _collect_subagent_reads(brain_dir, acc["subagent_cids"])
    acc["overlap_reads"] = sum(
        1 for p in acc["post_dispatch_reads"] if _matches_any(p, sub_reads) and not _matches_any(p, acc["edited_paths"])
    )
    return _summarize(cid, steps, planner, acc)


def _summarize(cid: str, steps: int, planner: int, acc: dict[str, Any]) -> dict[str, Any]:
    """Collapse accumulators into a JSON-friendly report row."""
    repeats = {p: n for p, n in acc["reads"].items() if n > 1 and p}
    dupes = acc["reads_while_pending"] + acc["overlap_reads"]
    return {
        "cid": cid, "steps": steps, "planner_turns": planner, "models": acc["models"],
        "tool_calls": dict(acc["tools"]), "failures": dict(acc["failures"]),
        "total_failures": sum(acc["failures"].values()),
        "subagents": acc["subagents"], "reads_after_subagent": dupes,
        "reads_while_pending": acc["reads_while_pending"], "subagent_overlap_reads": acc["overlap_reads"],
        "repeated_reads": dict(sorted(repeats.items(), key=lambda kv: -kv[1])[:5]),
        "parallel_same_file_edits": acc["parallel_same_file_edits"],
        "suggested_grade_cap": "C" if steps > 100 else ("B" if steps > 60 else "A"),
    }


def _resolve_cids(brain_dir: Path, cids: list[str] | None, latest: int | None) -> list[str]:
    """Pick explicit ids, or the ``latest`` most recently modified conversations."""
    if cids:
        return cids
    dirs = [d for d in brain_dir.iterdir() if (d / _LOG_REL).is_file()] if brain_dir.is_dir() else []
    dirs.sort(key=lambda d: (d / _LOG_REL).stat().st_mtime, reverse=True)
    return [d.name for d in dirs[: latest or 1]]


def format_markdown(rows: list[dict[str, Any]]) -> str:
    """Render a compact markdown table plus waste flags."""
    out = ["| cid | steps | fails | subagents | dup reads | grade cap |", "|---|---:|---:|---:|---:|:--:|"]
    flags: list[str] = []
    for r in rows:
        if r.get("missing"):
            out.append(f"| {r['cid'][:8]} | MISSING | - | - | - | - |")
            continue
        out.append(f"| {r['cid'][:8]} | {r['steps']} | {r['total_failures']} | {len(r['subagents'])} "
                   f"| {r['reads_after_subagent']} | {r['suggested_grade_cap']} |")
        if r["subagents"] and r["reads_after_subagent"] > 4:
            flags.append(
                f"{r['cid'][:8]}: {r['reads_after_subagent']} subagent duplicate reads "
                f"({r.get('reads_while_pending', 0)} pending + {r.get('subagent_overlap_reads', 0)} unedited overlap)"
            )
        for e in r["parallel_same_file_edits"]:
            flags.append(f"{r['cid'][:8]}: step {e['step']} issued {e['calls']} parallel edits on {Path(e['path']).name}")
    return "\n".join(out + [""] + [f"- FLAG {f}" for f in flags])


def cmd_transcript_audit(args: argparse.Namespace) -> int:
    """Run the audit for the requested conversations; exit 1 if none could be read."""
    brain = Path(args.brain_dir) if args.brain_dir else default_brain_dir()
    rows = [audit_conversation(brain, cid) for cid in _resolve_cids(brain, args.cids, args.latest)]
    print(json.dumps(rows, indent=2) if args.json else format_markdown(rows))
    return 0 if any(not r.get("missing") for r in rows) else 1


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``transcript-audit`` subcommand in diagnose.py."""
    p = subparsers.add_parser("transcript-audit", help="Audit conversation transcripts for waste, errors and subagent duplication")
    p.add_argument("--cids", nargs="+", default=None, help="Conversation ids to audit")
    p.add_argument("--latest", type=int, default=None, help="Audit the N most recently modified conversations")
    p.add_argument("--brain-dir", default=None, help="Override brain dir (default: AGY_BRAIN_DIR or ~/.gemini/antigravity/brain)")
    p.add_argument("--json", action="store_true", help="Emit JSON instead of markdown")
