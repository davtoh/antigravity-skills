#!/usr/bin/env python3
"""Unit tests for JavaScript runtime AST/lexer guard rules (js_guard_rules.py)."""

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from js_guard_rules import scan_js_runtime_guards
from shadow_prober import scan_path


class TestJsGuardRules(unittest.TestCase):
    """Verify JS_RAF_DPR_RESIZE, JS_HOT_EVENT_LOCALSTORAGE, and JS_PRIVATE_SWITCH_TAB_BINDING."""

    def test_raf_sync_canvas_dpr_detected_and_clean_ignored(self):
        bad = (
            "function tick() {\n"
            "  requestAnimationFrame(() => {\n"
            "    UnifiedCanvasOverlay.syncCanvasDpr(canvas, w, h);\n"
            "    draw();\n"
            "  });\n"
            "}\n"
        )
        good = (
            "new ResizeObserver(() => {\n"
            "  UnifiedCanvasOverlay.syncCanvasDpr(canvas, w, h);\n"
            "}).observe(video);\n"
            "requestAnimationFrame(() => { draw(); });\n"
            "// requestAnimationFrame(() => syncCanvasDpr(c));\n"
        )
        bad_findings = scan_js_runtime_guards("bad.js", bad)
        self.assertEqual([f["rule_id"] for f in bad_findings], ["JS_RAF_DPR_RESIZE"])
        self.assertEqual(bad_findings[0]["line"], 3)
        self.assertEqual(scan_js_runtime_guards("good.js", good), [])

    def test_timeupdate_localstorage_detected_and_debounced_allowed(self):
        bad = (
            "video.addEventListener('timeupdate', () => {\n"
            "  localStorage.setItem('pos', String(video.currentTime));\n"
            "});\n"
        )
        good = (
            "video.addEventListener('timeupdate', () => {\n"
            "  clearTimeout(saveTimer);\n"
            "  saveTimer = setTimeout(() => {\n"
            "    localStorage.setItem('pos', String(video.currentTime));\n"
            "  }, 500);\n"
            "});\n"
        )
        bad_findings = scan_js_runtime_guards("bad.js", bad)
        self.assertEqual([f["rule_id"] for f in bad_findings], ["JS_HOT_EVENT_LOCALSTORAGE"])
        self.assertEqual(bad_findings[0]["line"], 2)
        self.assertEqual(scan_js_runtime_guards("good.js", good), [])

    def test_private_switch_tab_binding_detected_and_window_wrapper_allowed(self):
        bad = (
            "navTabs.forEach((tab) => {\n"
            "  tab.addEventListener('click', () => switchTab(tab.getAttribute('data-tab')));\n"
            "});\n"
        )
        good = (
            "navTabs.forEach((tab) => {\n"
            "  tab.addEventListener('click', () => window.switchTab(tab.getAttribute('data-tab')));\n"
            "});\n"
        )
        bad_findings = scan_js_runtime_guards("bad.js", bad)
        self.assertEqual([f["rule_id"] for f in bad_findings], ["JS_PRIVATE_SWITCH_TAB_BINDING"])
        self.assertEqual(bad_findings[0]["line"], 2)
        self.assertEqual(scan_js_runtime_guards("good.js", good), [])

    def test_shadow_prober_scan_path_includes_js_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            js_file = Path(tmp) / "player.js"
            js_file.write_text(
                "requestAnimationFrame(() => {\n  syncCanvasDpr(canvas);\n});\n",
                encoding="utf-8",
            )
            findings = scan_path(Path(tmp))
            rule_ids = [d.rule_id for d in findings]
            self.assertIn("JS_RAF_DPR_RESIZE", rule_ids)


if __name__ == "__main__":
    unittest.main()
