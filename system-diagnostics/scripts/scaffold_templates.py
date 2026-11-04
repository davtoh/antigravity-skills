#!/usr/bin/env python3
"""Scaffolding and reporting templates for defect catalog (system-diagnostics).

Provides templated code generation for Red-to-Green quarantine reproduction tests,
Architectural Elevation Briefs, and human-readable DEFECT_CATALOG.md files.
"""

import re
from typing import Any

QUARANTINE_REL_PATH = "tests/quarantine"


def generate_catalog_markdown(catalog_data: dict[str, Any]) -> str:
    """Generate human-readable markdown representation of defect catalog."""
    summary = catalog_data.get("summary", {})
    defects = catalog_data.get("defects", [])
    ws = catalog_data.get("workspace", "")
    ts = catalog_data.get("updated_at", "")

    lines = [
        "# Latent Defect & Code Smell Catalog",
        "",
        f"**Workspace:** `{ws}`  ",
        f"**Last Updated:** `{ts}`  ",
        f"**Total Defects:** {summary.get('total', 0)} "
        f"(Tactical: {summary.get('by_track', {}).get('tactical', 0)}, "
        f"Architectural: {summary.get('by_track', {}).get('architectural', 0)})",
        "",
        "## Summary by Severity",
        f"- **HIGH:** {summary.get('by_severity', {}).get('HIGH', 0)}",
        f"- **MEDIUM:** {summary.get('by_severity', {}).get('MEDIUM', 0)}",
        f"- **LOW:** {summary.get('by_severity', {}).get('LOW', 0)}",
        "",
        "## Quarantined Defects",
        "",
        "| ID | Fingerprint | Severity | Track | Symbol | File:Line | Rule | Status |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for d in defects:
        d_id = d.get("id", "")
        fp = d.get("fingerprint", "")
        sev = d.get("severity", "MEDIUM")
        trk = d.get("track", "tactical")
        sym = f"`{d.get('symbol', '')}`" if d.get("symbol") else "-"
        loc = f"`{d.get('file', '')}:{d.get('line', '')}`"
        rule = d.get("rule_id", "")
        status = d.get("status", "quarantined")
        lines.append(f"| {d_id} | `{fp}` | {sev} | {trk} | {sym} | {loc} | {rule} | {status} |")

    lines.append("")
    lines.append("## Remediation Workflows")
    lines.append("- **Tactical Bugs:** Unlock test via `python skills/system-diagnostics/scripts/diagnose.py scaffold-defect --id <ID> --branch` -> solve in `/app-debugger`.")
    lines.append("- **Structural Defects:** Elevate via `python skills/system-diagnostics/scripts/diagnose.py scaffold-defect --id <ID> --elevate` -> redesign in `/frontier-architect` + `/grill-me`.")
    lines.append("")
    return "\n".join(lines) + "\n"


def build_tactical_test_code(
    d_id: str, rule_id: str, rel_file: str, symbol: str, message: str, suggested_fix: str
) -> str:
    """Generate self-contained Red-to-Green reproduction unittest."""
    sym_short = symbol.split(".")[-1] if symbol else "target"
    cls_name = "Test" + re.sub(r"[^a-zA-Z0-9]", "", d_id.title())

    return f'''#!/usr/bin/env python3
"""Quarantine Reproduction Test for {d_id} ({rule_id}).

Target: {rel_file} -> {symbol}
Message: {message}
Suggested Fix: {suggested_fix}

Workflow (/app-debugger):
  1. Verify failing test:
     python -m unittest {QUARANTINE_REL_PATH}/test_{d_id.lower().replace("-", "_")}.py
  2. Apply suggested fix in {rel_file}
  3. Re-verify test passes Green
"""

import ast
import pathlib
import sys
import unittest

WORKSPACE_ROOT = pathlib.Path(__file__).resolve().parents[2]
TARGET_FILE = WORKSPACE_ROOT / "{rel_file}"


class {cls_name}(unittest.TestCase):
    """Reproduces invariant failure for {d_id}."""

    def setUp(self):
        self.assertTrue(TARGET_FILE.is_file(), f"Target file does not exist: {{TARGET_FILE}}")
        self.code = TARGET_FILE.read_text(encoding="utf-8", errors="replace")

    def test_verify_remediation_{d_id.lower().replace("-", "_")}(self):
        """Invariant check: fails while defect is active, passes once fixed."""
        rule = "{rule_id}"
        if rule == "MUTABLE_DEFAULT_ARG":
            tree = ast.parse(self.code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "{sym_short}":
                    for d, p in zip(reversed(node.args.defaults), reversed(node.args.args)):
                        if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                            self.fail(
                                f"[{d_id}] Invariant violation: parameter '{{p.arg}}' in '{{node.name}}' has mutable default. "
                                f"Suggested Fix: {suggested_fix}"
                            )
        elif rule == "UNREACHABLE_CODE":
            tree = ast.parse(self.code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "{sym_short}":
                    for i, stmt in enumerate(node.body[:-1]):
                        if isinstance(stmt, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                            dead = node.body[i + 1]
                            self.fail(
                                f"[{d_id}] Dead statement at line {{dead.lineno}} following '{{type(stmt).__name__}}'. "
                                f"Suggested Fix: {suggested_fix}"
                            )
        elif rule == "SILENT_BARE_EXCEPT":
            tree = ast.parse(self.code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Try):
                    for h in node.handlers:
                        if h.type is None:
                            self.fail(
                                f"[{d_id}] Silent bare 'except:' clause at line {{h.lineno}}. "
                                f"Suggested Fix: {suggested_fix}"
                            )
        elif rule == "HARDCODED_SECRET_PATTERN":
            import re
            sec = re.compile(r"""(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|private[_-]?key|password)\\s*[:=]\\s*['"][a-zA-Z0-9_\\-\\.]{{16,}}['"]""")
            for idx, line in enumerate(self.code.splitlines(), start=1):
                if "# pragma: allow-defect" not in line and sec.search(line):
                    self.fail(
                        f"[{d_id}] Hardcoded secret pattern remains active at line {{idx}}. "
                        f"Suggested Fix: {suggested_fix}"
                    )
        elif rule == "CSS_IMPORTANT_OVERRUN":
            for idx, line in enumerate(self.code.splitlines(), start=1):
                if "!important" in line:
                    self.fail(
                        f"[{d_id}] '!important' found at line {{idx}}. "
                        f"Suggested Fix: {suggested_fix}"
                    )
        else:
            tree = ast.parse(self.code)
            self.assertIsNotNone(tree)


if __name__ == "__main__":
    unittest.main()
'''


def generate_architectural_brief(defect: dict[str, Any]) -> str:
    """Generate structured Architectural Elevation Brief for /frontier-architect + /grill-me."""
    d_id = defect.get("id", "DEFECT")
    rule = defect.get("rule_id", "")
    sym = defect.get("symbol", "-")
    loc = f"{defect.get('file', '')}:{defect.get('line', '')}"
    sev = defect.get("severity", "HIGH")
    cat = defect.get("category", "STRUCTURAL")
    fp = defect.get("fingerprint", "")
    msg = defect.get("message", "")
    fix = defect.get("suggested_fix", "")

    return f"""================================================================================
🏛️  ARCHITECTURAL ELEVATION BRIEF: {d_id} ({rule})
================================================================================
Target Symbol:  {sym}
Location:       {loc}
Severity:       {sev} | Category: {cat}
Fingerprint:    {fp}

Systemic Flaw Description:
  {msg}

Suggested Architectural Remediation:
  {fix}

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
