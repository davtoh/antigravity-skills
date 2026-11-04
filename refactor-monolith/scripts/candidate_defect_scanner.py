#!/usr/bin/env python3
"""Standard-library AST candidate defect scanner for refactor-monolith.

High-signal static checks only:
- SYNTAX_ERROR
- MUTABLE_DEFAULT_ARG
- UNREACHABLE_CODE
- UNDEFINED_NAME
"""

import ast
import builtins
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

@dataclass
class DefectEntry:
    """Intermediate representation of an AST-discovered candidate defect."""

    rule_id: str
    file: str
    line: int
    symbol: str
    message: str
    suggested_fix: str = ""
    severity: str = "HIGH"
    track: str = "tactical"

    def to_dict(self) -> dict[str, Any]:
        """Convert entry to SSOT defect catalog schema dictionary."""
        return {
            "id": "",
            "fingerprint": "",
            "rule_id": self.rule_id,
            "category": "BAD_LOGIC" if self.rule_id != "SYNTAX_ERROR" else "SYNTAX",
            "severity": self.severity,
            "track": self.track,
            "file": self.file.replace("\\", "/"),
            "line": self.line,
            "symbol": self.symbol,
            "message": self.message,
            "suggested_fix": self.suggested_fix,
            "status": "quarantined",
        }

_BUILTIN_NAMES: frozenset[str] = frozenset(dir(builtins)) | {
    "__file__", "__name__", "__doc__", "__all__", "__package__", "__spec__",
    "__annotations__", "__builtins__",
}

def _collect_module_names(tree: ast.AST) -> tuple[set[str], bool]:
    """Extract top-level imports, functions, classes, and global assignments."""
    mod_names: set[str] = set()
    has_star_import = False
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod_names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if any(a.name == "*" for a in node.names):
                has_star_import = True
            for alias in node.names:
                mod_names.add(alias.asname or alias.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            mod_names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name):
                    mod_names.add(t.id)
    return mod_names, has_star_import

def _check_mutable_defaults(node: Any, file_path: str) -> list[DefectEntry]:
    """Detect mutable lists, dicts, or sets in function default arguments."""
    findings: list[DefectEntry] = []
    for d, p in zip(reversed(node.args.defaults), reversed(node.args.args)):
        if isinstance(d, (ast.List, ast.Dict, ast.Set)):
            t_name = "[]" if isinstance(d, ast.List) else ("{}" if isinstance(d, ast.Dict) else "set()")
            findings.append(DefectEntry(
                rule_id="MUTABLE_DEFAULT_ARG", file=file_path, line=node.lineno, symbol=f"{node.name}.{p.arg}",
                message=f"Mutable default argument '{p.arg}={t_name}' persists mutated state across calls.",
                suggested_fix=f"Replace '{p.arg}={t_name}' with '{p.arg}=None' and initialize inside '{node.name}()'.",
            ))
    for d, p in zip(node.args.kw_defaults, node.args.kwonlyargs):
        if d is not None and isinstance(d, (ast.List, ast.Dict, ast.Set)):
            t_name = "[]" if isinstance(d, ast.List) else ("{}" if isinstance(d, ast.Dict) else "set()")
            findings.append(DefectEntry(
                rule_id="MUTABLE_DEFAULT_ARG", file=file_path, line=node.lineno, symbol=f"{node.name}.{p.arg}",
                message=f"Mutable default keyword argument '{p.arg}={t_name}' persists mutated state across calls.",
                suggested_fix=f"Replace '{p.arg}={t_name}' with '{p.arg}=None' and initialize inside '{node.name}()'.",
            ))
    return findings

