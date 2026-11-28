#!/usr/bin/env python3
"""
Unit tests for scripts/cdp_inspect.py discovery, argument helpers, target selection, and evaluation.
"""

import argparse
import asyncio
import base64
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import cdp_inspect  # noqa: E402


class TestCDPDiscoveryAndHelpers(unittest.TestCase):
    """Tests for Chrome discovery, viewport/eval parsing, JS builders, and runtime helpers."""

    def test_chrome_executable_env_override(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tf:
            mock_chrome = tf.name

        try:
            with patch.dict(os.environ, {"CHROME_BIN": mock_chrome}):
                found = cdp_inspect.find_chrome_executable()
                self.assertEqual(found, mock_chrome)
        finally:
            if os.path.exists(mock_chrome):
                os.remove(mock_chrome)

    def test_find_chrome_executable_platforms(self):
        with patch.dict(os.environ, {"CHROME_BIN": "", "CHROME_PATH": ""}):
            with patch("platform.system", return_value="Windows"), \
                 patch("os.path.exists", side_effect=lambda p: "chrome.exe" in str(p)):
                res_win = cdp_inspect.find_chrome_executable()
                self.assertIn("chrome.exe", res_win)

            with patch("platform.system", return_value="Darwin"), \
                 patch("os.path.exists", side_effect=lambda p: "Google Chrome.app" in str(p)):
                res_mac = cdp_inspect.find_chrome_executable()
                self.assertIn("Google Chrome", res_mac)

            with patch("platform.system", return_value="Linux"), \
                 patch("shutil.which", side_effect=lambda name: f"/usr/bin/{name}" if name == "chromium" else None):
                res_linux = cdp_inspect.find_chrome_executable()
                self.assertEqual(res_linux, "/usr/bin/chromium")

    def test_find_devtools_active_port_file(self):
        with tempfile.TemporaryDirectory() as td:
            port_file = Path(td) / "DevToolsActivePort"
            port_file.write_text("9222\n/devtools/browser/abc-123\n", encoding="utf-8")

            with patch("platform.system", return_value="Linux"), \
                 patch.dict(os.environ, {"XDG_CONFIG_HOME": td}):
                with patch("pathlib.Path.exists", return_value=True), \
                     patch("pathlib.Path.read_text", return_value="9222\n/devtools/browser/abc-123\n"):
                    res = cdp_inspect.find_devtools_active_port()
                    self.assertIsNotNone(res)
                    self.assertEqual(res, (9222, "/devtools/browser/abc-123"))

    def test_find_devtools_active_port_missing_returns_none(self):
        with patch("pathlib.Path.exists", return_value=False):
            self.assertIsNone(cdp_inspect.find_devtools_active_port())

    def test_parse_viewport_valid_and_invalid(self):
        self.assertEqual(cdp_inspect.parse_viewport("1920x1080"), (1920, 1080))
        self.assertEqual(cdp_inspect.parse_viewport("800x600"), (800, 600))
        with self.assertRaises(argparse.ArgumentTypeError):
            cdp_inspect.parse_viewport("invalid-size")

    def test_build_generic_audit_js(self):
        js = cdp_inspect.build_generic_audit_js([".video-container", "#header"])
        self.assertIn(".video-container", js)
        self.assertIn("#header", js)
        self.assertIn("window.__FRONTIER_SELECTORS__", js)
        self.assertIn("sanitizeSrc", js)

    def test_resolve_eval_file_arg(self):
        parser = cdp_inspect.build_parser()
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tf:
            tf.write("(() => ({ ok: 1 }))()")
            tf_path = tf.name
        try:
            args = parser.parse_args(["--eval-file", tf_path])
            cdp_inspect._resolve_eval_arg(parser, args)
            self.assertEqual(args.eval, "(() => ({ ok: 1 }))()")
            self.assertIsNone(args.capture_runtime)
            args_off = parser.parse_args(["--eval-file", tf_path, "--no-capture-runtime"])
            self.assertFalse(args_off.capture_runtime)
        finally:
            os.remove(tf_path)

    def test_audit_layout_js_contains_text_overflow_detector(self):
        js = cdp_inspect.build_generic_audit_js([])
        self.assertIn("button, a, .badge, .menuitem, .video-action-menu", js)
        self.assertIn("el.scrollWidth > el.clientWidth + 2", js)
        self.assertIn("Horizontal text overflow detected", js)
        self.assertIn("verifyDataSvgImages", js)
        self.assertIn("checkFlexChildBoxOverflow", js)
        self.assertIn("checkCanvasLuminance", js)

    def test_multi_viewport_audit_960_1280_1920(self):
        parser = cdp_inspect.build_parser()
        args = parser.parse_args(["--audit-layout", "--viewports", "960x720,1280x800,1920x1080"])
        fake_cdp = MagicMock()
        fake_cdp.send = AsyncMock(return_value={"result": {"value": {"layoutOverflowWarnings": [], "viewport": {"hasHorizontalWindowScroll": False}}}})
        rc = asyncio.run(cdp_inspect.run_against_target(fake_cdp, "sess-1", args))
        self.assertEqual(rc, 0)
        override_calls = [c for c in fake_cdp.send.await_args_list if c.args and c.args[0] == "Emulation.setDeviceMetricsOverride"]
        self.assertEqual([c.args[1]["width"] for c in override_calls], [960, 1280, 1920])

        # Edge cases: empty/None viewports list and --strict failing when any viewport overflows
        import cdp_viewport
        self.assertEqual(cdp_viewport.parse_viewports_list(None), [])
        self.assertEqual(cdp_viewport.parse_viewports_list(" , "), [])
        strict_args = parser.parse_args(["--audit-layout", "--viewports", "960x720", "--strict"])
        fake_cdp.send = AsyncMock(return_value={"result": {"value": {"layoutOverflowWarnings": [{"selector": "#x"}], "viewport": {"hasHorizontalWindowScroll": False}}}})
        self.assertEqual(asyncio.run(cdp_inspect.run_against_target(fake_cdp, "sess-1", strict_args)), 1)

    def test_urls_match_localhost_and_summarize_cdp_events(self):
        import cdp_runtime
        self.assertTrue(cdp_runtime.urls_match("http://localhost:8000", "http://127.0.0.1:8000/#videos"))
        self.assertFalse(cdp_runtime.urls_match("http://localhost:8000", "http://127.0.0.1:3000/"))
        summary = cdp_runtime.summarize_cdp_events([
            {"method": "Runtime.consoleAPICalled", "params": {"type": "error", "args": [{"value": "boom"}]}},
            {"method": "Runtime.exceptionThrown", "params": {"exceptionDetails": {"text": "Uncaught TypeError"}}},
            {"method": "Network.responseReceived", "params": {"response": {"url": "http://localhost:8000/api/404", "status": 404}}},
        ])
        self.assertEqual(summary["consoleErrors"], ["boom"])
        self.assertEqual(summary["exceptions"], ["Uncaught TypeError"])
        self.assertEqual(summary["networkErrors"][0]["status"], 404)

    def test_run_against_target_auto_enables_capture_runtime_for_eval(self):
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        parser = cdp_inspect.build_parser()
        fake_cdp = MagicMock()
        fake_cdp.send = AsyncMock(return_value={"result": {"value": {"ok": 1}}})

        args_default = parser.parse_args(["--eval", "(() => ({ ok: 1 }))()"])
        with patch.object(cdp_inspect, "enable_runtime_capture", new=AsyncMock()) as mock_en, \
             patch.object(cdp_inspect, "collect_runtime_report", new=AsyncMock(return_value={"consoleErrors": []})):
            rc = asyncio.run(cdp_inspect.run_against_target(fake_cdp, "sess-1", args_default))
        self.assertEqual(rc, 0)
        mock_en.assert_awaited_once()

        args_off = parser.parse_args(["--eval", "(() => ({ ok: 1 }))()", "--no-capture-runtime"])
        with patch.object(cdp_inspect, "enable_runtime_capture", new=AsyncMock()) as mock_en_off:
            rc_off = asyncio.run(cdp_inspect.run_against_target(fake_cdp, "sess-1", args_off))
        self.assertEqual(rc_off, 0)
        mock_en_off.assert_not_called()


class TestCDPTargetAndEval(unittest.TestCase):
    """Tests for CDP target selection, port-file polling, and page evaluation."""

    def test_evaluate_success_and_exception(self):
        async def _test():
            mock_cdp = MagicMock()
            mock_cdp.send = AsyncMock()

            mock_cdp.send.return_value = {"result": {"value": {"title": "App"}}}
            res = await cdp_inspect.evaluate(mock_cdp, "sess-1", "document.title")
            self.assertEqual(res, {"title": "App"})

            mock_cdp.send.return_value = {
                "exceptionDetails": {
                    "text": "Uncaught ReferenceError: missingVar is not defined",
                    "exception": {"description": "ReferenceError: missingVar is not defined\n at line 1"},
                }
            }
            res_err = await cdp_inspect.evaluate(mock_cdp, "sess-1", "missingVar")
            self.assertIn("jsException", res_err)
            self.assertIn("missingVar is not defined", res_err["jsException"])

        asyncio.run(_test())

    def test_pick_page_target_scenarios(self):
        async def _test():
            mock_cdp = MagicMock()
            mock_cdp.send = AsyncMock()

            targets_data = {
                "targetInfos": [
                    {"type": "page", "url": "chrome://newtab", "targetId": "TAB-CHROME"},
                    {"type": "page", "url": "http://localhost:3000/dashboard", "title": "Dashboard", "targetId": "TAB-1"},
                    {"type": "page", "url": "http://localhost:8080/app", "title": "App", "targetId": "TAB-2"},
                ]
            }
            mock_cdp.send.return_value = targets_data
            self.assertEqual(await cdp_inspect.pick_page_target(mock_cdp, "http://localhost:3000"), "TAB-1")

            mock_cdp.send.side_effect = [targets_data, {"targetId": "TAB-NEW"}]
            self.assertEqual(await cdp_inspect.pick_page_target(mock_cdp, "http://example.com"), "TAB-NEW")

            mock_cdp.send.side_effect = None
            mock_cdp.send.return_value = targets_data
            self.assertEqual(await cdp_inspect.pick_page_target(mock_cdp, ""), "TAB-1")

            mock_cdp.send.return_value = {"targetInfos": [{"type": "page", "url": "chrome://settings"}]}
            with self.assertRaises(RuntimeError):
                await cdp_inspect.pick_page_target(mock_cdp, "")

        asyncio.run(_test())

    def test_read_port_file_timeout_and_success(self):
        async def _test():
            with tempfile.TemporaryDirectory() as td:
                pdir = Path(td)
                self.assertIsNone(await cdp_inspect.read_port_file(pdir, timeout_s=0.1))

                (pdir / "DevToolsActivePort").write_text("12345\n/ws-path\n", encoding="utf-8")
                self.assertEqual(await cdp_inspect.read_port_file(pdir, timeout_s=1.0), (12345, "/ws-path"))

        asyncio.run(_test())

    def _run_target_args(self, screenshot_path: str) -> argparse.Namespace:
        return argparse.Namespace(
            navigate=True,
            target_url="http://localhost:3000",
            wait=0.01,
            click="#btn",
            selectors="#app",
            audit_layout=True,
            strict=True,
            eval="1+1",
            screenshot=screenshot_path,
        )

    def test_run_against_target_success_and_screenshot(self):
        async def _test():
            mock_cdp = MagicMock()
            mock_cdp.send = AsyncMock(return_value={"data": base64.b64encode(b"fake-jpeg-data").decode("ascii")})
            with tempfile.TemporaryDirectory() as td:
                out_shot = Path(td) / "shot.jpg"
                args = self._run_target_args(str(out_shot))
                eval_responses = [
                    {"clicked": True},
                    {"viewport": {"hasHorizontalWindowScroll": False}, "layoutOverflowWarnings": []},
                    {"result": 2},
                ]
                with patch("cdp_inspect.evaluate", side_effect=eval_responses):
                    code = await cdp_inspect.run_against_target(mock_cdp, "sess-1", args)
                self.assertEqual(code, 0)
                self.assertTrue(out_shot.exists())
                self.assertEqual(out_shot.read_bytes(), b"fake-jpeg-data")

        asyncio.run(_test())

    def test_run_against_target_strict_and_js_exception(self):
        async def _test():
            mock_cdp = MagicMock()
            mock_cdp.send = AsyncMock(return_value={"data": base64.b64encode(b"fake-jpeg-data").decode("ascii")})
            with tempfile.TemporaryDirectory() as td:
                args = self._run_target_args(str(Path(td) / "shot.jpg"))
                warn_responses = [
                    {"clicked": True},
                    {"viewport": {"hasHorizontalWindowScroll": True}, "layoutOverflowWarnings": ["overflowed"]},
                    {"result": 2},
                ]
                with patch("cdp_inspect.evaluate", side_effect=warn_responses):
                    self.assertEqual(await cdp_inspect.run_against_target(mock_cdp, "sess-1", args), 1)

                err_responses = [
                    {"clicked": True},
                    {"viewport": {"hasHorizontalWindowScroll": False}},
                    {"jsException": "SyntaxError: Unexpected token"},
                ]
                with patch("cdp_inspect.evaluate", side_effect=err_responses):
                    self.assertEqual(await cdp_inspect.run_against_target(mock_cdp, "sess-1", args), 3)

        asyncio.run(_test())


if __name__ == "__main__":
    unittest.main()
