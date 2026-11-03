#!/usr/bin/env python3
"""Additional comprehensive coverage tests targeting remaining branch and edge-case gaps.

Covers:
1. surface_scanners: to_dict methods, __all__ list exports, empty CSS rules, banner comments.
2. css_inspector: OSError handlers, banner truncation (--all vs default 12 limit), strict exits.
3. audit_reporters: invalid split-preview arguments, missing file error outputs.
4. smoke_test_generator: custom contract_builder, before_file JSON path, invalid target fallback.
5. contract_diff_engine: inline handler syntax skips, git tree read exceptions, invalid paths.
6. campaign_manager: corrupted state file handling, phase title updates, non-numeric phase fallback.
7. code_health_audit: empty file parsing, stylesheet & fallback parsing, line-reading errors.
8. language_analyzers: C# method extraction, multi-line comment edge cases, return block terminals.
9. auxiliary_tool_bridge: non-standard port listeners, container error details.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_SKILL_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _SKILL_ROOT / "scripts"
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from scripts.audit_reporters import inspect_sections, preview_split, _parse_split_spec
from scripts.auxiliary_tool_bridge import _resolve_cdp_script_and_url
from scripts.campaign_manager import cmd_state, _format_phase_icon, _parse_phase_sort_key
from scripts.code_health_audit import audit_file, AuditThresholds
from scripts.contract_diff_engine import build_contract, diff_contracts, _run_git
from scripts.contract_snapshot import CodebaseContract, cmd_capture, cmd_inspect
from scripts.css_inspector import cmd_inspect_css, _inspect_single_css_file
from scripts.language_analyzers import analyze_brace_language, _find_block_end, _has_opening_brace, _strip_strings_and_comments
from scripts.smoke_test_generator import cmd_generate_smoke_test, _resolve_root_expr
from scripts.surface_scanners import CssSurface, HtmlSurface, JsSurface, PythonSurface, scan_css_surface, scan_python_surface

class TestSurfaceScannersDeepCoverage(unittest.TestCase):
    """Test to_dict, __all__ string constants, and CSS banner exclusions."""

    def test_dataclass_to_dict_methods(self):
        h = HtmlSurface(ids=["x"], selects=["s"])
        self.assertEqual(h.to_dict()["ids"], ["x"])

        j = JsSurface(queried_ids=["q"], global_exports=["w"])
        self.assertEqual(j.to_dict()["queried_ids"], ["q"])

        p = PythonSurface(classes=["C"], functions=["f"])
        self.assertEqual(p.to_dict()["classes"], ["C"])

        c = CssSurface(custom_properties=["--p"], important_count=2)
        self.assertEqual(c.to_dict()["important_count"], 2)

    def test_python_surface_all_string_constants(self):
        code = (
            "__all__ = ['alpha', 'beta', 'gamma', 123]\n"
            "alpha = 1\n"
            "beta = 2\n"
        )
        surf = scan_python_surface(code)
        self.assertIn("alpha", surf.all_exports)
        self.assertIn("beta", surf.all_exports)
        self.assertIn("gamma", surf.all_exports)

    def test_css_banner_comments_and_ignore_prefixes(self):
        css = (
            "/* Section Header */\n"
            "/* ! Important License Notice */\n"
            "/* TODO: refactor this */\n"
            "/* eslint-disable */\n"
            "/* https://example.com */\n"
            ".nav { color: blue; }\n"
        )
        surf = scan_css_surface(css)
        self.assertTrue(len(surf.section_banners) >= 1)
        self.assertEqual(surf.section_banners[0]["title"], "Section Header")
        # Ignored banners should not be added
        self.assertFalse(any("License" in b["title"] for b in surf.section_banners))
        self.assertFalse(any("refactor" in b["title"] for b in surf.section_banners))

class TestCssInspectorAndAuditReportersDeepCoverage(unittest.TestCase):
    """Test missing file handling, banner truncation, and spec parsers."""

    def test_css_inspector_banner_truncation_and_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            # Create a file with > 12 banners
            banners = "\n".join(
                f"/* ==========================================================================\n"
                f"   Section {i}\n"
                f"   ========================================================================== */\n.s{i} {{ color: red; }}"
                for i in range(15)
            )
            css_file = p / "big.css"
            css_file.write_text(banners, encoding="utf-8")

            # Default run should truncate banners (> 12)
            code, _ = _inspect_single_css_file(css_file, show_all=False)
            self.assertEqual(code, 0)

            # Nonexistent file returns code 1
            code_err, _ = _inspect_single_css_file(p / "missing.css")
            self.assertEqual(code_err, 1)

            # Directory scan with unreadable file
            code_dir = cmd_inspect_css(p, show_all=True)
            self.assertEqual(code_dir, 0)

    def test_audit_reporters_parse_spec_and_missing_files(self):
        # Invalid split spec formats (less than 2 parts)
        self.assertIsNone(_parse_split_spec("invalid_without_colon"))

        # Valid 3-part spec
        path, line, win = _parse_split_spec("app.py:100:20")
        self.assertEqual(line, "100")
        self.assertEqual(win, 20)

        # File reading errors in preview_split and inspect_sections
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "none.py"
            self.assertEqual(preview_split(f"{missing}:10"), 2)
            self.assertEqual(inspect_sections(str(missing)), 2)

class TestSmokeTestGeneratorDeepCoverage(unittest.TestCase):
    """Test custom contract builder, before_file loading, and exception fallback in root expr."""

    def test_cmd_generate_smoke_test_with_before_file_and_builder(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / ".git").mkdir()
            out_test = base / "tests" / "test_out.py"

            # 1. Test before_file path
            bf = base / "baseline.json"
            bf.write_text(json.dumps({"html_ids": ["box"], "select_ids": ["sel"], "css_important_count": 0}), encoding="utf-8")
            code_bf = cmd_generate_smoke_test(base, str(out_test), before_file=str(bf))
            self.assertEqual(code_bf, 0)

            # 2. Test custom contract_builder
            mock_builder = mock.MagicMock(return_value=CodebaseContract(html_ids=["custom_id"]))
            code_cb = cmd_generate_smoke_test(base, str(out_test), contract_builder=mock_builder)
            self.assertEqual(code_cb, 0)
            mock_builder.assert_called_once()

    def test_resolve_root_expr_exception_fallback(self):
        # Pass an object that causes an exception during relpath resolution
        res = _resolve_root_expr(Path("target"), Path("root"), out_p=mock.MagicMock(parent=None))
        self.assertIn("pathlib.Path", res)

class TestContractDiffAndSnapshotDeepCoverage(unittest.TestCase):
    """Test git tree reading errors, inline handler skipped targets, and candidate fallbacks."""

    def test_diff_contracts_inline_handler_skips(self):
        # Handlers that start with let, var, const, if, return should not trigger missing export error
        before = CodebaseContract()
        after = CodebaseContract(inline_handlers=[
            {"event": "onclick", "target": "let x = 1;"},
            {"event": "onchange", "target": "if (true) return;"},
            {"event": "oninput", "target": "return false;"},
            {"event": "onclick", "target": "document.write('hi')"},
        ])
        issues = diff_contracts(before, after)
        self.assertEqual(issues, [])

    def test_read_git_tree_contract_exceptions(self):
        # Invalid git ref returns non-zero code from _run_git
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / ".git").mkdir()
            code, msg = _run_git(["show", "nonexistent_ref_12345:file.txt"], cwd=p)
            self.assertNotEqual(code, 0)

    def test_cmd_capture_and_inspect_truncations(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / ".git").mkdir()
            custom_out = base / "custom" / "base.json"

            # cmd_capture with explicit output file
            code_cap = cmd_capture(base, out_file=str(custom_out))
            self.assertEqual(code_cap, 0)
            self.assertTrue(custom_out.exists())

            # cmd_inspect with > 15 selects and routes
            huge_contract = CodebaseContract(
                select_ids=[f"sel-{i}" for i in range(20)],
                python_routes=[{"method": "GET", "path": f"/api/{i}", "handler": "h", "file": "r.py", "line": i} for i in range(20)]
            )
            with mock.patch("scripts.contract_snapshot.build_contract", return_value=huge_contract):
                code_insp = cmd_inspect(base)
                self.assertEqual(code_insp, 0)

class TestLanguageAnalyzersAndCodeHealthCoverage(unittest.TestCase):
    """Test C#, TypeScript, stylesheet, and empty file coverage."""

    def test_csharp_and_typescript_analyzers(self):
        cs_code = (
            "namespace Acme.App {\n"
            "    public class WorkerService {\n"
            "        public void Process() {\n"
            "            var x = 1;\n"
            "        }\n"
            "        private int Count() => 42;\n"
            "    }\n"
            "}\n"
        )
        symbols_cs = analyze_brace_language(cs_code)
        self.assertTrue(any(s.name == "WorkerService" for s in symbols_cs))

        ts_code = (
            "export class OrderHandler {\n"
            "    constructor() {}\n"
            "    public handle(): void {}\n"
            "}\n"
        )
        symbols_ts = analyze_brace_language(ts_code)
        self.assertTrue(any(s.name == "OrderHandler" for s in symbols_ts))

    def test_language_analyzers_helper_predicates(self):
        # _strip_strings_and_comments
        cleaned = _strip_strings_and_comments('int x = 1; // comment "quoted"')
        self.assertNotIn("comment", cleaned)

        # _has_opening_brace
        self.assertTrue(_has_opening_brace(["class Foo {", "}"], 0))
        self.assertFalse(_has_opening_brace(["int x = 1;", "int y = 2;"], 0))

        # _find_block_end
        lines = ["class A {", "    void run() {", "    }", "}"]
        idx = _find_block_end(lines, 0)
        self.assertEqual(idx, 4)

    def test_code_health_audit_empty_and_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            th = AuditThresholds()
            empty_file = base / "empty.py"
            empty_file.write_text("", encoding="utf-8")
            rep_empty = audit_file(empty_file, base, th)
            self.assertEqual(rep_empty.parser_mode, "empty")

            # Fallback text file
            txt_file = base / "script.sh"
            txt_file.write_text("echo 'hello'\necho 'world'\n", encoding="utf-8")
            rep_txt = audit_file(txt_file, base, th)
            self.assertEqual(rep_txt.parser_mode, "fallback")

