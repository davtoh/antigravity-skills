"""Automated end-to-end verification of all scenarios in the Scenario Combinations Matrix.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from scripts.contract_snapshot import main as contract_main
from scripts.code_health_audit import main as audit_main


class TestCodeHealthAuditScenarios(unittest.TestCase):
    """Verifies Scenarios 1-4: Directory triage, multi-target, split preview, and section outlines."""

    def test_scenario_directory_triage_and_multi_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            d1, d2 = tmp_path / "mod1", tmp_path / "mod2"
            d1.mkdir()
            d2.mkdir()
            (d1 / "a.py").write_text("x = 1\n", encoding="utf-8")
            (d2 / "b.py").write_text("y = 2\n", encoding="utf-8")

            # Scenario 1: Directory-Level Triage
            self.assertEqual(audit_main(["--path", str(tmp_path), "--by-dir"]), 0)
            # Scenario 2: Multi-Target Audit
            self.assertEqual(audit_main(["--path", str(d1 / "a.py"), str(d2)]), 0)

    def test_scenario_split_preview_and_section_outline(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            f = tmp_path / "service.py"
            f.write_text(
                "# ==========================================================================\n"
                "# Service Core\n"
                "# ==========================================================================\n"
                "class CoreService:\n"
                "    def process(self):\n"
                "        return 42\n",
                encoding="utf-8",
            )
            # Scenario 3: Split Point Preview
            self.assertEqual(audit_main(["--split-preview", f"{f}:4:2"]), 0)
            # Scenario 4: Section & Banner Outline
            self.assertEqual(audit_main(["--inspect-sections", str(f)]), 0)

    def test_scenario_precommit_strict_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            f = tmp_path / "huge.py"
            f.write_text("class GodClass:\n" + "".join(f"    def m{i}(self): pass\n" for i in range(16)), encoding="utf-8")
            # Strict mode should exit 1 on modularity breach
            self.assertEqual(audit_main(["--path", str(tmp_path), "--strict"]), 1)


class TestGitContractAndStateScenarios(unittest.TestCase):
    """Verifies Scenarios 5-14 & 23: Anchors, capture, inspect, CSS, campaign state, and git diff."""

    def _init_git_repo(self, path: Path) -> str:
        subprocess.run(["git", "init"], cwd=path, capture_output=True, check=False)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=path, capture_output=True, check=False)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True, check=False)
        (path / "index.html").write_text('<div id="root"><select id="mode"></select></div>', encoding="utf-8")
        (path / "app.js").write_text('window.App = { run: () => {} }; document.getElementById("mode");', encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=path, capture_output=True, check=False)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=path, capture_output=True, check=False)
        proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True, check=False)
        return proc.stdout.strip()

    def test_scenario_contract_lifecycle_and_git_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            initial_sha = self._init_git_repo(tmp_path)

            # Scenario 5: Anchor
            self.assertEqual(contract_main(["anchor", "--path", tmp]), 0)
            # Scenario 6: Capture baseline
            self.assertEqual(contract_main(["capture", "--path", tmp]), 0)
            # Scenario 7: Inspect surface
            self.assertEqual(contract_main(["inspect", "--path", tmp, "--show-routes"]), 0)
            # Scenario 13: Per-slice contract verify
            self.assertEqual(contract_main(["verify", "--path", tmp, "--strict"]), 0)

            # Drop an element and verify git-ref diff
            (tmp_path / "index.html").write_text('<div id="mutated"></div>', encoding="utf-8")
            # Scenario 14: Post-Refactor Regression Audit vs Git SHA
            self.assertEqual(contract_main(["verify", "--path", tmp, "--git-ref", initial_sha, "--strict"]), 1)

    def test_scenario_campaign_state_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Scenario 9: Init campaign
            self.assertEqual(contract_main(["state", "--path", tmp, "--action", "init", "--phases", "3"]), 0)
            # Scenario 10: Show progress
            self.assertEqual(contract_main(["state", "--path", tmp, "--action", "show"]), 0)
            # Scenario 11: Save checkpoint
            self.assertEqual(contract_main(["state", "--path", tmp, "--action", "checkpoint", "--note", "Batch 1 done"]), 0)
            # Scenario 12: Advance phase
            self.assertEqual(contract_main(["state", "--path", tmp, "--action", "advance", "--phase", "1"]), 0)

    def test_scenario_css_audit_and_smoke_generator(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "style.css").write_text(".card { color: red !important; }\n", encoding="utf-8")
            (tmp_path / "page.html").write_text('<div id="test-banner"></div>', encoding="utf-8")

            # Scenario 8: Stylesheet & Specificity Audit
            self.assertEqual(contract_main(["inspect-css", "--path", str(tmp_path / "style.css")]), 0)
            self.assertEqual(contract_main(["inspect-css", "--path", str(tmp_path / "style.css"), "--strict"]), 1)

            # Scenario 23: Generate Scoped Smoke Test
            out_test = tmp_path / "test_smoke.py"
            self.assertEqual(contract_main(["generate-smoke-test", "--path", tmp, "--out", str(out_test)]), 0)
            self.assertTrue(out_test.is_file())


class TestPatcherAndEolScenarios(unittest.TestCase):
    """Verifies Scenarios 16-18: Line-ending normalizer, agnostic patch, and script injection."""

    def test_scenario_eol_normalization(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            f = tmp_path / "legacy.js"
            f.write_bytes(b"var a = 1;\r\nvar b = 2;\r\n")

            # Scenario 16: Normalize to LF
            self.assertEqual(contract_main(["normalize-eol", "--path", str(f), "--to", "lf"]), 0)
            self.assertEqual(f.read_bytes(), b"var a = 1;\nvar b = 2;\n")

            # Normalize back to CRLF
            self.assertEqual(contract_main(["normalize-eol", "--path", str(f), "--to", "crlf"]), 0)
            self.assertEqual(f.read_bytes(), b"var a = 1;\r\nvar b = 2;\r\n")

    def test_scenario_patch_and_inject_scripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            html = tmp_path / "index.html"
            html.write_text("<html><head><script src=\"app.js\"></script></head><body></body></html>\n", encoding="utf-8")

            # Scenario 18: Safe HTML script injection
            inject_cmd = ["inject-scripts", "--html", str(html), "--before", "app.js", "--scripts", "part1.js", "part2.js"]
            self.assertEqual(contract_main(inject_cmd), 0)
            content = html.read_text(encoding="utf-8")
            self.assertIn('<script src="part1.js"></script>', content)
            self.assertIn('<script src="part2.js"></script>', content)

            # Scenario 17: Line-ending agnostic patch
            patch_cmd = ["patch", "--file", str(html), "--find", "part1.js", "--replace", "modular1.js"]
            self.assertEqual(contract_main(patch_cmd), 0)
            self.assertIn("modular1.js", html.read_text(encoding="utf-8"))


class TestDiagnosticAndAuxiliaryScenarios(unittest.TestCase):
    """Verifies Scenarios 15, 19-22, 24: Unified diagnostics, headless UI, and tool probing."""

    def test_scenario_unified_diagnose_and_probe_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "index.html").write_text('<div id="main-view"></div>', encoding="utf-8")
            contract_main(["capture", "--path", tmp])

            # Scenario 15: Unified 3-Tier Diagnostic
            self.assertEqual(contract_main(["diagnose", "--path", tmp]), 0)
            # Scenario 24: Discover Optional Tools
            self.assertEqual(contract_main(["probe-tools", "--path", tmp]), 0)

    def test_scenario_verify_ui_and_audit_container(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Scenario 20: Headless CDP Layout Audit (default headless)
            self.assertEqual(contract_main(["verify-ui", "--path", tmp]), 0)
            # Scenario 21: Live Browser UI Audit (with --live flag)
            self.assertEqual(contract_main(["verify-ui", "--path", tmp, "--live"]), 0)
            # Scenario 22: Container Sync Audit
            self.assertEqual(contract_main(["audit-container", "--path", tmp]), 0)

    def test_scenario_run_tests_forwarder(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            tests_dir = tmp_path / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_example.py").write_text(
                "import unittest\nclass DemoTest(unittest.TestCase):\n    def test_pass(self): self.assertTrue(True)\n",
                encoding="utf-8",
            )
            # Scenario 19: Virtualenv Test Runner Forwarder
            self.assertEqual(contract_main(["run-tests", "--path", tmp]), 0)


if __name__ == "__main__":
    unittest.main()
