#!/usr/bin/env python3
"""Transcript telemetry access for plan digests/retrospectives, routed by vendor (Antigravity or Claude).

Extracted from ``plan_digest.py`` (which re-exports these names, so existing imports and patches keep
working). Needs the sibling ``system-diagnostics`` scripts; returns ``None``/empty in standalone mode.
Antigravity ids behave exactly as before; Claude session ids (full or 8+ char prefix) are resolved by
``transcript_router`` (decision D2: explicit ``TRANSCRIPT_VENDOR`` > where the id is found > gemini).
"""

from pathlib import Path
from typing import Any
import sys

_SCRIPTS_DIR = Path(__file__).resolve().parent
_LOG_REL = Path(".system_generated") / "logs" / "transcript.jsonl"


def _load_auditor(brain_dir: str | None = None) -> tuple[Any, Path] | None:
    """Load transcript_auditor and resolved brain dir, else None in standalone mode."""
    sibling = _SCRIPTS_DIR.parent.parent / "system-diagnostics" / "scripts"
    for candidate in (_SCRIPTS_DIR, sibling):
        if (candidate / "transcript_auditor.py").is_file():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            import transcript_auditor
            return transcript_auditor, (Path(brain_dir) if brain_dir else transcript_auditor.default_brain_dir())
    return None


def _claude_session_id(cid: str) -> str | None:
    """Full id when ``cid`` names exactly one Claude session (needs the system-diagnostics scripts)."""
    try:
        from transcript_sources import default_claude_dir, find_claude_sessions
    except ImportError:
        return None
    hits = find_claude_sessions(cid, default_claude_dir())
    return hits[0].stem if len(hits) == 1 else None


def _resolve_one_cid(brain: Path, cid: str) -> str:
    """Resolve an exact or unique prefix id: Antigravity (6+ chars) in ``brain``, else Claude (8+ chars)."""
    if (brain / cid / _LOG_REL).is_file():
        return cid
    low = cid.lower()
    hits = [d.name for d in brain.iterdir() if d.is_dir() and d.name.lower().startswith(low) and (d / _LOG_REL).is_file()] if len(cid) >= 6 and brain.is_dir() else []
    return hits[0] if len(hits) == 1 else (_claude_session_id(cid) or cid)


def vendor_audit(ta: Any, brain: Path, cid: str) -> dict[str, Any]:
    """Audit one resolved id for either vendor; an ambiguous vendor yields a labeled missing row."""
    try:
        from transcript_router import audit
        return audit(cid, "auto", brain)
    except ImportError:
        return ta.audit_conversation(brain, cid)
    except ValueError as exc:
        return {"cid": cid, "missing": True, "error": str(exc)}


def audit_single_cid(cid: str, brain_dir: str | None = None) -> dict[str, Any] | None:
    """Audit one session ID (exact or unique prefix), or None if unavailable/missing."""
    loaded = _load_auditor(brain_dir)
    if not loaded:
        return None
    row = vendor_audit(loaded[0], loaded[1], _resolve_one_cid(loaded[1], cid))
    return None if not row or row.get("missing") else row


def _dedupe_cids(cids: list[str], brain: Path | None = None) -> list[str]:
    """Resolve and deduplicate CIDs case-insensitively, dropping >=6-char prefixes of longer CIDs."""
    res = [_resolve_one_cid(brain, str(c).strip()) if brain else str(c).strip() for c in cids if c and str(c).strip()]
    kept = [c for c in res if not any(len(c) >= 6 and o.lower() != c.lower() and o.lower().startswith(c.lower()) for o in res)]
    return list({c.lower(): c for c in reversed(kept)}.values())[::-1]


def _transcript_rows(cids: list[str] | None, brain_dir: str | None) -> list[dict[str, Any]] | None:
    """Optional telemetry; returns None when system-diagnostics is unavailable (standalone mode)."""
    if not cids:
        return []
    loaded = _load_auditor(brain_dir)
    if not loaded:
        return None
    return [vendor_audit(loaded[0], loaded[1], c) for c in _dedupe_cids(cids, loaded[1])]