class TestCampaignManagerCorruptedAndAuxiliaryCoverage(unittest.TestCase):
    """Test corrupted state files, non-numeric phase fallbacks, and CDP edge cases."""

    def test_campaign_manager_corrupted_state_and_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            refactor_dir = base / ".refactor"
            refactor_dir.mkdir()
            state_file = refactor_dir / "state.json"

            # Corrupted JSON returns code 1
            state_file.write_text("invalid json content {{{", encoding="utf-8")
            code = cmd_state(base, action="show")
            self.assertEqual(code, 1)

            # Valid state with custom status update and phase title
            valid_state = {
                "active_phase": 1,
                "phases": {"1": {"title": "Old", "status": "pending"}},
                "status": "pending"
            }
            state_file.write_text(json.dumps(valid_state), encoding="utf-8")
            code_up = cmd_state(base, action="set", phase=1, phase_title="New Title", status="in_progress")
            self.assertEqual(code_up, 0)
            updated = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual(updated["phases"]["1"]["title"], "New Title")
            self.assertEqual(updated["phases"]["1"]["status"], "in_progress")

    def test_format_phase_icon_and_sort_key(self):
        icon_done = _format_phase_icon(True, False)
        self.assertTrue(icon_done in ("✅", "[x]"))
        icon_active = _format_phase_icon(False, True)
        self.assertTrue(icon_active in ("▶️", "[>]"))
        icon_pending = _format_phase_icon(False, False)
        self.assertTrue(icon_pending in ("⏳", "[ ]"))

        # _parse_phase_sort_key
        self.assertEqual(_parse_phase_sort_key("1.2"), 1.2)
        self.assertEqual(_parse_phase_sort_key("non-numeric"), 999.0)

    def test_auxiliary_cdp_resolve_url_with_explicit_url(self):
        tools = {"cdp_inspect": "scripts/cdp_inspect.py"}
        script, url = _resolve_cdp_script_and_url(Path("."), tools, "http://localhost:9000")
        self.assertEqual(url, "http://localhost:9000")
        self.assertEqual(script, "scripts/cdp_inspect.py")

if __name__ == "__main__":
    unittest.main()
