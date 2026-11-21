#!/usr/bin/env python3
"""Cross-module Python AST defect rules for shadow_prober.

Implements:
1. Cross-module attribute/method resolution (CROSS_MODULE_MISSING_ATTR)
2. Cross-module monotonic -> Unix-epoch clock-domain taint (CROSS_MODULE_CLOCK_TAINT)
3. AB-BA lock-order inversion detection (LOCK_ORDER_INVERSION)
4. Single-module mixed clock-domain helper (MIXED_CLOCK_DOMAIN)
"""

import ast
from typing import Any


def check_mixed_clock_domains(
    rel_path: str,
    time_calls: list[tuple[int, str]],
    monotonic_calls: list[tuple[int, str]],
    add_fn: Any,
    timing_re: Any,
) -> None:
    """Flag mixed time.time() and time.monotonic() usage in the same scope or timing module."""
    if not (time_calls and monotonic_calls):
        return
    by_scope_t = {s: ln for ln, s in time_calls}
    by_scope_m = {s: ln for ln, s in monotonic_calls}
    shared = sorted(set(by_scope_t) & set(by_scope_m))
    if shared:
        for sc in shared:
            add_fn(
                "MIXED_CLOCK_DOMAIN", "BAD_LOGIC", "HIGH", "architectural",
                min(by_scope_t[sc], by_scope_m[sc]), sc or rel_path,
                f"Mixed clock domains in '{sc or rel_path}': time.time() (L{by_scope_t[sc]}) and time.monotonic() (L{by_scope_m[sc]}).",
                "Unify elapsed/deadline timing on time.monotonic() and reserve time.time() for wall-clock/epoch timestamps.",
                f"clock:{sc}",
            )
    elif timing_re.search(rel_path):
        t_ln, _ = time_calls[0]
        m_ln, _ = monotonic_calls[0]
        add_fn(
            "MIXED_CLOCK_DOMAIN", "BAD_LOGIC", "HIGH", "architectural",
            min(t_ln, m_ln), rel_path,
            f"Timing/worker module mixes time.time() (L{t_ln}) and time.monotonic() (L{m_ln}).",
            "Unify elapsed/deadline timing on time.monotonic() and reserve time.time() for wall-clock/epoch timestamps.",
            f"clock:{rel_path}",
        )


def _extract_class_info(cls_node: ast.ClassDef) -> tuple[set[str], list[str], bool]:
    """Collect declared methods, properties, self.* attrs, class attrs, and bases."""
    members: set[str] = set()
    bases = [b.id for b in cls_node.bases if isinstance(b, ast.Name)]
    is_dynamic = False
    for stmt in cls_node.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            members.add(stmt.name)
            if stmt.name in ("__getattr__", "__getattribute__"):
                is_dynamic = True
            for sub in ast.walk(stmt):
                if isinstance(sub, ast.Assign):
                    for t in sub.targets:
                        if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self":
                            members.add(t.attr)
                elif isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Attribute):
                    if isinstance(sub.target.value, ast.Name) and sub.target.value.id == "self":
                        members.add(sub.target.attr)
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            members.add(stmt.target.id)
        elif isinstance(stmt, ast.Assign):
            for t in stmt.targets:
                if isinstance(t, ast.Name):
                    members.add(t.id)
    return members, bases, is_dynamic


def _collect_class_registry(parsed_files: list[tuple[str, ast.AST]]) -> tuple[dict[str, set[str]], set[str]]:
    """Build inherited class member map and dynamic-attribute class set across all files."""
    raw: dict[str, set[str]] = {}
    bases_map: dict[str, list[str]] = {}
    dynamic: set[str] = set()
    for _, tree in parsed_files:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                mems, bases, is_dyn = _extract_class_info(node)
                raw.setdefault(node.name, set()).update(mems)
                bases_map[node.name] = bases
                if is_dyn:
                    dynamic.add(node.name)
    resolved: dict[str, set[str]] = {}
    for name in raw:
        acc = set(raw[name])
        stack = list(bases_map.get(name, []))
        seen: set[str] = {name}
        while stack:
            b = stack.pop()
            if b in seen:
                continue
            seen.add(b)
            if b in dynamic:
                dynamic.add(name)
            acc.update(raw.get(b, set()))
            stack.extend(bases_map.get(b, []))
        resolved[name] = acc
    return resolved, dynamic


def _bind_local_types(fn_node: ast.AST, classes: dict[str, set[str]]) -> dict[str, str]:
    """Infer simple local variable -> ClassName bindings from annotations and constructor calls."""
    env: dict[str, str] = {}
    args = getattr(fn_node, "args", None)
    if args:
        for a in list(args.args) + list(args.kwonlyargs):
            if isinstance(a.annotation, ast.Name) and a.annotation.id in classes:
                env[a.arg] = a.annotation.id
    for sub in ast.walk(fn_node):
        if isinstance(sub, ast.Assign) and isinstance(sub.value, ast.Call):
            cname = sub.value.func.id if isinstance(sub.value.func, ast.Name) else (
                sub.value.func.attr if isinstance(sub.value.func, ast.Attribute) else ""
            )
            if cname in classes:
                for t in sub.targets:
                    if isinstance(t, ast.Name):
                        env[t.id] = cname
        elif isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name) and isinstance(sub.annotation, ast.Name):
            if sub.annotation.id in classes:
                env[sub.target.id] = sub.annotation.id
    return env


