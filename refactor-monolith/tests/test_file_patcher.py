"""Unit and regression tests for file_patcher and diagnostic CLI commands."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))
_SCRIPTS_DIR = _SKILL_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from scripts.file_patcher import (
    cmd_normalize_eol,
    detect_file_eol,
    inject_html_scripts,
    normalize_file_eol,
    patch_file_content,
)
from scripts.contract_snapshot import main
from scripts.campaign_manager import print_turn_ceiling_alert


class TestFilePatcher(unittest.TestCase):
    def test_detect_and_normalize_eol(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "sample.txt"
            # Write CRLF
            f.write_bytes(b"line 1\r\nline 2\r\nline 3\r\n")
            self.assertEqual(detect_file_eol(f), "\r\n")

            # Convert to LF
            changed, msg = normalize_file_eol(f, target_eol="\n")
            self.assertTrue(changed)
            self.assertEqual(detect_file_eol(f), "\n")
            self.assertNotIn(b"\r\n", f.read_bytes())

            # Convert to CRLF
            changed2, msg2 = normalize_file_eol(f, target_eol="\r\n")
            self.assertTrue(changed2)
            self.assertEqual(detect_file_eol(f), "\r\n")
            self.assertIn(b"\r\n", f.read_bytes())

    def test_cmd_normalize_eol_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "a.js").write_bytes(b"const x = 1;\r\nconst y = 2;\r\n")
            (d / "b.py").write_bytes(b"def foo():\r\n    pass\r\n")
            (d / "binary.bin").write_bytes(b"hello\x00world\r\n")

            code = cmd_normalize_eol(d, to_eol="lf")
            self.assertEqual(code, 0)
            self.assertNotIn(b"\r\n", (d / "a.js").read_bytes())
            self.assertNotIn(b"\r\n", (d / "b.py").read_bytes())
            # Binary file must be preserved
            self.assertIn(b"\r\n", (d / "binary.bin").read_bytes())

    def test_patch_file_content_crlf_lf_tolerance(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "index.html"
            # Target file has Windows CRLF
            f.write_bytes(b"<!-- Head -->\r\n<script src=\"/static/app.js\"></script>\r\n<!-- Tail -->\r\n")

            # Search target uses LF (like strings emitted by LLMs)
            lf_target = '<script src="/static/app.js"></script>\n'
            lf_replacement = '<script src="/static/js/app_core.js"></script>\n<script src="/static/app.js"></script>\n'

            ok, msg = patch_file_content(f, lf_target, lf_replacement)
            self.assertTrue(ok)
            content = f.read_bytes()
            # File should still preserve CRLF
            self.assertIn(b"\r\n", content)
            self.assertIn(b"app_core.js", content)
            self.assertIn(b"app.js", content)

    def test_patch_file_target_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "sample.js"
            f.write_text("console.log('hi');\n", encoding="utf-8")
            ok, msg = patch_file_content(f, "non_existent_symbol", "replacement")
            self.assertFalse(ok)
            self.assertIn("not found", msg)

    def test_inject_html_scripts_before_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            html = Path(tmp) / "index.html"
            html.write_bytes(
                b"<!DOCTYPE html>\r\n"
                b"<html>\r\n"
                b"<body>\r\n"
                b"  <!-- JS Modules -->\r\n"
                b"  <script src=\"/static/app.js\"></script>\r\n"
                b"</body>\r\n"
                b"</html>\r\n"
            )

            scripts = ["/static/js/live_player.js", "/static/js/telemetry.js"]
            ok, msg = inject_html_scripts(html, scripts, before_script="app.js")
            self.assertTrue(ok)

            raw = html.read_bytes()
            # Preserved CRLF
            self.assertIn(b"\r\n", raw)
            text = raw.decode("utf-8")
            self.assertIn('<script src="/static/js/live_player.js"></script>', text)
            self.assertIn('<script src="/static/js/telemetry.js"></script>', text)
            # Must appear before app.js
            idx_live = text.index("/static/js/live_player.js")
            idx_app = text.index("/static/app.js")
            self.assertLess(idx_live, idx_app)

    def test_inject_html_scripts_skips_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            html = Path(tmp) / "index.html"
            html.write_text('<script src="/static/js/already_there.js"></script>\n', encoding="utf-8")
            ok, msg = inject_html_scripts(html, ["/static/js/already_there.js", "/static/js/new_script.js"])
            self.assertTrue(ok)
            text = html.read_text(encoding="utf-8")
            self.assertEqual(text.count("already_there.js"), 1)
            self.assertIn("new_script.js", text)

    def test_contract_cli_patch_and_inject(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "page.html"
            f.write_text('<html><body><script src="main.js"></script></body></html>\n', encoding="utf-8")

            # Test inject-scripts CLI
            code_inj = main(["inject-scripts", "--html", str(f), "--scripts", "sub1.js", "sub2.js", "--before", "main.js"])
            self.assertEqual(code_inj, 0)
            self.assertIn("sub1.js", f.read_text(encoding="utf-8"))

            # Test patch CLI
            code_ptc = main(["patch", "--file", str(f), "--find", "sub1.js", "--replace", "sub1_renamed.js"])
            self.assertEqual(code_ptc, 0)
            self.assertIn("sub1_renamed.js", f.read_text(encoding="utf-8"))

            # Test normalize-eol CLI
            code_eol = main(["normalize-eol", "--path", tmp, "--to", "lf"])
            self.assertEqual(code_eol, 0)

    def test_turn_ceiling_alert_emits(self):
        # Must execute cleanly without error
        print_turn_ceiling_alert("Slice 1.2 completed")


if __name__ == "__main__":
    unittest.main()
