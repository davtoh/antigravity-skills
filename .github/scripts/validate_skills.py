#!/usr/bin/env python3
"""CI validation script for Antigravity skills: integrity, syntax, evals, and CLI smoke checks."""

from __future__ import annotations

import json
import py_compile
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ALLOWED_FRONTMATTER_KEYS = {
    "name",
    "description",
    "license",
    "allowed-tools",
    "metadata",
    "compatibility",
}


def validate_skill(skill_path: Path) -> tuple[bool, str]:
    """Validate SKILL.md frontmatter (name, description, allowed keys, length limits)."""
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return False, "SKILL.md not found"

    content = skill_md.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not content.startswith("---"):
        return False, "No YAML frontmatter found"

    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return False, "Invalid frontmatter format"

    try:
        frontmatter = yaml.safe_load(match.group(1))
        if not isinstance(frontmatter, dict):
            return False, "Frontmatter must be a YAML dictionary"
    except yaml.YAMLError as exc:
        return False, f"Invalid YAML in frontmatter: {exc}"

    unexpected = set(frontmatter.keys()) - ALLOWED_FRONTMATTER_KEYS
    if unexpected:
        return False, f"Unexpected key(s) in SKILL.md frontmatter: {', '.join(sorted(unexpected))}"

    for req in ("name", "description"):
        if req not in frontmatter:
            return False, f"Missing '{req}' in frontmatter"

    name = frontmatter.get("name", "")
    if not isinstance(name, str):
        return False, f"Name must be a string, got {type(name).__name__}"
    name = name.strip()
    if name:
        if not re.match(r"^[a-z0-9-]+$", name):
            return False, f"Name '{name}' should be kebab-case"
        if name.startswith("-") or name.endswith("-") or "--" in name:
            return False, f"Name '{name}' cannot start/end with hyphen or contain '--'"
        if len(name) > 64:
            return False, f"Name is too long ({len(name)} > 64)"

    desc = frontmatter.get("description", "")
    if not isinstance(desc, str):
        return False, f"Description must be a string, got {type(desc).__name__}"
    desc = desc.strip()
    if "<" in desc or ">" in desc:
        return False, "Description cannot contain angle brackets (< or >)"
    if len(desc) > 1024:
        return False, f"Description is too long ({len(desc)} > 1024)"

    compat = frontmatter.get("compatibility", "")
    if compat:
        if not isinstance(compat, str):
            return False, f"Compatibility must be a string, got {type(compat).__name__}"
        if len(compat) > 500:
            return False, f"Compatibility is too long ({len(compat)} > 500)"

    return True, "Skill is valid!"

REQUIRED_EVAL_SKILLS = {
    "system-diagnostics",
    "app-debugger",
    "frontier-architect",
    "refactor-monolith",
}

CLI_SMOKE_ENTRYPOINTS = [
    "system-diagnostics/scripts/diagnose.py",
    "app-debugger/scripts/run_diagnose.py",
    "frontier-architect/scripts/plan_engine.py",
    "refactor-monolith/scripts/contract_snapshot.py",
]


def discover_skills(root: Path) -> list[Path]:
    """Return sorted list of skill directories containing SKILL.md."""
    skills = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith(".") or entry.name.endswith("-workspace"):
            continue
        if (entry / "SKILL.md").is_file():
            skills.append(entry)
    return skills


def check_frontmatter(skills: list[Path]) -> list[str]:
    """Validate SKILL.md frontmatter for every discovered skill."""
    errors = []
    for skill in skills:
        ok, msg = validate_skill(skill)
        if not ok:
            errors.append(f"[frontmatter] {skill.name}: {msg}")
    return errors


def check_python_syntax(skills: list[Path]) -> list[str]:
    """Compile all .py files across all skills to catch syntax errors."""
    errors = []
    for skill in skills:
        for py_file in sorted(skill.rglob("*.py")):
            if "__pycache__" in py_file.parts:
                continue
            try:
                py_compile.compile(str(py_file), doraise=True)
            except py_compile.PyCompileError as exc:
                rel = py_file.relative_to(REPO_ROOT)
                errors.append(f"[syntax] {rel}: {exc.msg}")
    return errors


