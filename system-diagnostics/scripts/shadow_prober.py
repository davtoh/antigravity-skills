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
        check_git_dirty, checkout_micro_branch, cmd_scaffold_defect, load_catalog,
        reconcile_defect, save_catalog, scaffold_defect, scaffold_tactical_test,
    )
except ImportError:
    from .defect_catalog import (
        check_git_dirty, checkout_micro_branch, cmd_scaffold_defect, load_catalog,
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
    return [p for p in target.rglob("*") if p.is_file() and p.suffix in extensions and not any(part in IGNORED_DIRS for part in p.parts)] if target.is_dir() else []


class PythonAstScanner(ast.NodeVisitor):
    """Two-pass AST visitor scanning Python code for latent bugs, mismatches and smells."""

    def __init__(self, rel_path: str, code: str):
        self.rel_path = rel_path
        self.findings: list[DefectFinding] = []
        self.func_sigs: dict[str, dict[str, Any]] = {}
        self.async_funcs: set[str] = set()

    def _add(self, rule: str, cat: str, sev: str, track: str, line: int, sym: str, msg: str, fix: str, fp: str = "") -> None:
        self.findings.append(DefectFinding(
            id="", fingerprint=compute_fingerprint(rule, sym, fp or str(line)), rule_id=rule,
            category=cat, severity=sev, track=track, file=self.rel_path, line=line,
            symbol=sym, message=msg, suggested_fix=fix,
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
    visit_AsyncFunctionDef = visit_FunctionDef

    def _check_func_def(self, node: Any) -> None:
        for d, p in zip(reversed(node.args.defaults), reversed(node.args.args)):
            if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                t_name = "[]" if isinstance(d, ast.List) else ("{}" if isinstance(d, ast.Dict) else "set()")
                self._add("MUTABLE_DEFAULT_ARG", "BAD_LOGIC", "HIGH", "tactical", node.lineno, node.name,
                          f"Mutable default argument '{p.arg}={t_name}' persists mutated state across calls.",
                          f"Replace '{p.arg}={t_name}' with '{p.arg}=None' and initialize inside '{node.name}()'.",
                          f"{node.name}.{p.arg}:{t_name}")
        for i, stmt in enumerate(node.body[:-1]):
            if isinstance(stmt, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                dead = node.body[i + 1]
                self._add("UNREACHABLE_CODE", "BAD_LOGIC", "MEDIUM", "tactical", dead.lineno, node.name,
                          f"Statement at line {dead.lineno} is unreachable after '{type(stmt).__name__.lower()}'.",
                          f"Remove unreachable statement at line {dead.lineno} or guard prior branch.", f"{dead.lineno}")
                break

    def visit_Expr(self, node: ast.Expr) -> None:
        if isinstance(node.value, ast.Call):
            call_name = self._resolve_call_name(node.value)
            if call_name in self.async_funcs:
                self._add("UNHANDLED_ASYNC_COROUTINE", "BAD_LOGIC", "HIGH", "architectural", node.lineno, call_name,
                          f"Call to async coroutine '{call_name}' is not awaited or scheduled as a task.",
                          f"Prepend 'await {call_name}(...)' or schedule via 'asyncio.create_task({call_name}(...))'.", f"expr:{call_name}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        call_name = self._resolve_call_name(node)
        if call_name in ("eval", "exec"):
            self._add(
                "UNSAFE_EVAL_EXEC", "VULNERABILITY", "HIGH", "architectural", node.lineno, call_name,
                f"Call to dynamic '{call_name}()' introduces code injection hazards.",
                "Use safe parsing (ast.literal_eval() / json.loads()) or structured dispatch per Rule 2.",
                f"{node.lineno}",
            )
        elif call_name in self.func_sigs:
            sig = self.func_sigs[call_name]
            num_args = len(node.args)
            if num_args < sig["min"] or num_args > sig["max"]:
                self._add("CALL_ARG_COUNT_MISMATCH", "CALLABLE_MISMATCH", "HIGH", "tactical", node.lineno, call_name,
                          f"Call '{call_name}()' expects {sig['min']}-{sig['max']} arg(s), but {num_args} given.",
                          f"Update call to '{call_name}()' at line {node.lineno} to supply required arguments.", f"{num_args}:{sig['min']}")
            kw_names = {kw.arg for kw in node.keywords if kw.arg}
            for req_kw in sig["kwonly"]:
                if req_kw not in kw_names:
                    self._add("MISSING_REQUIRED_KWARG", "CALLABLE_MISMATCH", "HIGH", "tactical", node.lineno, call_name,
                              f"Call '{call_name}()' is missing required keyword argument '{req_kw}'.",
                              f"Pass required parameter '{req_kw}=...' in call to '{call_name}()' at line {node.lineno}.",
                              f"{call_name}.{req_kw}:{node.lineno}")
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        for h in node.handlers:
            sym = f"{self.rel_path}:{h.lineno}"
            if h.type is None:
                self._add("SILENT_BARE_EXCEPT", "EXCEPTION_SMELL", "MEDIUM", "tactical", h.lineno, sym,
                          "Silent bare 'except:' clause suppresses unexpected errors and interrupts.",
                          "Catch specific exception types (e.g. 'except (ValueError, KeyError):') and log failures.")
            elif isinstance(h.type, ast.Name) and h.type.id == "BaseException":
                self._add("OVERBROAD_SHADOW_CATCH", "EXCEPTION_SMELL", "HIGH", "architectural", h.lineno, sym,
                          "Catching 'BaseException' intercepts SystemExit and KeyboardInterrupt.",
                          "Catch 'Exception' instead of 'BaseException', or re-raise with 'raise ... from err'.")
        self.generic_visit(node)

    def _resolve_call_name(self, node: ast.Call) -> str:
        return node.func.id if isinstance(node.func, ast.Name) else (node.func.attr if isinstance(node.func, ast.Attribute) else "")


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
            fp = compute_fingerprint("HARDCODED_SECRET_PATTERN", rel_path, str(lineno))
            findings.append(DefectFinding(
                "", fp, "HARDCODED_SECRET_PATTERN", "VULNERABILITY", "HIGH", "tactical",
                rel_path, lineno, rel_path,
                f"Possible hardcoded secret or API key pattern detected at line {lineno}.",
                "Extract secret to .env file and resolve via os.getenv() per Rule 1.",
            ))
    return findings


def audit_polyglot_lexer(file_path: Path, rel_path: str, text: str, deep: bool = False) -> list[DefectFinding]:
    """Static lexer checks for JavaScript/TypeScript, CSS, and Dart files."""
    findings: list[DefectFinding] = []
    suffix = file_path.suffix.lower()

    def _add_lex(rule: str, cat: str, sev: str, trk: str, lineno: int, msg: str, fix: str) -> None:
        fp = compute_fingerprint(rule, rel_path, str(lineno))
        findings.append(DefectFinding("", fp, rule, cat, sev, trk, rel_path, lineno, rel_path, msg, fix))

    for lineno, line in enumerate(text.splitlines(), start=1):
        if suffix in (".js", ".ts", ".jsx", ".tsx"):
            if re.search(r"\beval\s*\(", line):
                _add_lex("UNSAFE_EVAL_EXEC", "VULNERABILITY", "HIGH", "architectural", lineno,
                         f"Unsafe 'eval()' call at line {lineno} introduces remote code execution risks.",
                         "Replace eval() with JSON.parse() or typed property lookups per Rule 2.")
            if re.search(r"catch\s*\([^)]*\)\s*\{\s*\}", line):
                _add_lex("SILENT_BARE_EXCEPT", "EXCEPTION_SMELL", "MEDIUM", "tactical", lineno,
                         f"Empty catch block at line {lineno} suppresses errors silently.",
                         "Log errors to console or rethrow with contextual information.")
        elif suffix in (".css", ".scss") and deep and "!important" in line:
            _add_lex("CSS_IMPORTANT_OVERRUN", "RESOURCE_LEAK", "MEDIUM", "architectural", lineno,
                     f"'!important' declared at line {lineno} breaches specificity budgets.",
                     "Remove '!important' and use structured CSS specificity per Rule 6.")
        elif suffix == ".dart" and re.search(r"\bcatch\s*\([^)]*\)\s*\{\s*\}", line):
            _add_lex("SILENT_BARE_EXCEPT", "EXCEPTION_SMELL", "MEDIUM", "tactical", lineno,
                     f"Empty catch block at line {lineno} suppresses Dart exceptions silently.",
                     "Log the caught object/StackTrace or narrow error handling.")
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
            capture_output=True, text=True, timeout=timeout_sec, check=False,
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
                findings.extend(PythonAstScanner(rel_str, content).scan(tree))
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


def register_parsers(subparsers: Any) -> tuple[Any, Any]:
    """Register 'scan' and 'scaffold-defect' subparsers into diagnose.py CLI."""
    p_scan = subparsers.add_parser("scan", help="Polyglot scan for latent defects, smells, and vulnerabilities")
    p_scan.add_argument("--path", default=None, help="Root directory or file to scan (default: current directory)")
    p_scan.add_argument("--deep", action="store_true", help="Include CSS/SCSS and deeper AST rules")
    p_scan.add_argument("--all", dest="deep", action="store_true", help="Alias for --deep")
    p_scan.add_argument("--json", action="store_true", help="Output JSON catalog format")
    p_scan.add_argument("--strict", action="store_true", help="Exit code 1 if any defects found")

    p_scaf = subparsers.add_parser("scaffold-defect", help="Unlock and scaffold a defect for remediation")
    p_scaf.add_argument("--id", required=True, help="Defect ID (e.g. DEFECT-001) or fingerprint (e.g. DEF-MUTABLE-8f3a1c)")
    p_scaf.add_argument("--branch", action="store_true", help="Create and checkout micro-branch fix/defect-<id>")
    p_scaf.add_argument("--elevate", action="store_true", help="Force architectural elevation brief for /frontier-architect + /grill-me")
    p_scaf.add_argument("--fix", action="store_true", help="Force tactical test scaffolding for /app-debugger")
    p_scaf.add_argument("--path", default=None, help="Target workspace directory (default: current directory)")
    p_scaf.add_argument("--json", action="store_true", help="Output JSON result")
    return p_scan, p_scaf


def cmd_scan(args: Any) -> int:
    """CLI handler for `diagnose.py scan`."""
    target_path = Path(args.path).resolve() if getattr(args, "path", None) else Path.cwd()
    workspace = target_path if target_path.is_dir() else target_path.parent
    findings, json_path, md_path = scan_and_save(target_path, workspace=workspace, deep=getattr(args, "deep", False))

    if getattr(args, "json", False):
        catalog = load_catalog(workspace)
        print(json.dumps(catalog, indent=2))
        return 1 if (getattr(args, "strict", False) and findings) else 0

    print(f"\n=== Polyglot Latent Defect & Smell Scan ({target_path.name}) ===")
    print(f"Catalog SSOT: {json_path.name} (Report: {md_path.name})")

    tactical_count = sum(1 for f in findings if f.track == "tactical")
    arch_count = sum(1 for f in findings if f.track == "architectural")
    print(f"Total Defects Flagged: {len(findings)} (Tactical: {tactical_count}, Architectural: {arch_count})")

    if findings:
        print("\n--- Discovered Defects (Top 5 shown) ---")
        for f in findings[:5]:
            print(f"  [{f.id}] [{f.severity}] {f.rule_id} -> {f.file}:{f.line} ({f.symbol}) [{f.track}]")
            print(f"         Fix: {f.suggested_fix}")
        if len(findings) > 5:
            print(f"  ... and {len(findings) - 5} more defect(s) omitted to conserve tokens. See {json_path.name}.")

        print("\n--- Remediation Next Steps ---")
        if tactical_count > 0:
            first_tactical = next(f for f in findings if f.track == "tactical")
            print(f"  Tactical Bug (/app-debugger):         python skills/system-diagnostics/scripts/diagnose.py scaffold-defect --id {first_tactical.id} --branch")
        if arch_count > 0:
            first_arch = next(f for f in findings if f.track == "architectural")
            print(f"  Architectural Redesign (/frontier):   python skills/system-diagnostics/scripts/diagnose.py scaffold-defect --id {first_arch.id} --elevate")
    else:
        print("  ✓ Zero latent defects discovered.")
    print()

    return 1 if (getattr(args, "strict", False) and findings) else 0