def _check_unreachable_code(node: Any, file_path: str) -> list[DefectEntry]:
    """Detect unreachable statements following early return, raise, break, or continue."""
    findings: list[DefectEntry] = []
    for i, stmt in enumerate(node.body[:-1]):
        if isinstance(stmt, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
            dead = node.body[i + 1]
            findings.append(DefectEntry(
                rule_id="UNREACHABLE_CODE", file=file_path, line=dead.lineno, symbol=node.name,
                message=f"Statement at line {dead.lineno} is unreachable after '{type(stmt).__name__.lower()}'.",
                suggested_fix=f"Remove unreachable statement at line {dead.lineno} or guard prior branch.",
                severity="MEDIUM",
            ))
            break
    return findings

def _check_undefined_names(node: Any, file_path: str, mod_names: set[str]) -> list[DefectEntry]:
    """Detect loaded variables that have no local, module, or builtin binding."""
    findings: list[DefectEntry] = []
    local_names = {a.arg for a in node.args.args} | {a.arg for a in node.args.kwonlyargs}
    if node.args.vararg:
        local_names.add(node.args.vararg.arg)
    if node.args.kwarg:
        local_names.add(node.args.kwarg.arg)
    for sub in ast.walk(node):
        if isinstance(sub, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            stargets = sub.targets if isinstance(sub, ast.Assign) else [sub.target]
            for st in stargets:
                if isinstance(st, ast.Name):
                    local_names.add(st.id)
        elif isinstance(sub, (ast.For, ast.AsyncFor)) and isinstance(sub.target, ast.Name):
            local_names.add(sub.target.id)
        elif isinstance(sub, (ast.ExceptHandler, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and sub.name:
            local_names.add(sub.name)
        elif isinstance(sub, (ast.Global, ast.Nonlocal)):
            local_names.update(sub.names)
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
            if sub.id not in local_names and sub.id not in mod_names and sub.id not in _BUILTIN_NAMES:
                findings.append(DefectEntry(
                    rule_id="UNDEFINED_NAME", file=file_path, line=sub.lineno, symbol=sub.id,
                    message=f"Undefined name '{sub.id}' referenced in function '{node.name}'.",
                    suggested_fix=f"Define or import '{sub.id}' before referencing.",
                ))
    return findings

def _scan_py_ast_defects(source_text: str, file_path: str) -> list[DefectEntry]:
    """Inspect Python AST for SYNTAX_ERROR, MUTABLE_DEFAULT_ARG, UNREACHABLE_CODE, UNDEFINED_NAME."""
    try:
        tree = ast.parse(source_text, filename=file_path)
    except SyntaxError as err:
        return [DefectEntry(
            rule_id="SYNTAX_ERROR", file=file_path, line=err.lineno or 1, symbol=Path(file_path).name,
            message=f"SyntaxError: {err.msg}", suggested_fix="Fix syntax error before refactoring.",
        )]
    except Exception:
        return []

    mod_names, has_star = _collect_module_names(tree)
    findings: list[DefectEntry] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            findings.extend(_check_mutable_defaults(node, file_path))
            findings.extend(_check_unreachable_code(node, file_path))
            if not has_star:
                findings.extend(_check_undefined_names(node, file_path, mod_names))
    return findings

def scan_candidate_defects(candidate_paths: list[Path]) -> list[DefectEntry]:
    """Scan candidate Python source files for high-signal latent defects via standard library AST."""
    findings: list[DefectEntry] = []
    for p in candidate_paths:
        if p.is_file() and p.suffix.lower() == ".py":
            try:
                findings.extend(_scan_py_ast_defects(p.read_text(encoding="utf-8", errors="replace"), str(p)))
            except Exception:
                continue
    return findings

def save_defect_catalog(root: Path, defects: list[dict[str, Any]], mod_catalog: Any = None) -> tuple[Path, Path]:
    """Persist defect catalog JSON and human-readable DEFECT_CATALOG.md."""
    if mod_catalog:
        return mod_catalog.save_catalog(root, defects)
    diag_dir = root / ".diagnostics"
    diag_dir.mkdir(parents=True, exist_ok=True)
    json_path = diag_dir / "defect_catalog.json"
    json_path.write_text(
        json.dumps({"schema_version": "1.0", "workspace": str(root.as_posix()), "defects": defects}, indent=2),
        encoding="utf-8",
    )
    md_path = diag_dir / "DEFECT_CATALOG.md"
    lines = [
        "# SSOT Latent Defect & Smell Catalog", "",
        f"**Workspace**: `{root.as_posix()}`", f"**Total Defects**: {len(defects)}", "",
        "| ID | Severity | Track | File & Line | Symbol | Rule | Message | Status |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for d in defects:
        f_loc = f"{d.get('file', '')}:{d.get('line', 1)}"
        lines.append(
            f"| `{d.get('id', '')}` | {d.get('severity', 'MEDIUM')} | `{d.get('track', 'tactical')}` | "
            f"`{f_loc}` | `{d.get('symbol', '')}` | `{d.get('rule_id', '')}` | "
            f"{str(d.get('message', '')).replace('|', '/')} | `{d.get('status', 'quarantined')}` |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path

def _resolve_py_candidates(target: Path) -> list[Path]:
    """Find eligible Python files in target, excluding test and build folders."""
    if target.is_file():
        return [target] if target.suffix.lower() == ".py" else []
    return [
        p for p in target.rglob("*.py")
        if not any(ign in p.parts for ign in ("__pycache__", ".venv", "venv", ".refactor", ".diagnostics", "tests", "test"))
    ] if target.is_dir() else []

def _link_defect_catalog_in_plan(plan_p: str, root: Path, defect_count: int, target_name: str) -> None:
    """Link DEFECT_CATALOG.md in target plan.md, creating plan.md if needed."""
    plan_file = Path(plan_p) if Path(plan_p).is_absolute() else root / plan_p
    note = (
        f"\n> [!NOTE]\n"
        f"> **Quarantined Defect Catalog**: {defect_count} candidate defect(s) quarantined in `.diagnostics/DEFECT_CATALOG.md`.\n"
        f"> The refactoring campaign maintains strictly zero behavioral modification ($\\Delta\\text{{Behavior}} \\equiv 0$).\n"
        f"> Defect remediation is deferred to `/app-debugger` in a dedicated session upon campaign completion.\n"
    )
    if plan_file.exists():
        content = plan_file.read_text(encoding="utf-8", errors="replace")
        if "DEFECT_CATALOG.md" not in content:
            plan_file.write_text(content + note, encoding="utf-8")
    else:
        plan_file.parent.mkdir(parents=True, exist_ok=True)
        plan_file.write_text(
            f"# Refactoring Plan: {target_name}\n\nTarget: `{target_name}`\n{note}\n"
            f"## Phase 1: Structural Slicing\n- [ ] Extract submodules\n- [ ] Verify contract parity\n",
            encoding="utf-8",
        )

def run_candidate_defect_scan(target: Path, plan_p: str, root: Path, mod_catalog: Any = None) -> None:
    """Scan candidate source files for latent defects, writing .diagnostics/ and linking in plan.md."""
    findings = scan_candidate_defects(_resolve_py_candidates(target))
    if not findings:
        print("[Opt-In Scan] Candidate defect scan completed: 0 defects detected.")
        return
    defects = []
    for i, f in enumerate(findings, 1):
        d_dict = f.to_dict()
        d_dict["id"] = f"DEFECT-{i:03d}"
        prefix = f.rule_id.split("_")[0][:7].upper()
        h = hashlib.sha256(f"{f.rule_id}:{f.symbol}:{f.line}".encode("utf-8")).hexdigest()[:6]
        d_dict["fingerprint"] = f"DEF-{prefix}-{h}"
        defects.append(d_dict)
    json_path, _ = save_defect_catalog(root, defects, mod_catalog=mod_catalog)
    print(f"[Opt-In Scan] Discovered and quarantined {len(defects)} candidate defect(s) in {json_path}")
    _link_defect_catalog_in_plan(plan_p, root, len(defects), target.name)
