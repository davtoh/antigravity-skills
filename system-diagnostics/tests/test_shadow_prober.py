#!/usr/bin/env python3
"""Unit tests for Polyglot Shadow Prober (shadow_prober.py)."""

import ast
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from shadow_prober import (
    DefectFinding,
    PythonAstScanner,
    audit_hardcoded_secrets,
    audit_polyglot_lexer,
    compute_fingerprint,
    run_isolated_python_sandbox,
    scan_path,
)


class TestShadowProber(unittest.TestCase):
    """Test suite for polyglot AST, lexer, and sandbox probing."""

    def test_defect_finding_and_fingerprint(self):
        fp1 = compute_fingerprint("MUTABLE_DEFAULT_ARG", "foo.bar", "[]")
        fp2 = compute_fingerprint("MUTABLE_DEFAULT_ARG", "foo.bar", "[]")
        self.assertEqual(fp1, fp2)
        self.assertTrue(fp1.startswith("DEF-MUTABLE-"))

        finding = DefectFinding(
            id="DEFECT-001", fingerprint=fp1, rule_id="MUTABLE_DEFAULT_ARG",
            category="BAD_LOGIC", severity="HIGH", track="tactical",
            file="svc.py", line=10, symbol="foo", message="msg",
            suggested_fix="fix", status="quarantined"
        )
        d = finding.to_dict()
        self.assertEqual(d["id"], "DEFECT-001")
        self.assertEqual(d["track"], "tactical")

    def test_mutable_default_arg_detection(self):
        code = "def fn(items=[]):\n    pass\n"
        tree = ast.parse(code)
        scanner = PythonAstScanner("test.py", code)
        findings = scanner.scan(tree)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, "MUTABLE_DEFAULT_ARG")
        self.assertIn("items=[]", findings[0].message)
        self.assertEqual(findings[0].track, "tactical")

    def test_unreachable_code_detection(self):
        code = "def fn():\n    return 1\n    print('dead')\n"
        tree = ast.parse(code)
        scanner = PythonAstScanner("test.py", code)
        findings = scanner.scan(tree)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, "UNREACHABLE_CODE")
        self.assertIn("unreachable after 'return'", findings[0].message)

    def test_unhandled_async_coroutine(self):
        code = "async def fetch():\n    pass\ndef caller():\n    fetch()\n"
        tree = ast.parse(code)
        scanner = PythonAstScanner("test.py", code)
        findings = scanner.scan(tree)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, "UNHANDLED_ASYNC_COROUTINE")
        self.assertEqual(findings[0].track, "architectural")

    def test_call_arg_count_mismatch(self):
        code = "def target(a, b):\n    pass\ndef caller():\n    target(1)\n"
        tree = ast.parse(code)
        scanner = PythonAstScanner("test.py", code)
        findings = scanner.scan(tree)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, "CALL_ARG_COUNT_MISMATCH")

    def test_missing_required_kwarg(self):
        code = "def target(*, required_key):\n    pass\ndef caller():\n    target()\n"
        tree = ast.parse(code)
        scanner = PythonAstScanner("test.py", code)
        findings = scanner.scan(tree)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, "MISSING_REQUIRED_KWARG")

    def test_unsafe_eval_exec(self):
        code = "def run(x):\n    eval(x)\n"
        tree = ast.parse(code)
        scanner = PythonAstScanner("test.py", code)
        findings = scanner.scan(tree)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, "UNSAFE_EVAL_EXEC")
        self.assertEqual(findings[0].track, "architectural")

    def test_silent_except_and_overbroad(self):
        code = "try:\n    pass\nexcept:\n    pass\ntry:\n    pass\nexcept BaseException:\n    pass\n"
        tree = ast.parse(code)
        scanner = PythonAstScanner("test.py", code)
        findings = scanner.scan(tree)
        self.assertEqual(len(findings), 2)
        rules = {f.rule_id for f in findings}
        self.assertIn("SILENT_BARE_EXCEPT", rules)
        self.assertIn("OVERBROAD_SHADOW_CATCH", rules)

    def test_hardcoded_secrets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "config.py"
            f.write_text('API_KEY = "sk_live_1234567890abcdef1234"\n', encoding="utf-8")
            findings = audit_hardcoded_secrets(f, "config.py", f.read_text(encoding="utf-8"))
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].rule_id, "HARDCODED_SECRET_PATTERN")

            # Test files are excluded
            test_f = Path(tmpdir) / "test_config.py"
            test_f.write_text('API_KEY = "sk_live_1234567890abcdef1234"\n', encoding="utf-8")
            findings_test = audit_hardcoded_secrets(test_f, "tests/test_config.py", test_f.read_text(encoding="utf-8"))
            self.assertEqual(len(findings_test), 0)

    def test_polyglot_lexer_js_css_dart(self):
        # JS eval and catch
        js_code = "eval(userInput);\ntry { doSomething(); } catch (e) {}\n"
        js_findings = audit_polyglot_lexer(Path("app.js"), "app.js", js_code)
        self.assertEqual(len(js_findings), 2)

        # Dart catch
        dart_code = "try { load(); } catch (e) {}\n"
        dart_findings = audit_polyglot_lexer(Path("main.dart"), "main.dart", dart_code)
        self.assertEqual(len(dart_findings), 1)

        # CSS !important
        css_code = ".btn { color: red !important; }\n"
        css_findings = audit_polyglot_lexer(Path("style.css"), "style.css", css_code, deep=True)
        self.assertEqual(len(css_findings), 1)
        self.assertEqual(css_findings[0].rule_id, "CSS_IMPORTANT_OVERRUN")

    def test_scan_path_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            (p / "service.py").write_text("def run(items=[]):\n    return 1\n    x = 2\n", encoding="utf-8")
            (p / "app.js").write_text("eval('foo');\n", encoding="utf-8")
            results = scan_path(p)
            self.assertGreaterEqual(len(results), 3)
            self.assertEqual(results[0].id, "DEFECT-001")
            self.assertEqual(results[1].id, "DEFECT-002")


if __name__ == "__main__":
    unittest.main()
