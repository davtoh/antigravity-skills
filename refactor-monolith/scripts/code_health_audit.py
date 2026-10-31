#!/usr/bin/env python3
"""Cross-platform, zero-dependency modularity and AST code health auditor.

Scans source files across Python, JavaScript/TypeScript, CSS/SCSS, Dart, Go,
Rust, C#, and fallback languages while pruning third-party vendor/minified
assets to enforce quantitative modularity budgets.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from language_analyzers import (  # noqa: E402
    BRACE_EXTENSIONS,
    STYLE_EXTENSIONS,
    RawSymbol,
    analyze_brace_language,
    analyze_generic_fallback,
    analyze_stylesheet,
    is_vendor_or_generated,
)

SUPPORTED_EXTENSIONS: frozenset[str] = (
    frozenset({".py"}) | BRACE_EXTENSIONS | STYLE_EXTENSIONS
)

IGNORED_DIRS: frozenset[str] = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "dist", "build", "_build", "out", "target", ".idea", ".vscode",
    "scratch", "coverage", "htmlcov", "migrations", ".refactor",
})


@dataclass(frozen=True)
class AuditThresholds:
    """Quantitative modularity thresholds for files, classes, and functions."""
    warn_file_lines: int = 350
    max_file_lines: int = 500
    warn_class_methods: int = 10
    max_class_methods: int = 12
    max_func_lines: int = 40


@dataclass
class FunctionMetric:
    """Line span and status for a single function, method, or rule block."""
    name: str
    qualname: str
    start_line: int
    end_line: int
    lines: int
    status: str


@dataclass
class ClassMetric:
    """Method count, line span, and status for a class, struct, or selector group."""
    name: str
    start_line: int
    end_line: int
    lines: int
    method_count: int
    status: str
    methods: list[str] = field(default_factory=list)


@dataclass
class FileReport:
    """Aggregated modularity report for a single source file."""
    rel_path: str
    lines: int
    status: str
    classes: list[ClassMetric] = field(default_factory=list)
    oversized_functions: list[FunctionMetric] = field(default_factory=list)
    parser_mode: str = "ast"


def classify_count(value: int, warn_limit: int, max_limit: int) -> str:
    """Return 'CRITICAL', 'WARNING', or 'OK' against soft/hard thresholds."""
    return "CRITICAL" if value > max_limit else ("WARNING" if value > warn_limit else "OK")


def iter_source_files(target_path: Path, include_vendor: bool = False) -> Iterable[Path]:
    """Yield supported source files while pruning ignored and vendor directories."""
    if target_path.is_file():
        yield target_path
        return
    for item in sorted(target_path.rglob("*")):
        if not item.is_file() or item.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        rel_parts = item.relative_to(target_path).parts
        if any(p in IGNORED_DIRS or p.endswith(".egg-info") for p in rel_parts):
            continue
        if not include_vendor and is_vendor_or_generated(item, rel_parts):
            continue
        yield item


def measure_node_lines(node: ast.AST) -> tuple[int, int, int]:
    """Return (start_line, end_line, span) for an AST node."""
    start = getattr(node, "lineno", 1)
    end = getattr(node, "end_lineno", start) or start
    return start, end, max(1, end - start + 1)


def analyze_python_ast(
    source_text: str, thresholds: AuditThresholds
) -> tuple[list[ClassMetric], list[FunctionMetric]]:
    """Parse a Python module AST to extract class and function modularity metrics."""
    try:
        tree = ast.parse(source_text)
    except (SyntaxError, ValueError):
        return [], []
    classes, oversized_funcs, method_ids = [], [], set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            c_metric, c_funcs = _inspect_class_node(node, thresholds)
            classes.append(c_metric)
            oversized_funcs.extend(c_funcs)
            method_ids.update(id(i) for i in node.body)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and id(node) not in method_ids:
            f_metric = _inspect_func_node(node, node.name, thresholds.max_func_lines)
            if f_metric.status != "OK":
                oversized_funcs.append(f_metric)
    classes.sort(key=lambda c: (c.method_count, c.lines), reverse=True)
    oversized_funcs.sort(key=lambda f: f.lines, reverse=True)
    return classes, oversized_funcs


def _inspect_class_node(
    node: ast.ClassDef, thresholds: AuditThresholds
) -> tuple[ClassMetric, list[FunctionMetric]]:
    """Extract method count and oversized methods for a single Python ClassDef."""
    start, end, span = measure_node_lines(node)
    methods: list[str] = []
    oversized: list[FunctionMetric] = []
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods.append(item.name)
            f_metric = _inspect_func_node(
                item, f"{node.name}.{item.name}", thresholds.max_func_lines
            )
            if f_metric.status != "OK":
                oversized.append(f_metric)
    status = _resolve_class_status(len(methods), span, thresholds)
    return ClassMetric(node.name, start, end, span, len(methods), status, methods), oversized


def _resolve_class_status(method_count: int, span: int, thresholds: AuditThresholds) -> str:
    """Evaluate class status from both method count and line span."""
    status = classify_count(method_count, thresholds.warn_class_methods, thresholds.max_class_methods)
    return classify_count(span, 200, 300) if status == "OK" else status


def _inspect_func_node(
    node: ast.FunctionDef | ast.AsyncFunctionDef, qualname: str, max_func_lines: int
) -> FunctionMetric:
    """Measure line span for a single function or method AST node."""
    start, end, span = measure_node_lines(node)
    status = classify_count(span, max(20, int(max_func_lines * 0.75)), max_func_lines)
    return FunctionMetric(node.name, qualname, start, end, span, status)


def _convert_raw_symbols(
    raw_symbols: list[RawSymbol], thresholds: AuditThresholds
) -> tuple[list[ClassMetric], list[FunctionMetric]]:
    """Convert non-Python RawSymbol items into graded ClassMetric and FunctionMetric lists."""
    classes, funcs = [], []
    warn_fn = max(20, int(thresholds.max_func_lines * 0.75))
    for sym in raw_symbols:
        if sym.kind == "class":
            st = _resolve_class_status(len(sym.methods), sym.lines, thresholds)
            classes.append(ClassMetric(sym.name, sym.start_line, sym.end_line, sym.lines, len(sym.methods), st, sym.methods))
        elif (st := classify_count(sym.lines, warn_fn, thresholds.max_func_lines)) != "OK":
            funcs.append(FunctionMetric(sym.name, sym.qualname, sym.start_line, sym.end_line, sym.lines, st))
    classes.sort(key=lambda c: (c.method_count, c.lines), reverse=True)
    funcs.sort(key=lambda f: f.lines, reverse=True)
    return classes, funcs


def _dispatch_language_analysis(
    suffix: str, text: str, thresholds: AuditThresholds
) -> tuple[list[ClassMetric], list[FunctionMetric], str]:
    """Route source text to the matching structural analyzer."""
    if not text:
        return [], [], "empty"
    if suffix == ".py":
        return (*analyze_python_ast(text, thresholds), "ast")
    if suffix in BRACE_EXTENSIONS:
        return (*_convert_raw_symbols(analyze_brace_language(text), thresholds), "brace")
    if suffix in STYLE_EXTENSIONS:
        return (*_convert_raw_symbols(analyze_stylesheet(text), thresholds), "stylesheet")
    return (*_convert_raw_symbols(analyze_generic_fallback(text), thresholds), "fallback")


def audit_file(file_path: Path, base_dir: Path, thresholds: AuditThresholds) -> FileReport:
    """Read a source file and build its multi-language FileReport."""
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    line_count = len(text.splitlines())
    rel_path = file_path.name if file_path == base_dir else file_path.relative_to(base_dir).as_posix()
    status = classify_count(line_count, thresholds.warn_file_lines, thresholds.max_file_lines)
    classes, funcs, mode = _dispatch_language_analysis(file_path.suffix.lower(), text, thresholds)
    return FileReport(rel_path, line_count, status, classes, funcs, mode)


def has_hard_breach(reports: Iterable[FileReport]) -> bool:
    """Return True if any file, class, or function has status 'CRITICAL'."""
    return any(
        r.status == "CRITICAL"
        or any(c.status == "CRITICAL" for c in r.classes)
        or any(f.status == "CRITICAL" for f in r.oversized_functions)
        for r in reports
    )


def recommend_mode(reports: list[FileReport], max_lines: int = 500) -> str:
    """Determine whether repo warrants PROJECT_CAMPAIGN or SINGLE_FILE fast-track."""
    if len(reports) <= 1:
        return "SINGLE_FILE"
    app_reps = [r for r in reports if not any(p in r.rel_path.lower().split("/") for p in ("tests", "test"))]
    crit_app = [r for r in app_reps if r.status == "CRITICAL" or any(c.status == "CRITICAL" for c in r.classes)]
    excess_mass = sum(max(0, r.lines - max_lines) for r in crit_app)
    subsystems = {Path(r.rel_path).parts[0] for r in crit_app if len(Path(r.rel_path).parts) > 1}
    if len(crit_app) > 2 and (excess_mass >= 200 or len(subsystems) >= 2):
        return "PROJECT_CAMPAIGN"
    if len(crit_app) >= 2 and excess_mass >= 1000:
        return "PROJECT_CAMPAIGN"
    return "SINGLE_FILE"


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
    show_methods: bool, compact: bool = False, by_dir: bool = False
) -> None:
    """Format and print a human-readable modularity audit table."""
    ranked = sorted(reports, key=lambda r: r.lines, reverse=True)
    crit = sum(1 for r in reports if r.status == "CRITICAL")
    warn = sum(1 for r in reports if r.status == "WARNING")
    mode = recommend_mode(reports, thresholds.max_file_lines)
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


def preview_split(spec: str) -> int:
    """Safely print source lines around a proposed split line (path:line[:window])."""
    # Handle Windows drive letters like C:\path\to\file:lineno[:window]
    if len(spec) > 2 and spec[1] == ":" and spec[0].isalpha():
        rparts = spec[2:].rsplit(":", 2)
        if len(rparts) < 2:
            print("Usage: --split-preview <file_path>:<line_number>[:window_lines]", file=sys.stderr)
            return 2
        fpath = Path(spec[:2] + rparts[0])
        line_s = rparts[1]
        window = int(rparts[2]) if len(rparts) > 2 else 12
    else:
        parts = spec.rsplit(":", 2)
        if len(parts) < 2:
            print("Usage: --split-preview <file_path>:<line_number>[:window_lines]", file=sys.stderr)
            return 2
        fpath = Path(parts[0])
        line_s = parts[1]
        window = int(parts[2]) if len(parts) > 2 else 12

    if not fpath.exists():
        print(f"Error: file not found: {fpath}", file=sys.stderr)
        return 2
    try:
        lineno = int(line_s)
        lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as err:
        print(f"Error reading {fpath}: {err}", file=sys.stderr)
        return 2
    start = max(0, lineno - window - 1)
    end = min(len(lines), lineno + window)
    print(f"=== Split Preview: {fpath.name} around line {lineno} (L{start+1}-L{end}) ===")
    for idx in range(start, end):
        cur = idx + 1
        marker = "==> [SPLIT POINT]" if cur == lineno else "   "
        print(f"{marker} {cur:>5} | {lines[idx]}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser."""
    p = argparse.ArgumentParser(description="Cross-platform modularity & AST budget auditor.")
    p.add_argument("--path", nargs="+", default=["."], help="Target file(s) or directory path(s).")
    p.add_argument("--top", type=int, default=None, help="Max files to display (default: all up to 50).")
    p.add_argument("--warn-file-lines", type=int, default=350)
    p.add_argument("--max-file-lines", type=int, default=500)
    p.add_argument("--warn-class-methods", type=int, default=10)
    p.add_argument("--max-class-methods", type=int, default=12)
    p.add_argument("--max-func-lines", type=int, default=40)
    p.add_argument("--show-methods", action="store_true", help="Show class/section member lists.")
    p.add_argument("--compact", action="store_true", help="Compact file view without function details.")
    p.add_argument("--by-dir", action="store_true", help="Group and summarize line counts by directory.")
    p.add_argument("--split-preview", help="Preview lines around split: <file>:<line>[:window]")
    p.add_argument("--include-vendor", action="store_true", help="Include vendor/minified files.")
    p.add_argument("--json", action="store_true", help="Emit JSON output.")
    p.add_argument("--strict", action="store_true", help="Exit 1 on CRITICAL breach.")
    return p


