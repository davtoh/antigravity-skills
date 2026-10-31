#!/usr/bin/env python3
"""Cross-platform contract smoke test generator.

Generates self-contained, regression-locking unit tests enforcing DOM ID parity,
dropdown availability, and scoped CSS !important containment across refactor phases.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from campaign_manager import get_repo_root

_SMOKE_TEST_TEMPLATE = '''# Generated Contract Smoke Test - Enforces Zero-Regression Refactoring Parity
import pathlib
import re
import unittest

class TestCodebaseContractInvariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = {root_expr}
        ignored = {{".git", ".venv", "venv", "env", "node_modules", "__pycache__", "_build", "build", "dist", ".refactor", "scratch"}}
        cls.html_text = "".join(
            p.read_text(encoding="utf-8", errors="replace") + "\\n"
            for p in cls.root.rglob("*.html")
            if not any(part in ignored for part in p.parts)
        )
        cls.js_text = "".join(
            p.read_text(encoding="utf-8", errors="replace") + "\\n"
            for p in cls.root.rglob("*.js")
            if not any(part in ignored for part in p.parts)
        )

    def test_dom_interactive_selects_exist(self):
        """Verify all critical <select> dropdown IDs exist in HTML."""
        for sel in {select_ids}:
            self.assertIn(f'id="{{sel}}"', self.html_text, f"Missing select dropdown #{{sel}} in HTML!")

    def test_dom_element_ids_preserved(self):
        """Verify captured baseline HTML element IDs are preserved."""
        for el_id in {html_ids}:
            self.assertIn(f'id="{{el_id}}"', self.html_text, f"Critical DOM element id='{{el_id}}' was removed from HTML!")

    def test_zero_css_important_creep(self):
        """Verify scoped CSS does not exceed baseline !important threshold."""
        ignored = {{".git", ".venv", "venv", "env", "node_modules", "__pycache__", "_build", "build", "dist", ".refactor", "scratch"}}
        css_text = "".join(
            p.read_text(encoding="utf-8", errors="replace")
            for p in self.root.rglob("*.css")
            if not any(part in ignored for part in p.parts)
        )
        count = len(re.findall(r'!important\\b', css_text, re.IGNORECASE))
        self.assertLessEqual(count, {important_count}, f"!important count increased to {{count}}!")

if __name__ == "__main__":
    unittest.main()
'''


def _build_smoke_template(root_expr: str, select_ids: list[str], important_count: int, html_ids: list[str]) -> str:
    """Render unit test code string for contract smoke verification."""
    return _SMOKE_TEST_TEMPLATE.format(
        root_expr=root_expr,
        select_ids=repr(select_ids),
        important_count=important_count,
        html_ids=repr(html_ids),
    )


def _resolve_root_expr(target: Path, repo_root: Path) -> str:
    """Determine relative or absolute path expression for test root."""
    try:
        rel_target = target.relative_to(repo_root)
        if str(rel_target) in (".", ""):
            return "pathlib.Path(__file__).resolve().parent.parent"
        return f'pathlib.Path(__file__).resolve().parent.parent / "{rel_target.as_posix()}"'
    except ValueError:
        return f'pathlib.Path(r"{target.as_posix()}")'


def cmd_generate_smoke_test(
    target: Path,
    out_file: str,
    before_file: str = "",
    git_ref: str = "",
    contract_builder: Any = None,
) -> int:
    """Generate standalone unittest file enforcing contract parity."""
    # Lazy import to avoid circular dependency
    from contract_snapshot import CodebaseContract, build_contract

    if before_file:
        c = CodebaseContract.from_dict(json.loads(Path(before_file).read_text(encoding="utf-8")))
    elif contract_builder:
        c = contract_builder(target, git_ref)
    else:
        c = build_contract(target, git_ref)

    repo_root = get_repo_root(target)
    out_p = Path(out_file) if out_file else repo_root / "tests" / "test_refactor_contract.py"
    out_p.parent.mkdir(parents=True, exist_ok=True)

    root_expr = _resolve_root_expr(target, repo_root)
    out_p.write_text(_build_smoke_template(root_expr, c.select_ids, c.css_important_count, c.html_ids), encoding="utf-8")
    print(f"Generated contract smoke test -> {out_p}")
    return 0
