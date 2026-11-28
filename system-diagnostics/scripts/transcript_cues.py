#!/usr/bin/env python3
"""Cue lists for user-correction / workflow-redirect detection (English defaults, Spanish extras).

The Antigravity reader keeps its original English-only regexes (decision D4). Claude rows use
``load_cues()``: English defaults + Spanish defaults + optional extras from
``<workspace>/.diagnostics/retro_cues.json``::

    {"correction": ["word or phrase"], "bug_symptom": [...], "workflow_redirect": [...], "redirect_verb": [...]}

Entries are literal words/phrases (escaped, matched at word boundaries). Unknown keys, bad types and
a malformed file are ignored, never fatal.
"""

import json
import re
from pathlib import Path
from typing import Any

CUE_FILE = Path(".diagnostics") / "retro_cues.json"
_EN = {
    "correction": ["no", "instead", "wrong", "failed", "don't", "do not", "stop", "worthless", "why did you"],
    "bug_symptom": ["bug", "broken", "error", "fail", "failed", "failing", "crash", "crashed", "crashing", "exception",
                    "overflow", "black", "blank", "stuck", "regression", "/app-debugger"],
    "workflow_redirect": ["agent", "model", "hydrogen", "neon", "opus", "sonnet", "flash", "plan mode", "swarm",
                          "unchecked", "cleanup", "housekeeping"],
    "redirect_verb": ["switch", "change to"],
}
_ES = {
    "correction": ["en vez de", "en lugar de", "incorrecto", "equivocado", "equivocada", "mal", "fallo", "falló",
                   "no hagas", "detente", "basura", "por qué hiciste", "por que hiciste"],
    "bug_symptom": ["roto", "rota", "falla", "fallan", "se cuelga", "pantalla en blanco", "regresión", "excepción"],
    "workflow_redirect": ["agente", "modelo", "modo plan", "limpieza"],
    "redirect_verb": ["cambia a", "cambiar a", "cambiemos a", "usa el modelo"],
}


def _compile(words: list[str]) -> re.Pattern[str]:
    ordered = sorted({w.strip() for w in words if w.strip()}, key=lambda w: (-len(w), w))
    alt = "|".join(r"\s+".join(re.escape(part) for part in w.split()) for w in ordered)
    return re.compile(rf"(?<![\w-])(?:{alt})(?![\w-])", re.I) if alt else re.compile(r"(?!x)x")


def _extras(workspace: Path | None) -> dict[str, list[str]]:
    if workspace is None:
        return {}
    try:
        data: Any = json.loads((workspace / CUE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: [w for w in v if isinstance(w, str)] for k, v in data.items() if k in _EN and isinstance(v, list)}


def load_cues(workspace: Path | None = None) -> dict[str, re.Pattern[str]]:
    """Return compiled cue regexes keyed ``correction|bug_symptom|workflow_redirect|redirect_verb``."""
    extra = _extras(workspace)
    return {k: _compile(_EN[k] + _ES[k] + extra.get(k, [])) for k in _EN}
