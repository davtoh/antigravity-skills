#!/usr/bin/env python3
"""Zero-dependency opportunistic code formatter engine for refactoring slices.

Discovers and runs local formatters (Ruff, Black, Prettier, gofmt, rustfmt, dart format)
strictly on modified slice files. Enforces the Resilient Hybrid Gate:
- If a tool is present and fails on syntax errors, it hard-fails early to protect tests.
- If a tool is absent, it gracefully bypasses and relies on self-contained SLOC heuristics.
- NEVER runs repository-wide, protecting untouched defect catalog line numbers.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

# File extension mappings to language keys
_PY_EXTS = frozenset({".py", ".pyi"})
_JS_EXTS = frozenset({".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".css", ".scss", ".less", ".html", ".json"})
_GO_EXTS = frozenset({".go"})
_RS_EXTS = frozenset({".rs"})
_DART_EXTS = frozenset({".dart"})

def _resolve_venv_bin(base_dir: Path, bin_name: str) -> str | None:
    """Find a binary inside local virtualenv directories if present."""
    candidates = [
        base_dir / ".venv", base_dir / "venv", base_dir / "env",
        base_dir.parent / ".venv", base_dir.parent / "venv",
    ]
    for v in candidates:
        if v.is_dir():
            target = v / "Scripts" / (bin_name + ".exe") if os.name == "nt" else v / "bin" / bin_name
            if target.is_file():
                return str(target)
    return None

def _resolve_node_bin(base_dir: Path, bin_name: str) -> str | None:
    """Find a local npm binary in node_modules/.bin if present."""
    cur = base_dir.resolve()
    for p in [cur, *cur.parents]:
        bin_path = p / "node_modules" / ".bin" / (bin_name + ".cmd" if os.name == "nt" else bin_name)
        if bin_path.is_file():
            return str(bin_path)
    return None

def resolve_formatter_command(lang: str, base_dir: Path) -> list[str] | None:
    """Resolve the preferred formatter command for a given language group."""
    if lang == "python":
        if ruff := _resolve_venv_bin(base_dir, "ruff"):
            return [ruff, "format"]
        if shutil.which("ruff"):
            return ["ruff", "format"]
        if black := _resolve_venv_bin(base_dir, "black"):
            return [black]
        if shutil.which("black"):
            return ["black"]
        return None

    if lang == "javascript":
        if prettier := _resolve_node_bin(base_dir, "prettier"):
            return [prettier, "--write"]
        if shutil.which("prettier"):
            return ["prettier", "--write"]
        if shutil.which("npx"):
            return ["npx", "--no-install", "prettier", "--write"]
        return None

    if lang == "go":
        return ["gofmt", "-w"] if shutil.which("gofmt") else None

    if lang == "rust":
        return ["rustfmt"] if shutil.which("rustfmt") else None

    if lang == "dart":
        return ["dart", "format"] if shutil.which("dart") else None

    return None

def group_files_by_language(files: Sequence[Path]) -> dict[str, list[Path]]:
    """Partition filepaths into supported language formatter groups."""
    groups: dict[str, list[Path]] = {}
    for f in files:
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        if ext in _PY_EXTS:
            groups.setdefault("python", []).append(f)
        elif ext in _JS_EXTS:
            groups.setdefault("javascript", []).append(f)
        elif ext in _GO_EXTS:
            groups.setdefault("go", []).append(f)
        elif ext in _RS_EXTS:
            groups.setdefault("rust", []).append(f)
        elif ext in _DART_EXTS:
            groups.setdefault("dart", []).append(f)
    return groups

def _run_lang_formatter(cmd: list[str], paths: Sequence[Path], target_dir: Path, lang: str) -> bool:
    """Run formatter subprocess for a group of files. Returns True on error."""
    full_cmd = [*cmd, *[str(p) for p in paths]]
    try:
        res = subprocess.run(
            full_cmd,
            cwd=target_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if res.returncode == 0:
            print(f"  [Formatter] Formatted {len(paths)} {lang} file(s) with {Path(cmd[0]).name}.")
            return False
        err_msg = (res.stderr or res.stdout).strip()
        print(f"  [CRITICAL FORMATTER ERROR] {Path(cmd[0]).name} failed on {lang} file(s):\n{err_msg}")
        return True
    except subprocess.TimeoutExpired:
        print(f"  [Formatter Warning] Formatting timed out after 30s for {lang}; skipping.")
        return False
    except Exception as e:
        print(f"  [Formatter Warning] Could not execute {cmd[0]}: {e}")
        return False

def format_slice_files(target_dir: Path, file_paths: Sequence[str | Path]) -> int:
    """Opportunistically format slice files with installed formatters.
    
    Returns 0 on success or graceful bypass; returns 1 on syntax/formatter error.
    """
    resolved_files = [Path(p).resolve() if not Path(p).is_absolute() else Path(p) for p in file_paths]
    existing = [f for f in resolved_files if f.is_file()]
    if not existing:
        return 0

    groups = group_files_by_language(existing)
    if not groups:
        return 0

    has_error = False
    for lang, paths in sorted(groups.items()):
        cmd = resolve_formatter_command(lang, target_dir)
        if not cmd:
            print(f"  [Formatter] No {lang} formatter detected (ruff/black/prettier); bypassing (SLOC verified).")
            continue
        if _run_lang_formatter(cmd, paths, target_dir, lang):
            has_error = True

    return 1 if has_error else 0