def _collect_reports(
    targets: list[Path], thresholds: AuditThresholds, include_vendor: bool
) -> list[FileReport]:
    """Gather FileReports across targets while filtering header-detected vendor/minified files."""
    reports: list[FileReport] = []
    seen_files: set[Path] = set()
    for target in targets:
        base_dir = target if target.is_dir() else target.parent
        for f in iter_source_files(target, include_vendor=include_vendor):
            if f in seen_files:
                continue
            seen_files.add(f)
            if not include_vendor and not target.is_file():
                head = f.read_text(encoding="utf-8", errors="replace").splitlines()[:8]
                if is_vendor_or_generated(f, f.relative_to(base_dir).parts, head):
                    continue
            reports.append(audit_file(f, base_dir, thresholds))
    return reports


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for code_health_audit."""
    args = build_arg_parser().parse_args(argv)
    if args.split_preview:
        return preview_split(args.split_preview)
    raw_paths = args.path if isinstance(args.path, list) else [args.path]
    targets: list[Path] = []
    for rp in raw_paths:
        tp = Path(rp).resolve()
        if not tp.exists():
            print(f"Error: path does not exist: {rp}", file=sys.stderr)
            return 2
        targets.append(tp)
    thresholds = AuditThresholds(
        args.warn_file_lines, args.max_file_lines,
        args.warn_class_methods, args.max_class_methods, args.max_func_lines,
    )
    reports = _collect_reports(targets, thresholds, args.include_vendor)
    top_limit = args.top if args.top is not None else max(50, len(reports))
    if args.json:
        ranked = sorted(reports, key=lambda r: r.lines, reverse=True)[: top_limit]
        print(json.dumps({
            "total_files": len(reports), "hard_breach": has_hard_breach(reports),
            "recommended_mode": recommend_mode(reports, thresholds.max_file_lines),
            "thresholds": asdict(thresholds), "files": [asdict(r) for r in ranked],
        }, indent=2))
    else:
        print_text_summary(reports, thresholds, top_limit, args.show_methods, args.compact, args.by_dir)
    return 1 if (args.strict and has_hard_breach(reports)) else 0


if __name__ == "__main__":
    sys.exit(main())
