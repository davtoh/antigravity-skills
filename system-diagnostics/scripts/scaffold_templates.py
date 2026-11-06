#!/usr/bin/env python3
"""Scaffolding and reporting templates for defect catalog (system-diagnostics).

Provides templated code generation for Red-to-Green quarantine reproduction tests,
Architectural Elevation Briefs, and human-readable DEFECT_CATALOG.md files.
"""

import re
from typing import Any

QUARANTINE_REL_PATH = "tests/quarantine"
CLOSED_STATUSES = frozenset({"resolved", "dismissed"})


def _format_defect_row(d: dict[str, Any], include_resolution: bool = False) -> str:
    """Format a single defect dictionary into a Markdown table row."""
    d_id = d.get("id", "")
    fp = d.get("fingerprint", "")
    sev = d.get("severity", "MEDIUM")
    trk = d.get("track", "tactical")
    sym = f"`{d.get('symbol', '')}`" if d.get("symbol") else "-"
    loc = f"`{d.get('file', '')}:{d.get('line', '')}`"
    rule = d.get("rule_id", "")
    status = d.get("status", "quarantined")
    if include_resolution:
        note = (d.get("resolution") or "-").replace("|", "\\|")
        return f"| {d_id} | `{fp}` | {sev} | {sym} | {loc} | {rule} | {status} | {note} |"
    return f"| {d_id} | `{fp}` | {sev} | {trk} | {sym} | {loc} | {rule} | {status} |"


