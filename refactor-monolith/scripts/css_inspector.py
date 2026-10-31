#!/usr/bin/env python3
"""Cross-platform stylesheet inspector and specificity analyzer.

Provides zero-dependency CSS structural inspection, section banner detection,
@import resolution, and !important specificity auditing across files and directories.
Eliminates ad-hoc Python line-counting and regex scripts during stylesheet refactoring.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from surface_scanners import scan_css_surface

IGNORED_DIRS: frozenset[str] = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "dist", "build", "_build", "out", "target", ".idea", ".vscode",
    "scratch", "coverage", "htmlcov", "migrations", ".refactor",
})


def _is_vendor_or_minified(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith((".min.css", ".bundle.css")) or any(
        p in ("vendor", "node_modules", "dist") for p in path.parts
    )


def _inspect_single_css_file(file_path: Path, show_all: bool = False) -> tuple[int, dict[str, Any]]:
    """Audit a single CSS/SCSS file and print detailed structural metrics."""
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as err:
        print(f"Error reading {file_path}: {err}", file=sys.stderr)
        return 1, {}

    surf = scan_css_surface(text)
    line_count = len(text.splitlines())
    le_str = "CRLF (Windows \r\n)" if surf.has_crlf else "LF (POSIX \n)"

    print(f"=== Stylesheet Structural Inspection: {file_path.name} ===")
    print(f"Path:             {file_path.as_posix()}")
    print(f"Total Lines:      {line_count}")
    print(f"Line Endings:     {le_str}")
    print(f"@import Rules:    {len(surf.import_urls)}")
    for imp in surf.import_urls:
        print(f"  - @import url(\"{imp}\");")

    print(f"\nSection Banners:  {len(surf.section_banners)}")
    banners_to_show = surf.section_banners if show_all else surf.section_banners[:12]
    for b in banners_to_show:
        print(f"  - L{b['line']:<5} /* {b['title']} */")
    if not show_all and len(surf.section_banners) > 12:
        print(f"  ... and {len(surf.section_banners) - 12} more (use --all to show all)")

    print(f"\nCustom Properties: {len(surf.custom_properties)}")
    vars_preview = surf.custom_properties[:8]
    if vars_preview:
        print(f"  Sample: {', '.join(vars_preview)}{' ...' if len(surf.custom_properties) > 8 else ''}")

    print(f"Keyframes:        {len(surf.keyframes)}")
    print(f":fullscreen Rules:{len(surf.fullscreen_rules)}")
    print(f"!important Count: {surf.important_count}")

    if surf.important_occurrences:
        print("\n[CRITICAL SPECIFICITY] !important Occurrences:")
        for occ in surf.important_occurrences:
            print(f"  L{occ['line']:<5} | {occ['content']}")

    return 0, {
        "file": file_path.name,
        "lines": line_count,
        "crlf": surf.has_crlf,
        "imports": len(surf.import_urls),
        "important": surf.important_count,
    }


def _inspect_css_directory(dir_path: Path, show_all: bool = False) -> tuple[int, list[dict[str, Any]]]:
    """Audit all CSS/SCSS files in a directory and print summary table."""
    css_files = [
        p for p in dir_path.rglob("*")
        if p.is_file() and p.suffix.lower() in {".css", ".scss"}
        and not any(part in IGNORED_DIRS for part in p.parts)
        and not _is_vendor_or_minified(p)
    ]
    if not css_files:
        print(f"No CSS/SCSS stylesheets found in {dir_path.as_posix()}")
        return 0, []

    summaries = []
    total_important = 0
    total_lines = 0

    print(f"=== Stylesheet Modularity & Specificity Audit ({len(css_files)} files) ===")
    print(f"{'Stylesheet':<34} {'Lines':>6}  {'Endings':<6}  {'Imports':>7}  {'!important':>10}")
    print("-" * 74)

    for f in sorted(css_files):
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        surf = scan_css_surface(txt)
        lines = len(txt.splitlines())
        total_lines += lines
        total_important += surf.important_count
        le = "CRLF" if surf.has_crlf else "LF"
        rel_p = f.relative_to(dir_path).as_posix()
        imp_status = f"{surf.important_count} (!)" if surf.important_count > 0 else "0"
        print(f"{rel_p:<34} {lines:>6}  {le:<6}  {len(surf.import_urls):>7}  {imp_status:>10}")
        summaries.append({
            "path": rel_p,
            "lines": lines,
            "crlf": surf.has_crlf,
            "imports": len(surf.import_urls),
            "important": surf.important_count,
            "occurrences": surf.important_occurrences,
        })

    print("-" * 74)
    print(f"{'Total':<34} {total_lines:>6}         {sum(s['imports'] for s in summaries):>7}  {total_important:>10}")

    breached = [s for s in summaries if s["important"] > 0]
    if breached:
        print(f"\n[CRITICAL SPECIFICITY] {len(breached)} stylesheet(s) contain !important:")
        for b in breached:
            for occ in b["occurrences"]:
                print(f"  {b['path']}:L{occ['line']} | {occ['content']}")

    return (1 if total_important > 0 else 0), summaries


def cmd_inspect_css(target: Path, show_all: bool = False, strict: bool = False) -> int:
    """CLI handler for inspect-css subcommand."""
    t = target.resolve()
    if not t.exists():
        print(f"Error: path does not exist: {target}", file=sys.stderr)
        return 2

    if t.is_file():
        code, summary = _inspect_single_css_file(t, show_all)
        if code != 0:
            return code
        return 1 if (strict and summary.get("important", 0) > 0) else 0

    code, _ = _inspect_css_directory(t, show_all)
    return 1 if (strict and code != 0) else 0
