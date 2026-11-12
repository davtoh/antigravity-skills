#!/usr/bin/env python3
"""Thin SSOT shim delegating to system-diagnostics/scripts/css_inspector.py."""

import importlib.util
import os
import runpy
import sys
from pathlib import Path


def _resolve_ssot(script_name: str) -> Path:
    """Locate the authoritative script in system-diagnostics/scripts/."""
    env_dir = os.environ.get("SYSTEM_DIAGNOSTICS_DIR")
    here = Path(__file__).resolve().parent
    candidates = [
        Path(env_dir) / "scripts" / script_name if env_dir else None,
        here.parent.parent / "system-diagnostics" / "scripts" / script_name,
        Path.home() / ".gemini" / "config" / "skills" / "system-diagnostics" / "scripts" / script_name,
    ]
    for cand in candidates:
        if cand and cand.is_file():
            return cand.resolve()
    sys.stderr.write(
        f"[{here.parent.name}] Error: SSOT script '{script_name}' not found in system-diagnostics.\n"
    )
    raise SystemExit(2)


def _load_ssot_module(script_name: str):
    """Load SSOT module via importlib and bind its public and private attributes."""
    target = _resolve_ssot(script_name)
    ssot_dir = str(target.parent)
    if ssot_dir not in sys.path:
        sys.path.insert(0, ssot_dir)
    spec = importlib.util.spec_from_file_location(f"_ssot_{target.stem}", target)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load SSOT spec from {target}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return target, module


_TARGET_PATH, _SSOT_MOD = _load_ssot_module("css_inspector.py")
globals().update({k: v for k, v in vars(_SSOT_MOD).items() if not k.startswith("__")})

if __name__ == "__main__":
    runpy.run_path(str(_TARGET_PATH), run_name="__main__")
else:
    sys.modules[__name__] = _SSOT_MOD
