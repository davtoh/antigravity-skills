#!/usr/bin/env python3
"""Pluggable Extension Registry and Dynamic Probe Runner for system-diagnostics.

Discovers, executes, scaffolds, and promotes reusable diagnostic probes across
global skill directories and workspace-level registries.
Zero external dependencies; standard library Python 3.10+ only.
Cross-platform: Windows, macOS, Linux.
"""

import ast
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
DEFAULT_GLOBAL_PROBES = SCRIPTS_DIR.parent / "probes"

@dataclass
class ProbeInfo:
    """Metadata descriptor for a discovered diagnostic probe."""
    name: str
    description: str
    path: str
    scope: str  # 'builtin', 'workspace', or 'custom'

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def get_probe_search_dirs(workspace_root: Path | None = None) -> list[tuple[Path, str]]:
    """Return prioritized directories searched for probe modules."""
    dirs: list[tuple[Path, str]] = []

    # 1. Workspace local probes (.diagnostics/probes)
    root = (workspace_root or Path.cwd()).resolve()
    for candidate in [root, *root.parents[:3]]:
        ws_probe_dir = candidate / ".diagnostics" / "probes"
        if ws_probe_dir.is_dir():
            dirs.append((ws_probe_dir, "workspace"))
            break

    # 2. Skill bundled probes
    if DEFAULT_GLOBAL_PROBES.is_dir():
        dirs.append((DEFAULT_GLOBAL_PROBES, "builtin"))

    # 3. Global user configuration (~/.gemini/config/skills/system-diagnostics/probes)
    global_dir = Path.home() / ".gemini" / "config" / "skills" / "system-diagnostics" / "probes"
    if global_dir.is_dir() and global_dir != DEFAULT_GLOBAL_PROBES:
        dirs.append((global_dir, "global"))

    return dirs

def _extract_docstring(file_path: Path) -> str:
    """Safely extract module docstring using AST without executing code."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(content)
        doc = ast.get_docstring(tree)
        if doc:
            return doc.strip().split("\n")[0]
    except Exception:
        pass
    return "No description provided."

def list_probes(workspace_root: Path | None = None) -> list[ProbeInfo]:
    """Discover all available probes across search directories."""
    discovered: dict[str, ProbeInfo] = {}

    for directory, scope in get_probe_search_dirs(workspace_root):
        try:
            for item in directory.glob("*.py"):
                if item.name.startswith("__"):
                    continue
                name = item.stem
                if name not in discovered:
                    desc = _extract_docstring(item)
                    discovered[name] = ProbeInfo(
                        name=name,
                        description=desc,
                        path=str(item.resolve()),
                        scope=scope,
                    )
        except (OSError, PermissionError):
            continue

    return list(discovered.values())

def find_probe(name_or_path: str, workspace_root: Path | None = None) -> Path | None:
    """Find a probe by explicit path or registered name."""
    candidate = Path(name_or_path)
    if candidate.is_file():
        return candidate.resolve()

    clean_name = candidate.stem
    for probe_info in list_probes(workspace_root):
        if probe_info.name == clean_name:
            return Path(probe_info.path)
    return None

def run_probe(
    name_or_path: str,
    probe_args: list[str] | None = None,
    python_bin: str | None = None,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    """Execute a probe in an isolated subprocess and return structured telemetry."""
    probe_file = find_probe(name_or_path, workspace_root)
    if not probe_file:
        return {
            "status": "error",
            "probe": name_or_path,
            "summary": f"Probe '{name_or_path}' not found.",
            "details": {"searched_dirs": [str(d[0]) for d in get_probe_search_dirs(workspace_root)]},
            "latency_ms": 0.0,
        }

    py_exe = python_bin or sys.executable
    cmd = [py_exe, str(probe_file), *(probe_args or [])]

    start_time = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30.0,
        )
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "probe": probe_file.stem,
            "summary": f"Probe timed out after 30.0s.",
            "details": {"cmd": cmd},
            "latency_ms": 30000.0,
        }
    except Exception as err:
        return {
            "status": "error",
            "probe": probe_file.stem,
            "summary": f"Failed to execute probe: {err}",
            "details": {"exception": str(err)},
            "latency_ms": 0.0,
        }

    stdout_clean = proc.stdout.strip()
    result: dict[str, Any] = {
        "status": "ok" if proc.returncode == 0 else "error",
        "probe": probe_file.stem,
        "summary": "Probe completed successfully." if proc.returncode == 0 else "Probe exited with failure.",
        "details": {},
        "latency_ms": elapsed_ms,
        "exit_code": proc.returncode,
    }

    # Try parsing stdout as JSON from standard probe protocol
    parsed = False
    if stdout_clean:
        # Search backwards for a JSON block if probe printed logs first
        lines = stdout_clean.splitlines()
        for idx in range(len(lines)):
            chunk = "\n".join(lines[idx:])
            if chunk.startswith("{") and chunk.endswith("}"):
                try:
                    data = json.loads(chunk)
                    if isinstance(data, dict):
                        result["details"] = data.get("details", data)
                        result["status"] = data.get("status", result["status"])
                        result["summary"] = data.get("summary", result["summary"])
                        parsed = True
                        break
                except Exception:
                    pass

    if not parsed:
        result["details"] = {
            "stdout": stdout_clean,
            "stderr": proc.stderr.strip(),
        }

    return result

def scaffold_probe(name: str, domain: str = "general", target_dir: Path | None = None) -> Path:
    """Scaffold a new diagnostic probe module adhering to the standard protocol."""
    dest_dir = target_dir or (Path.cwd() / ".diagnostics" / "probes")
    dest_dir.mkdir(parents=True, exist_ok=True)

    clean_name = name.lower().replace("-", "_").replace(" ", "_")
    if not clean_name.endswith(".py"):
        clean_name += ".py"
    target_file = dest_dir / clean_name

    template = f'''#!/usr/bin/env python3
"""Diagnostic Probe: {clean_name[:-3]} ({domain}).

