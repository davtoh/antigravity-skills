#!/usr/bin/env python3
"""Cross-platform campaign state management for refactoring workflows.

Manages persistent state in <workspace>/.refactor/state.json across conversation
turns, tracks phase progress, and provisions the .refactor directory tree.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# Ensure stdout handles UTF-8 on Windows consoles without charmap UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def get_repo_root(target: Path | None = None) -> Path:
    """Find the root git repository directory containing target."""
    cur = (target or Path.cwd()).resolve()
    for parent in [cur, *cur.parents]:
        if (parent / ".git").exists():
            return parent
    return cur


def get_refactor_dir(target: Path | None = None) -> Path:
    """Get or create the .refactor state directory with subfolders and self-contained .gitignore."""
    rdir = get_repo_root(target) / ".refactor"
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "scripts").mkdir(parents=True, exist_ok=True)
    (rdir / "artifacts").mkdir(parents=True, exist_ok=True)
    gitignore = rdir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(
            "# Local refactoring campaign state, snapshots, and helper scripts\n"
            "# Ignored by default so they never pollute git status; use `git add -f` if versioning is desired.\n"
            "*\n"
            "!.gitignore\n",
            encoding="utf-8",
        )
    return rdir


def get_git_sha(target_dir: Path) -> str:
    """Resolve the active HEAD commit SHA."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=target_dir,
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
        return proc.stdout.strip() if proc.returncode == 0 else ""
    except Exception:
        return ""


def _format_phase_icon(is_completed: bool, is_active: bool) -> str:
    """Return status glyph with automatic ASCII fallback for non-UTF8 terminals."""
    try:
        icon = "✅" if is_completed else ("▶️" if is_active else "⏳")
        if hasattr(sys.stdout, "encoding") and sys.stdout.encoding:
            icon.encode(sys.stdout.encoding)
        return icon
    except Exception:
        return "[x]" if is_completed else ("[>]" if is_active else "[ ]")


def _init_campaign_state(target: Path, state_file: Path, plan: str, phases: int, phase_title: str) -> int:
    """Initialize a brand-new .refactor/state.json campaign."""
    rdir = state_file.parent
    plan_p = plan or str(rdir / "plan.md")
    base_p = str(rdir / "baseline.json")
    init_state = {
        "campaign": target.name,
        "target_path": str(target.as_posix() if hasattr(target, "as_posix") else target),
        "active_phase": 1,
        "total_phases": phases,
        "plan_path": plan_p,
        "baseline_contract": base_p,
        "status": "in_progress",
        "phases": {
            str(i): {
                "title": phase_title if i == 1 and phase_title else f"Phase {i}",
                "status": "active" if i == 1 else "pending",
                "sha": get_git_sha(target) if i == 1 else "",
            }
            for i in range(1, phases + 1)
        },
    }
    state_file.write_text(json.dumps(init_state, indent=2), encoding="utf-8")
    print(f"Initialized refactoring campaign state -> {state_file}")
    print(f"  Active Phase: 1 of {phases} | Target: {target.name} | Plan: {plan_p}")
    return 0


def _advance_campaign_state(target: Path, state_file: Path, state: dict[str, Any], phase: int | None, status: str, sha: str) -> int:
    """Mark active phase complete and advance campaign to next phase."""
    cur = phase or state.get("active_phase", 1)
    total = state.get("total_phases", 4)
    p_str = str(cur)
    if p_str in state.get("phases", {}):
        state["phases"][p_str]["status"] = status or "completed"
        if sha:
            state["phases"][p_str]["sha"] = sha
        elif not state["phases"][p_str].get("sha"):
            state["phases"][p_str]["sha"] = get_git_sha(target)
    nxt = cur + 1
    if nxt <= total:
        state["active_phase"] = nxt
        nxt_str = str(nxt)
        if nxt_str in state.get("phases", {}):
            state["phases"][nxt_str]["status"] = "active"
        state["status"] = "in_progress"
        print(f"Advanced campaign: Phase {cur} completed. Active Phase is now {nxt} of {total}.")
    else:
        state["status"] = "completed"
        print(f"Refactoring campaign completed! All {total} phases verified and closed.")
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return 0


def _set_campaign_state(state_file: Path, state: dict[str, Any], phase: int | None, phase_title: str, status: str, sha: str) -> int:
    """Manually update specific campaign properties."""
    if phase is not None:
        state["active_phase"] = phase
        p_str = str(phase)
        if p_str in state.get("phases", {}):
            if status:
                state["phases"][p_str]["status"] = status
            if phase_title:
                state["phases"][p_str]["title"] = phase_title
            if sha:
                state["phases"][p_str]["sha"] = sha
    if status and phase is None:
        state["status"] = status
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"Updated campaign state: Active Phase {state.get('active_phase')}, status={state.get('status')}")
    return 0