def _validate_evals_json(skill_name: str, path: Path) -> list[str]:
    """Validate structure and uniqueness of evals/evals.json."""
    errors = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"[evals] {skill_name}/evals/evals.json: invalid JSON ({exc})"]

    if not isinstance(data, dict):
        return [f"[evals] {skill_name}/evals/evals.json: root must be a JSON object"]

    declared_name = data.get("skill_name")
    if declared_name and declared_name != skill_name:
        errors.append(
            f"[evals] {skill_name}/evals/evals.json: skill_name '{declared_name}' != '{skill_name}'"
        )

    entries = data.get("evals")
    if not isinstance(entries, list) or not entries:
        return errors + [f"[evals] {skill_name}/evals/evals.json: 'evals' must be a non-empty list"]

    seen_ids: set[object] = set()
    for idx, item in enumerate(entries):
        if not isinstance(item, dict):
            errors.append(f"[evals] {skill_name}/evals/evals.json[{idx}]: entry must be an object")
            continue
        if "id" not in item:
            errors.append(f"[evals] {skill_name}/evals/evals.json[{idx}]: missing 'id'")
        else:
            item_id = item["id"]
            if item_id in seen_ids:
                errors.append(f"[evals] {skill_name}/evals/evals.json: duplicate id {item_id!r}")
            seen_ids.add(item_id)
        if not isinstance(item.get("prompt"), str) or not item["prompt"].strip():
            errors.append(f"[evals] {skill_name}/evals/evals.json[{idx}]: missing non-empty 'prompt'")
        has_expected = bool(item.get("expected_output")) or bool(item.get("expectations"))
        if not has_expected:
            errors.append(
                f"[evals] {skill_name}/evals/evals.json[{idx}]: needs 'expected_output' or 'expectations'"
            )
    return errors


def _validate_trigger_eval(skill_name: str, path: Path) -> list[str]:
    """Validate structure and polarity balance of evals/trigger_eval.json."""
    errors = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"[trigger_eval] {skill_name}/evals/trigger_eval.json: invalid JSON ({exc})"]

    if not isinstance(data, list) or not data:
        return [f"[trigger_eval] {skill_name}/evals/trigger_eval.json: must be a non-empty list"]

    pos = 0
    neg = 0
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            errors.append(f"[trigger_eval] {skill_name}[{idx}]: entry must be an object")
            continue
        if not isinstance(item.get("query"), str) or not item["query"].strip():
            errors.append(f"[trigger_eval] {skill_name}[{idx}]: missing non-empty 'query'")
        trigger = item.get("should_trigger")
        if not isinstance(trigger, bool):
            errors.append(f"[trigger_eval] {skill_name}[{idx}]: 'should_trigger' must be boolean")
        elif trigger:
            pos += 1
        else:
            neg += 1

    if pos == 0 or neg == 0:
        errors.append(
            f"[trigger_eval] {skill_name}: must include both true ({pos}) and false ({neg}) cases"
        )
    return errors


def check_evals(skills: list[Path]) -> list[str]:
    """Validate evals.json and trigger_eval.json across all skills."""
    errors = []
    for skill in skills:
        evals_dir = skill / "evals"
        evals_file = evals_dir / "evals.json"
        trigger_file = evals_dir / "trigger_eval.json"

        if skill.name in REQUIRED_EVAL_SKILLS:
            if not evals_file.is_file():
                errors.append(f"[evals] {skill.name}: missing required evals/evals.json")
            if not trigger_file.is_file():
                errors.append(f"[evals] {skill.name}: missing required evals/trigger_eval.json")

        if evals_file.is_file():
            errors.extend(_validate_evals_json(skill.name, evals_file))
        if trigger_file.is_file():
            errors.extend(_validate_trigger_eval(skill.name, trigger_file))
    return errors


def check_cli_smoke() -> list[str]:
    """Verify key CLI entrypoints start cleanly with --help."""
    errors = []
    for rel_path in CLI_SMOKE_ENTRYPOINTS:
        script = REPO_ROOT / rel_path
        if not script.is_file():
            errors.append(f"[cli-smoke] missing entrypoint: {rel_path}")
            continue
        res = subprocess.run(
            [sys.executable, str(script), "--help"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
        if res.returncode != 0:
            errors.append(f"[cli-smoke] {rel_path} --help exited {res.returncode}: {res.stderr.strip()}")
    return errors


def main() -> int:
    """Run all integrity, syntax, eval, and CLI smoke checks."""
    skills = discover_skills(REPO_ROOT)
    print(f"Discovered {len(skills)} skills: {', '.join(s.name for s in skills)}")

    errors: list[str] = []
    errors.extend(check_frontmatter(skills))
    errors.extend(check_python_syntax(skills))
    errors.extend(check_evals(skills))
    errors.extend(check_cli_smoke())

    if errors:
        print("\nValidation FAILED:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("All skill integrity, syntax, eval, and CLI smoke checks PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
