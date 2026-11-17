#!/usr/bin/env python3
"""
Unit tests for scripts/cdp_inspect.py lifecycle, CLI dispatch, and DOM probe behavior.
"""

import argparse
import asyncio
import io
import json
import shutil
import subprocess
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import cdp_inspect  # noqa: E402

_DOM_PROBE_HARNESS_TEMPLATE = """
const makeEl = (spec) => ({
  tagName: spec.tagName || 'BUTTON',
  id: spec.id || '',
  className: spec.className || '',
  textContent: spec.textContent || '',
  scrollWidth: spec.scrollWidth || 0,
  clientWidth: spec.clientWidth || 0,
  scrollHeight: spec.scrollHeight || 20,
  clientHeight: spec.clientHeight || 20,
  scrollLeft: 0,
  scrollTop: 0,
  parentElement: null,
  getBoundingClientRect: () => spec.rect || { x: 0, y: 0, left: 0, top: 0, right: 50, bottom: 24, width: 50, height: 24 },
  _style: spec.style || {},
});
const squashedBtn = makeEl({
  tagName: 'BUTTON',
  className: 'btn-xs btn-reconvert-video',
  textContent: 'Re-convert',
  scrollWidth: 80,
  clientWidth: 26,
  rect: { x: 0, y: 0, left: 0, top: 0, right: 28, bottom: 24, width: 28, height: 24 },
  style: { display: 'inline-flex', visibility: 'visible', whiteSpace: 'nowrap', overflow: 'visible', overflowX: 'visible', textOverflow: 'clip' },
});
const okBtn = makeEl({
  tagName: 'BUTTON',
  className: 'btn-ok',
  textContent: 'Convert',
  scrollWidth: 130,
  clientWidth: 130,
  style: { display: 'inline-flex', visibility: 'visible', whiteSpace: 'nowrap', overflow: 'visible', overflowX: 'visible', textOverflow: 'clip' },
});
const ellipsisLink = makeEl({
  tagName: 'A',
  className: 'ellipsis-link',
  textContent: 'very_long_filename.mp4',
  scrollWidth: 200,
  clientWidth: 100,
  style: { display: 'block', visibility: 'visible', whiteSpace: 'nowrap', overflow: 'hidden', overflowX: 'hidden', textOverflow: 'ellipsis' },
});
const hiddenMenu = makeEl({
  tagName: 'DIV',
  className: 'video-action-menu',
  textContent: 'Hidden',
  scrollWidth: 120,
  clientWidth: 0,
  rect: { x: 0, y: 0, left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 },
  style: { display: 'none', visibility: 'visible', whiteSpace: 'nowrap', overflow: 'visible', overflowX: 'visible' },
});
global.window = {
  innerWidth: 1440,
  innerHeight: 900,
  scrollX: 0,
  scrollY: 0,
  location: { href: 'http://localhost:8000/' },
  getComputedStyle: (el) => el._style,
};
global.document = {
  title: 'Test',
  documentElement: { scrollHeight: 900, scrollWidth: 1440, scrollLeft: 0, scrollTop: 0 },
  body: { scrollLeft: 0, scrollTop: 0 },
  querySelector: () => null,
  querySelectorAll: (sel) => {
    if (sel.includes('button, a, .badge')) return [squashedBtn, okBtn, ellipsisLink, hiddenMenu];
    return [];
  },
};
const result = eval(__AUDIT_JS_JSON__);
console.log(JSON.stringify(result.layoutOverflowWarnings));
"""


class TestCDPLifecycleAndCLI(unittest.TestCase):
    """Tests for live/headless browser lifecycles, attach_and_run, and CLI dispatch."""

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
            with patch("cdp_inspect.find_devtools_active_port", return_value=None):
                self.assertIsNone(await cdp_inspect.run_live(args))

            with patch("cdp_inspect.find_devtools_active_port", return_value=(9222, "/ws")), \
                 patch("cdp_inspect.attach_and_run", side_effect=ConnectionError("Refused")):
                self.assertIsNone(await cdp_inspect.run_live(args))

            args_no_fallback = argparse.Namespace(fallback_headless=False)
            with patch("cdp_inspect.find_devtools_active_port", return_value=(9222, "/ws")), \
                 patch("cdp_inspect.attach_and_run", side_effect=ConnectionError("Refused")):
                self.assertEqual(await cdp_inspect.run_live(args_no_fallback), 2)

        asyncio.run(_test())

    def test_run_headless_validation_and_launch(self):
        async def _test():
            args = argparse.Namespace(target_url="", list_tabs=False)
            self.assertEqual(await cdp_inspect.run_headless(args), 2)

            args_url = argparse.Namespace(target_url="http://localhost:3000", list_tabs=False, viewport=(1440, 900), port=0)
            with patch("cdp_inspect.find_chrome_executable", return_value="nonexistent_chrome_9999"), \
                 patch("os.path.exists", return_value=False), \
                 patch("shutil.which", return_value=None):
                self.assertEqual(await cdp_inspect.run_headless(args_url), 1)

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
                {"targetInfos": [{"type": "page", "url": "http://localhost:3000", "targetId": "T1"}]},
                {"sessionId": "S1"},
                {},
                {},
                {},
            ])

            args = argparse.Namespace(
                list_tabs=False,
                target_url="http://localhost:3000",
                navigate=False,
                wait=0,
                click=None,
                selectors=None,
                audit_layout=False,
                eval=None,
                screenshot=None,
            )
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

    def test_connect_timeout_flag_and_run_live_fallback_message(self):
        parser = cdp_inspect.build_parser()
        ns = parser.parse_args(["--connect-timeout", "35"])
        self.assertEqual(ns.connect_timeout, 35.0)
        args_no_fb = argparse.Namespace(fallback_headless=False)
        args_fb = argparse.Namespace(fallback_headless=True)
        with patch("cdp_inspect.find_devtools_active_port", return_value=(9222, "/devtools/browser/x")), \
             patch("cdp_inspect.attach_and_run", side_effect=TimeoutError("timed out")):
            buf1 = io.StringIO()
            with redirect_stderr(buf1):
                rc1 = asyncio.run(cdp_inspect.run_live(args_no_fb))
            self.assertEqual(rc1, 2)
            self.assertNotIn("Falling back to isolated headless browser", buf1.getvalue())
            buf2 = io.StringIO()
            with redirect_stderr(buf2):
                rc2 = asyncio.run(cdp_inspect.run_live(args_fb))
            self.assertIsNone(rc2)
            self.assertIn("Falling back to isolated headless browser", buf2.getvalue())


class TestCDPDOMProbeBehavior(unittest.TestCase):
    """Behavioral verification of generated layout audit JS under Node.js."""

    @unittest.skipUnless(shutil.which("node"), "Node.js required for JS DOM probe execution")
    def test_audit_layout_js_flags_interactive_text_overflow_behaviorally(self):
        audit_js = cdp_inspect.build_generic_audit_js([])
        harness = _DOM_PROBE_HARNESS_TEMPLATE.replace("__AUDIT_JS_JSON__", json.dumps(audit_js))
        proc = subprocess.run(
            ["node", "-e", harness],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        warnings = json.loads(proc.stdout.strip())
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["selector"], "button.btn-xs.btn-reconvert-video")
        self.assertEqual(warnings[0]["scrollWidth"], 80)
        self.assertEqual(warnings[0]["clientWidth"], 26)


if __name__ == "__main__":
    unittest.main()
