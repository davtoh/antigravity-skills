#!/usr/bin/env python3
"""Defect Catalog SSOT & JIT Scaffolder (system-diagnostics).

Manages authoritative defect persistence in <workspace>/.diagnostics/defect_catalog.json
and human-readable DEFECT_CATALOG.md, pre-flight git checks, and JIT test scaffolding.
"""

import ast
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Optional

try:
    from scaffold_templates import (
        build_tactical_test_code,
        generate_architectural_brief,
        generate_catalog_markdown,
    )
except ImportError:
    from .scaffold_templates import (
        build_tactical_test_code,
        generate_architectural_brief,
        generate_catalog_markdown,
    )

CATALOG_SCHEMA_VERSION = "1.0"
DIAGNOSTICS_DIRNAME = ".diagnostics"
CATALOG_JSON_FILENAME = "defect_catalog.json"
CATALOG_MD_FILENAME = "DEFECT_CATALOG.md"
GITIGNORE_FILENAME = ".gitignore"
QUARANTINE_DIR = Path("tests") / "quarantine"

IGNORED_RECONCILE_DIRS = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "dist", "build", "_build", "out", "target", ".idea", ".vscode",
    "scratch", "coverage", "htmlcov", "migrations", ".refactor", ".diagnostics",
})


def ensure_diagnostics_dir(workspace: Path) -> Path:
    """Ensure .diagnostics directory and self-contained .gitignore exist."""
    diag_dir = workspace / DIAGNOSTICS_DIRNAME
    diag_dir.mkdir(parents=True, exist_ok=True)
    gitignore = diag_dir / GITIGNORE_FILENAME
    if not gitignore.exists():
        gitignore.write_text(
            "# Auto-generated SSOT defect catalog gitignore\ndefect_catalog.json\nDEFECT_CATALOG.md\n",
            encoding="utf-8",
        )
    return diag_dir


def save_catalog(workspace: Path, defects: list[Any]) -> tuple[Path, Path]:
    """Persist defect catalog to defect_catalog.json (SSOT) and DEFECT_CATALOG.md."""
    diag_dir = ensure_diagnostics_dir(workspace)
    json_path = diag_dir / CATALOG_JSON_FILENAME
    md_path = diag_dir / CATALOG_MD_FILENAME

    defect_dicts = []
    by_track: dict[str, int] = {"tactical": 0, "architectural": 0}
    by_severity: dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}

    for d in defects:
        d_dict = d if isinstance(d, dict) else (d.to_dict() if hasattr(d, "to_dict") else asdict(d))
        defect_dicts.append(d_dict)
        trk = d_dict.get("track", "tactical")
        by_track[trk] = by_track.get(trk, 0) + 1
        sev = d_dict.get("severity", "MEDIUM")
        by_severity[sev] = by_severity.get(sev, 0) + 1

    catalog_data = {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "workspace": str(workspace.resolve()).replace("\\", "/"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": len(defect_dicts),
            "by_track": by_track,
            "by_severity": by_severity,
        },
        "defects": defect_dicts,
    }

    json_path.write_text(json.dumps(catalog_data, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(generate_catalog_markdown(catalog_data), encoding="utf-8")
    return json_path, md_path


def load_catalog(workspace: Path) -> dict[str, Any]:
    """Load defect catalog JSON from workspace .diagnostics/ directory."""
    json_path = workspace / DIAGNOSTICS_DIRNAME / CATALOG_JSON_FILENAME
    if not json_path.is_file():
        return {
            "schema_version": CATALOG_SCHEMA_VERSION,
            "workspace": str(workspace.resolve()).replace("\\", "/"),
            "updated_at": "",
            "summary": {"total": 0, "by_track": {"tactical": 0, "architectural": 0}, "by_severity": {"HIGH": 0, "MEDIUM": 0, "LOW": 0}},
            "defects": [],
        }
    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "schema_version": CATALOG_SCHEMA_VERSION,
            "workspace": str(workspace.resolve()).replace("\\", "/"),
            "updated_at": "",
            "summary": {"total": 0, "by_track": {}, "by_severity": {}},
            "defects": [],
        }


def check_git_dirty(workspace: Path) -> tuple[bool, list[str]]:
    """Check working tree for uncommitted changes, ignoring .diagnostics/ and .refactor/."""
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=workspace, capture_output=True, text=True, timeout=5.0, check=False,
        )
        if res.returncode != 0:
            return False, []
    except Exception:
        return False, []

    dirty_files = []
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line or len(line) < 3:
            continue
        rel_file = line[3:].strip().replace("\\", "/")
        if rel_file.startswith((".diagnostics/", ".refactor/", ".diagnostics\\", ".refactor\\")):
            continue
        dirty_files.append(rel_file)

    return len(dirty_files) > 0, dirty_files


def checkout_micro_branch(workspace: Path, branch_name: str) -> tuple[bool, str]:
    """Create and checkout micro-branch for defect isolation."""
    try:
        res = subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=workspace, capture_output=True, text=True, timeout=5.0, check=False,
        )
        if res.returncode == 0:
            return True, branch_name
        res2 = subprocess.run(
            ["git", "checkout", branch_name],
            cwd=workspace, capture_output=True, text=True, timeout=5.0, check=False,
        )
        if res2.returncode == 0:
            return True, branch_name
        return False, res.stderr.strip() or res2.stderr.strip()
    except Exception as exc:
        return False, str(exc)


