#!/usr/bin/env python3
"""AST guard rules for silent shape/dimension-guarded loop skips."""

import ast
from typing import Any

_SHAPE_ATTRS = frozenset({"shape", "ndim", "dim", "dims", "size", "channels", "dtype", "embedding_dim", "feat_dim"})
_LOG_CALLS = frozenset({"debug", "info", "warning", "warn", "error", "critical", "exception", "log", "print", "inc", "increment", "observe", "count"})


def _test_checks_shape(test_node: ast.AST) -> bool:
    """Return True if an if-condition inspects tensor/array shape, ndim, or len()."""
    for sub in ast.walk(test_node):
        if isinstance(sub, ast.Attribute) and sub.attr in _SHAPE_ATTRS:
            return True
        if isinstance(sub, ast.Name) and any(tok in sub.id.lower() for tok in ("shape", "dim", "ndim")):
            return True
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id == "len":
            return True
    return False


def _has_observability_call(stmts: list[ast.stmt]) -> bool:
    """Return True if statements emit a log, warning, metric, or raise."""
    for stmt in stmts:
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Raise):
                return True
            if isinstance(sub, ast.Call):
                fn = sub.func
                name = fn.attr.lower() if isinstance(fn, ast.Attribute) else (fn.id.lower() if isinstance(fn, ast.Name) else "")
                if name in _LOG_CALLS or any(k in name for k in ("log", "warn", "metric", "counter")):
                    return True
    return False


def _scan_loop_body(stmts: list[ast.stmt], rel: str, findings: list[dict[str, Any]]) -> None:
    for stmt in stmts:
        if isinstance(stmt, ast.If):
            has_continue = any(isinstance(b, ast.Continue) for b in stmt.body)
            if has_continue and _test_checks_shape(stmt.test) and not _has_observability_call(stmt.body):
                findings.append({
                    "rule_id": "SILENT_SHAPE_SKIP",
                    "category": "BAD_LOGIC",
                    "severity": "MEDIUM",
                    "track": "architectural",
                    "file": rel,
                    "line": stmt.lineno,
                    "symbol": "continue",
                    "message": "Shape/dimension-guarded 'continue' silently skips item without logging or metric.",
                    "suggested_fix": "Log a warning or increment a mismatch counter before 'continue'.",
                    "fp": f"shape_skip:{rel}:{stmt.lineno}",
                })
            _scan_loop_body(stmt.body, rel, findings)
            _scan_loop_body(stmt.orelse, rel, findings)


def check_silent_shape_skips(parsed_files: list[tuple[str, ast.AST]]) -> list[dict[str, Any]]:
    """Flag loop branches that skip mismatched shapes/dimensions with silent continue."""
    findings: list[dict[str, Any]] = []
    for rel, tree in parsed_files:
        for node in ast.walk(tree):
            if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
                _scan_loop_body(node.body, rel, findings)
    return findings
