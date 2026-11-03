#!/usr/bin/env python3
"""
Unit tests for scripts/cdp_inspect.py.
Thorough coverage of Chrome DevTools Protocol inspection logic, CLI parsing,
page picking, layout audit generation, and headless/live browser lifecycles via mocks.
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

import cdp_inspect

class TestCDPInspect(unittest.TestCase):
    """Thorough unit tests for scripts/cdp_inspect.py."""

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
        # 1. Windows mock
        with patch("platform.system", return_value="Windows"), \
             patch("os.path.exists", side_effect=lambda p: "chrome.exe" in str(p)):
            res_win = cdp_inspect.find_chrome_executable()
            self.assertIn("chrome.exe", res_win)

        # 2. Darwin mock
        with patch("platform.system", return_value="Darwin"), \
             patch("os.path.exists", side_effect=lambda p: "Google Chrome.app" in str(p)):
            res_mac = cdp_inspect.find_chrome_executable()
            self.assertIn("Google Chrome", res_mac)

        # 3. Linux mock
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
                # Mock candidates to include our temp file
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

    def test_evaluate_success_and_exception(self):
        async def _test():
            mock_cdp = MagicMock()
            mock_cdp.send = AsyncMock()

            # 1. Success value
            mock_cdp.send.return_value = {"result": {"value": {"title": "App"}}}
            res = await cdp_inspect.evaluate(mock_cdp, "sess-1", "document.title")
            self.assertEqual(res, {"title": "App"})

            # 2. Exception details
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

            # 1. Matching target_url
            t1 = await cdp_inspect.pick_page_target(mock_cdp, "http://localhost:3000")
            self.assertEqual(t1, "TAB-1")

            # 2. Non-matching target_url -> calls Target.createTarget
            mock_cdp.send.side_effect = [
                targets_data,
                {"targetId": "TAB-NEW"},
            ]
            t2 = await cdp_inspect.pick_page_target(mock_cdp, "http://example.com")
            self.assertEqual(t2, "TAB-NEW")

            # 3. No target_url provided -> picks first non-internal tab
            mock_cdp.send.side_effect = None
            mock_cdp.send.return_value = targets_data
            t3 = await cdp_inspect.pick_page_target(mock_cdp, "")
            self.assertEqual(t3, "TAB-1")

            # 4. No candidate tabs available raises RuntimeError
            mock_cdp.send.return_value = {"targetInfos": [{"type": "page", "url": "chrome://settings"}]}
            with self.assertRaises(RuntimeError):
                await cdp_inspect.pick_page_target(mock_cdp, "")

        asyncio.run(_test())

    def test_read_port_file_timeout_and_success(self):
        async def _test():
            with tempfile.TemporaryDirectory() as td:
                pdir = Path(td)
                # Timeout case (file does not exist)
                res_none = await cdp_inspect.read_port_file(pdir, timeout_s=0.1)
                self.assertIsNone(res_none)

                # Success case
                (pdir / "DevToolsActivePort").write_text("12345\n/ws-path\n", encoding="utf-8")
                res_ok = await cdp_inspect.read_port_file(pdir, timeout_s=1.0)
                self.assertEqual(res_ok, (12345, "/ws-path"))

        asyncio.run(_test())

    def test_run_against_target_all_flags(self):
        async def _test():
            mock_cdp = MagicMock()
            mock_cdp.send = AsyncMock()

            # Mock screenshot capture
            screenshot_bytes = base64.b64encode(b"fake-jpeg-data").decode("ascii")
            mock_cdp.send.return_value = {"data": screenshot_bytes}

            with tempfile.TemporaryDirectory() as td:
                out_shot = Path(td) / "shot.jpg"
                args = argparse.Namespace(
                    navigate=True,
                    target_url="http://localhost:3000",
                    wait=0.01,
                    click="#btn",
                    selectors="#app",
                    audit_layout=True,
                    strict=True,
                    eval="1+1",
                    screenshot=str(out_shot),
                )

                eval_responses = [
                    {"clicked": True},  # for click
                    {"viewport": {"hasHorizontalWindowScroll": False}, "layoutOverflowWarnings": []},  # layout
                    {"result": 2},  # eval
                ]

                with patch("cdp_inspect.evaluate", side_effect=eval_responses):
                    code = await cdp_inspect.run_against_target(mock_cdp, "sess-1", args)
                    self.assertEqual(code, 0)
                    self.assertTrue(out_shot.exists())
                    self.assertEqual(out_shot.read_bytes(), b"fake-jpeg-data")

                # Test strict mode failure when warnings present
                eval_responses_warn = [
                    {"clicked": True},
                    {"viewport": {"hasHorizontalWindowScroll": True}, "layoutOverflowWarnings": ["overflowed"]},
                    {"result": 2},
                ]
                with patch("cdp_inspect.evaluate", side_effect=eval_responses_warn):
                    code_warn = await cdp_inspect.run_against_target(mock_cdp, "sess-1", args)
                    self.assertEqual(code_warn, 1)

                # Test jsException sets exit_code 3
                eval_responses_err = [
                    {"clicked": True},
                    {"viewport": {"hasHorizontalWindowScroll": False}},
                    {"jsException": "SyntaxError: Unexpected token"},
                ]
                with patch("cdp_inspect.evaluate", side_effect=eval_responses_err):
                    code_err = await cdp_inspect.run_against_target(mock_cdp, "sess-1", args)
                    self.assertEqual(code_err, 3)

        asyncio.run(_test())

    def test_attach_and_run_list_tabs(self):
        async def _test():
            mock_ws = AsyncMock()
            mock_cdp = MagicMock()
            mock_cdp.send = AsyncMock(return_value={"targetInfos": [{"type": "page", "title": "Tab"}]})

            args = argparse.Namespace(list_tabs=True)
            with patch("cdp_inspect.connect_ws", return_value=mock_ws), \
                 patch("cdp_inspect.CDPSession", return_value=mock_cdp):
                code = await cdp_inspect.attach_and_run("ws://localhost:9222", args)
                self.assertEqual(code, 0)

        asyncio.run(_test())

    def test_run_live_connection_fallbacks(self):
        async def _test():
            args = argparse.Namespace(fallback_headless=True)
            # 1. No active port returns None
            with patch("cdp_inspect.find_devtools_active_port", return_value=None):
                self.assertIsNone(await cdp_inspect.run_live(args))

            # 2. Port found but connection fails -> returns None when fallback_headless is True
            with patch("cdp_inspect.find_devtools_active_port", return_value=(9222, "/ws")), \
                 patch("cdp_inspect.attach_and_run", side_effect=ConnectionError("Refused")):
                self.assertIsNone(await cdp_inspect.run_live(args))

            # 3. Connection fails and fallback_headless is False -> returns 2
            args_no_fallback = argparse.Namespace(fallback_headless=False)
            with patch("cdp_inspect.find_devtools_active_port", return_value=(9222, "/ws")), \
                 patch("cdp_inspect.attach_and_run", side_effect=ConnectionError("Refused")):
                self.assertEqual(await cdp_inspect.run_live(args_no_fallback), 2)

        asyncio.run(_test())

    def test_run_headless_validation_and_launch(self):
        async def _test():
            # 1. Missing URL & not list_tabs returns 2
            args = argparse.Namespace(target_url="", list_tabs=False)
            self.assertEqual(await cdp_inspect.run_headless(args), 2)

            # 2. Chrome binary not found returns 1
            args_url = argparse.Namespace(target_url="http://localhost:3000", list_tabs=False, viewport=(1440, 900), port=0)
            with patch("cdp_inspect.find_chrome_executable", return_value="nonexistent_chrome_9999"), \
                 patch("os.path.exists", return_value=False), \
                 patch("shutil.which", return_value=None):
                self.assertEqual(await cdp_inspect.run_headless(args_url), 1)

            # 3. Successful launch and audit
            mock_proc = MagicMock()
            mock_proc.terminate = MagicMock()
            mock_proc.wait = MagicMock()

            with patch("cdp_inspect.find_chrome_executable", return_value="/usr/bin/google-chrome"), \
                 patch("os.path.exists", return_value=True), \
                 patch("subprocess.Popen", return_value=mock_proc), \
                 patch("cdp_inspect.read_port_file", return_value=(9555, "/devtools/browser/xyz")), \
                 patch("cdp_inspect.attach_and_run", return_value=0):
                res = await cdp_inspect.run_headless(args_url)
                self.assertEqual(res, 0)
                self.assertTrue(mock_proc.terminate.called)

        asyncio.run(_test())

    def test_main_async_routing(self):
        async def _test():
            args_headless = argparse.Namespace(headless=True)
            with patch("cdp_inspect.run_headless", return_value=0) as mock_hl:
                code = await cdp_inspect.main_async(args_headless)
                self.assertEqual(code, 0)
                mock_hl.assert_called_once()

            args_live = argparse.Namespace(headless=False)
            with patch("cdp_inspect.run_live", return_value=0) as mock_live:
                code_live = await cdp_inspect.main_async(args_live)
                self.assertEqual(code_live, 0)
                mock_live.assert_called_once()

        asyncio.run(_test())

    def test_attach_and_run_with_target_and_viewport(self):
        async def _test():
            mock_ws = AsyncMock()
            mock_cdp = MagicMock()
            mock_cdp.send = AsyncMock(side_effect=[
                {"targetInfos": [{"type": "page", "url": "http://localhost:3000", "targetId": "T1"}]},  # Target.getTargets
                {"sessionId": "S1"},  # Target.attachToTarget
                {},  # Emulation.setDeviceMetricsOverride
                {},  # Page.enable
                {},  # Runtime.enable
            ])

            args = argparse.Namespace(list_tabs=False, target_url="http://localhost:3000", navigate=False, wait=0, click=None, selectors=None, audit_layout=False, eval=None, screenshot=None)
            with patch("cdp_inspect.connect_ws", return_value=mock_ws), \
                 patch("cdp_inspect.CDPSession", return_value=mock_cdp):
                code = await cdp_inspect.attach_and_run("ws://localhost:9222", args, viewport=(1280, 720))
                self.assertEqual(code, 0)

        asyncio.run(_test())

    def test_main_cli_dispatch(self):
        with patch("sys.argv", ["cdp_inspect.py", "--url", "http://localhost:8080", "--headless"]), \
             patch("cdp_inspect.main_async", new_callable=AsyncMock) as mock_async, \
             patch("sys.exit") as mock_exit:
            mock_async.return_value = 0
            cdp_inspect.main()
            mock_exit.assert_called_once_with(0)

if __name__ == "__main__":
    unittest.main()
