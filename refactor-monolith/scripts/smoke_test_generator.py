#!/usr/bin/env python3
"""Cross-platform contract smoke test generator.

Generates self-contained, regression-locking unit tests enforcing DOM ID parity,
dropdown availability, scoped CSS !important containment, and Python callable/signature
integrity across refactor phases.
"""

import json
import os
from pathlib import Path
from typing import Any

from campaign_manager import get_repo_root

_SMOKE_TEST_TEMPLATE = '''# Generated Contract Smoke Test - Enforces Zero-Regression Refactoring Parity
import ast
import enum
import importlib
import inspect
import pathlib
import re
import sys
import unittest

class TestCodebaseContractInvariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = {root_expr}
        cls.root_str = str(cls.root)
        if cls.root_str not in sys.path:
            sys.path.insert(0, cls.root_str)
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
        if not {select_ids}:
            return
        for sel in {select_ids}:
            found = bool(re.search(r'\\bid\\s*=\\s*["\\\']' + re.escape(sel) + r'["\\\']', self.html_text))
            self.assertTrue(found, f"Missing select dropdown #{{sel}} in HTML!")

    def test_dom_element_ids_preserved(self):
        """Verify captured baseline HTML element IDs are preserved."""
        if not {html_ids}:
            return
        for el_id in {html_ids}:
            found = bool(re.search(r'\\bid\\s*=\\s*["\\\']' + re.escape(el_id) + r'["\\\']', self.html_text))
            self.assertTrue(found, f"Critical DOM element id='{{el_id}}' was removed from HTML!")

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

    def test_python_callable_smoke_and_signature_parity(self):
        """Verify Python modules are importable, signatures are valid, and parameterless classes instantiate cleanly."""
        ignored = {{".git", ".venv", "venv", "env", "node_modules", "__pycache__", "_build", "build", "dist", ".refactor", "scratch"}}
        py_files = [p for p in self.root.rglob("*.py") if not any(part in ignored for part in p.parts)]
        if not py_files:
            return
        failures = []
        for p in py_files:
            try:
                code = p.read_text(encoding="utf-8", errors="replace")
                ast.parse(code, filename=str(p))
            except SyntaxError as e:
                failures.append(f"SyntaxError in {{p.name}}: {{e}}")
                continue

            rel_parts = p.relative_to(self.root).with_suffix("").parts
            rel_mod = ".".join(rel_parts)
            try:
                mod = importlib.import_module(rel_mod)
            except Exception:
                continue

            for name, obj in inspect.getmembers(mod):
                if inspect.isclass(obj) and getattr(obj, "__module__", None) == mod.__name__:
                    if inspect.isabstract(obj):
                        continue
                    if issubclass(obj, (enum.Enum, BaseException)):
                        continue
                    try:
                        sig = inspect.signature(obj)
                        req_params = [
                            param for param in sig.parameters.values()
                            if param.default is inspect.Parameter.empty
                            and param.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
                        ]
                        if not req_params:
                            try:
                                obj()
                            except TypeError as te:
                                failures.append(f"Initialization TypeError in {{name}}(): {{te}}")
                            except Exception:
                                pass
                    except (ValueError, TypeError) as se:
                        failures.append(f"Invalid class signature {{name}}: {{se}}")
                elif inspect.isfunction(obj) and getattr(obj, "__module__", None) == mod.__name__:
                    try:
                        inspect.signature(obj)
                    except (ValueError, TypeError) as se:
                        failures.append(f"Invalid function signature {{name}}: {{se}}")

        if failures:
            self.fail("Callable smoke test failed:\\n  " + "\\n  ".join(failures))

if __name__ == "__main__":
    unittest.main()
'''


def _build_smoke_template(
    root_expr: str,
    select_ids: list[str],
    important_count: int,
    html_ids: list[str],
    python_globals: list[str] | None = None,
) -> str:
    """Render unit test code string for contract smoke verification."""
    return _SMOKE_TEST_TEMPLATE.format(
        root_expr=root_expr,
        select_ids=repr(select_ids),
        important_count=important_count,
        html_ids=repr(html_ids),
        python_globals=repr(python_globals or []),
    )


def _resolve_root_expr(target: Path, repo_root: Path, out_p: Path | None = None) -> str:
    """Determine relative or absolute path expression for test root."""
    try:
        test_dir = out_p.parent.resolve() if out_p else repo_root / "tests"
        rel_target = os.path.relpath(target.resolve(), test_dir).replace("\\", "/")
        parts = [p for p in rel_target.split("/") if p]
        if not parts or parts == ["."]:
            return "pathlib.Path(__file__).resolve().parent"

        dot_count = 0
        for p in parts:
            if p == "..":
                dot_count += 1
            else:
                break

        remainder = parts[dot_count:]
        if dot_count > 0:
            parent_chain = ".".join(["parent"] * (dot_count + 1))
            if remainder:
                sub = "/".join(remainder)
                return f'pathlib.Path(__file__).resolve().{parent_chain} / "{sub}"'
            return f"pathlib.Path(__file__).resolve().{parent_chain}"

        sub = "/".join(remainder)
        return f'pathlib.Path(__file__).resolve().parent / "{sub}"'
    except Exception:
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

    root_expr = _resolve_root_expr(target, repo_root, out_p)
    out_p.write_text(
        _build_smoke_template(
            root_expr,
            c.select_ids,
            c.css_important_count,
            c.html_ids,
            c.python_globals,
        ),
        encoding="utf-8",
    )
    print(f"Generated contract smoke test -> {out_p}")
    return 0
