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

    def test_baseexception_cleanup_and_bare_reraise_is_not_flagged(self):
        code = "try:\n    pass\nexcept BaseException:\n    cleanup()\n    raise\n"
        findings = PythonAstScanner("test.py", code).scan(ast.parse(code))
        self.assertNotIn("OVERBROAD_SHADOW_CATCH", {f.rule_id for f in findings})

    def test_baseexception_swallowed_or_wrapped_still_flagged(self):
        for tail in ("    pass\n", "    raise RuntimeError('x')\n"):
            code = "try:\n    pass\nexcept BaseException:\n" + tail
            findings = PythonAstScanner("test.py", code).scan(ast.parse(code))
            self.assertIn("OVERBROAD_SHADOW_CATCH", {f.rule_id for f in findings})

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

    def test_instance_and_class_method_self_cls_bound_zero_false_positives(self):
        code = (
            "class CameraPool:\n"
            "    def load_cameras(self):\n"
            "        pass\n"
            "    def remove_camera(self, cam_id):\n"
            "        pass\n"
            "    @classmethod\n"
            "    def from_config(cls, cfg):\n"
            "        return cls()\n"
            "    @staticmethod\n"
            "    def compute_hash(a, b):\n"
            "        return a + b\n"
            "    @property\n"
            "    def primary(self):\n"
            "        return None\n"
            "    def run(self):\n"
            "        self.load_cameras()\n"
            "        self.remove_camera('cam_1')\n"
            "        self.from_config({})\n"
            "        self.compute_hash(1, 2)\n"
            "        self.remove_camera()\n"  # Genuine missing arg on self method
            "        self.compute_hash(1)\n"  # Genuine missing arg on staticmethod
        )
        tree = ast.parse(code)
        findings = PythonAstScanner("pool.py", code).scan(tree)
        self.assertEqual(len(findings), 2)
        self.assertEqual(findings[0].symbol, "remove_camera")
        self.assertEqual(findings[1].symbol, "compute_hash")

    def test_positional_or_keyword_and_starred_unpacking(self):
        code = (
            "def configure(host, port, timeout=5.0):\n"
            "    pass\n"
            "def caller(args, kwargs):\n"
            "    configure('localhost', port=8080)\n"
            "    configure(host='localhost', port=8080)\n"
            "    configure(*args)\n"
            "    configure(**kwargs)\n"
        )
        tree = ast.parse(code)
        findings = PythonAstScanner("cfg.py", code).scan(tree)
        self.assertEqual(len(findings), 0)

    def test_arbitrary_receiver_does_not_collide_with_module_async_or_arity(self):
        code = (
            "async def add_camera(req):\n"
            "    pool = get_pool()\n"
            "    pool.add_camera(req.id, req.name, req.source)\n"
        )
        tree = ast.parse(code)
        findings = PythonAstScanner("routers/cameras.py", code).scan(tree)
        self.assertEqual(len(findings), 0)

    def test_mixed_clock_domain_flagged_in_same_func_and_timing_module(self):
        same_fn = "import time\ndef step():\n    a = time.monotonic()\n    b = time.time()\n"
        f1 = PythonAstScanner("service.py", same_fn).scan(ast.parse(same_fn))
        self.assertEqual([x.rule_id for x in f1], ["MIXED_CLOCK_DOMAIN"])

        worker_mod = "import time\ndef a(): return time.monotonic()\ndef b(): return time.time()\n"
        f2 = PythonAstScanner("video/capture_worker.py", worker_mod).scan(ast.parse(worker_mod))
        self.assertEqual([x.rule_id for x in f2], ["MIXED_CLOCK_DOMAIN"])

        unrelated = "import time\ndef a(): return time.monotonic()\ndef b(): return time.time()\n"
        f3 = PythonAstScanner("utils/helper.py", unrelated).scan(ast.parse(unrelated))
        self.assertEqual(f3, [])

        aliased = (
            "from time import time as wall_time, monotonic as mono\n"
            "def f1(): return wall_time() - mono()\n"
            "def f2(): return wall_time() - mono()\n"
        )
        f4 = PythonAstScanner("service.py", aliased).scan(ast.parse(aliased))
        self.assertEqual(len(f4), 2)
        self.assertTrue(all(x.rule_id == "MIXED_CLOCK_DOMAIN" for x in f4))

    def test_cross_module_exempts_wall_helpers_dynamic_bases_store_attrs_and_subclasses(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            (ws / "worker.py").write_text(
                "import time\n"
                "def _wall_now():\n"
                "    return time.time()\n"
                "def step():\n"
                "    return time.monotonic(), _wall_now()\n",
                encoding="utf-8",
            )
            (ws / "types.py").write_text(
                "import ctypes\n"
                "class BaseEvent:\n"
                "    camera_id = 'c1'\n"
                "class ZoneEvent(BaseEvent):\n"
                "    zone_id = 'z1'\n"
                "class Track:\n"
                "    track_id = 1\n"
                "class LimitInfo(ctypes.Structure):\n"
                "    pass\n",
                encoding="utf-8",
            )
            (ws / "consumer.py").write_text(
                "from types import BaseEvent, Track, LimitInfo\n"
                "def attach(t: Track, ev: BaseEvent, info: LimitInfo):\n"
                "    t.reid_score = 0.9\n"
                "    return t.reid_score, ev.zone_id, info.BasicLimitInformation\n",
                encoding="utf-8",
            )
            findings = scan_path(ws)
            rules = {f.rule_id for f in findings}
            self.assertNotIn("MIXED_CLOCK_DOMAIN", rules)
            self.assertNotIn("CROSS_MODULE_MISSING_ATTR", rules)


if __name__ == "__main__":
    unittest.main()
