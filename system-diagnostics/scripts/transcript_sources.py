#!/usr/bin/env python3
"""Vendor detection and session discovery for transcript audits (Claude Code and Antigravity).

Source-vendor precedence (decision D2): explicit ``--vendor`` > env ``TRANSCRIPT_VENDOR`` >
where the id is found > default ``gemini``. An id found under both roots is an error.
"""

import os
import re
from pathlib import Path

VENDORS = ("gemini", "claude")
MIN_CLAUDE_PREFIX = 8  # shorter tokens only match exactly, so they cannot collide with unrelated sessions
_GEMINI_LOG = Path(".system_generated") / "logs" / "transcript.jsonl"


class AmbiguousVendorError(ValueError):
    """The id exists under both the Claude projects dir and the Antigravity brain dir."""


def default_brain_dir() -> Path:
    """Antigravity brain dir: ``AGY_BRAIN_DIR`` else ``~/.gemini/antigravity/brain``."""
    env = os.getenv("AGY_BRAIN_DIR", "")
    return Path(env) if env else Path.home() / ".gemini" / "antigravity" / "brain"


def default_claude_dir() -> Path:
    """Claude projects dir: ``$CLAUDE_CONFIG_DIR/projects`` if set, else ``~/.claude/projects``."""
    env = os.getenv("CLAUDE_CONFIG_DIR", "")
    return (Path(env) if env else Path.home() / ".claude") / "projects"


def project_slug(workdir: str | Path) -> str:
    """Claude's project folder name: path separators, dots and drive colons become ``-``."""
    return re.sub(r"[\\/.:]", "-", str(workdir))


def _project_dirs(claude_dir: Path, project_dir: Path | None) -> list[Path]:
    if project_dir is not None:
        return [project_dir] if project_dir.is_dir() else []
    try:
        return sorted(d for d in claude_dir.iterdir() if d.is_dir())
    except OSError:
        return []


def find_claude_sessions(token: str, claude_dir: Path, project_dir: Path | None = None) -> list[Path]:
    """Return session files named ``token`` exactly, else those it prefixes (>= 8 chars, case-insensitive)."""
    low, exact, prefix = token.strip().lower(), [], []
    for proj in _project_dirs(claude_dir, project_dir):
        try:
            files = sorted(proj.glob("*.jsonl"))
        except OSError:
            continue
        exact += [f for f in files if f.stem.lower() == low]
        prefix += [f for f in files if len(low) >= MIN_CLAUDE_PREFIX and f.stem.lower().startswith(low)]
    return exact or prefix


def find_gemini_session(token: str, brain_dir: Path) -> Path | None:
    """Return the Antigravity transcript for an exact or prefix id, else ``None``."""
    direct = brain_dir / token / _GEMINI_LOG
    if direct.is_file():
        return direct
    low = token.strip().lower()
    try:
        names = sorted(d for d in brain_dir.iterdir() if d.is_dir())
    except OSError:
        return None
    return next((d / _GEMINI_LOG for d in names if low and d.name.lower().startswith(low) and (d / _GEMINI_LOG).is_file()), None)


def detect_vendor(token: str, explicit: str | None = None, brain_dir: Path | None = None,
                  claude_dir: Path | None = None, project_dir: Path | None = None) -> str:
    """Pick the source vendor for ``token`` per D2; raises ``AmbiguousVendorError`` on a clash."""
    for choice in (explicit, os.getenv("TRANSCRIPT_VENDOR", "")):
        if choice and choice != "auto":
            if choice not in VENDORS:
                raise ValueError(f"unknown vendor {choice!r}; expected one of {VENDORS} or auto")
            return choice
    in_claude = bool(find_claude_sessions(token, claude_dir or default_claude_dir(), project_dir))
    in_gemini = find_gemini_session(token, brain_dir or default_brain_dir()) is not None
    if in_claude and in_gemini:
        raise AmbiguousVendorError(f"id {token!r} exists under both roots; pass --vendor claude|gemini")
    return "claude" if in_claude else "gemini"


def current_session_id(vendor: str) -> str:
    """Id of the running session: ``CLAUDE_CODE_SESSION_ID`` under Claude; empty otherwise (never guessed)."""
    return os.getenv("CLAUDE_CODE_SESSION_ID", "") if vendor == "claude" else ""


def list_sessions(vendor: str, brain_dir: Path | None = None, claude_dir: Path | None = None,
                  project_dir: Path | None = None) -> list[tuple[str, Path]]:
    """List ``(session_id, log_path)`` for a vendor, newest first."""
    if vendor == "claude":
        found = [f for p in _project_dirs(claude_dir or default_claude_dir(), project_dir) for f in p.glob("*.jsonl")]
        ids = [(f.stem, f) for f in found]
    else:
        root = brain_dir or default_brain_dir()
        try:
            ids = [(d.name, d / _GEMINI_LOG) for d in root.iterdir() if (d / _GEMINI_LOG).is_file()]
        except OSError:
            ids = []
    return sorted(ids, key=lambda item: item[1].stat().st_mtime, reverse=True)
