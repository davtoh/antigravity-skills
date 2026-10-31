"""Comprehensive CLI and integration tests for contract_snapshot, campaign_manager, and auxiliary tools.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure skill root is in sys.path for clean import of scripts
_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from scripts.contract_snapshot import main
from scripts.auxiliary_tool_bridge import _parse_cdp_output, cmd_run_tests
from scripts.audit_reporters import preview_split, inspect_sections


class TestContractCliCommands(unittest.TestCase):
    def test_probe_tools_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = main(["probe-tools", "--path", tmp])
            self.assertEqual(code, 0)

    def test_anchor_cli_non_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = main(["anchor", "--path", tmp])
            self.assertEqual(code, 2)

    def test_anchor_cli_with_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=False)
            subprocess.run(["git", "config", "user.name", "Tester"], cwd=tmp_path, capture_output=True, check=False)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, capture_output=True, check=False)
            (tmp_path / "README.md").write_text("# Hello", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=False)
            subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True, check=False)

            code = main(["anchor", "--path", tmp])
            self.assertEqual(code, 0)

    def test_capture_inspect_and_verify_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "index.html").write_text('<div id="root"><select id="cam-sel"></select></div>', encoding="utf-8")
            (tmp_path / "app.js").write_text('window.App = {}; document.getElementById("cam-sel");', encoding="utf-8")
            (tmp_path / "routes.py").write_text('@app.get("/items")\ndef list_items(): pass\n', encoding="utf-8")

            # 1. Capture to default .refactor/baseline.json
            code_cap = main(["capture", "--path", tmp])
            self.assertEqual(code_cap, 0)
            baseline = tmp_path / ".refactor" / "baseline.json"
            self.assertTrue(baseline.is_file())

            # 2. Inspect surface
            code_ins = main(["inspect", "--path", tmp, "--show-routes"])
            self.assertEqual(code_ins, 0)

            # 3. Verify against auto-detected baseline
            code_ver = main(["verify", "--path", tmp, "--strict"])
            self.assertEqual(code_ver, 0)

            # 4. Verify with nonexistent baseline
            code_bad = main(["verify", "--path", tmp, "--before", str(tmp_path / "missing.json")])
            self.assertEqual(code_bad, 2)

    def test_verify_discrepancy_strict(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "index.html").write_text('<div id="cam-sel"></div>', encoding="utf-8")
            (tmp_path / "app.js").write_text('document.getElementById("cam-sel");', encoding="utf-8")
            main(["capture", "--path", tmp])

            # Now modify index.html to drop cam-sel
            (tmp_path / "index.html").write_text('<div id="other"></div>', encoding="utf-8")
            code_fail = main(["verify", "--path", tmp, "--strict"])
            self.assertEqual(code_fail, 1)

    def test_additional_cli_subcommands(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
            main(["capture", "--path", tmp])

            # 1. generate-smoke-test CLI
            smoke_out = tmp_path / "tests" / "test_smoke.py"
            code_smk = main(["generate-smoke-test", "--path", tmp, "--out", str(smoke_out)])
            self.assertEqual(code_smk, 0)
            self.assertTrue(smoke_out.is_file())

            # 2. inspect-css CLI
            code_css = main(["inspect-css", "--path", tmp])
            self.assertEqual(code_css, 0)

            # 3. verify-ui CLI
            code_ui = main(["verify-ui", "--path", tmp])
            self.assertEqual(code_ui, 0)

            # 4. audit-container CLI
            code_doc = main(["audit-container", "--path", tmp])
            self.assertEqual(code_doc, 0)

            # 5. verify with --ui and --docker
            code_ver = main(["verify", "--path", tmp, "--ui", "--docker"])
            self.assertEqual(code_ver, 0)

    def test_run_tests_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            tests_dir = tmp_path / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_sample.py").write_text(
                "import unittest\nclass T(unittest.TestCase):\n    def test_ok(self): pass\n",
                encoding="utf-8"
            )
            # Run unittest forwarder with default discover tests
            code = main(["run-tests", "--path", tmp])
            self.assertEqual(code, 0)


class TestCampaignAndReporterTools(unittest.TestCase):
    def test_campaign_manager_full_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # Init
            code_init = main([
                "state", "--path", tmp, "--action", "init",
                "--plan", "plan.md", "--phases", "2", "--phase-title", "Phase 1"
            ])
            self.assertEqual(code_init, 0)

            # Show text and json
            code_show = main(["state", "--path", tmp, "--action", "show"])
            self.assertEqual(code_show, 0)
            code_json = main(["state", "--path", tmp, "--action", "show", "--json"])
            self.assertEqual(code_json, 0)

            # Checkpoint
            code_cp = main(["state", "--path", tmp, "--action", "checkpoint", "--note", "slice complete"])
            self.assertEqual(code_cp, 0)

            # Set
            code_set = main(["state", "--path", tmp, "--action", "set", "--phase", "1", "--status", "in_progress", "--sha", "1234567"])
            self.assertEqual(code_set, 0)

            # Advance Phase 1 -> Phase 2
            code_adv1 = main(["state", "--path", tmp, "--action", "advance", "--phase", "1", "--sha", "abcdef1"])
            self.assertEqual(code_adv1, 0)

            # Advance Phase 2 -> Completed
            code_adv2 = main(["state", "--path", tmp, "--action", "advance", "--phase", "2", "--sha", "abcdef2"])
            self.assertEqual(code_adv2, 0)

            # Show completed summary
            code_done = main(["state", "--path", tmp, "--action", "show"])
            self.assertEqual(code_done, 0)

    def test_campaign_manager_missing_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = main(["state", "--path", tmp, "--action", "show"])
            self.assertEqual(code, 1)

    def test_cdp_output_parsing(self):
        # 1. Clean output
        self.assertEqual(_parse_cdp_output('{"hasOverflow": false}'), 0)
        # 2. JS Exception
        self.assertEqual(_parse_cdp_output('{"jsException": "ReferenceError"}'), 1)
        # 3. Layout Overflow
        self.assertEqual(_parse_cdp_output('{"hasOverflow": true, "overflowingElements": ["div#main"]}'), 1)
        # 4. Non-JSON string
        self.assertEqual(_parse_cdp_output('Running inspection on page'), 0)

    def test_preview_split_edge_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sample_file = tmp_path / "sample.py"
            sample_file.write_text("x = 1\ny = 2\nz = 3\n", encoding="utf-8")

            # Invalid spec format
            self.assertEqual(preview_split("not_enough_colons"), 2)
            # Missing file
            self.assertEqual(preview_split(f"{tmp_path / 'missing.py'}:1:5"), 2)
            # Valid split preview
            self.assertEqual(preview_split(f"{sample_file}:2:2"), 0)

    def test_inspect_sections_edge_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sample_file = tmp_path / "sample.py"
            sample_file.write_text(
                "# ==========================================================================\n"
                "# Domain Models\n"
                "# ==========================================================================\n"
                "class UserModel:\n"
                "    pass\n"
                "def helper():\n"
                "    pass\n",
                encoding="utf-8"
            )
            # Missing file
            self.assertEqual(inspect_sections(str(tmp_path / "missing.py")), 2)
            # File with sections
            self.assertEqual(inspect_sections(str(sample_file)), 0)

            # File with no sections
            empty_file = tmp_path / "empty.py"
            empty_file.write_text("x = 10\n", encoding="utf-8")
            self.assertEqual(inspect_sections(str(empty_file)), 0)

    def test_audit_reporters_formatting(self):
        from scripts.code_health_audit import AuditThresholds, FileReport, ClassMetric, FunctionMetric
        from scripts.audit_reporters import print_by_dir_summary, print_text_summary

        thresholds = AuditThresholds()
        rep = FileReport(
            rel_path="src/sub/heavy.py",
            lines=600,
            status="CRITICAL",
            parser_mode="ast",
            classes=[
                ClassMetric(name="HeavyClass", start_line=10, end_line=150, lines=140, method_count=15, status="CRITICAL", methods=["m1", "m2"])
            ],
            oversized_functions=[
                FunctionMetric(name="heavy_fn", qualname="heavy_fn", start_line=160, end_line=220, lines=60, status="CRITICAL")
            ]
        )
        print_by_dir_summary([rep], thresholds)
        print_text_summary([rep], thresholds, top_n=5, show_methods=True, by_dir=True)
        print_text_summary([rep], thresholds, top_n=5, show_methods=True, by_dir=False)


if __name__ == "__main__":
    unittest.main()
