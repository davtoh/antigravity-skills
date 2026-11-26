#!/usr/bin/env python3
"""Session ledger writer: ``.frontier/sessions.jsonl`` (decision D6), read by ``transcript-audit --plan``.

Line contract: ``{"v":1,"ts":ISO-UTC,"plan":slug,"milestone":int|null,"event":"advance|retrospective|handoff|manual",
"vendor":"claude|gemini","session_id":id,"inferred":false,"branch":"<optional>"}``.
Only a known session id is recorded (``CLAUDE_CODE_SESSION_ID`` under Claude Code); an unknown id is
never guessed: no line is written and a one-line notice goes to stderr. Failures never break the caller.
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import subprocess
import sys

from plan_state import get_frontier_dir

EVENTS = ("advance", "retrospective", "handoff", "manual")


def current_session() -> tuple[str, str]:
    """``(vendor, session_id)`` of the running agent; empty id when it cannot be known."""
    return ("claude", os.getenv("CLAUDE_CODE_SESSION_ID", "").strip())


def _branch(root: Path) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def _already(path: Path, line: dict) -> bool:
    """True when the same plan/milestone/event/session was already recorded (hooks are idempotent)."""
    try:
        existing = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    keys = ("plan", "milestone", "event", "session_id")
    for raw in existing:
        try:
            old = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(old, dict) and all(old.get(k) == line[k] for k in keys):
            return True
    return False


def record_session(root: Path, plan: str, milestone: int | None, event: str = "manual") -> bool:
    """Append one ledger line for the current session; returns True when a line was written."""
    vendor, sid = current_session()
    if not sid:
        if os.getenv("CLAUDECODE"):
            print("[plan_engine] session ledger: no session id (CLAUDE_CODE_SESSION_ID unset); nothing recorded.", file=sys.stderr)
        return False
    line = {"v": 1, "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "plan": plan,
            "milestone": milestone if isinstance(milestone, int) else None, "event": event if event in EVENTS else "manual",
            "vendor": vendor, "session_id": sid, "inferred": False}
    if branch := _branch(root):
        line["branch"] = branch
    path = get_frontier_dir(root) / "sessions.jsonl"
    try:
        if _already(path, line):
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(line) + "\n")
    except OSError:
        return False
    return True
