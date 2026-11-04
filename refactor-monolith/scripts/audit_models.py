#!/usr/bin/env python3
"""Data models and thresholds for modularity and AST code health auditing."""

from dataclasses import dataclass, field

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
