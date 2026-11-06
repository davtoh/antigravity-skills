#!/usr/bin/env python3
"""Defect Catalog SSOT & JIT Scaffolder (system-diagnostics).

Manages authoritative defect persistence in <workspace>/.diagnostics/defect_catalog.json
and human-readable DEFECT_CATALOG.md, stateful lifecycle transitions, git safety, and JIT tests.
"""

import ast
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Optional

try:
    from scaffold_templates import (
        CLOSED_STATUSES, build_tactical_test_code, generate_architectural_brief, generate_catalog_markdown,
    )
except ImportError:
    from .scaffold_templates import (
        CLOSED_STATUSES, build_tactical_test_code, generate_architectural_brief, generate_catalog_markdown,
    )

CATALOG_SCHEMA_VERSION = "1.0"
DIAGNOSTICS_DIRNAME = ".diagnostics"
CATALOG_JSON_FILENAME = "defect_catalog.json"
CATALOG_MD_FILENAME = "DEFECT_CATALOG.md"
GITIGNORE_FILENAME = ".gitignore"
QUARANTINE_DIR = Path("tests") / "quarantine"
ACTIVE_STATUSES = frozenset({"quarantined", "scaffolded", "elevated"})
IGNORED_RECONCILE_DIRS = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist", "build", "_build",
    "out", "target", ".idea", ".vscode", "scratch", "coverage", "htmlcov",
    "migrations", ".refactor", ".diagnostics",
})


def ensure_diagnostics_dir(workspace: Path) -> Path:
    """Ensure .diagnostics directory and self-contained .gitignore exist."""
    diag_dir = workspace / DIAGNOSTICS_DIRNAME
    diag_dir.mkdir(parents=True, exist_ok=True)
    gitignore = diag_dir / GITIGNORE_FILENAME
    if not gitignore.exists():
        gitignore.write_text(
            "# Auto-generated SSOT defect catalog gitignore\n"
            "# Ignored by default so they never pollute git status; use `git add -f` if versioning is desired.\n*\n",
            encoding="utf-8",
        )
    return diag_dir


def _to_defect_dict(d: Any) -> dict[str, Any]:
    """Normalize a DefectFinding or dict into a standard catalog dictionary."""
    return dict(d) if isinstance(d, dict) else (d.to_dict() if hasattr(d, "to_dict") else asdict(d))


def _merge_scan_defects(
    existing: list[dict[str, Any]], incoming: list[dict[str, Any]], prune: bool = False
) -> list[dict[str, Any]]:
    """Reconcile incoming scan findings with prior catalog state by fingerprint."""
    prev_by_fp = {d.get("fingerprint", ""): d for d in existing if d.get("fingerprint")}
    incoming_fps = {d.get("fingerprint", "") for d in incoming if d.get("fingerprint")}
    now_iso = datetime.now(timezone.utc).isoformat()
    merged: list[dict[str, Any]] = []

    for inc in incoming:
        prev = prev_by_fp.get(inc.get("fingerprint", ""))
        if prev:
            prev_st = prev.get("status", "quarantined")
            if prev_st in ("dismissed", "scaffolded", "elevated") or (prev_st == "resolved" and prev.get("explicit_resolution")):
                inc["status"] = prev_st
                for key in ("resolution", "resolved_at", "explicit_resolution"):
                    if key in prev:
                        inc[key] = prev[key]
        merged.append(inc)

    if not prune:
        for fp, prev in prev_by_fp.items():
            if fp not in incoming_fps:
                prev_copy = dict(prev)
                if prev_copy.get("status", "quarantined") in ACTIVE_STATUSES:
                    prev_copy["status"] = "resolved"
                    prev_copy["resolved_at"] = now_iso
                    prev_copy["resolution"] = prev_copy.get("resolution") or "Auto-resolved: defect no longer detected in scan."
                merged.append(prev_copy)

    for idx, item in enumerate(merged, start=1):
        item["id"] = f"DEFECT-{idx:03d}"
    return merged


