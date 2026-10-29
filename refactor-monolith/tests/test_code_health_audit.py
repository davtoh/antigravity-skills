#!/usr/bin/env python3
"""Unit tests for code_health_audit modularity auditor."""

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
    ClassMetric,
    FileReport,
    FunctionMetric,
    analyze_python_ast,
    audit_file,
    classify_count,
    has_hard_breach,
    iter_source_files,
    main,
    measure_node_lines,
    recommend_mode,
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
    """Test AST-level parsing and detection of classes and functions."""

    def setUp(self) -> None:
        self.thresholds = AuditThresholds(
            warn_file_lines=350,
            max_file_lines=500,
            warn_class_methods=10,
            max_class_methods=12,
            max_func_lines=40,
        )

    def test_syntax_error_handled_gracefully(self) -> None:
        classes, funcs = analyze_python_ast("def broken_syntax(:", self.thresholds)
        self.assertEqual(classes, [])
        self.assertEqual(funcs, [])

    def test_null_bytes_handled_gracefully(self) -> None:
        classes, funcs = analyze_python_ast("def foo():\x00 pass", self.thresholds)
        self.assertEqual(classes, [])
        self.assertEqual(funcs, [])

    def test_class_method_count_and_status(self) -> None:
        method_defs = "\n".join(f"    def m_{i}(self): pass" for i in range(13))
        code = f"class LargeService:\n{method_defs}\n"
        classes, _ = analyze_python_ast(code, self.thresholds)
        self.assertEqual(len(classes), 1)
        self.assertEqual(classes[0].name, "LargeService")
        self.assertEqual(classes[0].method_count, 13)
        self.assertEqual(classes[0].status, "CRITICAL")

    def test_oversized_function_detection(self) -> None:
        # Create a function that spans 45 lines
        func_body = "\n".join("    x = 1" for _ in range(43))
        code = f"def giant_handler():\n{func_body}\n    return x\n"
        _, funcs = analyze_python_ast(code, self.thresholds)
        self.assertEqual(len(funcs), 1)
        self.assertEqual(funcs[0].name, "giant_handler")
        self.assertEqual(funcs[0].status, "CRITICAL")

    def test_nested_standalone_function_detection(self) -> None:
        func_body = "\n".join("        x = 1" for _ in range(43))
        code = f"if True:\n    def nested_func():\n{func_body}\n        return x\n"
        _, funcs = analyze_python_ast(code, self.thresholds)
        self.assertEqual(len(funcs), 1)
        self.assertEqual(funcs[0].name, "nested_func")
        self.assertEqual(funcs[0].status, "CRITICAL")


class TestSourceFileAudit(unittest.TestCase):
    """Test filesystem iteration, line counting, and audit aggregation."""

    def test_iter_source_files_ignores_unwanted_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "src").mkdir()
            (base / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
            (base / "node_modules").mkdir()
            (base / "node_modules" / "bad.js").write_text("const x = 1;", encoding="utf-8")
            (base / ".venv").mkdir()
            (base / ".venv" / "lib.py").write_text("import os", encoding="utf-8")

            found = list(iter_source_files(base))
            rel_found = [p.relative_to(base).as_posix() for p in found]
            self.assertIn("src/main.py", rel_found)
            self.assertNotIn("node_modules/bad.js", rel_found)
            self.assertNotIn(".venv/lib.py", rel_found)

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


class TestCliExecution(unittest.TestCase):
    """Test CLI argument parsing and exit codes."""

    def test_missing_path_returns_code_2(self) -> None:
        with patch("sys.stderr", new_callable=io.StringIO):
            code = main(["--path", "non_existent_directory_xyz_123"])
            self.assertEqual(code, 2)

    def test_clean_directory_strict_returns_code_0(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "clean.py"
            f.write_text("def hello(): return 'world'\n", encoding="utf-8")
            with patch("sys.stdout", new_callable=io.StringIO):
                code = main(["--path", tmpdir, "--strict"])
                self.assertEqual(code, 0)

    def test_breached_directory_strict_returns_code_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "huge.py"
            # Write 505 lines to trigger CRITICAL file status
            f.write_text("\n".join(f"x_{i} = {i}" for i in range(505)), encoding="utf-8")
            with patch("sys.stdout", new_callable=io.StringIO):
                code = main(["--path", tmpdir, "--strict"])
                self.assertEqual(code, 1)

    def test_json_flag_emits_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.py"
            f.write_text("val = 42\n", encoding="utf-8")
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                code = main(["--path", tmpdir, "--json"])
                self.assertEqual(code, 0)
                data = json.loads(mock_stdout.getvalue())
                self.assertIn("total_files", data)
                self.assertIn("hard_breach", data)
                self.assertEqual(data.get("recommended_mode"), "SINGLE_FILE")
                self.assertIn("files", data)

    def test_recommend_mode_switches_to_project_campaign(self) -> None:
        reports = [
            FileReport(f"m{i}.py", 600, "CRITICAL") for i in range(3)
        ]
        self.assertEqual(recommend_mode(reports), "PROJECT_CAMPAIGN")
        self.assertEqual(recommend_mode(reports[:2]), "SINGLE_FILE")


if __name__ == "__main__":
    unittest.main()
