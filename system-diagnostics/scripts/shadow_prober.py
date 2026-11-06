#!/usr/bin/env python3
"""Polyglot Shadow Prober, Defect Scanner & JIT Scaffolder (system-diagnostics).

Scans codebases for latent bugs, vulnerabilities, callable mismatches,
exception smells, and modularity/resource defects across Python, JS/TS, CSS, and Dart.
Ground-truth state is stored in <workspace>/.diagnostics/defect_catalog.json (SSOT).
"""

import ast
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Optional

try:
    from defect_catalog import (
        ACTIVE_STATUSES, IGNORED_WORKSPACE_DIRS as IGNORED_DIRS, check_git_dirty,
        checkout_micro_branch, cmd_scaffold_defect, cmd_status_transition, load_catalog,
        reconcile_defect, save_catalog, scaffold_defect, scaffold_tactical_test,
        update_defect_status,
    )
except ImportError:
    from .defect_catalog import (
        ACTIVE_STATUSES, IGNORED_WORKSPACE_DIRS as IGNORED_DIRS, check_git_dirty,
        checkout_micro_branch, cmd_scaffold_defect, cmd_status_transition, load_catalog,
        reconcile_defect, save_catalog, scaffold_defect, scaffold_tactical_test,
        update_defect_status,
    )

SECRET_REGEX = re.compile(r"""(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|private[_-]?key|password)\s*[:=]\s*['"][a-zA-Z0-9_\-\.]{16,}['"]""")
DUMMY_SECRET_WORDS = frozenset({"test", "fake", "dummy", "example", "placeholder", "xxx", "sample"})
SKIP_ARITY_DECORATORS = frozenset({"property", "setter", "deleter", "overload", "abstractmethod"})


@dataclass
class DefectFinding:
    """Authoritative representation of a discovered latent defect."""
    id: str; fingerprint: str; rule_id: str; category: str; severity: str
    track: str; file: str; line: int; symbol: str; message: str; suggested_fix: str
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


def _extract_callable_sig(node: Any, is_method: bool = False) -> Optional[dict[str, Any]]:
    """Build parameter arity contract for a function or method, accounting for bound self/cls."""
    dec_names = {d.id if isinstance(d, ast.Name) else (d.attr if isinstance(d, ast.Attribute) else "") for d in getattr(node, "decorator_list", [])}
    if dec_names & SKIP_ARITY_DECORATORS:
        return None
    all_pos = [a.arg for a in getattr(node.args, "posonlyargs", [])] + [a.arg for a in node.args.args]
    req_total = len(all_pos) - len(node.args.defaults)
    is_bound = is_method and ("staticmethod" not in dec_names)
    pos_params = all_pos[1:] if (is_bound and all_pos) else all_pos
    req_count = max(0, req_total - 1) if (is_bound and all_pos) else req_total
    kwonly = [a.arg for a, d in zip(node.args.kwonlyargs, node.args.kw_defaults) if d is None]
    return {
        "min": req_count, "max": len(pos_params) if node.args.vararg is None else 999,
        "pos_params": pos_params, "req_pos_names": pos_params[:req_count], "kwonly": kwonly,
    }