def reconcile_defect(workspace: Path, defect: dict[str, Any]) -> dict[str, Any]:
    """Reconcile defect file and line number dynamically if code moved during refactoring."""
    file_rel = defect.get("file", "")
    target_path = workspace / file_rel
    symbol = defect.get("symbol", "")

    if target_path.is_file() and target_path.suffix == ".py":
        try:
            tree = ast.parse(target_path.read_text(encoding="utf-8", errors="replace"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if node.name == symbol:
                        defect["line"] = node.lineno
                        return defect
        except Exception:
            pass
        return defect

    if symbol:
        for p in workspace.rglob("*.py"):
            if any(part in IGNORED_RECONCILE_DIRS for part in p.parts):
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                if symbol in content:
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                            if node.name == symbol:
                                defect["file"] = str(p.relative_to(workspace)).replace("\\", "/")
                                defect["line"] = node.lineno
                                return defect
            except Exception:
                continue
    return defect


def scaffold_tactical_test(workspace: Path, defect: dict[str, Any]) -> Path:
    """Synthesize failing-first reproduction test in tests/quarantine/."""
    q_dir = workspace / QUARANTINE_DIR
    q_dir.mkdir(parents=True, exist_ok=True)
    init_file = q_dir / "__init__.py"
    if not init_file.exists():
        init_file.write_text("", encoding="utf-8")

    d_id = defect.get("id", "DEFECT-001")
    id_clean = re.sub(r"[^a-zA-Z0-9_]", "_", d_id.lower())
    test_path = q_dir / f"test_{id_clean}.py"

    test_code = build_tactical_test_code(
        d_id=d_id,
        rule_id=defect.get("rule_id", "UNKNOWN_RULE"),
        rel_file=defect.get("file", ""),
        symbol=defect.get("symbol", ""),
        message=defect.get("message", ""),
        suggested_fix=defect.get("suggested_fix", ""),
    )
    test_path.write_text(test_code, encoding="utf-8")
    return test_path


def scaffold_defect(
    workspace: Path,
    defect_id_or_fp: str,
    branch: bool = False,
    elevate: bool = False,
    fix: bool = False,
) -> dict[str, Any]:
    """Unlock and scaffold defect for remediation via /app-debugger or /frontier-architect."""
    catalog = load_catalog(workspace)
    defects = catalog.get("defects", [])

    target_key = defect_id_or_fp.strip().upper()
    found: Optional[dict[str, Any]] = None
    for d in defects:
        if d.get("id", "").upper() == target_key or d.get("fingerprint", "").upper() == target_key:
            found = d
            break

    if not found:
        raise ValueError(
            f"Defect '{defect_id_or_fp}' not found in catalog ({len(defects)} defect(s) indexed). "
            f"Run scan or check .diagnostics/defect_catalog.json."
        )

    found = reconcile_defect(workspace, found)

    branch_name: Optional[str] = None
    if branch:
        is_dirty, dirty_files = check_git_dirty(workspace)
        if is_dirty:
            print(
                f"[Safety Notice] Working tree contains uncommitted edits ({len(dirty_files)} file(s)); "
                f"skipping branch checkout to protect unstaged work.",
                file=sys.stderr,
            )
        else:
            short_id = found.get("id", "001").lower().replace("defect-", "")
            b_target = f"fix/defect-{short_id}"
            success, b_res = checkout_micro_branch(workspace, b_target)
            if success:
                branch_name = b_target
            else:
                print(f"[Branch Warning] Could not checkout '{b_target}': {b_res}", file=sys.stderr)

    effective_track = "tactical" if fix else ("architectural" if elevate else found.get("track", "tactical"))

    if effective_track == "architectural":
        brief = generate_architectural_brief(found)
        found["status"] = "elevated"
        save_catalog(workspace, defects)
        return {
            "status": "elevated",
            "track": "architectural",
            "defect": found,
            "brief": brief,
            "branch": branch_name,
            "instructions": "Invoke /frontier-architect and /grill-me for a 3-tier redesign.",
        }

    test_file = scaffold_tactical_test(workspace, found)
    found["status"] = "scaffolded"
    save_catalog(workspace, defects)
    rel_test = str(test_file.relative_to(workspace)).replace("\\", "/")
    return {
        "status": "scaffolded",
        "track": "tactical",
        "defect": found,
        "test_file": str(test_file),
        "test_file_rel": rel_test,
        "branch": branch_name,
        "commands": [
            f"python -m unittest {rel_test}",
            f"# Apply fix in {found.get('file', '')}, then re-verify:",
            f"python -m unittest {rel_test}",
        ],
    }


def cmd_scaffold_defect(args: Any) -> int:
    """CLI handler for `diagnose.py scaffold-defect`."""
    workspace = Path(args.path).resolve() if getattr(args, "path", None) else Path.cwd()
    try:
        result = scaffold_defect(
            workspace=workspace,
            defect_id_or_fp=args.id,
            branch=getattr(args, "branch", False),
            elevate=getattr(args, "elevate", False),
            fix=getattr(args, "fix", False),
        )
    except Exception as exc:
        print(f"[diagnose scaffold-defect] Error: {exc}", file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        print(json.dumps(result, indent=2))
        return 0

    d = result["defect"]
    track = result["track"]
    print(f"\n=== Defect Remediation Dispatch: {d.get('id')} ({track.upper()}) ===")
    print(f"File:        {d.get('file')}:{d.get('line')}")
    print(f"Rule:        {d.get('rule_id')} ({d.get('category')})")
    print(f"Message:     {d.get('message')}")
    print(f"Fix Hint:    {d.get('suggested_fix')}")
    if result.get("branch"):
        print(f"Branch:      {result.get('branch')} (Active)")

    if track == "architectural":
        print("\n" + result.get("brief", ""))
        print("\nNext Action: Invoke /frontier-architect and /grill-me with the brief above.")
    else:
        print(f"\nQuarantine Test: {result.get('test_file_rel')}")
        print("\nVerification Commands (/app-debugger):")
        for cmd in result.get("commands", []):
            print(f"  {cmd}")
    print()
    return 0
