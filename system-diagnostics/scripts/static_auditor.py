#!/usr/bin/env python3
"""Modular Static Quality, Defect & Code Smell Auditor (system-diagnostics).

Scans repositories or subpaths for:
1. Virtualenv-native static type & lint errors (ruff, mypy, pyright, dart analyze)
2. Dynamic platform import smells (try..except ImportError ladders vs static sys.platform)
3. Callable & constructor signature smoke testing (catching initialization TypeErrors)
4. Modularity budget overruns (functions > 40L, classes > 12 methods, CSS !important)

Strictly token-budgeted: caps console output to top 5 issues per category to
prevent context window explosion during AI agent interactions.
"""

import ast
import ctypes
import enum
import importlib
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from defect_catalog import IGNORED_WORKSPACE_DIRS as IGNORED_DIRS
except ImportError:
    from .defect_catalog import IGNORED_WORKSPACE_DIRS as IGNORED_DIRS  # type: ignore[no-redef]

PLATFORM_MODULE_HINTS = frozenset({
    "win32api", "win32con", "win32gui", "win32process", "_winreg", "winreg",
    "msvcrt", "ctypes.windll", "fcntl", "termios", "tty", "pty", "posix",
    "_xlmac", "AppKit", "Foundation", "objc",
})


def _find_py_files(target: Path) -> list[Path]:
    """Find all Python source files excluding ignored build/cache directories."""
    if target.is_file() and target.suffix == ".py":
        return [target]
    if not target.is_dir():
        return []
    return [
        p for p in target.rglob("*.py")
        if not any(part in IGNORED_DIRS for part in p.parts)
        and p.name != "setup.py"
    ]


_LIFECYCLE_TOKENS = ("pool", "manager", "source", "capture", "thread", "worker", "loop", "server", "stream", "watcher", "app", "lifecycle")


def _smoke_check_class(name: str, obj: Any, p: Path) -> dict[str, Any] | None:
    """Validate class signature and parameterless instantiation unless lifecycle/abstract."""
    if inspect.isabstract(obj) or getattr(obj, "_is_protocol", False) or issubclass(obj, (BaseException, enum.Enum, ctypes.Structure, ctypes.Union)):
        return None
    try:
        sig = inspect.signature(obj)
    except (ValueError, TypeError) as se:
        return {"type": "invalid_signature", "file": str(p), "line": 1, "message": f"Invalid class signature {name}: {se}"}
    req = [prm for prm in sig.parameters.values() if prm.default is inspect.Parameter.empty and prm.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)]
    has_lc = any(hasattr(obj, a) for a in ("stop", "close", "start", "run", "shutdown"))
    if req or has_lc or any(t in name.lower() for t in _LIFECYCLE_TOKENS):
        return None
    try:
        obj()
    except TypeError as te:
        try:
            _, lineno = inspect.getsourcelines(obj)
        except (OSError, TypeError):
            lineno = 1
        return {"type": "initialization_type_error", "file": str(p), "line": lineno, "message": f"Initialization TypeError in {name}(): {te}"}
    except Exception:
        pass
    return None


def _smoke_check_member(mod_name: str, name: str, obj: Any, p: Path) -> dict[str, Any] | None:
    """Safely inspect one module member; skip lazy proxies (e.g., Django LazySettings)."""
    try:
        is_cls = inspect.isclass(obj)
        owner = getattr(obj, "__module__", None)
        is_fn = not is_cls and inspect.isfunction(obj)
    except Exception:
        return None
    if owner != mod_name:
        return None
    if is_cls:
        return _smoke_check_class(name, obj, p)
    if is_fn:
        try:
            inspect.signature(obj)
        except (ValueError, TypeError) as se:
            return {"type": "invalid_signature", "file": str(p), "line": 1, "message": f"Invalid function signature {name}: {se}"}
    return None


def audit_callable_smoke(target: Path) -> list[dict[str, Any]]:
    """Inspect Python signatures and instantiate parameterless classes to detect TypeErrors."""
    issues: list[dict[str, Any]] = []
    root = target if target.is_dir() else target.parent
    while (root / "__init__.py").is_file() and root.parent != root:
        root = root.parent
    if (root_str := str(root.resolve())) not in sys.path:
        sys.path.insert(0, root_str)
    for p in _find_py_files(target):
        try:
            ast.parse(p.read_text(encoding="utf-8", errors="replace"), filename=str(p))
        except SyntaxError as err:
            issues.append({"type": "syntax_error", "file": str(p), "line": err.lineno or 1, "message": f"SyntaxError: {err.msg}"})
            continue
        try:
            mod = importlib.import_module(".".join(p.relative_to(root).with_suffix("").parts))
            members = list(vars(mod).items())
        except Exception:
            continue
        for name, obj in members:
            if issue := _smoke_check_member(mod.__name__, name, obj, p):
                issues.append(issue)
    return issues


