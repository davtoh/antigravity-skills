#!/usr/bin/env python3
"""Shared engine-path bootstrap embedded verbatim into every generated `diagnostic_bridge.py`.

Candidate order (Runtime Parity Contract): ``SYSTEM_DIAGNOSTICS_DIR``, then for each ancestor of the
bridge (nearest first) ``.claude/skills/system-diagnostics`` and ``skills/system-diagnostics``, then
``~/.claude/skills/system-diagnostics``, a sibling ``system-diagnostics`` folder, and finally
``~/.gemini/config/skills/system-diagnostics``. A candidate counts only if ``scripts/trace_recorder.py``
exists, so a missing engine degrades to no-ops instead of a wrong path winning silently.
"""

PLACEHOLDER = "# @@ENGINE_BOOTSTRAP@@"

BOOTSTRAP_SRC = '''import os
import sys
from pathlib import Path

_SKILL = "system-diagnostics"


def _engine_candidates():
    here = Path(__file__).resolve()
    roots = list(here.parents)[:4]
    home = Path.home()
    found = []
    if os.environ.get("SYSTEM_DIAGNOSTICS_DIR"):
        found.append(Path(os.environ["SYSTEM_DIAGNOSTICS_DIR"]))
    found += [r / ".claude" / "skills" / _SKILL for r in roots]
    found.append(home / ".claude" / "skills" / _SKILL)
    found += [r.parent / _SKILL for r in roots]
    found += [r / "skills" / _SKILL for r in roots]
    found.append(home / ".gemini" / "config" / "skills" / _SKILL)
    return [c / "scripts" if (c / "scripts").is_dir() else c for c in found]


for _p in _engine_candidates():
    if (_p / "trace_recorder.py").is_file():
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))
        break
'''
