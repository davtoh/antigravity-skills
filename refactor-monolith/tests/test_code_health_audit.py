#!/usr/bin/env python3
"""Unit tests for code_health_audit and multi-language structural analyzers."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure skill root is in sys.path for clean import of scripts
_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from scripts.code_health_audit import (
    AuditThresholds,
    FileReport,
    analyze_python_ast,
    audit_file,
    classify_count,
    iter_source_files,
    main,
    recommend_mode,
)
from scripts.language_analyzers import (
    analyze_brace_language,
    analyze_generic_fallback,
    analyze_stylesheet,
    is_vendor_or_generated,
)


class TestClassifyCount(unittest.TestCase):
    """Test classification logic against soft and hard budget limits."""

    def test_ok_boundary(self) -> None:
        self.assertEqual(classify_count(350, 350, 500), "OK")
        self.assertEqual(classify_count(10, 10, 12), "OK")

    def test_warning_boundary(self) -> None:
        self.assertEqual(classify_count(351, 350, 500), "WARNING")
        self.assertEqual(classify_count(500, 350, 500), "WARNING")

    def test_critical_boundary(self) -> None:
        self.assertEqual(classify_count(501, 350, 500), "CRITICAL")
        self.assertEqual(classify_count(13, 10, 12), "CRITICAL")


class TestPythonAstAnalysis(unittest.TestCase):
    """Test AST-level parsing and detection of Python classes and functions."""

    def setUp(self) -> None:
        self.thresholds = AuditThresholds(350, 500, 10, 12, 40)

    def test_syntax_error_and_null_bytes_handled(self) -> None:
        self.assertEqual(analyze_python_ast("def broken(:", self.thresholds), ([], []))
        self.assertEqual(analyze_python_ast("def f():\x00 pass", self.thresholds), ([], []))

    def test_class_method_count_and_status(self) -> None:
        method_defs = "\n".join(f"    def m_{i}(self): pass" for i in range(13))
        classes, _ = analyze_python_ast(f"class LargeService:\n{method_defs}\n", self.thresholds)
        self.assertEqual(len(classes), 1)
        self.assertEqual(classes[0].name, "LargeService")
        self.assertEqual(classes[0].method_count, 13)
        self.assertEqual(classes[0].status, "CRITICAL")

    def test_oversized_function_detection(self) -> None:
        func_body = "\n".join("    x = 1" for _ in range(43))
        _, funcs = analyze_python_ast(f"def giant():\n{func_body}\n    return x\n", self.thresholds)
        self.assertEqual(len(funcs), 1)
        self.assertEqual(funcs[0].name, "giant")
        self.assertEqual(funcs[0].status, "CRITICAL")

    def test_nested_standalone_function_detection(self) -> None:
        func_body = "\n".join("        x = 1" for _ in range(43))
        code = f"if True:\n    def nested_func():\n{func_body}\n        return x\n"
        _, funcs = analyze_python_ast(code, self.thresholds)
        self.assertEqual(len(funcs), 1)
        self.assertEqual(funcs[0].name, "nested_func")
        self.assertEqual(funcs[0].status, "CRITICAL")


class TestMultiLanguageAnalyzers(unittest.TestCase):
    """Test zero-dependency C-style brace, stylesheet, fallback, and vendor analyzers."""

    def test_typescript_class_and_methods(self) -> None:
        ts_code = (
            "export class OrderController {\n"
            + "\n".join(f"  async handleItem{i}(req: Request) {{\n    return {i};\n  }}" for i in range(11))
            + "\n}\n"
        )
        symbols = analyze_brace_language(ts_code)
        classes = [s for s in symbols if s.kind == "class"]
        self.assertEqual(len(classes), 1)
        self.assertEqual(classes[0].name, "OrderController")
        self.assertEqual(len(classes[0].methods), 11)

    def test_go_struct_and_receiver_methods(self) -> None:
        go_code = (
            "type Store struct {\n  db string\n}\n"
            "func (s *Store) GetUser(id int) error {\n  return nil\n}\n"
            "func (s *Store) SaveUser(id int) error {\n  return nil\n}\n"
        )
        symbols = analyze_brace_language(go_code)
        classes = [s for s in symbols if s.kind == "class" and s.name == "Store"]
        self.assertEqual(len(classes), 1)
        self.assertEqual(classes[0].methods, ["GetUser", "SaveUser"])

    def test_stylesheet_clusters_and_keyframes(self) -> None:
        rules = "\n".join(f".nav-menu .item-{i} {{ color: red; }}" for i in range(7))
        big_kf = "@keyframes spin {\n" + "\n".join(f"  {i}% {{ opacity: 1; }}" for i in range(28)) + "\n}"
        css_code = f"/* === Header Navigation === */\n{rules}\n{big_kf}\n"
        symbols = analyze_stylesheet(css_code)
        names = {s.name for s in symbols}
        self.assertIn("Section:Header Navigation", names)
        self.assertIn(".nav-menu*", names)
        self.assertIn("@keyframes spin", names)

    def test_fallback_scanner_measures_blocks(self) -> None:
        ruby_like = "def alpha\n" + "  x = 1\n" * 35 + "def beta\n  y = 2\n"
        symbols = analyze_generic_fallback(ruby_like)
        self.assertEqual(len(symbols), 2)
        self.assertEqual(symbols[0].name, "alpha")
        self.assertGreaterEqual(symbols[0].lines, 35)

    def test_vendor_and_minified_detection(self) -> None:
        self.assertTrue(is_vendor_or_generated(Path("static/js/slick.js")))
        self.assertTrue(is_vendor_or_generated(Path("static/js/app.min.js")))
        self.assertTrue(is_vendor_or_generated(Path("static/scss/bootstrap/_reboot.scss"), ("static", "scss", "bootstrap", "_reboot.scss")))
        self.assertFalse(is_vendor_or_generated(Path("intelligent_tracker_hub/api_views.py")))

    def test_multiline_comment_braces_ignored(self) -> None:
        ts_code = "/*\n * { not a block }\n */\nexport function cleanFn() {\n  return 1;\n}\n"
        symbols = analyze_brace_language(ts_code)
        funcs = [s for s in symbols if s.kind == "func"]
        self.assertEqual(len(funcs), 1)
        self.assertEqual(funcs[0].name, "cleanFn")


class TestSourceFileAuditAndCli(unittest.TestCase):
    """Test filesystem iteration, vendor pruning, and CLI execution."""

    def test_iter_source_files_prunes_vendor_and_node_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "src").mkdir()
            (base / "src" / "main.ts").write_text("export const x = 1;", encoding="utf-8")
            (base / "src" / "slick.js").write_text("var slick = 1;", encoding="utf-8")
            (base / "node_modules").mkdir()
            (base / "node_modules" / "pkg.js").write_text("const y = 2;", encoding="utf-8")

            rel_default = [p.relative_to(base).as_posix() for p in iter_source_files(base)]
            self.assertEqual(rel_default, ["src/main.ts"])
            rel_vendor = [p.relative_to(base).as_posix() for p in iter_source_files(base, include_vendor=True)]
            self.assertIn("src/slick.js", rel_vendor)

    def test_audit_file_measures_lines(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write("a = 1\nb = 2\nc = 3\n")
            f_path = Path(f.name)
        try:
            report = audit_file(f_path, f_path.parent, AuditThresholds())
            self.assertEqual(report.lines, 3)
            self.assertEqual(report.status, "OK")
        finally:
            f_path.unlink(missing_ok=True)

    def test_cli_exit_codes_and_json_output(self) -> None:
        with patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(main(["--path", "non_existent_dir_12345"]), 2)
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "service.ts"
            f.write_text("export function run() {\n  return 1;\n}\n", encoding="utf-8")
            with patch("sys.stdout", new_callable=io.StringIO) as out:
                self.assertEqual(main(["--path", tmpdir, "--json", "--strict"]), 0)
                payload = json.loads(out.getvalue())
                self.assertEqual(payload["recommended_mode"], "SINGLE_FILE")
                self.assertEqual(payload["files"][0]["parser_mode"], "brace")

    def test_breached_directory_strict_returns_code_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "huge.py"
            f.write_text("\n".join(f"x_{i} = {i}" for i in range(505)), encoding="utf-8")
            with patch("sys.stdout", new_callable=io.StringIO):
                code = main(["--path", tmpdir, "--strict"])
                self.assertEqual(code, 1)

    def test_clean_directory_strict_returns_code_0(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "clean.py"
            f.write_text("def hello(): return 'world'\n", encoding="utf-8")
            with patch("sys.stdout", new_callable=io.StringIO):
                code = main(["--path", tmpdir, "--strict"])
                self.assertEqual(code, 0)

    def test_recommend_mode_switches_to_project_campaign(self) -> None:
        multi_sub = [FileReport(f"sub_{i}/m{i}.py", 650, "CRITICAL") for i in range(3)]
        self.assertEqual(recommend_mode(multi_sub), "PROJECT_CAMPAIGN")
        tests_only = [FileReport(f"tests/test_{i}.py", 800, "CRITICAL") for i in range(3)]
        self.assertEqual(recommend_mode(tests_only), "SINGLE_FILE")
        single_target = [FileReport("server.py", 3500, "CRITICAL")]
        self.assertEqual(recommend_mode(single_target), "SINGLE_FILE")
        two_huge_monoliths = [FileReport(f"pkg{i}/big.py", 1800, "CRITICAL") for i in range(2)]
        self.assertEqual(recommend_mode(two_huge_monoliths), "PROJECT_CAMPAIGN")


if __name__ == "__main__":
    unittest.main()
