"""Comprehensive CLI and integration tests for contract_snapshot, campaign_manager, and auxiliary tools.
"""

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
from scripts.auxiliary_tool_bridge import _parse_cdp_output
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
            # 1. Run unittest forwarder with default discover tests
            code = main(["run-tests", "--path", tmp])
            self.assertEqual(code, 0)

            # 2. Run with forwarded flags including -p and -v (which previously crashed argparse!)
            code_flags = main(["run-tests", "--path", tmp, "discover", "tests", "-p", "test_*.py", "-v"])
            self.assertEqual(code_flags, 0)

            # 3. Run with -- separator before flags
            code_sep = main(["run-tests", "--path", tmp, "--", "discover", "tests", "-v"])
            self.assertEqual(code_sep, 0)

            # 3b. Run with omitted discover subcommand and raw -p pattern flag
            code_omitted_discover = main(["run-tests", "--path", tmp, "--", "-p", "test_*.py"])
            self.assertEqual(code_omitted_discover, 0)

            # 4. Direct inline python command via -c
            code_cmd = main(["run-tests", "--path", tmp, "-c", "import sys; sys.exit(0)"])
            self.assertEqual(code_cmd, 0)

            # 5. Direct inline command exiting 1
            code_fail = main(["run-tests", "--path", tmp, "-c", "import sys; sys.exit(1)"])
            self.assertEqual(code_fail, 1)

    def test_run_tests_pytest_detection_and_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "conftest.py").write_text("# pytest marker\n", encoding="utf-8")
            # When conftest.py is present, auto-detects pytest.
            # Using -c to avoid needing full pytest installed in test runner environment:
            code = main(["run-tests", "--path", tmp, "-c", "print('auto-runner check')"])
            self.assertEqual(code, 0)

            # Explicit runner argument
            code_runner = main(["run-tests", "--path", tmp, "--runner", "unittest", "-c", "print('explicit runner')"])
            self.assertEqual(code_runner, 0)

    def test_iter_repo_files_pruning(self):
        from scripts.contract_diff_engine import iter_repo_files
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # Create valid file
            (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
            # Create files in ignored directories
            venv_dir = tmp_path / ".venv" / "lib"
            venv_dir.mkdir(parents=True)
            (venv_dir / "bad.py").write_text("should_not_be_scanned\n", encoding="utf-8")
            nm_dir = tmp_path / "node_modules" / "pkg"
            nm_dir.mkdir(parents=True)
            (nm_dir / "index.js").write_text("should_not_be_scanned\n", encoding="utf-8")

            files = iter_repo_files(tmp_path)
            filenames = [f.name for f in files]
            self.assertIn("main.py", filenames)
            self.assertNotIn("bad.py", filenames)
            self.assertNotIn("index.js", filenames)

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
            # Querying missing state exits cleanly with informative message
            code_show = main(["state", "--path", tmp, "--action", "show"])
            self.assertEqual(code_show, 0)
            # Mutations without existing state exit 1
            code_adv = main(["state", "--path", tmp, "--action", "advance"])
            self.assertEqual(code_adv, 1)

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

    def test_verify_supports_multiple_path_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "mod1").mkdir()
            (tmp_path / "mod2").mkdir()
            (tmp_path / "mod1" / "app.py").write_text("x = 1\n", encoding="utf-8")
            (tmp_path / "mod2" / "test.py").write_text("y = 2\n", encoding="utf-8")
            self.assertEqual(main(["capture", "--path", str(tmp_path)]), 0)
            code = main(["verify", "--path", str(tmp_path / "mod1"), str(tmp_path / "mod2"), "--strict"])
            self.assertEqual(code, 0)

    def test_run_tests_cli_module_flag_and_headless_env(self):
        from unittest.mock import patch, MagicMock
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with tempfile.TemporaryDirectory() as tmp:
                code = main(["run-tests", "--path", tmp, "-m", "sphinx", "-W", "--keep-going"])
                self.assertEqual(code, 0)
                cmd = mock_run.call_args[0][0]
                self.assertIn("-m", cmd)
                self.assertIn("sphinx", cmd)
                env = mock_run.call_args[1].get("env", {})
                self.assertEqual(env.get("MPLBACKEND"), "Agg")
                self.assertEqual(env.get("QT_QPA_PLATFORM"), "offscreen")
                self.assertEqual(mock_run.call_args[1].get("timeout"), 180)

    def test_run_tests_timeout_expired_returns_124(self):
        from unittest.mock import patch
        from scripts.auxiliary_tool_bridge import cmd_run_tests
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["test"], timeout=1)):
            with tempfile.TemporaryDirectory() as tmp:
                code = cmd_run_tests(Path(tmp), ["discover", "tests"], timeout=1)
                self.assertEqual(code, 124)

    def test_merge_contracts_deduplication(self):
        from scripts.contract_diff_engine import CodebaseContract, merge_contracts
        c1 = CodebaseContract(
            html_ids=["b", "a"],
            select_ids=["sel1"],
            inline_handlers=[{"event": "click", "target": "run"}],
            css_important_count=2,
            python_globals=["User"],
        )
        c2 = CodebaseContract(
            html_ids=["a", "c"],
            select_ids=["sel1", "sel2"],
            inline_handlers=[{"event": "click", "target": "run"}, {"event": "load", "target": "init"}],
            css_important_count=3,
            python_globals=["User", "Admin"],
        )
        merged = merge_contracts([c1, c2])
        self.assertEqual(merged.html_ids, ["a", "b", "c"])
        self.assertEqual(merged.select_ids, ["sel1", "sel2"])
        self.assertEqual(len(merged.inline_handlers), 2)
        self.assertEqual(merged.css_important_count, 5)
        self.assertEqual(merged.python_globals, ["Admin", "User"])

    def test_run_tests_auto_detects_django_settings_and_injects_env(self):
        from unittest.mock import patch, MagicMock
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with tempfile.TemporaryDirectory() as tmp:
                manage_py = Path(tmp) / "manage.py"
                manage_py.write_text(
                    "import os\nif __name__ == '__main__':\n"
                    "    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'my_enterprise.settings')\n",
                    encoding="utf-8",
                )
                code = main(["run-tests", "--path", tmp, "manage.py", "check"])
                self.assertEqual(code, 0)
                cmd = mock_run.call_args[0][0]
                self.assertIn("manage.py", cmd)
                self.assertIn("check", cmd)
                env = mock_run.call_args[1].get("env", {})
                self.assertEqual(env.get("DJANGO_SETTINGS_MODULE"), "my_enterprise.settings")

    def test_typecheck_cli_skipped_gracefully_when_no_checker(self):
        from unittest.mock import patch, MagicMock
        with patch("subprocess.run") as mock_run:
            # Simulate ruff/mypy not installed (--version returns code 1)
            mock_run.return_value = MagicMock(returncode=1)
            with tempfile.TemporaryDirectory() as tmp:
                code = main(["typecheck", "--path", tmp])
                self.assertEqual(code, 0)

    def test_typecheck_cli_ruff_pass_and_failure_truncation(self):
        from unittest.mock import patch, MagicMock
        with patch("subprocess.run") as mock_run:
            # 1. ruff --version succeeds
            # 2. ruff check succeeds
            mock_run.side_effect = [
                MagicMock(returncode=0),
                MagicMock(returncode=0, stdout="All clean\n"),
            ]
            with tempfile.TemporaryDirectory() as tmp:
                code = main(["typecheck", "--path", tmp])
                self.assertEqual(code, 0)

        with patch("subprocess.run") as mock_run:
            # 1. ruff --version succeeds
            # 2. ruff check fails with 8 errors (should truncate to 5)
            mock_run.side_effect = [
                MagicMock(returncode=0),
                MagicMock(returncode=1, stdout="\n".join(f"file.py:{i}: error: E{i}" for i in range(8))),
            ]
            with tempfile.TemporaryDirectory() as tmp:
                code = main(["typecheck", "--path", tmp])
                self.assertEqual(code, 1)

if __name__ == "__main__":
    unittest.main()
