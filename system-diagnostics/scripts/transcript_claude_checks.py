#!/usr/bin/env python3
"""Metric derivation for Claude rows (Milestone 2): failures, subagent overlap, markers, cues.

Input is the normalized step list from ``transcript_claude.read_session``; output is a dict of row
fields that the router merges over the structural metrics. Counting rules mirror the Antigravity
reader (``transcript_auditor``) so both vendors feed the same flags and grade cap.

Pending-subagent model: an ``Agent`` call is pending from its ``tool_use`` until its ``tool_result``.
If that result says the agent runs in the background (marker ``bg_launch``) it stays pending until a
user ``<task-notification>`` arrives (one notification retires one agent). Subagent logs are read as
``agent_id`` steps; their ``Read``/``cat`` paths feed the overlap metrics.
"""

import re
from collections import Counter
from typing import Any

from transcript_auditor import _matches_any, _norm_path
from transcript_checks import extract_user_correction

_CAT_RE = re.compile(r"^\s*cat\s+(?:--\s+)?(\S+)\s*$")
_REJECTED_RE = re.compile(r"user doesn't want to proceed|tool use was rejected", re.I)
_DOC_TOKENS = ("/.todo/", "/.frontier/", "/docs/", "/brain/", "/agents.md", "/.agents/", "/claude.md")
HEAVY_CACHE_READ, HEAVY_OUTPUT = 5_000_000, 200_000


def _read_path(step: dict[str, Any]) -> str:
    """Path read by a ``Read`` call or a bare ``cat <path>`` command; empty otherwise."""
    if step["kind"] != "tool_call":
        return ""
    if step["tool"] == "view_file":
        return step["args"]["path"]
    match = _CAT_RE.match(step["args"]["command"]) if step["tool"] == "run_command" else None
    return match.group(1) if match else ""


def failure_metrics(main: list[dict[str, Any]]) -> dict[str, Any]:
    """``failures`` by class, ``total_failures``, ``audit_catches``, usage errors and up to 5 samples."""
    targets = {s["call_id"]: s["args"]["target"] for s in main if s["kind"] == "tool_call"}
    fails: Counter[str] = Counter()
    catches = usage = rejected = 0
    samples: list[str] = []
    for s in (s for s in main if s["kind"] == "tool_result" and s["fail"]):
        if s["fail"] == "audit_catch":
            catches += 1
            continue
        if _REJECTED_RE.search(s["fail_note"]):  # user declined the call: not a failure, not a grade input
            rejected += 1
            continue
        fails[s["fail"]] += 1
        usage += s["usage_error"]
        if len(samples) < 5:
            samples.append(f"step {s['idx']} {s['fail']} ({targets.get(s['call_id']) or 'tool'}): {s['fail_note']}")
    return {"failures": dict(fails), "total_failures": sum(fails.values()), "audit_catches": catches,
            "tooling_cli_fails": usage, "failure_samples": samples, "user_rejected": rejected}


def _walk_pending(main: list[dict[str, Any]]) -> tuple[int, int, list[str]]:
    """Return ``(reads_while_pending, schedule_while_subagent, post_dispatch_reads)`` in main-thread order."""
    pending: set[str] = set()
    background = while_pending = scheduled = 0
    first_dispatch = False
    after: list[str] = []
    for s in main:
        busy = bool(pending) or background > 0
        if s["kind"] == "tool_call" and s["tool"] == "invoke_subagent":
            pending.add(s["call_id"])
            first_dispatch = True
        elif s["kind"] == "tool_call" and s["tool"] == "schedule" and busy:
            scheduled += 1
        elif path := _read_path(s):
            if busy:
                while_pending += 1
            elif first_dispatch:
                after.append(path)
        elif s["kind"] == "tool_result" and s["call_id"] in pending:
            pending.discard(s["call_id"])
            background += "bg_launch" in s["markers"]
        elif s["kind"] == "text" and "task_notification" in s["markers"]:
            background = max(0, background - 1)
    return while_pending, scheduled, after


def subagent_metrics(steps: list[dict[str, Any]]) -> dict[str, Any]:
    """``reads_after_subagent`` (= pending + unedited overlap), ``reads_while_pending``, ``schedule_while_subagent``."""
    main = [s for s in steps if s["agent_id"] is None]
    while_pending, scheduled, after = _walk_pending(main)
    sub_reads = {_norm_path(p) for s in steps if s["agent_id"] is not None and (p := _read_path(s))}
    edited = {_norm_path(s["args"]["path"]) for s in main if s["kind"] == "tool_call" and s["tool"] == "edit_file" and s["args"]["path"]}
    overlap = sum(1 for p in after if _matches_any(p, sub_reads) and not _matches_any(p, edited))
    doc_only = all(any(tok in f"/{ep}" for tok in _DOC_TOKENS) for ep in edited)
    overlap = 0 if (doc_only and overlap <= 8) else overlap
    return {"reads_after_subagent": while_pending + overlap, "reads_while_pending": while_pending,
            "subagent_overlap_reads": overlap, "schedule_while_subagent": scheduled}


def marker_metrics(main: list[dict[str, Any]]) -> dict[str, Any]:
    """Boolean/count fields derived from the reader's content-free ``markers``."""
    marks = Counter(m for s in main for m in s["markers"])
    return {"has_debug_retro": marks["debug_retro"] > 0, "has_commit_hint": marks["commit_hint"] > 0,
            "has_learning_block": marks["learning_block"] > 0, "cdp_live_fallbacks": marks["cdp_fallback"],
            "cdp_live_failures": marks["cdp_live_fail"], "changelog_adds": marks["changelog_add"],
            "masked_failures": marks["masked_failure"]}


def cue_metrics(main: list[dict[str, Any]], cues: dict[str, Any]) -> dict[str, list[str]]:
    """``user_corrections`` / ``workflow_redirects`` from user text, using ``cues`` (see transcript_cues)."""
    acc: dict[str, Any] = {"seen_first_user": False, "user_corrections": [], "workflow_redirects": []}
    for s in main:
        if s["role"] == "user" and s["kind"] == "text" and s["cue_text"]:
            extract_user_correction(s["cue_text"], s["idx"], acc, cues)
    return {"user_corrections": acc["user_corrections"], "workflow_redirects": acc["workflow_redirects"]}


def token_note(tokens: dict[str, int]) -> str | None:
    """Informational only; never changes the grade."""
    notes = []
    if tokens["cache_read"] > HEAVY_CACHE_READ:
        notes.append(f"heavy cache reads ({tokens['cache_read']:,})")
    if tokens["output"] > HEAVY_OUTPUT:
        notes.append(f"heavy output ({tokens['output']:,})")
    return "; ".join(notes) or None


def plan_mode_calls(tools: Counter[str]) -> int:
    """Same allowance as the Antigravity reader: 1 enter and 2 exits are normal."""
    return max(0, tools["enter_plan_mode"] - 1) + max(0, tools["exit_plan_mode"] - 2)


def derive(steps: list[dict[str, Any]], cues: dict[str, Any]) -> dict[str, Any]:
    """All Milestone 2 row fields for one session (main thread + subagent reads)."""
    main = [s for s in steps if s["agent_id"] is None]
    return {**failure_metrics(main), **subagent_metrics(steps), **marker_metrics(main), **cue_metrics(main, cues)}
