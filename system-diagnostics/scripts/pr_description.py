#!/usr/bin/env python3
"""Deterministic GitHub PR description generator from CHANGELOG.md, .TODO/ plans, and git history."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from changelog_archive import parse_changelog, resolve_archive_dir


def _run_git(root: Path, *args: str) -> str:
    """Run a read-only git command and return stripped stdout or empty string on error."""
    try:
        res = subprocess.run(
            ["git", *args], cwd=str(root), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=5.0,
        )
        return res.stdout.strip() if res.returncode == 0 else ""
    except Exception:
        return ""


def _resolve_base_ref(root: Path, explicit_base: str | None) -> str:
    """Pick explicit base ref or auto-detect main/master."""
    if explicit_base:
        return explicit_base
    for cand in ("main", "master"):
        if _run_git(root, "rev-parse", "--verify", cand):
            return cand
    return ""


def _load_plan_milestones(root: Path, plan_arg: str | None) -> tuple[str, list[str]]:
    """Extract plan title and checked/milestone bullets from a .TODO/ plan file."""
    if not plan_arg:
        return "", []
    p = Path(plan_arg)
    if not p.is_absolute():
        cand = root / ".TODO" / (plan_arg if plan_arg.endswith(".md") else f"{plan_arg}.md")
        p = cand if cand.is_file() else (root / plan_arg)
    if not p.is_file():
        return "", []
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    title = next((ln[2:].strip() for ln in lines if ln.startswith("# ")), p.stem)
    milestones = [
        ln.lstrip("# ").strip()
        for ln in lines
        if re.match(r"^#{2,3}\s+.*(?:Milestone|Step)\b", ln, re.I)
    ]
    return title, milestones[:12]


def _collect_changelog_items(root: Path, target_log: str, recent: int) -> list[dict[str, str]]:
    """Collect up to ``recent`` entries across active CHANGELOG.md and archive shards."""
    entries: list[Any] = []
    tgt = root / target_log
    if tgt.is_file():
        _, parsed = parse_changelog(tgt.read_text(encoding="utf-8", errors="replace"))
        entries.extend(parsed)
    if len(entries) < recent:
        arch = resolve_archive_dir(root)
        for shard in sorted(arch.glob("changelog_*.md"), reverse=True):
            _, more = parse_changelog(shard.read_text(encoding="utf-8", errors="replace"))
            entries.extend(more)
            if len(entries) >= recent:
                break
    items: list[dict[str, str]] = []
    for e in entries[:recent]:
        summary = next((b.split(":", 1)[1].strip() for b in e.body if b.startswith("- **Summary**:")), "")
        verify = next((b.split(":", 1)[1].strip() for b in e.body if b.startswith("- **Verification**:")), "")
        items.append({"header": e.header.lstrip("# ").strip(), "summary": summary, "verify": verify})
    return items


def _format_pr_markdown(
    branch: str,
    base_ref: str,
    commits: list[str],
    diff_stat: str,
    plan_title: str,
    milestones: list[str],
    changelog_items: list[dict[str, str]],
) -> str:
    """Format gathered git, plan, and changelog data into a GitHub PR body."""
    lines = [f"## Summary ({branch})", ""]
    if plan_title:
        lines.append(f"- **Plan**: {plan_title}")
    if base_ref:
        lines.append(f"- **Base Branch**: `{base_ref}` ({len(commits)} commit(s))")
    lines.extend(["", "### Key Changes & Milestones"])
    if milestones:
        lines.extend(f"- {m}" for m in milestones)
    if changelog_items:
        if milestones:
            lines.extend(["", "### Changelog Highlights"])
        for item in changelog_items:
            lines.append(f"- **{item['header']}**" + (f": {item['summary']}" if item["summary"] else ""))
    if not milestones and not changelog_items:
        lines.extend([f"- `{c}`" for c in commits[:15]] if commits else ["- *(No git commits, changelog entries, or plan milestones found)*"])
    if commits and (milestones or changelog_items):
        lines.extend(["", "### Commits Included"] + [f"- `{c}`" for c in commits[:12]])
    if diff_stat:
        stat_lines = diff_stat.splitlines()
        preview = stat_lines[:15] + ([f"... (+{len(stat_lines) - 15} more lines)"] if len(stat_lines) > 15 else [])
        lines.extend(["", "### Files Changed", "```text", *preview, "```"])
    verifs = [it["verify"] for it in changelog_items if it["verify"]]
    if verifs:
        lines.extend(["", "### Verification"] + [f"- {v}" for v in verifs[:5]])
    return "\n".join(lines).strip() + "\n"


def build_pr_description(
    root: Path,
    *,
    base: str | None = None,
    plan: str | None = None,
    target_log: str = "CHANGELOG.md",
    recent: int = 5,
) -> dict[str, Any]:
    """Build structured PR description metadata and formatted Markdown."""
    branch = _run_git(root, "branch", "--show-current") or "HEAD"
    base_ref = _resolve_base_ref(root, base)
    rev_range = f"{base_ref}..HEAD" if base_ref and base_ref != branch else "-n 10"
    commits = [ln for ln in _run_git(root, "log", rev_range, "--oneline").splitlines() if ln.strip()]
    diff_stat = _run_git(root, "diff", "--stat", f"{base_ref}...HEAD") if base_ref and base_ref != branch else ""
    plan_title, milestones = _load_plan_milestones(root, plan)
    changelog_items = _collect_changelog_items(root, target_log, max(1, recent))
    markdown = _format_pr_markdown(branch, base_ref, commits, diff_stat, plan_title, milestones, changelog_items)
    return {
        "branch": branch, "base": base_ref, "commits": commits,
        "milestones": milestones, "changelog": changelog_items, "markdown": markdown,
    }


def cmd_changelog_pr_description(args: argparse.Namespace) -> int:
    """CLI handler for ``diagnose.py changelog pr-description``."""
    root = Path(args.path or ".").resolve()
    payload = build_pr_description(
        root,
        base=getattr(args, "base", None),
        plan=getattr(args, "plan", None),
        target_log=getattr(args, "target_log", "CHANGELOG.md") or "CHANGELOG.md",
        recent=getattr(args, "recent", 5),
    )
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
    else:
        print(payload["markdown"], end="")
    return 0
