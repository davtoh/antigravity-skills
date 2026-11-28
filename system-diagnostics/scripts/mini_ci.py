#!/usr/bin/env python3
"""Project-agnostic, stdlib-only local Mini-CI runner (`diagnose.py ci`)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping

DEFAULT_DOCKER_IMAGE = "python:3.12-slim"
PY_TOKEN = "__MINI_CI_PYTHON__"
DEFAULT_EXCLUDES = frozenset({
    ".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "node_modules", ".tox", "dist", "build", ".eggs", ".frontier", ".diagnostics",
})
_WIN_DRIVE_RE = re.compile(r"^([A-Za-z]):[\\/]?(.*)$")


def load_config(root: Path) -> dict[str, Any]:
    """Load optional `.diagnostics/mini_ci.json` override config."""
    cfg_path = root / ".diagnostics" / "mini_ci.json"
    if not cfg_path.is_file():
        return {}
    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{cfg_path} must contain a JSON object.")
    return raw


def discover_skill_test_dirs(root: Path) -> list[str]:
    """Return sorted relative POSIX paths of `*/tests` dirs containing `test_*.py`."""
    if not root.is_dir():
        return []
    found: list[str] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        if not entry.is_dir() or entry.name.startswith(".") or entry.name in DEFAULT_EXCLUDES:
            continue
        tests_dir = entry / "tests"
        if tests_dir.is_dir() and any(tests_dir.glob("test_*.py")):
            found.append(f"{entry.name}/tests")
    return found


def detect_layout(root: Path) -> str:
    """Auto-detect repository layout: `skills_monorepo` or `python_repo`."""
    if (root / ".github" / "scripts" / "validate_skills.py").is_file():
        return "skills_monorepo"
    return "skills_monorepo" if len(discover_skill_test_dirs(root)) >= 2 else "python_repo"


def windows_to_wsl_path(path: str | Path) -> str:
    """Convert a Windows drive path (e.g. `C:\\repo`) to `/mnt/c/repo`."""
    text = str(path)
    match = _WIN_DRIVE_RE.match(text)
    if not match:
        return text.replace("\\", "/")
    drive, rest = match.group(1).lower(), match.group(2).replace("\\", "/").lstrip("/")
    return f"/mnt/{drive}/{rest}" if rest else f"/mnt/{drive}"


def select_linux_backend(preferred: str = "auto", *, is_windows: bool | None = None, which_fn: Any = shutil.which) -> str:
    """Select Linux execution backend (`wsl` or `docker`)."""
    if preferred in ("wsl", "docker"):
        return preferred
    if preferred != "auto":
        raise ValueError(f"Unsupported Linux backend: {preferred}")
    on_win = (os.name == "nt") if is_windows is None else is_windows
    if on_win and (which_fn("wsl.exe") or which_fn("wsl")):
        return "wsl"
    if which_fn("docker"):
        return "docker"
    raise RuntimeError("No Linux backend available (install WSL or Docker).")


def create_clean_snapshot(root: Path, dest: Path | None = None, exclude_dirs: Iterable[str] | None = None) -> Path:
    """Copy `root` into an isolated temp snapshot without VCS/venv/cache dirs."""
    excludes = set(DEFAULT_EXCLUDES) | set(exclude_dirs or ())
    target = dest if dest is not None else Path(tempfile.mkdtemp(prefix="mini_ci_snap_"))
    shutil.copytree(root, target, ignore=lambda _c, names: {n for n in names if n in excludes}, symlinks=True, dirs_exist_ok=True)
    return target


def build_fast_env(base_env: Mapping[str, str] | None = None, config: Mapping[str, Any] | None = None, simulate_ci_chrome: bool = False) -> dict[str, str]:
    """Construct clean host CI environment without mutating caller env."""
    env = dict(base_env if base_env is not None else os.environ)
    env.update({"CI": "true", "MPLBACKEND": "Agg", "QT_QPA_PLATFORM": "offscreen", "PYTHONUTF8": "1"})
    if simulate_ci_chrome:
        env.update({"CI_SIMULATE_CHROME": "1", "CHROME_NO_SANDBOX": "1", "HEADLESS": "1"})
    for key, val in (config or {}).get("env", {}).items():
        env[str(key)] = str(val)
    return env


def _target_to_step(root: Path, python_bin: str, target: str, use_pytest: bool) -> list[str]:
    if use_pytest:
        return [python_bin, "-m", "pytest", target]
    norm = target.replace("\\", "/")
    if (root / norm).is_dir():
        return [python_bin, "-m", "unittest", "discover", "-s", norm, "-p", "test_*.py", "-v"]
    if norm.endswith(".py"):
        return [python_bin, "-m", "unittest", "discover", "-s", Path(norm).parent.as_posix() or ".", "-p", Path(norm).name, "-v"]
    return [python_bin, "-m", "unittest", target, "-v"]


def _parse_config_steps(raw_steps: list[Any], python_bin: str) -> list[list[str]]:
    steps: list[list[str]] = []
    for item in raw_steps:
        tokens = [str(t) for t in item] if isinstance(item, list) else shlex.split(str(item))
        steps.append([python_bin if t == "{python}" else t for t in tokens])
    return steps


def build_ci_steps(root: Path, python_bin: str, *, config: Mapping[str, Any] | None = None, tests: list[str] | None = None, skip_lint: bool = False, which_fn: Any = shutil.which) -> list[list[str]]:
    """Build ordered CI command argv lists for `root`."""
    use_pytest = ((root / "pytest.ini").is_file() or (root / "conftest.py").is_file()) and bool(which_fn("pytest"))
    if tests:
        return [_target_to_step(root, python_bin, t, use_pytest) for t in tests]
    if (config or {}).get("steps"):
        return _parse_config_steps(config["steps"], python_bin)
    if detect_layout(root) == "skills_monorepo":
        steps = [[python_bin, ".github/scripts/validate_skills.py"]] if (root / ".github" / "scripts" / "validate_skills.py").is_file() else []
        return steps + [[python_bin, "-m", "unittest", "discover", "-s", d, "-p", "test_*.py"] for d in discover_skill_test_dirs(root)]
    steps = [["ruff", "check", "."]] if (not skip_lint and which_fn("ruff")) else []
    if use_pytest:
        return steps + [[python_bin, "-m", "pytest"]]
    start_dir = "tests" if (root / "tests").is_dir() else "."
    return steps + [[python_bin, "-m", "unittest", "discover", "-s", start_dir, "-p", "test_*.py"]]


def _render_shell_step(step: list[str], py_var: str = '"$PY_BIN"') -> str:
    return " ".join(py_var if tok == PY_TOKEN else shlex.quote(tok) for tok in step)


def build_wsl_script(wsl_workdir: str, steps: list[list[str]], *, config: Mapping[str, Any] | None = None, has_requirements: bool = False) -> str:
    """Build an isolated-HOME bash script streamed to `wsl ... bash -s`."""
    cfg = config or {}
    pip_pkgs = [str(p) for p in cfg.get("pip_packages", [])]
    lines = [
        "set -euo pipefail", 'CLEAN_HOME="$(mktemp -d)"', 'trap \'rm -rf "$CLEAN_HOME"\' EXIT',
        'export HOME="$CLEAN_HOME" XDG_CONFIG_HOME="$CLEAN_HOME/.config" XDG_CACHE_HOME="$CLEAN_HOME/.cache"',
        "export CI=true MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen PYTHONUTF8=1",
        *[f"export {k}={shlex.quote(str(v))}" for k, v in cfg.get("env", {}).items()],
        f"cd {shlex.quote(wsl_workdir)}", 'PY_BIN="python3"',
    ]
    if has_requirements or pip_pkgs:
        extra = " ".join(shlex.quote(p) for p in pip_pkgs)
        lines.extend([
            'REQ_HASH="$({ [ -f requirements.txt ] && cat requirements.txt; printf "%s" ' + shlex.quote(extra) + '; } | sha256sum | cut -c1-12)"',
            'VENV_DIR="/tmp/mini_ci_venvs/$REQ_HASH"',
            'if [ ! -x "$VENV_DIR/bin/python" ]; then python3 -m venv "$VENV_DIR"; fi',
            'PY_BIN="$VENV_DIR/bin/python"',
            '[ -f requirements.txt ] && "$PY_BIN" -m pip install -q -r requirements.txt || true',
            *([f'"$PY_BIN" -m pip install -q {extra}'] if pip_pkgs else []),
        ])
    lines.extend(_render_shell_step(s) for s in steps)
    return "\n".join(lines) + "\n"


def build_dockerfile(docker_image: str = DEFAULT_DOCKER_IMAGE, *, config: Mapping[str, Any] | None = None, has_requirements: bool = False) -> str:
    """Generate a minimal cached Dockerfile for `--linux --backend docker`."""
    cfg = config or {}
    apt_pkgs = [str(p) for p in cfg.get("apt_packages", [])]
    pip_pkgs = [str(p) for p in cfg.get("pip_packages", [])]
    lines = [f"FROM {docker_image}"]
    if apt_pkgs:
        joined = " ".join(shlex.quote(p) for p in apt_pkgs)
        lines.append(f"RUN apt-get update && apt-get install -y --no-install-recommends {joined} && rm -rf /var/lib/apt/lists/*")
    lines.append("WORKDIR /workspace")
    if has_requirements:
        lines.extend(["COPY requirements.txt .", "RUN pip install --no-cache-dir -r requirements.txt"])
    if pip_pkgs:
        lines.append(f"RUN pip install --no-cache-dir {' '.join(shlex.quote(p) for p in pip_pkgs)}")
    return "\n".join(lines) + "\n"


def build_docker_run_command(host_root: Path, image: str, steps: list[list[str]], *, config: Mapping[str, Any] | None = None) -> list[str]:
    """Build `docker run --rm` argv with isolated `/tmp/mini_ci_home` HOME."""
    cmd = [
        "docker", "run", "--rm", "-v", f"{host_root}:/workspace", "-w", "/workspace",
        "-e", "HOME=/tmp/mini_ci_home", "-e", "CI=true", "-e", "MPLBACKEND=Agg", "-e", "QT_QPA_PLATFORM=offscreen",
    ]
    for key, val in (config or {}).get("env", {}).items():
        cmd.extend(["-e", f"{key}={val}"])
    rendered = " && ".join(_render_shell_step(s, py_var="python3") for s in steps)
    shell_body = f"mkdir -p /tmp/mini_ci_home && {rendered}" if rendered else "mkdir -p /tmp/mini_ci_home"
    return cmd + [image, "bash", "-c", shell_body]


def _resolve_host_python(root: Path) -> str:
    try:
        import diagnose
        return diagnose.find_virtualenv_python(root)
    except Exception:
        return sys.executable


def _run_fast(work_root: Path, config: dict[str, Any], args: argparse.Namespace) -> int:
    py_bin = _resolve_host_python(work_root)
    steps = build_ci_steps(work_root, py_bin, config=config, tests=args.tests, skip_lint=args.skip_lint)
    env = build_fast_env(config=config, simulate_ci_chrome=getattr(args, "simulate_ci_chrome", False))
    print(f"=== Mini-CI [fast] ({detect_layout(work_root)} @ {work_root}) ===")
    for idx, step in enumerate(steps, 1):
        print(f"  [{idx}/{len(steps)}] {' '.join(step)}")
        if not args.dry_run:
            res = subprocess.run(step, cwd=str(work_root), env=env)
            if res.returncode != 0:
                return res.returncode
    return 0


def _run_docker(work_root: Path, config: dict[str, Any], steps: list[list[str]], args: argparse.Namespace, has_req: bool) -> int:
    base_image = args.docker_image or config.get("docker_image") or DEFAULT_DOCKER_IMAGE
    need_build = has_req or bool(config.get("apt_packages")) or bool(config.get("pip_packages"))
    dockerfile = build_dockerfile(base_image, config=config, has_requirements=has_req)
    tag = f"mini-ci-{hashlib.sha256(dockerfile.encode()).hexdigest()[:12]}" if need_build else base_image
    run_cmd = build_docker_run_command(work_root, tag, steps, config=config)
    print(f"=== Mini-CI [linux:docker] ({tag}) ===")
    if args.dry_run:
        if need_build:
            print(f"# docker build -t {tag} -f - .\n{dockerfile}")
        print(" ".join(shlex.quote(c) for c in run_cmd))
        return 0
    if need_build:
        res = subprocess.run(["docker", "build", "-t", tag, "-f", "-", str(work_root)], input=dockerfile, text=True)
        if res.returncode != 0:
            return res.returncode
    return subprocess.run(run_cmd).returncode


def _run_linux(work_root: Path, config: dict[str, Any], args: argparse.Namespace) -> int:
    backend = select_linux_backend(args.backend)
    steps = build_ci_steps(work_root, PY_TOKEN, config=config, tests=args.tests, skip_lint=args.skip_lint)
    has_req = (work_root / "requirements.txt").is_file()
    if backend == "docker":
        return _run_docker(work_root, config, steps, args, has_req)
    wsl_path = windows_to_wsl_path(work_root)
    script = build_wsl_script(wsl_path, steps, config=config, has_requirements=has_req)
    distro = args.wsl_distro or config.get("wsl_distro")
    cmd = ["wsl.exe", *(["-d", distro] if distro else []), "--", "bash", "-s"]
    print(f"=== Mini-CI [linux:wsl] ({wsl_path}) ===")
    if args.dry_run:
        print(script, end="")
        return 0
    return subprocess.run(cmd, input=script, text=True, encoding="utf-8").returncode


def register_parser(sub: Any) -> None:
    """Register `diagnose.py ci` subcommand."""
    p = sub.add_parser("ci", help="Project-agnostic local Mini-CI runner (host --fast or --linux WSL/Docker)")
    p.add_argument("--path", default=".", help="Target repository root (default: .)")
    p.add_argument("--fast", action="store_true", help="Run on host virtualenv Python (default)")
    p.add_argument("--linux", action="store_true", help="Run inside isolated Linux backend (WSL or Docker)")
    p.add_argument("--backend", choices=("auto", "wsl", "docker"), default="auto", help="Linux backend (default: auto)")
    p.add_argument("--wsl-distro", dest="wsl_distro", default=None, help="Specific WSL distro name")
    p.add_argument("--docker-image", dest="docker_image", default=None, help=f"Docker image (default: {DEFAULT_DOCKER_IMAGE})")
    p.add_argument("--tests", nargs="+", default=None, help="Targeted test files/dirs to run")
    p.add_argument("--skip-lint", dest="skip_lint", action="store_true", help="Skip ruff lint step")
    p.add_argument("--clean-snapshot", dest="clean_snapshot", action="store_true", help="Run against an isolated temp copy")
    p.add_argument("--simulate-ci-chrome", dest="simulate_ci_chrome", action="store_true", help="Set headless CI Chrome env vars")
    p.add_argument("--dry-run", dest="dry_run", action="store_true", help="Print planned commands/script without executing")


def cmd_ci(args: argparse.Namespace) -> int:
    """CLI entrypoint for `diagnose.py ci`."""
    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"[diagnose ci] Error: Directory not found: {root}", file=sys.stderr)
        return 2
    try:
        config = load_config(root)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"[diagnose ci] Error: Invalid .diagnostics/mini_ci.json: {exc}", file=sys.stderr)
        return 2
    snap_dir: Path | None = None
    try:
        work_root = create_clean_snapshot(root, exclude_dirs=config.get("exclude_dirs")) if args.clean_snapshot else root
        snap_dir = work_root if args.clean_snapshot else None
        return _run_linux(work_root, config, args) if args.linux else _run_fast(work_root, config, args)
    except (ValueError, RuntimeError) as exc:
        print(f"[diagnose ci] Error: {exc}", file=sys.stderr)
        return 2
    finally:
        if snap_dir and snap_dir.exists():
            shutil.rmtree(snap_dir, ignore_errors=True)