def save_catalog(
    workspace: Path, defects: list[Any], reconcile_scan: bool = False, prune: bool = False
) -> tuple[Path, Path]:
    """Persist defect catalog to defect_catalog.json (SSOT) and DEFECT_CATALOG.md."""
    diag_dir = ensure_diagnostics_dir(workspace)
    json_path, md_path = diag_dir / CATALOG_JSON_FILENAME, diag_dir / CATALOG_MD_FILENAME
    defect_dicts = [_to_defect_dict(d) for d in defects]
    if reconcile_scan and json_path.is_file():
        defect_dicts = _merge_scan_defects(load_catalog(workspace).get("defects", []), defect_dicts, prune=prune)
    elif prune:
        defect_dicts = [d for d in defect_dicts if d.get("status", "quarantined") not in CLOSED_STATUSES]

    by_track: dict[str, int] = {"tactical": 0, "architectural": 0}
    by_severity: dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    active_count = resolved_count = dismissed_count = 0

    for d_dict in defect_dicts:
        st = d_dict.get("status", "quarantined")
        if st == "resolved":
            resolved_count += 1
        elif st == "dismissed":
            dismissed_count += 1
        else:
            active_count += 1
            trk = d_dict.get("track", "tactical")
            by_track[trk] = by_track.get(trk, 0) + 1
            sev = d_dict.get("severity", "MEDIUM")
            by_severity[sev] = by_severity.get(sev, 0) + 1

    catalog_data = {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "workspace": str(workspace.resolve()).replace("\\", "/"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": active_count, "active": active_count, "resolved": resolved_count,
            "dismissed": dismissed_count, "total_tracked": len(defect_dicts),
            "by_track": by_track, "by_severity": by_severity,
        },
        "defects": defect_dicts,
    }
    json_path.write_text(json.dumps(catalog_data, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(generate_catalog_markdown(catalog_data), encoding="utf-8")
    return json_path, md_path


def load_catalog(workspace: Path) -> dict[str, Any]:
    """Load defect catalog JSON from workspace .diagnostics/ directory."""
    json_path = workspace / DIAGNOSTICS_DIRNAME / CATALOG_JSON_FILENAME
    empty = {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "workspace": str(workspace.resolve()).replace("\\", "/"),
        "updated_at": "",
        "summary": {
            "total": 0, "active": 0, "resolved": 0, "dismissed": 0, "total_tracked": 0,
            "by_track": {"tactical": 0, "architectural": 0}, "by_severity": {"HIGH": 0, "MEDIUM": 0, "LOW": 0},
        },
        "defects": [],
    }
    if not json_path.is_file():
        return empty
    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return empty


def update_defect_status(
    workspace: Path, defect_id_or_fp: str, new_status: str, note: str = ""
) -> list[dict[str, Any]]:
    """Mark one or more comma-separated defect IDs/fingerprints as resolved or dismissed."""
    defects = load_catalog(workspace).get("defects", [])
    keys = {k.strip().upper() for k in defect_id_or_fp.split(",") if k.strip()}
    now_iso = datetime.now(timezone.utc).isoformat()
    updated: list[dict[str, Any]] = []

    for d in defects:
        if d.get("id", "").upper() in keys or d.get("fingerprint", "").upper() in keys or d.get("rule_id", "").upper() in keys:
            d["status"] = new_status
            d["resolved_at"] = now_iso
            d["resolution"] = note or f"Marked {new_status} via CLI."
            d["explicit_resolution"] = True
            updated.append(d)

    if not updated:
        raise ValueError(f"Defect '{defect_id_or_fp}' not found in catalog ({len(defects)} tracked).")
    save_catalog(workspace, defects, reconcile_scan=False)
    return updated


def check_git_dirty(workspace: Path) -> tuple[bool, list[str]]:
    """Check working tree for uncommitted changes, ignoring .diagnostics/ and .refactor/."""
    try:
        res = subprocess.run(["git", "status", "--porcelain"], cwd=workspace, capture_output=True, text=True, timeout=5.0, check=False)
        if res.returncode != 0:
            return False, []
    except Exception:
        return False, []
    dirty = [
        line[3:].strip().replace("\\", "/") for line in res.stdout.splitlines()
        if len(line.strip()) >= 3 and not line[3:].strip().replace("\\", "/").startswith((".diagnostics/", ".refactor/"))
    ]
    return len(dirty) > 0, dirty


def checkout_micro_branch(workspace: Path, branch_name: str) -> tuple[bool, str]:
    """Create and checkout micro-branch for defect isolation."""
    for flag in (["-b", branch_name], [branch_name]):
        try:
            res = subprocess.run(["git", "checkout", *flag], cwd=workspace, capture_output=True, text=True, timeout=5.0, check=False)
            if res.returncode == 0:
                return True, branch_name
        except Exception as exc:
            return False, str(exc)
    return False, f"Failed to checkout {branch_name}"


def _find_symbol_lineno(tree: ast.AST, symbol: str) -> Optional[int]:
    """Locate line number of `symbol` or `ClassName.method_name` in parsed AST."""
    if "." in symbol:
        cls_target, meth_target = symbol.split(".", 1)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == cls_target:
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == meth_target:
                        return child.lineno
    short = symbol.split(".")[-1]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in (symbol, short):
            return node.lineno
    return None


def reconcile_defect(workspace: Path, defect: dict[str, Any]) -> dict[str, Any]:
    """Reconcile defect file and line number dynamically if code moved during refactoring."""
    target_path = workspace / defect.get("file", "")
    symbol = defect.get("symbol", "")
    if target_path.is_file() and target_path.suffix == ".py":
        try:
            lineno = _find_symbol_lineno(ast.parse(target_path.read_text(encoding="utf-8", errors="replace")), symbol)
            if lineno is not None:
                defect["line"] = lineno
        except Exception:
            pass
        return defect

    short = symbol.split(".")[-1] if symbol else ""
    if short:
        for p in workspace.rglob("*.py"):
            if any(part in IGNORED_RECONCILE_DIRS for part in p.parts):
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                if short in content:
                    lineno = _find_symbol_lineno(ast.parse(content), symbol)
                    if lineno is not None:
                        defect["file"] = str(p.relative_to(workspace)).replace("\\", "/")
                        defect["line"] = lineno
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
    test_path = q_dir / f"test_{re.sub(r'[^a-zA-Z0-9_]', '_', d_id.lower())}.py"
    test_path.write_text(
        build_tactical_test_code(
            d_id=d_id, rule_id=defect.get("rule_id", "UNKNOWN_RULE"), rel_file=defect.get("file", ""),
            symbol=defect.get("symbol", ""), message=defect.get("message", ""), suggested_fix=defect.get("suggested_fix", ""),
        ),
        encoding="utf-8",
    )
    return test_path


def scaffold_defect(
    workspace: Path, defect_id_or_fp: str, branch: bool = False, elevate: bool = False, fix: bool = False
) -> dict[str, Any]:
    """Unlock and scaffold defect for remediation via /app-debugger or /frontier-architect."""
    defects = load_catalog(workspace).get("defects", [])
    target_key = defect_id_or_fp.strip().upper()
    found = next((d for d in defects if d.get("id", "").upper() == target_key or d.get("fingerprint", "").upper() == target_key), None)
    if not found:
        raise ValueError(f"Defect '{defect_id_or_fp}' not found in catalog ({len(defects)} defect(s) indexed).")
    found = reconcile_defect(workspace, found)
    branch_name: Optional[str] = None
    if branch:
        is_dirty, dirty_files = check_git_dirty(workspace)
        if is_dirty:
            print(f"[Safety Notice] Working tree contains uncommitted edits ({len(dirty_files)} file(s)); skipping branch checkout to protect unstaged work.", file=sys.stderr)
        else:
            b_target = f"fix/defect-{found.get('id', '001').lower().replace('defect-', '')}"
            ok, _ = checkout_micro_branch(workspace, b_target)
            branch_name = b_target if ok else None

    effective_track = "tactical" if fix else ("architectural" if elevate else found.get("track", "tactical"))
    if effective_track == "architectural":
        found["status"] = "elevated"
        save_catalog(workspace, defects)
        return {"status": "elevated", "track": "architectural", "defect": found, "brief": generate_architectural_brief(found), "branch": branch_name, "instructions": "Invoke /frontier-architect and /grill-me for a 3-tier redesign."}

    test_file = scaffold_tactical_test(workspace, found)
    found["status"] = "scaffolded"
    save_catalog(workspace, defects)
    rel_test = str(test_file.relative_to(workspace)).replace("\\", "/")
    return {
        "status": "scaffolded", "track": "tactical", "defect": found, "test_file": str(test_file), "test_file_rel": rel_test, "branch": branch_name,
        "commands": [f"python -m unittest {rel_test}", f"# Apply fix in {found.get('file', '')}, then re-verify:", f"python -m unittest {rel_test}"],
    }


def cmd_scaffold_defect(args: Any) -> int:
    """CLI handler for `diagnose.py scaffold-defect`."""
    workspace = Path(args.path).resolve() if getattr(args, "path", None) else Path.cwd()
    try:
        res = scaffold_defect(workspace, args.id, getattr(args, "branch", False), getattr(args, "elevate", False), getattr(args, "fix", False))
    except Exception as exc:
        print(f"[diagnose scaffold-defect] Error: {exc}", file=sys.stderr)
        return 1
    if getattr(args, "json", False):
        print(json.dumps(res, indent=2))
        return 0
    d = res["defect"]
    print(f"\n=== Defect Remediation Dispatch: {d.get('id')} ({res['track'].upper()}) ===\nFile: {d.get('file')}:{d.get('line')} | Rule: {d.get('rule_id')}")
    print(res.get("brief", "") if res["track"] == "architectural" else f"Quarantine Test: {res.get('test_file_rel')}")
    return 0


def cmd_status_transition(args: Any, target_status: str) -> int:
    """CLI handler for `resolve-defect` and `dismiss-defect`."""
    workspace = Path(args.path).resolve() if getattr(args, "path", None) else Path.cwd()
    note = getattr(args, "note", None) or getattr(args, "reason", None) or ""
    try:
        updated = update_defect_status(workspace, args.id, target_status, note=note)
    except Exception as exc:
        print(f"[diagnose {target_status}-defect] Error: {exc}", file=sys.stderr)
        return 1
    if getattr(args, "json", False):
        print(json.dumps({"status": target_status, "updated_count": len(updated), "defects": updated}, indent=2))
        return 0
    print(f"[diagnose] Marked {len(updated)} defect(s) as '{target_status}': {', '.join(d.get('id', '') for d in updated)}")
    return 0
