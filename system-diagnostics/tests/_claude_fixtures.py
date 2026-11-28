"""Synthetic Claude Code session builders shared by the transcript tests (no real transcripts)."""

import json
from pathlib import Path


def rec(kind: str, *blocks: dict, ts: str = "2026-11-26T10:00:00Z", model: str = "", usage: dict | None = None) -> dict:
    msg: dict = {"content": list(blocks)}
    if model:
        msg["model"] = model
    if usage:
        msg["usage"] = usage
    return {"type": kind, "sessionId": "s", "timestamp": ts, "message": msg}


def text(value: str) -> dict:
    return {"type": "text", "text": value}


def use(tid: str, name: str, **inp: str) -> dict:
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}


def result(tid: str, content: str, error: bool = False) -> dict:
    block = {"type": "tool_result", "tool_use_id": tid, "content": content}
    return {**block, "is_error": True} if error else block


def write_jsonl(path: Path, records: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(r if isinstance(r, str) else json.dumps(r) for r in records) + "\n", encoding="utf-8")


def session(claude_dir: Path, sid: str, records: list, slug: str = "-proj", subagents: dict | None = None) -> Path:
    main = claude_dir / slug / f"{sid}.jsonl"
    write_jsonl(main, records)
    for agent, recs in (subagents or {}).items():
        write_jsonl(claude_dir / slug / sid / "subagents" / f"agent-{agent}.jsonl", recs)
    return main
