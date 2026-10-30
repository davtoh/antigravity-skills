#!/usr/bin/env python3
"""Cross-platform contract snapshot, regression auditor, and smoke-test generator.

Captures and diffs AST, DOM, global export, and route contracts before and after
refactoring across Python, HTML, JavaScript, and CSS without external dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from surface_scanners import (  # noqa: E402
    scan_css_surface,
    scan_html_surface,
    scan_js_surface,
    scan_python_surface,
)


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


def get_git_sha(target_dir: Path) -> str:
    """Resolve the active HEAD commit SHA."""
    code, out = _run_git(["rev-parse", "HEAD"], cwd=target_dir)
    return out if code == 0 else ""


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
    """List source files in target directory, optionally from a historical git commit."""
    if git_ref:
        code, out = _run_git(["ls-tree", "-r", "--name-only", git_ref], cwd=base_dir)
        return [Path(p) for p in out.splitlines() if p.strip()] if code == 0 else []
    return [p for p in base_dir.rglob("*") if p.is_file() and ".git" not in p.parts]


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
                _dispatch_scan(sfx, text, acc)

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


def _dispatch_scan(sfx: str, text: str, acc: dict[str, Any]) -> None:
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
        p = scan_python_surface(text)
        acc["routes"].extend(p.routes)
        acc["py_globals"].update(p.mutable_globals)
    elif sfx in {".css", ".scss"}:
        c = scan_css_surface(text)
        acc["important"] += c.important_count
        acc["css_vars"].update(c.custom_properties)


def diff_contracts(before: CodebaseContract, after: CodebaseContract) -> list[str]:
    """Compare before and after contracts and return list of critical discrepancies."""
    issues: list[str] = []
    missing_ids = [i for i in after.js_queried_ids if after.html_ids and i not in after.html_ids]
    for mid in sorted(missing_ids):
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


def discover_optional_tools() -> dict[str, str]:
    """Locate optional auxiliary tools from sibling skills or workspace without hard dependencies."""
    home = Path.home()
    candidates = {
        "cdp_inspect": [
            os.environ.get("CDP_INSPECT_PATH", ""),
            str(Path.cwd() / "scripts" / "cdp_inspect.py"),
            str(home / ".gemini" / "config" / "skills" / "frontier-architect" / "scripts" / "cdp_inspect.py"),
        ],
        "docker_audit": [
            os.environ.get("DOCKER_AUDIT_PATH", ""),
            str(Path.cwd() / "scripts" / "docker_audit.py"),
            str(home / ".gemini" / "config" / "skills" / "frontier-architect" / "scripts" / "docker_audit.py"),
        ],
    }
    found = {}
    for name, paths in candidates.items():
        for p in paths:
            if p and Path(p).is_file():
                found[name] = p
                break
    return found


def cmd_anchor(target: Path, worktree_dir: str = "") -> int:
    """Print reference git commit anchor and git worktree recipe."""
    sha = get_git_sha(target)
    if not sha:
        print("Error: Target path is not a git repository.", file=sys.stderr)
        return 2
    code, dirty = _run_git(["status", "--porcelain"], cwd=target)
    print(f"=== Reference Git Anchor ===\nCurrent HEAD SHA: {sha}")
    print("[WARNING] Uncommitted modifications present!" if dirty else "Working directory clean (golden anchor).")
    target_worktree = worktree_dir or str(target.parent / f"{target.name}_pre_refactor")
    print(f"\n--- Parallel Git Worktree Recipe ---\n  git -C \"{target}\" worktree add \"{target_worktree}\" {sha[:7]}")
    print(f"To remove after verification:\n  git -C \"{target}\" worktree remove \"{target_worktree}\"")
    return 0


def cmd_capture(target: Path, out_file: str, git_ref: str = "") -> int:
    """Capture codebase contract to JSON file."""
    contract = build_contract(target, git_ref)
    out_path = Path(out_file) if out_file else target / ".refactor_baseline.json"
    out_path.write_text(json.dumps(contract.to_dict(), indent=2), encoding="utf-8")
    src = f"git ref {git_ref}" if git_ref else "live workspace"
    print(f"Contract captured from {src} -> {out_path} ({len(contract.html_ids)} IDs, {len(contract.select_ids)} Selects, {len(contract.js_global_exports)} Globals, {len(contract.python_routes)} Routes)")
    return 0


def cmd_inspect(target: Path, git_ref: str = "", before_file: str = "") -> int:
    """Print human-readable Interactive Surface Inventory."""
    contract = CodebaseContract.from_dict(json.loads(Path(before_file).read_text(encoding="utf-8"))) if before_file else build_contract(target, git_ref)
    print("=== Interactive Surface Inventory ===")
    print(f"Total HTML Element IDs:       {len(contract.html_ids)}")
    print(f"Interactive Select Dropdowns: {len(contract.select_ids)}")
    for s in contract.select_ids[:15]:
        print(f"  - #{s}")
    if len(contract.select_ids) > 15:
        print(f"  ... and {len(contract.select_ids) - 15} more")
    print(f"Inline Event Handlers:        {len(contract.inline_handlers)}")
    print(f"Global window.* Exports:      {len(contract.js_global_exports)}")
    for g in contract.js_global_exports[:15]:
        print(f"  - window.{g}")
    print(f"Backend API Routes:           {len(contract.python_routes)}")
    print(f"CSS !important Count:         {contract.css_important_count}")
    return 0


def cmd_verify(target: Path, before_file: str = "", git_ref: str = "", strict: bool = False) -> int:
    """Diff current codebase contract against baseline or historical git commit."""
    if before_file and Path(before_file).is_file():
        before = CodebaseContract.from_dict(json.loads(Path(before_file).read_text(encoding="utf-8")))
    elif git_ref:
        before = build_contract(target, git_ref)
    else:
        print("Error: provide --before <file.json> or --git-ref <sha> to verify against.", file=sys.stderr)
        return 2

    after = build_contract(target)
    issues = diff_contracts(before, after)
    opt_tools = discover_optional_tools()

    print(f"=== Contract Verification: Before ({before.commit_sha[:7] or 'snapshot'}) vs After ({after.commit_sha[:7] or 'current'}) ===")
    if not issues:
        print("OK: Zero contract regressions detected! (DOM IDs, selects, globals, routes, and CSS preserved)")
    else:
        print(f"CRITICAL: Found {len(issues)} contract discrepancy/discrepancies:")
        for iss in issues:
            print(f"  {iss}")

    print("\n--- Tool Discovery Status ---")
    if opt_tools:
        for name, p in opt_tools.items():
            print(f"  [Optional Tool Detected] {name} -> {p}")
    else:
        print("  [Self-Contained Mode] Built-in static contract verifier active. (Optional live tools not found)")

    test_files = [f for f in iter_repo_files(target) if "test" in f.name.lower()]
    if not any("smoke" in f.name.lower() or "contract" in f.name.lower() for f in test_files):
        print("\n[BLINDSPOT WARNING] No frontend contract smoke test found in tests/!")
        print("Run `contract_snapshot.py generate-smoke-test --out tests/test_refactor_contract.py` to lock in parity.")

    return 1 if (strict and issues) else 0


def _build_smoke_template(select_ids: list[str], important_count: int) -> str:
    """Render unit test code string for contract smoke verification."""
    return f'''# Generated Contract Smoke Test - Enforces Zero-Regression Refactoring Parity
import pathlib
import re
import unittest

class TestCodebaseContractInvariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = pathlib.Path(__file__).resolve().parent.parent
        cls.html_text = "".join(p.read_text(encoding="utf-8", errors="replace") + "\\n" for p in cls.root.rglob("*.html") if ".git" not in p.parts)
        cls.js_text = "".join(p.read_text(encoding="utf-8", errors="replace") + "\\n" for p in cls.root.rglob("*.js") if ".git" not in p.parts)

    def test_dom_interactive_selects_exist(self):
        """Verify all critical <select> dropdown IDs exist in HTML."""
        for sel in {repr(select_ids)}:
            self.assertIn(f'id="{{sel}}"', self.html_text, f"Missing select dropdown #{{sel}} in HTML!")

    def test_js_queries_match_existing_dom_ids(self):
        """Verify every getElementById queried in JS actually exists in HTML."""
        queried = set(re.findall(r'getElementById\\(["\\']([a-zA-Z0-9_\\-]+)["\\']\\)', self.js_text))
        for q_id in sorted(queried):
            if not q_id.startswith(("dynamic", "test")):
                self.assertIn(f'id="{{q_id}}"', self.html_text, f"JS queries #{{q_id}} but it is missing in HTML!")

    def test_zero_css_important_creep(self):
        """Verify CSS does not exceed baseline !important threshold."""
        css_text = "".join(p.read_text(encoding="utf-8", errors="replace") for p in self.root.rglob("*.css") if ".git" not in p.parts)
        count = len(re.findall(r'!important\\b', css_text, re.IGNORECASE))
        self.assertLessEqual(count, {important_count}, f"!important count increased to {{count}}!")

if __name__ == "__main__":
    unittest.main()
'''


def cmd_generate_smoke_test(target: Path, out_file: str, before_file: str = "", git_ref: str = "") -> int:
    """Generate standalone unittest file enforcing contract parity."""
    c = CodebaseContract.from_dict(json.loads(Path(before_file).read_text(encoding="utf-8"))) if before_file else build_contract(target, git_ref)
    out_p = Path(out_file) if out_file else target / "tests" / "test_refactor_contract.py"
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(_build_smoke_template(c.select_ids, c.css_important_count), encoding="utf-8")
    print(f"Generated contract smoke test -> {out_p}")
    return 0


def _add_common_path_args(parser: argparse.ArgumentParser) -> None:
    """Add standard --path, --before, and --git-ref arguments."""
    parser.add_argument("--path", default=".", help="Target repository directory.")
    parser.add_argument("--before", default="", help="Baseline JSON path.")
    parser.add_argument("--git-ref", default="", help="Historical git commit/branch.")


def build_cli_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser."""
    p = argparse.ArgumentParser(description="Cross-platform codebase contract snapshot and regression auditor.")
    sub = p.add_subparsers(dest="subcommand", required=True)

    p_anc = sub.add_parser("anchor", help="Identify git reference anchor and worktree recipe.")
    p_anc.add_argument("--path", default=".", help="Target repository directory.")
    p_anc.add_argument("--worktree-dir", default="", help="Optional worktree path.")

    p_cap = sub.add_parser("capture", help="Capture contract to JSON file.")
    _add_common_path_args(p_cap)
    p_cap.add_argument("--out", default="", help="Output JSON path.")

    p_ins = sub.add_parser("inspect", help="Display Interactive Surface Inventory.")
    _add_common_path_args(p_ins)

    p_ver = sub.add_parser("verify", help="Diff contracts and check regressions.")
    _add_common_path_args(p_ver)
    p_ver.add_argument("--strict", action="store_true", help="Exit 1 on critical discrepancy.")

    p_smk = sub.add_parser("generate-smoke-test", help="Generate permanent unittest contract test.")
    _add_common_path_args(p_smk)
    p_smk.add_argument("--out", default="", help="Output test file path.")

    sub.add_parser("probe-tools", help="Discover optional auxiliary tools (cdp_inspect, docker_audit).")
    return p


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    args = build_cli_parser().parse_args(argv)
    if args.subcommand == "probe-tools":
        tools = discover_optional_tools()
        print("=== Optional Auxiliary Tools Discovery ===")
        for k, v in tools.items():
            print(f"  {k}: {v}")
        if not tools:
            print("  (None detected; running in 100% self-contained mode)")
        return 0

    target = Path(args.path).resolve()
    if args.subcommand == "anchor":
        return cmd_anchor(target, getattr(args, "worktree_dir", ""))
    if args.subcommand == "capture":
        return cmd_capture(target, getattr(args, "out", ""), getattr(args, "git_ref", ""))
    if args.subcommand == "inspect":
        return cmd_inspect(target, getattr(args, "git_ref", ""), getattr(args, "before", ""))
    if args.subcommand == "verify":
        return cmd_verify(target, getattr(args, "before", ""), getattr(args, "git_ref", ""), args.strict)
    if args.subcommand == "generate-smoke-test":
        return cmd_generate_smoke_test(target, getattr(args, "out", ""), getattr(args, "before", ""), getattr(args, "git_ref", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
