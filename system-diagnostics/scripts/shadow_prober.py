#!/usr/bin/env python3
"""Polyglot Shadow Prober, Defect Scanner & JIT Scaffolder (system-diagnostics).

Scans codebases for latent bugs, vulnerabilities, callable mismatches,
exception smells, and modularity/resource defects across Python, JS/TS, CSS, and Dart.
Ground-truth state is stored in <workspace>/.diagnostics/defect_catalog.json (SSOT).
"""

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

try:
    from defect_catalog import (
        check_git_dirty, checkout_micro_branch, load_catalog,
        reconcile_defect, save_catalog, scaffold_defect, scaffold_tactical_test,
    )
except ImportError:
    from .defect_catalog import (
        check_git_dirty, checkout_micro_branch, load_catalog,
        reconcile_defect, save_catalog, scaffold_defect, scaffold_tactical_test,
    )

IGNORED_DIRS = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "dist", "build", "_build", "out", "target", ".idea", ".vscode",
    "scratch", "coverage", "htmlcov", "migrations", ".refactor",
})
SECRET_REGEX = re.compile(
    r"""(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|private[_-]?key|password)\s*[:=]\s*['"][a-zA-Z0-9_\-\.]{16,}['"]"""
)
DUMMY_SECRET_WORDS = frozenset({"test", "fake", "dummy", "example", "placeholder", "xxx", "sample"})


@dataclass
class DefectFinding:
    """Authoritative representation of a discovered latent defect."""
    id: str
    fingerprint: str
    rule_id: str
    category: str
    severity: str
    track: str
    file: str
    line: int
    symbol: str
    message: str
    suggested_fix: str
    status: str = "quarantined"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_fingerprint(rule_id: str, symbol: str, normalized_code: str) -> str:
    """Generate immutable content-addressable hash DEF-<RULE_PREFIX>-<6HEX>."""
    prefix = rule_id.split("_")[0][:7].upper()
    h = hashlib.sha256(f"{rule_id}:{symbol}:{normalized_code.strip()}".encode("utf-8")).hexdigest()[:6]
    return f"DEF-{prefix}-{h}"


def _find_source_files(target: Path, extensions: tuple[str, ...]) -> list[Path]:
    """Find source files matching extensions while filtering ignored directories."""
    if target.is_file():
        return [target] if target.suffix in extensions else []
    if not target.is_dir():
        return []
    return [
        p for p in target.rglob("*")
        if p.is_file() and p.suffix in extensions and not any(part in IGNORED_DIRS for part in p.parts)
    ]


