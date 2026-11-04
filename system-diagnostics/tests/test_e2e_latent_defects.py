#!/usr/bin/env python3
"""End-to-End Integration Tests for Latent Defect & Smell Protocol (Tier 3 Slice 4).

Covers:
1. Dual-Key fingerprint stability across file moves and line shifts.
2. Isolated PEP 578 Python sandbox side-effect containment & timeouts.
3. Dirty-tree git pre-flight safety and non-destructive branch guards.
4. Dual-track remediation scaffolding (Tactical Red-to-Green vs Architectural Elevation).
"""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from defect_catalog import (
    check_git_dirty,
    load_catalog,
    reconcile_defect,
    save_catalog,
    scaffold_defect,
)
from shadow_prober import (
    DefectFinding,
    compute_fingerprint,
    run_isolated_python_sandbox,
    scan_and_save,
    scan_path,
)


class TestDualKeyFingerprintStability(unittest.TestCase):
    """End-to-end tests for Dual-Key fingerprint stability across file moves and shifts."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_fingerprint_stability_across_file_move_and_line_shift(self):
        # 1. Author source file in legacy location
        legacy_dir = self.ws / "legacy" / "services"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        legacy_file = legacy_dir / "calculator.py"
        legacy_file.write_text(
            "def calculate_total(amounts, ledger=[]):\n"
            "    ledger.extend(amounts)\n"
            "    return sum(ledger)\n",
            encoding="utf-8",
        )

        # 2. Run initial scan and persist SSOT catalog
        findings, json_path, md_path = scan_and_save(self.ws)
        self.assertEqual(len(findings), 1)
        original_fp = findings[0].fingerprint
        self.assertTrue(original_fp.startswith("DEF-MUTABLE-"))
        self.assertEqual(findings[0].id, "DEFECT-001")
        self.assertEqual(findings[0].file, "legacy/services/calculator.py")
        self.assertEqual(findings[0].line, 1)

        # 3. Simulate file move to new domain path and line shift with docstring
        new_dir = self.ws / "core" / "billing"
        new_dir.mkdir(parents=True, exist_ok=True)
        new_file = new_dir / "ledger_service.py"
        new_file.write_text(
            '"""Billing and ledger service module.\n\n'
            'Refactored from legacy architecture.\n'
            '"""\n\n'
            "# Helper utility\n"
            "def audit_log(msg):\n"
            "    pass\n\n\n"
            "def calculate_total(amounts, ledger=[]):\n"
            "    ledger.extend(amounts)\n"
            "    return sum(ledger)\n",
            encoding="utf-8",
        )
        legacy_file.unlink()

        # 4. Verify catalog reconciliation updates path/line while fingerprint remains invariant
        catalog = load_catalog(self.ws)
        stale_entry = catalog["defects"][0]
        reconciled = reconcile_defect(self.ws, stale_entry)

        self.assertEqual(reconciled["id"], "DEFECT-001")
        self.assertEqual(reconciled["fingerprint"], original_fp)  # Invariant!
        self.assertEqual(reconciled["file"], "core/billing/ledger_service.py")
        self.assertEqual(reconciled["line"], 11)  # Accurately shifted!

        # 5. Verify rescanning reproduces the exact same fingerprint
        new_findings = scan_path(self.ws)
        self.assertEqual(len(new_findings), 1)
        self.assertEqual(new_findings[0].fingerprint, original_fp)

        # 6. Verify JIT scaffolding resolves by invariant fingerprint
        save_catalog(self.ws, [reconciled])
        res = scaffold_defect(self.ws, original_fp)
        self.assertEqual(res["status"], "scaffolded")
        self.assertEqual(res["defect"]["id"], "DEFECT-001")
        self.assertEqual(res["defect"]["file"], "core/billing/ledger_service.py")


