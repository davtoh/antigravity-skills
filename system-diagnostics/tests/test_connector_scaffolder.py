#!/usr/bin/env python3
"""Scaffolder tests: bootstrap parity (Claude layout), flag wiring, CLI validation."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import connector_scaffolder
import trace_cli


class TestScaffolder(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="sysdiag_scaf_")).resolve()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_without_flag_has_no_observation_code(self):
        for fw in ("fastapi", "flask", "generic"):
            text = connector_scaffolder.scaffold_connector(self.root, fw).read_text(encoding="utf-8")
            self.assertNotIn("register_observation_routes", text)
            self.assertIn("SYSTEM_DIAGNOSTICS_DIR", text)
            self.assertNotIn("@@ENGINE_BOOTSTRAP@@", text)
            compile(text, "bridge.py", "exec")

    def test_with_flag_adds_routes_for_every_framework(self):
        for fw in ("fastapi", "flask", "generic"):
            text = connector_scaffolder.scaffold_connector(self.root, fw, with_observations=True).read_text(encoding="utf-8")
            self.assertIn("def register_observation_routes", text)
            self.assertIn("handle_diagnostics_request", text)
            compile(text, "bridge.py", "exec")

    def test_claude_layout_finds_engine_from_another_cwd(self):
        skills = self.root / ".claude" / "skills"
        skills.mkdir(parents=True)
        shutil.copytree(SCRIPTS_DIR.parent, skills / "system-diagnostics", ignore=shutil.ignore_patterns("tests", "__pycache__"))
        connector_scaffolder.scaffold_connector(self.root, "generic", "services", with_observations=True)
        other = Path(tempfile.mkdtemp()).resolve()
        env = {k: v for k, v in os.environ.items() if k != "SYSTEM_DIAGNOSTICS_DIR"}
        env["HOME"] = str(other)
        code = "import sys; sys.path.insert(0, %r); import diagnostic_bridge as b; print(b._obs is not None)" % str(self.root / "services")
        out = subprocess.run([sys.executable, "-c", code], cwd=other, env=env, capture_output=True, text=True)
        shutil.rmtree(other, ignore_errors=True)
        self.assertEqual(out.stdout.strip(), "True", out.stderr)

    def test_gemini_layout_finds_engine_from_another_cwd(self):
        fake_home = Path(tempfile.mkdtemp(prefix="sysdiag_home_")).resolve()
        try:
            skills = fake_home / ".gemini" / "config" / "skills"
            skills.mkdir(parents=True)
            shutil.copytree(SCRIPTS_DIR.parent, skills / "system-diagnostics", ignore=shutil.ignore_patterns("tests", "__pycache__"))
            connector_scaffolder.scaffold_connector(self.root, "generic", "services", with_observations=True)
            other = Path(tempfile.mkdtemp()).resolve()
            env = {k: v for k, v in os.environ.items() if k != "SYSTEM_DIAGNOSTICS_DIR"}
            env["HOME"] = str(fake_home)
            env["USERPROFILE"] = str(fake_home)
            code = "import sys; sys.path.insert(0, %r); import diagnostic_bridge as b; print(b._obs is not None)" % str(self.root / "services")
            out = subprocess.run([sys.executable, "-c", code], cwd=other, env=env, capture_output=True, text=True)
            shutil.rmtree(other, ignore_errors=True)
            self.assertEqual(out.stdout.strip(), "True", out.stderr)
        finally:
            shutil.rmtree(fake_home, ignore_errors=True)

    def test_cli_rejects_flag_without_scaffold(self):
        args = argparse.Namespace(with_observations=True, scaffold=None)
        self.assertEqual(trace_cli.cmd_traces(args, None), 2)


if __name__ == "__main__":
    unittest.main()
