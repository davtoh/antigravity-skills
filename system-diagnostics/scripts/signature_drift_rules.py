#!/usr/bin/env python3
"""Cross-module CALLABLE_SIGNATURE_DRIFT and METHOD_KWARG_MISMATCH AST rules."""

import ast
from typing import Any

_STDLIB_RECEIVERS = frozenset({
    "log", "logger", "logging", "json", "os", "sys", "re", "cv2", "np", "numpy",
    "plt", "pd", "torch", "sqlite3", "conn", "cursor", "client", "app", "router",
    "request", "response", "session", "ws", "websocket", "proc", "process",
    "thread", "loop", "parser", "subparsers", "fig", "ax", "canvas", "ctx",
    "driver", "page", "browser", "subprocess", "threading", "asyncio", "pathlib",
    "requests", "httpx", "fastapi", "unittest", "pytest", "yaml", "toml", "csv",
})

_COMMON_METHOD_NAMES = frozenset({
    "get", "get_state", "set", "update", "pop", "clear", "copy", "items", "keys", "values",
    "append", "extend", "insert", "remove", "sort", "index", "count", "split",
    "join", "strip", "replace", "format", "encode", "decode", "read", "write",
    "close", "flush", "seek", "open", "start", "stop", "run", "wait", "acquire",
    "release", "send", "recv", "connect", "bind", "listen", "accept", "execute",
    "executemany", "commit", "rollback", "fetchone", "fetchall", "dump", "dumps",
    "load", "loads", "match", "search", "sub", "findall", "compile", "info",
    "debug", "warning", "error", "critical", "exception", "log", "add", "delete",
    "put", "post", "patch", "head", "options", "request", "render", "draw",
    "save", "reset", "check", "validate", "parse", "serialize", "to_dict",
    "from_dict", "clone", "step", "predict", "fit", "transform", "eval",
    "forward", "create", "select", "filter", "query", "find", "exists", "rename",
    "mkdir", "unlink", "stat", "resolve", "glob", "rglob", "read_text",
    "write_text", "read_bytes", "write_bytes", "add_argument", "set_defaults",
    "add_route", "include_router", "mount", "create_task", "gather", "sleep",
    "wait_for", "send_json", "send_text", "send_bytes", "receive_json",
    "receive_text", "raise_for_status", "imwrite", "imread", "resize",
    "cvtColor", "rectangle", "putText", "circle", "line", "polylines",
    "fillPoly", "addWeighted", "imshow", "waitKey", "zeros", "ones", "array",
    "asarray", "clip", "reshape", "astype", "concatenate", "stack",
})


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


def _collect_imported_external(tree: ast.AST, classes: dict[str, set[str]]) -> set[str]:
    """Collect imported module/symbol names that are not local repo classes."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                if bound not in classes:
                    names.add(bound)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bound = alias.asname or alias.name
                if bound != "*" and bound not in classes:
                    names.add(bound)
    return names


def _is_ignored_receiver(val: ast.AST, imported_ext: set[str]) -> bool:
    """Return True when receiver looks like stdlib, mock, or imported external symbol."""
    cur: ast.AST = val
    names: list[str] = []
    while isinstance(cur, ast.Attribute):
        names.append(cur.attr.lower())
        cur = cur.value
    if isinstance(cur, ast.Name):
        if cur.id in imported_ext:
            return True
        names.append(cur.id.lower())
    for part in names:
        if part in _STDLIB_RECEIVERS or any(tok in part for tok in ("mock", "stub", "fake", "dummy")):
            return True
    return False


def _find_unknown_method_kwargs(
    call: ast.Call,
    env: dict[str, str],
    meth_sigs: dict[tuple[str, str], dict[str, Any]],
    meth_by_name: dict[str, list[tuple[str, dict[str, Any]]]],
    dynamic: set[str],
    imported_ext: set[str],
) -> tuple[str, list[str]] | None:
    """Return (symbol, unknown_kwargs) for a method call with invalid keyword args."""
    if not isinstance(call.func, ast.Attribute) or not call.keywords:
        return None
    if any(k.arg is None for k in call.keywords):
        return None
    kw_names = [k.arg for k in call.keywords if k.arg is not None]
    attr = call.func.attr
    cname = env.get(call.func.value.id) if isinstance(call.func.value, ast.Name) else None
    if cname:
        if cname in dynamic or (cname, attr) not in meth_sigs:
            return None
        sig = meth_sigs[(cname, attr)]
        if sig["has_kwarg"]:
            return None
        unknown = [k for k in kw_names if k not in sig["all_params"]]
        return (f"{cname}.{attr}", unknown) if unknown else None
    if attr.startswith("_") or attr in _COMMON_METHOD_NAMES or attr not in meth_by_name:
        return None
    if _is_ignored_receiver(call.func.value, imported_ext):
        return None
    candidates = meth_by_name[attr]
    if any(cls in dynamic or sig["has_kwarg"] for cls, sig in candidates):
        return None
    unknown = [k for k in kw_names if all(k not in sig["all_params"] for _, sig in candidates)]
    return (f"*.{attr}", unknown) if unknown else None


def _iter_scoped_calls(tree: ast.AST, classes: dict[str, set[str]], bind_fn: Any) -> list[tuple[ast.Call, dict[str, str]]]:
    """Collect (call, type_env) across class methods, functions, and module scope."""
    items: list[tuple[ast.Call, dict[str, str]]] = []
    visited_calls: set[int] = set()

    def _collect(node: ast.AST, env: dict[str, str]) -> None:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and id(sub) not in visited_calls:
                visited_calls.add(id(sub))
                items.append((sub, env))

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    env = dict(bind_fn(stmt, classes))
                    env["self"] = node.name
                    _collect(stmt, env)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _collect(node, bind_fn(node, classes))
    _collect(tree, {})
    return items


def check_method_kwarg_mismatch(
    parsed_files: list[tuple[str, ast.AST]],
    classes: dict[str, set[str]],
    dynamic: set[str],
    bind_fn: Any,
) -> list[dict[str, Any]]:
    """Flag method calls across all scopes passing unknown keyword arguments."""
    _, meth_sigs = _collect_signatures(parsed_files)
    meth_by_name: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for (cname, mname), sig in meth_sigs.items():
        meth_by_name.setdefault(mname, []).append((cname, sig))
    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for rel, tree in parsed_files:
        imported_ext = _collect_imported_external(tree, classes)
        for call, env in _iter_scoped_calls(tree, classes, bind_fn):
            res = _find_unknown_method_kwargs(call, env, meth_sigs, meth_by_name, dynamic, imported_ext)
            if not res:
                continue
            sym, unknown = res
            key = (rel, call.lineno, sym)
            if key in seen:
                continue
            seen.add(key)
            findings.append({
                "rule_id": "METHOD_KWARG_MISMATCH", "category": "CALLABLE_MISMATCH",
                "severity": "HIGH", "track": "architectural", "file": rel, "line": call.lineno,
                "symbol": sym,
                "message": f"Method call '{sym}()' passes unknown keyword argument(s) {unknown}.",
                "suggested_fix": f"Align keyword arguments of '{sym}()' with its method definition.",
                "fp": f"mkw:{rel}:{call.lineno}:{sym}",
            })
    return findings