class PythonAstScanner(ast.NodeVisitor):
    """Scope- and receiver-aware AST visitor scanning Python code for latent bugs and smells."""

    def __init__(self, rel_path: str, code: str):
        self.rel_path, self.findings = rel_path, []
        self.func_sigs, self.async_funcs = {}, set()
        self.class_methods, self.class_async, self.current_class = {}, {}, None

    def _add(self, rule: str, cat: str, sev: str, track: str, line: int, sym: str, msg: str, fix: str, fp: str = "") -> None:
        self.findings.append(DefectFinding("", compute_fingerprint(rule, sym, fp or str(line)), rule, cat, sev, track, self.rel_path, line, sym, msg, fix))

    def scan(self, tree: ast.AST) -> list[DefectFinding]:
        for stmt in getattr(tree, "body", []):
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if isinstance(stmt, ast.AsyncFunctionDef):
                    self.async_funcs.add(stmt.name)
                sig = _extract_callable_sig(stmt, is_method=False)
                if sig:
                    self.func_sigs[stmt.name] = sig
            elif isinstance(stmt, ast.ClassDef):
                c_sigs, c_async = {}, set()
                for m in stmt.body:
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if isinstance(m, ast.AsyncFunctionDef):
                            c_async.add(m.name)
                        msig = _extract_callable_sig(m, is_method=True)
                        if msig:
                            c_sigs[m.name] = msig
                self.class_methods[stmt.name], self.class_async[stmt.name] = c_sigs, c_async
        self.visit(tree)
        return self.findings

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        prev, self.current_class = self.current_class, node.name
        self.generic_visit(node)
        self.current_class = prev

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
                          f"Replace '{p.arg}={t_name}' with '{p.arg}=None' and initialize inside '{node.name}()'.", f"{node.name}.{p.arg}:{t_name}")
        for i, stmt in enumerate(node.body[:-1]):
            if isinstance(stmt, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                dead = node.body[i + 1]
                self._add("UNREACHABLE_CODE", "BAD_LOGIC", "MEDIUM", "tactical", dead.lineno, node.name,
                          f"Statement at line {dead.lineno} is unreachable after '{type(stmt).__name__.lower()}'.",
                          f"Remove unreachable statement at line {dead.lineno} or guard prior branch.", f"{dead.lineno}")
                break

    def _resolve_target(self, node: ast.Call) -> tuple[str, Optional[dict[str, Any]], bool]:
        if isinstance(node.func, ast.Name):
            name = node.func.id
            return name, self.func_sigs.get(name), (name in self.async_funcs)
        if isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            if isinstance(node.func.value, ast.Name) and node.func.value.id in ("self", "cls") and self.current_class:
                return attr, self.class_methods.get(self.current_class, {}).get(attr), (attr in self.class_async.get(self.current_class, set()))
            return attr, None, False
        return "", None, False

    def visit_Expr(self, node: ast.Expr) -> None:
        if isinstance(node.value, ast.Call):
            call_name, _, is_async = self._resolve_target(node.value)
            if is_async:
                self._add("UNHANDLED_ASYNC_COROUTINE", "BAD_LOGIC", "HIGH", "architectural", node.lineno, call_name,
                          f"Call to async coroutine '{call_name}' is not awaited or scheduled as a task.",
                          f"Prepend 'await {call_name}(...)' or schedule via 'asyncio.create_task({call_name}(...))'.", f"expr:{call_name}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        call_name, sig, _ = self._resolve_target(node)
        if isinstance(node.func, ast.Name) and call_name in ("eval", "exec"):
            self._add("UNSAFE_EVAL_EXEC", "VULNERABILITY", "HIGH", "architectural", node.lineno, call_name,
                      f"Call to dynamic '{call_name}()' introduces code injection hazards.",
                      "Use safe parsing (ast.literal_eval() / json.loads()) or structured dispatch per Rule 2.", f"{node.lineno}")
        elif sig is not None:
            has_unpack = any(isinstance(a, ast.Starred) for a in node.args) or any(kw.arg is None for kw in node.keywords)
            if not has_unpack:
                num_pos = len(node.args)
                kw_names = {kw.arg for kw in node.keywords if kw.arg}
                missing_pos = [p for p in sig["req_pos_names"][num_pos:] if p not in kw_names]
                supplied = num_pos + sum(1 for p in sig["pos_params"][num_pos:] if p in kw_names)
                if missing_pos or num_pos > sig["max"]:
                    self._add("CALL_ARG_COUNT_MISMATCH", "CALLABLE_MISMATCH", "HIGH", "tactical", node.lineno, call_name,
                              f"Call '{call_name}()' expects {sig['min']}-{sig['max']} arg(s), but {supplied} given.",
                              f"Update call to '{call_name}()' at line {node.lineno} to supply required arguments.", f"{supplied}:{sig['min']}")
                for req_kw in sig["kwonly"]:
                    if req_kw not in kw_names:
                        self._add("MISSING_REQUIRED_KWARG", "CALLABLE_MISMATCH", "HIGH", "tactical", node.lineno, call_name,
                                  f"Call '{call_name}()' is missing required keyword argument '{req_kw}'.",
                                  f"Pass required parameter '{req_kw}=...' in call to '{call_name}()' at line {node.lineno}.", f"{call_name}.{req_kw}:{node.lineno}")
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
                "", fp, "HARDCODED_SECRET_PATTERN", "VULNERABILITY", "HIGH", "tactical", rel_path, lineno, rel_path,
                f"Possible hardcoded secret or API key pattern detected at line {lineno}.",
                "Extract secret to .env file and resolve via os.getenv() per Rule 1.",
            ))
    return findings


def audit_polyglot_lexer(file_path: Path, rel_path: str, text: str, deep: bool = False) -> list[DefectFinding]:
    """Static lexer checks for JavaScript/TypeScript, CSS, and Dart files."""
    findings: list[DefectFinding] = []
    suffix = file_path.suffix.lower()

    def _add_lex(rule: str, cat: str, sev: str, trk: str, lineno: int, msg: str, fix: str) -> None:
        findings.append(DefectFinding("", compute_fingerprint(rule, rel_path, str(lineno)), rule, cat, sev, trk, rel_path, lineno, rel_path, msg, fix))

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
    probe_script = (
        "import sys, importlib, pathlib\n"
        "def audit_hook(e, a):\n"
        "    if e in ('os.system', 'subprocess.Popen', 'socket.connect'): raise PermissionError(e)\n"
        "sys.addaudithook(audit_hook)\n"
        f"mod_path = pathlib.Path(r'{file_path}').resolve()\n"
        "sys.path.insert(0, str(mod_path.parent))\n"
        f"target = getattr(importlib.import_module(mod_path.stem), '{symbol}', None)\n"
        "if target and callable(target): target()\n"
    )
    try:
        proc = subprocess.run([sys.executable, "-I", "-c", probe_script], capture_output=True, text=True, timeout=timeout_sec, check=False)
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
                findings.extend(PythonAstScanner(rel_str, content).scan(ast.parse(content, filename=str(f))))
            except SyntaxError:
                pass
    for idx, defect in enumerate(findings, start=1):
        defect.id = f"DEFECT-{idx:03d}"
    return findings


