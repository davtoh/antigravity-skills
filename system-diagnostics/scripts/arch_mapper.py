#!/usr/bin/env python3
"""Architecture, Modularity & Integration Mapper (system-diagnostics).

Generates a compact JSON or Markdown architectural snapshot of any repository:
- Modularity budgets (file lines >= 350/500, class methods > 12, functions > 40L)
- Backend API routes & CLI argparse entrypoints
- Internal package import coupling graph
- Unused symbol imports (excluding __init__.py re-exports)

Zero external dependencies; Python 3.10+ stdlib only.
"""

import argparse
import ast
import json
import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from defect_catalog import IGNORED_WORKSPACE_DIRS as IGNORED_DIRS
except ImportError:
    from .defect_catalog import IGNORED_WORKSPACE_DIRS as IGNORED_DIRS

SOURCE_EXTS = frozenset({".py", ".js", ".mjs", ".ts", ".jsx", ".tsx", ".css", ".scss", ".html"})
HTTP_METHODS = frozenset({"get", "post", "put", "delete", "patch", "websocket", "api_route"})


@dataclass
class ModuleStats:
    """Static architectural summary for a single source file."""
    path: str
    ext: str
    lines: int
    classes: list[dict[str, Any]] = field(default_factory=list)
    routes: list[dict[str, Any]] = field(default_factory=list)
    cli_flags: list[str] = field(default_factory=list)
    cli_subcommands: list[str] = field(default_factory=list)
    internal_imports: list[str] = field(default_factory=list)
    unused_imports: list[str] = field(default_factory=list)
    long_functions: list[dict[str, Any]] = field(default_factory=list)


def _iter_source_files(root: Path, include_tests: bool = False) -> list[Path]:
    """Walk repository source files while skipping ignored/hidden directories."""
    results: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in IGNORED_DIRS
            and not d.startswith(".")
            and (include_tests or d not in ("tests", "test", "__tests__"))
        )
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            if p.suffix.lower() in SOURCE_EXTS:
                results.append(p)
    return results


def _detect_local_packages(root: Path) -> set[str]:
    """Identify top-level Python package names in the repository."""
    pkgs: set[str] = set()
    for child in root.iterdir():
        if child.is_dir() and not child.name.startswith(".") and child.name not in IGNORED_DIRS:
            if (child / "__init__.py").is_file() or any(child.glob("*.py")):
                pkgs.add(child.name)
    return pkgs


def _extract_route_decorator(dec: ast.expr, router_prefix: str) -> dict[str, Any] | None:
    """Extract FastAPI/Flask route metadata from a decorator AST node."""
    if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
        return None
    method = dec.func.attr.lower()
    if method not in HTTP_METHODS:
        return None
    path_arg = ""
    if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
        path_arg = dec.args[0].value
    full_path = f"{router_prefix.rstrip('/')}/{path_arg.lstrip('/')}" if router_prefix else path_arg
    if full_path and not full_path.startswith("/"):
        full_path = "/" + full_path
    return {"method": method.upper(), "path": full_path or "/", "line": dec.lineno}


def _find_router_prefix(tree: ast.Module) -> str:
    """Find APIRouter(prefix='...') assignment if present in module."""
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            fn = node.value.func
            fn_name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
            if fn_name == "APIRouter":
                for kw in node.value.keywords:
                    if kw.arg == "prefix" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        return kw.value.value
    return ""


