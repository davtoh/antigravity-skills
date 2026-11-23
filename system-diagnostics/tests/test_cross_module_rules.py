#!/usr/bin/env python3
"""Unit tests for cross_module_rules, audit_layout.js extensions, and trace_cli."""

import argparse
import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from cross_module_rules import scan_cross_module_defects
import trace_recorder


class TestCrossModuleAndDiagnosticsUpgrades(unittest.TestCase):
    """Tests for cross-module AST rules, audit_layout.js, and trace_recorder isolation."""

    def test_cross_module_missing_attr_and_clock_taint(self):
        a_src = (
            "import time\n"
            "class AnalyticsEngine:\n"
            "    def draw_zones(self): pass\n"
            "def get_mono():\n"
            "    return time.monotonic()\n"
        )
        b_src = (
            "import time\n"
            "def run(eng: AnalyticsEngine):\n"
            "    eng.draw_heatmap_overlay()\n"
            "    t = get_mono()\n"
            "    return time.time() - t\n"
        )
        parsed = [("a.py", ast.parse(a_src)), ("b.py", ast.parse(b_src))]
        rules = {d["rule_id"] for d in scan_cross_module_defects(parsed)}
        self.assertIn("CROSS_MODULE_MISSING_ATTR", rules)
        self.assertIn("CROSS_MODULE_CLOCK_TAINT", rules)

    def test_lock_order_inversion_detection(self):
        src = (
            "def fn1():\n"
            "    with lock_a:\n"
            "        with lock_b:\n"
            "            pass\n"
            "def fn2():\n"
            "    with lock_b:\n"
            "        with lock_a:\n"
            "            pass\n"
        )
        findings = scan_cross_module_defects([("locks.py", ast.parse(src))])
        self.assertTrue(any(d["rule_id"] == "LOCK_ORDER_INVERSION" for d in findings))

    def test_audit_layout_js_has_stability_flush_and_dupe_checks(self):
        js = (SCRIPTS_DIR / "audit_layout.js").read_text(encoding="utf-8")
        self.assertIn("layoutJitterWarnings", js)
        self.assertIn("flushControlWarnings", js)
        self.assertIn("duplicateControlWarnings", js)
        self.assertIn("brokenImageWarnings", js)
        self.assertIn("__FRONTIER_STABILITY_MS__", js)

    def test_repo_missing_rollback_ast_rule(self):
        bad_repo = (
            "class BadRepo:\n"
            "    def write(self, val):\n"
            "        self._conn.execute('INSERT INTO t VALUES (?)', (val,))\n"
            "        self._conn.commit()\n"
        )
        good_repo = (
            "class GoodRepo:\n"
            "    def write(self, val):\n"
            "        try:\n"
            "            self._conn.execute('INSERT INTO t VALUES (?)', (val,))\n"
            "            self._conn.commit()\n"
            "        except Exception:\n"
            "            self._conn.rollback()\n"
            "            raise\n"
        )
        bad_rules = {d["rule_id"] for d in scan_cross_module_defects([("foo_repo.py", ast.parse(bad_repo))])}
        good_rules = {d["rule_id"] for d in scan_cross_module_defects([("bar_repo.py", ast.parse(good_repo))])}
        self.assertIn("REPO_MISSING_ROLLBACK", bad_rules)
        self.assertNotIn("REPO_MISSING_ROLLBACK", good_rules)

    def test_trace_recorder_skips_unittest_by_default_and_resolves_id(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DIAGNOSTICS_TRACE_IN_TESTS", None)
            self.assertFalse(trace_recorder.install_trace_recorder())
            res = trace_recorder.record_exception(ValueError("ignored"))
            self.assertTrue(res.get("skipped"))
        with tempfile.TemporaryDirectory() as tmp:
            mgr = trace_recorder.TraceCatalogManager(Path(tmp))
            issue = mgr.record_trace({
                "fingerprint": "TRC-VAL-111111", "timestamp": "2026-11-21T00:00:00Z",
                "severity": "ERROR", "exception_type": "ValueError", "message": "bad",
                "culprit_file": "x.py", "culprit_line": 1, "culprit_func": "f",
                "traceback": [], "environment": {}, "context": {},
            })
            rc = trace_recorder.cmd_traces(argparse.Namespace(path=tmp, action="resolve", issue_id=issue["id"], scaffold=None))
            self.assertEqual(rc, 0)
            self.assertEqual(mgr.load_catalog()["issues"][0]["status"], "resolved")
