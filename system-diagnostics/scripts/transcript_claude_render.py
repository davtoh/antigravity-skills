#!/usr/bin/env python3
"""Markdown rendering for mixed-vendor audits (Antigravity-only output stays byte-identical, D4)."""

from typing import Any

import transcript_auditor as ta
from transcript_checks import append_row_notes


def _tokens_cell(row: dict[str, Any]) -> str:
    tok = row.get("tokens")
    if not tok:
        return "-"
    return f"{tok['input'] + tok['cache_creation']:,} in / {tok['cache_read']:,} cached / {tok['output']:,} out"


def format_rows(rows: list[dict[str, Any]]) -> str:
    """Legacy table when no Claude row is present; otherwise the table gains ``vendor`` and ``tokens``."""
    if not any(r.get("vendor") == "claude" for r in rows):
        return ta.format_markdown(rows)
    out = ["| cid | vendor | steps | fails | subagents | dup reads | grade cap | tokens |", "|---|---|---:|---:|---:|---:|:--:|---|"]
    notes: list[str] = []
    for r in rows:
        cid8 = r["cid"][:8]
        if r.get("missing"):
            out.append(f"| {cid8} | - | MISSING | - | - | - | - | - |")
            continue
        out.append(f"| {cid8} | {r.get('vendor', 'gemini')} | {r['steps']} | {r['total_failures']} | {len(r['subagents'])} "
                   f"| {r['reads_after_subagent']} | {r['suggested_grade_cap']} | {_tokens_cell(r)} |")
        append_row_notes(r, cid8, notes)
        if r.get("token_note"):
            notes.append(f"- NOTE {cid8}: {r['token_note']} (informational, grade unchanged)")
    return "\n".join(out + ([""] + notes if notes else [""]))
