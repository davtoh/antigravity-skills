#!/usr/bin/env python3
"""Archive discovery, changelog parsing, and entry-boundary rotation helpers."""

import datetime
import re
from pathlib import Path

AI_GUARD_BANNER = (
    "<!-- AI AGENT NOTICE: Historical archive only. "
    "DO NOT read this file unless explicitly asked to research past migrations. -->\n\n"
)


def _discover_existing_archive(root: Path) -> Path | None:
    """Search standard root and docs/archive subdirectories for an existing archive folder."""
    if (root / ".changelogs").is_dir():
        return root / ".changelogs"
    for cand in ("archive/changelogs", "archive/changelog", "changelogs", ".changelog"):
        if (root / cand).is_dir():
            return root / cand
    for depth in (1, 2):
        for pat in ("*/archive/changelogs", "*/changelogs", "*/archive/changelog"):
            for match in root.glob("*/" * (depth - 1) + pat):
                if match.is_dir():
                    return match
    for parent in ("docs", "archive", "doc"):
        p_dir = root / parent
        if p_dir.is_dir():
            for sub in p_dir.iterdir() if p_dir.is_dir() else ():
                if sub.is_dir() and "changelog" in sub.name.lower():
                    return sub
    return None


def resolve_archive_dir(root: Path, custom_archive: str | None = None) -> Path:
    """Discover or create archive directory according to multi-tier discovery."""
    if custom_archive:
        custom_p = Path(custom_archive)
        target = custom_p if custom_p.is_absolute() else (root / custom_p)
        target.mkdir(parents=True, exist_ok=True)
        return target
    if found := _discover_existing_archive(root):
        return found
    p1 = root / ".changelogs"
    p1.mkdir(parents=True, exist_ok=True)
    gi = p1 / ".gitignore"
    if not gi.exists():
        gi.write_text("*\n", encoding="utf-8")
    return p1


class ChangelogEntry:
    """Structured representation of a single changelog milestone entry."""

    def __init__(self, header: str, body: list[str], raw_text: str | None = None):
        self.header = header.strip()
        self.body = [line.rstrip() for line in body]
        self.raw_text = raw_text or (self.header + "\n" + "\n".join(self.body) + "\n")
        m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", self.header)
        now = datetime.datetime.now(datetime.timezone.utc)
        self.year = int(m.group(1)) if m else now.year
        self.month = int(m.group(2)) if m else now.month
        self.half = "H1" if self.month <= 6 else "H2"

    def compact(self, max_body_lines: int = 15) -> str:
        """Compact verbose entries (>= 25 lines) down to <= 15 lines."""
        if len(self.body) < 25:
            return self.header + "\n" + "\n".join(self.body) + "\n"
        keep, file_count, in_f = [], 0, False
        for line in self.body:
            if re.match(r"^-\s+\*\*(Type|Summary|Verification)\*\*:", line):
                in_f = False
                keep.append(line)
            elif re.match(r"^-\s+\*\*Files\*\*:", line) or line.strip() == "### Files:":
                in_f = True
                keep.append(line)
            elif in_f and line.strip().startswith("- "):
                file_count += 1
                if file_count <= 4:
                    keep.append(line)
                elif file_count == 5:
                    keep.append("  - ... (+more modified files)")
            elif len(keep) < max_body_lines - 1:
                keep.append(line)
        return self.header + "\n" + "\n".join(keep) + "\n"


def parse_changelog(content: str) -> tuple[str, list[ChangelogEntry]]:
    """Parse markdown changelog into prologue and list of structured entries."""
    prologue_lines, entries, cur_h, cur_b = [], [], None, []
    for line in content.splitlines():
        if line.startswith("## "):
            if cur_h is not None:
                entries.append(ChangelogEntry(cur_h, cur_b))
            cur_h, cur_b = line, []
        elif cur_h is None:
            prologue_lines.append(line)
        else:
            cur_b.append(line)
        # cur_b grows until next entry header
    if cur_h is not None:
        entries.append(ChangelogEntry(cur_h, cur_b))
    prologue = "\n".join(prologue_lines).strip()
    return (prologue + "\n\n" if prologue else "# Changelog\n\n"), entries


def _write_archive_shard(archive_dir: Path, year: int, half: str, entries: list[ChangelogEntry]) -> Path:
    shard = archive_dir / f"changelog_{year}_{half}.md"
    existing = shard.read_text(encoding="utf-8") if shard.exists() else ""
    body = "\n\n".join(e.raw_text.strip() for e in entries) + "\n"
    if not existing:
        shard.write_text(f"{AI_GUARD_BANNER}# Historical Changelog Archive ({year} {half})\n\n{body}", encoding="utf-8")
    else:
        shard.write_text(existing.rstrip() + "\n\n" + body, encoding="utf-8")
    return shard


def rotate_entries(
    prologue: str, entries: list[ChangelogEntry], archive_dir: Path, max_lines: int = 150, min_entries: int = 3
) -> tuple[str, list[Path]]:
    """Keep recent entries <= max_lines (min 3 entries), rotate overflow to shard."""
    if not entries:
        return prologue, []
    seen, unique = set(), []
    for e in entries:
        if e.header not in seen:
            seen.add(e.header)
            unique.append(e)
    active, overflow, curr_lines = [], [], len(prologue.splitlines())
    for idx, e in enumerate(unique):
        e_lines = len(e.compact().splitlines())
        if idx < min_entries or (curr_lines + e_lines <= max_lines):
            active.append(e)
            curr_lines += e_lines
        else:
            overflow.append(e)
    shards_written = []
    if overflow:
        groups: dict[tuple[int, str], list[ChangelogEntry]] = {}
        for oe in overflow:
            groups.setdefault((oe.year, oe.half), []).append(oe)
        for (y, h), grp in groups.items():
            shards_written.append(_write_archive_shard(archive_dir, y, h, grp))
    return prologue + "\n\n".join(e.compact().strip() for e in active) + "\n", shards_written