def generate_catalog_markdown(catalog_data: dict[str, Any]) -> str:
    """Generate human-readable markdown representation of defect catalog."""
    summary = catalog_data.get("summary", {})
    defects = catalog_data.get("defects", [])
    active_list = [d for d in defects if d.get("status", "quarantined") not in CLOSED_STATUSES]
    closed_list = [d for d in defects if d.get("status", "quarantined") in CLOSED_STATUSES]

    lines = [
        "# Latent Defect & Code Smell Catalog",
        "",
        f"**Workspace:** `{catalog_data.get('workspace', '')}`  ",
        f"**Last Updated:** `{catalog_data.get('updated_at', '')}`  ",
        f"**Total Defects:** {summary.get('total', len(active_list))} "
        f"(Tactical: {summary.get('by_track', {}).get('tactical', 0)}, "
        f"Architectural: {summary.get('by_track', {}).get('architectural', 0)}, "
        f"Resolved: {summary.get('resolved', 0)}, Dismissed: {summary.get('dismissed', 0)})",
        "",
        "## Summary by Severity (Active)",
        f"- **HIGH:** {summary.get('by_severity', {}).get('HIGH', 0)}",
        f"- **MEDIUM:** {summary.get('by_severity', {}).get('MEDIUM', 0)}",
        f"- **LOW:** {summary.get('by_severity', {}).get('LOW', 0)}",
        "",
        "## Quarantined & Active Defects",
        "",
        "| ID | Fingerprint | Severity | Track | Symbol | File:Line | Rule | Status |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for d in active_list:
        lines.append(_format_defect_row(d, include_resolution=False))

    if closed_list:
        lines.extend([
            "",
            "## Resolved & Dismissed History",
            "",
            "| ID | Fingerprint | Severity | Symbol | File:Line | Rule | Status | Resolution Note |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ])
        for d in closed_list:
            lines.append(_format_defect_row(d, include_resolution=True))

    lines.extend([
        "",
        "## Remediation Workflows",
        "- **Tactical Bugs:** Unlock test via `python skills/system-diagnostics/scripts/diagnose.py scaffold-defect --id <ID> --branch` -> solve in `/app-debugger`.",
        "- **Structural Defects:** Elevate via `python skills/system-diagnostics/scripts/diagnose.py scaffold-defect --id <ID> --elevate` -> redesign in `/frontier-architect` + `/grill-me`.",
        "- **Mark Solved / Dismiss:** `python skills/system-diagnostics/scripts/diagnose.py resolve-defect --id <ID> --note \"Fixed\"` or `dismiss-defect --id <ID> --reason \"False positive\"`.",
        "",
    ])
    return "\n".join(lines) + "\n"


def _build_rule_check_body(d_id: str, rule_id: str, sym_short: str, suggested_fix: str) -> str:
    """Return rule-specific Python unittest assertion block for tactical quarantine tests."""
    fix_esc = suggested_fix.replace('"', '\\"')
    return f'''        rule = "{rule_id}"
        is_py = TARGET_FILE.suffix.lower() == ".py"
        if rule == "MUTABLE_DEFAULT_ARG" and is_py:
            tree = ast.parse(self.code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "{sym_short}":
                    for d, p in zip(reversed(node.args.defaults), reversed(node.args.args)):
                        if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                            self.fail(f"[{d_id}] Invariant violation: parameter '{{p.arg}}' in '{{node.name}}' has mutable default. Suggested Fix: {fix_esc}")
        elif rule == "UNREACHABLE_CODE" and is_py:
            tree = ast.parse(self.code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "{sym_short}":
                    for i, stmt in enumerate(node.body[:-1]):
                        if isinstance(stmt, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                            dead = node.body[i + 1]
                            self.fail(f"[{d_id}] Dead statement at line {{dead.lineno}} following '{{type(stmt).__name__}}'. Suggested Fix: {fix_esc}")
        elif rule == "SILENT_BARE_EXCEPT":
            if is_py:
                tree = ast.parse(self.code)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Try):
                        for h in node.handlers:
                            if h.type is None:
                                self.fail(f"[{d_id}] Silent bare 'except:' clause at line {{h.lineno}}. Suggested Fix: {fix_esc}")
            elif re.search(r"catch\\s*\\([^)]*\\)\\s*\\{{\\s*\\}}", self.code):
                self.fail(f"[{d_id}] Empty catch block suppresses errors silently. Suggested Fix: {fix_esc}")
        elif rule == "HARDCODED_SECRET_PATTERN":
            sec = re.compile(r"""(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|private[_-]?key|password)\\s*[:=]\\s*['"][a-zA-Z0-9_\\-\\.]{{16,}}['"]""")
            for idx, line in enumerate(self.code.splitlines(), start=1):
                if "# pragma: allow-defect" not in line and sec.search(line):
                    self.fail(f"[{d_id}] Hardcoded secret pattern remains active at line {{idx}}. Suggested Fix: {fix_esc}")
        elif rule == "CSS_IMPORTANT_OVERRUN":
            for idx, line in enumerate(self.code.splitlines(), start=1):
                if "!important" in line:
                    self.fail(f"[{d_id}] '!important' found at line {{idx}}. Suggested Fix: {fix_esc}")
        elif is_py:
            self.assertIsNotNone(ast.parse(self.code))'''


def build_tactical_test_code(
    d_id: str, rule_id: str, rel_file: str, symbol: str, message: str, suggested_fix: str
) -> str:
    """Generate self-contained Red-to-Green reproduction unittest."""
    sym_short = symbol.split(".")[-1] if symbol else "target"
    cls_name = "Test" + re.sub(r"[^a-zA-Z0-9]", "", d_id.title())
    id_slug = d_id.lower().replace("-", "_")
    body_code = _build_rule_check_body(d_id, rule_id, sym_short, suggested_fix)

    return f'''#!/usr/bin/env python3
"""Quarantine Reproduction Test for {d_id} ({rule_id}).

Target: {rel_file} -> {symbol}
Message: {message}
Suggested Fix: {suggested_fix}

Workflow (/app-debugger):
  1. Verify failing test:
     python -m unittest {QUARANTINE_REL_PATH}/test_{id_slug}.py
  2. Apply suggested fix in {rel_file}
  3. Re-verify test passes Green
"""

import ast
import pathlib
import re
import unittest

WORKSPACE_ROOT = pathlib.Path(__file__).resolve().parents[2]
TARGET_FILE = WORKSPACE_ROOT / "{rel_file}"


class {cls_name}(unittest.TestCase):
    """Reproduces invariant failure for {d_id}."""

    def setUp(self):
        self.assertTrue(TARGET_FILE.is_file(), f"Target file does not exist: {{TARGET_FILE}}")
        self.code = TARGET_FILE.read_text(encoding="utf-8", errors="replace")

    def test_verify_remediation_{id_slug}(self):
        """Invariant check: fails while defect is active, passes once fixed."""
{body_code}


if __name__ == "__main__":
    unittest.main()
'''


def generate_architectural_brief(defect: dict[str, Any]) -> str:
    """Generate structured Architectural Elevation Brief for /frontier-architect + /grill-me."""
    d_id = defect.get("id", "DEFECT")
    rule = defect.get("rule_id", "")
    loc = f"{defect.get('file', '')}:{defect.get('line', '')}"
    return f"""================================================================================
🏛️  ARCHITECTURAL ELEVATION BRIEF: {d_id} ({rule})
================================================================================
Target Symbol:  {defect.get('symbol', '-')}
Location:       {loc}
Severity:       {defect.get('severity', 'HIGH')} | Category: {defect.get('category', 'STRUCTURAL')}
Fingerprint:    {defect.get('fingerprint', '')}

Systemic Flaw Description:
  {defect.get('message', '')}

Suggested Architectural Remediation:
  {defect.get('suggested_fix', '')}

Architectural Friction & Risk Analysis:
  Tactical in-flight patches for this defect risk introducing Hyrum's Law cascades,
  unhandled async state races, or violating Rule 5 modularity boundaries.
  A structural redesign is required to preserve system invariants.

Recommended Workflow:
  1. Invoke `/frontier-architect` to explore a 3-tier architectural design:
     - Tier 1 (Baseline): Minimal structural correction.
     - Tier 2 (SOTA): Decoupled asynchronous event pipeline or proper encapsulation.
     - Tier 3 (Moonshot): Self-healing or zero-overhead contract isolation.
  2. Use `/grill-me` to interview the user on design tradeoffs before editing code.
================================================================================"""
