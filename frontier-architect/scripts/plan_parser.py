#!/usr/bin/env python3
"""Markdown parser and AST-like checklist patcher for Frontier Architect plans.

Parses human-readable markdown plans (.plans/, .TODO/, docs/plans/) into structured
milestone representations, scenario matrices, and verification commands.
"""

from pathlib import Path
from typing import Any
import re

M_REGEX = re.compile(r"^(#{2,4})\s+\*{0,2}(?:Milestone|Phase|Step)\s+(\d+)\*{0,2}[:\s-]*(.*)$", re.IGNORECASE)
TASK_REGEX = re.compile(r"^(\s*[-*]\s*\[)([ xX])(\]\s*(.*))$")
TASK_UNCHECKED_REGEX = re.compile(r"^(\s*[-*]\s*\[)[ ](\]\s*.*)$")
BULLET_TASK_REGEX = re.compile(r"^(\s*[-*]\s+)(?!\[[ xX]\])(.*)$")
CHILD_PLAN_REGEX = re.compile(
    r"^\s*[-*]?\s*\*{0,2}Child\s+Plan\*{0,2}:\s*(?:\[[^\]]*\]\(([^)\s]+\.md)\)|`?([^`\s]+\.md)`?)",
    re.IGNORECASE,
)
VERIFIER_PREFIXES = (
    "python", "pytest", "npm", "cargo", "go test", "unittest",
    "node", "deno", "bun", "mvn", "gradle", "flutter", "dotnet", ".venv",
)


def _is_section_boundary(line: str) -> bool:
    """Check if line is a non-milestone section boundary that ends milestone tasks."""
    if M_REGEX.match(line):
        return False
    if re.match(r"^#{1,3}\s+", line):
        return not line.lower().lstrip("#").strip().startswith("scenario")
    return False


def slugify(text: str) -> str:
    """Convert arbitrary title into safe filesystem slug."""
    clean = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[-\s]+", "_", clean).strip("_") or "unnamed_plan"


def discover_plans(root: Path) -> list[Path]:
    """Discover candidate architectural markdown plans in root sorted by mtime."""
    candidates: list[Path] = []
    search_dirs = [root / d for d in (".plans", ".TODO", "docs/plans", "plans")]
    for sub in root.iterdir():
        if sub.is_dir() and not sub.name.startswith(".") and sub.name not in ("node_modules", "tests", "evals"):
            search_dirs.extend([sub / ".plans", sub / ".TODO", sub / "plans"])

    for dir_path in search_dirs:
        if dir_path.is_dir():
            candidates.extend(dir_path.glob("*.md"))
    for p in root.glob("*plan*.md"):
        candidates.append(p)

    seen: set[Path] = set()
    unique: list[Path] = []
    for p in sorted(candidates, key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=True):
        resolved = p.resolve()
        if resolved not in seen and p.is_file():
            seen.add(resolved)
            unique.append(p)
    return unique


def parse_plan_markdown(content: str) -> dict[str, Any]:
    """Parse title, milestones, tasks, and verification commands from markdown."""
    lines = content.splitlines()
    title = "Architectural Implementation Plan"
    for line in lines:
        if line.startswith("# "):
            title = line[2:].strip()
            break

    milestones: list[dict[str, Any]] = []
    current_m: dict[str, Any] | None = None

    for idx, line in enumerate(lines):
        m_match = M_REGEX.match(line)
        if m_match:
            if current_m:
                _finalize_milestone(current_m)
                milestones.append(current_m)
            current_m = {
                "index": int(m_match.group(2)),
                "title": m_match.group(3).strip(),
                "raw_heading": line,
                "line_index": idx,
                "tasks": [],
                "child_plan": None,
                "is_complete": False,
            }
            continue

        if current_m:
            cp_match = CHILD_PLAN_REGEX.match(line)
            if cp_match:
                current_m["child_plan"] = (cp_match.group(1) or cp_match.group(2)).strip()
                continue
            t_match = TASK_REGEX.match(line)
            b_match = BULLET_TASK_REGEX.match(line) if not t_match else None
            if t_match:
                current_m["tasks"].append({
                    "text": t_match.group(4).strip(),
                    "checked": t_match.group(2).lower() == "x",
                    "has_checkbox": True,
                    "line_index": idx,
                })
            elif b_match and not line.strip().startswith(("#", "```", "---", "***")):
                # Fallback: treat plain list items under a milestone as unchecked tasks
                current_m["tasks"].append({
                    "text": b_match.group(2).strip(),
                    "checked": False,
                    "has_checkbox": False,
                    "line_index": idx,
                })
            elif _is_section_boundary(line):
                _finalize_milestone(current_m)
                milestones.append(current_m)
                current_m = None

    if current_m:
        _finalize_milestone(current_m)
        milestones.append(current_m)

    verifiers = _extract_verifiers(content)
    return {
        "title": title,
        "milestones": milestones,
        "verification_commands": verifiers,
        "total_milestones": len(milestones),
    }