class PythonAstScanner(ast.NodeVisitor):
    """Two-pass AST visitor scanning Python code for latent bugs, mismatches and smells."""

    def __init__(self, rel_path: str, code: str):
        self.rel_path = rel_path
        self.findings: list[DefectFinding] = []
        self.func_sigs: dict[str, dict[str, Any]] = {}
        self.async_funcs: set[str] = set()

    def _add(self, rule: str, cat: str, sev: str, track: str, line: int, sym: str, msg: str, fix: str, fp: str = "") -> None:
        code_fp = fp or str(line)
        self.findings.append(DefectFinding(
            id="", fingerprint=compute_fingerprint(rule, sym, code_fp), rule_id=rule,
            category=cat, severity=sev, track=track, file=self.rel_path, line=line,
            symbol=sym, message=msg, suggested_fix=fix
        ))

    def scan(self, tree: ast.AST) -> list[DefectFinding]:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if isinstance(node, ast.AsyncFunctionDef):
                    self.async_funcs.add(node.name)
                req_pos = len(node.args.args) - len(node.args.defaults)
                kwonly = [a.arg for a, d in zip(node.args.kwonlyargs, node.args.kw_defaults) if d is None]
                self.func_sigs[node.name] = {
                    "min": req_pos,
                    "max": len(node.args.args) if node.args.vararg is None else 999,
                    "kwonly": kwonly,
                }
        self.visit(tree)
        return self.findings

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_func_def(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_func_def(node)
        self.generic_visit(node)

    def _check_func_def(self, node: Any) -> None:
        for d, p in zip(reversed(node.args.defaults), reversed(node.args.args)):
            if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                t_name = "[]" if isinstance(d, ast.List) else ("{}" if isinstance(d, ast.Dict) else "set()")
                self._add(
                    "MUTABLE_DEFAULT_ARG", "BAD_LOGIC", "HIGH", "tactical", node.lineno, node.name,
                    f"Mutable default argument '{p.arg}={t_name}' persists mutated state across calls.",
                    f"Replace '{p.arg}={t_name}' with '{p.arg}=None' and initialize inside '{node.name}()'.",
                    f"{node.name}.{p.arg}:{t_name}"
                )
        for i, stmt in enumerate(node.body[:-1]):
            if isinstance(stmt, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                dead = node.body[i + 1]
                self._add(
                    "UNREACHABLE_CODE", "BAD_LOGIC", "MEDIUM", "tactical", dead.lineno, node.name,
                    f"Statement at line {dead.lineno} is unreachable after '{type(stmt).__name__.lower()}'.",
                    f"Remove unreachable statement at line {dead.lineno} or guard prior branch.",
                    f"{dead.lineno}"
                )
                break

    def visit_Expr(self, node: ast.Expr) -> None:
        if isinstance(node.value, ast.Call):
            call_name = self._resolve_call_name(node.value)
            if call_name in self.async_funcs:
                self._add(
                    "UNHANDLED_ASYNC_COROUTINE", "BAD_LOGIC", "HIGH", "architectural", node.lineno, call_name,
                    f"Call to async coroutine '{call_name}' is not awaited or scheduled as a task.",
                    f"Prepend 'await {call_name}(...)' or schedule via 'asyncio.create_task({call_name}(...))'.",
                    f"expr:{call_name}"
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        call_name = self._resolve_call_name(node)
        if call_name in ("eval", "exec"):
            self._add(
                "UNSAFE_EVAL_EXEC", "VULNERABILITY", "HIGH", "architectural", node.lineno, call_name,
                f"Call to dynamic '{call_name}()' introduces code injection hazards.",
                "Use safe parsing (ast.literal_eval() / json.loads()) or structured dispatch per Rule 2.",
                f"{node.lineno}"
            )
        elif call_name in self.func_sigs:
            sig = self.func_sigs[call_name]
            num_args = len(node.args)
            if num_args < sig["min"] or num_args > sig["max"]:
                self._add(
                    "CALL_ARG_COUNT_MISMATCH", "CALLABLE_MISMATCH", "HIGH", "tactical", node.lineno, call_name,
                    f"Call '{call_name}()' expects {sig['min']}-{sig['max']} arg(s), but {num_args} given.",
                    f"Update call to '{call_name}()' at line {node.lineno} to supply required arguments.",
                    f"{num_args}:{sig['min']}"
                )
            kw_names = {kw.arg for kw in node.keywords if kw.arg}
            for req_kw in sig["kwonly"]:
                if req_kw not in kw_names:
                    self._add(
                        "MISSING_REQUIRED_KWARG", "CALLABLE_MISMATCH", "HIGH", "tactical", node.lineno, call_name,
                        f"Call '{call_name}()' is missing required keyword argument '{req_kw}'.",
                        f"Pass required parameter '{req_kw}=...' in call to '{call_name}()' at line {node.lineno}.",
                        f"{call_name}.{req_kw}:{node.lineno}"
                    )
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        for h in node.handlers:
            if h.type is None:
                self._add(
                    "SILENT_BARE_EXCEPT", "EXCEPTION_SMELL", "MEDIUM", "tactical", h.lineno, f"{self.rel_path}:{h.lineno}",
                    "Silent bare 'except:' clause suppresses unexpected errors and interrupts.",
                    "Catch specific exception types (e.g. 'except (ValueError, KeyError):') and log failures.",
                    f"{h.lineno}"
                )
            elif isinstance(h.type, ast.Name) and h.type.id == "BaseException":
                self._add(
                    "OVERBROAD_SHADOW_CATCH", "EXCEPTION_SMELL", "HIGH", "architectural", h.lineno, f"{self.rel_path}:{h.lineno}",
                    "Catching 'BaseException' intercepts SystemExit and KeyboardInterrupt.",
                    "Catch 'Exception' instead of 'BaseException', or re-raise with 'raise ... from err'.",
                    f"{h.lineno}"
                )
        self.generic_visit(node)

    def _resolve_call_name(self, node: ast.Call) -> str:
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""


def audit_hardcoded_secrets(target: Path, rel_path: str, text: str) -> list[DefectFinding]:
    """Scan code text for hardcoded credentials, API keys, and sensitive tokens."""
    if "test" in rel_path.lower():
        return []
    findings: list[DefectFinding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if "# pragma: allow-defect" in line or "# noqa" in line:
            continue
        m = SECRET_REGEX.search(line)
        if m and not any(w in m.group(0).lower() for w in DUMMY_SECRET_WORDS):
            fp = compute_fingerprint("HARDCODED_SECRET_PATTERN", rel_path, f"{lineno}")
            findings.append(DefectFinding(
                id="", fingerprint=fp, rule_id="HARDCODED_SECRET_PATTERN",
                category="VULNERABILITY", severity="HIGH", track="tactical",
                file=rel_path, line=lineno, symbol=rel_path,
                message=f"Possible hardcoded secret or API key pattern detected at line {lineno}.",
                suggested_fix="Extract secret to .env file and resolve via os.getenv() per Rule 1."
            ))
    return findings


def audit_polyglot_lexer(file_path: Path, rel_path: str, text: str, deep: bool = False) -> list[DefectFinding]:
    """Static lexer checks for JavaScript/TypeScript, CSS, and Dart files."""
    findings: list[DefectFinding] = []
    suffix = file_path.suffix.lower()

    if suffix in (".js", ".ts", ".jsx", ".tsx"):
        for lineno, line in enumerate(text.splitlines(), start=1):
            if re.search(r"\beval\s*\(", line):
                fp = compute_fingerprint("UNSAFE_EVAL_EXEC", rel_path, f"{lineno}")
                findings.append(DefectFinding(
                    id="", fingerprint=fp, rule_id="UNSAFE_EVAL_EXEC",
                    category="VULNERABILITY", severity="HIGH", track="architectural",
                    file=rel_path, line=lineno, symbol=rel_path,
                    message=f"Unsafe 'eval()' call at line {lineno} introduces remote code execution risks.",
                    suggested_fix="Replace eval() with JSON.parse() or typed property lookups per Rule 2."
                ))
            if re.search(r"catch\s*\([^)]*\)\s*\{\s*\}", line):
                fp = compute_fingerprint("SILENT_BARE_EXCEPT", rel_path, f"{lineno}")
                findings.append(DefectFinding(
                    id="", fingerprint=fp, rule_id="SILENT_BARE_EXCEPT",
                    category="EXCEPTION_SMELL", severity="MEDIUM", track="tactical",
                    file=rel_path, line=lineno, symbol=rel_path,
                    message=f"Empty catch block at line {lineno} suppresses errors silently.",
                    suggested_fix="Log errors to console or rethrow with contextual information."
                ))
    elif suffix in (".css", ".scss") and deep:
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "!important" in line:
                fp = compute_fingerprint("CSS_IMPORTANT_OVERRUN", rel_path, f"{lineno}")
                findings.append(DefectFinding(
                    id="", fingerprint=fp, rule_id="CSS_IMPORTANT_OVERRUN",
                    category="RESOURCE_LEAK", severity="MEDIUM", track="architectural",
                    file=rel_path, line=lineno, symbol=rel_path,
                    message=f"'!important' declared at line {lineno} breaches specificity budgets.",
                    suggested_fix="Remove '!important' and use structured CSS specificity per Rule 6."
                ))
    elif suffix == ".dart":
        for lineno, line in enumerate(text.splitlines(), start=1):
            if re.search(r"\bcatch\s*\([^)]*\)\s*\{\s*\}", line):
                fp = compute_fingerprint("SILENT_BARE_EXCEPT", rel_path, f"{lineno}")
                findings.append(DefectFinding(
                    id="", fingerprint=fp, rule_id="SILENT_BARE_EXCEPT",
                    category="EXCEPTION_SMELL", severity="MEDIUM", track="tactical",
                    file=rel_path, line=lineno, symbol=rel_path,
                    message=f"Empty catch block at line {lineno} suppresses Dart exceptions silently.",
                    suggested_fix="Log the caught object/StackTrace or narrow error handling."
                ))
    return findings


def run_isolated_python_sandbox(file_path: Path, symbol: str, timeout_sec: float = 2.0) -> Optional[str]:
    """Execute Python candidate callable under isolated 2-second PEP 578 audit sandbox."""
    probe_script = f"""
import sys, importlib, pathlib
def audit_hook(event, args):
    if event in ("os.system", "subprocess.Popen", "socket.connect"):
        raise PermissionError(f"Prohibited operation in sandbox: {{event}}")
sys.addaudithook(audit_hook)
mod_path = pathlib.Path(r"{file_path}").resolve()
sys.path.insert(0, str(mod_path.parent))
mod = importlib.import_module(mod_path.stem)
target = getattr(mod, "{symbol}", None)
if target and callable(target):
    target()
"""
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-c", probe_script],
            capture_output=True, text=True, timeout=timeout_sec, check=False
        )
        if proc.returncode != 0 and "TypeError" in proc.stderr:
            return proc.stderr.strip().splitlines()[-1]
    except Exception:
        pass
    return None


def scan_path(target: Path, deep: bool = False) -> list[DefectFinding]:
    """Scan path across Python, JS/TS, CSS, and Dart for latent defects with dual-key IDs."""
    root = target if target.is_dir() else target.parent
    files = _find_source_files(target, (".py", ".js", ".ts", ".jsx", ".tsx", ".css", ".scss", ".dart"))
    findings: list[DefectFinding] = []

    for f in files:
        rel_str = str(f.relative_to(root)).replace("\\", "/") if f.is_relative_to(root) else f.name
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        findings.extend(audit_hardcoded_secrets(f, rel_str, content))
        findings.extend(audit_polyglot_lexer(f, rel_str, content, deep=deep))

        if f.suffix == ".py":
            try:
                tree = ast.parse(content, filename=str(f))
                scanner = PythonAstScanner(rel_str, content)
                findings.extend(scanner.scan(tree))
            except SyntaxError:
                pass

    for idx, defect in enumerate(findings, start=1):
        defect.id = f"DEFECT-{idx:03d}"

    return findings


def scan_and_save(target: Path, workspace: Optional[Path] = None, deep: bool = False) -> tuple[list[DefectFinding], Path, Path]:
    """Scan target for defects and persist results to .diagnostics/ SSOT catalog."""
    findings = scan_path(target, deep=deep)
    ws = workspace or (target if target.is_dir() else target.parent)
    json_path, md_path = save_catalog(ws, findings)
    return findings, json_path, md_path