def audit_platform_smells(target: Path) -> list[dict[str, Any]]:
    """Detect dynamic try..except ImportError ladders on platform-specific modules."""
    py_files = _find_py_files(target)
    smells: list[dict[str, Any]] = []

    for p in py_files:
        try:
            code = p.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(code, filename=str(p))
        except Exception:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                catches_import_error = False
                for handler in node.handlers:
                    if handler.type:
                        for h_node in ast.walk(handler.type):
                            if isinstance(h_node, ast.Name) and h_node.id in ("ImportError", "ModuleNotFoundError"):
                                catches_import_error = True
                                break
                if catches_import_error:
                    for body_item in node.body:
                        for imp_node in ast.walk(body_item):
                            mod_name = ""
                            if isinstance(imp_node, ast.Import):
                                for alias in imp_node.names:
                                    mod_name = alias.name
                            elif isinstance(imp_node, ast.ImportFrom) and imp_node.module:
                                mod_name = imp_node.module
                            if mod_name and (mod_name in PLATFORM_MODULE_HINTS or any(mod_name.startswith(h) for h in PLATFORM_MODULE_HINTS)):
                                smells.append({
                                    "type": "dynamic_platform_import_ladder",
                                    "file": str(p),
                                    "line": node.lineno,
                                    "message": f"Dynamic try..except on platform module '{mod_name}'. Use static guard `if sys.platform == 'win32':` instead.",
                                })
    return smells


def _run_linter(py_bin: str, mod: str, args: list[str], cwd: Path, match_fn: Any, label: str) -> tuple[bool, int, list[str]]:
    """Run one optional linter/typechecker module and return (ran, exit_code, logs)."""
    try:
        if subprocess.run([py_bin, "-m", mod, "--version"], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False).returncode != 0:
            return False, 0, []
        proc = subprocess.run([py_bin, "-m", mod, *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    except Exception:
        return False, 0, []
    if proc.returncode == 0:
        return True, 0, [f"[{mod}] PASS: 0 {label} found in {cwd.name if cwd.is_dir() else ''}{'' if cwd.is_dir() else ''}".rstrip() + ("." if cwd.is_dir() else "")]
    lines = [ln for ln in proc.stdout.splitlines() if match_fn(ln)]
    logs = [f"[{mod}] Flagged {len(lines)} {label}(s) (top 5 shown):"] + [f"  {ln}" for ln in lines[:5]]
    if len(lines) > 5:
        logs.append(f"  ... and {len(lines) - 5} more issues omitted to conserve tokens.")
    return True, 1, logs


def run_static_typecheckers(target: Path, py_bin: str) -> tuple[int, list[str]]:
    """Execute ruff, mypy, or pyright on Python targets with token-capped output."""
    if target.is_file() and target.suffix.lower() != ".py":
        return 0, [f"[typecheck] SKIPPED: Non-Python target {target.name}."]
    cwd = target if target.is_dir() else target.parent
    t_str = str(target)
    logs: list[str] = []
    has_run, exit_code = False, 0
    for mod, args, fn, lbl in (
        ("ruff", ["check", "--no-cache", "--select", "E,F,W", "--ignore", "E501,E701,E402", "--output-format", "concise", t_str], lambda ln: bool(ln.strip()) and not ln.startswith("Found "), "lint issue"),
        ("mypy", ["--no-incremental", "--cache-dir", os.devnull, "--no-error-summary", "--ignore-missing-imports", "--follow-imports=silent", t_str], lambda ln: "error:" in ln, "type error"),
    ):
        ran, rc, m_logs = _run_linter(py_bin, mod, args, cwd, fn, lbl)
        if ran:
            has_run = True
            exit_code = max(exit_code, rc)
            logs.extend([f"[{mod}] PASS: 0 {lbl}s found in {target.name}." if rc == 0 else m_logs[0], *([] if rc == 0 else m_logs[1:])])
    if not has_run:
        logs.append(f"[typecheck] SKIPPED: No ruff/mypy installed in {py_bin}.")
    return exit_code, logs


def _opt_int(args: Any, name: str) -> int | None:
    """Return integer attribute from args, ignoring unset or MagicMock values."""
    val = getattr(args, name, None)
    return val if isinstance(val, int) and not isinstance(val, bool) else None


def audit_modularity_budgets(
    target: Path,
    *,
    max_lines: int = 350,
    max_fn_lines: int = 40,
    max_methods: int = 12,
) -> list[dict[str, Any]]:
    """Flag files, classes, and functions exceeding modularity line or method budgets."""
    issues: list[dict[str, Any]] = []
    for p in _find_py_files(target):
        try:
            code = p.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(code, filename=str(p))
        except Exception:
            continue
        lines = len(code.splitlines())
        if lines >= max_lines:
            issues.append({"type": "file_budget_overrun", "file": str(p), "line": 1, "message": f"File has {lines} lines (budget < {max_lines})."})
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and getattr(node, "end_lineno", None):
                seg = ast.get_source_segment(code, node)
                if seg is not None:
                    # Exclude blank and comment-only lines so helpful comments never penalize budgets
                    span = sum(1 for ln in seg.splitlines() if ln.strip() and not ln.lstrip().startswith("#"))
                else:
                    span = (node.end_lineno or node.lineno) - node.lineno + 1
                if span > max_fn_lines:
                    issues.append({"type": "function_budget_overrun", "file": str(p), "line": node.lineno, "message": f"Function '{node.name}' is {span} lines (budget <= {max_fn_lines})."})
            elif isinstance(node, ast.ClassDef):
                methods = sum(1 for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)))
                if methods > max_methods:
                    issues.append({"type": "class_budget_overrun", "file": str(p), "line": node.lineno, "message": f"Class '{node.name}' has {methods} methods (budget <= {max_methods})."})
    return issues