class TestSandboxSideEffectContainment(unittest.TestCase):
    """End-to-end tests for PEP 578 audit sandbox isolation and timeouts."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sandbox_blocks_subprocess_and_os_system(self):
        script_file = self.ws / "risky_ops.py"
        script_file.write_text(
            "import os, subprocess\n"
            "def try_subprocess():\n"
            "    subprocess.Popen(['echo', 'blocked'])\n"
            "def try_os_system():\n"
            "    os.system('echo blocked')\n",
            encoding="utf-8",
        )

        # Subprocess call must be blocked by PEP 578 audit hook without throwing unhandled exceptions
        err_sub = run_isolated_python_sandbox(script_file, "try_subprocess", timeout_sec=2.0)
        self.assertIsNone(err_sub)

        # os.system call must be blocked by audit hook
        err_sys = run_isolated_python_sandbox(script_file, "try_os_system", timeout_sec=2.0)
        self.assertIsNone(err_sys)

    def test_sandbox_timeout_terminates_runaway_loop(self):
        infinite_file = self.ws / "hang.py"
        infinite_file.write_text(
            "import time\n"
            "def infinite_loop():\n"
            "    while True:\n"
            "        time.sleep(0.01)\n",
            encoding="utf-8",
        )

        # Timeout of 0.5s must cleanly terminate runaway callable
        err = run_isolated_python_sandbox(infinite_file, "infinite_loop", timeout_sec=0.5)
        self.assertIsNone(err)

    def test_sandbox_detects_missing_positional_args(self):
        func_file = self.ws / "calc.py"
        func_file.write_text(
            "def requires_args(a, b, c):\n"
            "    return a + b + c\n",
            encoding="utf-8",
        )

        err = run_isolated_python_sandbox(func_file, "requires_args", timeout_sec=2.0)
        self.assertIsNotNone(err)
        self.assertIn("TypeError", err)
        self.assertIn("missing 3 required positional arguments", err)


class TestDirtyTreeBranchSafety(unittest.TestCase):
    """End-to-end tests for git branch safety and uncommitted work protection."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        try:
            subprocess.run(["git", "init"], cwd=self.ws, capture_output=True, check=True)
            subprocess.run(["git", "config", "user.name", "Tester"], cwd=self.ws, capture_output=True, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.ws, capture_output=True, check=True)
            # Create main branch initial commit
            (self.ws / "README.md").write_text("# Project\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=self.ws, capture_output=True, check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=self.ws, capture_output=True, check=True)
        except Exception:
            self.skipTest("git command not available")

    def tearDown(self):
        self.tmp.cleanup()

    def _get_current_branch(self) -> str:
        proc = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                              cwd=self.ws, capture_output=True, text=True, check=True)
        return proc.stdout.strip()

    def test_clean_tree_creates_and_checks_out_micro_branch(self):
        (self.ws / "calc.py").write_text("def run(items=[]):\n    pass\n", encoding="utf-8")
        subprocess.run(["git", "add", "calc.py"], cwd=self.ws, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "add calc"], cwd=self.ws, capture_output=True, check=True)

        scan_and_save(self.ws)
        res = scaffold_defect(self.ws, "DEFECT-001", branch=True)

        self.assertEqual(res["status"], "scaffolded")
        self.assertEqual(res["branch"], "fix/defect-001")
        self.assertEqual(self._get_current_branch(), "fix/defect-001")

    def test_diagnostic_and_refactor_changes_do_not_block_branching(self):
        (self.ws / "calc.py").write_text("def run(items=[]):\n    pass\n", encoding="utf-8")
        subprocess.run(["git", "add", "calc.py"], cwd=self.ws, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "add calc"], cwd=self.ws, capture_output=True, check=True)

        scan_and_save(self.ws)
        # Touch .refactor/ and .diagnostics/ files
        (self.ws / ".refactor").mkdir(parents=True, exist_ok=True)
        (self.ws / ".refactor" / "state.json").write_text('{"phase": 1}\n', encoding="utf-8")

        is_dirty, files = check_git_dirty(self.ws)
        self.assertFalse(is_dirty)

        res = scaffold_defect(self.ws, "DEFECT-001", branch=True)
        self.assertEqual(res["branch"], "fix/defect-001")

    def test_dirty_tree_aborts_branching_safely_protecting_user_work(self):
        (self.ws / "calc.py").write_text("def run(items=[]):\n    pass\n", encoding="utf-8")
        subprocess.run(["git", "add", "calc.py"], cwd=self.ws, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "add calc"], cwd=self.ws, capture_output=True, check=True)

        scan_and_save(self.ws)
        # Dirty tree by creating uncommitted application file
        (self.ws / "uncommitted_feature.py").write_text("# Work in progress\n", encoding="utf-8")

        initial_branch = self._get_current_branch()
        res = scaffold_defect(self.ws, "DEFECT-001", branch=True)

        # Must skip branching to prevent losing unstaged edits
        self.assertIsNone(res["branch"])
        self.assertEqual(self._get_current_branch(), initial_branch)
        # Test file must still be generated safely in-place
        self.assertTrue(Path(res["test_file"]).is_file())


class TestDualTrackScaffoldingIntegration(unittest.TestCase):
    """End-to-end tests for Dual-Track remediation (Tactical Red/Green vs Architectural Brief)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_tactical_defect_full_red_to_green_cycle(self):
        src_file = self.ws / "user_service.py"
        src_file.write_text(
            "def register_user(username, roles=[]):\n"
            "    roles.append(username)\n"
            "    return roles\n",
            encoding="utf-8",
        )

        scan_and_save(self.ws)
        res = scaffold_defect(self.ws, "DEFECT-001")
        self.assertEqual(res["status"], "scaffolded")
        self.assertEqual(res["track"], "tactical")
        test_file = Path(res["test_file"])

        # Red: Initial test run fails
        proc_red = subprocess.run([sys.executable, "-m", "unittest", str(test_file)],
                                  cwd=self.ws, capture_output=True, text=True, check=False)
        self.assertNotEqual(proc_red.returncode, 0)
        self.assertIn("Invariant violation", proc_red.stderr + proc_red.stdout)

        # Green: Apply suggested fix
        src_file.write_text(
            "def register_user(username, roles=None):\n"
            "    if roles is None:\n"
            "        roles = []\n"
            "    roles.append(username)\n"
            "    return roles\n",
            encoding="utf-8",
        )
        proc_green = subprocess.run([sys.executable, "-m", "unittest", str(test_file)],
                                    cwd=self.ws, capture_output=True, text=True, check=False)
        self.assertEqual(proc_green.returncode, 0)

    def test_architectural_defect_emits_elevation_brief(self):
        eval_file = self.ws / "security.py"
        eval_file.write_text("def parse_expression(expr):\n    return eval(expr)\n", encoding="utf-8")

        findings, _, _ = scan_and_save(self.ws)
        self.assertEqual(findings[0].track, "architectural")

        res = scaffold_defect(self.ws, "DEFECT-001")
        self.assertEqual(res["status"], "elevated")
        self.assertEqual(res["track"], "architectural")
        self.assertIn("ARCHITECTURAL ELEVATION BRIEF", res["brief"])
        self.assertIn("/frontier-architect", res["brief"])
        self.assertIn("/grill-me", res["brief"])
        # No unit test generated for architectural elevation
        self.assertFalse((self.ws / "tests" / "quarantine" / "test_defect_001.py").exists())


if __name__ == "__main__":
    unittest.main()

