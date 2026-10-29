#!/usr/bin/env python3
"""Cross-platform, zero-dependency modularity and AST code health auditor.

Scans source files across Python, JavaScript/TypeScript, CSS, Dart, Go, Rust,
and C# to enforce quantitative modularity budgets (file line limits, class
method limits, and function length limits).
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".js", ".ts", ".tsx", ".jsx", ".css", ".scss",
    ".dart", ".go", ".rs", ".cs",
})

IGNORED_DIRS: frozenset[str] = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "dist", "build", "_build", "out", "target", ".idea", ".vscode",
    "scratch", "coverage", "htmlcov",
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
    """Line span and status for a single function or method."""

    name: str
    qualname: str
    start_line: int
    end_line: int
    lines: int
    status: str


@dataclass
class ClassMetric:
    """Method count, line span, and status for a single class."""

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


def classify_count(value: int, warn_limit: int, max_limit: int) -> str:
    """Return 'CRITICAL', 'WARNING', or 'OK' against soft/hard thresholds."""
    if value > max_limit:
        return "CRITICAL"
    return "WARNING" if value > warn_limit else "OK"


def iter_source_files(target_path: Path) -> Iterable[Path]:
    """Yield supported source files while pruning ignored build/venv directories."""
    if target_path.is_file():
        yield target_path
        return
    for item in sorted(target_path.rglob("*")):
        if not item.is_file() or item.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        rel_parts = item.relative_to(target_path).parts
        if not any(p in IGNORED_DIRS or p.endswith(".egg-info") for p in rel_parts):
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
    node: ast.ClassDef,
    thresholds: AuditThresholds,
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
    metric = ClassMetric(
        name=node.name, start_line=start, end_line=end,
        lines=span, method_count=len(methods), status=status, methods=methods,
    )
    return metric, oversized


def _resolve_class_status(
    method_count: int, span: int, thresholds: AuditThresholds
) -> str:
    """Evaluate class status from both method count and line span."""
    status = classify_count(
        method_count, thresholds.warn_class_methods, thresholds.max_class_methods
    )
    if status == "OK":
        return classify_count(span, 200, 300)
    return status


def _inspect_func_node(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    qualname: str,
    max_func_lines: int,
) -> FunctionMetric:
    """Measure line span for a single function or method AST node."""
    start, end, span = measure_node_lines(node)
    warn_limit = max(20, int(max_func_lines * 0.75))
    status = classify_count(span, warn_limit, max_func_lines)
    return FunctionMetric(
        name=node.name, qualname=qualname,
        start_line=start, end_line=end, lines=span, status=status,
    )


def audit_file(
    file_path: Path, base_dir: Path, thresholds: AuditThresholds
) -> FileReport:
    """Read a source file and build its FileReport."""
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""

    line_count = len(text.splitlines())
    rel_path = (
        file_path.name
        if file_path == base_dir
        else file_path.relative_to(base_dir).as_posix()
    )
    status = classify_count(
        line_count, thresholds.warn_file_lines, thresholds.max_file_lines
    )
    classes, funcs = (
        analyze_python_ast(text, thresholds)
        if file_path.suffix.lower() == ".py" and text
        else ([], [])
    )
    return FileReport(rel_path, line_count, status, classes, funcs)


def has_hard_breach(reports: Iterable[FileReport]) -> bool:
    """Return True if any file, class, or function has status 'CRITICAL'."""
    return any(
        r.status == "CRITICAL"
        or any(c.status == "CRITICAL" for c in r.classes)
        or any(f.status == "CRITICAL" for f in r.oversized_functions)
        for r in reports
    )


def recommend_mode(reports: list[FileReport]) -> str:
    """Return 'PROJECT_CAMPAIGN' if >2 files have CRITICAL status, else 'SINGLE_FILE'."""
    crit_files = sum(
        1 for r in reports
        if r.status == "CRITICAL" or any(c.status == "CRITICAL" for c in r.classes)
    )
    return "PROJECT_CAMPAIGN" if crit_files > 2 else "SINGLE_FILE"


def print_text_summary(
    reports: list[FileReport],
    thresholds: AuditThresholds,
    top_n: int,
    show_methods: bool,
) -> None:
    """Format and print a human-readable modularity audit table."""
    ranked = sorted(reports, key=lambda r: r.lines, reverse=True)
    crit = sum(1 for r in reports if r.status == "CRITICAL")
    warn = sum(1 for r in reports if r.status == "WARNING")
    mode = recommend_mode(reports)
    print(f"=== Modularity Audit ({len(reports)} files | Critical: {crit} | Warning: {warn}) ===")
    print(
        f"Budgets: File <= {thresholds.warn_file_lines}/{thresholds.max_file_lines}L | "
        f"Class <= {thresholds.warn_class_methods}/{thresholds.max_class_methods}M | "
        f"Func <= {thresholds.max_func_lines}L | Recommended Mode: {mode}\n"
    )
    print(f"{'Status':<10} {'Lines':>7}  {'Path'}\n" + "-" * 72)
    for rep in ranked[:top_n]:
        print(f"{rep.status:<10} {rep.lines:>7}  {rep.rel_path}")
        _print_file_details(rep, show_methods)


def _print_file_details(rep: FileReport, show_methods: bool) -> None:
    """Print class and function breach details for a single file report."""
    for cls in rep.classes:
        if show_methods or cls.status != "OK":
            print(
                f"   [Class {cls.status}] {cls.name} "
                f"(L{cls.start_line}-L{cls.end_line}, {cls.lines}L, {cls.method_count} methods)"
            )
            if show_methods and cls.methods:
                preview = ", ".join(cls.methods[:12])
                print(f"      Methods: {preview}{' ...' if len(cls.methods) > 12 else ''}")
    for fn in rep.oversized_functions[:8]:
        if show_methods or fn.status == "CRITICAL":
            print(f"   [Func  {fn.status}] {fn.qualname} (L{fn.start_line}-L{fn.end_line}, {fn.lines}L)")


def build_arg_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser."""
    p = argparse.ArgumentParser(description="Cross-platform modularity & AST budget auditor.")
    p.add_argument("--path", default=".", help="Target file or directory path.")
    p.add_argument("--top", type=int, default=15, help="Max files to display.")
    p.add_argument("--warn-file-lines", type=int, default=350)
    p.add_argument("--max-file-lines", type=int, default=500)
    p.add_argument("--warn-class-methods", type=int, default=10)
    p.add_argument("--max-class-methods", type=int, default=12)
    p.add_argument("--max-func-lines", type=int, default=40)
    p.add_argument("--show-methods", action="store_true", help="Show class method lists.")
    p.add_argument("--json", action="store_true", help="Emit JSON output.")
    p.add_argument("--strict", action="store_true", help="Exit 1 on CRITICAL breach.")
    return p


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for code_health_audit."""
    args = build_arg_parser().parse_args(argv)
    target = Path(args.path).resolve()
    if not target.exists():
        print(f"Error: path does not exist: {args.path}", file=sys.stderr)
        return 2

    thresholds = AuditThresholds(
        args.warn_file_lines, args.max_file_lines,
        args.warn_class_methods, args.max_class_methods, args.max_func_lines,
    )
    base_dir = target if target.is_dir() else target.parent
    reports = [audit_file(f, base_dir, thresholds) for f in iter_source_files(target)]

    if args.json:
        ranked = sorted(reports, key=lambda r: r.lines, reverse=True)[: args.top]
        print(json.dumps({
            "total_files": len(reports),
            "hard_breach": has_hard_breach(reports),
            "recommended_mode": recommend_mode(reports),
            "thresholds": asdict(thresholds),
            "files": [asdict(r) for r in ranked],
        }, indent=2))
    else:
        print_text_summary(reports, thresholds, args.top, args.show_methods)
    return 1 if (args.strict and has_hard_breach(reports)) else 0


if __name__ == "__main__":
    sys.exit(main())