def _collect_used_names(tree: ast.Module) -> set[str]:
    """Collect all referenced Name/Attribute root identifiers outside import nodes."""
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Store):
            used.add(node.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # Preserve __all__ string exports from being flagged unused
            used.add(node.value)
    return used


def _analyze_python_file(path: Path, rel_path: str, text: str, local_pkgs: set[str]) -> ModuleStats:
    """Parse a Python file via AST for classes, routes, CLI flags, imports, and budgets."""
    stats = ModuleStats(path=rel_path, ext=".py", lines=len(text.splitlines()))
    try:
        tree = ast.parse(text, filename=rel_path)
    except SyntaxError:
        return stats

    router_prefix = _find_router_prefix(tree)
    used_names = _collect_used_names(tree)
    is_init = path.name == "__init__.py"
    imported_locals: list[tuple[str, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            bases = [ast.unparse(b) for b in node.bases] if hasattr(ast, "unparse") else []
            span = (node.end_lineno or node.lineno) - node.lineno + 1
            stats.classes.append({"name": node.name, "methods": len(methods), "lines": span, "bases": bases})
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            span = (node.end_lineno or node.lineno) - node.lineno + 1
            if span > 40:
                stats.long_functions.append({"name": node.name, "lines": span, "line": node.lineno})
            for dec in node.decorator_list:
                route = _extract_route_decorator(dec, router_prefix)
                if route:
                    route["handler"] = node.name
                    stats.routes.append(route)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "add_argument" and node.args:
                if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    stats.cli_flags.append(node.args[0].value)
            elif node.func.attr == "add_parser" and node.args:
                if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    stats.cli_subcommands.append(node.args[0].value)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in local_pkgs:
                    stats.internal_imports.append(alias.name)
                bound = alias.asname or top
                imported_locals.append((bound, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module:
            top = node.module.split(".")[0]
            if top in local_pkgs:
                stats.internal_imports.append(node.module)
            if not is_init and node.module != "__future__":
                for alias in node.names:
                    if alias.name != "*":
                        bound = alias.asname or alias.name
                        imported_locals.append((bound, f"{node.module}.{alias.name}"))

    if not is_init:
        stats.unused_imports = sorted({
            full for bound, full in imported_locals if bound not in used_names
        })
    stats.internal_imports = sorted(set(stats.internal_imports))
    return stats


def scan_architecture(root: Path, include_tests: bool = False) -> dict[str, Any]:
    """Scan repository architecture, modularity budgets, routes, CLI, and coupling."""
    root = root.resolve()
    local_pkgs = _detect_local_packages(root)
    files = _iter_source_files(root, include_tests=include_tests)

    modules: list[ModuleStats] = []
    dir_summary: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "lines": 0})
    pkg_edges: dict[str, set[str]] = defaultdict(set)

    for fp in files:
        rel = fp.relative_to(root).as_posix()
        text = fp.read_text(encoding="utf-8", errors="replace")
        line_count = len(text.splitlines())
        top_dir = rel.split("/", 1)[0] if "/" in rel else "."
        dir_summary[top_dir]["files"] += 1
        dir_summary[top_dir]["lines"] += line_count

        if fp.suffix == ".py":
            mod = _analyze_python_file(fp, rel, text, local_pkgs)
            for imp in mod.internal_imports:
                target_pkg = ".".join(imp.split(".")[:2])
                if top_dir != imp.split(".")[0]:
                    pkg_edges[top_dir].add(target_pkg)
        else:
            mod = ModuleStats(path=rel, ext=fp.suffix.lower(), lines=line_count)
        modules.append(mod)

    hard_files = [{"path": m.path, "lines": m.lines} for m in modules if m.lines >= 500]
    warn_files = [{"path": m.path, "lines": m.lines} for m in modules if 350 <= m.lines < 500]
    heavy_classes = [
        {"path": m.path, **c}
        for m in modules for c in m.classes if c["methods"] > 12 or c["lines"] > 300
    ]
    routes = [{"file": m.path, **r} for m in modules for r in m.routes]
    cli_surfaces = [
        {"file": m.path, "subcommands": m.cli_subcommands, "flags": sorted(set(m.cli_flags))}
        for m in modules if m.cli_subcommands or m.cli_flags
    ]
    unused = [
        {"file": m.path, "symbols": m.unused_imports}
        for m in modules if m.unused_imports
    ]

    return {
        "workspace": root.name,
        "total_files": len(modules),
        "total_lines": sum(m.lines for m in modules),
        "local_packages": sorted(local_pkgs),
        "directories": dict(sorted(dir_summary.items())),
        "modularity_violations": {
            "files_over_500": sorted(hard_files, key=lambda x: -x["lines"]),
            "files_350_to_499": sorted(warn_files, key=lambda x: -x["lines"]),
            "classes_over_budget": sorted(heavy_classes, key=lambda x: -x["methods"]),
        },
        "routes_count": len(routes),
        "routes_by_file": _group_by_file(routes),
        "cli_surfaces": cli_surfaces,
        "cross_package_coupling": {k: sorted(v) for k, v in sorted(pkg_edges.items())},
        "unused_internal_or_module_imports": unused,
    }


def _group_by_file(routes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group route dictionaries by source file path."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in routes:
        grouped[r["file"]].append({"method": r["method"], "path": r["path"], "handler": r["handler"]})
    return dict(sorted(grouped.items()))


def format_markdown(report: dict[str, Any], full: bool = False) -> str:
    """Render compact Markdown architectural snapshot."""
    lines = [
        f"# Architecture Map: `{report['workspace']}`",
        f"- **Files scanned**: {report['total_files']} | **Total lines**: {report['total_lines']:,} | **API routes**: {report['routes_count']}",
        f"- **Top-level packages**: {', '.join(f'`{p}`' for p in report['local_packages']) or 'None'}",
        "",
        "## Directory Footprint",
        "| Directory | Files | Lines |",
        "| :--- | ---: | ---: |",
    ]
    for d, st in report["directories"].items():
        lines.append(f"| `{d}` | {st['files']} | {st['lines']:,} |")

    viol = report["modularity_violations"]
    lines.extend(["", "## Modularity Budget Alerts (>= 350L / > 12 methods)"])
    for item in viol["files_over_500"]:
        lines.append(f"- **HARD (>=500L)**: `{item['path']}` ({item['lines']} lines)")
    for item in viol["files_350_to_499"]:
        lines.append(f"- **WARN (350-499L)**: `{item['path']}` ({item['lines']} lines)")
    for cls in viol["classes_over_budget"][:15]:
        lines.append(f"- **CLASS**: `{cls['path']}` -> `{cls['name']}` ({cls['methods']} methods, {cls['lines']} lines)")

    lines.extend(["", "## Cross-Package Coupling"])
    for src, targets in report["cross_package_coupling"].items():
        shown = targets if full else targets[:12]
        suffix = f" (+{len(targets) - 12} more)" if not full and len(targets) > 12 else ""
        lines.append(f"- `{src}` -> {', '.join(f'`{t}`' for t in shown)}{suffix}")

    lines.extend(["", "## Unused Imports (Potential Disconnected Modules)"])
    for item in (report["unused_internal_or_module_imports"] if full else report["unused_internal_or_module_imports"][:15]):
        lines.append(f"- `{item['file']}`: {', '.join(f'`{s}`' for s in item['symbols'])}")

    lines.extend(["", "## CLI Surfaces"])
    for cli in report["cli_surfaces"]:
        lines.append(f"- `{cli['file']}`: subcommands={cli['subcommands']} | flags={len(cli['flags'])}")

    lines.extend(["", f"## API Routes ({report['routes_count']} total)"])
    for rfile, rlist in report["routes_by_file"].items():
        lines.append(f"- `{rfile}`: {len(rlist)} routes")
        if full:
            for r in rlist:
                lines.append(f"  - `{r['method']} {r['path']}` -> `{r['handler']}`")
    return "\n".join(lines) + "\n"


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the 'arch-map' subcommand in diagnose.py."""
    p = subparsers.add_parser("arch-map", help="Generate compact architecture, modularity, route, and coupling map")
    p.add_argument("--path", default=None, help="Root directory to scan (default: current directory)")
    p.add_argument("--include-tests", action="store_true", help="Include test directories in scan")
    p.add_argument("--json", action="store_true", help="Output structured JSON instead of Markdown")
    p.add_argument("--full", action="store_true", help="Include full route and symbol lists without truncation")
    p.add_argument("--out", default=None, help="Optional output file path (.md or .json)")


def cmd_arch_map(args: argparse.Namespace) -> int:
    """Execute the arch-map diagnostic command."""
    target = Path(args.path).resolve() if getattr(args, "path", None) else Path.cwd()
    report = scan_architecture(target, include_tests=getattr(args, "include_tests", False))
    output = json.dumps(report, indent=2) if getattr(args, "json", False) else format_markdown(report, full=getattr(args, "full", False))
    out_path = getattr(args, "out", None)
    if out_path:
        Path(out_path).write_bytes(output.encode("utf-8"))
        print(f"[diagnose arch-map] Wrote architecture map to {out_path}")
    else:
        print(output)
    return 0

