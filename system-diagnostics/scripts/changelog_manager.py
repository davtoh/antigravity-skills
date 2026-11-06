#!/usr/bin/env python3
"""Unified Changelog & Auto-Archiving Engine (diagnose.py changelog).
Zero-token changelog management, declarative regex sanitization, smart archive
discovery, entry-boundary window rotation (<= 150 lines), and commit emission.
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

AI_GUARD_BANNER = (
    "<!-- AI AGENT NOTICE: Historical archive only. "
    "DO NOT read this file unless explicitly asked to research past migrations. -->\n\n"
)

def _to_repo_relative(val: str, repo_root: Path) -> str:
    clean = re.sub(r"^file:///[A-Za-z]:", lambda m: m.group(0)[-2:], val)
    clean = re.sub(r"^file:///", "/", clean)
    frag = ("#" + clean.split("#", 1)[1]) if "#" in clean else ""
    clean = clean.split("#", 1)[0]
    try:
        p, r = Path(clean).resolve(), repo_root.resolve()
        if p.is_relative_to(r):
            return p.relative_to(r).as_posix() + frag
    except Exception:
        pass
    return Path(clean).name + frag if Path(clean).suffix else "<local_path>"

def _sanitize_user_path(val: str, repo_root: Path) -> str:
    try:
        p, r = Path(val).resolve(), repo_root.resolve()
        if p.is_relative_to(r):
            return p.relative_to(r).as_posix()
    except Exception:
        pass
    return "<local_path>"

SANITIZATION_RULES: dict[str, tuple[str, Any]] = {
    "file_uri_windows": (r"file:///[A-Za-z]:/[^\s\)\"`]+", _to_repo_relative),
    "file_uri_posix": (r"file:///[^\s\)\"`]+", _to_repo_relative),
    "venv_windows": (r"(?:\.\\|\./)?\.?venv\\Scripts\\python(?:\.exe)?", "python"),
    "venv_posix": (r"(?:\./)?\.?venv/bin/python(?:3(?:\.\d+)?)?", "python"),
    "localhost_url": (r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0)(?::\d+)?(?=/|\b)", "$APP_URL"),
    "windows_user_path": (r"[A-Za-z]:\\Users\\[^\\]+\\[^\s\)\"`]+", _sanitize_user_path),
    "posix_user_path": (r"/(?:Users|home)/[^/]+/[^\s\)\"`]+", _sanitize_user_path),
}

def sanitize_text(text: str, repo_root: Path) -> str:
    res = text
    for _, (pattern, repl) in SANITIZATION_RULES.items():
        if callable(repl):
            res = re.sub(pattern, lambda m: repl(m.group(0), repo_root), res)
        else:
            res = re.sub(pattern, repl, res)
    return res

def resolve_archive_dir(root: Path) -> Path:
    """Discover or create archive directory according to 3-tier priority."""
    p1 = root / ".changelogs"
    if p1.is_dir():
        return p1
    for depth in (1, 2):
        for c in root.glob("*/" * depth + "archive/changelogs"):
            if c.is_dir():
                return c
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
            is_tag = bool(re.match(r"^-\s+\*\*(Type|Summary|Verification)\*\*:", line))
            if is_tag:
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

def _get_git_modified_files(root: Path) -> tuple[list[str], bool]:
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3.0
        )
        if res.returncode == 0:
            files = [line[3:].strip() for line in res.stdout.splitlines() if len(line) > 3]
            return files, True
        return [], False
    except Exception:
        return [], False

def _build_entry(root: Path, c_type: str, c_title: str, c_summary: str, files: list[str], verify: str) -> ChangelogEntry:
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    header = f"## [{now_iso}] {c_type}: {c_title}"
    body = [f"- **Type**: {c_type}"]
    if c_summary:
        body.append(f"- **Summary**: {c_summary}")
    if files:
        body.append(f"- **Files** ({len(files)}):")
        for f in files[:8]:
            body.append(f"  - `{f}`")
        if len(files) > 8:
            body.append(f"  - ... (+{len(files) - 8} more)")
    if verify:
        body.append(f"- **Verification**: {verify}")
    return ChangelogEntry(header, body)

def _emit_commit_hint(c_type: str, c_title: str, c_summary: str, files: list[str], is_git: bool = True) -> None:
    msg = f"{c_type}: {c_title}"
    print("\n=== Suggested Git Commit ===")
    if not is_git:
        print("# Notice: Git uninitialized. Run 'git init' first if versioning:\ngit init")
    if c_summary:
        print(f'git commit -m "{msg}" -m "{c_summary}"')
    else:
        print(f'git commit -m "{msg}"')
    if files:
        print(f"# Files ({len(files)}): {', '.join(files[:5])}" + ("..." if len(files) > 5 else ""))
    print("============================\n")

def migrate_logs(root: Path, src_name: str, tgt_name: str, max_lines: int = 150) -> tuple[bool, str]:
    """Migrate legacy log to target log with identity guard and safe merge."""
    src_p, tgt_p = (root / src_name).resolve(), (root / tgt_name).resolve()
    if not src_p.exists():
        if not tgt_p.exists():
            return False, f"Source log '{src_name}' does not exist."
        p, e = parse_changelog(tgt_p.read_text(encoding="utf-8"))
        c, _ = rotate_entries(p, e, resolve_archive_dir(root), max_lines=max_lines)
        tgt_p.write_text(c, encoding="utf-8")
        return True, f"Target log '{tgt_name}' rotated in-place."

    if src_p == tgt_p:
        p, e = parse_changelog(src_p.read_text(encoding="utf-8"))
        c, _ = rotate_entries(p, e, resolve_archive_dir(root), max_lines=max_lines)
        src_p.write_text(c, encoding="utf-8")
        return True, f"Same-path guard: rotated '{src_name}' in-place."

    _, src_e = parse_changelog(sanitize_text(src_p.read_text(encoding="utf-8"), root))
    p, tgt_e = parse_changelog(sanitize_text(tgt_p.read_text(encoding="utf-8"), root)) if tgt_p.exists() else ("# Changelog\n\n", [])
    final_content, shards = rotate_entries(p, tgt_e + src_e, resolve_archive_dir(root), max_lines=max_lines)
    tgt_p.write_text(final_content, encoding="utf-8")
    try:
        src_p.unlink()
        msg = f"Migrated {len(src_e)} entries from '{src_name}' -> '{tgt_name}'."
        return True, msg + (f" Archived {len(shards)} shard(s)." if shards else "")
    except Exception as ex:
        return True, f"Merged into '{tgt_name}', could not unlink '{src_name}': {ex}"

def cmd_changelog_add(args: argparse.Namespace) -> int:
    """Record a milestone, auto-rotate, and emit single-generation commit hint."""
    root = Path(args.path or ".").resolve()
    tgt_name, src_name = args.target_log or "CHANGELOG.md", args.source_log or "MIGRATION_LOG.md"
    if (root / src_name).exists() and (root / src_name).resolve() != (root / tgt_name).resolve():
        migrate_logs(root, src_name, tgt_name, max_lines=args.max_lines)

    tgt_file = root / tgt_name
    prologue, entries = parse_changelog(tgt_file.read_text(encoding="utf-8")) if tgt_file.exists() else ("# Changelog\n\n", [])
    c_type = sanitize_text(args.type or "refactor", root).strip()
    c_title = sanitize_text(args.title or "Milestone Update", root).strip()
    c_summary = sanitize_text(args.summary or "", root).strip()
    is_git = True
    if args.files:
        raw_files = args.files
    else:
        raw_files, is_git = _get_git_modified_files(root)
    clean_files = [sanitize_text(f, root).strip() for f in raw_files]

    entry = _build_entry(root, c_type, c_title, c_summary, clean_files, sanitize_text(args.verify or "", root).strip())
    final_c, shards = rotate_entries(prologue, [entry] + entries, resolve_archive_dir(root), max_lines=args.max_lines)
    tgt_file.write_text(final_c, encoding="utf-8")

    print(f"[changelog add] Added entry to {tgt_name} ({len(final_c.splitlines())} lines).")
    if shards:
        print(f"[changelog add] Overflow rotated to archive: {', '.join(s.name for s in shards)}")
    if getattr(args, "commit_hint", True):
        _emit_commit_hint(c_type, c_title, c_summary, clean_files, is_git=is_git)
    return 0

def cmd_changelog_migrate(args: argparse.Namespace) -> int:
    root = Path(args.path or ".").resolve()
    ok, msg = migrate_logs(root, args.source_log or "MIGRATION_LOG.md", args.target_log or "CHANGELOG.md", max_lines=args.max_lines)
    print(f"[changelog migrate] {msg}")
    return 0 if ok else 1

def cmd_changelog_show(args: argparse.Namespace) -> int:
    root = Path(args.path or ".").resolve()
    tgt = root / (args.target_log or "CHANGELOG.md")
    if not tgt.exists():
        print(f"[changelog show] No changelog found at {tgt}", file=sys.stderr)
        return 1
    _, entries = parse_changelog(tgt.read_text(encoding="utf-8"))
    recent = entries[: args.recent]
    if getattr(args, "json", False):
        print(json.dumps([{"header": e.header, "body": e.body, "year": e.year, "half": e.half} for e in recent], indent=2))
    else:
        print(f"=== Recent Changelog Entries ({len(recent)}) ===")
        for e in recent:
            print(e.compact().strip() + "\n")
    return 0

def cmd_changelog_status(args: argparse.Namespace) -> int:
    root = Path(args.path or ".").resolve()
    tgt, src = root / (args.target_log or "CHANGELOG.md"), root / (args.source_log or "MIGRATION_LOG.md")
    arch = resolve_archive_dir(root)
    shards = list(arch.glob("changelog_*.md"))
    tl = len(tgt.read_text(encoding="utf-8").splitlines()) if tgt.exists() else 0
    sl = len(src.read_text(encoding="utf-8").splitlines()) if src.exists() else 0
    arch_rel = str(arch.relative_to(root) if arch.is_relative_to(root) else arch)
    if getattr(args, "json", False):
        print(json.dumps({"target": {"name": tgt.name, "lines": tl}, "source": {"name": src.name, "lines": sl}, "archive": arch_rel, "shards": [s.name for s in shards]}, indent=2))
    else:
        print(f"=== Changelog Status ({root.name}) ===")
        print(f"Target Log:   {tgt.name} ({tl} lines, {'exists' if tgt.exists() else 'missing'})")
        print(f"Legacy Log:   {src.name} ({sl} lines, {'present' if src.exists() else 'none'})")
        print(f"Archive Dir:  {arch_rel} ({len(shards)} shards)")
    return 0

def _add_common_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--path", default=None, help="Repository root path")
    parser.add_argument("--source-log", default="MIGRATION_LOG.md", help="Legacy source log filename")
    parser.add_argument("--target-log", default="CHANGELOG.md", help="Target active log filename")

def register_parser(sub: Any) -> None:
    """Register 'changelog' subparser and its child actions."""
    acts = sub.add_parser("changelog", help="Manage bounded changelog, auto-archiving, and commit hints").add_subparsers(dest="action", help="Changelog action")

    p_add = acts.add_parser("add", help="Record a milestone and emit commit hint")
    _add_common_flags(p_add)
    p_add.add_argument("--type", default="refactor", help="Change type (refactor, feat, fix, etc.)")
    p_add.add_argument("--title", required=True, help="Milestone title")
    p_add.add_argument("--summary", default="", help="Summary description")
    p_add.add_argument("--files", nargs="*", default=None, help="Modified files")
    p_add.add_argument("--verify", default="", help="Verification evidence string")
    p_add.add_argument("--max-lines", type=int, default=150, help="Max line ceiling for active log")
    p_add.add_argument("--no-commit-hint", dest="commit_hint", action="store_false", default=True, help="Omit commit hint")

    p_mig = acts.add_parser("migrate", help="Migrate legacy log to bounded changelog and shards")
    _add_common_flags(p_mig)
    p_mig.add_argument("--max-lines", type=int, default=150, help="Max line ceiling")

    p_show = acts.add_parser("show", help="Display recent changelog entries")
    p_show.add_argument("--path", default=None, help="Repository root path")
    p_show.add_argument("--target-log", default="CHANGELOG.md", help="Target log filename")
    p_show.add_argument("--recent", type=int, default=3, help="Number of entries to show")
    p_show.add_argument("--json", action="store_true", help="Output JSON format")

    p_stat = acts.add_parser("status", help="Display changelog health and archive status")
    _add_common_flags(p_stat)
    p_stat.add_argument("--json", action="store_true", help="Output JSON format")

def cmd_changelog(args: argparse.Namespace) -> int:
    """CLI dispatcher for changelog commands."""
    action = getattr(args, "action", None)
    dispatch = {"add": cmd_changelog_add, "migrate": cmd_changelog_migrate, "show": cmd_changelog_show, "status": cmd_changelog_status}
    handler = dispatch.get(action) if action else None
    if not handler:
        print("Usage: diagnose.py changelog {add,migrate,show,status} ...", file=sys.stderr)
        return 2
    return handler(args)
