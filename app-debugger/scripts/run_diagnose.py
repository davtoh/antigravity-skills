#!/usr/bin/env python3
"""Dynamic resolver and executor for system-diagnostics from app-debugger.

Discovers diagnose.py across environment variables, sibling directories,
workspace trees, and global user configurations. If missing, prints actionable
installation instructions and graceful fallback diagnostics.
Zero external dependencies; standard library Python 3.10+ only.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _get_candidate_paths(base_dir: Path | None = None) -> list[Path]:
    """Generate prioritized candidate filepaths for diagnose.py."""
    candidates: list[Path] = []
    if os.environ.get("DIAGNOSE_CLI_PATH"):
        candidates.append(Path(os.environ["DIAGNOSE_CLI_PATH"]))
    if os.environ.get("SYSTEM_DIAGNOSTICS_DIR"):
        candidates.append(Path(os.environ["SYSTEM_DIAGNOSTICS_DIR"]) / "scripts" / "diagnose.py")

    # Sibling skill directory relative to this script
    script_dir = Path(__file__).resolve().parent
    candidates.append(script_dir.parent.parent / "system-diagnostics" / "scripts" / "diagnose.py")

    # Workspace directory tree search
    cwd = base_dir.resolve() if base_dir else Path.cwd().resolve()
    for root in [cwd, *cwd.parents[:3]]:
        candidates.append(root / "skills" / "system-diagnostics" / "scripts" / "diagnose.py")
        candidates.append(root / ".gemini" / "skills" / "system-diagnostics" / "scripts" / "diagnose.py")
        candidates.append(root / ".gemini" / "config" / "skills" / "system-diagnostics" / "scripts" / "diagnose.py")

    # User home global configuration
    home = Path.home()
    candidates.append(home / ".gemini" / "config" / "skills" / "system-diagnostics" / "scripts" / "diagnose.py")
    candidates.append(home / ".gemini" / "skills" / "system-diagnostics" / "scripts" / "diagnose.py")
    return candidates


def resolve_diagnose_path(base_dir: Path | None = None) -> Path | None:
    """Locate diagnose.py or return None if unavailable."""
    for candidate in _get_candidate_paths(base_dir):
        try:
            if candidate.is_file():
                return candidate.resolve()
        except (OSError, PermissionError):
            continue
    return None


def print_missing_dependency_recipe() -> None:
    """Print actionable installation recipes when system-diagnostics is absent."""
    msg = """[app-debugger] Error: 'system-diagnostics' tool engine not found.

The app-debugger workflow relies on system-diagnostics (diagnose.py) for
empirical 3-tier proof (DOM layout inspection, container audits, surface scans).

To resolve this dependency:
  1. Global / Sibling install (Recommended):
     Clone or place system-diagnostics in:
       ~/.gemini/config/skills/system-diagnostics/
  2. Workspace install:
     Place system-diagnostics in:
       <workspace>/skills/system-diagnostics/
  3. Environment Variable override:
     Set SYSTEM_DIAGNOSTICS_DIR=/path/to/system-diagnostics
     or DIAGNOSE_CLI_PATH=/path/to/system-diagnostics/scripts/diagnose.py
"""
    print(msg, file=sys.stderr)


def main(args: list[str] | None = None) -> int:
    """Discover diagnose.py and forward arguments, or report status/missing error."""
    cli_args = sys.argv[1:] if args is None else args

    if cli_args and cli_args[0] in ("--probe", "--status"):
        resolved = resolve_diagnose_path()
        if resolved:
            print(f"[app-debugger] system-diagnostics engine found: {resolved}")
            return 0
        print_missing_dependency_recipe()
        return 1

    diagnose_bin = resolve_diagnose_path()
    if not diagnose_bin:
        print_missing_dependency_recipe()
        return 1

    cmd = [sys.executable, str(diagnose_bin), *cli_args]
    try:
        proc = subprocess.run(cmd, check=False)
        return proc.returncode
    except Exception as err:
        print(f"[app-debugger] Execution error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

