#!/usr/bin/env python3
"""Unit tests for Defect Catalog SSOT & JIT Scaffolder (defect_catalog.py)."""

import json
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
    checkout_micro_branch,
    ensure_diagnostics_dir,
    load_catalog,
    reconcile_defect,
    save_catalog,
    scaffold_defect,
    scaffold_tactical_test,
)
from shadow_prober import DefectFinding, compute_fingerprint


class TestDefectCatalog(unittest.TestCase):
    """Test suite for defect catalog SSOT, git safety, and JIT scaffolding."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_ensure_diagnostics_dir_and_gitignore(self):
        diag_dir = ensure_diagnostics_dir(self.ws)
        self.assertTrue(diag_dir.is_dir())
        gitignore = diag_dir / ".gitignore"
        self.assertTrue(gitignore.is_file())
        content = gitignore.read_text(encoding="utf-8")
        self.assertIn("*", content)

    def test_save_and_load_catalog_roundtrip(self):
        fp = compute_fingerprint("MUTABLE_DEFAULT_ARG", "UserService.add_role", "roles=[]")
        defect = DefectFinding(
            id="DEFECT-001",
            fingerprint=fp,
            rule_id="MUTABLE_DEFAULT_ARG",
            category="BAD_LOGIC",
            severity="HIGH",
            track="tactical",
            file="src/user.py",
            line=42,
            symbol="UserService.add_role",
            message="Mutable default argument persists state.",
            suggested_fix="Replace with None.",
            status="quarantined",
        )

        json_path, md_path = save_catalog(self.ws, [defect])
        self.assertTrue(json_path.is_file())
        self.assertTrue(md_path.is_file())

        # Verify JSON SSOT
        loaded = load_catalog(self.ws)
        self.assertEqual(loaded["schema_version"], "1.0")
        self.assertEqual(loaded["summary"]["total"], 1)
        self.assertEqual(loaded["summary"]["by_track"]["tactical"], 1)
        self.assertEqual(loaded["summary"]["by_severity"]["HIGH"], 1)
        self.assertEqual(len(loaded["defects"]), 1)
        self.assertEqual(loaded["defects"][0]["id"], "DEFECT-001")
        self.assertEqual(loaded["defects"][0]["fingerprint"], fp)

        # Verify Markdown human report
        md_text = md_path.read_text(encoding="utf-8")
        self.assertIn("# Latent Defect & Code Smell Catalog", md_text)
        self.assertIn("DEFECT-001", md_text)
        self.assertIn(fp, md_text)
        self.assertIn("MUTABLE_DEFAULT_ARG", md_text)

    def test_reconcile_defect_line_shift_and_file_move(self):
        # 1. Line shift in existing file
        src_file = self.ws / "math_ops.py"
        src_file.write_text(
            "# Added comments at top\n# Shift lines\n\ndef calculate(a, b=[]):\n    return a\n",
            encoding="utf-8",
        )
        defect = {
            "id": "DEFECT-001",
            "file": "math_ops.py",
            "line": 1,  # Stale line
            "symbol": "calculate",
        }
        reconciled = reconcile_defect(self.ws, defect)
        self.assertEqual(reconciled["line"], 4)

        # 2. File moved to subfolder
        sub_dir = self.ws / "services"
        sub_dir.mkdir(parents=True, exist_ok=True)
        new_file = sub_dir / "worker.py"
        new_file.write_text("def dispatch_task(data=[]):\n    pass\n", encoding="utf-8")
        moved_defect = {
            "id": "DEFECT-002",
            "file": "old_worker.py",  # Stale file
            "line": 10,
            "symbol": "dispatch_task",
        }
        reconciled_moved = reconcile_defect(self.ws, moved_defect)
        self.assertEqual(reconciled_moved["file"], "services/worker.py")
        self.assertEqual(reconciled_moved["line"], 1)

    def test_check_git_dirty_filters_diagnostics_and_refactor(self):
        # Initialize a temporary git repository
        try:
            subprocess.run(["git", "init"], cwd=self.ws, capture_output=True, check=True)
            subprocess.run(["git", "config", "user.name", "Tester"], cwd=self.ws, capture_output=True, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.ws, capture_output=True, check=True)
        except Exception:
            self.skipTest("git command not available")

        # Clean repo initial commit
        initial = self.ws / "README.md"
        initial.write_text("hello\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=self.ws, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.ws, capture_output=True, check=True)

        # 1. Changes in .diagnostics/ or .refactor/ should NOT be treated as dirty tree
        diag_file = self.ws / ".diagnostics" / "defect_catalog.json"
        diag_file.parent.mkdir(parents=True, exist_ok=True)
        diag_file.write_text("{}", encoding="utf-8")

        refactor_file = self.ws / ".refactor" / "plan.md"
        refactor_file.parent.mkdir(parents=True, exist_ok=True)
        refactor_file.write_text("refactor\n", encoding="utf-8")

        is_dirty, files = check_git_dirty(self.ws)
        self.assertFalse(is_dirty)
        self.assertEqual(files, [])

        # 2. Modifying application code marks tree as dirty
        app_file = self.ws / "app.py"
        app_file.write_text("code\n", encoding="utf-8")
        is_dirty, files = check_git_dirty(self.ws)
        self.assertTrue(is_dirty)
        self.assertIn("app.py", files)

    def test_scaffold_tactical_test_red_to_green_cycle(self):
        # Create defective source file
        src_file = self.ws / "calc.py"
        src_file.write_text("def append_val(val, target=[]):\n    target.append(val)\n    return target\n", encoding="utf-8")

        defect = {
            "id": "DEFECT-001",
            "fingerprint": "DEF-MUTABLE-123456",
            "rule_id": "MUTABLE_DEFAULT_ARG",
            "category": "BAD_LOGIC",
            "severity": "HIGH",
            "track": "tactical",
            "file": "calc.py",
            "line": 1,
            "symbol": "append_val",
            "message": "Mutable default argument.",
            "suggested_fix": "Replace with None.",
            "status": "quarantined",
        }
        save_catalog(self.ws, [defect])

        # Scaffold tactical reproduction test
        res = scaffold_defect(self.ws, "DEFECT-001")
        self.assertEqual(res["status"], "scaffolded")
        self.assertEqual(res["track"], "tactical")
        test_file = Path(res["test_file"])
        self.assertTrue(test_file.is_file())

        # Step 1: Run reproduction test -> Must fail RED initially
        proc_red = subprocess.run(
            [sys.executable, "-m", "unittest", str(test_file)],
            cwd=self.ws, capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(proc_red.returncode, 0)
        self.assertIn("Invariant violation", proc_red.stderr + proc_red.stdout)

        # Step 2: Apply suggested fix to source file
        src_file.write_text(
            "def append_val(val, target=None):\n    if target is None:\n        target = []\n    target.append(val)\n    return target\n",
            encoding="utf-8",
        )

        # Step 3: Re-verify reproduction test -> Must pass GREEN!
        proc_green = subprocess.run(
            [sys.executable, "-m", "unittest", str(test_file)],
            cwd=self.ws, capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc_green.returncode, 0)

        # Step 4: Verify catalog status updated to 'scaffolded'
        updated_catalog = load_catalog(self.ws)
        self.assertEqual(updated_catalog["defects"][0]["status"], "scaffolded")

    def test_scaffold_architectural_elevation(self):
        defect = {
            "id": "DEFECT-002",
            "fingerprint": "DEF-ASYNC-987654",
            "rule_id": "UNHANDLED_ASYNC_COROUTINE",
            "category": "BAD_LOGIC",
            "severity": "HIGH",
            "track": "architectural",
            "file": "events/dispatcher.py",
            "line": 40,
            "symbol": "EventDispatcher.emit",
            "message": "Coroutine is not awaited.",
            "suggested_fix": "Prepend await or schedule task.",
            "status": "quarantined",
        }
        save_catalog(self.ws, [defect])

        # Scaffolding without --fix should produce Architectural Elevation Brief
        res = scaffold_defect(self.ws, "DEFECT-002")
        self.assertEqual(res["status"], "elevated")
        self.assertEqual(res["track"], "architectural")
        self.assertIn("ARCHITECTURAL ELEVATION BRIEF", res["brief"])
        self.assertIn("/frontier-architect", res["brief"])
        self.assertIn("/grill-me", res["brief"])

        # Verify catalog status updated to 'elevated'
        updated = load_catalog(self.ws)
        self.assertEqual(updated["defects"][0]["status"], "elevated")

    def test_scaffold_defect_not_found(self):
        with self.assertRaises(ValueError):
            scaffold_defect(self.ws, "DEFECT-999")

    def test_resolve_and_dismiss_defect_lifecycle(self):
        from defect_catalog import update_defect_status

        d1 = DefectFinding(
            id="DEFECT-001", fingerprint="DEF-MUTABLE-111111", rule_id="MUTABLE_DEFAULT_ARG",
            category="BAD_LOGIC", severity="HIGH", track="tactical", file="a.py", line=1,
            symbol="fn1", message="msg1", suggested_fix="fix1",
        )
        d2 = DefectFinding(
            id="DEFECT-002", fingerprint="DEF-CALL-222222", rule_id="CALL_ARG_COUNT_MISMATCH",
            category="CALLABLE_MISMATCH", severity="HIGH", track="tactical", file="b.py", line=5,
            symbol="fn2", message="msg2", suggested_fix="fix2",
        )
        save_catalog(self.ws, [d1, d2])

        update_defect_status(self.ws, "DEFECT-001", "resolved", note="Replaced mutable default with None")
        update_defect_status(self.ws, "DEF-CALL-222222", "dismissed", note="False positive on dynamic proxy")

        cat = load_catalog(self.ws)
        self.assertEqual(cat["summary"]["total"], 0)
        self.assertEqual(cat["summary"]["active"], 0)
        self.assertEqual(cat["summary"]["resolved"], 1)
        self.assertEqual(cat["summary"]["dismissed"], 1)
        self.assertEqual(cat["summary"]["total_tracked"], 2)

        md_text = (self.ws / ".diagnostics" / "DEFECT_CATALOG.md").read_text(encoding="utf-8")
        self.assertIn("## Resolved & Dismissed History", md_text)
        self.assertIn("Replaced mutable default with None", md_text)
        self.assertIn("False positive on dynamic proxy", md_text)

    def test_reconcile_scan_auto_resolves_fixed_and_preserves_dismissed(self):
        from defect_catalog import update_defect_status
        from shadow_prober import scan_and_save

        src = self.ws / "worker.py"
        src.write_text("def job1(a=[]):\n    pass\ndef job2(b={}):\n    pass\n", encoding="utf-8")

        scan_and_save(self.ws)
        cat1 = load_catalog(self.ws)
        self.assertEqual(cat1["summary"]["active"], 2)

        # Dismiss job2
        update_defect_status(self.ws, "DEFECT-002", "dismissed", note="Accepted config dict")
        # Fix job1 in code
        src.write_text("def job1(a=None):\n    pass\ndef job2(b={}):\n    pass\n", encoding="utf-8")

        # Re-scan with reconciliation
        scan_and_save(self.ws, reconcile_scan=True, prune=False)
        cat2 = load_catalog(self.ws)
        self.assertEqual(cat2["summary"]["active"], 0)
        self.assertEqual(cat2["summary"]["resolved"], 1)
        self.assertEqual(cat2["summary"]["dismissed"], 1)

        # Re-scan with prune=True drops vanished job1
        scan_and_save(self.ws, reconcile_scan=True, prune=True)
        cat3 = load_catalog(self.ws)
        self.assertEqual(cat3["summary"]["total_tracked"], 1)
        self.assertEqual(cat3["defects"][0]["status"], "dismissed")

    def test_scaffold_js_silent_catch_red_to_green_without_syntax_error(self):
        js_file = self.ws / "telemetry.js"
        js_file.write_text("try { JSON.parse(raw); } catch (err) {}\n", encoding="utf-8")

        defect = {
            "id": "DEFECT-001",
            "fingerprint": "DEF-SILENT-999999",
            "rule_id": "SILENT_BARE_EXCEPT",
            "category": "EXCEPTION_SMELL",
            "severity": "MEDIUM",
            "track": "tactical",
            "file": "telemetry.js",
            "line": 1,
            "symbol": "telemetry.js",
            "message": "Empty catch block suppresses errors.",
            "suggested_fix": "Log with console.debug.",
            "status": "quarantined",
        }
        save_catalog(self.ws, [defect])
        res = scaffold_defect(self.ws, "DEFECT-001")
        test_file = Path(res["test_file"])

        # Red: Fails invariant assertion (not SyntaxError)
        proc_red = subprocess.run([sys.executable, "-m", "unittest", str(test_file)], cwd=self.ws, capture_output=True, text=True, check=False)
        self.assertNotEqual(proc_red.returncode, 0)
        self.assertIn("Empty catch block suppresses errors", proc_red.stderr + proc_red.stdout)

        # Green: Add console.debug inside catch
        js_file.write_text("try { JSON.parse(raw); } catch (err) { console.debug(err); }\n", encoding="utf-8")
        proc_green = subprocess.run([sys.executable, "-m", "unittest", str(test_file)], cwd=self.ws, capture_output=True, text=True, check=False)
        self.assertEqual(proc_green.returncode, 0)


if __name__ == "__main__":
    unittest.main()