def scan_and_save(
    target: Path, workspace: Optional[Path] = None, deep: bool = False,
    reconcile_scan: bool = True, prune: bool = False,
) -> tuple[list[DefectFinding], Path, Path]:
    """Scan target for defects and persist reconciled results to .diagnostics/ SSOT catalog."""
    findings = scan_path(target, deep=deep)
    ws = workspace or (target if target.is_dir() else target.parent)
    json_path, md_path = save_catalog(ws, findings, reconcile_scan=reconcile_scan, prune=prune)
    return findings, json_path, md_path


def register_parsers(subparsers: Any) -> tuple[Any, Any]:
    """Register 'scan', 'scaffold-defect', 'resolve-defect', and 'dismiss-defect' subparsers."""
    p_scan = subparsers.add_parser("scan", help="Polyglot scan for latent defects, smells, and vulnerabilities")
    p_scan.add_argument("--path", default=None, help="Root directory or file to scan (default: current directory)")
    p_scan.add_argument("--deep", action="store_true", help="Include CSS/SCSS and deeper AST rules")
    p_scan.add_argument("--all", dest="deep", action="store_true", help="Alias for --deep")
    p_scan.add_argument("--prune", action="store_true", help="Purge obsolete/resolved/dismissed defects not in current scan")
    p_scan.add_argument("--json", action="store_true", help="Output JSON catalog format")
    p_scan.add_argument("--strict", action="store_true", help="Exit code 1 if any active defects found")

    p_scaf = subparsers.add_parser("scaffold-defect", help="Unlock and scaffold a defect for remediation")
    p_scaf.add_argument("--id", required=True, help="Defect ID (e.g. DEFECT-001) or fingerprint")
    p_scaf.add_argument("--branch", action="store_true", help="Create and checkout micro-branch fix/defect-<id>")
    p_scaf.add_argument("--elevate", action="store_true", help="Force architectural elevation brief")
    p_scaf.add_argument("--fix", action="store_true", help="Force tactical test scaffolding")
    p_scaf.add_argument("--path", default=None, help="Target workspace directory")
    p_scaf.add_argument("--json", action="store_true", help="Output JSON result")

    for cmd_name, flag, help_msg in (("resolve-defect", "--note", "Mark defect(s) resolved"), ("dismiss-defect", "--reason", "Dismiss defect(s)")):
        p = subparsers.add_parser(cmd_name, help=help_msg)
        p.add_argument("--id", required=True, help="Defect ID(s), fingerprint(s), or rule_id (comma-separated)")
        p.add_argument(flag, default="", help="Resolution or dismissal note")
        p.add_argument("--path", default=None, help="Target workspace directory")
        p.add_argument("--json", action="store_true", help="Output JSON result")
    return p_scan, p_scaf


def cmd_scan(args: Any) -> int:
    """CLI handler for `diagnose.py scan`."""
    target_path = Path(args.path).resolve() if getattr(args, "path", None) else Path.cwd()
    workspace = target_path if target_path.is_dir() else target_path.parent
    _, json_path, md_path = scan_and_save(
        target_path, workspace=workspace, deep=getattr(args, "deep", False),
        reconcile_scan=True, prune=getattr(args, "prune", False),
    )
    catalog = load_catalog(workspace)
    active = [d for d in catalog.get("defects", []) if d.get("status", "quarantined") in ACTIVE_STATUSES]
    summary = catalog.get("summary", {})
    if getattr(args, "json", False):
        print(json.dumps(catalog, indent=2))
        return 1 if (getattr(args, "strict", False) and active) else 0

    tactical_count = sum(1 for d in active if d.get("track") == "tactical")
    arch_count = sum(1 for d in active if d.get("track") == "architectural")
    print(f"\n=== Polyglot Latent Defect & Smell Scan ({target_path.name}) ===\nCatalog SSOT: {json_path.name} (Report: {md_path.name})")
    print(f"Active Defects: {len(active)} (Tactical: {tactical_count}, Architectural: {arch_count} | Resolved: {summary.get('resolved', 0)}, Dismissed: {summary.get('dismissed', 0)})")
    for d in active[:5]:
        print(f"  [{d.get('id')}] [{d.get('severity')}] {d.get('rule_id')} -> {d.get('file')}:{d.get('line')} ({d.get('symbol')}) [{d.get('track')}]\n         Fix: {d.get('suggested_fix')}")
    if not active:
        print("  ✓ Zero active latent defects.")
    print()
    return 1 if (getattr(args, "strict", False) and active) else 0
