#!/usr/bin/env python3
"""Automated unit test suite for css_inspector.py in system-diagnostics.

Zero external dependencies; standard library Python 3.10+ only.
Tests CSS modularity, specificity inspection, section banners, and !important auditing.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

# Ensure system-diagnostics/scripts is in sys.path
SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from css_inspector import cmd_inspect_css


class TestCssInspector(unittest.TestCase):
    """Test suite for stylesheet inspection and specificity auditing."""

    def test_inspect_single_clean_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "clean.css"
            f.write_text(
                "/* ==========================================================================\n"
                "   Base Tokens\n"
                "   ========================================================================== */\n"
                ":root { --primary: #00ffcc; }\n"
                ".card { border-radius: 8px; }\n",
                encoding="utf-8",
            )
            code = cmd_inspect_css(f, show_all=True, strict=True)
            self.assertEqual(code, 0)

    def test_inspect_file_with_important_strict_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "breached.css"
            f.write_text(
                ".btn-alert { color: red !important; }\n",
                encoding="utf-8",
            )
            # Default non-strict returns 0
            code_default = cmd_inspect_css(f, show_all=False, strict=False)
            self.assertEqual(code_default, 0)

            # Strict mode returns 1 because of !important
            code_strict = cmd_inspect_css(f, show_all=False, strict=True)
            self.assertEqual(code_strict, 1)

    def test_inspect_directory_and_ignores(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            css_dir = base / "styles"
            css_dir.mkdir()
            (css_dir / "tokens.css").write_text(":root { --primary: #fff; }\n", encoding="utf-8")
            (css_dir / "layout.css").write_text(".grid { display: grid; }\n", encoding="utf-8")

            # Vendor directory should be ignored
            vendor_dir = css_dir / "vendor"
            vendor_dir.mkdir()
            (vendor_dir / "bundle.css").write_text(".bad { color: red !important; }\n", encoding="utf-8")

            # Minified file should be ignored
            (css_dir / "app.min.css").write_text(".min { color: red !important; }\n", encoding="utf-8")

            code = cmd_inspect_css(css_dir, show_all=False, strict=True)
            # Should pass because vendor and .min.css are ignored
            self.assertEqual(code, 0)

    def test_nonexistent_path(self):
        code = cmd_inspect_css(Path("nonexistent_path_12345.css"))
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()

