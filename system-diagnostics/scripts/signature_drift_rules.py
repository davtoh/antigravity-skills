#!/usr/bin/env python3
"""Cross-module CALLABLE_SIGNATURE_DRIFT AST rule inside try/except blocks."""

import ast
from typing import Any


def _sig_from_fn(node: ast.FunctionDef | ast.AsyncFunctionDef, drop_first: bool = False) -> dict[str, Any]:
    """Extract positional bounds, keyword names, and variadic flags from a function AST."""
    args = node.args
    pos = list(args.posonlyargs) + list(args.args)
    if drop_first and pos:
        pos = pos[1:]
    n_pos = len(pos)
    n_def = min(len(args.defaults), n_pos)
    min_pos = n_pos - n_def
    pos_names = [a.arg for a in pos]
    kwonly_names = {a.arg for a in args.kwonlyargs}
    req_kwonly = {
        a.arg for a, d in zip(args.kwonlyargs, args.kw_defaults) if d is None
    }
    return {
        "min_pos": min_pos,
        "max_pos": n_pos,
        "pos_names": pos_names,
        "all_params": set(pos_names) | kwonly_names,
        "req_kwonly": req_kwonly,
        "has_vararg": args.vararg is not None,
        "has_kwarg": args.kwarg is not None,
    }


def _collect_signatures(
    parsed_files: list[tuple[str, ast.AST]],
) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    """Collect unique top-level function signatures and (ClassName, method) signatures."""
    fn_counts: dict[str, int] = {}
    fn_sigs: dict[str, dict[str, Any]] = {}
    meth_sigs: dict[tuple[str, str], dict[str, Any]] = {}
    for _, tree in parsed_files:
        for node in getattr(tree, "body", []):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_counts[node.name] = fn_counts.get(node.name, 0) + 1
                fn_sigs[node.name] = _sig_from_fn(node, drop_first=False)
            elif isinstance(node, ast.ClassDef):
                for stmt in node.body:
                    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        decs = {d.id for d in stmt.decorator_list if isinstance(d, ast.Name)}
                        meth_sigs[(node.name, stmt.name)] = _sig_from_fn(
                            stmt, drop_first=("staticmethod" not in decs)
                        )
    unique_fns = {k: v for k, v in fn_sigs.items() if fn_counts.get(k) == 1}
    return unique_fns, meth_sigs


def _drift_reason(call: ast.Call, sig: dict[str, Any]) -> str | None:
    """Return a mismatch description if call arguments violate sig, else None."""
    if any(isinstance(a, ast.Starred) for a in call.args) or any(k.arg is None for k in call.keywords):
        return None
    kw_names = [k.arg for k in call.keywords if k.arg is not None]
    if not sig["has_kwarg"]:
        unknown = [k for k in kw_names if k not in sig["all_params"]]
        if unknown:
            return f"unexpected keyword argument(s) {unknown}"
    n_pos = len(call.args)
    if not sig["has_vararg"] and n_pos > sig["max_pos"]:
        return f"too many positional args ({n_pos} > {sig['max_pos']})"
    covered_pos = set(sig["pos_names"][:n_pos])
    missing_req = [
        p for p in sig["pos_names"][:sig["min_pos"]]
        if p not in covered_pos and p not in kw_names
    ] + [p for p in sig["req_kwonly"] if p not in kw_names]
    if missing_req:
        return f"missing required argument(s) {sorted(missing_req)}"
    return None


def check_callable_signature_drift(
    parsed_files: list[tuple[str, ast.AST]],
    classes: dict[str, set[str]],
    dynamic: set[str],
    bind_fn: Any,
) -> list[dict[str, Any]]:
    """Flag calls inside try/except blocks whose arguments drift from local definitions."""
    unique_fns, meth_sigs = _collect_signatures(parsed_files)
    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for rel, tree in parsed_files:
        for fn_node in ast.walk(tree):
            if not isinstance(fn_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            env = bind_fn(fn_node, classes)
            for sub in ast.walk(fn_node):
                if not isinstance(sub, ast.Try):
                    continue
                for stmt in sub.body:
                    for call in (n for n in ast.walk(stmt) if isinstance(n, ast.Call)):
                        sig, sym = None, ""
                        if isinstance(call.func, ast.Name) and call.func.id in unique_fns:
                            sig, sym = unique_fns[call.func.id], call.func.id
                        elif isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
                            cname = env.get(call.func.value.id)
                            if cname and cname not in dynamic and (cname, call.func.attr) in meth_sigs:
                                sig, sym = meth_sigs[(cname, call.func.attr)], f"{cname}.{call.func.attr}"
                        if sig and (reason := _drift_reason(call, sig)):
                            key = (rel, call.lineno, sym)
                            if key not in seen:
                                seen.add(key)
                                findings.append({
                                    "rule_id": "CALLABLE_SIGNATURE_DRIFT", "category": "CALLABLE_MISMATCH",
                                    "severity": "HIGH", "track": "architectural", "file": rel, "line": call.lineno,
                                    "symbol": sym,
                                    "message": f"Call to '{sym}()' inside try/except has {reason}.",
                                    "suggested_fix": f"Align '{sym}()' call arguments with its definition.",
                                    "fp": f"sig:{rel}:{call.lineno}:{sym}",
                                })
    return findings
