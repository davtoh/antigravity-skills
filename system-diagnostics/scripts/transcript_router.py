#!/usr/bin/env python3
"""Vendor router: one ``audit()`` returning the common row shape for either transcript vendor.

Antigravity rows come straight from ``transcript_auditor.audit_conversation`` (unchanged, D4).
Claude rows carry the same keys plus ``vendor``, ``session_id``, ``tokens``, ``token_note``.
Structural metrics live here; failure, subagent-overlap, marker and cue metrics come from
``transcript_claude_checks.derive``. JSON consumers must ignore unknown keys.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import transcript_auditor as ta
from transcript_checks import compute_grade_cap
from transcript_claude import read_session
from transcript_claude_checks import derive, plan_mode_calls, token_note
from transcript_claude_render import format_rows  # noqa: F401  (re-exported for the CLI hook)
from transcript_cues import load_cues
from transcript_sources import default_claude_dir, detect_vendor, find_claude_sessions

_TOKEN_KEYS = ("input", "output", "cache_read", "cache_creation")


def _empty_row(cid: str) -> dict[str, Any]:
    zero = ("tooling_cli_fails", "audit_catches", "reads_after_subagent", "reads_while_pending",
            "subagent_overlap_reads", "schedule_while_subagent", "cdp_live_fallbacks", "cdp_live_failures", "changelog_adds")
    row: dict[str, Any] = {k: 0 for k in zero}
    row.update(cid=cid, failure_samples=[], user_corrections=[], workflow_redirects=[], repeated_reads={},
               has_debug_retro=False, has_commit_hint=False, has_learning_block=False)
    return row


def _tally(steps: list[dict[str, Any]]) -> dict[str, Any]:
    tools: Counter[str] = Counter()
    reads: Counter[str] = Counter()
    subs: list[dict[str, Any]] = []
    tokens = dict.fromkeys(_TOKEN_KEYS, 0)
    models: list[str] = []
    for s in steps:
        if s["model"] and s["model"] not in models:
            models.append(s["model"])
        for key in _TOKEN_KEYS:
            tokens[key] += (s["tokens"] or {}).get(key, 0)
        if s["kind"] == "tool_call" and s["agent_id"] is None:
            tools[s["tool"]] += 1
            reads[s["args"]["path"]] += s["tool"] == "view_file"
            if s["tool"] == "invoke_subagent":
                subs.append({"type": None, "model": "inherit", "step": s["idx"]})
    return {"tools": tools, "reads": reads, "subs": subs, "tokens": tokens, "models": models}


def _parallel_edits(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Two or more edits of one path in the same assistant record share ``ts`` in the main thread."""
    seen: Counter[tuple[str, str]] = Counter(
        (s["ts"], s["args"]["path"]) for s in steps
        if s["kind"] == "tool_call" and s["tool"] == "edit_file" and s["agent_id"] is None and s["ts"] and s["args"]["path"])
    first = {(s["ts"], s["args"]["path"]): s["idx"] for s in reversed(steps) if s["kind"] == "tool_call" and s["tool"] == "edit_file"}
    return [{"step": first[k], "path": k[1], "calls": n} for k, n in seen.items() if n > 1]


def _claude_row(cid: str, path: Path, workspace: Path | None = None) -> dict[str, Any]:
    steps = list(read_session(path))
    main = [s for s in steps if s["agent_id"] is None]
    t = _tally(steps)
    n_steps = sum(1 for s in main if s["kind"] == "tool_call" or (s["kind"] == "text" and s["role"] == "user"))
    derived = derive(steps, load_cues(workspace or Path.cwd()))
    row = _empty_row(cid)
    row.update(
        steps=n_steps, planner_turns=sum(1 for s in main if s["role"] == "assistant" and s["kind"] == "text"),
        models=t["models"], observed_models=t["models"], tool_calls=dict(t["tools"]),
        subagents=t["subs"], parallel_same_file_edits=_parallel_edits(steps),
        repeated_reads=dict(sorted(((p, n) for p, n in t["reads"].items() if n > 1 and p), key=lambda kv: -kv[1])[:5]),
        plan_mode_calls=plan_mode_calls(t["tools"]), **derived,
        suggested_grade_cap=compute_grade_cap(n_steps, derived["total_failures"]),
        vendor="claude", session_id=path.stem, tokens=t["tokens"], token_note=token_note(t["tokens"]))
    return row


def audit(cid: str, vendor: str = "auto", brain_dir: Path | None = None, claude_dir: Path | None = None,
          project_dir: Path | None = None, workspace: Path | None = None) -> dict[str, Any]:
    """Audit one session for either vendor; ``{"cid", "missing": True}`` when no log exists."""
    brain = brain_dir or ta.default_brain_dir()
    chosen = detect_vendor(cid, vendor, brain, claude_dir, project_dir)
    if chosen == "gemini":
        return ta.audit_conversation(brain, cid)
    found = find_claude_sessions(cid, claude_dir or default_claude_dir(), project_dir)
    if len(found) != 1:
        return {"cid": cid, "missing": True, **({"ambiguous": [f.stem for f in found]} if found else {})}
    return _claude_row(cid, found[0], workspace)


def add_vendor_args(parser: argparse.ArgumentParser) -> None:
    """Add the additive vendor flags to ``transcript-audit`` (defaults keep Antigravity behavior)."""
    parser.add_argument("--vendor", choices=("auto", "gemini", "claude"), default="auto", help="Source transcript format (default: auto-detect, else gemini)")
    parser.add_argument("--claude-dir", default=None, help="Claude projects dir (default: $CLAUDE_CONFIG_DIR/projects or ~/.claude/projects)")
    parser.add_argument("--project-dir", default=None, help="Restrict Claude lookup to this project slug folder")
    from transcript_list import add_list_args  # lazy: it imports the auditor
    add_list_args(parser)


def audit_for_cli(args: argparse.Namespace, brain: Path, cids: list[str]) -> list[dict[str, Any]] | None:
    """Audit ``cids`` for the CLI; prints a one-line error and returns ``None`` on a vendor error."""
    claude, proj = getattr(args, "claude_dir", None), getattr(args, "project_dir", None)
    try:
        return [audit(c, getattr(args, "vendor", "auto"), brain, Path(claude) if claude else None, Path(proj) if proj else None) for c in cids]
    except ValueError as exc:
        print(f"transcript-audit: {exc}", file=sys.stderr)
        return None
