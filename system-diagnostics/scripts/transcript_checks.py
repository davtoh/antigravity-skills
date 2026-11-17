#!/usr/bin/env python3
"""Classification, failure-snippet, and markdown-flag helpers for transcript_auditor."""

import re
from pathlib import Path
from typing import Any

_EXIT_RE = re.compile(r"(?:^|\n)Command exited with code (-?\d+)")
_USER_REQ_RE = re.compile(r"<USER_REQUEST>(.*?)</USER_REQUEST>", re.DOTALL)
_CORRECTION_RE = re.compile(r"\b(no|instead|wrong|failed|don't|do not|stop|worthless|why did you)\b", re.I)
_FIRST_OVERRIDE_RE = re.compile(r"^(?:no\b|stop\b|wrong\b|don't\b|do not\b|actually\b|wait\b)", re.I)
_NOISE_PREFIXES = (
    "Created At:", "Completed At:", "Command output:", "Log: file:///",
    "<SYSTEM_MESSAGE>", "</SYSTEM_MESSAGE>", "YOU MUST TAKE ", "DO NOTHING ELSE.",
)


def classify_result(content: str, status: str, last_cmd: str = "") -> str | None:
    """Classify a tool-result step as cmd_fail / audit_catch / edit_fail / read_fail, else None."""
    head = content[:1500] if "<SYSTEM_MESSAGE>" in content[:150] else content[:400]
    is_read_output = "Showing lines " in content[:220] or "Partial read " in content[:220]
    match = _EXIT_RE.search(head)
    if match and not is_read_output:
        code = int(match.group(1))
        if code == 1 and re.search(r"\bgit\s+grep\b", last_cmd) and "fatal:" not in content.lower():
            return None
        if code == 1 and re.search(r"diagnose\.py\s+(?:audit|scan)\b", last_cmd) and "traceback" not in content.lower():
            return "audit_catch"
        return "cmd_fail" if code != 0 else None
    if status == "ERROR":
        return "edit_fail" if "target content not found" in content else ("read_fail" if "file does not exist" in content else None)
    return None


def failure_snippet(content: str) -> str:
    """Extract a concise single-line failure snippet from tool output."""
    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    body = [ln for ln in lines if not ln.startswith(_NOISE_PREFIXES)]
    non_exit = [ln for ln in body if not _EXIT_RE.match(ln)]
    chosen = non_exit[-1] if non_exit else (body[0] if body else "error")
    return " ".join(chosen.split())[:90]


def extract_user_correction(content: str, idx: int, acc: dict[str, Any]) -> None:
    """Capture up to 3 user correction/override prompts for /learn and eval generation."""
    is_first = not acc["seen_first_user"]
    acc["seen_first_user"] = True
    if len(acc["user_corrections"]) >= 3:
        return
    matches = _USER_REQ_RE.findall(content)
    clean_req = " ".join(("\n".join(matches) if matches else content).split())
    if not clean_req or (is_first and not _FIRST_OVERRIDE_RE.match(clean_req)):
        return
    if _CORRECTION_RE.search(clean_req):
        acc["user_corrections"].append(f"step {idx}: {clean_req[:110]}")


def append_row_notes(r: dict[str, Any], cid8: str, notes: list[str]) -> None:
    """Append waste flags, failure samples, repeated reads, and user corrections for one row."""
    if r["subagents"] and r["reads_after_subagent"] > 4:
        notes.append(f"- FLAG {cid8}: {r['reads_after_subagent']} subagent duplicate reads ({r.get('reads_while_pending', 0)} pending + {r.get('subagent_overlap_reads', 0)} unedited overlap)")
    notes += [f"- FLAG {cid8}: step {e['step']} issued {e['calls']} parallel edits on {Path(e['path']).name}" for e in r["parallel_same_file_edits"]]
    if r.get("cdp_live_fallbacks", 0) >= 1:
        notes.append(f"- FLAG {cid8}: {r['cdp_live_fallbacks']} CDP --live->headless fallback(s) (live browser state bypassed)")
    if r.get("changelog_adds", 0) >= 2:
        notes.append(f"- FLAG {cid8}: {r['changelog_adds']} changelog add calls in one session (premature fix clutter)")
    if (r.get("failures") or {}).get("read_fail", 0) >= 2:
        notes.append(f"- FLAG {cid8}: {r['failures']['read_fail']} read_fail path-guess errors (use git grep/surface first)")
    notes += [f"- FAIL {cid8}: {s}" for s in r.get("failure_samples", [])]
    if r.get("plan_mode_calls"):
        notes.append(f"- FLAG {cid8}: called enter/exit_plan_mode ({r['plan_mode_calls']}x)")
    if reps := ", ".join(f"{Path(p).name} ({n}x)" for p, n in (r.get("repeated_reads") or {}).items() if n >= 2):
        notes.append(f"- REPEAT {cid8}: {reps}")
    notes += [f"- CORRECTION {cid8}: {c}" for c in r.get("user_corrections", [])]
