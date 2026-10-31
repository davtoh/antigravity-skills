#!/usr/bin/env python3
"""Cross-platform reporting, section inspection, and split-preview formatters for code_health_audit.

Decoupled from AST/brace parsing to respect quantitative modularity budgets.
Supports line ending (CRLF vs LF) detection and structural section outlines.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from code_health_audit import AuditThresholds, FileReport


def print_by_dir_summary(reports: list[FileReport], thresholds: AuditThresholds) -> None:
    """Print directory-level aggregated summary of files, lines, and breaches."""
    dir_groups: dict[str, list[FileReport]] = defaultdict(list)
    for r in reports:
        p = Path(r.rel_path).parent.as_posix()
        dir_groups[p if p else "."].append(r)
    print(f"{'Directory / Subsystem':<38} {'Files':>6} {'Total Lines':>12}  {'Status'}\n" + "-" * 78)
    for d_name in sorted(dir_groups.keys()):
        group = dir_groups[d_name]
        total_l = sum(r.lines for r in group)
        crit = sum(1 for r in group if r.status == "CRITICAL")
        warn = sum(1 for r in group if r.status == "WARNING")
        status = f"{crit} Critical, {warn} Warn" if crit or warn else "OK (All within budget)"
        print(f"{d_name:<38} {len(group):>6} {total_l:>11,}L  {status}")


def print_text_summary(
    reports: list[FileReport], thresholds: AuditThresholds, top_n: int,
    show_methods: bool, compact: bool = False, by_dir: bool = False,
    mode: str = "SINGLE_FILE"
) -> None:
    """Format and print a human-readable modularity audit table."""
    ranked = sorted(reports, key=lambda r: r.lines, reverse=True)
    crit = sum(1 for r in reports if r.status == "CRITICAL")
    warn = sum(1 for r in reports if r.status == "WARNING")
    print(f"=== Modularity Audit ({len(reports)} files | Critical: {crit} | Warning: {warn}) ===")
    print(
        f"Budgets: File <= {thresholds.warn_file_lines}/{thresholds.max_file_lines}L | "
        f"Class <= {thresholds.warn_class_methods}/{thresholds.max_class_methods}M | "
        f"Func <= {thresholds.max_func_lines}L | Recommended Mode: {mode}\n"
    )
    if by_dir:
        print_by_dir_summary(reports, thresholds)
        return
    print(f"{'Status':<10} {'Lines':>7}  {'Parser':<10} {'Path'}\n" + "-" * 78)
    for rep in ranked[:top_n]:
        print(f"{rep.status:<10} {rep.lines:>7}  {rep.parser_mode:<10} {rep.rel_path}")
        if not compact:
            _print_file_details(rep, show_methods)


def _print_file_details(rep: FileReport, show_methods: bool) -> None:
    """Print class and function breach details for a single file report."""
    cls_list = rep.classes if show_methods else [c for c in rep.classes if c.status != "OK"][:4]
    for cls in cls_list:
        print(
            f"   [Class {cls.status}] {cls.name} "
            f"(L{cls.start_line}-L{cls.end_line}, {cls.lines}L, {cls.method_count} items)"
        )
        if show_methods and cls.methods:
            preview = ", ".join(cls.methods[:12])
            print(f"      Items: {preview}{' ...' if len(cls.methods) > 12 else ''}")
    fn_limit = 12 if show_methods else 4
    for fn in rep.oversized_functions[:fn_limit]:
        if show_methods or fn.status == "CRITICAL":
            print(f"   [Func  {fn.status}] {fn.qualname} (L{fn.start_line}-L{fn.end_line}, {fn.lines}L)")


def _parse_split_spec(spec: str) -> tuple[Path, str, int] | None:
    """Parse spec into (file_path, line_s, window). Supports Windows drive letters."""
    if len(spec) > 2 and spec[1] == ":" and spec[0].isalpha():
        rparts = spec[2:].rsplit(":", 2)
        if len(rparts) < 2:
            return None
        return Path(spec[:2] + rparts[0]), rparts[1], int(rparts[2]) if len(rparts) > 2 else 12
    parts = spec.rsplit(":", 2)
    if len(parts) < 2:
        return None
    return Path(parts[0]), parts[1], int(parts[2]) if len(parts) > 2 else 12


def preview_split(spec: str) -> int:
    """Safely print source lines around a proposed split line (path:line[:window])."""
    parsed = _parse_split_spec(spec)
    if not parsed:
        print("Usage: --split-preview <file_path>:<line_number>[:window_lines]", file=sys.stderr)
        return 2
    fpath, line_s, window = parsed

    if not fpath.exists():
        print(f"Error: file not found: {fpath}", file=sys.stderr)
        return 2
    try:
        lineno = int(line_s)
        raw_bytes = fpath.read_bytes()
        has_crlf = b"\r\n" in raw_bytes
        lines = raw_bytes.decode("utf-8", errors="replace").splitlines()
    except Exception as err:
        print(f"Error reading {fpath}: {err}", file=sys.stderr)
        return 2

    start = max(0, lineno - window - 1)
    end = min(len(lines), lineno + window)
    le_desc = "CRLF (Windows \r\n)" if has_crlf else "LF (POSIX \n)"
    print(f"=== Split Preview: {fpath.name} around line {lineno} (L{start+1}-L{end}) ===")
    print(f"Line Endings: {le_desc}")
    if has_crlf:
        print("[CRLF TIP] File uses Windows CRLF line endings. Preserve \r\n or use write_file to avoid edit_file mismatch.")

    for idx in range(start, end):
        cur = idx + 1
        marker = "==> [SPLIT POINT]" if cur == lineno else "   "
        print(f"{marker} {cur:>5} | {lines[idx]}")
    return 0


_BANNER_COMMENT_RE = re.compile(
    r'^\s*(?:/\*+|#+|//+)\s*(?:[=\-_*#~]{3,}\s*)?([A-Za-z0-9][A-Za-z0-9\s.,&/\(\)\'\"\-]{2,60}?)(?:\s*[=\-_*#~]{3,})?(?:\*+/)?\s*$'
)


def _extract_line_sections(lines: list[str]) -> list[tuple[int, str, str]]:
    """Scan lines for comment banners, class definitions, and function declarations."""
    found_sections = []
    for idx, line in enumerate(lines, start=1):
        m_banner = _BANNER_COMMENT_RE.match(line)
        if m_banner:
            title = m_banner.group(1).strip()
            if not title.startswith(("!", "TODO", "FIXME", "eslint", "stylelint", "http", "type:")):
                found_sections.append((idx, "Banner", title))
                continue
        if re.match(r'^\s*(?:export\s+)?class\s+([A-Za-z0-9_]+)', line):
            m_cls = re.match(r'^\s*(?:export\s+)?class\s+([A-Za-z0-9_]+)', line)
            found_sections.append((idx, "Class", m_cls.group(1)))
        elif re.match(r'^(?:async\s+)?def\s+([A-Za-z0-9_]+)', line):
            m_fn = re.match(r'^(?:async\s+)?def\s+([A-Za-z0-9_]+)', line)
            found_sections.append((idx, "Function", m_fn.group(1)))
    return found_sections


def inspect_sections(file_path_str: str) -> int:
    """Outline structural sections, classes, and major comment banners of a file."""
    fpath = Path(file_path_str).resolve()
    if not fpath.exists() or not fpath.is_file():
        print(f"Error: file not found: {file_path_str}", file=sys.stderr)
        return 2

    try:
        raw_bytes = fpath.read_bytes()
        has_crlf = b"\r\n" in raw_bytes
        lines = raw_bytes.decode("utf-8", errors="replace").splitlines()
    except Exception as err:
        print(f"Error reading {fpath}: {err}", file=sys.stderr)
        return 2

    le_str = "CRLF (Windows \r\n)" if has_crlf else "LF (POSIX \n)"
    print(f"=== File Structural Outline: {fpath.name} ({len(lines)} lines | {le_str}) ===")

    found_sections = _extract_line_sections(lines)
    if not found_sections:
        print("No section banners or top-level declarations detected.")
        return 0

    print(f"{'Line':<8} {'Type':<12} {'Identifier / Title'}")
    print("-" * 65)
    for ln, stype, title in found_sections:
        print(f"L{ln:<7} {stype:<12} {title}")
    return 0