def _add_state_cli_args(p_st: Any) -> None:
    """Configure arguments for campaign state subcommand."""
    p_st.add_argument("--path", default=".", help="Target repository directory.")
    p_st.add_argument("--action", choices=["init", "show", "status", "advance", "set", "checkpoint"], default="show", help="Action.")
    p_st.add_argument("--init", dest="action", action="store_const", const="init", help="Initialize new campaign state.")
    p_st.add_argument("--advance", dest="action", action="store_const", const="advance", help="Mark current phase completed and advance.")
    p_st.add_argument("--show", dest="action", action="store_const", const="show", help="Display current campaign progress.")
    p_st.add_argument("--status-cmd", dest="action", action="store_const", const="status", help="Alias for show.")
    p_st.add_argument("--checkpoint", dest="action", action="store_const", const="checkpoint", help="Record intermediate slice checkpoint.")
    p_st.add_argument("--note", default="", help="Note or description for intermediate slice checkpoint.")
    p_st.add_argument("--target", default="", help="Refactoring target directory.")
    p_st.add_argument("--plan", default="", help="Path to refactoring plan markdown.")
    p_st.add_argument("--phases", type=int, default=4, help="Total phases in campaign.")
    p_st.add_argument("--phase", default=None, help="Specific phase number/sub-phase to update/advance.")
    p_st.add_argument("--phase-title", default="", help="Title for the active phase.")
    p_st.add_argument("--status", default="", help="Status string (e.g. completed, in_progress, pending).")
    p_st.add_argument("--sha", default="", help="Commit SHA to record.")
    p_st.add_argument("--json", action="store_true", help="Output state as JSON.")


def _save_checkpoint(state_file: Path, state: dict[str, Any], note: str, sha: str, target: Path) -> int:
    """Save an intermediate slice checkpoint into state.json."""
    c_sha = sha or get_git_sha(target)
    state["last_checkpoint"] = {
        "note": note or "Intermediate slice verified",
        "sha": c_sha,
    }
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
    sha_str = f" ({c_sha[:7]})" if c_sha else ""
    print(f"Saved campaign checkpoint: {note or 'Intermediate slice'}{sha_str}")
    print("[Turn Budget Tip] If this turn has reached 20-25 tool calls, commit and run `/refactor-monolith continue` in a fresh chat.")
    return 0


def _dispatch_state_action(
    target: Path,
    state_file: Path,
    state: dict[str, Any],
    action: str,
    phase: Any,
    phase_title: str,
    status: str,
    sha: str,
    note: str,
    as_json: bool,
) -> int:
    """Dispatch campaign state mutations or display."""
    p_val = int(phase) if phase and str(phase).isdigit() else None
    if action == "checkpoint":
        return _save_checkpoint(state_file, state, note, sha, target)
    if action == "advance":
        return _advance_campaign_state(target, state_file, state, p_val, status, sha)
    if action == "set":
        return _set_campaign_state(state_file, state, p_val, phase_title, status, sha)
    if as_json:
        print(json.dumps(state, indent=2))
        return 0
    return _print_campaign_summary(state)


def cmd_state(
    target: Path,
    action: str,
    plan: str = "",
    phases: int = 4,
    phase: Any = None,
    phase_title: str = "",
    status: str = "",
    sha: str = "",
    note: str = "",
    as_json: bool = False,
) -> int:
    """Initialize, inspect, or advance persistent refactoring campaign state."""
    rdir = get_refactor_dir(target)
    state_file = rdir / "state.json"
    if action == "init":
        return _init_campaign_state(target, state_file, plan, phases, phase_title)

    if not state_file.exists():
        print(f"No active campaign state found at {state_file}. Run `contract_snapshot.py state --init` first.", file=sys.stderr)
        return 1

    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception as err:
        print(f"Error reading {state_file}: {err}", file=sys.stderr)
        return 1

    return _dispatch_state_action(
        target, state_file, state, action, phase, phase_title, status, sha, note, as_json
    )


def _parse_phase_sort_key(key: str) -> float:
    try:
        return float(key)
    except ValueError:
        return 999.0


def _print_campaign_summary(state: dict[str, Any]) -> int:
    """Print structured summary of campaign phases and resumption instructions."""
    act = state.get("active_phase", 1)
    tot = state.get("total_phases", 4)
    st = state.get("status", "unknown")
    phases_map = state.get("phases", {})
    act_title = phases_map.get(str(act), {}).get("title", f"Phase {act}")

    print("=== Active Refactoring Campaign State ===")
    print(f"Target Subsystem:  {state.get('target_path', '.')}")
    print(f"Campaign Status:   {st.upper()} (Active: Phase {act} of {tot})")
    print(f"Plan Document:     {state.get('plan_path', '.refactor/plan.md')}")
    print(f"Baseline Snapshot: {state.get('baseline_contract', '.refactor/baseline.json')}")
    if state.get("last_checkpoint"):
        chk = state["last_checkpoint"]
        sha_str = f" ({chk.get('sha')[:7]})" if chk.get("sha") else ""
        print(f"Last Checkpoint:   {chk.get('note', '')}{sha_str}")

    print("\n--- Phases Overview ---")
    for p_num, p_info in sorted(phases_map.items(), key=lambda x: _parse_phase_sort_key(x[0])):
        icon = _format_phase_icon(p_info.get("status") == "completed", str(p_num) == str(act))
        sha_str = f" ({p_info.get('sha')[:7]})" if p_info.get("sha") else ""
        print(f"  {icon} Phase {p_num}: {p_info.get('title', '')} [{p_info.get('status', 'pending')}]{sha_str}")

    if st != "completed":
        print(f"\n--- Resumption Instruction for Next Chat ---")
        print(f"To continue Phase {act} ({act_title}) in a fresh chat, tell the agent:")
        print(f"  /refactor-monolith continue")
    return 0