def _finalize_milestone(m: dict[str, Any]) -> None:
    """Calculate milestone completion state."""
    has_explicit_unchecked = any(t.get("has_checkbox") and not t["checked"] for t in m["tasks"])
    marked_completed = "(completed)" in m.get("title", "").lower()
    if marked_completed and not has_explicit_unchecked:
        for t in m["tasks"]:
            t["checked"] = True
        m["is_complete"] = True
        return
    m["is_complete"] = len(m["tasks"]) > 0 and all(t["checked"] for t in m["tasks"])


def _is_valid_verifier(line: str) -> bool:
    """Check if a stripped command string is a concrete runnable verifier."""
    if not line or line.startswith("#") or " " not in line:
        return False
    if "plan_engine.py" in line or ("<" in line and ">" in line):
        return False
    return any(line.startswith(p) for p in VERIFIER_PREFIXES)


def _extract_verifiers(content: str) -> list[str]:
    """Extract runnable shell commands from fenced code blocks and Markdown tables/backticks."""
    verifiers: list[str] = []

    def _add(cmd: str) -> None:
        line = cmd.strip()
        if _is_valid_verifier(line) and line not in verifiers:
            verifiers.append(line)

    # 1. Fenced code blocks (highest priority)
    blocks = re.findall(r"^```[^\r\n]*\r?\n(.*?)\r?\n^```", content, re.MULTILINE | re.DOTALL)
    for block in blocks:
        for raw_line in block.splitlines():
            _add(raw_line)

    # 2. Markdown table rows (e.g., Scenario Combinations Matrix)
    for row in re.findall(r"^\s*\|[^\r\n]+\|", content, re.MULTILINE):
        for inline_cmd in re.findall(r"`([^`\r\n]+)`", row):
            _add(inline_cmd)

    # 3. Remaining inline backtick commands
    for inline_cmd in re.findall(r"`([^`\r\n]+)`", content):
        _add(inline_cmd)

    return verifiers


def patch_milestone_checkboxes(plan_path: Path, milestone_index: int) -> int:
    """In-place patch unchecked checkboxes to [x] for a given milestone."""
    raw = plan_path.read_text(encoding="utf-8")
    lines = raw.splitlines(keepends=True)

    in_target = False
    patched_count = 0
    new_lines = []

    for line in lines:
        m_match = M_REGEX.match(line)
        if m_match:
            idx = int(m_match.group(2))
            in_target = (idx == milestone_index)
        elif in_target and _is_section_boundary(line):
            in_target = False

        if in_target:
            if TASK_UNCHECKED_REGEX.match(line):
                line = TASK_UNCHECKED_REGEX.sub(r"\g<1>x\g<2>", line)
                patched_count += 1
            elif BULLET_TASK_REGEX.match(line) and not line.strip().startswith(("#", "```", "---", "***")):
                line = BULLET_TASK_REGEX.sub(r"\g<1>[x] \g<2>", line)
                patched_count += 1
        new_lines.append(line)

    plan_path.write_text("".join(new_lines), encoding="utf-8")
    return patched_count
