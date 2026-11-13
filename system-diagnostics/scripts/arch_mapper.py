#!/usr/bin/env python3
"""Architecture, Modularity & Integration Mapper (system-diagnostics).

Complements surface_scanners.py and static_auditor.py by generating a compact
JSON or Markdown architectural snapshot of any repository:
- Modularity budgets (file lines >= 350/500, class methods > 12, functions > 40L)
- Backend API routes (via surface_scanners) & CLI argparse entrypoints
- Internal package import coupling graph & unused symbol imports
- CSS !important specificity alerts (via surface_scanners)

Zero external dependencies; Python 3.10+ stdlib only.
"""

import argparse
import ast
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import surface_scanners
    from defect_catalog import IGNORED_WORKSPACE_DIRS as IGNORED_DIRS
except ImportError:
    from . import surface_scanners
    from .defect_catalog import IGNORED_WORKSPACE_DIRS as IGNORED_DIRS


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
    css_important: int = 0


def _iter_source_files(root: Path, include_tests: bool = False) -> list[Path]:
    """Reuse surface_scanners.walk_source_files to collect sorted repo source files."""
    grouped = surface_scanners.walk_source_files(root, include_tests=include_tests)
    combined = [p for paths in grouped.values() for p in paths]
    return sorted(combined)


def _resolve_scan_base(root: Path) -> Path:
    """Resolve containing project/package root directory when ``root`` is a file."""
    base_dir = root if root.is_dir() else root.parent
    while (base_dir / "__init__.py").is_file() and base_dir.parent != base_dir:
        base_dir = base_dir.parent
    return base_dir


def _detect_local_packages(root: Path) -> set[str]:
    """Identify top-level Python package names in the repository."""
    pkgs: set[str] = set()
    scan_dir = _resolve_scan_base(root)
    if not scan_dir.is_dir():
        return pkgs
    for child in scan_dir.iterdir():
        if child.is_dir() and not child.name.startswith(".") and child.name not in IGNORED_DIRS:
            if (child / "__init__.py").is_file() or any(child.glob("*.py")):
                pkgs.add(child.name)
    return pkgs


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


def _apply_router_prefix(routes: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    """Prepend APIRouter prefix to routes extracted by surface_scanners."""
    normalized: list[dict[str, Any]] = []
    for r in routes:
        path_arg = r.get("path", "")
        full_path = f"{prefix.rstrip('/')}/{path_arg.lstrip('/')}" if prefix else path_arg
        if full_path and not full_path.startswith("/"):
            full_path = "/" + full_path
        normalized.append({**r, "path": full_path or "/"})
    return normalized


def _collect_annotation_strings(node: ast.AST, used: set[str]) -> None:
    """Collect stringified type names inside annotations without matching docstrings."""
    ann_nodes: list[ast.AST | None] = []
    if isinstance(node, ast.AnnAssign):
        ann_nodes.append(node.annotation)
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        ann_nodes.append(node.returns)
        for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
            ann_nodes.append(arg.annotation)
        if node.args.vararg:
            ann_nodes.append(node.args.vararg.annotation)
        if node.args.kwarg:
            ann_nodes.append(node.args.kwarg.annotation)
    for ann in ann_nodes:
        if ann is None:
            continue
        for sub in ast.walk(ann):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                used.add(sub.value.split(".")[0].split("[")[0].strip())


def _collect_used_names(tree: ast.Module, all_exports: list[str]) -> set[str]:
    """Collect referenced identifiers, __all__ exports, and string annotations."""
    used: set[str] = set(all_exports)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Store):
            used.add(node.id)
        elif isinstance(node, (ast.AnnAssign, ast.FunctionDef, ast.AsyncFunctionDef)):
            _collect_annotation_strings(node, used)
    return used


