#!/usr/bin/env python3
"""Unit tests for probe_runner and dynamic probe extensions."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Add scripts directory to sys.path
TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import diagnose
import probe_runner

class TestProbeRunner(unittest.TestCase):
    """Test suite for probe discovery, execution, scaffolding, and promotion."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="test_probe_")
        self.ws_root = Path(self.tmp_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_list_probes_finds_builtin(self):
        """Verify built-in camera_hardware probe is discovered."""
        probes = probe_runner.list_probes(workspace_root=self.ws_root)
        names = [p.name for p in probes]
        self.assertIn("camera_hardware", names)

    def test_scaffold_probe_creates_valid_template(self):
        """Verify scaffolding produces a valid python file with standard protocol."""
        target_dir = self.ws_root / ".diagnostics" / "probes"
        created = probe_runner.scaffold_probe("db_health", domain="database", target_dir=target_dir)
        self.assertTrue(created.is_file())
        self.assertEqual(created.name, "db_health.py")

        # Verify discovery of new probe
        probes = probe_runner.list_probes(workspace_root=self.ws_root)
        names = [p.name for p in probes]
        self.assertIn("db_health", names)

    def test_run_probe_executes_successfully(self):
        """Verify probe execution captures stdout and parses JSON telemetry."""
        target_dir = self.ws_root / ".diagnostics" / "probes"
        probe_runner.scaffold_probe("dummy_probe", domain="test", target_dir=target_dir)

        result = probe_runner.run_probe("dummy_probe", workspace_root=self.ws_root)
        self.assertEqual(result.get("status"), "ok")
        self.assertEqual(result.get("probe"), "dummy_probe")
        self.assertIn("latency_ms", result)

    def test_save_probe_promotes_script(self):
        """Verify promoting a scratch script to workspace probe registry."""
        scratch_script = self.ws_root / "scratch_test.py"
        scratch_script.write_text(
            '''import json
def main():
    print(json.dumps({"status": "ok", "summary": "Custom scratch check", "details": {"val": 42}}))
if __name__ == "__main__":
    main()
''',
            encoding="utf-8",
        )

        saved = probe_runner.save_probe(
            str(scratch_script),
            "custom_check",
            scope="workspace",
            workspace_root=self.ws_root,
        )
        self.assertTrue(saved.is_file())
        self.assertEqual(saved.name, "custom_check.py")

        # Test running promoted probe
        result = probe_runner.run_probe("custom_check", workspace_root=self.ws_root)
        self.assertEqual(result.get("status"), "ok")
        self.assertEqual(result.get("summary"), "Custom scratch check")
        self.assertEqual(result.get("details", {}).get("val"), 42)

    def test_diagnose_cli_probe_list(self):
        """Verify diagnose.py CLI probe subcommands."""
        parser = diagnose.build_parser()
        args = parser.parse_args(["probe", "list", "--path", str(self.ws_root)])
        ret = diagnose.cmd_probe(args)
        self.assertEqual(ret, 0)

if __name__ == "__main__":
    unittest.main()
