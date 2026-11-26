#!/usr/bin/env python3
"""Claude Code session reader: normalizes ``<session>.jsonl`` (plus ``subagents/``) into steps.

Claude's log format is not a stable API: every access is defensive (unknown keys ignored,
missing fields defaulted, malformed lines skipped). Raw content never leaves this module
beyond ``text_snippet`` (<= 120 chars).

Step counting rule (used by the router): a *step* is a ``tool_call`` step or a user ``text`` step.
Normalized step: ``{idx, ts, role, kind, tool, args:{path,command,target}, ok, exit_code, error,
model, tokens, agent_id, call_id, text_snippet}``.
"""

import json
import re
from pathlib import Path
from typing import Any, Iterator

SNIPPET_MAX = 120
CANONICAL_TOOLS = {
    "Bash": "run_command", "Read": "view_file", "Edit": "edit_file", "Write": "edit_file",
    "NotebookEdit": "edit_file", "Agent": "invoke_subagent", "Task": "invoke_subagent",
    "EnterPlanMode": "enter_plan_mode", "ExitPlanMode": "exit_plan_mode", "Grep": "search",
    "Glob": "search", "ScheduleWakeup": "schedule", "Skill": "skill",
}
_EXIT_RE = re.compile(r"^Exit code (-?\d+)", re.M)


def _snippet(text: Any) -> str:
    return " ".join(str(text).split())[:SNIPPET_MAX]


def iter_records(path: Path) -> Iterator[dict[str, Any]]:
    """Yield decoded JSON objects, skipping blank, malformed or non-object lines."""
    try:
        handle = path.open("r", encoding="utf-8", errors="replace")
    except OSError:
        return
    with handle:
        for line in handle:
            try:
                rec = json.loads(line) if line.strip() else None
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict):
                yield rec


def session_files(main: Path) -> list[tuple[str | None, Path]]:
    """Main log first (agent ``None``), then ``<id>/subagents/agent-*.jsonl`` sorted by name."""
    files: list[tuple[str | None, Path]] = [(None, main)]
    sub = main.parent / main.stem / "subagents"
    try:
        files += [(f.stem[len("agent-"):] if f.stem.startswith("agent-") else f.stem, f) for f in sorted(sub.glob("agent-*.jsonl"))]
    except OSError:
        pass
    return files


def _blocks(message: Any) -> list[Any]:
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return content if isinstance(content, list) else []


def _tool_args(inp: Any) -> dict[str, str]:
    inp = inp if isinstance(inp, dict) else {}
    path = str(inp.get("file_path") or inp.get("path") or inp.get("notebook_path") or "")
    command = str(inp.get("command") or "")
    target = Path(path).name if path else (command.splitlines()[0][:80] if command else "")
    return {"path": path, "command": command, "target": target}


def _result_text(content: Any) -> str:
    if isinstance(content, list):
        return " ".join(str(b.get("text", "")) for b in content if isinstance(b, dict))
    return str(content or "")


def _tokens(message: Any) -> dict[str, int] | None:
    usage = message.get("usage") if isinstance(message, dict) else None
    if not isinstance(usage, dict):
        return None
    pick = lambda key: int(usage.get(key) or 0) if isinstance(usage.get(key), (int, float)) else 0  # noqa: E731
    return {"input": pick("input_tokens"), "output": pick("output_tokens"),
            "cache_read": pick("cache_read_input_tokens"), "cache_creation": pick("cache_creation_input_tokens")}


def _base(rec: dict[str, Any], role: str, kind: str, agent: str | None) -> dict[str, Any]:
    msg = rec.get("message")
    return {"ts": str(rec.get("timestamp") or ""), "role": role, "kind": kind, "tool": "", "args": {},
            "ok": None, "exit_code": None, "error": False, "agent_id": agent, "call_id": "", "text_snippet": "",
            "model": str(msg.get("model") or "") if isinstance(msg, dict) and role == "assistant" else "", "tokens": None}


def _normalize_block(block: Any, rec: dict[str, Any], role: str, agent: str | None, calls: dict[str, str]) -> dict[str, Any] | None:
    if not isinstance(block, dict):
        return None
    btype = block.get("type")
    if btype == "text" and block.get("text"):
        step = _base(rec, role, "text", agent)
        step["text_snippet"] = _snippet(block["text"])
        return step
    if btype == "tool_use":
        step = _base(rec, "assistant", "tool_call", agent)
        name = str(block.get("name") or "")
        step.update(tool=CANONICAL_TOOLS.get(name, name), args=_tool_args(block.get("input")), call_id=str(block.get("id") or ""))
        calls[step["call_id"]] = step["tool"]
        return step
    if btype == "tool_result":
        step = _base(rec, "tool_result", "tool_result", agent)
        text, err = _result_text(block.get("content")), block.get("is_error") is True
        match = _EXIT_RE.search(text)
        step.update(call_id=str(block.get("tool_use_id") or ""), error=err, ok=not err, text_snippet=_snippet(text),
                    exit_code=int(match.group(1)) if match else None)
        step["tool"] = calls.get(step["call_id"], "")
        return step
    return None


def _file_steps(path: Path, agent: str | None, start: int) -> Iterator[dict[str, Any]]:
    calls: dict[str, str] = {}
    idx = start
    for rec in iter_records(path):
        role = rec.get("type")
        if role not in ("user", "assistant"):
            continue
        tokens = _tokens(rec.get("message")) if role == "assistant" else None
        for block in _blocks(rec.get("message")):
            step = _normalize_block(block, rec, role, agent, calls)
            if step is None:
                continue
            step["idx"], step["tokens"], tokens, idx = idx, tokens, None, idx + 1
            yield step


def read_session(main: Path, include_subagents: bool = True) -> Iterator[dict[str, Any]]:
    """Yield normalized steps for the main log, then each subagent log (``agent_id`` set)."""
    idx = 0
    for agent, path in session_files(main) if include_subagents else [(None, main)]:
        for step in _file_steps(path, agent, idx):
            idx = step["idx"] + 1
            yield step