def _walk_python_ast(tree: ast.Module, stats: ModuleStats, local_pkgs: set[str]) -> list[tuple[str, str]]:
    """Populate classes, long functions, CLI flags, and import edges from AST."""
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
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("add_argument", "add_parser") and node.args:
                arg0 = node.args[0]
                if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                    target = stats.cli_flags if node.func.attr == "add_argument" else stats.cli_subcommands
                    target.append(arg0.value)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in local_pkgs:
                    stats.internal_imports.append(alias.name)
                imported_locals.append((alias.asname or top, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module:
            top = node.module.split(".")[0]
            if top in local_pkgs:
                stats.internal_imports.append(node.module)
            if node.module != "__future__":
                for alias in node.names:
                    if alias.name != "*":
                        imported_locals.append((alias.asname or alias.name, f"{node.module}.{alias.name}"))
    return imported_locals


def _analyze_python_file(path: Path, rel_path: str, text: str, local_pkgs: set[str]) -> ModuleStats:
    """Analyze a Python file by composing surface_scanners with AST architectural metrics."""
    stats = ModuleStats(path=rel_path, ext=".py", lines=len(text.splitlines()))
    try:
        tree = ast.parse(text, filename=rel_path)
    except SyntaxError:
        return stats

    py_surf = surface_scanners.scan_python_surface(text, rel_path=rel_path)
    stats.routes = _apply_router_prefix(py_surf.routes, _find_router_prefix(tree))
    used_names = _collect_used_names(tree, py_surf.all_exports)
    imported_locals = _walk_python_ast(tree, stats, local_pkgs)

    if path.name != "__init__.py":
        stats.unused_imports = sorted({
            full for bound, full in imported_locals if bound not in used_names
        })
    stats.internal_imports = sorted(set(stats.internal_imports))
    return stats


def _group_by_file(routes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group route dictionaries by source file path."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in routes:
        grouped[r["file"]].append({"method": r["method"], "path": r["path"], "handler": r["handler"]})
    return dict(sorted(grouped.items()))


def _build_report_dict(
    root: Path, local_pkgs: set[str], modules: list[ModuleStats],
    dir_summary: dict[str, dict[str, int]], pkg_edges: dict[str, set[str]],
) -> dict[str, Any]:
    """Assemble structured architecture report dictionary from scanned modules."""
    routes = [{"file": m.path, **r} for m in modules for r in m.routes]
    long_fns = [{"path": m.path, **fn} for m in modules for fn in m.long_functions]
    return {
        "workspace": root.name,
        "total_files": len(modules),
        "total_lines": sum(m.lines for m in modules),
        "local_packages": sorted(local_pkgs),
        "directories": dict(sorted(dir_summary.items())),
        "modularity_violations": {
            "files_over_500": sorted([{"path": m.path, "lines": m.lines} for m in modules if m.lines >= 500], key=lambda x: -x["lines"]),
            "files_350_to_499": sorted([{"path": m.path, "lines": m.lines} for m in modules if 350 <= m.lines < 500], key=lambda x: -x["lines"]),
            "classes_over_budget": sorted([{"path": m.path, **c} for m in modules for c in m.classes if c["methods"] > 12 or c["lines"] > 300], key=lambda x: -x["methods"]),
            "functions_over_40": sorted(long_fns, key=lambda x: -x["lines"]),
            "css_important_files": [{"path": m.path, "count": m.css_important} for m in modules if m.css_important > 0],
        },
        "routes_count": len(routes),
        "routes_by_file": _group_by_file(routes),
        "cli_surfaces": [{"file": m.path, "subcommands": m.cli_subcommands, "flags": sorted(set(m.cli_flags))} for m in modules if m.cli_subcommands or m.cli_flags],
        "cross_package_coupling": {k: sorted(v) for k, v in sorted(pkg_edges.items())},
        "unused_internal_or_module_imports": [{"file": m.path, "symbols": m.unused_imports} for m in modules if m.unused_imports],
    }


def scan_architecture(root: Path, include_tests: bool = False) -> dict[str, Any]:
    """Scan repository architecture, modularity budgets, routes, CLI, and coupling."""
    root = root.resolve()
    base_dir = _resolve_scan_base(root) if root.is_file() else root
    local_pkgs = _detect_local_packages(base_dir)
    files = _iter_source_files(root, include_tests=include_tests)
    modules: list[ModuleStats] = []
    dir_summary: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "lines": 0})
    pkg_edges: dict[str, set[str]] = defaultdict(set)

    for fp in files:
        rel = fp.relative_to(base_dir).as_posix()
        text = fp.read_text(encoding="utf-8", errors="replace")
        line_count = len(text.splitlines())
        top_dir = rel.split("/", 1)[0] if "/" in rel else "."
        dir_summary[top_dir]["files"] += 1
        dir_summary[top_dir]["lines"] += line_count

        if fp.suffix == ".py":
            mod = _analyze_python_file(fp, rel, text, local_pkgs)
            for imp in mod.internal_imports:
                if top_dir != imp.split(".")[0]:
                    pkg_edges[top_dir].add(".".join(imp.split(".")[:2]))
        else:
            imp_cnt = surface_scanners.scan_css_surface(text).important_count if fp.suffix.lower() in (".css", ".scss") else 0
            mod = ModuleStats(path=rel, ext=fp.suffix.lower(), lines=line_count, css_important=imp_cnt)
        modules.append(mod)

    return _build_report_dict(root, local_pkgs, modules, dir_summary, pkg_edges)


def _format_modularity_section(viol: dict[str, Any], full: bool) -> list[str]:
    """Render modularity budget alerts for files, classes, long functions, and CSS."""
    lines = ["", "## Modularity Budget Alerts (>= 350L / > 12 methods / > 40L fn)"]
    for item in viol["files_over_500"]:
        lines.append(f"- **HARD (>=500L)**: `{item['path']}` ({item['lines']} lines)")
    for item in viol["files_350_to_499"]:
        lines.append(f"- **WARN (350-499L)**: `{item['path']}` ({item['lines']} lines)")
    cls_list = viol["classes_over_budget"]
    for cls in (cls_list if full else cls_list[:15]):
        lines.append(f"- **CLASS**: `{cls['path']}` -> `{cls['name']}` ({cls['methods']} methods, {cls['lines']} lines)")
    if not full and len(cls_list) > 15:
        lines.append(f"- *... and {len(cls_list) - 15} more class alert(s) omitted (pass `--full` to view all).*")
    fn_list = viol.get("functions_over_40", [])
    for fn in (fn_list if full else fn_list[:10]):
        lines.append(f"- **FUNC (>40L)**: `{fn['path']}:{fn['line']}` -> `{fn['name']}` ({fn['lines']} lines)")
    if not full and len(fn_list) > 10:
        lines.append(f"- *... and {len(fn_list) - 10} more function alert(s) omitted (pass `--full` to view all).*")
    for css in viol.get("css_important_files", []):
        lines.append(f"- **CSS (!important)**: `{css['path']}` ({css['count']} occurrences)")
    return lines


def _format_surfaces_section(report: dict[str, Any], full: bool) -> list[str]:
    """Render coupling, unused imports, CLI surfaces, and API routes."""
    lines = ["", "## Cross-Package Coupling"]
    for src, targets in report["cross_package_coupling"].items():
        shown = targets if full else targets[:12]
        suffix = f" (+{len(targets) - 12} more)" if not full and len(targets) > 12 else ""
        lines.append(f"- `{src}` -> {', '.join(f'`{t}`' for t in shown)}{suffix}")

    lines.extend(["", "## Unused Imports (Potential Disconnected Modules)"])
    unused_all = report["unused_internal_or_module_imports"]
    for item in (unused_all if full else unused_all[:30]):
        lines.append(f"- `{item['file']}`: {', '.join(f'`{s}`' for s in item['symbols'])}")
    if not full and len(unused_all) > 30:
        lines.append(f"- *... and {len(unused_all) - 30} more file(s) omitted (pass `--full` to view all).*")

    lines.extend(["", "## CLI Surfaces"])
    for cli in report["cli_surfaces"]:
        lines.append(f"- `{cli['file']}`: subcommands={cli['subcommands']} | flags={len(cli['flags'])}")

    lines.extend(["", f"## API Routes ({report['routes_count']} total)"])
    for rfile, rlist in report["routes_by_file"].items():
        lines.append(f"- `{rfile}`: {len(rlist)} routes")
        if full:
            for r in rlist:
                lines.append(f"  - `{r['method']} {r['path']}` -> `{r['handler']}`")
    return lines


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
    lines.extend(_format_modularity_section(report["modularity_violations"], full=full))
    lines.extend(_format_surfaces_section(report, full=full))
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
