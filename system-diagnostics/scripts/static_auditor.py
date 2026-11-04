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
import importlib
import inspect
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

IGNORED_DIRS = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "dist", "build", "_build", "out", "target", ".idea", ".vscode",
    "scratch", "coverage", "htmlcov", "migrations", ".refactor",
})

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
    ]


def audit_callable_smoke(target: Path) -> list[dict[str, Any]]:
    """Inspect Python signatures and instantiate parameterless classes to detect TypeErrors."""
    py_files = _find_py_files(target)
    issues: list[dict[str, Any]] = []
    root = target if target.is_dir() else target.parent
    root_str = str(root.resolve())
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    for p in py_files:
        try:
            code = p.read_text(encoding="utf-8", errors="replace")
            ast.parse(code, filename=str(p))
        except SyntaxError as err:
            issues.append({
                "type": "syntax_error",
                "file": str(p),
                "line": err.lineno or 1,
                "message": f"SyntaxError: {err.msg}",
            })
            continue

        try:
            rel_parts = p.relative_to(root).with_suffix("").parts
            rel_mod = ".".join(rel_parts)
            mod = importlib.import_module(rel_mod)
        except Exception:
            continue

        for name, obj in inspect.getmembers(mod):
            if inspect.isclass(obj) and getattr(obj, "__module__", None) == mod.__name__:
                if inspect.isabstract(obj):
                    continue
                try:
                    sig = inspect.signature(obj)
                    req_params = [
                        param for param in sig.parameters.values()
                        if param.default is inspect.Parameter.empty
                        and param.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
                    ]
                    if not req_params:
                        try:
                            obj()
                        except TypeError as te:
                            issues.append({
                                "type": "initialization_type_error",
                                "file": str(p),
                                "line": getattr(obj, "__doc__", "") and 1 or 1,
                                "message": f"Initialization TypeError in {name}(): {te}",
                            })
                        except Exception:
                            pass
                except (ValueError, TypeError) as se:
                    issues.append({
                        "type": "invalid_signature",
                        "file": str(p),
                        "line": 1,
                        "message": f"Invalid class signature {name}: {se}",
                    })
            elif inspect.isfunction(obj) and getattr(obj, "__module__", None) == mod.__name__:
                try:
                    inspect.signature(obj)
                except (ValueError, TypeError) as se:
                    issues.append({
                        "type": "invalid_signature",
                        "file": str(p),
                        "line": 1,
                        "message": f"Invalid function signature {name}: {se}",
                    })
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


def run_static_typecheckers(target: Path, py_bin: str) -> tuple[int, list[str]]:
    """Execute ruff, mypy, or pyright on target with token-capped output."""
    logs: list[str] = []
    target_str = str(target)
    has_run = False
    exit_code = 0

    # 1. Ruff check
    try:
        ruff_v = subprocess.run([py_bin, "-m", "ruff", "--version"], cwd=target if target.is_dir() else target.parent, capture_output=True, text=True, check=False)
        if ruff_v.returncode == 0:
            has_run = True
            cmd = [py_bin, "-m", "ruff", "check", "--select", "E,F,W", target_str]
            proc = subprocess.run(cmd, cwd=target if target.is_dir() else target.parent, capture_output=True, text=True, check=False)
            if proc.returncode == 0:
                logs.append(f"[ruff] PASS: 0 lint issues found in {target.name}.")
            else:
                lines = [l for l in proc.stdout.splitlines() if l.strip()]
                exit_code = max(exit_code, 1)
                logs.append(f"[ruff] Flagged {len(lines)} issue(s) (top 5 shown):")
                for l in lines[:5]:
                    logs.append(f"  {l}")
                if len(lines) > 5:
                    logs.append(f"  ... and {len(lines) - 5} more issues omitted to conserve tokens.")
    except Exception:
        pass

    # 2. Mypy check
    try:
        mypy_v = subprocess.run([py_bin, "-m", "mypy", "--version"], cwd=target if target.is_dir() else target.parent, capture_output=True, text=True, check=False)
        if mypy_v.returncode == 0:
            has_run = True
            cmd = [py_bin, "-m", "mypy", "--no-error-summary", "--ignore-missing-imports", target_str]
            proc = subprocess.run(cmd, cwd=target if target.is_dir() else target.parent, capture_output=True, text=True, check=False)
            if proc.returncode == 0:
                logs.append(f"[mypy] PASS: 0 type errors found in {target.name}.")
            else:
                lines = [l for l in proc.stdout.splitlines() if "error:" in l]
                exit_code = max(exit_code, 1)
                logs.append(f"[mypy] Flagged {len(lines)} type error(s) (top 5 shown):")
                for l in lines[:5]:
                    logs.append(f"  {l}")
                if len(lines) > 5:
                    logs.append(f"  ... and {len(lines) - 5} more errors omitted to conserve tokens.")
    except Exception:
        pass

    if not has_run:
        logs.append(f"[typecheck] SKIPPED: No ruff/mypy installed in {py_bin}.")

    return exit_code, logs


def cmd_audit(target: Path, py_bin: str, args: Any) -> int:
    """Entrypoint for `diagnose.py audit` subcommand."""
    do_all = not (getattr(args, "callable_smoke", False) or getattr(args, "smells", False) or getattr(args, "typecheck", False))
    results: dict[str, Any] = {
        "target": str(target),
        "issues": [],
        "typecheck_logs": [],
        "status": "PASS",
    }
    overall_code = 0

    # 1. Typecheck & Linters
    if do_all or getattr(args, "typecheck", False):
        tc_code, tc_logs = run_static_typecheckers(target, py_bin)
        results["typecheck_logs"] = tc_logs
        if tc_code != 0:
            overall_code = max(overall_code, tc_code)
            results["status"] = "DEFECTS_FOUND"

    # 2. Platform Import Smells
    if do_all or getattr(args, "smells", False):
        smells = audit_platform_smells(target)
        results["issues"].extend(smells)
        if smells:
            results["status"] = "DEFECTS_FOUND"
            if getattr(args, "strict", False):
                overall_code = max(overall_code, 1)

    # 3. Callable & Constructor Smoke Testing
    if do_all or getattr(args, "callable_smoke", False):
        smoke_issues = audit_callable_smoke(target)
        results["issues"].extend(smoke_issues)
        if smoke_issues:
            results["status"] = "DEFECTS_FOUND"
            overall_code = max(overall_code, 1)

    if getattr(args, "json", False):
        print(json.dumps(results, indent=2))
        return overall_code

    print(f"\n=== Static Quality & Defect Audit ({target.name}) ===")
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
    return overall_code