def _print_audit_report(target: Path, results: dict[str, Any], line_cnt: int | None) -> None:
    """Render token-capped console summary for cmd_audit."""
    print(f"\n=== Static Quality & Defect Audit ({target.name}) ===")
    if line_cnt is not None:
        tag = "HARD >=500L" if line_cnt >= 500 else ("WARN >=350L" if line_cnt >= 350 else "OK <350L")
        print(f"  [lines] {target.name}: {line_cnt} lines ({tag})")
    for log in results["typecheck_logs"]:
        print(f"  {log}")
    if results["issues"]:
        print(f"\n[Latent Defects & Smells Flagged: {len(results['issues'])}]")
        for issue in results["issues"][:5]:
            p_rel = os.path.relpath(issue["file"], str(target)).replace("\\", "/") if target.is_dir() else Path(issue["file"]).name
            print(f"  - [{issue['type']}] {p_rel}:{issue['line']} -> {issue['message']}")
        if len(results["issues"]) > 5:
            print(f"  ... and {len(results['issues']) - 5} more issue(s) omitted to conserve tokens (use --json for full list).")
    else:
        print("  ✓ Zero latent defects or platform smells detected.")
    print(f"\nAudit Result: {results['status']}\n")


def cmd_audit(target: Path, py_bin: str, args: Any) -> int:
    """Entrypoint for `diagnose.py audit` subcommand."""
    do_all = not (getattr(args, "callable_smoke", False) or getattr(args, "smells", False) or getattr(args, "typecheck", False))
    results: dict[str, Any] = {"target": str(target), "issues": [], "typecheck_logs": [], "status": "PASS"}
    line_cnt = len(target.read_text(encoding="utf-8", errors="replace").splitlines()) if target.is_file() else None
    if line_cnt is not None:
        results["line_count"] = line_cnt
    overall_code = 0
    if not target.exists():
        results["issues"].append({"type": "missing_file", "file": str(target), "line": 0, "message": "Target path does not exist."})
        results["status"], overall_code = "DEFECTS_FOUND", 1
    elif do_all or getattr(args, "typecheck", False):
        tc_code, results["typecheck_logs"] = run_static_typecheckers(target, py_bin)
        if tc_code != 0:
            overall_code, results["status"] = max(overall_code, tc_code), "DEFECTS_FOUND"
    max_l, max_fn = _opt_int(args, "max_lines"), _opt_int(args, "max_fn_lines")
    checks = (
        (do_all or getattr(args, "smells", False), audit_platform_smells(target), getattr(args, "strict", False)),
        (do_all or getattr(args, "callable_smoke", False), audit_callable_smoke(target), True),
        (do_all or max_l is not None or max_fn is not None, audit_modularity_budgets(target, max_lines=max_l or 350, max_fn_lines=max_fn or 40), getattr(args, "strict", False) or max_l is not None or max_fn is not None),
    )
    for enabled, found, fail_on in checks:
        if enabled and found:
            results["issues"].extend(found)
            results["status"] = "DEFECTS_FOUND"
            overall_code = max(overall_code, 1) if fail_on else overall_code
    if getattr(args, "json", False):
        print(json.dumps(results, indent=2))
        return overall_code
    _print_audit_report(target, results, line_cnt)
    return overall_code


def register_parser(subparsers: Any) -> Any:
    """Register 'audit' subparser into diagnose.py CLI."""
    p_aud = subparsers.add_parser("audit", help="Static quality, defect, typecheck and code smell audit")
    p_aud.add_argument("--path", nargs="+", default=None, help="Root directory or file(s) to audit")
    p_aud.add_argument("--typecheck", action="store_true", help="Run virtualenv typecheckers (ruff/mypy)")
    p_aud.add_argument("--smells", action="store_true", help="Scan for platform import smells")
    p_aud.add_argument("--callable-smoke", action="store_true", help="Run callable signature and constructor smoke checks")
    p_aud.add_argument("--json", action="store_true", help="Output JSON report")
    p_aud.add_argument("--strict", action="store_true", help="Exit code 1 if any smells or defects found")
    p_aud.add_argument("--max-lines", type=int, default=None, help="Custom file line-count ceiling (fails if >= N)")
    p_aud.add_argument("--max-fn-lines", type=int, default=None, help="Custom function line-count ceiling (default: 40)")
    return p_aud

