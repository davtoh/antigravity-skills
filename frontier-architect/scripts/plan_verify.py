#!/usr/bin/env python3
"""OS-agnostic verification command normalization and execution for plan_engine."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import argparse
import os
import re
import subprocess
import sys

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from plan_parser import parse_plan_markdown
from plan_state import get_frontier_dir, load_json, resolve_plan_path, save_json


def _extract_leading_env(cmd: str) -> tuple[dict[str, str], str]:
    """Extract leading POSIX VAR=VAL assignments so Windows shell=True runs cleanly."""
    extra_env: dict[str, str] = {}
    rest = cmd.lstrip()
    while True:
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=([^\s'\"]+)\s+(.+)$", rest)
        if not m:
            break
        extra_env[m.group(1)] = m.group(2)
        rest = m.group(3).lstrip()
    return extra_env, rest


def _resolve_venv_python(root: Path) -> str | None:
    """Return relative virtualenv python path if .venv/venv/env exists under root."""
    rel_candidates = (
        (".venv\\Scripts\\python.exe", "venv\\Scripts\\python.exe", "env\\Scripts\\python.exe")
        if os.name == "nt"
        else (".venv/bin/python", "venv/bin/python", "env/bin/python")
    )
    for rel in rel_candidates:
        if (root / rel.replace("\\", "/")).is_file():
            return rel
    return None


def _normalize_verify_cmd(cmd: str, root: Path) -> str:
    """Normalize leading python/pytest/venv paths for the host OS while preserving arguments."""
    if not cmd.strip():
        return cmd
    stripped = cmd.lstrip()
    quote = stripped[0] if stripped[0] in ('"', "'") else ""
    if quote:
        end_idx = stripped.find(quote, 1)
        if end_idx == -1:
            return cmd
        first_token, rest = stripped[1:end_idx], stripped[end_idx + 1 :]
    else:
        parts = stripped.split(None, 1)
        first_token, rest = parts[0], (" " + parts[1] if len(parts) > 1 else "")
    if first_token in ("python", "python3"):
        venv_py = _resolve_venv_python(root)
        return f"{venv_py}{rest}" if venv_py else cmd
    if first_token == "pytest":
        venv_py = _resolve_venv_python(root)
        return f"{venv_py} -m pytest{rest}" if venv_py else cmd
    if os.name != "nt" or "/" not in first_token:
        return cmd
    clean = first_token.removeprefix("./")
    if clean in (".venv/bin/python", "venv/bin/python", "env/bin/python"):
        win_py = root / clean.split("/")[0] / "Scripts" / "python.exe"
        if win_py.is_file():
            first_token = first_token.replace("/bin/python", "\\Scripts\\python.exe").replace("/", "\\")
    elif clean.startswith((".venv/", "venv/", "env/")) or (root / clean.replace("/", "\\")).exists():
        first_token = first_token.replace("/", "\\")
    return f"{quote}{first_token}{quote}{rest}"


def _parse_test_counts(output: str) -> tuple[int, int]:
    """Extract passed and failed test counts from unittest or pytest output."""
    passed, failed = 0, 0
    ok_match = re.search(r"Ran (\d+) tests?.*?\n\nOK", output)
    if ok_match:
        passed = int(ok_match.group(1))
    fail_match = re.search(r"FAILED \((?:failures=(\d+))?(?:, )?(?:errors=(\d+))?\)", output)
    if fail_match:
        failed = sum(int(x) for x in fail_match.groups() if x)
    if passed == 0 and failed == 0:
        pt_pass = re.search(r"(\d+)\s+passed", output)
        pt_fail = re.search(r"(\d+)\s+failed", output)
        pt_err = re.search(r"(\d+)\s+errors?", output)
        if pt_pass or pt_fail or pt_err:
            passed = int(pt_pass.group(1)) if pt_pass else 0
            failed = (int(pt_fail.group(1)) if pt_fail else 0) + (int(pt_err.group(1)) if pt_err else 0)
    return passed, failed


def cmd_verify(root: Path, args: argparse.Namespace) -> int:
    """Run verification command and update baseline ledger."""
    cmd = args.command
    plan_p = resolve_plan_path(root, args.plan)
    if not cmd and plan_p:
        parsed = parse_plan_markdown(plan_p.read_text(encoding="utf-8"))
        if parsed["verification_commands"]:
            cmd = parsed["verification_commands"][0]
    if not cmd:
        cmd = load_json(get_frontier_dir(root) / "state.json", {}).get("verification_baseline", {}).get("command")
    if not cmd:
        print("[plan_engine] Error: No verification command specified or found in plan. Pass --command \"<cmd>\" or include runnable commands in code blocks / Scenario Matrix tables.")
        return 1
    extra_env, stripped_cmd = _extract_leading_env(cmd)
    exec_cmd = _normalize_verify_cmd(stripped_cmd, root)
    run_env = {**os.environ, **extra_env} if extra_env else None
    print(f"[plan_engine] Running verifier: {exec_cmd}")
    proc = subprocess.run(exec_cmd, shell=True, cwd=root, env=run_env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    output = (proc.stdout or "") + (proc.stderr or "")
    print(output)
    passed, failed = _parse_test_counts(output)
    fdir = get_frontier_dir(root)
    ws = load_json(fdir / "state.json", {})
    ws["verification_baseline"] = {
        "command": cmd, "last_exit_code": proc.returncode,
        "passed_tests": passed, "failed_tests": failed, "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    save_json(fdir / "state.json", ws)
    return proc.returncode