Standard Protocol Diagnostic Probe.
Returns structured JSON telemetry for system-diagnostics & app-debugger.
"""

import json
import sys
import time
from typing import Any

def probe(*args: str, **kwargs: Any) -> dict[str, Any]:
    """Execute domain inspection and return structured telemetry.

    Returns:
        dict with status ('ok', 'warning', 'error'), domain, summary, and details.
    """
    start = time.perf_counter()
    # TODO: Implement domain inspection logic (e.g. check hardware, DB, or network)
    status = "ok"
    summary = "Diagnostic probe completed."
    details: dict[str, Any] = {{"items": []}}

    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    return {{
        "status": status,
        "domain": "{domain}",
        "summary": summary,
        "details": details,
        "latency_ms": latency_ms,
    }}

def main() -> int:
    result = probe(*sys.argv[1:])
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") in ("ok", "warning") else 1

if __name__ == "__main__":
    sys.exit(main())
'''
    target_file.write_text(template.replace("\r\n", "\n"), encoding="utf-8")
    return target_file

def save_probe(
    source_path: str,
    name: str,
    scope: str = "global",
    workspace_root: Path | None = None,
) -> Path:
    """Promote a verified script (e.g. from scratch/) into the probe registry."""
    src = Path(source_path).resolve()
    if not src.is_file():
        raise FileNotFoundError(f"Source script not found: {source_path}")

    # Validate Python syntax
    content = src.read_text(encoding="utf-8", errors="replace")
    try:
        ast.parse(content)
    except SyntaxError as err:
        raise ValueError(f"Source script has invalid Python syntax: {err}") from err

    clean_name = name.lower().replace("-", "_").replace(" ", "_")
    if not clean_name.endswith(".py"):
        clean_name += ".py"

    if scope == "workspace":
        target_dir = (workspace_root or Path.cwd()).resolve() / ".diagnostics" / "probes"
    else:
        target_dir = DEFAULT_GLOBAL_PROBES

    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / clean_name

    # Write normalized LF content
    target_file.write_text(content.replace("\r\n", "\n"), encoding="utf-8")
    return target_file


def register_parser(subparsers: Any) -> Any:
    """Register 'probe' subparser and its subactions into diagnose.py CLI."""
    p_probe = subparsers.add_parser("probe", help="Dynamic & extensible diagnostic probes (hardware, DB, etc.)")
    probe_sub = p_probe.add_subparsers(dest="probe_action", help="Probe action to execute")

    p_plist = probe_sub.add_parser("list", help="List registered diagnostic probes")
    p_plist.add_argument("--path", default=None, help="Root directory (default: current directory)")
    p_plist.add_argument("--json", action="store_true", help="Output JSON format")

    p_prun = probe_sub.add_parser("run", help="Run a diagnostic probe by name or file path")
    p_prun.add_argument("name", help="Probe name or file path")
    p_prun.add_argument("probe_args", nargs="*", default=[], help="Arguments passed to the probe")
    p_prun.add_argument("--path", default=None, help="Root directory (default: current directory)")
    p_prun.add_argument("--json", action="store_true", help="Output JSON format")

    p_pnew = probe_sub.add_parser("new", help="Scaffold a new probe template in .diagnostics/probes/")
    p_pnew.add_argument("name", help="Probe name to create")
    p_pnew.add_argument("--domain", default="general", help="Diagnostic domain (e.g. hardware, database)")
    p_pnew.add_argument("--path", default=None, help="Root directory (default: current directory)")

    p_psave = probe_sub.add_parser("save", help="Promote a verified script into the probe registry")
    p_psave.add_argument("source", help="Source script path (e.g. from scratch/)")
    p_psave.add_argument("name", help="Registered probe name")
    p_psave.add_argument("--workspace", action="store_true", help="Save to workspace .diagnostics/ instead of global")
    p_psave.add_argument("--path", default=None, help="Root workspace directory")
    return p_probe