def _check_missing_attrs(parsed_files: list[tuple[str, ast.AST]], classes: dict[str, set[str]], dynamic: set[str]) -> list[dict[str, Any]]:
    """Flag obj.attr accesses where obj's inferred class lacks attr across modules."""
    findings: list[dict[str, Any]] = []
    for rel, tree in parsed_files:
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            env = _bind_local_types(node, classes)
            for sub in ast.walk(node):
                if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name):
                    cname = env.get(sub.value.id) or (sub.value.id if sub.value.id in classes else None)
                    if cname and cname not in dynamic and sub.attr not in classes[cname] and not sub.attr.startswith("__"):
                        findings.append({
                            "rule_id": "CROSS_MODULE_MISSING_ATTR", "category": "CALLABLE_MISMATCH",
                            "severity": "HIGH", "track": "architectural", "file": rel, "line": sub.lineno,
                            "symbol": f"{cname}.{sub.attr}",
                            "message": f"'{cname}' has no attribute or method '{sub.attr}' (cross-module check).",
                            "suggested_fix": f"Verify '{cname}.{sub.attr}' spelling or implement '{sub.attr}' on '{cname}'.",
                            "fp": f"{cname}.{sub.attr}",
                        })
    return findings


def _is_time_call(node: ast.AST | None, attr: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "time"
        and node.func.attr == attr
    )


def _check_clock_taint(parsed_files: list[tuple[str, ast.AST]]) -> list[dict[str, Any]]:
    """Flag cross-module monotonic() return values compared with or passed to wall-clock time.time()."""
    mono_funcs: set[str] = set()
    for _, tree in parsed_files:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if any(_is_time_call(getattr(sub, "value", None), "monotonic") for sub in ast.walk(node) if isinstance(sub, ast.Return)):
                    mono_funcs.add(node.name)
    if not mono_funcs:
        return []
    findings: list[dict[str, Any]] = []
    for rel, tree in parsed_files:
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            tainted = {
                t.id for sub in ast.walk(node) if isinstance(sub, ast.Assign)
                and isinstance(sub.value, ast.Call) and isinstance(sub.value.func, ast.Name) and sub.value.func.id in mono_funcs
                for t in sub.targets if isinstance(t, ast.Name)
            }
            if not tainted:
                continue
            has_wall = any(_is_time_call(sub, "time") for sub in ast.walk(node))
            if has_wall:
                findings.append({
                    "rule_id": "CROSS_MODULE_CLOCK_TAINT", "category": "BAD_LOGIC",
                    "severity": "HIGH", "track": "architectural", "file": rel, "line": node.lineno,
                    "symbol": node.name,
                    "message": f"Function '{node.name}' mixes monotonic-tainted value ({', '.join(sorted(tainted))}) with wall-clock time.time().",
                    "suggested_fix": "Use time.monotonic() consistently for elapsed/deadline math.",
                    "fp": f"taint:{rel}:{node.name}",
                })
    return findings


def _lock_name(expr: ast.AST) -> str | None:
    if isinstance(expr, ast.Name) and "lock" in expr.id.lower():
        return expr.id
    if isinstance(expr, ast.Attribute) and "lock" in expr.attr.lower():
        return expr.attr
    return None


def _collect_nested_locks(stmts: list[ast.stmt], held: list[str], rel: str, edges: dict[tuple[str, str], tuple[str, int]]) -> None:
    for stmt in stmts:
        if isinstance(stmt, (ast.With, ast.AsyncWith)):
            added = [ln for item in stmt.items if (ln := _lock_name(item.context_expr))]
            for outer in held:
                for inner in added:
                    if outer != inner:
                        edges.setdefault((outer, inner), (rel, stmt.lineno))
            _collect_nested_locks(stmt.body, held + added, rel, edges)
        else:
            for child in ast.iter_child_nodes(stmt):
                if isinstance(child, ast.stmt):
                    _collect_nested_locks([child], held, rel, edges)


def _check_lock_order_inversion(parsed_files: list[tuple[str, ast.AST]]) -> list[dict[str, Any]]:
    """Detect AB-BA lock acquisition order inversions across functions/modules."""
    edges: dict[tuple[str, str], tuple[str, int]] = {}
    for rel, tree in parsed_files:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _collect_nested_locks(node.body, [], rel, edges)
    findings: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for (a, b), (rel, line) in edges.items():
        if (b, a) in edges and (min(a, b), max(a, b)) not in seen_pairs:
            seen_pairs.add((min(a, b), max(a, b)))
            rel2, line2 = edges[(b, a)]
            findings.append({
                "rule_id": "LOCK_ORDER_INVERSION", "category": "DEADLOCK_RISK",
                "severity": "HIGH", "track": "architectural", "file": rel, "line": line,
                "symbol": f"{a}<->{b}",
                "message": f"AB-BA lock order inversion: '{a}' -> '{b}' ({rel}:{line}) vs '{b}' -> '{a}' ({rel2}:{line2}).",
                "suggested_fix": f"Enforce a single canonical lock acquisition order for '{a}' and '{b}'.",
                "fp": f"lock:{min(a,b)}:{max(a,b)}",
            })
    return findings


def scan_cross_module_defects(parsed_files: list[tuple[str, ast.AST]]) -> list[dict[str, Any]]:
    """Run all cross-module Python AST checks over parsed (rel_path, AST) tuples."""
    if not parsed_files:
        return []
    classes, dynamic = _collect_class_registry(parsed_files)
    return (
        _check_missing_attrs(parsed_files, classes, dynamic)
        + _check_clock_taint(parsed_files)
        + _check_lock_order_inversion(parsed_files)
    )
