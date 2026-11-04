#!/usr/bin/env python3
"""Automated unit and integration tests for contract smoke test generation.

Tests:
1. Relative root path expression resolution across nested directories (tests/, tests/unit/, etc.).
2. DOM element ID and <select> matching supporting single quotes, double quotes, and spacing.
3. Pure library / non-web scope handling where HTML files are absent or empty.
4. Inline script function extraction satisfying HTML inline event handlers.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Add scripts directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from contract_diff_engine import build_contract, diff_contracts  # noqa: E402
from smoke_test_generator import _resolve_root_expr, cmd_generate_smoke_test  # noqa: E402
from surface_scanners import scan_js_surface  # noqa: E402

class TestSmokeTestPathResolution(unittest.TestCase):
    """Test _resolve_root_expr path calculations for arbitrary directory depths."""

    def test_single_level_test_dir(self) -> None:
        base = Path("/repo/root")
        test_file = base / "tests" / "test_refactor_contract.py"

        # Target is repo root
        expr_root = _resolve_root_expr(base, base, test_file)
        self.assertEqual(expr_root, "pathlib.Path(__file__).resolve().parent.parent")

        # Target is subfolder
        expr_sub = _resolve_root_expr(base / "dashboard", base, test_file)
        self.assertEqual(expr_sub, 'pathlib.Path(__file__).resolve().parent.parent / "dashboard"')

    def test_deeply_nested_test_dir(self) -> None:
        base = Path("/repo/root")
        test_file = base / "tests" / "unittest_tests" / "test_refactor_contract.py"

        # Target is repo root from 2-levels deep test file
        expr_root = _resolve_root_expr(base, base, test_file)
        self.assertEqual(expr_root, "pathlib.Path(__file__).resolve().parent.parent.parent")

        # Target is subfolder from 2-levels deep test file
        expr_sub = _resolve_root_expr(base / "RRtoolbox", base, test_file)
        self.assertEqual(expr_sub, 'pathlib.Path(__file__).resolve().parent.parent.parent / "RRtoolbox"')

    def test_same_dir_and_subfolder(self) -> None:
        base = Path("/repo/root")
        test_file = base / "tests" / "test_refactor_contract.py"

        # Target is the test directory itself
        expr_same = _resolve_root_expr(base / "tests", base, test_file)
        self.assertEqual(expr_same, "pathlib.Path(__file__).resolve().parent")

        # Target is a subfolder of test directory
        expr_child = _resolve_root_expr(base / "tests" / "fixtures", base, test_file)
        self.assertEqual(expr_child, 'pathlib.Path(__file__).resolve().parent / "fixtures"')

class TestSmokeTestExecutionAndQuoteTolerance(unittest.TestCase):
    """Test generated smoke test execution on varied HTML quotes and spacings."""

    def test_smoke_test_passes_with_mixed_quotes_and_spacing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / ".git").mkdir()
            app_dir = base / "webapp"
            app_dir.mkdir()

            html_content = (
                '<!DOCTYPE html>\n'
                '<html>\n'
                '<body>\n'
                '  <select id="cam-double"></select>\n'
                '  <select id = \'cam-single\'></select>\n'
                '  <div id="player-double"></div>\n'
                '  <div id = \'player-single\'></div>\n'
                '</body>\n'
                '</html>\n'
            )
            (app_dir / "index.html").write_text(html_content, encoding="utf-8")
            (app_dir / "app.css").write_text("body { margin: 0; }\n", encoding="utf-8")

            out_test = base / "tests" / "test_contract.py"
            code = cmd_generate_smoke_test(app_dir, out_file=str(out_test))
            self.assertEqual(code, 0)
            self.assertTrue(out_test.exists())

            # Execute the generated smoke test using python runner
            res = subprocess.run([sys.executable, str(out_test)], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Generated smoke test failed: {res.stderr}\nOutput: {res.stdout}")

    def test_smoke_test_execution_empty_html_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / ".git").mkdir()
            lib_dir = base / "mylib"
            lib_dir.mkdir()
            (lib_dir / "module.py").write_text("def run(): return 42\n", encoding="utf-8")

            out_test = base / "tests" / "test_contract.py"
            code = cmd_generate_smoke_test(lib_dir, out_file=str(out_test))
            self.assertEqual(code, 0)

            # Execution with no HTML/CSS in scope should pass cleanly
            res = subprocess.run([sys.executable, str(out_test)], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Empty scope test failed: {res.stderr}")

class TestInlineScriptFunctionExtraction(unittest.TestCase):
    """Test that inline <script> functions satisfy HTML inline handlers without false alarms."""

    def test_inline_script_functions_captured_in_surface(self) -> None:
        js_code = (
            "async function switchShowcase(key) { console.log(key); }\n"
            "function copyCommand() { return true; }\n"
            "window.App = { init() {} };\n"
        )
        surf = scan_js_surface(js_code)
        self.assertIn("switchShowcase", surf.global_exports)
        self.assertIn("copyCommand", surf.global_exports)
        self.assertIn("App", surf.global_exports)

    def test_diff_contracts_recognizes_inline_script_handlers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / ".git").mkdir()
            html = (
                '<!DOCTYPE html>\n'
                '<html>\n'
                '<body>\n'
                '  <button onclick="switchShowcase(\'retina\')">Show</button>\n'
                '  <button onclick="copyCommand()">Copy</button>\n'
                '  <script>\n'
                '    function switchShowcase(key) { return key; }\n'
                '    function copyCommand() { return true; }\n'
                '  </script>\n'
                '</body>\n'
                '</html>\n'
            )
            (base / "demo.html").write_text(html, encoding="utf-8")

            # Capture contract from live workspace
            c_before = build_contract(base)
            c_after = build_contract(base)

            # Contract diff should report zero issues (inline functions satisfy handlers)
            issues = diff_contracts(c_before, c_after)
            self.assertEqual(issues, [], f"Unexpected contract issues found: {issues}")


class TestCallableSmokeParity(unittest.TestCase):
    """Test generated smoke test callable signature and class instantiation verification."""

    def test_callable_smoke_verifies_classes_and_functions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / ".git").mkdir()
            pkg = base / "pkg"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("", encoding="utf-8")
            (pkg / "service.py").write_text(
                "import abc\n"
                "class AbstractWorker(abc.ABC):\n"
                "    @abc.abstractmethod\n"
                "    def work(self):\n"
                "        pass\n\n"
                "class DataProcessor:\n"
                "    def __init__(self, mode: str = 'default'):\n"
                "        self.mode = mode\n"
                "    def process(self):\n"
                "        return 100\n\n"
                "def calculate(factor: int = 1) -> int:\n"
                "    return 42 * factor\n",
                encoding="utf-8",
            )

            out_test = base / "tests" / "test_smoke_callables.py"
            code = cmd_generate_smoke_test(pkg, out_file=str(out_test))
            self.assertEqual(code, 0)
            self.assertTrue(out_test.exists())

            # Execute generated smoke test - should pass cleanly
            res = subprocess.run([sys.executable, str(out_test)], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Smoke test failed: {res.stderr}\nOutput: {res.stdout}")

    def test_callable_smoke_catches_init_type_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / ".git").mkdir()
            pkg = base / "broken_pkg"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("", encoding="utf-8")
            (pkg / "faulty.py").write_text(
                "class FaultyClass:\n"
                "    def __init__(self):\n"
                "        raise TypeError('missing 1 required positional argument: stage')\n",
                encoding="utf-8",
            )

            out_test = base / "tests" / "test_smoke_broken.py"
            code = cmd_generate_smoke_test(pkg, out_file=str(out_test))
            self.assertEqual(code, 0)

            # Execution of generated smoke test should catch the TypeError and fail with returncode != 0
            res = subprocess.run([sys.executable, str(out_test)], capture_output=True, text=True)
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("Initialization TypeError in FaultyClass", res.stderr + res.stdout)

    def test_callable_smoke_skips_enums_and_exceptions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / ".git").mkdir()
            pkg = base / "enum_pkg"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("", encoding="utf-8")
            (pkg / "types.py").write_text(
                "import enum\n\n"
                "class Status(enum.Enum):\n"
                "    PENDING = 1\n"
                "    ACTIVE = 2\n\n"
                "class CustomError(Exception):\n"
                "    pass\n",
                encoding="utf-8",
            )
            out_test = base / "tests" / "test_smoke_enums.py"
            code = cmd_generate_smoke_test(pkg, out_file=str(out_test))
            self.assertEqual(code, 0)
            self.assertTrue(out_test.exists())
            res = subprocess.run([sys.executable, str(out_test)], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Enum smoke test failed: {res.stderr}\nOutput: {res.stdout}")


if __name__ == "__main__":
    unittest.main()
