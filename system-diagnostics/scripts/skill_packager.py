#!/usr/bin/env python3
"""Temp-staged standalone skill bundler compliant with /skill-creator.

Stages a registered skill into a temporary directory, materializes any thin SSOT
delegating shims with their authoritative implementations from system-diagnostics/scripts/,
strips dev-only test/eval artifacts, and invokes skill-creator/scripts/package_skill.py
(or a built-in zip fallback when skill-creator is not installed locally).
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
SKILLS_ROOT = SCRIPTS_DIR.parent.parent

SSOT_BUNDLE_MAP: dict[str, tuple[str, ...]] = {
    "frontier-architect": (
        "cdp_inspect.py",
        "cdp_transport.py",
        "audit_layout.js",
        "docker_audit.py",
    ),
    "refactor-monolith": (
        "css_inspector.py",
        "surface_scanners.py",
    ),
}

DEV_EXCLUDE_NAMES: frozenset[str] = frozenset({
    "tests", "evals", "__pycache__", "node_modules",
    ".diagnostics", ".frontier", ".refactor", ".coverage", ".DS_Store",
})


def _ignore_dev_files(_dir: str, names: list[str]) -> set[str]:
    """Filter out dev-only test/eval directories and bytecode when staging."""
    return {
        n for n in names
        if n in DEV_EXCLUDE_NAMES or n.endswith((".pyc", ".pyo", ".swp", ".tmp"))
    }


def stage_standalone_skill(skill_dir: Path, staging_root: Path, ssot_scripts_dir: Path | None = None) -> Path:
    """Copy skill_dir into staging_root/<name> and replace SSOT shims with full scripts."""
    ssot_dir = ssot_scripts_dir or SCRIPTS_DIR
    dest = staging_root / skill_dir.name
    shutil.copytree(skill_dir, dest, ignore=_ignore_dev_files)

    bundled_files = SSOT_BUNDLE_MAP.get(skill_dir.name, ())
    if bundled_files:
        dest_scripts = dest / "scripts"
        dest_scripts.mkdir(parents=True, exist_ok=True)
        for fname in bundled_files:
            src_file = ssot_dir / fname
            if not src_file.is_file():
                raise FileNotFoundError(f"Missing SSOT script required for bundling: {src_file}")
            shutil.copy2(src_file, dest_scripts / fname)
    return dest


def _find_skill_creator_packager(skills_root: Path) -> Path | None:
    """Locate skill-creator/scripts/package_skill.py if available."""
    candidates = [
        skills_root / "skill-creator" / "scripts" / "package_skill.py",
        Path.home() / ".gemini" / "config" / "skills" / "skill-creator" / "scripts" / "package_skill.py",
    ]
    for c in candidates:
        if c.is_file():
            return c.resolve()
    return None


def _fallback_zip_skill(staged_dir: Path, out_dir: Path) -> Path:
    """Create a .skill zip archive with identical layout to package_skill.py."""
    skill_md = staged_dir / "SKILL.md"
    if not skill_md.is_file():
        raise FileNotFoundError(f"SKILL.md not found in {staged_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    archive_path = out_dir / f"{staged_dir.name}.skill"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in sorted(staged_dir.rglob("*")):
            if fp.is_file():
                zf.write(fp, fp.relative_to(staged_dir.parent))
    return archive_path


def package_single_skill(skill_dir: Path, out_dir: Path, skills_root: Path | None = None) -> Path | None:
    """Stage and package a single skill into out_dir/<skill_name>.skill."""
    root = skills_root or SKILLS_ROOT
    if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").is_file():
        print(f"[package-skill] Error: Invalid skill directory: {skill_dir}", file=sys.stderr)
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    packager = _find_skill_creator_packager(root)
    with tempfile.TemporaryDirectory(prefix="agy_stage_") as tmp:
        staged = stage_standalone_skill(skill_dir, Path(tmp))
        if packager:
            proc = subprocess.run(
                [sys.executable, str(packager), str(staged), str(out_dir)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if proc.stdout:
                print(proc.stdout.strip())
            if proc.returncode != 0:
                if proc.stderr:
                    print(proc.stderr.strip(), file=sys.stderr)
                return None
            out_file = out_dir / f"{skill_dir.name}.skill"
            return out_file if out_file.is_file() else None
        out_file = _fallback_zip_skill(staged, out_dir)
        print(f"[package-skill] Packaged standalone skill: {out_file}")
        return out_file


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the package-skill subcommand on diagnose.py."""
    p = subparsers.add_parser(
        "package-skill",
        help="Temp-stage and package standalone .skill archive(s) with SSOT scripts materialized",
    )
    p.add_argument(
        "skill",
        nargs="?",
        default="all",
        help="Skill name, directory path, or 'all' (default: all registered skills)",
    )
    p.add_argument("--out", default=None, help="Output directory for .skill archive(s) (default: ./dist)")


def cmd_package_skill(args: argparse.Namespace) -> int:
    """CLI handler for diagnose.py package-skill."""
    out_dir = Path(args.out).resolve() if getattr(args, "out", None) else (Path.cwd() / "dist").resolve()
    target = getattr(args, "skill", "all") or "all"

    if target.lower() == "all":
        names = ("system-diagnostics", "app-debugger", "frontier-architect", "refactor-monolith")
        targets = [SKILLS_ROOT / n for n in names if (SKILLS_ROOT / n / "SKILL.md").is_file()]
    else:
        cand = Path(target)
        if not cand.is_dir():
            cand = SKILLS_ROOT / target
        targets = [cand.resolve()]

    if not targets:
        print(f"[package-skill] Error: No matching skills found for '{target}'.", file=sys.stderr)
        return 2

    for tdir in targets:
        built = package_single_skill(tdir, out_dir)
        if not built:
            return 1
    return 0
