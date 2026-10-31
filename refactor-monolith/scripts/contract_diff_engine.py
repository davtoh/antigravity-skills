#!/usr/bin/env python3
"""Cross-platform contract diff engine, surface aggregator, and regression detector.

Builds and diffs CodebaseContract representations across HTML, JS, Python, and CSS
without external dependencies.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from campaign_manager import get_git_sha
from surface_scanners import (
    scan_css_surface,
    scan_html_surface,
    scan_js_surface,
    scan_python_surface,
)

IGNORED_DIRS: frozenset[str] = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "dist", "build", "_build", "out", "target", ".idea", ".vscode",
    "scratch", "coverage", "htmlcov", "migrations", ".refactor",
})


@dataclass
class CodebaseContract:
    """Aggregated contract of interactive and public architectural surfaces."""
    commit_sha: str = ""
    html_ids: list[str] = field(default_factory=list)
    select_ids: list[str] = field(default_factory=list)
    inline_handlers: list[dict[str, str]] = field(default_factory=list)
    script_order: list[str] = field(default_factory=list)
    js_queried_ids: list[str] = field(default_factory=list)
    js_global_exports: list[str] = field(default_factory=list)
    python_routes: list[dict[str, str]] = field(default_factory=list)
    python_globals: list[str] = field(default_factory=list)
    css_important_count: int = 0
    css_custom_properties: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CodebaseContract:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def _run_git(args: list[str], cwd: Path | None = None) -> tuple[int, str]:
    """Execute a git command safely and return (exit_code, output)."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd or Path.cwd(),
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
        return proc.returncode, proc.stdout.strip()
    except Exception as err:
        return 1, str(err)


def read_file_content(path: Path, git_ref: str = "", cwd: Path | None = None) -> str:
    """Read file content either from the live filesystem or from a git ref."""
    if not git_ref:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
    code, out = _run_git(["show", f"{git_ref}:{path.as_posix()}"], cwd=cwd)
    return out if code == 0 else ""


def iter_repo_files(base_dir: Path, git_ref: str = "") -> list[Path]:
    """List source files in target directory, pruning ignored directories and git commits."""
    if git_ref:
        code, out = _run_git(["ls-tree", "-r", "--name-only", git_ref], cwd=base_dir)
        if code != 0:
            return []
        res: list[Path] = []
        for line in out.splitlines():
            line = line.strip()
            if line and not any(part in IGNORED_DIRS for part in Path(line).parts):
                res.append(Path(line))
        return res
    return [
        p for p in base_dir.rglob("*")
        if p.is_file() and not any(part in IGNORED_DIRS for part in p.parts)
    ]


def build_contract(target_dir: Path, git_ref: str = "") -> CodebaseContract:
    """Extract full contract from disk or historical git tree."""
    contract = CodebaseContract(commit_sha=git_ref or get_git_sha(target_dir))
    files = iter_repo_files(target_dir, git_ref)
    acc: dict[str, Any] = {
        "ids": set(), "selects": set(), "handlers": [], "scripts": [],
        "queried": set(), "globals": set(), "routes": [], "py_globals": set(),
        "css_vars": set(), "important": 0,
    }
    for f in sorted(files):
        sfx = f.suffix.lower()
        if sfx in {".html", ".js", ".ts", ".jsx", ".tsx", ".py", ".css", ".scss"}:
            text = read_file_content(f if git_ref else target_dir / f, git_ref, cwd=target_dir)
            if text:
                rel_p = str(f.as_posix() if hasattr(f, "as_posix") else f).replace("\\", "/")
                _dispatch_scan(sfx, text, acc, rel_path=rel_p)

    contract.html_ids = sorted(acc["ids"])
    contract.select_ids = sorted(acc["selects"])
    contract.inline_handlers = acc["handlers"]
    contract.script_order = acc["scripts"]
    contract.js_queried_ids = sorted(acc["queried"])
    contract.js_global_exports = sorted(acc["globals"])
    contract.python_routes = acc["routes"]
    contract.python_globals = sorted(acc["py_globals"])
    contract.css_important_count = acc["important"]
    contract.css_custom_properties = sorted(acc["css_vars"])
    return contract


def _dispatch_scan(sfx: str, text: str, acc: dict[str, Any], rel_path: str = "") -> None:
    """Route file text to surface scanner and aggregate results."""
    if sfx == ".html":
        h = scan_html_surface(text)
        acc["ids"].update(h.ids)
        acc["selects"].update(h.selects)
        acc["handlers"].extend(h.inline_handlers)
        acc["scripts"].extend(h.script_srcs)
    elif sfx in {".js", ".ts", ".jsx", ".tsx"}:
        j = scan_js_surface(text)
        acc["queried"].update(j.queried_ids)
        acc["globals"].update(j.global_exports)
    elif sfx == ".py":
        p = scan_python_surface(text, rel_path=rel_path)
        acc["routes"].extend(p.routes)
        acc["py_globals"].update(p.mutable_globals)
    elif sfx in {".css", ".scss"}:
        c = scan_css_surface(text)
        acc["important"] += c.important_count
        acc["css_vars"].update(c.custom_properties)


def diff_contracts(before: CodebaseContract, after: CodebaseContract) -> list[str]:
    """Compare before and after contracts and return list of critical discrepancies."""
    issues: list[str] = []

    before_missing = set(before.js_queried_ids) - set(before.html_ids) if before.js_queried_ids else set()
    current_missing = set(after.js_queried_ids) - set(after.html_ids)
    newly_missing = current_missing - before_missing
    removed_html_ids = (set(before.html_ids) - set(after.html_ids)) & set(after.js_queried_ids)

    critical_dom_ids = sorted(newly_missing | removed_html_ids)
    for mid in critical_dom_ids:
        if mid in removed_html_ids:
            issues.append(f"[CRITICAL DOM] Element id='{mid}' present before refactor was removed from HTML, but JS still queries #{mid}!")
        else:
            issues.append(f"[CRITICAL DOM] JS queries #{mid} via getElementById/querySelector, but id='{mid}' is missing in HTML!")

    for sel in sorted(set(before.select_ids) - set(after.select_ids)):
        issues.append(f"[CRITICAL SELECT] Interactive dropdown #{sel} present before refactor was removed or renamed!")

    for g in sorted(set(before.js_global_exports) - set(after.js_global_exports)):
        issues.append(f"[CRITICAL GLOBAL] Pre-refactor window.{g} export was lost during decomposition!")

    _check_handlers_and_routes(before, after, issues)

    if after.css_important_count > before.css_important_count:
        issues.append(f"[CRITICAL CSS] !important count increased from {before.css_important_count} to {after.css_important_count}!")

    return issues


def _check_handlers_and_routes(before: CodebaseContract, after: CodebaseContract, issues: list[str]) -> None:
    """Validate that inline event handlers and Python routes were preserved."""
    for h in after.inline_handlers:
        target = h["target"].split(".")[0]
        if target not in {"document", "window", "event", "this", "console"} and target not in after.js_global_exports:
            if not target.startswith(("let ", "var ", "const ", "if", "return")):
                issues.append(f"[CRITICAL HANDLER] HTML inline {h['event']} references '{h['target']}' but it is not exported on window!")
    before_routes = {f"{r.get('method')} {r.get('path')}" for r in before.python_routes}
    after_routes = {f"{r.get('method')} {r.get('path')}" for r in after.python_routes}
    for lost_r in sorted(before_routes - after_routes):
        issues.append(f"[CRITICAL ROUTE] API route {lost_r} present before refactor is missing in refactored routers!")
