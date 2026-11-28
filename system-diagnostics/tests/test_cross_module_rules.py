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

    def test_callable_signature_drift_inside_try_except(self):
        svc_src = (
            "class ConfidenceEngine:\n"
            "    def record_human_feedback(self, entity_id, decision, camera_id=None):\n"
            "        return (entity_id, decision, camera_id)\n"
        )
        caller_src = (
            "def apply_fb(ce: ConfidenceEngine):\n"
            "    try:\n"
            "        ce.record_human_feedback(1, 'confirm', bogus_kw=True)\n"
            "    except Exception:\n"
            "        pass\n"
            "    try:\n"
            "        ce.record_human_feedback(1, 'reject', camera_id='cam_1')\n"
            "    except Exception:\n"
            "        pass\n"
        )
        findings = scan_cross_module_defects([("ce.py", ast.parse(svc_src)), ("caller.py", ast.parse(caller_src))])
        drift = [d for d in findings if d["rule_id"] == "CALLABLE_SIGNATURE_DRIFT"]
        self.assertEqual(len(drift), 1)
        self.assertEqual(drift[0]["line"], 3)

    def test_audit_layout_js_has_empty_src_and_squeezed_modal_checks(self):
        js = (SCRIPTS_DIR / "audit_layout.js").read_text(encoding="utf-8")
        self.assertIn("squeezedControlWarnings", js)
        self.assertIn(".data-table", js)
        self.assertIn("empty or missing src", js)
        self.assertIn("offsetParent === null", js)

    def test_silent_shape_skip_ast_rule(self):
        src = (
            "def match(items, log):\n"
            "    for x in items:\n"
            "        if x.shape[0] != 512:\n"
            "            continue\n"
            "    for y in items:\n"
            "        if y.ndim != 2:\n"
            "            log.warning('dim mismatch')\n"
            "            continue\n"
        )
        findings = scan_cross_module_defects([("reid.py", ast.parse(src))])
        skips = [d for d in findings if d["rule_id"] == "SILENT_SHAPE_SKIP"]
        self.assertEqual(len(skips), 1)
        self.assertEqual(skips[0]["line"], 3)

    def test_silent_shape_skip_elif_and_raise_edges(self):
        src = (
            "def check(batch):\n"
            "    for item in batch:\n"
            "        if item is None:\n"
            "            continue\n"
            "        elif len(item) < 3:\n"
            "            continue\n"
            "    for item in batch:\n"
            "        if item.shape[0] == 0:\n"
            "            raise ValueError('empty')\n"
        )
        findings = scan_cross_module_defects([("pipe.py", ast.parse(src))])
        skips = [d for d in findings if d["rule_id"] == "SILENT_SHAPE_SKIP"]
        self.assertEqual(len(skips), 1)
        self.assertEqual(skips[0]["line"], 5)

    def test_method_kwarg_mismatch_catches_dbg01_and_allows_valid_or_kwargs(self):
        handoff_src = (
            "class MultiCameraHandoffCoordinator:\n"
            "    def record_zone_exit(self, camera_id, zone_id, entity_id, timestamp=None):\n"
            "        return (camera_id, zone_id, entity_id, timestamp)\n"
            "class FlexibleService:\n"
            "    def emit_custom(self, name, **kwargs):\n"
            "        return (name, kwargs)\n"
        )
        caller_src = (
            "def on_exit(handoff, flex: FlexibleService, mock_handoff):\n"
            "    handoff.record_zone_exit('cam_1', 'z1', 'e1', track_id=42)\n"
            "    handoff.record_zone_exit('cam_1', 'z1', 'e1', timestamp=1.0)\n"
            "    flex.emit_custom('ev', arbitrary_flag=True)\n"
            "    mock_handoff.record_zone_exit('cam_1', 'z1', 'e1', track_id=42)\n"
        )
        findings = scan_cross_module_defects([
            ("handoff.py", ast.parse(handoff_src)),
            ("governance.py", ast.parse(caller_src)),
        ])
        mismatches = [d for d in findings if d["rule_id"] == "METHOD_KWARG_MISMATCH"]
        self.assertEqual(len(mismatches), 1)
        self.assertEqual(mismatches[0]["line"], 2)
        self.assertIn("track_id", mismatches[0]["message"])

    def test_method_kwarg_mismatch_resolved_receiver_and_preserves_try_drift(self):
        svc_src = (
            "class Handoff:\n"
            "    def notify_peer(self, camera_id, zone_id):\n"
            "        return (camera_id, zone_id)\n"
            "class Other:\n"
            "    def notify_peer(self, camera_id, extra=None):\n"
            "        return (camera_id, extra)\n"
        )
        caller_src = (
            "def run(h: Handoff):\n"
            "    h.notify_peer('cam_1', extra=1)\n"
            "    try:\n"
            "        h.notify_peer('cam_1', bogus=2)\n"
            "    except Exception:\n"
            "        pass\n"
        )
        findings = scan_cross_module_defects([
            ("svc.py", ast.parse(svc_src)),
            ("caller.py", ast.parse(caller_src)),
        ])
        kw_lines = {d["line"] for d in findings if d["rule_id"] == "METHOD_KWARG_MISMATCH"}
        try_lines = {d["line"] for d in findings if d["rule_id"] == "CALLABLE_SIGNATURE_DRIFT"}
        self.assertEqual(kw_lines, {2, 4})
        self.assertEqual(try_lines, {4})
